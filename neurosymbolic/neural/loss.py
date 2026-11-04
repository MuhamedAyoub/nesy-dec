"""Constraint-aware contrastive loss for Paper 2.

Total loss:

    L = L_triplet  +  λ_ml · L_must_link  +  λ_cl · L_cannot_link

where L_triplet is the standard triplet margin loss, and the two extra
terms apply embedding-space constraints derived from the symbolic facts
that survive *within the current batch* (we don't materialize the full
fact set every step — that would be O(N²) memory).

This is the neuro-symbolic glue: the symbolic layer's hard rules act as
an inductive bias on the embedding space, even when those exact pairs
weren't sampled into the contrastive triplets. Concretely:

  * For every (a, b) in the batch where the symbolic must_link rule fires,
    we add a penalty proportional to ‖e_a − e_b‖ — pulling them closer.
  * For every (a, b) in the batch where the symbolic cannot_link rule fires,
    we add a penalty proportional to max(0, margin − ‖e_a − e_b‖) — pushing
    them apart up to a margin.

Crucially, these losses are computed over *all* embeddings in the batch
(anchors ∪ positives ∪ negatives), not just the (a, p, n) triple. That
multiplies the supervision signal per step roughly by 3 without extra
forward passes.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F


@dataclass
class LossConfig:
    triplet_margin: float = 0.3
    constraint_margin: float = 0.5  # cannot-link target distance
    lambda_must_link: float = 0.3
    lambda_cannot_link: float = 0.3


def _build_pair_mask(
    names: list[str], pair_set: set[tuple[str, str]]
) -> torch.Tensor:
    """Return a [B, B] bool tensor where [i, j] = True iff (names[i], names[j])
    appears in pair_set (in either order). Diagonal forced to False.
    """
    n = len(names)
    name_to_idx: dict[str, list[int]] = {}
    for i, nm in enumerate(names):
        name_to_idx.setdefault(nm, []).append(i)
    mask = torch.zeros((n, n), dtype=torch.bool)
    for a, b in pair_set:
        if a not in name_to_idx or b not in name_to_idx:
            continue
        for i in name_to_idx[a]:
            for j in name_to_idx[b]:
                if i != j:
                    mask[i, j] = True
                    mask[j, i] = True
    return mask


def constraint_loss(
    embeddings: torch.Tensor,
    names: list[str],
    must_link: set[tuple[str, str]],
    cannot_link: set[tuple[str, str]],
    config: LossConfig,
) -> tuple[torch.Tensor, dict[str, float]]:
    """Embedding-space penalties for must-link / cannot-link facts active in
    the current batch's class-name set.

    embeddings: [B, D] L2-normalized. Cosine distance = 1 − cos = 0.5·‖a−b‖²
    when both unit-norm, so we use ‖·‖ directly.
    """
    device = embeddings.device
    must_mask = _build_pair_mask(names, must_link).to(device)
    cant_mask = _build_pair_mask(names, cannot_link).to(device)

    # Pairwise Euclidean distances (B×B). Embeddings are unit-norm, so
    # distance ∈ [0, 2].
    dists = torch.cdist(embeddings, embeddings, p=2)

    # Symmetric masks → take upper triangle to avoid double-counting.
    triu = torch.triu(torch.ones_like(dists, dtype=torch.bool), diagonal=1)
    must_mask = must_mask & triu
    cant_mask = cant_mask & triu

    # Must-link: minimize distance (pull together).
    must_count = must_mask.sum().clamp(min=1)
    must_loss = (dists * must_mask.float()).sum() / must_count

    # Cannot-link: hinge — push apart up to constraint_margin.
    hinge = torch.clamp(config.constraint_margin - dists, min=0.0)
    cant_count = cant_mask.sum().clamp(min=1)
    cant_loss = (hinge * cant_mask.float()).sum() / cant_count

    stats = {
        "must_pairs_in_batch": int(must_mask.sum().item()),
        "cant_pairs_in_batch": int(cant_mask.sum().item()),
        "must_loss": float(must_loss.item()),
        "cant_loss": float(cant_loss.item()),
    }
    total = config.lambda_must_link * must_loss + config.lambda_cannot_link * cant_loss
    return total, stats


def triplet_loss(
    anchor: torch.Tensor,
    positive: torch.Tensor,
    negative: torch.Tensor,
    margin: float,
) -> torch.Tensor:
    """Standard triplet margin loss with Euclidean distance over normalized
    embeddings. max(0, ‖a−p‖ − ‖a−n‖ + margin)."""
    pos_d = (anchor - positive).norm(p=2, dim=1)
    neg_d = (anchor - negative).norm(p=2, dim=1)
    return F.relu(pos_d - neg_d + margin).mean()


class ConstraintAwareTripletLoss(nn.Module):
    """The full Paper-2 loss: triplet + must-link + cannot-link."""

    def __init__(self, config: LossConfig | None = None) -> None:
        super().__init__()
        self.config = config or LossConfig()

    def forward(
        self,
        anchor_emb: torch.Tensor,
        positive_emb: torch.Tensor,
        negative_emb: torch.Tensor,
        anchor_names: list[str],
        positive_names: list[str],
        negative_names: list[str],
        must_link: set[tuple[str, str]],
        cannot_link: set[tuple[str, str]],
    ) -> tuple[torch.Tensor, dict[str, float]]:
        triplet = triplet_loss(
            anchor_emb, positive_emb, negative_emb, self.config.triplet_margin
        )
        all_emb = torch.cat([anchor_emb, positive_emb, negative_emb], dim=0)
        all_names = anchor_names + positive_names + negative_names
        constraint, c_stats = constraint_loss(
            all_emb, all_names, must_link, cannot_link, self.config
        )
        total = triplet + constraint
        stats = {
            "triplet_loss": float(triplet.item()),
            "constraint_loss_weighted": float(constraint.item()),
            "total_loss": float(total.item()),
            **c_stats,
        }
        return total, stats


def facts_to_pair_sets(
    facts_payload: dict,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Convert the SymbolicFacts JSON to the canonical pair sets the loss uses.

    Cannot-link is expanded from namespace representatives to the full
    cross-product (the loss applies only to pairs present in the current
    batch, so total memory remains bounded).
    """
    must = {tuple(sorted([a, b])) for a, b, *_ in facts_payload.get("must_link", [])}

    cant: set[tuple[str, str]] = set()
    by_ns: dict[str, list[str]] = {}
    for cls, ns in facts_payload.get("namespaces", {}).items():
        if ns:
            by_ns.setdefault(ns, []).append(cls)
    ns_keys = sorted(by_ns)
    for i, ns_a in enumerate(ns_keys):
        for ns_b in ns_keys[i + 1:]:
            for a in by_ns[ns_a]:
                for b in by_ns[ns_b]:
                    cant.add(tuple(sorted([a, b])))
    # Also include direct (non-namespace) cannot_link facts.
    for a, b, reason in facts_payload.get("cannot_link", []):
        if not str(reason).startswith("ns_pair:"):
            cant.add(tuple(sorted([a, b])))

    return must, cant
