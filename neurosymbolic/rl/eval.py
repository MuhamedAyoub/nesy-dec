"""Phase 3 multi-app evaluation.

Loads each app's `policy_best.pt`, greedy-decodes a partition, and builds
a comparison table against:

  * graph_rl              ← this work (Phase 3 RL over the graph)
  * phase1_hdbscan        ← native neuro-symbolic: HDBSCAN over the Phase-1
                            UnixCoder embeddings, auto-K, noise reattached to
                            the nearest centroid (no RL — the learned-but-
                            unsupervised counterpart of graph_rl)
  * mvc                   ← Berkane two-phase decomposer (Paper 2 baseline)
  * rails_aware_hc        ← rails-aware hierarchical clustering
  * phase1_clustering     ← UnixCoder embeddings + Ward agglomerative
                            (Paper 2 Phase 1 alone, no RL)
  * random                ← sanity floor

All four metrics (SM, IFN, ICP, NED) plus the Weerasinghe Eq.5 Score
(z-normed across THESE 5 tools so the column comparisons are honest).

Outputs (under <output-dir>):
  - phase3_eval.json         ← full per-app comparison
  - phase3_eval.md           ← markdown summary table
  - phase3_eval.csv          ← flat CSV (one row per app×method)

Usage
-----
    python -m neurosymbolic.rl.eval \\
        --apps astuto-main feedbin-main chatwoot-develop industrial-x \\
        --rl-input-dir output/phase3_rl \\
        --output-dir   output/phase3_rl/_eval
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch

from .decompose import greedy_decompose
from .graph_env import EnvConfig, load_env_for_app
from .policy import GNNActorCritic, PolicyConfig
from .train import _default_paths


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from vendor.ror_msi.evaluate import (  # noqa: E402
    compute_icp,
    compute_ifn,
    compute_ned,
    compute_sm,
    compute_weerasinghe_scores,
)


_DEFAULT_APPS = ("astuto-main", "feedbin-main", "chatwoot-develop", "industrial-x")


def _partition_metrics(partitions: list[list[str]], graph) -> dict:
    return {
        "SM": round(compute_sm(partitions, graph), 4),
        "IFN": round(compute_ifn(partitions, graph), 4),
        "ICP": round(compute_icp(partitions, graph), 4),
        "NED": round(compute_ned(partitions), 4),
        "num_microservices": len(partitions),
        "num_classes_assigned": sum(len(p) for p in partitions),
        "partition_sizes": [len(p) for p in partitions],
    }


def _load_policy(ckpt_path: Path, device: torch.device) -> GNNActorCritic:
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    cfg = PolicyConfig(**ckpt["config"])
    pol = GNNActorCritic(cfg).to(device)
    pol.load_state_dict(ckpt["policy"])
    pol.eval()
    return pol


def _rl_partition(app: str, rl_dir: Path, paths: dict[str, Path],
                  device: torch.device):
    """Greedy decode the trained policy. Returns (partitions, env) or ([], None).

    Looks for `policy_best.pt` under `rl_dir/<app>` first, then `policy.pt`.
    If neither exists, returns ([], None).
    """
    app_dir = rl_dir / app
    ckpt = None
    if (app_dir / "policy_best.pt").exists():
        ckpt = app_dir / "policy_best.pt"
    elif (app_dir / "policy.pt").exists():
        ckpt = app_dir / "policy.pt"
    else:
        # Maybe stored in a --run-name subfolder; pick the most recent.
        candidates = sorted(app_dir.glob("*/policy_best.pt"),
                             key=lambda p: p.stat().st_mtime, reverse=True)
        if candidates:
            ckpt = candidates[0]
    if ckpt is None or not ckpt.exists():
        return [], None
    pol = _load_policy(ckpt, device)
    # The env's action space MUST match the checkpoint's policy head count.
    # policy heads = n_real_clusters (+1 if trained with the outlier action).
    # env_meta (saved by train.py) disambiguates; fall back to old behaviour
    # (all heads = real clusters) for checkpoints without it.
    raw = torch.load(ckpt, weights_only=False, map_location=device)
    meta = raw.get("env_meta", {})
    if meta.get("allow_outliers"):
        env_cfg = EnvConfig(n_clusters=int(meta["n_real_clusters"]),
                            allow_outliers=True)
    else:
        env_cfg = EnvConfig(n_clusters=int(pol.cfg.n_clusters))
    env = load_env_for_app(
        app,
        facts_path=paths["facts"],
        graph_exp_json=paths["graph_exp"],
        embeddings_pt=paths["embeddings"],
        config=env_cfg,
    )
    parts = greedy_decompose(env, pol, device)
    return parts, env


def _phase1_clustering_partition(
    app: str, paths: dict[str, Path], n_clusters: int
) -> tuple[list[list[str]], dict] | tuple[None, None]:
    """Cluster Phase-1 UnixCoder embeddings with Ward agglomerative.
    Returns (partitions, graph) or (None, None) if embeddings missing."""
    if not paths["embeddings"].exists():
        return None, None
    from sklearn.cluster import AgglomerativeClustering
    ckpt = torch.load(paths["embeddings"], weights_only=False)
    embs = ckpt["embeddings"].cpu().numpy()
    names = list(ckpt["names"])
    # Build graph from the same MVC exp_*.json the env uses, restrict to it.
    exp = json.loads(paths["graph_exp"].read_text())
    graph = exp["dependency_graph"]
    graph_nodes = set(graph.keys())
    for s, edges in graph.items():
        graph_nodes.update(edges.keys())
    keep_idx = [i for i, n in enumerate(names) if n in graph_nodes]
    if len(keep_idx) < n_clusters:
        n_clusters = max(2, len(keep_idx) // 3)
    sub_embs = embs[keep_idx]
    sub_names = [names[i] for i in keep_idx]
    normed = sub_embs / (np.linalg.norm(sub_embs, axis=1, keepdims=True) + 1e-12)
    labels = AgglomerativeClustering(n_clusters=n_clusters, linkage="ward").fit_predict(normed)
    by: dict[int, list[str]] = {}
    for n, lab in zip(sub_names, labels):
        by.setdefault(int(lab), []).append(n)
    parts = [by[k] for k in sorted(by)]
    return parts, graph


def _phase1_hdbscan_partition(
    app: str, paths: dict[str, Path], min_cluster_size: int = 5
) -> tuple[list[list[str]], dict] | tuple[None, None]:
    """Native neuro-symbolic decomposition: HDBSCAN over Phase-1 UnixCoder
    embeddings (no RL). HDBSCAN auto-discovers the cluster count; noise points
    (label -1) are re-attached to their nearest cluster centroid by cosine
    similarity so every class is assigned (fair comparison vs graph_rl).

    Returns (partitions, graph) or (None, None) if embeddings missing.
    """
    if not paths["embeddings"].exists():
        return None, None
    from sklearn.cluster import HDBSCAN
    ckpt = torch.load(paths["embeddings"], weights_only=False)
    embs = ckpt["embeddings"].cpu().numpy()
    names = list(ckpt["names"])
    exp = json.loads(paths["graph_exp"].read_text())
    graph = exp["dependency_graph"]
    graph_nodes = set(graph.keys())
    for s, edges in graph.items():
        graph_nodes.update(edges.keys())
    keep_idx = [i for i, n in enumerate(names) if n in graph_nodes]
    if len(keep_idx) < 2:
        return None, None
    sub_embs = embs[keep_idx]
    sub_names = [names[i] for i in keep_idx]
    normed = sub_embs / (np.linalg.norm(sub_embs, axis=1, keepdims=True) + 1e-12)
    # HDBSCAN on cosine geometry (unit-normed vectors + euclidean ≈ cosine).
    mcs = min(min_cluster_size, max(2, len(keep_idx) // 3))
    labels = HDBSCAN(min_cluster_size=mcs, metric="euclidean").fit_predict(normed)

    real = sorted({int(l) for l in labels if l != -1})
    if not real:
        # Degenerate: HDBSCAN found no cluster — fall back to one bucket.
        return [sub_names], graph
    # Centroid (mean of unit vectors, re-normalised) per real cluster.
    centroids = {}
    for c in real:
        idx = [i for i, l in enumerate(labels) if int(l) == c]
        v = normed[idx].mean(axis=0)
        centroids[c] = v / (np.linalg.norm(v) + 1e-12)
    cmat = np.stack([centroids[c] for c in real])  # (K, D)
    final = labels.copy()
    for i, l in enumerate(labels):
        if int(l) == -1:
            sims = cmat @ normed[i]            # cosine to each centroid
            final[i] = real[int(np.argmax(sims))]
    by: dict[int, list[str]] = {}
    for n, lab in zip(sub_names, final):
        by.setdefault(int(lab), []).append(n)
    parts = [by[k] for k in sorted(by)]
    return parts, graph


def _random_partition(
    names: list[str], n_clusters: int, seed: int = 42
) -> list[list[str]]:
    rng = np.random.default_rng(seed)
    labels = rng.integers(0, n_clusters, size=len(names))
    by: dict[int, list[str]] = {}
    for n, lab in zip(names, labels):
        by.setdefault(int(lab), []).append(n)
    return [by[k] for k in sorted(by)]


def _find_baseline(app: str, suffix: str) -> Path | None:
    """Find exp_*_<suffix> under results/<app>/. Returns most-recent match."""
    d = REPO / "results" / app
    if not d.exists():
        return None
    cands = sorted(d.glob(f"exp_*{suffix}"))
    return cands[-1] if cands else None


def _write_candidate_dump(
    app: str, partitions: list[list[str]], graph: dict, metrics: dict,
    out_dir: Path, role_of: dict[str, str] | None = None,
) -> None:
    """Persist the RL partition so the user can REVIEW what was produced.

    Two files under <out_dir>/candidates/:
      - exp_rl_<app>.json   evaluator-compatible (same shape as results/*.json)
      - candidates_<app>.md human-readable: each service's class list, sorted
                            by size, with role breakdown when facts are present.
    """
    cdir = out_dir / "candidates"
    cdir.mkdir(parents=True, exist_ok=True)
    # Machine-readable, consumable by evaluate.py / report.py.
    payload = {
        "app": app,
        "params": {"method": "graph_rl", "n_clusters": len(partitions)},
        "clusters": [{"id": k, "classes": members}
                     for k, members in enumerate(partitions)],
        "dependency_graph": graph,
        "metrics": metrics,
    }
    (cdir / f"exp_rl_{app}.json").write_text(json.dumps(payload, indent=2))

    # Human-readable review file.
    ordered = sorted(enumerate(partitions), key=lambda kv: -len(kv[1]))
    lines = [
        f"# graph_rl candidate decomposition — `{app}`",
        "",
        f"{len(partitions)} microservices, "
        f"{sum(len(p) for p in partitions)} classes. "
        f"SM={metrics.get('SM')}, IFN={metrics.get('IFN')}, "
        f"ICP={metrics.get('ICP')}, NED={metrics.get('NED')}.",
        "",
        "Services are listed largest-first. Sizes in the NED 'good' band "
        "[5,20] are healthy; very large or singleton services hurt NED.",
        "",
    ]
    for k, members in ordered:
        band = "ok" if 5 <= len(members) <= 20 else "extreme"
        lines.append(f"## service {k} — {len(members)} classes ({band})")
        if role_of:
            roles: dict[str, int] = {}
            for c in members:
                roles[role_of.get(c, "unknown")] = roles.get(role_of.get(c, "unknown"), 0) + 1
            role_str = ", ".join(f"{r}:{n}" for r, n in
                                 sorted(roles.items(), key=lambda x: -x[1]))
            lines.append(f"_roles: {role_str}_")
        lines.append("")
        for c in sorted(members):
            lines.append(f"- {c}")
        lines.append("")
    (cdir / f"candidates_{app}.md").write_text("\n".join(lines))


def build_peer_metrics(app: str, *, include_phase1: bool = True,
                       include_random: bool = True) -> list[dict]:
    """The fixed (SM,IFN,ICP,NED) vectors the RL agent is z-scored against.

    EXACTLY the same baselines `evaluate_app` grades on — mvc, rails_aware_hc,
    phase1_clustering, random — computed on the same shared dependency graph.
    Used by train.py to give the zscore reward its comparison set so the
    training objective matches the leaderboard.

    Returns a list of dicts with keys SM/IFN/ICP/NED (no rounding — the reward
    wants full precision). Skips any baseline whose inputs are missing.
    """
    paths_full = _default_paths(app)
    paths = {
        "facts": paths_full["facts"],
        "graph_exp": paths_full["graph_exp"],
        "embeddings": paths_full["embeddings"],
    }
    peers: list[dict] = []

    def _raw(parts, graph):
        return {
            "SM": compute_sm(parts, graph),
            "IFN": compute_ifn(parts, graph),
            "ICP": compute_icp(parts, graph),
            "NED": compute_ned(parts),
        }

    # mvc (also the source of the shared graph)
    mvc_exp = _find_baseline(app, "_mvc.json") or paths["graph_exp"]
    mvc_payload = json.loads(Path(mvc_exp).read_text())
    graph = mvc_payload["dependency_graph"]
    mvc_parts = [c["classes"] for c in mvc_payload["clusters"]]
    peers.append(_raw(mvc_parts, graph))
    K = max(2, len(mvc_parts))

    # rails_aware_hc
    rails_exp = _find_baseline(app, "_rails_aware.json")
    if rails_exp and rails_exp.exists():
        d = json.loads(rails_exp.read_text())
        peers.append(_raw([c["classes"] for c in d["clusters"]], graph))

    # phase1 clustering (UnixCoder + Ward)
    if include_phase1:
        parts, _g = _phase1_clustering_partition(app, paths, K)
        if parts:
            peers.append(_raw(parts, graph))
        # native neuro-symbolic HDBSCAN (auto-K, no RL)
        parts_h, _gh = _phase1_hdbscan_partition(app, paths)
        if parts_h:
            peers.append(_raw(parts_h, graph))

    # random floor
    if include_random:
        all_classes = sorted(set(graph.keys()) | {t for e in graph.values() for t in e})
        peers.append(_raw(_random_partition(all_classes, K), graph))

    return peers


def evaluate_app(
    app: str,
    rl_dir: Path,
    device: torch.device,
    *,
    include_random: bool = True,
    include_phase1: bool = True,
    candidate_out_dir: Path | None = None,
) -> dict:
    """Build the per-method comparison dict for one app."""
    paths_full = _default_paths(app)
    paths = {
        "facts": paths_full["facts"],
        "graph_exp": paths_full["graph_exp"],
        "embeddings": paths_full["embeddings"],
    }
    out: dict = {"app": app, "methods": {}}

    # --- 1) MVC baseline (Berkane two-phase) ----------------------------------
    mvc_exp = _find_baseline(app, "_mvc.json")
    if mvc_exp is None:
        # fallback to whatever's in the train default
        mvc_exp = paths["graph_exp"]
    if not mvc_exp or not mvc_exp.exists():
        out["error"] = f"missing MVC baseline for {app}"
        return out
    mvc_payload = json.loads(mvc_exp.read_text())
    mvc_parts = [c["classes"] for c in mvc_payload["clusters"]]
    graph = mvc_payload["dependency_graph"]
    out["methods"]["mvc"] = {
        "source": str(mvc_exp.relative_to(REPO)),
        **_partition_metrics(mvc_parts, graph),
    }
    K = max(2, len(mvc_parts))

    # --- 2) Rails-aware HC ---------------------------------------------------
    rails_exp = _find_baseline(app, "_rails_aware.json")
    if rails_exp and rails_exp.exists():
        d = json.loads(rails_exp.read_text())
        parts = [c["classes"] for c in d["clusters"]]
        out["methods"]["rails_aware_hc"] = {
            "source": str(rails_exp.relative_to(REPO)),
            **_partition_metrics(parts, graph),
        }

    # --- 3) Phase 1 clustering (UnixCoder + Ward) ---------------------------
    if include_phase1:
        parts, _g = _phase1_clustering_partition(app, paths, K)
        if parts:
            out["methods"]["phase1_clustering"] = {
                "source": "ward(unixcoder_embeddings)",
                **_partition_metrics(parts, graph),
            }

    # --- 3b) Native neuro-symbolic HDBSCAN (auto-K, no RL) ------------------
    if include_phase1:
        parts, _g = _phase1_hdbscan_partition(app, paths)
        if parts:
            out["methods"]["phase1_hdbscan"] = {
                "source": "hdbscan(unixcoder_embeddings)",
                **_partition_metrics(parts, graph),
            }

    # --- 4) Graph-RL (this work) --------------------------------------------
    rl_parts, rl_env = _rl_partition(app, rl_dir, paths, device)
    if rl_parts:
        rl_metrics = _partition_metrics(rl_parts, graph)
        out["methods"]["graph_rl"] = {
            "source": f"{rl_dir.name}/{app}/policy_best.pt",
            **rl_metrics,
        }
        # Persist the candidate decomposition for human review.
        if candidate_out_dir is not None:
            _write_candidate_dump(
                app, rl_parts, graph, rl_metrics, candidate_out_dir,
                role_of=getattr(rl_env, "role_of", None),
            )
            out["methods"]["graph_rl"]["candidate_file"] = \
                f"candidates/candidates_{app}.md"
    else:
        out["methods"]["graph_rl"] = {"error": f"no checkpoint under {rl_dir / app}"}

    # --- 5) Random sanity floor --------------------------------------------
    if include_random:
        all_classes_in_graph = sorted(set(graph.keys()) | {t for e in graph.values() for t in e})
        parts = _random_partition(all_classes_in_graph, K)
        out["methods"]["random"] = {
            "source": "uniform_random",
            **_partition_metrics(parts, graph),
        }

    # --- Weerasinghe Eq.5 Score (z-normed across ALL methods for this app) ----
    metrics_by_tool = {
        name: {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}
        for name, m in out["methods"].items()
        if "error" not in m
    }
    scores = compute_weerasinghe_scores(metrics_by_tool)
    for name, s in scores.items():
        out["methods"][name]["Score_weerasinghe"] = (
            round(float(s), 4) if isinstance(s, float) and not math.isnan(s) else None
        )
    return out


# ---------------------------------------------------------------------------
# Markdown / CSV emitters
# ---------------------------------------------------------------------------

_METHOD_ORDER = ("graph_rl", "phase1_hdbscan", "mvc", "rails_aware_hc",
                 "phase1_clustering", "random")


def render_markdown(results: list[dict], out_path: Path) -> None:
    lines = [
        "# Phase 3 — Multi-app Evaluation",
        "",
        "Comparison of the **graph-RL decomposer** against the reference",
        "methods on the standard 4-app Rails benchmark. The two learned",
        "neuro-symbolic decompositions are **graph_rl** (RL over the graph)",
        "and **phase1_hdbscan** (native HDBSCAN over the Phase-1 embeddings,",
        "no RL). Score column is Weerasinghe et al. (2026) Eq. 5, z-normalised",
        "across all methods within each app (higher = better).",
        "",
    ]
    # One block per app.
    for r in results:
        app = r["app"]
        lines.append(f"## `{app}`")
        lines.append("")
        if "error" in r:
            lines.append(f"_error: {r['error']}_")
            lines.append("")
            continue
        header = ["method", "SM", "IFN", "ICP", "NED", "Score", "#MS", "#classes", "sizes"]
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join("---" for _ in header) + "|")
        # Order methods deterministically; unknown methods at the end.
        ordered = [n for n in _METHOD_ORDER if n in r["methods"]]
        ordered += [n for n in r["methods"] if n not in ordered]
        for name in ordered:
            m = r["methods"][name]
            if "error" in m:
                lines.append(f"| **{name}** | _error: {m['error']}_ | | | | | | | |")
                continue
            row = [
                f"**{name}**",
                f"{m['SM']:+.4f}",
                f"{m['IFN']:.4f}",
                f"{m['ICP']:.4f}",
                f"{m['NED']:.4f}",
                _score_str(m.get("Score_weerasinghe")),
                str(m["num_microservices"]),
                str(m["num_classes_assigned"]),
                ",".join(str(s) for s in m["partition_sizes"]),
            ]
            lines.append("| " + " | ".join(row) + " |")
        # Quick verdict
        rl = r["methods"].get("graph_rl", {})
        mvc = r["methods"].get("mvc", {})
        if "Score_weerasinghe" in rl and "Score_weerasinghe" in mvc and rl["Score_weerasinghe"] is not None and mvc["Score_weerasinghe"] is not None:
            d = rl["Score_weerasinghe"] - mvc["Score_weerasinghe"]
            verdict = "**wins**" if d > 0.05 else "**ties**" if abs(d) <= 0.05 else "**loses**"
            lines.append("")
            lines.append(f"_graph_rl {verdict} vs mvc on {app}: ΔScore = {d:+.4f}_")
        cand = rl.get("candidate_file")
        if cand:
            lines.append("")
            lines.append(f"_RL candidate decomposition (per-service class lists): [`{cand}`]({cand})_")
        lines.append("")

    # Cross-app summary.
    lines.append("## Cross-app summary")
    lines.append("")
    lines.append("Score (Weerasinghe Eq. 5) per app × method:")
    lines.append("")
    apps = [r["app"] for r in results if "error" not in r]
    methods_present: list[str] = []
    for r in results:
        for name in r.get("methods", {}):
            if name not in methods_present:
                methods_present.append(name)
    methods_present = [m for m in _METHOD_ORDER if m in methods_present] + \
                      [m for m in methods_present if m not in _METHOD_ORDER]
    lines.append("| method | " + " | ".join(apps) + " | mean |")
    lines.append("|" + "|".join("---" for _ in range(len(apps) + 2)) + "|")
    for m in methods_present:
        row = [m]
        vals: list[float] = []
        for r in results:
            v = r["methods"].get(m, {}).get("Score_weerasinghe")
            row.append(_score_str(v))
            if v is not None:
                vals.append(float(v))
        row.append(f"{np.mean(vals):+.4f}" if vals else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    out_path.write_text("\n".join(lines))


def _score_str(v) -> str:
    if v is None:
        return "—"
    return f"{v:+.4f}"


def render_csv(results: list[dict], out_path: Path) -> None:
    rows: list[dict] = []
    for r in results:
        if "error" in r:
            continue
        for name, m in r["methods"].items():
            if "error" in m:
                continue
            rows.append({
                "app": r["app"],
                "method": name,
                "SM": m["SM"],
                "IFN": m["IFN"],
                "ICP": m["ICP"],
                "NED": m["NED"],
                "Score_weerasinghe": m.get("Score_weerasinghe"),
                "num_microservices": m["num_microservices"],
                "num_classes_assigned": m["num_classes_assigned"],
            })
    if not rows:
        return
    with out_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for row in rows:
            w.writerow(row)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Multi-app Phase 3 evaluation")
    parser.add_argument("--apps", nargs="+", default=list(_DEFAULT_APPS))
    parser.add_argument("--rl-input-dir", type=str,
                        default=str(REPO / "neurosymbolic" / "output" / "phase3_rl"))
    parser.add_argument("--output-dir", type=str,
                        default=str(REPO / "neurosymbolic" / "output" / "phase3_rl" / "_eval"))
    parser.add_argument("--no-random", action="store_true")
    parser.add_argument("--no-phase1", action="store_true")
    parser.add_argument("--device", type=str,
                        default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    rl_dir = Path(args.rl_input_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    device = torch.device(args.device)

    results: list[dict] = []
    for app in args.apps:
        print(f"[eval] {app}")
        try:
            r = evaluate_app(
                app, rl_dir, device,
                include_random=not args.no_random,
                include_phase1=not args.no_phase1,
                candidate_out_dir=out_dir,
            )
        except Exception as e:
            r = {"app": app, "error": f"{type(e).__name__}: {e}"}
            print(f"[eval]   FAILED: {e}")
        results.append(r)

    (out_dir / "phase3_eval.json").write_text(json.dumps(results, indent=2, default=str))
    render_markdown(results, out_dir / "phase3_eval.md")
    render_csv(results, out_dir / "phase3_eval.csv")
    print(f"[eval] wrote {out_dir / 'phase3_eval.md'}")
    print(f"[eval] wrote {out_dir / 'phase3_eval.csv'}")
    print(f"[eval] wrote {out_dir / 'phase3_eval.json'}")


if __name__ == "__main__":
    main()
