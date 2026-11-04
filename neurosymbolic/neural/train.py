"""Training loop for Paper 2.

Two-phase training, mirroring MonoEmbed's transfer-learning rationale:

  Phase A — Cross-language pretraining (optional). If `--java-triplets`
            is provided, train on a mixed Java + Ruby corpus first so the
            model learns "architectural similarity" before fine-tuning on
            Ruby specifics. For this artifact's scope, we run
            Ruby-only by default.

  Phase B — Ruby fine-tuning. Per-app and joint variants supported.

Defaults are sized for Colab T4 (16GB) and validated to run on CPU for
smoke tests (slow but functional).

Outputs:
  - LoRA adapter weights → out_dir/adapter
  - Per-class embedding matrix → out_dir/embeddings/<app>.pt
  - Training log → out_dir/train_log.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path

import numpy as np
import torch
from torch.optim import AdamW

from neurosymbolic.neural.dataset import TripletDataset, make_loader
from neurosymbolic.neural.loss import (
    ConstraintAwareTripletLoss,
    LossConfig,
    facts_to_pair_sets,
)
from neurosymbolic.neural.model import build_model


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _device() -> torch.device:
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _join_pair_sets(a, b):
    return a | b


def train(
    apps: list[str],
    triplets_dir: Path,
    code_index_dir: Path,
    facts_dir: Path,
    out_dir: Path,
    *,
    epochs: int = 3,
    batch_size: int = 16,
    lr: float = 5e-5,
    max_length: int = 512,
    use_lora: bool = True,
    use_constraint_loss: bool = True,
    loss_config: "LossConfig | None" = None,
    save_per_epoch_embeddings: bool = False,
    smoke: bool = False,
    seed: int = 42,
) -> dict:
    """Run training over the union of `apps`. Returns the final log dict."""
    _set_seed(seed)
    device = _device()
    out_dir.mkdir(parents=True, exist_ok=True)

    # ----- Build model -----
    model_name = "microsoft/unixcoder-base"
    model, tokenizer = build_model(model_name=model_name, use_lora=use_lora)
    model.to(device)

    # ----- Build datasets -----
    datasets: list[TripletDataset] = []
    must_link_global: set[tuple[str, str]] = set()
    cannot_link_global: set[tuple[str, str]] = set()
    for app in apps:
        ds = TripletDataset(
            triplets_path=triplets_dir / f"{app}.json",
            code_index_path=code_index_dir / f"{app}.json",
            facts_path=facts_dir / f"{app}.json",
        )
        if len(ds) == 0:
            print(f"[skip] {app}: empty dataset", file=sys.stderr)
            continue
        ml, cl = facts_to_pair_sets(ds.facts)
        # Namespace-prefix the pair sets with the app name so cross-app
        # collisions on common class names (User, Comment) don't leak.
        ml = {(f"{app}::{a}", f"{app}::{b}") for a, b in ml}
        cl = {(f"{app}::{a}", f"{app}::{b}") for a, b in cl}
        must_link_global |= ml
        cannot_link_global |= cl
        # And tag the dataset's example names with the app prefix so the
        # per-batch lookup hits the right facts.
        for ex in ds.examples:
            ex.anchor_name = f"{app}::{ex.anchor_name}"
            ex.positive_name = f"{app}::{ex.positive_name}"
            ex.negative_name = f"{app}::{ex.negative_name}"
        datasets.append(ds)

    if not datasets:
        raise RuntimeError("no training data loaded")

    # Joint loader: concat all app datasets so each step mixes apps.
    full = torch.utils.data.ConcatDataset(datasets)
    loader = torch.utils.data.DataLoader(
        full,
        batch_size=batch_size,
        shuffle=True,
        generator=torch.Generator().manual_seed(seed),
        collate_fn=lambda batch: _collate_with_tokenizer(batch, tokenizer, max_length),
    )

    if smoke:
        # Limit to a handful of steps for local CPU sanity check.
        loader_iter = list(loader)[:3]
    else:
        loader_iter = None  # use the full loader

    # ----- Loss + optimizer -----
    loss_fn = ConstraintAwareTripletLoss(loss_config or LossConfig())
    optim = AdamW(
        [p for p in model.parameters() if p.requires_grad], lr=lr, weight_decay=0.01
    )

    lc = loss_config or LossConfig()
    log: dict = {
        "config": {
            "apps": apps,
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": lr,
            "use_lora": use_lora,
            "use_constraint_loss": use_constraint_loss,
            "loss_config": {
                "triplet_margin": lc.triplet_margin,
                "constraint_margin": lc.constraint_margin,
                "lambda_must_link": lc.lambda_must_link,
                "lambda_cannot_link": lc.lambda_cannot_link,
            },
            "smoke": smoke,
        },
        "steps": [],
        "epoch_summaries": [],
    }

    # ----- Train -----
    for epoch in range(1, epochs + 1):
        epoch_t0 = time.time()
        model.train()
        losses: list[float] = []
        triplet_losses: list[float] = []
        constraint_losses: list[float] = []

        iterator = loader_iter if loader_iter is not None else loader
        for step, batch in enumerate(iterator):
            optim.zero_grad()
            a_emb = model(
                batch["anchor"]["input_ids"].to(device),
                batch["anchor"]["attention_mask"].to(device),
            )
            p_emb = model(
                batch["positive"]["input_ids"].to(device),
                batch["positive"]["attention_mask"].to(device),
            )
            n_emb = model(
                batch["negative"]["input_ids"].to(device),
                batch["negative"]["attention_mask"].to(device),
            )

            ml_use = must_link_global if use_constraint_loss else set()
            cl_use = cannot_link_global if use_constraint_loss else set()

            total, stats = loss_fn(
                a_emb,
                p_emb,
                n_emb,
                batch["anchor_names"],
                batch["positive_names"],
                batch["negative_names"],
                ml_use,
                cl_use,
            )
            total.backward()
            optim.step()

            losses.append(stats["total_loss"])
            triplet_losses.append(stats["triplet_loss"])
            constraint_losses.append(stats["constraint_loss_weighted"])
            log["steps"].append({"epoch": epoch, "step": step, **stats})
            if step % 10 == 0 or smoke:
                print(
                    f"[ep{epoch} step{step}] total={stats['total_loss']:.4f} "
                    f"triplet={stats['triplet_loss']:.4f} "
                    f"constraint={stats['constraint_loss_weighted']:.4f} "
                    f"(ml_in_batch={stats['must_pairs_in_batch']} "
                    f"cl_in_batch={stats['cant_pairs_in_batch']})",
                    file=sys.stderr,
                )

        epoch_summary = {
            "epoch": epoch,
            "avg_loss": float(np.mean(losses)) if losses else float("nan"),
            "avg_triplet_loss": float(np.mean(triplet_losses)) if triplet_losses else float("nan"),
            "avg_constraint_loss": float(np.mean(constraint_losses)) if constraint_losses else float("nan"),
            "wall_seconds": time.time() - epoch_t0,
        }
        log["epoch_summaries"].append(epoch_summary)
        print(f"[epoch {epoch} done] {epoch_summary}", file=sys.stderr)

        if save_per_epoch_embeddings:
            ck_dir = out_dir / "embeddings_per_epoch" / f"epoch_{epoch}"
            ck_dir.mkdir(parents=True, exist_ok=True)
            _extract_embeddings(
                model, tokenizer, apps, datasets, ck_dir,
                batch_size=batch_size, max_length=max_length, device=device,
            )

    # ----- Persist -----
    log_path = out_dir / "train_log.json"
    log_path.write_text(json.dumps(log, indent=2))
    if use_lora:
        adapter_path = out_dir / "adapter"
        adapter_path.mkdir(exist_ok=True)
        # PEFT models expose .save_pretrained on the wrapped encoder.
        model.encoder.save_pretrained(adapter_path)
        tokenizer.save_pretrained(adapter_path)
        print(f"[saved] adapter → {adapter_path}", file=sys.stderr)

    # ----- Per-app embedding extraction (final) -----
    embeds_dir = out_dir / "embeddings"
    embeds_dir.mkdir(exist_ok=True)
    _extract_embeddings(
        model, tokenizer, apps, datasets, embeds_dir,
        batch_size=batch_size, max_length=max_length, device=device,
    )

    return log


def _extract_embeddings(model, tokenizer, apps, datasets, out_dir, *, batch_size, max_length, device):
    """Encode all classes in each app's code_index and dump per-app .pt files."""
    model.eval()
    with torch.no_grad():
        for app, ds in zip(apps, datasets):
            class_names = sorted(ds.code_index.keys())
            embs = []
            for i in range(0, len(class_names), batch_size):
                chunk = class_names[i : i + batch_size]
                texts = [ds.code_index[n]["code"] for n in chunk]
                enc = tokenizer(
                    texts, max_length=max_length, padding=True,
                    truncation=True, return_tensors="pt",
                ).to(device)
                emb = model(enc["input_ids"], enc["attention_mask"]).cpu()
                embs.append(emb)
            all_embs = torch.cat(embs, dim=0)
            # Atomic write: save to a temp file then os.replace, so an interrupted
            # or racing run can never leave a truncated .pt that silently poisons
            # the RL (same corruption class that hit the facts files).
            import os as _os, tempfile as _tf
            final_pt = out_dir / f"{app}.pt"
            final_pt.parent.mkdir(parents=True, exist_ok=True)
            _fd, _tmp = _tf.mkstemp(dir=str(final_pt.parent), suffix=".pt.tmp")
            _os.close(_fd)
            try:
                torch.save({"names": class_names, "embeddings": all_embs}, _tmp)
                _os.replace(_tmp, final_pt)  # atomic
            finally:
                if _os.path.exists(_tmp):
                    _os.remove(_tmp)
            print(
                f"[saved] embeddings ({len(class_names)} classes) → "
                f"{final_pt}",
                file=sys.stderr,
            )
    model.train()


def _collate_with_tokenizer(batch, tokenizer, max_length):
    """Module-level collator (avoids lambda capture issues with workers)."""
    from neurosymbolic.neural.dataset import collate_triplets
    return collate_triplets(batch, tokenizer, max_length)


def main() -> None:
    p = argparse.ArgumentParser(description="Train constraint-aware UnixCoder")
    p.add_argument("--apps", nargs="+", required=True)
    p.add_argument("--triplets-dir", default="neurosymbolic/output/triplets")
    p.add_argument("--code-index-dir", default="neurosymbolic/output/code_index")
    p.add_argument("--facts-dir", default="neurosymbolic/output/facts")
    p.add_argument("--out-dir", default="neurosymbolic/output/train")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch-size", type=int, default=16)
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--max-length", type=int, default=512)
    p.add_argument("--no-lora", action="store_true")
    p.add_argument("--no-constraint-loss", action="store_true",
                   help="ablation: disable must-link/cannot-link regularizer")
    p.add_argument("--triplet-margin", type=float, default=0.3,
                   help="margin for the base contrastive triplet loss")
    p.add_argument("--constraint-margin", type=float, default=0.5,
                   help="margin used inside the must/cannot-link regularizer")
    p.add_argument("--lambda-must-link", type=float, default=0.3,
                   help="weight of the must-link constraint term")
    p.add_argument("--lambda-cannot-link", type=float, default=0.3,
                   help="weight of the cannot-link constraint term")
    p.add_argument("--smoke", action="store_true",
                   help="3-step CPU smoke test, no real training")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    loss_config = LossConfig(
        triplet_margin=args.triplet_margin,
        constraint_margin=args.constraint_margin,
        lambda_must_link=(
            args.lambda_must_link if not args.no_constraint_loss else 0.0
        ),
        lambda_cannot_link=(
            args.lambda_cannot_link if not args.no_constraint_loss else 0.0
        ),
    )

    train(
        apps=args.apps,
        triplets_dir=Path(args.triplets_dir),
        code_index_dir=Path(args.code_index_dir),
        facts_dir=Path(args.facts_dir),
        out_dir=Path(args.out_dir),
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        max_length=args.max_length,
        use_lora=not args.no_lora,
        use_constraint_loss=not args.no_constraint_loss,
        loss_config=loss_config,
        smoke=args.smoke,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
