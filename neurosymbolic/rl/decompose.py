"""Load a trained policy and produce an exp_*.json partition.

Output shape matches `results/<app>/exp_*.json` so the existing evaluator
and report generators consume it without changes:

    {
      "app": "...",
      "params": {"method": "graph_rl", "n_clusters": K, ...},
      "clusters": [{"id": k, "classes": [...]}, ...],
      "dependency_graph": {...},   # carried over from the reference exp_*.json
      "weerasinghe": {"SM": ..., "IFN": ..., "ICP": ..., "NED": ..., "Score": ...},
    }

Usage:
    python -m neurosymbolic.rl.decompose --app astuto-main
    python -m neurosymbolic.rl.decompose --app astuto-main --policy best
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch

from .graph_env import EnvConfig, load_env_for_app
from .policy import GNNActorCritic, PolicyConfig


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


def _load_policy(ckpt_path: Path, device: torch.device) -> GNNActorCritic:
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    cfg = PolicyConfig(**ckpt["config"])
    policy = GNNActorCritic(cfg).to(device)
    policy.load_state_dict(ckpt["policy"])
    policy.eval()
    return policy


def greedy_decompose(env, policy: GNNActorCritic, device: torch.device) -> list[list[str]]:
    """Argmax-over-legal at every step. No exploration."""
    env.reset()
    node_feat = torch.from_numpy(env.node_features).to(device)
    edge_index = torch.from_numpy(env.edge_index).to(device)
    while not env.done:
        mask_np = env.legal_actions()
        mask = torch.from_numpy(mask_np).to(device)
        assignments = torch.tensor(env.assignments, dtype=torch.long, device=device)
        with torch.no_grad():
            logits, _ = policy(
                node_feat, edge_index, env.current_node, assignments, mask,
            )
        # Argmax with mask already applied (logits at masked positions are -inf).
        action = int(torch.argmax(logits).item())
        env.step(action)
    # Build partition.
    by_cluster: dict[int, list[str]] = {}
    for i, c in enumerate(env.assignments):
        if c < 0:
            continue
        by_cluster.setdefault(c, []).append(env.names[i])
    return [by_cluster[k] for k in sorted(by_cluster)]


def write_exp_json(
    app: str,
    partitions: list[list[str]],
    graph: dict[str, dict[str, int]],
    out_path: Path,
    *,
    policy_meta: dict,
) -> dict:
    """Emit exp_*.json compatible with the rest of the pipeline."""
    sm = compute_sm(partitions, graph)
    ifn = compute_ifn(partitions, graph)
    icp = compute_icp(partitions, graph)
    ned = compute_ned(partitions)
    payload = {
        "app": app,
        "params": {
            "method": "graph_rl",
            "n_clusters": len(partitions),
            **policy_meta,
        },
        "clusters": [
            {"id": k, "classes": members}
            for k, members in enumerate(partitions)
        ],
        "dependency_graph": graph,
        "metrics": {
            "SM": round(sm, 4),
            "IFN": round(ifn, 4),
            "ICP": round(icp, 4),
            "NED": round(ned, 4),
            "num_microservices": len(partitions),
            "num_classes_assigned": sum(len(p) for p in partitions),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Greedy decode + write exp_rl.json")
    parser.add_argument("--app", required=True)
    parser.add_argument("--policy", choices=["last", "best"], default="best")
    parser.add_argument("--policy-path", type=str, default=None,
                        help="explicit checkpoint path; overrides --policy")
    parser.add_argument("--n-clusters", type=int, default=None)
    parser.add_argument("--facts-path", type=str, default=None)
    parser.add_argument("--graph-exp", type=str, default=None)
    parser.add_argument("--embeddings", type=str, default=None)
    parser.add_argument("--input-dir", type=str, default=None,
                        help="training output dir; defaults to output/phase3_rl/<app>")
    parser.add_argument("--output", type=str, default=None,
                        help="exp_rl.json output path; defaults to results/<app>/exp_rl.json")
    parser.add_argument("--device", type=str,
                        default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    defaults_facts = REPO / "neurosymbolic" / "output" / "facts" / f"{args.app}.json"
    defaults_graph = REPO / "results" / args.app / "exp_a0.5_b0.5_n8_mvc.json"
    defaults_emb = REPO / "neurosymbolic" / "output" / "phase1_rails_aware" / "train" / "embeddings" / f"{args.app}.pt"
    defaults_input = REPO / "neurosymbolic" / "output" / "phase3_rl" / args.app
    defaults_output = REPO / "results" / args.app / "exp_rl.json"

    facts_path = Path(args.facts_path) if args.facts_path else defaults_facts
    graph_exp = Path(args.graph_exp) if args.graph_exp else defaults_graph
    embeddings = Path(args.embeddings) if args.embeddings else defaults_emb
    input_dir = Path(args.input_dir) if args.input_dir else defaults_input
    output = Path(args.output) if args.output else defaults_output

    ckpt_path = Path(args.policy_path) if args.policy_path else (
        input_dir / ("policy_best.pt" if args.policy == "best" else "policy.pt")
    )
    if not ckpt_path.exists():
        raise FileNotFoundError(f"missing checkpoint: {ckpt_path}")

    device = torch.device(args.device)
    env = load_env_for_app(
        args.app,
        facts_path=facts_path,
        graph_exp_json=graph_exp,
        embeddings_pt=embeddings,
        config=EnvConfig(n_clusters=args.n_clusters),
    )
    policy = _load_policy(ckpt_path, device)
    partitions = greedy_decompose(env, policy, device)

    # Use the reference graph for the persisted metrics (same denominator as MVC).
    payload = write_exp_json(
        app=args.app,
        partitions=partitions,
        graph=env.graph,
        out_path=output,
        policy_meta={
            "checkpoint": str(ckpt_path.name),
            "hidden_dim": policy.cfg.hidden_dim,
            "n_gnn_layers": policy.cfg.n_gnn_layers,
        },
    )

    # Comparison vs the MVC baseline at the same K.
    cmp_metrics = {
        "graph_rl": payload["metrics"],
        "mvc_baseline": {
            "SM": compute_sm(env.baseline_partitions, env.graph),
            "IFN": compute_ifn(env.baseline_partitions, env.graph),
            "ICP": compute_icp(env.baseline_partitions, env.graph),
            "NED": compute_ned(env.baseline_partitions),
        },
    }
    scores = compute_weerasinghe_scores({
        t: {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}
        for t, m in cmp_metrics.items()
    })
    print(f"[decompose] wrote {output}")
    print(f"[decompose] graph_rl     Score = {scores.get('graph_rl', float('nan')):+.3f}")
    print(f"[decompose] mvc_baseline Score = {scores.get('mvc_baseline', float('nan')):+.3f}")
    delta = scores.get('graph_rl', np.nan) - scores.get('mvc_baseline', np.nan)
    print(f"[decompose] Δ Score (RL − MVC) = {delta:+.3f}")


if __name__ == "__main__":
    main()
