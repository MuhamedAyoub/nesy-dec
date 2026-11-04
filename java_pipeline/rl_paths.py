"""Point the Rails NeSy-Dec stack at the Java artifacts, without editing it.

The Java analogue of v2_paths.py. Every driver resolves its inputs through
neurosymbolic.rl.train._default_paths and neurosymbolic.rl.eval._find_baseline,
so patching those two (and the copies other modules imported by name) is
enough. Two language-specific pieces are patched as well:

  * graph_env._build_role_vocab returns the Java stereotype vocabulary
    (java_pipeline.facts.ROLES, 16 roles) instead of the 25 Rails role
    directories, as the phase plan asks. The policy's input width follows the
    feature width, so nothing else changes.
  * _find_baseline("_mvc.json") returns the Java teacher, which is both the
    shared scoring graph and the first z-score peer, exactly as the Rails v2
    run redirected it to the v2 teacher. _find_baseline("_rails_aware.json")
    returns None: the Rails v2 run used the v1 Rails-aware partition there,
    and Java has no second resolver, so that peer is skipped (build_peer_metrics
    skips missing peers). The Java peer set is therefore teacher, UnixCoder+Ward,
    UnixCoder+HDBSCAN and random.

Call activate() before importing run_neurosym_ablation.
"""
from __future__ import annotations

import sys
from pathlib import Path

from java_pipeline.facts import ROLES
from java_pipeline.subjects import OUT

TEACHER = "exp_a0.9_b0.1_n8_java.json"
RUN = OUT / "_nesy"
EMBEDDINGS = RUN / "encoder" / "train" / "embeddings"

_ACTIVE: dict = {}


def teacher(app: str) -> Path:
    return OUT / app / TEACHER


def paths(app: str, embeddings_dir: Path | None = None) -> dict[str, Path]:
    emb = Path(embeddings_dir or _ACTIVE.get("embeddings_dir") or EMBEDDINGS)
    return {"facts": OUT / app / "facts_nesy.json", "graph_exp": teacher(app),
            "embeddings": emb / f"{app}.pt", "output": RUN / "rl" / app}


def find_baseline(app: str, suffix: str) -> Path | None:
    if suffix == "_mvc.json":
        return teacher(app)
    return None


def activate(embeddings_dir: Path | None = None) -> None:
    """Idempotent. embeddings_dir overrides the NeSy-Rep embedding bank (for
    example the pretrained UnixCoder bank in a smoke test)."""
    _ACTIVE["embeddings_dir"] = embeddings_dir
    from neurosymbolic.rl import eval as _eval
    from neurosymbolic.rl import graph_env as _env
    from neurosymbolic.rl import train as _train

    _train._default_paths = paths
    _eval._default_paths = paths
    _eval._find_baseline = find_baseline
    _env._build_role_vocab = lambda facts: {r: i for i, r in enumerate(ROLES)}
    for name in ("neurosymbolic.rl.constraint_eval", "run_neurosym_ablation"):
        mod = sys.modules.get(name)
        if mod is not None:
            if hasattr(mod, "_default_paths"):
                mod._default_paths = paths
            if hasattr(mod, "_find_baseline"):
                mod._find_baseline = find_baseline
