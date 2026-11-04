"""Behavior-cloning warm-start from a teacher partition (rails_aware_hc).

Why
---
The Eq.5 objective is NOT degenerate (a balanced, high-SM decomposition like
rails_aware_hc genuinely scores best), but the single-giant-cluster solution is
a WIDE local trap: greedily internalizing edges always lowers ICP/IFN locally,
while high SM needs foresight. From a cold start, PPO falls into the giant.

Fix: imitation-learn the teacher partition first (supervised cross-entropy on
the per-node cluster choice), landing the policy in the teacher's high-SM basin,
THEN let PPO refine. From there the giant is a strictly worse solution.

Cluster-id alignment
--------------------
The policy's K cluster heads are interchangeable (no fixed identity), so we must
pin each teacher cluster to a head id consistently. We assign head ids by FIRST
APPEARANCE in the env's node order: the first node placed defines head 0, the
next node from a new teacher cluster defines head 1, etc. This makes the target
action sequence self-consistent with the env's legal-action masking and with how
`cluster_summaries` accumulates assigned nodes.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from .graph_env import RailsDecompositionEnv
from .policy import GNNActorCritic


def load_teacher_partition(rails_exp_json: Path) -> list[list[str]]:
    """Read a rails_aware exp_*.json -> list of class-name lists."""
    d = json.loads(Path(rails_exp_json).read_text())
    return [c["classes"] for c in d["clusters"]]


def build_bc_targets(
    env: RailsDecompositionEnv,
    teacher_partitions: list[list[str]],
) -> np.ndarray:
    """Return target_action[node_idx] (env index space), with teacher clusters
    mapped onto head ids by first-appearance in env._order.

    Nodes whose class isn't in the teacher partition (shouldn't happen once the
    env trims to graph-active classes, but be defensive) are assigned to the
    head of the most-recently-seen teacher cluster, or head 0 at the start.
    """
    # class name -> teacher cluster index
    name_to_tcluster: dict[str, int] = {}
    for ti, members in enumerate(teacher_partitions):
        for m in members:
            name_to_tcluster[m] = ti

    teacher_to_head: dict[int, int] = {}
    next_head = 0
    target = np.zeros(len(env.names), dtype=np.int64)
    last_head = 0
    for node in env._order:  # placement order the env will actually follow
        name = env.names[node]
        tcl = name_to_tcluster.get(name)
        if tcl is None:
            head = last_head
        else:
            if tcl not in teacher_to_head:
                if next_head < env.K:
                    teacher_to_head[tcl] = next_head
                    next_head += 1
                else:
                    # More teacher clusters than heads: fold extras into head 0.
                    teacher_to_head[tcl] = 0
            head = teacher_to_head[tcl]
        target[node] = head
        last_head = head
    return target


def behavior_clone(
    env: RailsDecompositionEnv,
    policy: GNNActorCritic,
    target_action: np.ndarray,
    device: torch.device,
    *,
    epochs: int = 200,
    lr: float = 1e-3,
    log_every: int = 20,
) -> dict:
    """Teacher-force the target action sequence and minimize masked CE.

    One episode = one full pass over env._order. We re-encode the (static) graph
    once per epoch and run a single batched forward over all N placement states,
    so this is cheap. Returns a small training summary.
    """
    node_feat = torch.from_numpy(env.node_features).to(device)
    edge_index = torch.from_numpy(env.edge_index).to(device)
    targets = torch.from_numpy(target_action).to(device)
    optimizer = torch.optim.AdamW(policy.parameters(), lr=lr)

    N = len(env.names)
    K = env.action_dim   # policy action heads (K clusters + outlier slot if on)
    last = {}
    for epoch in range(epochs):
        # Build the (N, N) assignment-state matrix that the env WOULD present:
        # state at step t has the first t nodes (in _order) assigned to their
        # TARGET head, the rest -1. This is teacher forcing.
        assigns = np.full((N, N), -1, dtype=np.int64)
        cursors = np.zeros(N, dtype=np.int64)
        masks = np.zeros((N, K), dtype=bool)
        # The EFFECTIVE target per step: the teacher head if it's legal under
        # cannot_link masking, else the same legal fallback the env applies.
        # Using the raw teacher head when it's masked would make its logit -inf
        # and the cross-entropy +inf (NaN weights). This bit feedbin/chatwoot,
        # which have cannot_link constraints rails sometimes violates.
        eff_targets = np.zeros(N, dtype=np.int64)
        env.reset()
        for t in range(N):
            node = env.current_node
            assigns[t, :] = env.assignments       # state BEFORE placing node
            cursors[t] = node
            legal = env.legal_actions()
            masks[t, :] = legal
            a = int(target_action[node])
            if a >= len(legal) or not legal[a]:
                a = int(np.argmax(legal))         # nearest legal fallback
            eff_targets[t] = a                    # supervise on the LEGAL head
            env.step(a)

        a_t = torch.from_numpy(assigns).to(device)
        c_t = torch.from_numpy(cursors).to(device)
        m_t = torch.from_numpy(masks).to(device)
        node_emb = policy.encode(node_feat, edge_index)
        logits, _ = policy.forward_batched(node_emb, c_t, a_t, m_t)  # [N, K]
        # Supervise on the per-step EFFECTIVE (always-legal) target head, so the
        # CE target's logit is never the -inf of a masked position.
        step_targets = torch.from_numpy(eff_targets).to(device)      # [N]
        # (O1a) CLASS-BALANCED CE. Plain CE lets the largest teacher clusters
        # dominate the gradient, so at large N the policy collapses many small
        # services into a few big ones (BC underfit -> giant). Weight each
        # sample by 1/sqrt(freq of its target head) so small clusters are not
        # drowned out. (sqrt softens it — full 1/freq over-weights singletons.)
        counts = np.bincount(eff_targets, minlength=K).astype(np.float64)
        w = 1.0 / np.sqrt(np.clip(counts, 1.0, None))
        w = w / w.mean()                                    # keep loss scale ~same
        cls_w = torch.from_numpy(w).to(device=device, dtype=logits.dtype)  # [K]
        loss = F.cross_entropy(logits, step_targets, weight=cls_w)
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 1.0)
        optimizer.step()

        if epoch % log_every == 0 or epoch == epochs - 1:
            with torch.no_grad():
                pred = logits.argmax(dim=-1)
                acc = float((pred == step_targets).float().mean().item())
                # size-distance to teacher: how close are PREDICTED cluster sizes
                # to the target sizes? (the real BC-fidelity signal, vs node match)
                tgt_sizes = np.bincount(eff_targets, minlength=K)
                pred_sizes = np.bincount(pred.cpu().numpy(), minlength=K)
                size_l1 = int(np.abs(np.sort(tgt_sizes) - np.sort(pred_sizes)).sum())
            last = {"epoch": epoch, "loss": float(loss.item()),
                    "acc": acc, "size_l1": size_l1}
            print(f"[bc {epoch:4d}] loss={loss.item():.4f}  match={acc:.3f}  "
                  f"size_L1_to_teacher={size_l1}")
    return last
