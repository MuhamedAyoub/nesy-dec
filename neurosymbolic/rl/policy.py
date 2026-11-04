"""GNN actor-critic for graph-RL decomposition.

Architecture
------------
1. Node encoder: MLP projects raw features to `hidden_dim`.
2. GraphSAGE-style message passing (n_layers): each layer aggregates
   neighbor means and concatenates with self, then a linear+GELU.
3. Cluster-context: for the current cursor node, build a per-cluster
   summary from already-assigned nodes (mean of their embeddings, plus a
   learned "empty cluster" vector). Concatenate the cursor node's encoding
   with each cluster's summary and pass through a scoring head.
4. Actor head: K logits, then masked softmax.
5. Critic head: scalar value from a global pooled embedding.

Why hand-rolled (no PyG)
------------------------
- Avoids a heavy dependency for what is essentially scatter_mean over a
  small graph (N ≤ 250 classes, |E| ≤ ~3k).
- Works identically on CPU smoke tests and H100.
- The aggregation is naive O(E·d) which is fine at these scales.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class PolicyConfig:
    in_dim: int        # node feature dim (set by env)
    hidden_dim: int = 128
    n_gnn_layers: int = 2
    n_clusters: int = 8
    dropout: float = 0.1
    # Wider for H100; the smoke test overrides hidden_dim/n_gnn_layers.


def _scatter_mean(values: torch.Tensor, index: torch.Tensor, dim_size: int) -> torch.Tensor:
    """Numerically stable mean aggregation over `index`.

    values: [E, d] messages
    index:  [E] target node id per message
    dim_size: number of target nodes
    Returns: [dim_size, d]
    """
    d = values.size(-1)
    out = torch.zeros(dim_size, d, device=values.device, dtype=values.dtype)
    out.index_add_(0, index, values)
    count = torch.zeros(dim_size, device=values.device, dtype=values.dtype)
    count.index_add_(0, index, torch.ones(values.size(0), device=values.device, dtype=values.dtype))
    count = count.clamp(min=1.0).unsqueeze(-1)
    return out / count


class SAGELayer(nn.Module):
    """One GraphSAGE step: h_i' = W * concat(h_i, mean(h_j for j in N(i)))."""

    def __init__(self, in_dim: int, out_dim: int) -> None:
        super().__init__()
        self.lin = nn.Linear(in_dim * 2, out_dim)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        # edge_index: [2, E]; x: [N, d]
        if edge_index.numel() == 0:
            agg = torch.zeros_like(x)
        else:
            src, tgt = edge_index[0], edge_index[1]
            msgs = x[src]
            agg = _scatter_mean(msgs, tgt, x.size(0))
        h = torch.cat([x, agg], dim=-1)
        return F.gelu(self.lin(h))


class GNNActorCritic(nn.Module):
    """Encoder + actor + critic.

    forward signature: (node_features, edge_index, cursor, assignments)
      -> (logits[K], value)

    `assignments` is a [N] long tensor with -1 for unassigned; the cluster
    summaries are built from currently assigned nodes only.
    """

    def __init__(self, cfg: PolicyConfig) -> None:
        super().__init__()
        self.cfg = cfg
        self.input_proj = nn.Sequential(
            nn.Linear(cfg.in_dim, cfg.hidden_dim),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
        )
        self.gnn = nn.ModuleList([
            SAGELayer(cfg.hidden_dim, cfg.hidden_dim)
            for _ in range(cfg.n_gnn_layers)
        ])
        # Learned representation for "empty cluster" so the agent can still
        # decide to put the current class in a brand-new bucket.
        self.empty_cluster = nn.Parameter(torch.zeros(cfg.hidden_dim))
        nn.init.normal_(self.empty_cluster, std=0.02)
        # (O1c) Per-slot identity embedding. The K cluster heads are otherwise
        # interchangeable and every EMPTY slot shares one `empty_cluster` vector,
        # so the policy cannot tell empty slot 3 from empty slot 17 — at large K
        # this collapses many services into few (BC underfit -> giant). A learned
        # per-slot bias added to each cluster summary makes the heads distinct.
        self.slot_emb = nn.Parameter(torch.zeros(cfg.n_clusters, cfg.hidden_dim))
        nn.init.normal_(self.slot_emb, std=0.02)
        # Scoring head: concat(node, cluster) -> scalar logit.
        self.score = nn.Sequential(
            nn.Linear(cfg.hidden_dim * 2, cfg.hidden_dim),
            nn.GELU(),
            nn.Dropout(cfg.dropout),
            nn.Linear(cfg.hidden_dim, 1),
        )
        # Critic: from global mean pool.
        self.value = nn.Sequential(
            nn.Linear(cfg.hidden_dim, cfg.hidden_dim),
            nn.GELU(),
            nn.Linear(cfg.hidden_dim, 1),
        )

    def encode(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        h = self.input_proj(x)
        for layer in self.gnn:
            h = h + layer(h, edge_index)  # residual
        return h

    def cluster_summaries(
        self, node_emb: torch.Tensor, assignments: torch.Tensor, K: int
    ) -> torch.Tensor:
        """[K, hidden] — mean of assigned node embeddings per cluster, with
        `empty_cluster` substituted for clusters that have no members yet."""
        d = node_emb.size(-1)
        sums = torch.zeros(K, d, device=node_emb.device, dtype=node_emb.dtype)
        counts = torch.zeros(K, device=node_emb.device, dtype=node_emb.dtype)
        mask = assignments >= 0
        if mask.any():
            sums.index_add_(0, assignments[mask], node_emb[mask])
            counts.index_add_(
                0, assignments[mask],
                torch.ones(int(mask.sum().item()), device=node_emb.device, dtype=node_emb.dtype),
            )
        means = sums / counts.clamp(min=1.0).unsqueeze(-1)
        empty = counts == 0
        if empty.any():
            means[empty] = self.empty_cluster
        return means

    def forward(
        self,
        node_features: torch.Tensor,    # [N, in_dim]
        edge_index: torch.Tensor,       # [2, E]
        cursor: int,
        assignments: torch.Tensor,      # [N], long, -1 for unassigned
        action_mask: torch.Tensor | None = None,  # [K] bool
    ) -> tuple[torch.Tensor, torch.Tensor]:
        h = self.encode(node_features, edge_index)                # [N, d]
        cluster_h = self.cluster_summaries(h, assignments, self.cfg.n_clusters)  # [K, d]
        cluster_h = cluster_h + self.slot_emb                                    # (O1c) per-slot identity
        node_h = h[cursor].unsqueeze(0).expand(self.cfg.n_clusters, -1)          # [K, d]
        pair = torch.cat([node_h, cluster_h], dim=-1)                            # [K, 2d]
        logits = self.score(pair).squeeze(-1)                                    # [K]
        if action_mask is not None:
            # All-False mask -> all -inf -> NaN softmax; fall back to all-legal.
            if not bool(action_mask.any()):
                action_mask = torch.ones_like(action_mask)
            logits = logits.masked_fill(~action_mask, float("-inf"))
        # Critic over the whole graph.
        v = self.value(h.mean(dim=0))                                            # [1]
        return logits, v.squeeze(-1)

    # ------------------------------------------------------------------
    # Batched path — used by the GPU-shaped rollout and PPO update.
    # ------------------------------------------------------------------

    def batched_cluster_summaries(
        self, node_emb: torch.Tensor, assignments: torch.Tensor, K: int
    ) -> torch.Tensor:
        """Vectorized over a batch of partition states.

        node_emb:    [N, d]   — same encoded graph for every sample.
        assignments: [B, N]   — long, -1 for unassigned.
        returns:     [B, K, d]
        """
        B, N = assignments.shape
        d = node_emb.size(-1)
        device = node_emb.device
        dtype = node_emb.dtype
        # Flatten (b, n) -> a single bucket index b*K + a, with -1's redirected
        # to a throwaway bucket at the end so we can use one scatter_add.
        sink = B * K
        a = assignments.clone()
        a[a < 0] = -1  # safety
        flat_buckets = torch.where(
            a >= 0,
            torch.arange(B, device=device).unsqueeze(1) * K + a,
            torch.full_like(a, sink),
        ).reshape(-1)                                              # [B*N]
        # Broadcast node_emb across batch: shape [B*N, d].
        node_emb_b = node_emb.unsqueeze(0).expand(B, -1, -1).reshape(B * N, d)
        sums = torch.zeros(B * K + 1, d, device=device, dtype=dtype)
        sums.index_add_(0, flat_buckets, node_emb_b)
        counts = torch.zeros(B * K + 1, device=device, dtype=dtype)
        counts.index_add_(0, flat_buckets,
                          torch.ones(B * N, device=device, dtype=dtype))
        sums = sums[:-1].reshape(B, K, d)
        counts = counts[:-1].reshape(B, K)
        means = sums / counts.clamp(min=1.0).unsqueeze(-1)
        empty = counts == 0                                        # [B, K]
        if empty.any():
            means = torch.where(
                empty.unsqueeze(-1),
                self.empty_cluster.view(1, 1, -1).expand_as(means),
                means,
            )
        return means

    def forward_batched(
        self,
        node_emb: torch.Tensor,         # [N, d]  ENCODED graph (cached)
        cursor: torch.Tensor,           # [B] long
        assignments: torch.Tensor,      # [B, N] long, -1 unassigned
        action_mask: torch.Tensor,      # [B, K] bool
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Run actor+critic over a batch of partition states sharing the same
        encoded graph. ONE forward pass, B samples — this is the GPU-friendly
        path used by both vectorized rollout and PPO update.
        """
        B = cursor.shape[0]
        K = self.cfg.n_clusters
        d = node_emb.size(-1)
        cluster_h = self.batched_cluster_summaries(node_emb, assignments, K)  # [B,K,d]
        cluster_h = cluster_h + self.slot_emb.unsqueeze(0)                    # (O1c) per-slot identity
        node_h = node_emb[cursor]                                              # [B, d]
        node_h_k = node_h.unsqueeze(1).expand(B, K, d)                         # [B,K,d]
        pair = torch.cat([node_h_k, cluster_h], dim=-1)                        # [B,K,2d]
        logits = self.score(pair).squeeze(-1)                                  # [B, K]
        # Guard: a row whose mask is ALL-False would become all -inf -> softmax
        # NaN and Categorical() raises. Happens at large K when cannot_link
        # forbids every head for some buffered state (astuto K=10 never hits it;
        # feedbin/chatwoot K=25+ do). Re-allow all heads for any dead row, the
        # same fallback env.legal_actions() applies at decode time.
        safe_mask = action_mask.clone()
        dead = ~safe_mask.any(dim=-1)                                          # [B]
        if dead.any():
            safe_mask[dead] = True
        logits = logits.masked_fill(~safe_mask, float("-inf"))
        # Critic: graph-mean is shared across the batch (same encoded graph).
        v = self.value(node_emb.mean(dim=0, keepdim=True)).squeeze(-1)         # [1]
        v = v.expand(B)                                                        # [B]
        return logits, v
