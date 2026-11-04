"""Idea 1: a GraphRL-Dec reward that is not the evaluation metric alone.

GraphRL-Dec's zscore reward is the Eq. 5 z-score of evaluate.py's SM, IFN, ICP
and NED: the very functions the primary convention scores with. The
kl0_ep2000 ablation improved that convention in 7 of 12 cases but the
binarized one in only 3 (RESULTS.md, section 4).

The dual reward is the mean of two Eq. 5 z-scores against the same four
peers (teacher, UnixCoder+Ward, UnixCoder+HDBSCAN, random):

    phi(s) = 0.5 * z_evaluate(s) + 0.5 * z_rldec(s)

- z_evaluate is the environment's own zscore potential, unchanged.
- z_rldec scores the current partial partition with RLDec's metric code
  (java_pipeline.metrics, preset "rldec") on the same graph.

The regularizers the environment adds to its potential (balance, semantic,
affinity, noise) are kept as they are. Checkpoint selection
(--select-by-decode) uses the same dual score, so selection cannot undo the
reward.

The weerasinghe convention (Eq. 1-4 on calls_graph.json) is in neither term.
It is the held-out check.

Nothing in neurosymbolic/ is edited: activate() patches three functions at
run time, and only environments loaded after it carry the dual objective.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from java_pipeline import metrics as M

_ON = {"active": False}


def _rldec(A: np.ndarray, labels: np.ndarray) -> dict:
    m = M.compute(A, labels, "rldec")
    return {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}


def _dense(names: list[str], graph: dict) -> np.ndarray:
    idx = {n: i for i, n in enumerate(names)}
    A = np.zeros((len(names), len(names)))
    for s, es in graph.items():
        for t, w in es.items():
            if s in idx and t in idx:
                A[idx[s], idx[t]] += float(w)
    return A


def _labels(env, parts: list[list[str]] | None = None) -> np.ndarray:
    if parts is None:
        return np.asarray(env.assignments, dtype=int)
    lab = np.full(len(env.names), -1, dtype=int)
    for k, p in enumerate(parts):
        for c in p:
            lab[env.name_to_idx[c]] = k
    return lab


def _peer_partitions(app: str, graph_exp: Path, names: list[str]) -> list[list[list[str]]]:
    """The same four peers build_peer_metrics uses, as partitions."""
    from neurosymbolic.rl import eval as ev
    exp = json.loads(Path(graph_exp).read_text())
    teacher = [c["classes"] for c in exp["clusters"]]
    K = max(2, len(teacher))
    paths = ev._default_paths(app)
    peers = [teacher]
    w, _ = ev._phase1_clustering_partition(app, paths, K)
    if w:
        peers.append(w)
    h, _ = ev._phase1_hdbscan_partition(app, paths)
    if h:
        peers.append(h)
    graph = exp["dependency_graph"]
    all_classes = sorted(set(graph) | {t for e in graph.values() for t in e})
    peers.append(ev._random_partition(all_classes, K))
    return peers


def activate() -> None:
    """Idempotent. Call after java_pipeline.rl_paths.activate()."""
    if _ON["active"]:
        return
    _ON["active"] = True
    from neurosymbolic.rl import graph_env as ge
    from neurosymbolic.rl import train as tr

    orig_load = ge.load_env_for_app

    def load_env_for_app(app, *, facts_path, graph_exp_json, embeddings_pt, config=None):
        env = orig_load(app, facts_path=facts_path, graph_exp_json=graph_exp_json,
                        embeddings_pt=embeddings_pt, config=config)
        env._dual_A = _dense(env.names, env.graph)
        env._dual_peers = [_rldec(env._dual_A, _labels(env, p))
                           for p in _peer_partitions(app, graph_exp_json, env.names)]
        return env

    ge.load_env_for_app = load_env_for_app
    tr.load_env_for_app = load_env_for_app

    orig_pot = ge.RailsDecompositionEnv._potential_from_metrics

    def potential(self, m):
        base = orig_pot(self, m)
        if not hasattr(self, "_dual_A") or getattr(self, "_reward_mode", "") != "zscore":
            return base
        ze = ge._weerasinghe_zscore({k: m[k] for k in ("SM", "IFN", "ICP", "NED")}, self._peer_metrics)
        zr = ge._weerasinghe_zscore(_rldec(self._dual_A, _labels(self)), self._dual_peers)
        return base - 0.5 * ze + 0.5 * zr

    ge.RailsDecompositionEnv._potential_from_metrics = potential

    orig_dec = tr._greedy_decode_score

    def decode_score(env, policy, device):
        score, sizes, raw = orig_dec(env, policy, device)
        if not hasattr(env, "_dual_A"):
            return score, sizes, raw
        from neurosymbolic.rl.decompose import greedy_decompose
        parts = greedy_decompose(env, policy, device)
        zr = ge._weerasinghe_zscore(_rldec(env._dual_A, _labels(env, parts)), env._dual_peers)
        return float(0.5 * score + 0.5 * zr), sizes, raw

    tr._greedy_decode_score = decode_score
