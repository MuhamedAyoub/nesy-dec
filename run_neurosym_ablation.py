"""Neuro-symbolic ablation — the Phase-3 contribution artifact.

Trains the graph-RL decomposer with progressively richer signals and reports
the RAW-COMPOSITE Eq.5 Score (compute_composite_score on each method's own
graph — the absolute, comparable number) of each variant against the baselines
(mvc / rails_aware_hc / phase1_clustering / random).

Variants (each adds one signal on top of the previous):
  structural   : SM/ICP/IFN reward only (the old behaviour)
  +semantic    : + neural UnixCoder cohesion (semantic_coef)
  +affinity    : + symbolic graded soft_affinity (soft_affinity_coef)
  +noise       : + framework_noise prior with the outlier action
  full         : everything + balance + KL anchor (the headline config)

All variants warm-start from rails_aware_hc (BC) then PPO-refine. We judge by
the DECODED raw-composite score, never the internal training reward.

Usage:
    python run_neurosym_ablation.py --apps astuto-main --device cuda --episodes 600
    python run_neurosym_ablation.py --apps astuto-main feedbin-main industrial-x chatwoot-develop
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

REPO = Path(__file__).resolve().parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from vendor.ror_msi.evaluate import (compute_composite_score, compute_icp, compute_ifn,
                      compute_ned, compute_sm)
from neurosymbolic.rl import train as train_mod
from neurosymbolic.rl.eval import (_default_paths, _find_baseline, _load_policy,
                                    _phase1_clustering_partition, _random_partition)
from neurosymbolic.rl.graph_env import EnvConfig, load_env_for_app
from neurosymbolic.rl.decompose import greedy_decompose


# Each variant = the extra CLI flags layered on the shared base recipe.
# The signal-ablation ladder (structural -> full) plus the three analysis-phase
# experiments (C1 / C2 / C1+C2) layered on `full`. C1 (inferred coupling) requires
# the facts to be generated first:  python -m neurosymbolic.infer_coupling --apps ...
_FULL = ["--semantic-coef", "1.0", "--soft-affinity-coef", "0.2",
         "--noise-coef", "0.1", "--allow-outliers",
         "--balance-coef", "0.6", "--kl-coef", "0.2"]
VARIANTS = {
    "structural": [],
    "+semantic":  ["--semantic-coef", "1.0"],
    "+affinity":  ["--semantic-coef", "1.0", "--soft-affinity-coef", "0.2"],
    "+noise":     ["--semantic-coef", "1.0", "--soft-affinity-coef", "0.2",
                   "--noise-coef", "0.1", "--allow-outliers"],
    "full":       _FULL,
    # --- analysis-phase contributions (3 experiments, layered on full) --------
    "full+C2":    _FULL + ["--affinity-from-embeddings"],
    "full+C1":    _FULL + ["--inferred-coupling-coef", "0.2"],
    "full+C1+C2": _FULL + ["--affinity-from-embeddings", "--inferred-coupling-coef", "0.2"],
}


def _score(parts, graph):
    sm = compute_sm(parts, graph); ifn = compute_ifn(parts, graph)
    icp = compute_icp(parts, graph); ned = compute_ned(parts)
    return (compute_composite_score(sm, ifn, icp, ned, len(parts)),
            sorted((len(p) for p in parts), reverse=True))


def _baseline_scores(app):
    """Raw-composite Score of the reference methods on their own graphs."""
    out = {}
    mvc = _find_baseline(app, "_mvc.json")
    if mvc:
        d = json.loads(Path(mvc).read_text()); g = d["dependency_graph"]
        out["mvc"] = _score([c["classes"] for c in d["clusters"]], g)
        # phase1 + random share the mvc graph
        K = max(2, len(d["clusters"]))
        pf = _default_paths(app)
        paths = {"facts": pf["facts"], "graph_exp": pf["graph_exp"], "embeddings": pf["embeddings"]}
        p1, _ = _phase1_clustering_partition(app, paths, K)
        if p1:
            out["phase1"] = _score(p1, g)
        allc = sorted(set(g.keys()) | {t for e in g.values() for t in e})
        out["random"] = _score(_random_partition(allc, K), g)
    rails = REPO / "results" / app / "exp_a0.9_b0.1_n8_rails_aware.json"
    if rails.exists():
        d = json.loads(rails.read_text())
        out["rails_aware_hc"] = _score([c["classes"] for c in d["clusters"]],
                                       d["dependency_graph"])
    return out


def _train_variant(app, name, extra, base, device, run_root, seed=42):
    # seed in the run-name keeps each seed's checkpoints separate (RQ4).
    run_name = f"ablate_{name.replace('+', '')}_s{seed}"
    # size-cap (safety net vs giants) and kl_coef are infrastructure shared by
    # ALL variants — not signals being ablated — so apply them to every run.
    argv = ["train", "--app", app, "--device", device,
            "--num-envs", base["num_envs"], "--episodes", base["episodes"],
            "--reward-mode", base["reward_mode"],
            "--warmstart-rails", "auto",
            "--warmstart-epochs", base["warmstart_epochs"],
            "--warmstart-lr", "1e-3", "--lr", "1e-4", "--seed", str(seed),
            "--kl-coef", base.get("kl_coef", "0.5"),
            "--size-cap-factor", base.get("size_cap_factor", "5.0"),
            "--log-every", "300", "--select-by-decode",
            "--run-name", run_name, "--force-overwrite"] + extra
    old = sys.argv
    sys.argv = argv
    try:
        train_mod.main()
    finally:
        sys.argv = old
    return run_root / app / run_name / "policy_best.pt"


def _decode(app, ckpt, device):
    raw = torch.load(ckpt, weights_only=False, map_location=device)
    meta = raw.get("env_meta", {})
    pol = _load_policy(ckpt, device)
    pf = _default_paths(app)
    if meta.get("allow_outliers"):
        cfg = EnvConfig(n_clusters=int(meta["n_real_clusters"]), allow_outliers=True)
    else:
        cfg = EnvConfig(n_clusters=int(pol.cfg.n_clusters))
    env = load_env_for_app(app, facts_path=pf["facts"],
                           graph_exp_json=_find_baseline(app, "_mvc.json"),
                           embeddings_pt=pf["embeddings"], config=cfg)
    return _score(greedy_decompose(env, pol, device), env.graph)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apps", nargs="+", default=["astuto-main"])
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--episodes", default="600")
    ap.add_argument("--num-envs", default="16")
    ap.add_argument("--warmstart-epochs", default="800")   # long BC = teacher fidelity
    ap.add_argument("--reward-mode", default="zscore")
    ap.add_argument("--kl-coef", default="0.5")
    ap.add_argument("--size-cap-factor", default="5.0")    # giant safety net
    args = ap.parse_args()

    base = {"num_envs": args.num_envs, "episodes": args.episodes,
            "warmstart_epochs": args.warmstart_epochs, "reward_mode": args.reward_mode,
            "kl_coef": args.kl_coef, "size_cap_factor": args.size_cap_factor}
    run_root = REPO / "neurosymbolic" / "output" / "phase3_rl"

    results = {}  # app -> {variant: (score, sizes)}
    for app in args.apps:
        results[app] = {}
        for name, extra in VARIANTS.items():
            print(f"\n{'#'*70}\n# {app}  variant={name}  {' '.join(extra) or '(structural only)'}\n{'#'*70}")
            try:
                ckpt = _train_variant(app, name, extra, base, args.device, run_root)
                results[app][name] = _decode(app, ckpt, args.device)
            except Exception as e:
                print(f"  variant {name} FAILED: {type(e).__name__}: {e}")
                results[app][name] = (float("nan"), [])

    # ---- report ----
    print("\n" + "=" * 78)
    print("NEURO-SYMBOLIC ABLATION — raw-composite Eq.5 (own graph), higher = better")
    print("=" * 78)
    for app in args.apps:
        base_sc = _baseline_scores(app)
        print(f"\n### {app}")
        print(f"{'variant':<14}{'Score':>9}  sizes(top8) / #singletons / #in-band[5,20]")
        print("-" * 78)
        for name in VARIANTS:
            sc, sizes = results[app].get(name, (float("nan"), []))
            sing = sum(1 for s in sizes if s == 1)
            inb = sum(1 for s in sizes if 5 <= s <= 20)
            sz = ",".join(map(str, sizes[:8]))
            print(f"{name:<14}{sc:>+9.4f}  {sz}   sing={sing} band={inb}")
        print("-" * 14 + " baselines " + "-" * 14)
        for b in ("rails_aware_hc", "mvc", "phase1", "random"):
            if b in base_sc:
                sc, sizes = base_sc[b]
                print(f"{b:<14}{sc:>+9.4f}  {','.join(map(str, sizes[:8]))}")
    print("\n" + "=" * 78)
    print("Read: does each added signal raise the Score / improve sizes? Is 'full'"
          " > mvc/random/phase1 and in the rails ballpark? That's the contribution.")
    # persist
    out = run_root / "_eval" / "neurosym_ablation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(
        {a: {n: {"score": s, "sizes": z} for n, (s, z) in v.items()}
         for a, v in results.items()}, indent=2))
    print("wrote", out)


if __name__ == "__main__":
    main()
