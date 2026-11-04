"""Decomposition metrics (SM, IFN, ICP, NED) and the Eq. 5 composite, with
every definitional choice made explicit.

The same partition gets different numbers from evaluate.py, from RLDec's
metric code, and from the text of Weerasinghe et al. 2026 (results/
RECON.md, section 3). This module computes all of them from one core so that
each reported number names the convention it uses.

Presets
-------
  evaluate     Reproduces evaluate.py (the Rails papers' metric code) exactly:
               weighted edges, self-calls excluded from SM and ICP, NED band
               [5, 20], SM of a single service = its scoh.
  weerasinghe  Eq. 1-4 as written in 2601.23141v1.pdf pp. 4-5. The formulas
               are those of `evaluate`; the difference is the INPUT, which
               must be a call-count matrix (calls, not resolved evidence
               weights). ICP is cross calls / all calls, the reading the
               paper's prose gives ("percentage of runtime calls").
  rldec        Reproduces decomp-rldec/rldec/metrics exactly: SM on the
               binarized matrix with the diagonal kept, ICP on log(1 + w)
               with the diagonal kept, NED band [5, 19], SM = IFN = 0 when
               there are fewer than two services. Outliers dropped, as in
               rldec/callbacks.py:85-88.

Eq. 5
-----
  eq5_scores(..., convention="as_written")    population std, divide by 6
                                              (evaluate.py:199-249).
  eq5_scores(..., convention="as_published")  sample std (ddof=1), divide by
               7. This reproduces all 35 Score cells of Weerasinghe Table 1
               from the metric cells beside them; the text's divisor of 6
               reproduces none (results/recon/eq5_implied_weights.out).

Input convention: a dense matrix A with A[i, j] = weight of i -> j over a
fixed node order, and an integer label per node (-1 = unassigned).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Mapping, Sequence

import numpy as np


@dataclass(frozen=True)
class Convention:
    name: str
    sm_binarize: bool          # SM on (A > 0) instead of A
    sm_self_loops: bool        # keep A[i, i] in intra-service cohesion
    icp_log1p: bool            # ICP on log(1 + A)
    icp_self_loops: bool       # keep A[i, i] in the ICP denominator
    ned_band: tuple[int, int]  # inclusive service-size band
    sm_single_zero: bool       # SM = 0 when fewer than two services
    outliers: str              # "drop" or "singletons" for label -1


PRESETS: dict[str, Convention] = {
    "evaluate": Convention("evaluate", False, False, False, False, (5, 20), False, "drop"),
    "weerasinghe": Convention("weerasinghe", False, False, False, False, (5, 20), False, "drop"),
    "rldec": Convention("rldec", True, True, True, True, (5, 19), True, "drop"),
}


def _prepare(A: np.ndarray, labels: Sequence[int], outliers: str):
    labels = np.asarray(labels, dtype=int)
    A = np.asarray(A, dtype=float)
    assert A.shape == (len(labels), len(labels)), "A must be N x N over the label order"
    if outliers == "drop":
        keep = labels != -1
        A, labels = A[keep][:, keep], labels[keep]
    elif outliers == "singletons":
        labels = labels.copy()
        out = labels == -1
        labels[out] = labels.max(initial=-1) + 1 + np.arange(out.sum())
    else:
        raise ValueError(f"unknown outlier policy {outliers!r}")
    ids, labels = np.unique(labels, return_inverse=True)
    onehot = np.zeros((len(labels), len(ids)))
    onehot[np.arange(len(labels)), labels] = 1.0
    return A, labels, onehot


def structural_modularity(A, onehot, conv: Convention) -> float:
    K = onehot.shape[1]
    if K == 0 or (K < 2 and conv.sm_single_zero):
        return 0.0
    B = (A > 0).astype(float) if conv.sm_binarize else A.copy()
    if not conv.sm_self_loops:
        np.fill_diagonal(B, 0.0)
    m = onehot.sum(0)
    C = onehot.T @ B @ onehot / np.outer(m, m)
    cohesion = np.trace(C)
    if K < 2:
        return float(cohesion)
    coupling = C.sum() - cohesion          # ordered pairs k != l
    return float(cohesion / K - coupling / (K * (K - 1)))


def interface_number(A, onehot) -> float:
    K = onehot.shape[1]
    if K <= 1:
        return 0.0
    inbound = (onehot.T @ (A > 0)) * (1.0 - onehot.T)   # [service, node]: calls from other services
    return float((inbound.sum(0) > 0).sum() / K)


def inter_partition_calls(A, onehot, conv: Convention) -> float:
    if onehot.shape[1] == 0:
        return 0.0
    T = np.log1p(A) if conv.icp_log1p else A.copy()
    if not conv.icp_self_loops:
        np.fill_diagonal(T, 0.0)
    S = onehot.T @ T @ onehot
    total = S.sum()
    return float((total - np.trace(S)) / total) if total > 0 else 0.0


def non_extreme_distribution(onehot, band: tuple[int, int]) -> float:
    K = onehot.shape[1]
    if K == 0:
        return 1.0
    m = onehot.sum(0)
    return float(1.0 - ((m >= band[0]) & (m <= band[1])).sum() / K)


def compute(A, labels, convention: str | Convention = "evaluate") -> dict:
    """All four metrics plus service count and coverage for one partition."""
    conv = PRESETS[convention] if isinstance(convention, str) else convention
    labels = np.asarray(labels, dtype=int)
    coverage = float((labels != -1).mean()) if len(labels) else 0.0
    A2, _, onehot = _prepare(A, labels, conv.outliers)
    return {
        "SM": structural_modularity(A2, onehot, conv),
        "IFN": interface_number(A2, onehot),
        "ICP": inter_partition_calls(A2, onehot, conv),
        "NED": non_extreme_distribution(onehot, conv.ned_band),
        "num_ms": int(onehot.shape[1]),
        "coverage": coverage,
        "convention": asdict(conv),
    }


def from_graph(graph: Mapping[str, Mapping[str, float]],
               partitions: Sequence[Sequence[str]],
               nodes: Sequence[str] | None = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Adapter from the pipeline's JSON shapes (dependency_graph dict-of-dicts,
    clusters as lists of names) to (A, labels, node order). Nodes default to
    every name in the graph or the partitions, sorted."""
    if nodes is None:
        names = set(graph) | {t for e in graph.values() for t in e}
        names |= {c for p in partitions for c in p}
        nodes = sorted(names)
    idx = {n: i for i, n in enumerate(nodes)}
    A = np.zeros((len(nodes), len(nodes)))
    for s, edges in graph.items():
        if s not in idx:
            continue
        for t, w in edges.items():
            if t in idx:
                A[idx[s], idx[t]] += float(w)
    labels = np.full(len(nodes), -1, dtype=int)
    for k, p in enumerate(partitions):
        for c in p:
            if c in idx:
                labels[idx[c]] = k
    return A, labels, list(nodes)


def eq5_scores(metrics_by_tool: Mapping[str, Mapping[str, float]],
               convention: str = "as_written") -> dict[str, float]:
    """Weerasinghe Eq. 5 over one benchmark's pool of tools.

    as_written    population std, divide by sum|w| = 6 (paper text, evaluate.py).
    as_published  sample std, divide by 7 (reproduces Table 1's Score column).
    A metric with zero spread over the pool makes every score NaN, as in
    evaluate.compute_weerasinghe_scores.
    """
    ddof, divisor = {"as_written": (0, 6.0), "as_published": (1, 7.0)}[convention]
    w = {"SM": 3.0, "IFN": -1.0, "ICP": -1.0, "NED": -1.0}
    tools = list(metrics_by_tool)
    X = np.array([[metrics_by_tool[t][m] for m in w] for t in tools], dtype=float)
    sd = X.std(0, ddof=ddof)
    if np.any(sd == 0) or np.isnan(X).any():
        return {t: float("nan") for t in tools}
    Z = (X - X.mean(0)) / sd
    s = Z @ np.array(list(w.values())) / divisor
    return {t: float(v) for t, v in zip(tools, s)}
