"""Triplet dataset that joins triplets.json with code_index.json.

A triplet (anchor, positive, negative) maps to three code strings; this
module produces tokenized batches ready for UnixCoder. The design keeps the
class-name index in sync with the code-index by filtering at construction
time, so __getitem__ never has to handle missing keys.

We also keep `symbolic_facts.json` accessible from the dataset, so the loss
function (loss.py) can pull the must-link / cannot-link sets directly without
re-parsing files. That avoids loading the same JSON in two places at runtime.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from torch.utils.data import Dataset


@dataclass
class TripletExample:
    anchor_code: str
    positive_code: str
    negative_code: str
    anchor_name: str
    positive_name: str
    negative_name: str
    pos_source: str
    neg_source: str


class TripletDataset(Dataset):
    """In-memory triplet dataset for one Rails app.

    The whole code index for one app is small (≤ ~1MB even for Chatwoot), so
    we keep it resident. Tokenization happens in the collator, not here, so
    different tokenizers (UnixCoder, CodeBERT, ...) can reuse the same dataset.
    """

    def __init__(
        self,
        triplets_path: str | Path,
        code_index_path: str | Path,
        facts_path: str | Path | None = None,
    ) -> None:
        self.triplets_path = Path(triplets_path)
        self.code_index_path = Path(code_index_path)
        self.facts_path = Path(facts_path) if facts_path else None

        triplets_raw: list[dict[str, str]] = json.loads(self.triplets_path.read_text())
        self.code_index: dict[str, dict[str, Any]] = json.loads(
            self.code_index_path.read_text()
        )
        # Drop any triplet whose endpoints aren't all indexed (the code_reader
        # ensures coverage but Industrial-X-style incomplete dumps still need this).
        self.examples: list[TripletExample] = []
        for t in triplets_raw:
            try:
                a, p, n = t["anchor"], t["positive"], t["negative"]
                self.examples.append(
                    TripletExample(
                        anchor_code=self.code_index[a]["code"],
                        positive_code=self.code_index[p]["code"],
                        negative_code=self.code_index[n]["code"],
                        anchor_name=a,
                        positive_name=p,
                        negative_name=n,
                        pos_source=t.get("pos_source", ""),
                        neg_source=t.get("neg_source", ""),
                    )
                )
            except KeyError:
                continue

        self._facts: dict[str, Any] | None = None  # lazy

    @property
    def facts(self) -> dict[str, Any]:
        if self._facts is None:
            if self.facts_path is None or not self.facts_path.exists():
                self._facts = {"must_link": [], "cannot_link": [], "namespaces": {}}
            else:
                self._facts = json.loads(self.facts_path.read_text())
        return self._facts

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> TripletExample:
        return self.examples[idx]


def collate_triplets(
    examples: list[TripletExample], tokenizer: Any, max_length: int = 512
) -> dict[str, Any]:
    """Tokenizer collator. Returns three batches (anchor/positive/negative)
    each with input_ids and attention_mask, plus the raw class names so the
    loss can look up symbolic constraints."""
    anchors = [ex.anchor_code for ex in examples]
    positives = [ex.positive_code for ex in examples]
    negatives = [ex.negative_code for ex in examples]

    enc = lambda texts: tokenizer(  # noqa: E731
        texts,
        max_length=max_length,
        padding=True,
        truncation=True,
        return_tensors="pt",
    )

    a_batch = enc(anchors)
    p_batch = enc(positives)
    n_batch = enc(negatives)

    return {
        "anchor": a_batch,
        "positive": p_batch,
        "negative": n_batch,
        "anchor_names": [ex.anchor_name for ex in examples],
        "positive_names": [ex.positive_name for ex in examples],
        "negative_names": [ex.negative_name for ex in examples],
        "pos_sources": [ex.pos_source for ex in examples],
        "neg_sources": [ex.neg_source for ex in examples],
    }


def make_loader(
    dataset: TripletDataset,
    tokenizer: Any,
    batch_size: int = 16,
    max_length: int = 512,
    shuffle: bool = True,
    seed: int = 42,
) -> torch.utils.data.DataLoader:
    """Build a DataLoader bound to a tokenizer. Determinism via `seed`."""
    g = torch.Generator()
    g.manual_seed(seed)
    return torch.utils.data.DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        generator=g,
        collate_fn=lambda batch: collate_triplets(batch, tokenizer, max_length),
    )
