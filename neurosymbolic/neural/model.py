"""UnixCoder embedding model with LoRA fine-tuning.

Why UnixCoder (microsoft/unixcoder-base, 125M params):
  * Encoder transformer specialized for code; outperforms CodeBERT on most
    code-understanding tasks per the original paper [Guo et al., ACL 2022].
  * Fits in 6GB VRAM for inference and is comfortable on a Colab T4 for
    LoRA fine-tuning.
  * MonoEmbed [Sellami Ch.3] reports it as the strongest pre-trained encoder
    in the 9-10 rank range — better than CodeBERT/GraphCodeBERT and only
    surpassed by 7B+ LLMs we can't afford on 3-month timeline.

Embedding strategy: mean-pool the last hidden state over real tokens (mask
applied). This matches MonoEmbed's last-token pooling alternative but mean
pooling is more stable for short Ruby class snippets where the last token
is often a closing `end`.

LoRA configuration: rank 16 on attention q/v projections — light, fast, and
sufficient for the contrastive objective per LLM2Vec / SFR-Embedding ablations.
"""

from __future__ import annotations

import torch
import torch.nn as nn
from peft import LoraConfig, TaskType, get_peft_model
from transformers import AutoModel, AutoTokenizer


DEFAULT_MODEL = "microsoft/unixcoder-base"


def load_tokenizer(model_name: str = DEFAULT_MODEL):
    return AutoTokenizer.from_pretrained(model_name)


def load_base_model(model_name: str = DEFAULT_MODEL):
    return AutoModel.from_pretrained(model_name)


def attach_lora(
    model: nn.Module,
    r: int = 16,
    alpha: int = 32,
    dropout: float = 0.05,
    target_modules: list[str] | None = None,
) -> nn.Module:
    """Wrap a HuggingFace encoder with a LoRA adapter.

    `target_modules=None` lets PEFT pick attention projections automatically
    via its built-in module-name heuristic for RoBERTa-family encoders
    (UnixCoder is RoBERTa-based).
    """
    if target_modules is None:
        target_modules = ["query", "value"]
    config = LoraConfig(
        r=r,
        lora_alpha=alpha,
        target_modules=target_modules,
        lora_dropout=dropout,
        bias="none",
        task_type=TaskType.FEATURE_EXTRACTION,
    )
    return get_peft_model(model, config)


def mean_pool(
    last_hidden: torch.Tensor, attention_mask: torch.Tensor
) -> torch.Tensor:
    """Mean of last_hidden over real tokens. Output shape: [B, hidden_dim]."""
    mask = attention_mask.unsqueeze(-1).float()
    summed = (last_hidden * mask).sum(dim=1)
    count = mask.sum(dim=1).clamp(min=1.0)
    return summed / count


class UnixCoderEmbedder(nn.Module):
    """Thin module: tokens → embedding vector. Delegates to a HF encoder.

    Used as the shared backbone for anchor/positive/negative — weights are
    tied (same module called three times), which matches the contrastive
    triplet setup in MonoEmbed.
    """

    def __init__(self, encoder: nn.Module, normalize: bool = True) -> None:
        super().__init__()
        self.encoder = encoder
        self.normalize = normalize

    def forward(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        # PEFT-wrapped models return a ModelOutput; .last_hidden_state for HF encoders.
        last_hidden = (
            out.last_hidden_state if hasattr(out, "last_hidden_state") else out[0]
        )
        emb = mean_pool(last_hidden, attention_mask)
        if self.normalize:
            emb = nn.functional.normalize(emb, p=2, dim=-1)
        return emb


def build_model(
    model_name: str = DEFAULT_MODEL,
    use_lora: bool = True,
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05,
) -> tuple[UnixCoderEmbedder, object]:
    """Construct (model, tokenizer). Model trainable params print to stderr
    so the caller can sanity-check LoRA's parameter savings."""
    import sys

    tokenizer = load_tokenizer(model_name)
    base = load_base_model(model_name)
    if use_lora:
        base = attach_lora(base, r=lora_r, alpha=lora_alpha, dropout=lora_dropout)
    embedder = UnixCoderEmbedder(base)
    trainable = sum(p.numel() for p in embedder.parameters() if p.requires_grad)
    total = sum(p.numel() for p in embedder.parameters())
    print(
        f"[model] trainable: {trainable:,} / {total:,} "
        f"({100*trainable/total:.2f}%)",
        file=sys.stderr,
    )
    return embedder, tokenizer
