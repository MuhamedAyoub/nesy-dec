"""PPO trainer for Phase 3 graph-RL decomposition (GPU-shaped).

This rewrite turns the trainer into a properly GPU-utilising loop:

  * **Cached graph encoding.** The GraphSAGE encoder is run ONCE per PPO
    update — the graph (`node_features`, `edge_index`) is static across an
    episode. We then reuse the [N, d] embedding table for every per-state
    actor/critic call. Was: re-encoded ~80× per episode.
  * **Batched PPO update.** All rollout transitions are stacked into a
    single (B, N) assignments tensor + (B,) cursor + (B, K) mask, fed
    through one `forward_batched()` call per epoch. Was: a Python `for i`
    loop with one forward + one backward PER transition.
  * **Vectorized rollout.** `--num-envs M` parallel envs are stepped
    together; their per-step states are stacked into one (M, N) batch and
    the policy is called once per env-step instead of M times. Env logic
    itself stays in Python (it's cheap), but the GPU dispatch is collapsed.
  * **Device-resident static tensors.** `node_features` and `edge_index`
    are uploaded to the device once at train start and reused.

CLI
---
    # RTX 3060 (6 GB) — good defaults for an 80–250-node graph
    python -m neurosymbolic.rl.train --app astuto-main \\
        --device cuda --num-envs 8 --episodes 2000

    # CPU smoke test
    python -m neurosymbolic.rl.train --app astuto-main --device cpu \\
        --num-envs 4 --episodes 50

Outputs (under <output_dir>/<app>[/run_name]/):
  - policy.pt        — checkpointed GNNActorCritic state dict
  - policy_best.pt   — best mean-ΔU checkpoint seen during training
  - train_log.json   — per-episode metrics (reward, eq5, raw, entropy, loss)
"""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from .graph_env import EnvConfig, RailsDecompositionEnv, load_env_for_app
from .policy import GNNActorCritic, PolicyConfig


REPO = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# PPO hyperparameters
# ---------------------------------------------------------------------------

@dataclass
class PPOConfig:
    episodes: int = 2000
    num_envs: int = 8                 # parallel envs per rollout
    update_epochs: int = 4
    minibatch_size: int = 256         # over flattened (M*T) transitions
    gamma: float = 0.99
    gae_lambda: float = 0.95
    clip_eps: float = 0.2
    value_coef: float = 0.5
    entropy_coef: float = 0.01
    lr: float = 3e-4
    max_grad_norm: float = 0.5
    seed: int = 42
    log_every: int = 10
    checkpoint_every: int = 200
    # --- anti-drift knobs (keep PPO from undoing a behavior-cloned warm start) -
    # Save policy_best.pt on best GREEDY-DECODED leaderboard Score instead of
    # mean training-episode delta. Robust to early kills and to the giant trap
    # (a collapsed decode scores low, so it never becomes "best").
    select_by_decode: bool = False
    # KL penalty pulling the live policy toward the frozen BC reference. >0 lets
    # PPO refine locally but blocks drift back to the giant. (RLHF-style anchor.)
    kl_coef: float = 0.0
    # Freeze the GraphSAGE encoder during PPO; only the cluster head + critic
    # adapt. The BC-learned representations stay in the rails basin.
    freeze_encoder: bool = False


# ---------------------------------------------------------------------------
# Vectorized rollout
# ---------------------------------------------------------------------------

class VectorRollout:
    """Holds M parallel envs and the (M, T, ...) trajectory tensors.

    Episodes have IDENTICAL length T = N (one step per class). We allocate
    flat (M*T) buffers and PPO consumes them as a single batch.
    """

    def __init__(self, envs: list[RailsDecompositionEnv], N: int, K: int) -> None:
        self.envs = envs
        self.M = len(envs)
        self.T = N
        self.K = K
        # Per-step buffers (host side, copied to device once per update).
        self.assignments = np.full((self.M, self.T, N), -1, dtype=np.int64)
        self.cursor = np.zeros((self.M, self.T), dtype=np.int64)
        self.mask = np.zeros((self.M, self.T, K), dtype=bool)
        self.action = np.zeros((self.M, self.T), dtype=np.int64)
        self.logp = np.zeros((self.M, self.T), dtype=np.float32)
        self.value = np.zeros((self.M, self.T), dtype=np.float32)
        self.reward = np.zeros((self.M, self.T), dtype=np.float32)
        self.done = np.zeros((self.M, self.T), dtype=bool)


def collect_rollout(
    rollout: VectorRollout,
    policy: GNNActorCritic,
    node_emb: torch.Tensor,   # [N, d] — cached encoded graph (no grad)
    device: torch.device,
) -> list[dict]:
    """Step every env in lockstep for T = N steps; record transitions.

    One batched policy forward per timestep across all M envs.
    """
    M, T, K = rollout.M, rollout.T, rollout.K
    N = node_emb.size(0)
    for env in rollout.envs:
        env.reset()

    # Pre-allocated device-side per-step buffers (reused across T steps).
    cur_assign = torch.full((M, N), -1, dtype=torch.long, device=device)
    cur_cursor = torch.zeros(M, dtype=torch.long, device=device)
    cur_mask = torch.zeros(M, K, dtype=torch.bool, device=device)
    # Scratch numpy buffers for host->device copies.
    host_assign = np.full((M, N), -1, dtype=np.int64)
    host_mask = np.zeros((M, K), dtype=bool)
    host_cursor = np.zeros(M, dtype=np.int64)

    # logp/value never feed the Python env step, so we keep them ON-DEVICE in
    # (T, M) buffers and copy to host ONCE after the loop. This removes 2 of the
    # 3 per-timestep GPU->CPU syncs (each sync stalls the pipeline; at high
    # num_envs they dominated the rollout). Only `action` must round-trip per
    # step because env.step() needs a Python int.
    dev_logp = torch.empty((T, M), device=device)
    dev_value = torch.empty((T, M), device=device)

    infos: list[dict] = []
    for t in range(T):
        # Stage per-env state into host buffers, then one bulk copy.
        for ei, env in enumerate(rollout.envs):
            host_assign[ei, :] = env.assignments  # list[int] of length N
            host_cursor[ei] = env.current_node
            host_mask[ei, :] = env.legal_actions()
        cur_assign.copy_(torch.from_numpy(host_assign))
        cur_cursor.copy_(torch.from_numpy(host_cursor))
        cur_mask.copy_(torch.from_numpy(host_mask))

        with torch.no_grad():
            logits, value = policy.forward_batched(
                node_emb, cur_cursor, cur_assign, cur_mask,
            )                                                  # [M, K], [M]
            dist = Categorical(logits=logits)
            action = dist.sample()                             # [M]
            dev_logp[t] = dist.log_prob(action)
            dev_value[t] = value

        actions_np = action.cpu().numpy()                      # the only per-step sync

        # Save state BEFORE stepping (we want s_t, not s_{t+1}).
        rollout.assignments[:, t, :] = host_assign
        rollout.cursor[:, t] = host_cursor
        rollout.mask[:, t, :] = host_mask
        rollout.action[:, t] = actions_np

        # Step every env (Python loop — env is cheap).
        for ei, env in enumerate(rollout.envs):
            r, d, info = env.step(int(actions_np[ei]))
            rollout.reward[ei, t] = r
            rollout.done[ei, t] = d
            if d:
                infos.append(info)

    # One bulk transfer of logp/value for the whole rollout: (T, M) -> (M, T).
    rollout.logp[:, :] = dev_logp.t().cpu().numpy()
    rollout.value[:, :] = dev_value.t().cpu().numpy()
    return infos


def compute_gae(
    rollout: VectorRollout,
    gamma: float,
    lam: float,
) -> tuple[np.ndarray, np.ndarray]:
    """GAE on each parallel trajectory. Returns (advantages, returns) of
    shape (M, T)."""
    M, T = rollout.M, rollout.T
    advs = np.zeros((M, T), dtype=np.float32)
    last_gae = np.zeros(M, dtype=np.float32)
    next_value = np.zeros(M, dtype=np.float32)  # terminal V = 0
    for t in reversed(range(T)):
        # `done[t]` is True at the final step => future value zero, no bootstrap.
        not_done = 1.0 - rollout.done[:, t].astype(np.float32)
        delta = rollout.reward[:, t] + gamma * next_value * not_done - rollout.value[:, t]
        last_gae = delta + gamma * lam * not_done * last_gae
        advs[:, t] = last_gae
        next_value = rollout.value[:, t]
    returns = advs + rollout.value
    return advs, returns


# ---------------------------------------------------------------------------
# Batched PPO update — one forward+backward per minibatch over (M*T) samples
# ---------------------------------------------------------------------------

def ppo_update_batched(
    policy: GNNActorCritic,
    optimizer: torch.optim.Optimizer,
    rollout: VectorRollout,
    advantages: np.ndarray,
    returns: np.ndarray,
    node_feat_dev: torch.Tensor,
    edge_index_dev: torch.Tensor,
    cfg: PPOConfig,
    device: torch.device,
    kl_ref: GNNActorCritic | None = None,
) -> dict:
    """One PPO update. Re-encodes the graph WITH grad, then runs B-sized
    forward/backward over minibatches drawn from the (M*T) flat buffer.

    If `kl_ref` is given and cfg.kl_coef>0, adds a KL(live || ref) penalty per
    minibatch so the policy refines locally without drifting back to the giant.
    """
    M, T = rollout.M, rollout.T
    B = M * T
    # Flatten everything into (B, ...).
    assigns_flat = torch.from_numpy(rollout.assignments.reshape(B, -1)).to(device)
    cursor_flat = torch.from_numpy(rollout.cursor.reshape(B)).to(device)
    mask_flat = torch.from_numpy(rollout.mask.reshape(B, rollout.K)).to(device)
    action_flat = torch.from_numpy(rollout.action.reshape(B)).to(device)
    old_logp = torch.from_numpy(rollout.logp.reshape(B)).to(device)
    advs = torch.from_numpy(advantages.reshape(B)).to(device)
    rets = torch.from_numpy(returns.reshape(B)).to(device)
    # Per-batch normalization is standard.
    advs = (advs - advs.mean()) / (advs.std() + 1e-8)

    stats = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "n_updates": 0}

    for _ in range(cfg.update_epochs):
        perm = torch.randperm(B, device=device)
        for start in range(0, B, cfg.minibatch_size):
            idx = perm[start : start + cfg.minibatch_size]
            # Re-encode the graph with grad ONCE per minibatch.
            # (Encoding is O(E·d) ≈ trivial; encoder weights need gradients.)
            node_emb = policy.encode(node_feat_dev, edge_index_dev)   # [N, d]
            logits, value = policy.forward_batched(
                node_emb,
                cursor_flat[idx],
                assigns_flat[idx],
                mask_flat[idx],
            )                                                          # [b,K], [b]
            dist = Categorical(logits=logits)
            new_logp = dist.log_prob(action_flat[idx])
            ratio = torch.exp(new_logp - old_logp[idx])
            adv = advs[idx]
            ret = rets[idx]
            s1 = ratio * adv
            s2 = torch.clamp(ratio, 1 - cfg.clip_eps, 1 + cfg.clip_eps) * adv
            p_loss = -torch.min(s1, s2).mean()
            v_loss = F.mse_loss(value, ret)
            entropy = dist.entropy().mean()
            loss = p_loss + cfg.value_coef * v_loss - cfg.entropy_coef * entropy

            if kl_ref is not None and cfg.kl_coef > 0.0:
                with torch.no_grad():
                    ref_emb = kl_ref.encode(node_feat_dev, edge_index_dev)
                    ref_logits, _ = kl_ref.forward_batched(
                        ref_emb, cursor_flat[idx], assigns_flat[idx], mask_flat[idx])
                # KL(live || ref) over legal heads only. Masked positions have
                # -inf logits; p*(logp-logq) there = 0*(-inf - -inf) = 0*nan, and
                # crucially torch.where does NOT stop the NaN gradient flowing
                # back through the un-selected branch. So we must keep every
                # value fed into the multiply FINITE: substitute 0 for the -inf
                # log-probs BEFORE the arithmetic (legal positions are unchanged
                # since they're already finite).
                logp = torch.log_softmax(logits, dim=-1)         # [b,K]
                logq = torch.log_softmax(ref_logits, dim=-1)     # [b,K]
                legal = torch.isfinite(logp) & torch.isfinite(logq)
                logp_safe = torch.where(legal, logp, torch.zeros_like(logp))
                logq_safe = torch.where(legal, logq, torch.zeros_like(logq))
                p = torch.where(legal, logp.exp(), torch.zeros_like(logp))
                kl = (p * (logp_safe - logq_safe)).sum(dim=-1).mean()
                loss = loss + cfg.kl_coef * kl

            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.parameters(), cfg.max_grad_norm)
            optimizer.step()

            n = idx.numel()
            stats["policy_loss"] += float(p_loss.item()) * n
            stats["value_loss"] += float(v_loss.item()) * n
            stats["entropy"] += float(entropy.item()) * n
            stats["n_updates"] += n

    nu = max(1, stats["n_updates"])
    return {
        "policy_loss": stats["policy_loss"] / nu,
        "value_loss": stats["value_loss"] / nu,
        "entropy": stats["entropy"] / nu,
    }


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def _clone_env(template: RailsDecompositionEnv, seed_offset: int) -> RailsDecompositionEnv:
    """Make an extra env that shares heavy artifacts (graph, embeddings,
    role_vocab, edge_index) with `template` but has its own mutable state.

    Cloning by re-running the constructor would re-load the embeddings and
    recompute the role_vocab; here we shallow-copy then reset.
    """
    import copy as _copy
    twin = _copy.copy(template)
    # Mutable state must not be aliased.
    twin.assignments = list(template.assignments)
    twin.cursor = 0
    twin._shaped_total = 0.0
    twin.rng = np.random.default_rng(template.cfg.seed + seed_offset)
    # Re-run reset to allocate a fresh _IncrementalUtility.
    twin.reset()
    return twin


def _greedy_decode_score(env: RailsDecompositionEnv, policy: GNNActorCritic,
                         device: torch.device) -> tuple[float, list[int], float]:
    """Greedy-decode the current policy and return (Score, sizes, raw U).

    Score is the same z-normalized Eq.5 the evaluator reports, computed against
    the env's fixed peer set when in zscore mode, else the raw composite. Used
    for best-checkpoint selection so a collapsed decode can never win.

    raw U is ALWAYS the raw absolute composite (3SM - IFN/K - ICP - NED)/6,
    regardless of reward mode: the paper reports raw U, so the training log
    must carry it alongside the (mode-dependent) selection Score.
    """
    from .decompose import greedy_decompose
    from vendor.ror_msi.evaluate import (compute_sm as _sm, compute_ifn as _ifn,
                          compute_icp as _icp, compute_ned as _ned,
                          compute_composite_score as _comp)
    from .graph_env import _weerasinghe_zscore
    parts = greedy_decompose(env, policy, device)
    m = {"SM": _sm(parts, env.graph), "IFN": _ifn(parts, env.graph),
         "ICP": _icp(parts, env.graph), "NED": _ned(parts)}
    raw_u = _comp(m["SM"], m["IFN"], m["ICP"], m["NED"], len(parts))
    if getattr(env, "_reward_mode", "raw_u") == "zscore" and env._peer_metrics:
        score = _weerasinghe_zscore(m, env._peer_metrics)
    else:
        score = raw_u
    return float(score), sorted((len(p) for p in parts), reverse=True), float(raw_u)


def train(
    env: RailsDecompositionEnv,
    cfg: PPOConfig,
    output_dir: Path,
    device: torch.device,
    hidden_dim: int = 128,
    n_gnn_layers: int = 2,
    warm_policy: GNNActorCritic | None = None,
    bc_reference: GNNActorCritic | None = None,
) -> dict:
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)

    if warm_policy is not None:
        # Continue from a behavior-cloned policy (its PolicyConfig already
        # matches env.K because BC was run on this env).
        policy = warm_policy.to(device)
        policy_cfg = policy.cfg
    else:
        policy_cfg = PolicyConfig(
            in_dim=env.node_features.shape[1],
            hidden_dim=hidden_dim,
            n_gnn_layers=n_gnn_layers,
            n_clusters=env.action_dim,   # +1 head for the outlier action if on
        )
        policy = GNNActorCritic(policy_cfg).to(device)

    # Anti-drift: optionally freeze the encoder so PPO can't move the
    # BC-learned node representations out of the rails basin.
    if cfg.freeze_encoder:
        for p in policy.input_proj.parameters():
            p.requires_grad = False
        for p in policy.gnn.parameters():
            p.requires_grad = False
        print("[train] encoder FROZEN — only cluster head + critic adapt")

    # Anti-drift: a frozen copy of the BC policy to KL-anchor against.
    kl_ref = None
    if cfg.kl_coef > 0.0 and bc_reference is not None:
        import copy as _copy
        kl_ref = _copy.deepcopy(bc_reference).to(device)
        for p in kl_ref.parameters():
            p.requires_grad = False
        kl_ref.eval()
        print(f"[train] KL-anchored to BC policy (kl_coef={cfg.kl_coef})")

    trainable = [p for p in policy.parameters() if p.requires_grad]
    optim = torch.optim.AdamW(trainable, lr=cfg.lr)

    # Static graph tensors live on the device for the whole run.
    node_feat_dev = torch.from_numpy(env.node_features).to(device)
    edge_index_dev = torch.from_numpy(env.edge_index).to(device)

    # Build M parallel envs (shallow-clone shared artifacts to save RAM).
    envs = [env] + [_clone_env(env, seed_offset=i + 1)
                    for i in range(cfg.num_envs - 1)]
    N = len(env.names)
    K = env.action_dim   # K clusters (+1 outlier slot if allow_outliers)
    rollout = VectorRollout(envs, N=N, K=K)

    log: list[dict] = []
    best_delta = -float("inf")
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "train_log.json"
    ckpt_path = output_dir / "policy.pt"
    best_path = output_dir / "policy_best.pt"

    # Episode-0 decode of the (warm-started or fresh) policy BEFORE any PPO
    # update, so the training curve has its warm-start anchor: the paper's
    # "PPO improves over BC" claim is read directly off train_log.json.
    if cfg.select_by_decode:
        dec_score0, dec_sizes0, dec_raw0 = _greedy_decode_score(env, policy, device)
        log.append({
            "episode": 0,
            "stage": "warmstart" if warm_policy is not None else "init",
            "decode_score": round(dec_score0, 4),
            "decode_raw_u": round(dec_raw0, 4),
            "decode_sizes": dec_sizes0,
        })
        log_path.write_text(json.dumps(log, indent=2))
        print(f"[ep     0] decode Score={dec_score0:+.4f}  rawU={dec_raw0:+.4f}  "
              f"max|m|={max(dec_sizes0) if dec_sizes0 else 0}")

        # Seed best-checkpoint selection with the WARM-START policy itself, so
        # the behaviour-cloned teacher is a floor PPO has to beat rather than a
        # starting point it can only drift away from. Without this, best_delta
        # begins at -inf and the first PPO update always overwrites the BC
        # policy even when it decodes strictly worse -- on a strong teacher
        # (the v2 clustering) that made PPO degrade 6 of 8 applications.
        best_delta = dec_score0
        torch.save({"policy": policy.state_dict(),
                    "config": asdict(policy_cfg),
                    "episode": 0,
                    "env_meta": {"allow_outliers": bool(getattr(env.cfg, "allow_outliers", False)),
                                 "n_real_clusters": env.K},
                    "decode_score": dec_score0,
                    "decode_raw_u": dec_raw0,
                    "decode_sizes": dec_sizes0}, best_path)

    start = time.time()
    episode = 0
    while episode < cfg.episodes:
        # ----- ROLLOUT: encode graph once (no grad), collect M*T transitions
        with torch.no_grad():
            node_emb_nograd = policy.encode(node_feat_dev, edge_index_dev)
        infos = collect_rollout(rollout, policy, node_emb_nograd, device)
        episode += cfg.num_envs
        # ----- UPDATE
        advs, rets = compute_gae(rollout, cfg.gamma, cfg.gae_lambda)
        upd = ppo_update_batched(
            policy, optim, rollout, advs, rets,
            node_feat_dev, edge_index_dev, cfg, device, kl_ref=kl_ref,
        )
        # ----- LOG
        ep_rewards = rollout.reward.sum(axis=1)   # [M]
        mean_r = float(ep_rewards.mean())
        with np.errstate(invalid="ignore"):
            import warnings as _w
            with _w.catch_warnings():
                _w.simplefilter("ignore", category=RuntimeWarning)
                mean_delta = float(np.nanmean([i.get("delta_eq5", float("nan")) for i in infos]))
                mean_eq5 = float(np.nanmean([i.get("terminal_eq5", float("nan")) for i in infos]))
        entry = {
            "episode": episode,
            "mean_reward": mean_r,
            "mean_delta_eq5": mean_delta,
            "mean_terminal_eq5": mean_eq5,
            "baseline_eq5": env._baseline_eq5,
            **upd,
            "elapsed_sec": round(time.time() - start, 1),
        }
        log.append(entry)
        if (episode // max(1, cfg.num_envs)) % max(1, cfg.log_every // max(1, cfg.num_envs)) == 0 \
                or episode >= cfg.episodes:
            print(
                f"[ep {episode:5d}] R={mean_r:+.3f}  "
                f"Δeq5={mean_delta:+.3f}  eq5={mean_eq5:+.3f}  "
                f"H={upd['entropy']:.2f}  pl={upd['policy_loss']:+.3f}  "
                f"vl={upd['value_loss']:.3f}  "
                f"t={entry['elapsed_sec']:.1f}s"
            )
        # Env decode metadata baked into every checkpoint so eval can rebuild a
        # matching env (e.g. allow_outliers -> policy has K+1 heads but only K
        # real clusters). Without this, decode would treat the outlier head as a
        # real cluster and garble the partition.
        env_meta = {"allow_outliers": bool(getattr(env.cfg, "allow_outliers", False)),
                    "n_real_clusters": env.K}
        if cfg.select_by_decode:
            # Best = best GREEDY-DECODED leaderboard Score (collapse can't win).
            dec_score, dec_sizes, dec_raw = _greedy_decode_score(env, policy, device)
            entry["decode_score"] = round(dec_score, 4)
            entry["decode_raw_u"] = round(dec_raw, 4)
            entry["decode_sizes"] = dec_sizes
            if dec_score > best_delta:
                best_delta = dec_score
                torch.save({"policy": policy.state_dict(),
                            "config": asdict(policy_cfg),
                            "episode": episode, "env_meta": env_meta,
                            "decode_score": dec_score,
                            "decode_raw_u": dec_raw,
                            "decode_sizes": dec_sizes}, best_path)
        elif not math.isnan(mean_delta) and mean_delta > best_delta:
            best_delta = mean_delta
            torch.save({"policy": policy.state_dict(),
                        "config": asdict(policy_cfg),
                        "episode": episode, "env_meta": env_meta,
                        "delta": mean_delta}, best_path)
        if episode % cfg.checkpoint_every < cfg.num_envs:
            torch.save({"policy": policy.state_dict(),
                        "config": asdict(policy_cfg),
                        "episode": episode, "env_meta": env_meta}, ckpt_path)
            log_path.write_text(json.dumps(log, indent=2))
    env_meta = {"allow_outliers": bool(getattr(env.cfg, "allow_outliers", False)),
                "n_real_clusters": env.K}
    torch.save({"policy": policy.state_dict(),
                "config": asdict(policy_cfg),
                "episode": episode, "env_meta": env_meta}, ckpt_path)
    log_path.write_text(json.dumps(log, indent=2))
    return {"best_delta": best_delta, "final_log": log[-1] if log else {}}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

# The default Phase-2 constraint-aware variant (gentle must-link, strong
# cannot-link). Used only as a fallback when no data-driven selection exists.
_PHASE2_BEST_VARIANT = "phase1_ml0.0_cl0.3"

# Where the λ-sweep analyzer (experiments.analyze) records the winning variant.
_SELECTION_FILE = (REPO / "neurosymbolic" / "output" / "phase2_lambda"
                   / "selected_best.json")


def _selected_embeddings_path(app: str) -> Path | None:
    """If the λ-sweep analyzer recorded a data-driven winner, resolve its
    embedding for this app. Returns None if no selection file / no .pt yet."""
    if not _SELECTION_FILE.exists():
        return None
    try:
        sel = json.loads(_SELECTION_FILE.read_text())
    except (OSError, ValueError):
        return None
    train_dir = sel.get("train_dir")
    if not train_dir:
        return None
    pt = Path(train_dir) / "embeddings" / f"{app}.pt"
    return pt if pt.exists() else None


def _embeddings_path(app: str) -> Path:
    # 1. Data-driven winner from the sweep (experiments.analyze → selected_best.json).
    selected = _selected_embeddings_path(app)
    if selected is not None:
        return selected
    # 2. Hard-coded default Phase-2 variant, if its embeddings exist.
    phase2 = (REPO / "neurosymbolic" / "output" / "phase2_lambda"
              / _PHASE2_BEST_VARIANT / "train" / "embeddings" / f"{app}.pt")
    if phase2.exists():
        return phase2
    # 3. Plain Phase-1 rails-aware fine-tune so the pipeline still runs end-to-end.
    return (REPO / "neurosymbolic" / "output" / "phase1_rails_aware"
            / "train" / "embeddings" / f"{app}.pt")


def _default_paths(app: str) -> dict[str, Path]:
    return {
        "facts": REPO / "neurosymbolic" / "output" / "facts" / f"{app}.json",
        "graph_exp": REPO / "results" / app / "exp_a0.5_b0.5_n8_mvc.json",
        "embeddings": _embeddings_path(app),
        "output": REPO / "neurosymbolic" / "output" / "phase3_rl" / app,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PPO trainer for Phase 3 graph-RL (GPU-shaped)")
    parser.add_argument("--app", required=True, help="app name (e.g. astuto-main)")
    parser.add_argument("--episodes", type=int, default=2000)
    parser.add_argument("--num-envs", type=int, default=8,
                        help="parallel envs per rollout (8 fits a 6GB RTX 3060)")
    parser.add_argument("--update-epochs", type=int, default=4)
    parser.add_argument("--minibatch-size", type=int, default=256)
    parser.add_argument("--hidden-dim", type=int, default=128,
                        help="GNN hidden width. 128 fits RTX 3060 6GB easily")
    parser.add_argument("--gnn-layers", type=int, default=2)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--lambda-must-link", type=float, default=0.1)
    parser.add_argument("--lambda-cannot-link", type=float, default=0.1)
    parser.add_argument("--dense-reward-coef", type=float, default=1.0,
                        help="multiplier on the potential-based shaping reward "
                             "(0 = terminal-only U)")
    parser.add_argument("--oversize-penalty", type=float, default=0.02,
                        help="per-step penalty for placing into a cluster already "
                             "at/above the NED max_size (20)")
    parser.add_argument("--k-policy", choices=["ned_target", "baseline"],
                        default="ned_target",
                        help="how to pick K when --n-clusters is unset")
    parser.add_argument("--reward-mode", choices=["zscore", "raw_u", "multiplicative"],
                        default="zscore",
                        help="zscore = potential-shape toward the EXACT "
                             "z-normalized Eq.5 leaderboard Score vs the 4 peer "
                             "methods (what eval.py grades on; default). "
                             "raw_u = legacy raw Weerasinghe U (collapses to one "
                             "giant cluster because its NED term is capped at -1/6)")
    parser.add_argument("--log-every", type=int, default=10)
    parser.add_argument("--warmstart-rails", type=str, default=None,
                        help="path to a rails_aware exp_*.json to imitation-learn "
                             "BEFORE PPO. Lands the policy in the teacher's "
                             "high-SM basin so PPO doesn't collapse to one giant. "
                             "Use 'auto' to pick results/<app>/exp_a0.9_b0.1_n8_rails_aware.json")
    parser.add_argument("--warmstart-epochs", type=int, default=300,
                        help="behavior-cloning epochs before PPO (0 disables)")
    parser.add_argument("--warmstart-lr", type=float, default=1e-3)
    # Anti-drift options (combine freely; see rl/README for the ablation).
    parser.add_argument("--select-by-decode", action="store_true",
                        help="save policy_best.pt on best GREEDY-DECODED Score "
                             "(robust to drift/early-kill; collapse can't win)")
    parser.add_argument("--kl-coef", type=float, default=0.0,
                        help="KL anchor to the BC policy during PPO (e.g. 0.1). "
                             "0 disables. Requires --warmstart-rails.")
    parser.add_argument("--freeze-encoder", action="store_true",
                        help="freeze the GraphSAGE encoder during PPO; only the "
                             "cluster head + critic adapt")
    parser.add_argument("--balance-coef", type=float, default=0.0,
                        help="balance regularizer in the reward potential: "
                             "subtract coef*oversize_frac so the giant-cluster "
                             "trap becomes non-competitive. ~0.3 works on astuto "
                             "(critical≈0.095); leaves balanced partitions intact")
    # HyDec-inspired enhancements (independently ablatable).
    parser.add_argument("--semantic-coef", type=float, default=0.0,
                        help="(B) weight on intra-cluster UnixCoder cosine cohesion "
                             "added to the reward — the neuro-symbolic semantic "
                             "signal. ~0.5-1.0 to start; 0 = structural-only (old)")
    parser.add_argument("--allow-outliers", action="store_true",
                        help="(A) add a (K+1)-th action that leaves a class "
                             "unassigned; unassigned classes are excluded from "
                             "metrics (like HyDec min_samples outliers)")
    parser.add_argument("--normalize-calls", action="store_true",
                        help="(C) HyDec-normalize call weights (by target incoming "
                             "total, symmetric) before metrics. Changes scoring; "
                             "ablate separately")
    parser.add_argument("--soft-affinity-coef", type=float, default=0.0,
                        help="(E) weight on the symbolic soft_affinity signal: "
                             "+coef*Σweight per already-placed affinity partner "
                             "sharing the cluster. ~0.1-0.3 to start")
    parser.add_argument("--noise-coef", type=float, default=0.0,
                        help="(F) framework_noise prior: reward outlier-ing a "
                             "boilerplate base class (with --allow-outliers), else "
                             "penalize co-clustering it with real classes")
    parser.add_argument("--affinity-from-embeddings", action="store_true",
                        help="(C2) learn soft-affinity pair weights from UnixCoder "
                             "cosine instead of the hand-set constants")
    parser.add_argument("--inferred-coupling-coef", type=float, default=0.0,
                        help="(C1) weight on LLM-inferred behavioral-coupling facts "
                             "(run neurosymbolic.infer_coupling first to emit them)")
    parser.add_argument("--size-cap-factor", type=float, default=0.0,
                        help="(O2b) hard size cap = ceil(factor*N/K); a cluster at "
                             "the cap becomes an illegal action -> giant impossible. "
                             "1.5 recommended; 0 disables. Floored at NED max (20).")
    parser.add_argument("--n-clusters", type=int, default=None)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--facts-path", type=str, default=None)
    parser.add_argument("--graph-exp", type=str, default=None)
    parser.add_argument("--embeddings", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--run-name", type=str, default=None)
    parser.add_argument("--force-overwrite", action="store_true")
    parser.add_argument("--device", type=str, default="cuda" if torch.cuda.is_available() else "cpu")
    args = parser.parse_args()

    defaults = _default_paths(args.app)
    facts_path = Path(args.facts_path) if args.facts_path else defaults["facts"]
    graph_exp = Path(args.graph_exp) if args.graph_exp else defaults["graph_exp"]
    embeddings = Path(args.embeddings) if args.embeddings else defaults["embeddings"]
    output_dir = Path(args.output_dir) if args.output_dir else defaults["output"]
    if args.run_name:
        output_dir = output_dir / args.run_name

    if output_dir.exists() and any(output_dir.iterdir()) and not args.force_overwrite:
        raise SystemExit(
            f"[train] output_dir already has files: {output_dir}\n"
            f"        pass --run-name <something> to write to a subfolder, or\n"
            f"        --force-overwrite to deliberately replace the existing run."
        )

    print(f"[train] facts:      {facts_path}")
    print(f"[train] graph_exp:  {graph_exp}")
    print(f"[train] embeddings: {embeddings}")
    print(f"[train] output:     {output_dir}")
    print(f"[train] device:     {args.device}  num_envs={args.num_envs}")

    peer_metrics = None
    if args.reward_mode in ("zscore", "multiplicative"):
        # Build the SAME peer set eval.py grades against so the training
        # objective IS the leaderboard number. Imported lazily to avoid a
        # module-load import cycle (eval imports train._default_paths).
        from .eval import build_peer_metrics
        peer_metrics = build_peer_metrics(args.app)
        print(f"[train] zscore reward vs {len(peer_metrics)} fixed peers")

    # Resolve warm-start teacher and pin K to its cluster count so the policy's
    # cluster heads line up with the teacher during behavior cloning.
    teacher_parts = None
    n_clusters = args.n_clusters
    if args.warmstart_rails and args.warmstart_epochs > 0:
        from .warmstart import load_teacher_partition
        if args.warmstart_rails == "auto":
            rails_path = REPO / "results" / args.app / "exp_a0.9_b0.1_n8_rails_aware.json"
        else:
            rails_path = Path(args.warmstart_rails)
        if not rails_path.exists():
            raise SystemExit(f"[train] warmstart rails file not found: {rails_path}")
        teacher_parts = load_teacher_partition(rails_path)
        n_clusters = max(2, len(teacher_parts))
        print(f"[train] warm-start teacher: {rails_path.name} "
              f"({len(teacher_parts)} clusters -> K={n_clusters})")

    env_cfg = EnvConfig(
        n_clusters=n_clusters,
        k_policy=args.k_policy,
        lambda_must_link=args.lambda_must_link,
        lambda_cannot_link=args.lambda_cannot_link,
        dense_reward_coef=args.dense_reward_coef,
        oversize_penalty=args.oversize_penalty,
        gamma=0.99,
        seed=args.seed,
        reward_mode=args.reward_mode,
        peer_metrics=peer_metrics,
        balance_coef=args.balance_coef,
        semantic_coef=args.semantic_coef,
        allow_outliers=args.allow_outliers,
        normalize_calls=args.normalize_calls,
        soft_affinity_coef=args.soft_affinity_coef,
        affinity_from_embeddings=args.affinity_from_embeddings,
        inferred_coupling_coef=args.inferred_coupling_coef,
        noise_coef=args.noise_coef,
        size_cap_factor=args.size_cap_factor,
    )
    env = load_env_for_app(
        args.app,
        facts_path=facts_path,
        graph_exp_json=graph_exp,
        embeddings_pt=embeddings,
        config=env_cfg,
    )
    print(f"[train] N={len(env.names)}  E={env.edge_index.shape[1]}  K={env.K}  "
          f"must_link={len(env.must_link)}  cannot_link={len(env.cannot_link)}")
    print(f"[train] baseline eq5 (vs random) = {env._baseline_eq5:+.3f}")

    ppo_cfg = PPOConfig(
        episodes=args.episodes,
        num_envs=args.num_envs,
        update_epochs=args.update_epochs,
        minibatch_size=args.minibatch_size,
        lr=args.lr,
        seed=args.seed,
        log_every=args.log_every,
        select_by_decode=args.select_by_decode,
        kl_coef=args.kl_coef,
        freeze_encoder=args.freeze_encoder,
    )
    device = torch.device(args.device)

    # ----- Behavior-cloning warm-start (optional) --------------------------
    warm_policy = None
    if teacher_parts is not None:
        from .warmstart import behavior_clone, build_bc_targets
        warm_cfg = PolicyConfig(
            in_dim=env.node_features.shape[1],
            hidden_dim=args.hidden_dim,
            n_gnn_layers=args.gnn_layers,
            n_clusters=env.action_dim,   # match the policy's action heads
        )
        warm_policy = GNNActorCritic(warm_cfg).to(device)
        targets = build_bc_targets(env, teacher_parts)
        print(f"[train] behavior cloning {args.warmstart_epochs} epochs "
              f"(teacher heads used: {len(set(targets.tolist()))}/{env.K})")
        behavior_clone(
            env, warm_policy, targets, device,
            epochs=args.warmstart_epochs, lr=args.warmstart_lr,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        torch.save({"policy": warm_policy.state_dict(),
                    "config": asdict(warm_cfg)},
                   output_dir / "policy_bc.pt")
        print(f"[train] saved BC checkpoint -> {output_dir / 'policy_bc.pt'}")

    res = train(
        env, ppo_cfg, output_dir, device,
        hidden_dim=args.hidden_dim, n_gnn_layers=args.gnn_layers,
        warm_policy=warm_policy, bc_reference=warm_policy,
    )
    print(f"[train] best (decode Score or Δ) = {res['best_delta']:+.3f}")


if __name__ == "__main__":
    main()
