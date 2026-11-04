"""Diagnostic: is the teacher a local optimum of the dual objective?

Starting from the teacher's partition, repeatedly apply the best single-class
move (to another existing service) that raises the dual score. No service may
grow past the RL environment's size cap, max(20, ceil(5 N / K)):

    0.5 * z_evaluate + 0.5 * z_rldec

This is java_pipeline/dual_reward.py's objective, against the same four peers
(teacher, UnixCoder+Ward, UnixCoder+HDBSCAN, random), with z-scores in the
environment's own form (population std, divided by 6). The search stops when
no move helps or after MAX_MOVES moves.

The result is scored like every other method, and the weerasinghe convention
(calls_graph.json) is the held-out check.

- If the search finds improvements that also hold out, better partitions
  exist near the teacher, and the RL stage is failing to find them.
- If it finds none, the teacher is already locally optimal for these
  metrics.

Usage: python3 -m java_pipeline.local_search
Writes results/<app>/baselines/local_search_dual.json.
"""
from __future__ import annotations

import json
import sys

import numpy as np

from java_pipeline import metrics as M
from java_pipeline import rl_paths
from java_pipeline.results import APPS
from java_pipeline.subjects import OUT

MAX_MOVES = 200
SIZE_CAP_FACTOR = 5.0      # the RL environment's cap (run_gpu.RL size_cap_factor), floored at 20 as in graph_env
W = {"SM": 3.0, "IFN": -1.0, "ICP": -1.0, "NED": -1.0}


def z(m: dict, peers: list[dict]) -> float:
    """graph_env._weerasinghe_zscore: population std, skip zero-variance columns, divide by 6."""
    pool = peers + [m]
    s = 0.0
    for k, w in W.items():
        v = np.array([p[k] for p in pool])
        sd = v.std()
        if sd > 0:
            s += w * (m[k] - v.mean()) / sd
    return s / 6.0


def refine(app: str, start_parts: list[list[str]] | None = None) -> dict:
    """Hill-climb from start_parts (default: the teacher). Returns the result
    record; the peers and the size cap are those of the teacher run."""
    import math
    from java_pipeline.dual_reward import _peer_partitions
    exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
    names = sorted(exp["dependency_graph"])
    idx = {n: i for i, n in enumerate(names)}
    A, _, _ = M.from_graph(exp["dependency_graph"], [], names)

    def met(labels, conv):
        m = M.compute(A, labels, conv)
        return {k: m[k] for k in W}

    def labels_of(parts):
        lab = np.full(len(names), -1, dtype=int)
        for k, p in enumerate(parts):
            for c in p:
                lab[idx[c]] = k
        return lab

    peers = [labels_of(p) for p in _peer_partitions(app, rl_paths.teacher(app), names)]
    pe = [met(l, "evaluate") for l in peers]
    pr = [met(l, "rldec") for l in peers]

    def dual(lab):
        return 0.5 * z(met(lab, "evaluate"), pe) + 0.5 * z(met(lab, "rldec"), pr)

    teacher = [c["classes"] for c in exp["clusters"]]
    lab = labels_of(start_parts or teacher)
    lab = np.unique(lab, return_inverse=True)[1]
    K = lab.max() + 1
    cap = max(20, math.ceil(SIZE_CAP_FACTOR * len(names) / len(teacher)))
    start = cur = dual(lab)
    moves = 0
    while moves < MAX_MOVES:
        best, best_move = cur, None
        for i in range(len(names)):
            old = lab[i]
            if (lab == old).sum() == 1:
                continue                     # do not empty a service
            for k in range(K):
                if k == old or (lab == k).sum() >= cap:
                    continue                 # same size cap as the RL environment
                lab[i] = k
                s = dual(lab)
                if s > best + 1e-9:
                    best, best_move = s, (i, k)
            lab[i] = old
        if best_move is None:
            break
        lab[best_move[0]] = best_move[1]
        cur, moves = best, moves + 1
    parts = [[names[i] for i in np.where(lab == k)[0]] for k in range(K) if (lab == k).any()]
    return {"method": "local_search_dual", "app": app, "moves": moves, "size_cap": cap,
            "dual_score_start": start, "dual_score_end": cur, "partitions": parts}


def main() -> None:
    sys.argv = sys.argv[:1]
    rl_paths.activate()
    for app in APPS:
        out = dict(refine(app), start="teacher")
        (OUT / app / "baselines" / "local_search_dual.json").write_text(json.dumps(out, indent=2))
        print(f"{app:18s} moves {out['moves']:3d}  dual {out['dual_score_start']:+.3f} -> {out['dual_score_end']:+.3f}  "
              f"sizes {sorted(map(len, out['partitions']), reverse=True)}")


if __name__ == "__main__":
    main()
