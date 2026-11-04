"""Constraint-aware contrastive triplet generation.

Bridges the symbolic rule engine and UnixCoder fine-tuning. Given the
SymbolicFacts for a Rails app + the existing ROR-MSI dependency_graph
JSON, produces (anchor, positive, negative) triplets where:

  positive = a class that should plausibly co-locate with the anchor
  negative = a hard negative — a class that looks similar (same role, same
             role suffix) but is symbolically forbidden to co-locate

The point of "hard negatives" is non-trivial. For Java microservice triplets,
MonoEmbed [Sellami Ch.3] forced the negative to come from the *same monolith*
as the anchor, so the model couldn't cheat on project-specific cues. We
extend that idea: our hardest negatives come from the same *Rails role*
(controller-vs-controller, model-vs-model) but from disjoint bounded contexts
or with no association/coupling path. That forces UnixCoder to learn the
domain semantics under the surface boilerplate.

Three positive sources, in priority order:
  1. must-link facts (associations, hard symbolic supervision)
  2. dependency-graph co-citation (classes in the same call neighborhood)
  3. shared-data-entity coupling (high data_associations overlap)

Three negative sources, in priority order:
  1. cannot-link facts (namespace boundaries — hardest)
  2. same-role / different-cluster heuristic
  3. random in-app class with no dependency edge to the anchor

Triplets are deduplicated and the ratio of source types is balanced so the
model doesn't overfit on any single supervision signal.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from neurosymbolic.symbolic.rules import (
    SymbolicFacts,
    extract_facts,
    extract_facts_from_rails_app,
)


@dataclass(frozen=True)
class Triplet:
    anchor: str
    positive: str
    negative: str
    pos_source: str   # "must_link" | "cocite" | "shared_entity"
    neg_source: str   # "cannot_link" | "same_role" | "random"

    def as_tuple(self) -> tuple[str, str, str]:
        return (self.anchor, self.positive, self.negative)


def _load_dep_graph(experiment_json: Path) -> tuple[dict[str, dict[str, int]], dict[str, list[str]]]:
    """Load dependency_graph and data_associations from any ROR-MSI exp_*.json.

    Any experiment file works — the graph is parameter-independent. We pick
    the first one we find for each app.
    """
    d = json.loads(experiment_json.read_text())
    return d.get("dependency_graph", {}), d.get("data_associations", {})


def _pick_experiment_json(app_dir: Path) -> Path | None:
    """Pick the best exp_*.json under `app_dir`.

    Preference: MVC two-phase (`_mvc.json`) > Rails-aware HC
    (`_rails_aware.json`) > legacy ROR-MSI (any other `exp_*.json`). The
    dependency graph in each variant is what the triplet generator needs
    for the cocite positive source; richer graphs yield richer triplets.
    """
    candidates = sorted(app_dir.glob("exp_*.json"))
    if not candidates:
        return None
    for suffix in ("_mvc.json", "_rails_aware.json"):
        for c in candidates:
            if c.name.endswith(suffix):
                return c
    # Fall back to any plain exp_*.json (excluding suffixed variants).
    suffixed = {"_mvc.json", "_rails_aware.json", "_gravity.json"}
    for c in candidates:
        if not any(c.name.endswith(s) for s in suffixed):
            return c
    return candidates[0]


def _role_index(facts: SymbolicFacts) -> dict[str, str]:
    """Inverse of role_groups: class → role."""
    out: dict[str, str] = {}
    for role, members in facts.role_groups.items():
        for c in members:
            out[c] = role
    return out


def _coupled_neighbors(graph: dict[str, dict[str, int]], cls: str, k: int = 5) -> list[str]:
    """Top-k most-called neighbors of `cls` in the dependency graph (excluding
    self-loops). Used as positive candidates beyond explicit associations."""
    neighbors = graph.get(cls, {})
    ranked = sorted(
        ((n, w) for n, w in neighbors.items() if n != cls),
        key=lambda x: -x[1],
    )
    return [n for n, _ in ranked[:k]]


def _shared_entity_partners(
    data_assoc: dict[str, list[str]], cls: str, min_overlap: int = 1
) -> list[str]:
    """Classes sharing ≥ min_overlap data entities with `cls`."""
    own = set(data_assoc.get(cls, []))
    if not own:
        return []
    partners: list[tuple[str, int]] = []
    for other, ents in data_assoc.items():
        if other == cls:
            continue
        overlap = len(own & set(ents))
        if overlap >= min_overlap:
            partners.append((other, overlap))
    partners.sort(key=lambda x: -x[1])
    return [c for c, _ in partners]


def _must_link_partners(facts: SymbolicFacts, cls: str) -> list[str]:
    out: list[str] = []
    for a, b, _ in facts.must_link:
        if a == cls and b != cls:
            out.append(b)
        elif b == cls and a != cls:
            out.append(a)
    return out


def _cannot_link_partners(facts: SymbolicFacts, cls: str) -> set[str]:
    """Full expansion of cannot-link including the namespace cross-product."""
    out: set[str] = set()
    for a, b in facts.iter_cannot_link():
        if a == cls and b != cls:
            out.add(b)
        elif b == cls and a != cls:
            out.add(a)
    return out


def _connected(graph: dict[str, dict[str, int]], a: str, b: str) -> bool:
    """True iff there's a direct edge a→b or b→a in the call graph."""
    if a in graph and b in graph[a]:
        return True
    if b in graph and a in graph[b]:
        return True
    return False


def generate_triplets(
    facts: SymbolicFacts,
    graph: dict[str, dict[str, int]],
    data_assoc: dict[str, list[str]],
    *,
    target_count: int = 1000,
    pos_mix: tuple[float, float, float] = (0.5, 0.3, 0.2),
    neg_mix: tuple[float, float, float] = (0.5, 0.3, 0.2),
    max_per_class_frac: float = 0.05,
    seed: int = 42,
) -> list[Triplet]:
    """Sample up to `target_count` triplets with a controlled source mix.

    `pos_mix` = fractions for (must_link, cocite, shared_entity).
    `neg_mix` = fractions for (cannot_link, same_role, random).

    The mix is honored *up to availability*: e.g. Industrial-X has no must-link, so
    its triplets fall back to the next priority. We log how the mix actually
    landed at the end so the caller can spot under-served apps.
    """
    rng = random.Random(seed)
    role_of = _role_index(facts)
    # We deliberately do NOT restrict to dep-graph callers. The existing AST
    # call-graph misses models entirely (Rails models are mostly callees, not
    # callers), and dropping them would discard the strongest symbolic signal:
    # ActiveRecord associations between models. The neural layer is precisely
    # what should fix this blind spot.
    graph_nodes = set(graph.keys())
    for src, edges in graph.items():
        graph_nodes.update(edges.keys())
    active = set(facts.classes) | graph_nodes
    classes = [c for c in facts.classes if c in active]
    if len(classes) < 4:
        return []
    framework = set(facts.framework_noise)

    # Pre-compute per-class candidate pools, restricted to active classes.
    pos_must: dict[str, list[str]] = {}
    pos_cocite: dict[str, list[str]] = {}
    pos_entity: dict[str, list[str]] = {}
    neg_cannot: dict[str, list[str]] = {}
    neg_same_role: dict[str, list[str]] = {}
    neg_random_pool: dict[str, list[str]] = {}

    by_role: dict[str, list[str]] = {}
    for c in classes:
        by_role.setdefault(role_of.get(c, "unknown"), []).append(c)

    for c in classes:
        if c in framework:
            continue
        pos_must[c] = [p for p in _must_link_partners(facts, c) if p in active and p not in framework]
        pos_cocite[c] = [p for p in _coupled_neighbors(graph, c) if p in active and p not in framework and p != c]
        pos_entity[c] = [p for p in _shared_entity_partners(data_assoc, c) if p in active and p not in framework]
        neg_cannot[c] = sorted(_cannot_link_partners(facts, c) & active)
        role = role_of.get(c, "unknown")
        same_role = [o for o in by_role.get(role, []) if o != c and o not in framework]
        neg_same_role[c] = same_role
        neg_random_pool[c] = [o for o in classes if o != c and o not in framework]

    pos_targets = {
        "must_link": int(target_count * pos_mix[0]),
        "cocite": int(target_count * pos_mix[1]),
        "shared_entity": int(target_count * pos_mix[2]),
    }
    neg_targets = {
        "cannot_link": int(target_count * neg_mix[0]),
        "same_role": int(target_count * neg_mix[1]),
        "random": int(target_count * neg_mix[2]),
    }

    triplets: set[Triplet] = set()
    pos_emitted = {k: 0 for k in pos_targets}
    neg_emitted = {k: 0 for k in neg_targets}
    # Cap how many times any single class can appear in a given role across the
    # triplet set. Prevents one popular class (e.g. SearchController in Industrial-X,
    # used by many other classes) from saturating positives or negatives and
    # making the model overfit to "everything pairs with X."
    cap = max(5, int(target_count * max_per_class_frac))
    use_count: dict[tuple[str, str], int] = {}  # (class, role) -> count

    def _pos_at_cap(c: str) -> bool:
        return use_count.get((c, "positive"), 0) >= cap

    def _neg_at_cap(c: str) -> bool:
        return use_count.get((c, "negative"), 0) >= cap

    def _anchor_at_cap(c: str) -> bool:
        return use_count.get((c, "anchor"), 0) >= cap

    def _pick_pos(anchor: str) -> tuple[str | None, str]:
        # Choose a positive source that still has budget AND candidates.
        order = ["must_link", "cocite", "shared_entity"]
        rng.shuffle(order)
        # Prefer the source furthest below its target.
        order.sort(key=lambda k: pos_emitted[k] / max(1, pos_targets[k]))
        for src in order:
            if pos_emitted[src] >= pos_targets[src]:
                continue
            pool = {"must_link": pos_must, "cocite": pos_cocite, "shared_entity": pos_entity}[src][anchor]
            pool = [p for p in pool if not _pos_at_cap(p)]
            if not pool:
                continue
            return rng.choice(pool), src
        # All budgets exhausted — relaxed fallback (still respects availability and caps).
        for src in ("must_link", "cocite", "shared_entity"):
            pool = {"must_link": pos_must, "cocite": pos_cocite, "shared_entity": pos_entity}[src][anchor]
            pool = [p for p in pool if not _pos_at_cap(p)]
            if pool:
                return rng.choice(pool), src
        return None, ""

    def _pick_neg(anchor: str, positive: str) -> tuple[str | None, str]:
        order = ["cannot_link", "same_role", "random"]
        rng.shuffle(order)
        order.sort(key=lambda k: neg_emitted[k] / max(1, neg_targets[k]))
        for src in order:
            if neg_emitted[src] >= neg_targets[src]:
                continue
            pool = {"cannot_link": neg_cannot, "same_role": neg_same_role, "random": neg_random_pool}[src][anchor]
            # A negative must NOT be the positive, NOT in must-link with anchor,
            # NOT in shared_entity partners (avoid contradicting a soft positive),
            # and (for the random/same-role sources) NOT directly coupled to it.
            forbidden = (
                set(pos_must.get(anchor, []))
                | set(pos_entity.get(anchor, []))
                | {anchor, positive}
            )
            valid = [n for n in pool if n not in forbidden and not _neg_at_cap(n)]
            if src in ("same_role", "random"):
                valid = [n for n in valid if not _connected(graph, anchor, n)]
            if valid:
                return rng.choice(valid), src
        return None, ""

    # Each anchor gets multiple sampling chances proportional to remaining budget.
    # Round-robin over anchors keeps coverage even.
    anchors = [c for c in classes if c not in framework]
    rng.shuffle(anchors)
    max_attempts = target_count * 4
    attempts = 0
    while attempts < max_attempts and (
        sum(pos_emitted.values()) < target_count
        or sum(neg_emitted.values()) < target_count
    ):
        for anchor in anchors:
            attempts += 1
            if attempts >= max_attempts:
                break
            if _anchor_at_cap(anchor):
                continue
            pos, ps = _pick_pos(anchor)
            if pos is None:
                continue
            neg, ns = _pick_neg(anchor, pos)
            if neg is None:
                continue
            t = Triplet(anchor, pos, neg, ps, ns)
            if t in triplets:
                continue
            triplets.add(t)
            pos_emitted[ps] += 1
            neg_emitted[ns] += 1
            use_count[(anchor, "anchor")] = use_count.get((anchor, "anchor"), 0) + 1
            use_count[(pos, "positive")] = use_count.get((pos, "positive"), 0) + 1
            use_count[(neg, "negative")] = use_count.get((neg, "negative"), 0) + 1
            if len(triplets) >= target_count:
                break
        if len(triplets) >= target_count:
            break

    out = list(triplets)
    out.sort(key=lambda t: (t.anchor, t.positive, t.negative))
    return out


def generate_for_app(
    app_dir: Path,
    facts: SymbolicFacts,
    *,
    target_count: int = 1000,
    seed: int = 42,
) -> tuple[list[Triplet], dict[str, int]]:
    """Convenience: load the experiment JSON for `app_dir` and generate triplets.

    Returns (triplets, source_distribution_stats).
    """
    exp = _pick_experiment_json(app_dir)
    if exp is None:
        return [], {}
    graph, data_assoc = _load_dep_graph(exp)
    triplets = generate_triplets(
        facts, graph, data_assoc, target_count=target_count, seed=seed
    )
    stats: dict[str, int] = {}
    for t in triplets:
        stats[f"pos_{t.pos_source}"] = stats.get(f"pos_{t.pos_source}", 0) + 1
        stats[f"neg_{t.neg_source}"] = stats.get(f"neg_{t.neg_source}", 0) + 1
    return triplets, stats


def save_triplets(triplets: Iterable[Triplet], path: Path) -> None:
    payload = [
        {
            "anchor": t.anchor,
            "positive": t.positive,
            "negative": t.negative,
            "pos_source": t.pos_source,
            "neg_source": t.neg_source,
        }
        for t in triplets
    ]
    path.write_text(json.dumps(payload, indent=2))


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Generate contrastive triplets per app")
    p.add_argument("--results-dir", default="results")
    p.add_argument("--datasets-dir", default="datasets",
                   help="root of Rails app sources (rails-aware mode)")
    p.add_argument("--mode", choices=["rails-aware", "legacy"], default="rails-aware")
    p.add_argument("--facts-dir", default="neurosymbolic/output/facts")
    p.add_argument("--out-dir", default="neurosymbolic/output/triplets")
    p.add_argument("--target", type=int, default=1000, help="triplets per app")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--apps", nargs="*")
    args = p.parse_args()

    results_root = Path(args.results_dir)
    datasets_root = Path(args.datasets_dir)
    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    for app_dir in sorted(results_root.iterdir()):
        if not app_dir.is_dir():
            continue
        if args.apps and app_dir.name not in args.apps:
            continue
        # Re-extract facts to keep SymbolicFacts as the canonical source.
        ds_dir = datasets_root / app_dir.name
        if args.mode == "rails-aware" and (ds_dir / "app").is_dir():
            facts = extract_facts_from_rails_app(ds_dir, app_dir.name)
        elif (app_dir / "input").is_dir():
            facts = extract_facts(app_dir / "input", app_dir.name)
        else:
            print(f"[skip] no source dir for {app_dir.name}")
            continue
        triplets, stats = generate_for_app(
            app_dir, facts, target_count=args.target, seed=args.seed
        )
        out_path = out_root / f"{app_dir.name}.json"
        save_triplets(triplets, out_path)
        print(f"{app_dir.name}: {len(triplets)} triplets → {out_path}")
        print(f"  sources: {stats}")


if __name__ == "__main__":
    main()
