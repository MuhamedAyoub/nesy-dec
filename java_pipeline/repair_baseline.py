"""Constraint-repair baselines: what GraphRL-Dec adds over repairing its
teacher by rule (RESULTS.md, section 4).

GraphRL-Dec keeps the teacher's partition except where the cannot-link mask
forbids it. These baselines do the same repair with no learning, in the
environment GraphRL-Dec decodes in (same class order, same mask, same size
cap; EnvConfig as in run_gpu.decode for the variants without outliers):

  repair_masked   walk the classes in the environment's order; take the
                  teacher's service, or, when the mask forbids it, the
                  lowest-index legal service. This is the target sequence
                  behaviour cloning trains on (warmstart.py, eff_targets).
  repair_connect  the same walk; a forbidden class goes to the legal service
                  holding the most edge weight (G, both directions) to it.
  repair_post     no walk: start from the teacher's finished partition and
                  repeatedly move the class with the most cannot-link
                  violations that has somewhere legal to go, to the service
                  without a cannot-link partner
                  holding the most edge weight to it, until none is left.
                  K stays the teacher's; no size cap.

All three are deterministic. They are written to
results/<app>/baselines/repair_*.json, so results.py scores them. The
same three repairs of NeSy-Rep + Ward (baselines/unixcoder_ward_nesyrep.json)
instead of the RoR-MSI teacher are written as repair_nesyward_*.json: the
rule-based counterpart of GraphRL-Dec warm-started from NeSy-Rep + Ward.

Usage:
  python -m java_pipeline.repair_baseline          # write the baselines (needs the RL environment, torch)
  python3 -m java_pipeline.repair_baseline report  # after results.py: the comparison table, markdown
"""
from __future__ import annotations

import csv
import json
import statistics as st
import sys
from collections import defaultdict

from java_pipeline.subjects import OUT

APPS = ["acmeair", "daytrader7", "lit-jpetstore"]          # the apps with cannot-link pairs
VARIANTS = ("repair_masked", "repair_connect", "repair_post")


def weights(app: str) -> dict[tuple[str, str], float]:
    """Undirected edge weight of G."""
    G = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["dependency_graph"]
    w: dict[tuple[str, str], float] = defaultdict(float)
    for a, ds in G.items():
        items = ds.items() if isinstance(ds, dict) else ((d, 1.0) for d in ds)
        for b, x in items:
            if a != b:
                w[tuple(sorted((a, b)))] += float(x)
    return w


def start_partition(app: str, source: str) -> list[list[str]]:
    if source == "teacher":
        return [c["classes"] for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]]
    return json.loads((OUT / app / "baselines" / "unixcoder_ward_nesyrep.json").read_text())["partitions"]


def walk(app: str, connect: bool, source: str = "teacher") -> list[list[str]]:
    from neurosymbolic.rl.graph_env import EnvConfig, load_env_for_app
    from java_pipeline import rl_paths
    exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
    teacher = {c: k for k, cl in enumerate(start_partition(app, source)) for c in cl}
    p = rl_paths.paths(app)
    env = load_env_for_app(app, facts_path=p["facts"], graph_exp_json=p["graph_exp"], embeddings_pt=p["embeddings"],
                           config=EnvConfig(n_clusters=len(exp["clusters"])))
    w = weights(app)
    env.reset()
    while not env.done:
        node = env.current_node
        name = env.names[node]
        legal = env.legal_actions()
        a = teacher[name]
        if not legal[a]:
            if connect:
                score = defaultdict(float)
                for j, c in enumerate(env.assignments):
                    if c >= 0:
                        score[c] += w.get(tuple(sorted((name, env.names[j]))), 0.0)
                a = max((k for k in range(len(legal)) if legal[k]), key=lambda k: (score[k], -k))
            else:
                a = int(legal.argmax())
        env.step(a)
    parts: dict[int, list[str]] = defaultdict(list)
    for i, c in enumerate(env.assignments):
        if c >= 0:
            parts[c].append(env.names[i])
    return [sorted(v) for _, v in sorted(parts.items())]


def post(app: str, source: str = "teacher") -> list[list[str]]:
    start = start_partition(app, source)
    of = {c: k for k, cl in enumerate(start) for c in cl}
    K = len(start)
    partners: dict[str, set[str]] = defaultdict(set)
    for a, b, *_ in json.loads((OUT / app / "facts_nesy.json").read_text())["cannot_link"]:
        if a in of and b in of:
            partners[a].add(b)
            partners[b].add(a)
    w = weights(app)
    for _ in range(10 * len(of)):
        bad = {c: sum(of[p] == of[c] for p in partners[c]) for c in partners}
        bad = {c: n for c, n in bad.items() if n}
        if not bad:
            break
        legal_of = {x: [k for k in range(K) if k != of[x] and not any(of[p] == k for p in partners[x])] for x in bad}
        movable = [x for x in sorted(bad) if legal_of[x]]
        if not movable:
            raise SystemExit(f"{app}: no violating class has a legal service ({len(bad)} violating)")
        c = max(movable, key=lambda x: bad[x])
        legal = legal_of[c]
        conn = {k: sum(w.get(tuple(sorted((c, d))), 0.0) for d, kk in of.items() if kk == k and d != c) for k in legal}
        of[c] = max(legal, key=lambda k: (conn[k], -k))
    parts: dict[int, list[str]] = defaultdict(list)
    for c, k in of.items():
        parts[k].append(c)
    return [sorted(v) for _, v in sorted(parts.items())]


def build() -> None:
    from java_pipeline import rl_paths
    rl_paths.activate()
    import torch
    for app in APPS:
        for src, prefix in (("teacher", "repair"), ("nesyward", "repair_nesyward")):
            for name, fn in ((f"{prefix}_masked", lambda: walk(app, False, src)), (f"{prefix}_connect", lambda: walk(app, True, src)),
                             (f"{prefix}_post", lambda: post(app, src))):
                parts = fn()
                out = {"method": name, "app": app, "start": src, "partitions": parts, "torch": torch.__version__}
                (OUT / app / "baselines" / f"{name}.json").write_text(json.dumps(out, indent=2))
                print(f"{app:14s} {name:24s} sizes {sorted(map(len, parts), reverse=True)}")


def report() -> None:
    from java_pipeline import metrics as M
    from java_pipeline.results import POOL, RES
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["app"], r["family"])].append(r)

    def same_as(app: str, fam: str) -> str:
        g = [json.loads(p.read_text())["partitions"] for p in sorted((OUT / "_nesy" / "rl" / app).glob("full_s*/partition.json"))]
        x = json.loads((OUT / app / "baselines" / f"{fam}.json").read_text())["partitions"]
        return f"{sum({frozenset(p) for p in x} == {frozenset(p) for p in y} for y in g)}/{len(g)}"

    def moved(app: str, parts: list[list[str]]) -> int:
        T = [c["classes"] for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]]
        t_of = {c: k for k, p in enumerate(T) for c in p}
        r_of = {c: k for k, p in enumerate(parts) for c in p}
        match = {k: max(range(len(T)), key=lambda j: len(set(parts[k]) & set(T[j]))) for k in range(len(parts))}
        return sum(match[r_of[c]] != t_of[c] for c in r_of)

    print("### Constraint repair by rule against GraphRL-Dec full\n")
    print("Score: Eq. 5 as published, in the nine-method pool with the row in GraphRL-Dec full's place "
          "(GraphRL-Dec full's own Score in that pool in brackets). Means over 3 seeds for GraphRL-Dec.\n")
    print("| app | method | equals GraphRL-Dec full (seeds) | classes moved from teacher | cannot-link violations | "
          "must-link kept | Score, evaluate | Score, rldec | Score, weerasinghe |")
    print("|---|---|---|---|---|---|---|---|---|")
    for app in APPS:
        for fam in ("teacher", "graphrl:full") + VARIANTS:
            rs = by[(app, fam)]
            cells = []
            for conv in ("evaluate", "rldec", "weerasinghe"):
                pool = {f: {k: st.mean(float(r[f"{conv}_{k}"]) for r in by[(app, f)]) for k in ("SM", "IFN", "ICP", "NED")}
                        for f in POOL if f != "graphrl:full"}
                pool["x"] = {k: st.mean(float(r[f"{conv}_{k}"]) for r in rs) for k in ("SM", "IFN", "ICP", "NED")}
                pool["g"] = {k: st.mean(float(r[f"{conv}_{k}"]) for r in by[(app, "graphrl:full")]) for k in ("SM", "IFN", "ICP", "NED")}
                sc_x = M.eq5_scores({k: v for k, v in pool.items() if k != "g"}, "as_published")["x"]
                sc_g = M.eq5_scores({k: v for k, v in pool.items() if k not in ("x", "g")} | {"x": pool["g"]}, "as_published")["x"]
                cells.append(f"{sc_x:+.2f} ({sc_g:+.2f})")
            if fam == "teacher":
                eq, mv = "-", "0"
            elif fam == "graphrl:full":
                eq = "-"
                mv = " / ".join(str(moved(app, json.loads(p.read_text())["partitions"]))
                                for p in sorted((OUT / "_nesy" / "rl" / app).glob("full_s*/partition.json")))
            else:
                eq = same_as(app, fam)
                mv = str(moved(app, json.loads((OUT / app / "baselines" / f"{fam}.json").read_text())["partitions"]))
            viol = st.mean(float(r["cannot_link_violations"]) for r in rs)
            ml = st.mean(float(r["must_link_satisfaction"]) for r in rs)
            print(f"| {app} | {fam} | {eq} | {mv} | {viol:.0f} of {rs[0]['cannot_link_pairs']} | {ml:.3f} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    report() if sys.argv[1:] == ["report"] else build()
