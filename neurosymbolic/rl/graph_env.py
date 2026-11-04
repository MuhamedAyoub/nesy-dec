"""RailsDecompositionEnv — the Phase 3 MDP.

Sequential class-to-cluster assignment over a rails-aware coupling graph.
Pure Python + numpy (no torch) so the env can be exercised from notebooks,
unit tests, or replayed for diagnostics without GPU dependencies.

Reward design (potential-based shaping)
---------------------------------------
The objective is the Weerasinghe Eq.5 utility U of the *final* partition.
Per-step reward is the **potential-based shaping** term

    F(s, s') = gamma * U(s') - U(s)

where U is the SAME Eq.5 utility evaluated on the partial partition. Ng,
Harada & Russell (1999) prove this leaves the optimal policy unchanged
relative to a terminal-only U reward, while giving PPO dense per-step
credit. Because U(empty)=0, the discounted episode return telescopes to
gamma^T * U(final) — i.e. PPO maximizes the true metric, not a proxy.

This replaces the previous dense ΔSM signal, which rewarded merging
everything into one cluster (SM = mu/m^2 grows when dense classes pile up)
and ignored the NED size constraint until the terminal step. That proxy
was *anti-correlated* with U and drove a degenerate "one giant cluster +
singletons" policy that scored below random.

We add one small structural guard: a per-step penalty for placing a class
into a cluster that already exceeds the NED max_size, so the agent feels
the size constraint locally instead of only at the end.

Action masking
--------------
At step t, when placing class `i`, every cluster id k ∈ {0..K-1} is legal
*unless* some class j already in cluster k is in `cannot_link(i, j)`.
Empty clusters are always legal (we never force a class into a cluster
that already excludes it). This implements the symbolic prior as a hard
constraint at decision time — something agglomerative clustering can't do.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# Reuse repo-level metric functions so the reward matches the evaluator.
REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from vendor.ror_msi.evaluate import (  # noqa: E402
    compute_icp,
    compute_ifn,
    compute_ned,
    compute_sm,
)


# Weights from Weerasinghe Eq.5. We use them directly on raw metric values
# rather than z-normalizing across tools — z-norm requires multiple tools and
# adds noise (different baseline tools per call). For PPO we want a stable
# scalar utility per partition.
_W = {"SM": 3.0, "IFN": -1.0, "ICP": -1.0, "NED": -1.0}
_SUM_ABS_W = sum(abs(v) for v in _W.values())  # 6.0


class _IncrementalUtility:
    """Maintains Weerasinghe Eq.5 U over a *growing* partition.

    Classes are placed one at a time; after each placement we update the
    running cluster bookkeeping in O(deg(node) + K) and recompute U exactly
    — no O(N·E) rescan. The recomputed U matches `_partition_utility` on the
    same partial partition (verified in the smoke test), so the reward stays
    consistent with the evaluator.

    Bookkeeping per cluster k:
      size[k]       number of classes placed in k
      intra[k]      directed call count with BOTH endpoints in k
    Cross-cluster traffic is tracked as a dict keyed by sorted (k1,k2).

    Eq.5 (raw-metric form, IFN normalised by K):
      U = (3*SM - IFN/K - ICP - NED) / 6
    """

    def __init__(self, n_nodes: int, K: int, min_size: int, max_size: int,
                 adj_directed: list[list[tuple[int, int]]],
                 unit_embeddings: np.ndarray | None = None) -> None:
        self.K = K
        self.min_size = min_size
        self.max_size = max_size
        # adj_directed[i] = list of (j, w) for directed edge i->j (j != i).
        self._adj = adj_directed
        # node -> cluster (-1 unassigned)
        self.assign = [-1] * n_nodes
        # (B) Semantic cohesion bookkeeping. `unit_embeddings` are L2-normalized
        # rows; per cluster we keep the running SUM of member unit-vectors. Then
        # the cluster's mean-to-centroid cosine is ||sum||^2 / size^2 — i.e. the
        # average pairwise cosine of its members (incl. self). This is the
        # semantic-cohesion analogue of HyDec's TF-IDF cosine, computed in O(d)
        # per placement (no pairwise loop).
        self._emb = unit_embeddings
        self._emb_dim = 0 if unit_embeddings is None else unit_embeddings.shape[1]
        self._emb_sum = (np.zeros((K, self._emb_dim), dtype=np.float64)
                         if unit_embeddings is not None else None)
        self.size = [0] * K
        self.intra = [0] * K                       # directed intra calls per cluster
        self.cross: dict[tuple[int, int], int] = {}  # (min,max) -> directed cross calls (both dirs)
        # interface nodes: a node is an interface of its cluster if some node
        # in another cluster calls it. Track per-node incoming-from-outside count.
        self._ext_in = [0] * n_nodes               # calls into node from other clusters
        self._iface_count = [0] * K                # number of interface nodes per cluster
        self.total_calls = 0                       # total inter-class directed calls placed
        self.total_cross = 0                       # cross-cluster directed calls placed
        # reverse adjacency for interface updates: who calls node i
        self._radj: list[list[tuple[int, int]]] = [[] for _ in range(n_nodes)]
        for i, outs in enumerate(adj_directed):
            for (j, w) in outs:
                self._radj[j].append((i, w))

    def place(self, node: int, cluster: int) -> None:
        """Assign `node` to `cluster`, updating all running aggregates."""
        assert self.assign[node] == -1
        self.assign[node] = cluster
        self.size[cluster] += 1
        if self._emb_sum is not None:
            self._emb_sum[cluster] += self._emb[node]
        # An edge is only counted once BOTH endpoints are placed — that is the
        # exact set `compute_sm/icp/ifn` iterate over. So here we classify every
        # edge incident to `node` whose other endpoint is already placed.
        #
        # Outgoing edges node -> j  (node is source).
        for (j, w) in self._adj[node]:
            cj = self.assign[j]
            if cj == -1:
                continue  # j unplaced; this edge is classified when j is placed
            self._classify(node, cluster, j, cj, w)
        # Incoming edges i -> node  (node is target).
        for (i, w) in self._radj[node]:
            ci = self.assign[i]
            if ci == -1:
                continue  # i unplaced; classified when i is placed
            self._classify(i, ci, node, cluster, w)

    def _classify(self, src: int, csrc: int, tgt: int, ctgt: int, w: int) -> None:
        """Account one directed edge src->tgt with both endpoints placed."""
        self.total_calls += w
        if csrc == ctgt:
            self.intra[csrc] += w
        else:
            self.total_cross += w
            key = (min(csrc, ctgt), max(csrc, ctgt))
            self.cross[key] = self.cross.get(key, 0) + w
            # tgt is called from outside its cluster -> interface of ctgt.
            self._bump_iface(tgt, ctgt)

    def _bump_iface(self, node: int, cluster: int) -> None:
        if self._ext_in[node] == 0:
            self._iface_count[cluster] += 1
        self._ext_in[node] += 1

    def utility(self) -> dict:
        """Exact Eq.5 metrics over currently-placed nodes."""
        active = [k for k in range(self.K) if self.size[k] > 0]
        M = len(active)
        if M == 0:
            return {"SM": 0.0, "IFN": 0.0, "ICP": 0.0, "NED": 1.0,
                    "num_ms": 0, "U": 0.0}
        # SM
        scoh = 0.0
        for k in active:
            m = self.size[k]
            scoh += self.intra[k] / (m * m) if m > 0 else 0.0
        avg_scoh = scoh / M
        scop_sum = 0.0
        for (a, b), g in self.cross.items():
            ma, mb = self.size[a], self.size[b]
            if ma > 0 and mb > 0:
                scop_sum += g / (2 * ma * mb)
        denom_scop = (M * (M - 1)) / 2 if M > 1 else 1.0
        sm = avg_scoh - scop_sum / denom_scop
        # IFN = mean interface count over active clusters
        ifn = sum(self._iface_count[k] for k in active) / M
        # ICP = cross / total
        icp = (self.total_cross / self.total_calls) if self.total_calls > 0 else 0.0
        # NED = 1 - frac of clusters in [min,max]
        non_extreme = sum(1 for k in active
                          if self.min_size <= self.size[k] <= self.max_size)
        ned = 1.0 - non_extreme / M
        ifn_norm = ifn / M
        u = (_W["SM"] * sm + _W["IFN"] * ifn_norm
             + _W["ICP"] * icp + _W["NED"] * ned) / _SUM_ABS_W
        return {"SM": sm, "IFN": ifn, "ICP": icp, "NED": ned,
                "num_ms": M, "U": float(u),
                "SemCoh": self.semantic_cohesion(active)}

    def semantic_cohesion(self, active: list[int] | None = None) -> float:
        """SIZE-WEIGHTED mean within-cluster UnixCoder cosine over clusters that
        reach min_size — the neuro-symbolic semantic signal.

        For a cluster with unit-vector sum S and size m, the mean pairwise cosine
        of its members (incl. self-pairs) is ||S||^2 / m^2 — O(d), no pairwise
        loop. We then weight each cluster by its size and divide by the total
        placed-in-band count:

            SemCoh = sum_{k: m_k>=min_size} m_k * (||S_k||^2 / m_k^2)
                     ----------------------------------------------------
                          sum_{k: m_k>=min_size} m_k

        CRITICAL: clusters with m < min_size (singletons especially) are EXCLUDED.
        A singleton has ||S||^2/1 = 1.0 — trivially "perfectly cohesive" — so the
        naive mean PAID the agent to spin off singletons (industrial-x got 8). Requiring
        m>=min_size removes that exploit; semantics now rewards only real,
        in-band cohesive services. Returns 0.0 if no in-band cluster exists.
        """
        if self._emb_sum is None:
            return 0.0
        if active is None:
            active = [k for k in range(self.K) if self.size[k] > 0]
        num = 0.0
        denom = 0.0
        for k in active:
            m = self.size[k]
            if m >= self.min_size:           # ignore singletons / tiny clusters
                s = self._emb_sum[k]
                coh = float(s @ s) / (m * m)
                num += m * coh
                denom += m
        return (num / denom) if denom > 0 else 0.0


def _weerasinghe_zscore(
    rl_metrics: dict, peer_metrics: list[dict]
) -> float:
    """The EXACT Eq.5 z-normalized Score that evaluate.compute_weerasinghe_scores
    assigns to the RL partition, given a FIXED set of peer metric vectors.

    rl_metrics:    {"SM","IFN","ICP","NED"} for the candidate partition.
    peer_metrics:  list of {"SM","IFN","ICP","NED"} for the fixed baselines
                   (mvc, rails_aware_hc, phase1_clustering, random).

    Returns the RL tool's score = sum_m w_m * z(x_{m,rl}) / sum|w|, where z is
    standardized over {peers + rl}. Matches evaluate.py to float precision.

    If any metric column has zero variance across the pool (degenerate), that
    metric is skipped from the sum rather than nuking the whole score — this
    only happens transiently very early in an episode and the terminal step is
    always well-conditioned.
    """
    import math as _m
    cols = ("SM", "IFN", "ICP", "NED")
    pool = peer_metrics + [rl_metrics]
    score = 0.0
    for met in cols:
        vals = [p[met] for p in pool]
        mu = sum(vals) / len(vals)
        var = sum((v - mu) ** 2 for v in vals) / len(vals)
        sigma = _m.sqrt(var)
        if sigma == 0:
            continue  # skip degenerate column (transient, early-episode only)
        z = (rl_metrics[met] - mu) / sigma
        score += _W[met] * z
    return score / _SUM_ABS_W


def _partition_utility(partitions, graph) -> dict:
    """Compute (SM, IFN, ICP, NED, U) for a partition.

    U = (3·SM − IFN/K − ICP − NED) / 6   (Weerasinghe weights, IFN normalized
    by K to match the legacy `compute_composite_score`). Higher is better.

    Returns dict {SM, IFN, ICP, NED, num_ms, U}.
    """
    if not partitions:
        return {"SM": 0.0, "IFN": 0.0, "ICP": 0.0, "NED": 1.0, "num_ms": 0, "U": 0.0}
    sm = compute_sm(partitions, graph)
    ifn = compute_ifn(partitions, graph)
    icp = compute_icp(partitions, graph)
    ned = compute_ned(partitions)
    K = max(1, len(partitions))
    ifn_norm = ifn / K
    u = (_W["SM"] * sm + _W["IFN"] * ifn_norm + _W["ICP"] * icp + _W["NED"] * ned) / _SUM_ABS_W
    return {"SM": sm, "IFN": ifn, "ICP": icp, "NED": ned, "num_ms": K, "U": float(u)}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class EnvConfig:
    """Environment hyperparameters.

    `n_clusters`: target K. If None, taken from the baseline partition at
    reset so the agent and baseline are compared at the same K.

    `lambda_must_link` / `lambda_cannot_link`: shaped per-step bonus/penalty
    for satisfying / violating soft constraints. Kept small (0.05–0.1) so the
    terminal Weerasinghe score remains the dominant signal.

    `dense_reward_coef`: scales the per-step ΔSM signal. Setting to 0
    recovers the original terminal-only reward. Default 1.0 gives PPO dense
    credit-assignment per placement, which is critical at N=80+ steps.

    `node_order`: how to iterate through classes. "degree" (highest-degree
    first) is the standard graph-partitioning heuristic and gives the early
    actions the most context. "random" is for ablation / regularization.
    """

    n_clusters: int | None = None
    # How K is chosen when `n_clusters` is None:
    #   "ned_target" — round(N / 12.5), floored at the baseline K, so the agent
    #                  has room to build NED-'good' [5,20] services (default).
    #   "baseline"   — copy the baseline partition's K exactly (legacy).
    k_policy: str = "ned_target"
    lambda_must_link: float = 0.1
    lambda_cannot_link: float = 0.1
    # `shaping_coef` scales the potential-based per-step reward
    #   F = shaping_coef * (gamma * U(s') - U(s)).
    # Default 1.0 means PPO's discounted return equals the true Eq.5 utility
    # of the final partition (Ng et al. 1999). Set 0 for terminal-only U.
    shaping_coef: float = 1.0
    # Must match the PPO discount so the telescoping return is exact.
    gamma: float = 0.99
    # Per-step penalty for placing a class into a cluster that is already at
    # or above the NED max_size — gives the size constraint a local signal.
    oversize_penalty: float = 0.02
    # `dense_reward_coef` is retained for CLI/back-compat but no longer drives
    # the old ΔSM proxy; it is an alias multiplier on `shaping_coef`.
    dense_reward_coef: float = 1.0
    node_order: str = "degree"  # "degree" | "random" | "name"
    seed: int = 42
    # Reward objective:
    #   "raw_u"  — potential shaping toward raw Weerasinghe U (legacy; the
    #              NED term is bounded at -1/6 so it under-weights balance and
    #              the agent collapses to one giant cluster).
    #   "zscore" — potential shaping toward the EXACT z-normalized Eq.5 Score
    #              the evaluator reports, computed against `peer_metrics`. This
    #              is the leaderboard number, so the agent optimizes what it is
    #              actually graded on (being worst-NED among peers costs ~-1.5σ).
    reward_mode: str = "raw_u"
    # Balance regularizer folded into the potential Φ. The z-Score / raw-U
    # objective is exploitable: a single giant cluster drives ICP=IFN=0 and
    # still scores well (the giant is a wide local trap). We subtract
    #   balance_coef * oversize_frac,  oversize_frac = sum(max(0,size_k-hi))/N
    # which is ~0 for balanced partitions (rails) but large for a giant. With
    # balance_coef≈0.3 the giant drops below rails while good partitions are
    # almost untouched (critical coef on astuto ≈0.095; 0.3 = ~3x margin).
    # Because it's part of Φ it telescopes like any potential shaping term.
    balance_coef: float = 0.0
    # Fixed peer metric vectors for the zscore reward; each is a dict with keys
    # SM/IFN/ICP/NED. Order doesn't matter (z-norm is symmetric). Must be the
    # SAME baselines eval.py grades against (mvc, rails_aware_hc, phase1, random).
    peer_metrics: list[dict] | None = None

    # --- HyDec-inspired enhancements (each independently ablatable) ----------
    # (A) Outlier action: add a (K+1)-th action that leaves a class UNASSIGNED
    #     (-1), like HyDec's min_samples outliers. Unassigned classes are
    #     excluded from SM/IFN/ICP/NED. Lets the agent drop noise instead of
    #     forcing every class into a service (which hurts NED/SM).
    allow_outliers: bool = False
    # (B) Semantic cohesion: add semantic_coef * mean_k(avg pairwise UnixCoder
    #     cosine within cluster k) to the reward potential. Fuses the semantic
    #     signal HyDec clusters on; our embeddings are already in the env but
    #     never entered the (purely structural) objective before.
    semantic_coef: float = 0.0
    # (C) HyDec-normalized call weights: normalize each call by the target's
    #     incoming-call total (symmetric average) before building the graph the
    #     reward metrics see. Raises SM the way HyDec's call_similarity does.
    #     OFF by default to preserve evaluator comparability; ablate separately.
    normalize_calls: bool = False
    # (E) Soft-affinity reward: the symbolic analysis emits graded co-location
    #     preferences (soft_affinity: [a, b, weight, provenance]) — the richest
    #     symbolic signal, previously UNUSED by Phase 3. Per step, add
    #     soft_affinity_coef * sum(weight) over already-placed affinity partners
    #     that share the chosen cluster. The symbolic complement to the neural
    #     semantic_coef term.
    soft_affinity_coef: float = 0.0
    # (C2) Learned soft-affinity weights. When True, the soft_affinity PAIRS are
    # taken from the symbolic facts as usual, but each pair's WEIGHT is replaced
    # by the UnixCoder cosine similarity of the two classes (clamped to [0,1])
    # instead of the hand-set 0.15-1.0 constant. Turns a heuristic prior into a
    # learned neuro-symbolic bridge: the embedding decides how strongly two
    # symbolically-related classes should co-locate.
    affinity_from_embeddings: bool = False
    # (C1) LLM-inferred behavioral-coupling reward. Consumes the
    # `inferred_coupling` facts (produced by neurosymbolic/infer_coupling.py):
    # confidence-weighted pairs that likely share an execution flow (transitive
    # call reachability + optional LLM capability grouping, call-graph-validated).
    # Adds inferred_coupling_coef * sum(confidence) over already-placed inferred
    # partners sharing the chosen cluster --- the neural/behavioral complement to
    # the symbolic soft_affinity term. 0 disables.
    inferred_coupling_coef: float = 0.0
    # (F) Framework-noise prior: framework_noise lists boilerplate base classes
    #     (ApplicationController, ApplicationRecord, ...) that shouldn't anchor a
    #     service. With allow_outliers, reward outlier-ing a noise class by
    #     noise_coef; otherwise (no outlier action) apply a small penalty for
    #     co-clustering a noise class with normal classes.
    noise_coef: float = 0.0
    # (O2b) Hard per-cluster size cap = ceil(size_cap_factor * N / K). A cluster
    # at/above the cap becomes an ILLEGAL action (empty clusters & outlier slot
    # stay legal). Makes a giant structurally impossible instead of merely
    # penalized — the reward-based balance terms drift to a giant at large N.
    # 0 disables; 1.5 = at most ~1.5x the even share per service. Floored at the
    # NED max_size (20) so healthy in-band services are never blocked.
    size_cap_factor: float = 0.0


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _build_role_vocab(facts: dict) -> dict[str, int]:
    """Deterministic role -> int mapping for one-hot encoding.

    24-dir Rails layout: controllers/mailers/jobs/policies/workflows/models/
    helpers/lib/services/builders/presenters/validators/uploaders/finders/
    actions/channels/listeners/dispatchers/drops/fields/mailboxes/dashboards/
    classes/data + an "unknown" bucket. We fix this at construction so model
    weights stay compatible across apps.
    """
    roles = (
        "controllers", "mailers", "jobs", "policies", "workflows", "models",
        "helpers", "lib", "services", "builders", "presenters", "validators",
        "uploaders", "finders", "actions", "channels", "listeners",
        "dispatchers", "drops", "fields", "mailboxes", "dashboards",
        "classes", "data", "unknown",
    )
    return {r: i for i, r in enumerate(roles)}


def _node_features(
    names: list[str],
    embeddings: np.ndarray,
    role_of: dict[str, str],
    graph: dict[str, dict[str, int]],
    role_vocab: dict[str, int],
) -> np.ndarray:
    """Concat per-class features.

    Layout: [emb (d), role_one_hot (|R|), log_in_degree (1), log_out_degree (1)]
    Order is fixed; policy.py reads it positionally.
    """
    d = embeddings.shape[1]
    R = len(role_vocab)
    N = len(names)
    feats = np.zeros((N, d + R + 2), dtype=np.float32)
    feats[:, :d] = embeddings
    out_deg = np.zeros(N, dtype=np.float32)
    in_deg = np.zeros(N, dtype=np.float32)
    name_idx = {n: i for i, n in enumerate(names)}
    for src, edges in graph.items():
        if src not in name_idx:
            continue
        si = name_idx[src]
        for tgt, w in edges.items():
            if tgt not in name_idx or tgt == src:
                continue
            out_deg[si] += w
            in_deg[name_idx[tgt]] += w
    for i, n in enumerate(names):
        r = role_of.get(n, "unknown")
        feats[i, d + role_vocab.get(r, role_vocab["unknown"])] = 1.0
    feats[:, d + R] = np.log1p(in_deg)
    feats[:, d + R + 1] = np.log1p(out_deg)
    return feats


def _edge_index(
    names: list[str], graph: dict[str, dict[str, int]]
) -> tuple[np.ndarray, np.ndarray]:
    """Return (edge_index [2, E], edge_weight [E]).

    Treated as undirected for message passing: every directed call adds both
    (src, tgt) and (tgt, src) so the GNN sees a symmetric neighborhood.
    """
    name_idx = {n: i for i, n in enumerate(names)}
    src_list, tgt_list, w_list = [], [], []
    for s, edges in graph.items():
        if s not in name_idx:
            continue
        si = name_idx[s]
        for t, w in edges.items():
            if t not in name_idx or t == s:
                continue
            ti = name_idx[t]
            src_list.append(si); tgt_list.append(ti); w_list.append(float(w))
            src_list.append(ti); tgt_list.append(si); w_list.append(float(w))
    if not src_list:
        return np.zeros((2, 0), dtype=np.int64), np.zeros(0, dtype=np.float32)
    return (
        np.array([src_list, tgt_list], dtype=np.int64),
        np.array(w_list, dtype=np.float32),
    )


# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------

@dataclass
class EnvSnapshot:
    """Lightweight episode-state dump for logging and replay."""
    assignments: list[int]
    cursor: int
    step_reward: float
    cumulative_shaped: float


class RailsDecompositionEnv:
    """Sequential MDP: assign every class to one of K clusters.

    Parameters
    ----------
    facts: parsed symbolic facts payload (must_link, cannot_link, role_groups)
    graph: dep graph {src_class: {tgt_class: weight}}  (from rails-aware HC
           or MVC exp_*.json — whichever the trainer chose as the reference)
    embeddings: ndarray [N_classes, emb_dim]    Phase 1 UnixCoder vectors
    names: list of class names matching embedding rows
    baseline_partitions: the partition we score against for ΔScore reward
    config: EnvConfig
    """

    def __init__(
        self,
        facts: dict,
        graph: dict[str, dict[str, int]],
        embeddings: np.ndarray,
        names: list[str],
        baseline_partitions: list[list[str]],
        config: EnvConfig | None = None,
    ) -> None:
        self.cfg = config or EnvConfig()
        self.rng = np.random.default_rng(self.cfg.seed)

        # Filter to classes present in BOTH the embedding bank and the graph
        # — anything outside both is unscorable, so it can't drive learning.
        graph_nodes: set[str] = set(graph.keys())
        for src, e in graph.items():
            graph_nodes.update(e.keys())
        emb_idx = {n: i for i, n in enumerate(names)}
        kept = [n for n in names if n in graph_nodes and n in emb_idx]
        if len(kept) < 2:
            raise ValueError(
                f"too few graph-active classes with embeddings: {len(kept)}"
            )
        self.names = kept
        self.name_to_idx = {n: i for i, n in enumerate(self.names)}
        self.embeddings = embeddings[[emb_idx[n] for n in self.names]]
        # L2-normalized embeddings for the semantic-cohesion reward (B). Cosine
        # cohesion is computed from unit vectors so the running cluster sum gives
        # mean pairwise cosine directly. Built once; reused every episode.
        _emb = np.asarray(self.embeddings, dtype=np.float64)
        _norms = np.linalg.norm(_emb, axis=1, keepdims=True)
        _norms[_norms == 0] = 1.0
        self._unit_emb = (_emb / _norms).astype(np.float64)

        # Carry the graph but trimmed to kept names — keeps SM/ICP fair.
        self.graph: dict[str, dict[str, int]] = {}
        for s, edges in graph.items():
            if s not in self.name_to_idx:
                continue
            inner = {t: w for t, w in edges.items() if t in self.name_to_idx}
            if inner:
                self.graph[s] = inner

        # (C) HyDec-style call normalization: scale each call s->t by t's total
        # incoming weight so heavily-called hubs don't dominate SM/ICP. Mirrors
        # decomp-hydec call_similarity (each call / target incoming total). OFF
        # by default to keep evaluator comparability; enabled via normalize_calls.
        if getattr(self.cfg, "normalize_calls", False):
            incoming: dict[str, float] = {}
            for s, edges in self.graph.items():
                for t, w in edges.items():
                    incoming[t] = incoming.get(t, 0.0) + w
            norm: dict[str, dict[str, int]] = {}
            for s, edges in self.graph.items():
                inner = {}
                for t, w in edges.items():
                    denom = incoming.get(t, 0.0)
                    # scale to keep integer-ish magnitudes the metrics expect;
                    # *len so total mass is preserved on average.
                    val = (w / denom) if denom > 0 else 0.0
                    inner[t] = max(1, int(round(val * len(self.name_to_idx))))
                if inner:
                    norm[s] = inner
            self.graph = norm

        # Constraints — store as sets of sorted-tuple keys.
        self.must_link: set[tuple[str, str]] = set()
        for triple in facts.get("must_link", []):
            a, b = triple[0], triple[1]
            if a in self.name_to_idx and b in self.name_to_idx and a != b:
                self.must_link.add((min(a, b), max(a, b)))
        self.cannot_link: set[tuple[str, str]] = set()
        for triple in facts.get("cannot_link", []):
            a, b = triple[0], triple[1]
            if a in self.name_to_idx and b in self.name_to_idx and a != b:
                self.cannot_link.add((min(a, b), max(a, b)))

        # Role lookup for features.
        role_of: dict[str, str] = {}
        for role, members in facts.get("role_groups", {}).items():
            for m in members:
                role_of[m] = role
        self.role_of = role_of

        # NED size band (matches evaluate.compute_ned defaults).
        self._ned_min, self._ned_max = 5, 20

        # K from baseline if not configured.
        baseline_filtered = [[c for c in p if c in self.name_to_idx]
                             for p in baseline_partitions]
        baseline_filtered = [p for p in baseline_filtered if p]
        self.baseline_partitions = baseline_filtered
        if self.cfg.n_clusters is not None:
            self.K = max(2, self.cfg.n_clusters)
        elif self.cfg.k_policy == "ned_target":
            # Give the agent enough clusters to form NED-'good' [5,20] services.
            # Target the mid-band size (~12.5) so most services can land in band,
            # but never go BELOW the baseline K (keeps the comparison fair) and
            # cap so we don't explode the action space.
            n = len(self.names)
            mid = (self._ned_min + self._ned_max) / 2.0   # 12.5
            ned_k = max(2, round(n / mid))
            self.K = max(len(baseline_filtered), ned_k, 2)
        else:  # "baseline"
            self.K = max(2, len(baseline_filtered))

        # (O2b) Per-cluster hard size cap = ceil(size_cap_factor * N / K). With
        # the default factor 1.5 and balanced K, no service can exceed ~1.5x the
        # even share — kills the giant by construction. None disables the cap.
        scf = getattr(self.cfg, "size_cap_factor", 0.0)
        if scf and scf > 0:
            import math as _math
            # Cap = factor * even-share, but NEVER below NED max_size (20) — else
            # we'd forbid healthy services. On big apps the teacher has good
            # services well above 20 (industrial-x up to 53), so the factor*N/K term is
            # what lets those exist while still killing true giants. e.g. industrial-x
            # N=258 K=24 factor=1.5 -> 16 -> floored to 20; factor=3 -> 32.
            self._size_cap = max(self._ned_max,
                                 _math.ceil(scf * len(self.names) / max(1, self.K)))
        else:
            self._size_cap = None

        # Pre-compute static graph artifacts the policy needs every step.
        self.role_vocab = _build_role_vocab(facts)
        self.node_features = _node_features(
            self.names, self.embeddings, self.role_of, self.graph, self.role_vocab,
        )
        self.edge_index, self.edge_weight = _edge_index(self.names, self.graph)

        # Baseline partition utility (Weerasinghe weights on raw metrics).
        # Computed ONCE here — never re-sampled per episode, so the reward
        # reference point is stable across rollouts.
        self._baseline_metrics = _partition_utility(self.baseline_partitions, self.graph)
        # Back-compat alias for callers (train.py, decompose.py logs).
        self._baseline_eq5 = self._baseline_metrics["U"]

        # Reward objective. For "zscore" we need the fixed peer metric vectors.
        self._reward_mode = getattr(self.cfg, "reward_mode", "raw_u")
        self._peer_metrics = getattr(self.cfg, "peer_metrics", None)
        if self._reward_mode in ("zscore", "multiplicative") and not self._peer_metrics:
            raise ValueError(
                f"reward_mode='{self._reward_mode}' requires cfg.peer_metrics (the "
                "fixed mvc/rails_aware_hc/phase1/random metric vectors to z-norm against)."
            )

        # Directed adjacency (index space) for the incremental utility tracker.
        # adj_directed[i] = [(j, w), ...] for each call i -> j, j != i.
        self._adj_directed: list[list[tuple[int, int]]] = [
            [] for _ in range(len(self.names))
        ]
        for s, edges in self.graph.items():
            si = self.name_to_idx[s]
            for t, w in edges.items():
                ti = self.name_to_idx[t]
                if ti != si:
                    self._adj_directed[si].append((ti, int(w)))

        # Pre-compute the placement order.
        self._order = self._make_order()

        # Per-class constraint partners (for fast masking).
        self._cannot_partners: dict[int, set[int]] = {i: set() for i in range(len(self.names))}
        for a, b in self.cannot_link:
            ia, ib = self.name_to_idx[a], self.name_to_idx[b]
            self._cannot_partners[ia].add(ib)
            self._cannot_partners[ib].add(ia)
        self._must_partners: dict[int, set[int]] = {i: set() for i in range(len(self.names))}
        for a, b in self.must_link:
            ia, ib = self.name_to_idx[a], self.name_to_idx[b]
            self._must_partners[ia].add(ib)
            self._must_partners[ib].add(ia)

        # (E) Soft-affinity partners: idx -> {partner_idx: weight}. Built only
        # when soft_affinity_coef>0 (industrial-x has ~17k pairs, so skip the work when
        # unused). Entry shape: [name_a, name_b, weight, provenance].
        self._soft_partners: dict[int, dict[int, float]] = {}
        learn_aff = getattr(self.cfg, "affinity_from_embeddings", False)
        if getattr(self.cfg, "soft_affinity_coef", 0.0):
            self._soft_partners = {i: {} for i in range(len(self.names))}
            for entry in facts.get("soft_affinity", []):
                if len(entry) < 3:
                    continue
                a, b, w = entry[0], entry[1], float(entry[2])
                if a in self.name_to_idx and b in self.name_to_idx and a != b:
                    ia, ib = self.name_to_idx[a], self.name_to_idx[b]
                    if learn_aff:
                        # (C2) LEARNED weight = UnixCoder cosine of the pair,
                        # clamped to [0,1]. Unit embeddings -> dot product is the
                        # cosine. Replaces the hand-set constant `w`.
                        w = max(0.0, float(self._unit_emb[ia] @ self._unit_emb[ib]))
                    # keep the max weight if a pair appears under several tags
                    self._soft_partners[ia][ib] = max(self._soft_partners[ia].get(ib, 0.0), w)
                    self._soft_partners[ib][ia] = max(self._soft_partners[ib].get(ia, 0.0), w)

        # (C1) Inferred-coupling partners: idx -> {partner_idx: confidence}.
        # Built only when inferred_coupling_coef>0. Same shape as soft_partners
        # but sourced from the LLM-inferred `inferred_coupling` facts.
        self._inferred_partners: dict[int, dict[int, float]] = {}
        if getattr(self.cfg, "inferred_coupling_coef", 0.0):
            self._inferred_partners = {i: {} for i in range(len(self.names))}
            for entry in facts.get("inferred_coupling", []):
                if len(entry) < 3:
                    continue
                a, b, c = entry[0], entry[1], float(entry[2])
                if a in self.name_to_idx and b in self.name_to_idx and a != b:
                    ia, ib = self.name_to_idx[a], self.name_to_idx[b]
                    self._inferred_partners[ia][ib] = max(self._inferred_partners[ia].get(ib, 0.0), c)
                    self._inferred_partners[ib][ia] = max(self._inferred_partners[ib].get(ia, 0.0), c)

        # (F) Framework-noise class indices (boilerplate base classes).
        self._noise_idx: set[int] = set()
        for name in facts.get("framework_noise", []):
            if name in self.name_to_idx:
                self._noise_idx.add(self.name_to_idx[name])

        # Mutable state.
        self.assignments: list[int] = []
        self.cursor: int = 0
        self._shaped_total: float = 0.0
        self.reset()

    # ---- order ----------------------------------------------------------

    def _make_order(self) -> list[int]:
        if self.cfg.node_order == "name":
            return list(range(len(self.names)))
        if self.cfg.node_order == "random":
            idx = list(range(len(self.names)))
            self.rng.shuffle(idx)
            return idx
        # default: highest total degree first
        deg = np.zeros(len(self.names))
        for src, edges in self.graph.items():
            si = self.name_to_idx[src]
            for tgt, w in edges.items():
                if tgt in self.name_to_idx:
                    deg[si] += w
                    deg[self.name_to_idx[tgt]] += w
        return list(np.argsort(-deg))

    # ---- core MDP ------------------------------------------------------

    def reset(self) -> None:
        self.assignments = [-1] * len(self.names)
        self.cursor = 0
        self._shaped_total = 0.0
        # Incremental Eq.5 utility tracker; U(empty)=0 so shaping telescopes.
        self._util = _IncrementalUtility(
            n_nodes=len(self.names), K=self.K,
            min_size=self._ned_min, max_size=self._ned_max,
            adj_directed=self._adj_directed,
            # Pass unit embeddings only when the semantic term is active, so the
            # tracker skips the bookkeeping otherwise.
            unit_embeddings=(self._unit_emb
                             if getattr(self.cfg, "semantic_coef", 0.0) else None),
        )
        # Potential Φ(empty). For raw_u, U(empty)=0. For zscore, the empty
        # partition's Φ is whatever the z-Score of (SM=0,IFN=0,ICP=0,NED=1)
        # is against the peers — a constant, so it cancels in the telescoping
        # return (return = γ^T·Φ(final) − Φ(empty)·… → dominated by Φ(final)).
        self._last_U = self._potential_from_metrics(self._util.utility())
        if self.cfg.node_order == "random":
            self._order = self._make_order()

    @property
    def done(self) -> bool:
        return self.cursor >= len(self.names)

    @property
    def current_node(self) -> int:
        """Index (in self.names) of the class to place next."""
        return self._order[self.cursor]

    @property
    def action_dim(self) -> int:
        """Number of actions the policy chooses among: K clusters, plus one
        extra 'outlier' action (leave unassigned) when allow_outliers is set."""
        return self.K + (1 if getattr(self.cfg, "allow_outliers", False) else 0)

    def legal_actions(self) -> np.ndarray:
        """Boolean mask of length action_dim. True = legal action.

        A cluster k is illegal iff some class already placed in k is a
        cannot_link partner of the current node. Empty clusters are always
        legal (the agent can always open a fresh service). When allow_outliers,
        the last slot (index K) is the always-legal 'leave unassigned' action.
        """
        node = self.current_node
        forbidden = set()
        cant = self._cannot_partners[node]
        if cant:
            for j, c in enumerate(self.assignments):
                if c >= 0 and j in cant:
                    forbidden.add(c)
        mask = np.ones(self.action_dim, dtype=bool)
        for k in forbidden:
            if 0 <= k < self.K:
                mask[k] = False

        # (O2b) Hard size cap: forbid placing into a NON-EMPTY cluster that has
        # already reached the cap. Empty clusters stay legal so the agent can
        # always open a fresh service (no dead-end), and the outlier slot (if
        # any) is untouched. This makes a giant cluster STRUCTURALLY IMPOSSIBLE —
        # the same masking trick that gives us 0 cannot-link violations — rather
        # than merely penalizing it in the reward (which drifts at large N).
        if self._size_cap is not None:
            for k in range(self.K):
                if 0 < self._util.size[k] >= self._size_cap:
                    mask[k] = False

        # If every cluster is forbidden (pathological cannot_link clique, or all
        # clusters full), fall back to "any cluster allowed" so the episode can
        # finish. Without the cap this matched the old behaviour exactly.
        if not mask.any():
            mask[:] = True
        return mask

    def _potential_from_metrics(self, m: dict) -> float:
        """Φ(s): the scalar the potential shaping climbs toward.

        raw_u         → the Weerasinghe raw U already computed by the tracker.
        zscore        → the EXACT z-normalized Eq.5 Score vs the fixed peers, so
                        the telescoped return equals the leaderboard number.
        multiplicative→ RLDec-style (Sellami et al. 2024): a non-negative quality
                        signal MULTIPLIED by the balance gate (1 − NED). A giant
                        has NED≈1 so its potential is crushed to ~0, regardless of
                        its SM/ICP — unlike the additive balance_coef, which only
                        shifts it by a constant and leaves it a finite attractor.
                        See [[rldec-reference-implementation]].
        """
        if self._reward_mode == "multiplicative":
            # Quality = shifted z-Score (>=0 so the gate can't flip its sign).
            # The gate (1-NED) in [0,1] zeroes out imbalanced partitions.
            rl_metrics = {"SM": m["SM"], "IFN": m["IFN"],
                          "ICP": m["ICP"], "NED": m["NED"]}
            quality = _weerasinghe_zscore(rl_metrics, self._peer_metrics)
            # Shift into the non-negative range; +3 comfortably exceeds the most
            # negative achievable z-Score so quality>=0 in practice. The gate
            # then scales it; a constant offset in Φ telescopes away (potential
            # shaping is invariant to Φ + const since U(empty) sets the baseline).
            quality = quality + 3.0
            gate = 1.0 - m["NED"]
            phi = quality * gate
        elif self._reward_mode == "zscore":
            rl_metrics = {"SM": m["SM"], "IFN": m["IFN"],
                          "ICP": m["ICP"], "NED": m["NED"]}
            phi = _weerasinghe_zscore(rl_metrics, self._peer_metrics)
        else:
            phi = m["U"]

        # Balance regularizer: subtract a penalty proportional to how many
        # classes sit ABOVE the NED max_size band, normalized by N. ~0 for
        # balanced partitions, large for a giant -> removes the collapse trap.
        bc = getattr(self.cfg, "balance_coef", 0.0)
        if bc:
            n_placed = sum(self._util.size)
            if n_placed > 0:
                oversize = sum(max(0, s - self._ned_max)
                               for s in self._util.size) / n_placed
                phi = phi - bc * oversize

        # (B) NEURO-SYMBOLIC semantic cohesion: reward clusters whose members are
        # semantically similar (UnixCoder cosine), not just structurally coupled.
        # This is the whole point of the neuro-symbolic approach — the semantic
        # signal now drives the objective, not just the GNN's input features.
        sc = getattr(self.cfg, "semantic_coef", 0.0)
        if sc:
            phi = phi + sc * m.get("SemCoh", 0.0)
        return phi

    def step(self, action: int) -> tuple[float, bool, dict]:
        """Apply `action` to the current node. Returns (reward, done, info).

        Reward = potential-based shaping on the true Eq.5 utility U:

            r_t = shaping * (gamma * U(s_{t+1}) - U(s_t))
                  + lambda_ml * (must_link partners now co-clustered)
                  - lambda_cl * (cannot_link partners now co-clustered)
                  - oversize_penalty * [target cluster already >= NED max_size]
                  + mask_penalty   (only if the caller violated the action mask)

        Summed over the episode the shaping term telescopes to
        gamma^T * U(final) (since U(empty)=0), so PPO's discounted return is
        exactly the true objective. The constraint/guard terms are small soft
        priors. No extra terminal reward is added — that would double-count.
        """
        if self.done:
            raise RuntimeError("step() called on terminated env; call reset()")
        legal = self.legal_actions()
        mask_penalty = 0.0
        if not legal[action]:
            # Caller violated the mask. Treat as a small penalty and snap
            # to the lowest-index legal cluster so the episode keeps moving.
            mask_penalty = -0.5
            action = int(np.argmax(legal))

        node = self.current_node

        # (A) Outlier action: index == K means "leave this class unassigned".
        # We advance the cursor without placing the node; it stays -1 and is
        # excluded from all metrics (like HyDec min_samples outliers). The
        # potential still updates (NED/SM change as fewer nodes are placed).
        if getattr(self.cfg, "allow_outliers", False) and action == self.K:
            self.cursor += 1
            coef = self.cfg.shaping_coef * self.cfg.dense_reward_coef
            cur_U = self._potential_from_metrics(self._util.utility())
            potential = coef * (self.cfg.gamma * cur_U - self._last_U)
            self._last_U = cur_U
            # (F) reward outlier-ing a framework-noise class (boilerplate belongs
            # outside real services), per the noise prior.
            noise_bonus = 0.0
            nc = getattr(self.cfg, "noise_coef", 0.0)
            if nc and node in self._noise_idx:
                noise_bonus = nc
            step_reward = potential + mask_penalty + noise_bonus
            if self.done:
                terminal = self._terminal_reward()
                info = {
                    "terminal_eq5": terminal["eq5"],
                    "baseline_eq5": self._baseline_eq5,
                    "delta_eq5": terminal["delta"],
                    "shaped_total": self._shaped_total,
                    "raw_metrics": terminal["raw"],
                }
                return step_reward, True, info
            return step_reward, False, {}

        shaped = self._shaped_reward(node, action)

        # Local size guard: discourage piling onto an already-oversized cluster.
        oversize = 0.0
        if self._util.size[action] >= self._ned_max:
            oversize = -self.cfg.oversize_penalty

        # Apply the assignment to BOTH the public list and the incremental
        # utility tracker, then read the new exact U for potential shaping.
        self.assignments[node] = int(action)
        self._util.place(node, int(action))
        self.cursor += 1
        self._shaped_total += shaped

        coef = self.cfg.shaping_coef * self.cfg.dense_reward_coef
        cur_U = self._potential_from_metrics(self._util.utility())
        potential = coef * (self.cfg.gamma * cur_U - self._last_U)
        self._last_U = cur_U

        step_reward = potential + shaped + oversize + mask_penalty

        if self.done:
            terminal = self._terminal_reward()
            info = {
                "terminal_eq5": terminal["eq5"],
                "baseline_eq5": self._baseline_eq5,
                "delta_eq5": terminal["delta"],
                "shaped_total": self._shaped_total,
                "raw_metrics": terminal["raw"],
            }
            return step_reward, True, info
        return step_reward, False, {}

    # ---- rewards -------------------------------------------------------

    def _shaped_reward(self, node: int, cluster: int) -> float:
        """Per-placement symbolic shaping (all relative to ALREADY-placed nodes):
          +λ_ml  per must_link partner now co-clustered,
          −λ_cl  per cannot_link partner now co-clustered (≈0 under masking),
          (E) +soft_affinity_coef * Σ weight over soft-affinity partners now
              co-clustered — the graded symbolic co-location signal,
          (F) −noise_coef when placing a framework-noise class into a NON-noise
              cluster (discourages boilerplate anchoring a real service; with
              allow_outliers the agent is instead rewarded for outlier-ing it,
              handled in step()).
        """
        bonus = 0.0
        for j in self._must_partners[node]:
            if 0 <= j < len(self.assignments) and self.assignments[j] == cluster:
                bonus += self.cfg.lambda_must_link
        penalty = 0.0
        for j in self._cannot_partners[node]:
            if 0 <= j < len(self.assignments) and self.assignments[j] == cluster:
                penalty += self.cfg.lambda_cannot_link

        # (E) graded soft affinity
        sa_coef = getattr(self.cfg, "soft_affinity_coef", 0.0)
        if sa_coef and node in self._soft_partners:
            aff = 0.0
            for j, w in self._soft_partners[node].items():
                if self.assignments[j] == cluster:
                    aff += w
            bonus += sa_coef * aff

        # (C1) inferred behavioral coupling: reward co-locating classes that
        # share an inferred execution flow (confidence-weighted).
        ic_coef = getattr(self.cfg, "inferred_coupling_coef", 0.0)
        if ic_coef and node in self._inferred_partners:
            flow = 0.0
            for j, c in self._inferred_partners[node].items():
                if self.assignments[j] == cluster:
                    flow += c
            bonus += ic_coef * flow

        # (F) framework-noise placed into a real (non-noise) cluster
        nc = getattr(self.cfg, "noise_coef", 0.0)
        if nc and node in self._noise_idx:
            has_normal = any(self.assignments[j] == cluster and j not in self._noise_idx
                             for j in range(len(self.assignments)))
            if has_normal:
                penalty += nc

        return bonus - penalty

    def _partitions(self) -> list[list[str]]:
        by_cluster: dict[int, list[str]] = {}
        for i, c in enumerate(self.assignments):
            if c < 0:
                continue
            by_cluster.setdefault(c, []).append(self.names[i])
        return [by_cluster[k] for k in sorted(by_cluster)]

    def _terminal_reward(self) -> dict:
        """Terminal diagnostics. `eq5` is the quantity the agent optimizes:
        raw U in raw_u mode, the z-normalized leaderboard Score in zscore mode.
        `delta` is measured against the baseline on the SAME scale."""
        partitions = self._partitions()
        m = _partition_utility(partitions, self.graph)
        if self._reward_mode == "zscore":
            rl_metrics = {"SM": m["SM"], "IFN": m["IFN"],
                          "ICP": m["ICP"], "NED": m["NED"]}
            eq5 = _weerasinghe_zscore(rl_metrics, self._peer_metrics)
            # Baseline on the same z scale = the best peer's z-Score, so Δ>0
            # means the RL partition would top the leaderboard.
            base_scores = [
                _weerasinghe_zscore(p, [q for q in self._peer_metrics if q is not p] + [rl_metrics])
                for p in self._peer_metrics
            ]
            delta = eq5 - (max(base_scores) if base_scores else 0.0)
        else:
            eq5 = m["U"]
            delta = m["U"] - self._baseline_metrics["U"]
        return {
            "eq5": float(eq5),      # kept key name for back-compat with logs
            "delta": float(delta),
            "raw": {"SM": m["SM"], "IFN": m["IFN"], "ICP": m["ICP"], "NED": m["NED"],
                    "num_ms": m["num_ms"]},
        }

    def snapshot(self) -> EnvSnapshot:
        return EnvSnapshot(
            assignments=list(self.assignments),
            cursor=self.cursor,
            step_reward=0.0,
            cumulative_shaped=self._shaped_total,
        )


# ---------------------------------------------------------------------------
# Factory: load an env for one app from disk
# ---------------------------------------------------------------------------

def load_env_for_app(
    app: str,
    *,
    facts_path: Path,
    graph_exp_json: Path,
    embeddings_pt: Path,
    config: EnvConfig | None = None,
) -> RailsDecompositionEnv:
    """Construct an env from the standard output layout.

    facts_path:       neurosymbolic/output/facts/<app>.json
    graph_exp_json:   results/<app>/exp_*_mvc.json  (or rails-aware)
    embeddings_pt:    neurosymbolic/output/phase1_rails_aware/train/embeddings/<app>.pt
    """
    import torch

    facts = _load_json(facts_path)
    exp = _load_json(graph_exp_json)
    graph = exp["dependency_graph"]
    baseline = [c["classes"] for c in exp["clusters"]]
    ckpt = torch.load(embeddings_pt, weights_only=False)
    embs = ckpt["embeddings"].cpu().numpy()
    names = list(ckpt["names"])
    return RailsDecompositionEnv(
        facts=facts,
        graph=graph,
        embeddings=embs,
        names=names,
        baseline_partitions=baseline,
        config=config,
    )
