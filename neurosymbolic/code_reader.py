"""Class-name → source-code lookup for the neural analysis layer.

The triplet generator emits class names. UnixCoder consumes tokens. This
module bridges them: given a Rails app input directory, build an index
mapping each class name to a normalized code string suitable for
tokenization (≤ ~480 chars of context, framework boilerplate stripped,
oversized files truncated to the most informative regions).

Design choices:
  * **Class-level granularity** matches MonoEmbed [Sellami Ch.3] and the
    triplet generator. We do not split methods into separate samples.
  * **Truncation strategy**: keep the class declaration line + the first
    ~30 non-trivial lines of body. Rails classes follow a consistent
    "associations / validations / callbacks / public methods" ordering, so
    the head of the file carries most of the domain signal.
  * **Boilerplate stripping**: drop pure-comment header blocks, drop
    blank-line runs, normalize whitespace. UnixCoder has 512 tokens; we
    aim for ≤ ~400 to leave room for special tokens.
  * **Multiple classes per file**: rare in well-formed Rails apps, but
    possible. We emit the first non-trivial class and ignore the rest;
    the triplet generator references classes by file-stem-derived names
    anyway.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from neurosymbolic.symbolic.rules import (
    CLASS_DEF_RE,
    MODULE_DEF_RE,
    _singular_to_class,
)


_BLANK_RE = re.compile(r"^\s*$")
_PURE_COMMENT_RE = re.compile(r"^\s*#")
_MAX_BODY_LINES = 30
_MAX_CHARS = 1800  # rough proxy for ≤ ~400 UnixCoder tokens


@dataclass
class ClassCode:
    name: str
    path: str
    code: str  # normalized snippet ready for tokenization
    raw_lines: int  # original LOC, for stats


def _strip_leading_comments(lines: list[str]) -> list[str]:
    """Drop the leading shebang/comment header but preserve inline comments
    inside the class body — those often hold domain hints (`# A user can ...`)."""
    i = 0
    while i < len(lines) and (
        _BLANK_RE.match(lines[i]) or _PURE_COMMENT_RE.match(lines[i])
    ):
        i += 1
    return lines[i:]


def _compress_blank_runs(lines: list[str]) -> list[str]:
    """Collapse runs of ≥2 blank lines into a single blank line."""
    out: list[str] = []
    prev_blank = False
    for ln in lines:
        if _BLANK_RE.match(ln):
            if prev_blank:
                continue
            prev_blank = True
            out.append("")
        else:
            prev_blank = False
            out.append(ln.rstrip())
    return out


def _truncate_to_window(lines: list[str], max_lines: int, max_chars: int) -> str:
    """Keep up to `max_lines` non-blank lines or `max_chars` chars, whichever
    binds first. Always preserves the class declaration line if present."""
    out: list[str] = []
    body_count = 0
    chars = 0
    for ln in lines:
        if not _BLANK_RE.match(ln):
            body_count += 1
        out.append(ln)
        chars += len(ln) + 1
        if body_count >= max_lines or chars >= max_chars:
            break
    return "\n".join(out)


def normalize_source(text: str) -> str:
    """Produce a UnixCoder-friendly snippet from raw Ruby source."""
    lines = text.splitlines()
    lines = _strip_leading_comments(lines)
    lines = _compress_blank_runs(lines)
    return _truncate_to_window(lines, _MAX_BODY_LINES, _MAX_CHARS)


def _extract_names(text: str, file_stem: str) -> list[str]:
    """Return all plausible names for the primary entity in this file.

    Ruby files frequently nest a class inside a module (`module Search; class
    ActionsBulk`). The triplet generator references such classes by their
    *bare* name (`ActionsBulk`), so we must surface both the qualified and
    bare forms — and prefer the inner-most class over an outer module.
    """
    classes: list[str] = []
    modules: list[str] = []
    for line in text.splitlines():
        m = CLASS_DEF_RE.match(line)
        if m:
            full = m.group(1)
            classes.append(full.split("::")[-1])
            if "::" in full:
                classes.append(full)
            continue
        m = MODULE_DEF_RE.match(line)
        if m:
            modules.append(m.group(1).split("::")[-1])
    if classes:
        # Inner class wins; outer module name kept as a secondary alias.
        primary = classes[0]
        return [primary] + [c for c in classes[1:] if c != primary]
    if modules:
        return [modules[0]]
    return [_singular_to_class(file_stem)]


def build_index(input_dir: str | Path) -> dict[str, ClassCode]:
    """Walk `input_dir/{classes,data}` and return name → ClassCode.

    Each class file produces one ClassCode but may register under multiple
    aliases (e.g. `ActionsBulk` and `Search::ActionsBulk` for a class nested
    in a module). The triplet generator's bare-name references find a hit
    via the bare alias.
    """
    input_dir = Path(input_dir)
    out: dict[str, ClassCode] = {}
    for path in input_dir.rglob("*.rb"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        names = _extract_names(text, path.stem)
        if not names:
            continue
        primary = names[0]
        cc = ClassCode(
            name=primary,
            path=str(path),
            code=normalize_source(text),
            raw_lines=len(text.splitlines()),
        )
        for name in names:
            existing = out.get(name)
            if existing is None:
                out[name] = cc
                continue
            # Collision: prefer the file under classes/ over data/.
            if "/classes/" in str(path) and "/classes/" not in existing.path:
                out[name] = cc
    return out


# Rails subdirectories whose .rb files define classes we care about
# (mirrors RAILS_APP_DIRS in symbolic/rules.py — kept in sync manually).
_RAILS_APP_SUBDIRS = (
    "models", "controllers", "helpers", "mailers", "jobs", "policies",
    "workflows", "services", "builders", "presenters", "validators",
    "uploaders", "finders", "actions", "channels", "listeners",
    "dispatchers", "drops", "fields", "mailboxes", "dashboards",
    "lib", "classes", "data",
)


def build_index_from_rails_app(app_root: str | Path) -> dict[str, ClassCode]:
    """Walk the FULL Rails tree (`<app_root>/app/<role>/...`) and index
    every class. Mirrors the coverage of `RailsAwareGraph.rb` so the neural
    layer's code-context matches what the symbolic layer sees.

    Accepts either `datasets/<app>` (Rails root) or `datasets/<app>/app`
    (the app/ directory itself). Searches all known Rails subdirectories.
    """
    app_root = Path(app_root)
    app_dir = app_root / "app" if (app_root / "app").is_dir() else app_root
    out: dict[str, ClassCode] = {}
    for sub in _RAILS_APP_SUBDIRS:
        sub_dir = app_dir / sub
        if not sub_dir.is_dir():
            continue
        for path in sub_dir.rglob("*.rb"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            names = _extract_names(text, path.stem)
            if not names:
                continue
            primary = names[0]
            cc = ClassCode(
                name=primary,
                path=str(path),
                code=normalize_source(text),
                raw_lines=len(text.splitlines()),
            )
            for name in names:
                # Prefer the first occurrence we see; collisions across roles
                # are rare in well-formed Rails apps. When they happen, the
                # role-priority order in _RAILS_APP_SUBDIRS biases toward
                # models > controllers > helpers > ..., which matches the
                # convention of "models are canonical".
                if name not in out:
                    out[name] = cc
    return out


def filter_triplets_by_index(
    triplets: list[dict],
    index: dict[str, ClassCode] | dict[str, dict],
) -> list[dict]:
    """Drop triplets whose anchor/positive/negative isn't in the code index.

    Necessary for incomplete input dumps (e.g. Industrial-X ships only controllers,
    so triplets referencing helpers/services have no code to feed UnixCoder).
    Returns the filtered list — caller decides whether to warn on drop rate.
    """
    keys = set(index.keys())
    return [
        t for t in triplets
        if t["anchor"] in keys and t["positive"] in keys and t["negative"] in keys
    ]


def save_index(index: dict[str, ClassCode], path: str | Path) -> None:
    """JSON dump for downstream consumption (training script, evaluation)."""
    payload = {
        name: {"path": cc.path, "code": cc.code, "raw_lines": cc.raw_lines}
        for name, cc in sorted(index.items())
    }
    Path(path).write_text(json.dumps(payload, indent=2))


def main() -> None:
    import argparse

    p = argparse.ArgumentParser(description="Build class-name → code index per app")
    p.add_argument("--results-dir", default="results")
    p.add_argument("--datasets-dir", default="datasets",
                   help="root of Rails app sources (rails-aware mode)")
    p.add_argument("--mode", choices=["rails-aware", "legacy"], default="rails-aware")
    p.add_argument("--out-dir", default="neurosymbolic/output/code_index")
    p.add_argument("--apps", nargs="*")
    args = p.parse_args()

    out_root = Path(args.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    if args.mode == "rails-aware":
        datasets_root = Path(args.datasets_dir)
        for app_dir in sorted(datasets_root.iterdir()):
            if not app_dir.is_dir() or not (app_dir / "app").is_dir():
                continue
            if args.apps and app_dir.name not in args.apps:
                continue
            index = build_index_from_rails_app(app_dir)
            out_path = out_root / f"{app_dir.name}.json"
            save_index(index, out_path)
            avg_chars = (
                sum(len(cc.code) for cc in index.values()) / max(1, len(index))
            )
            print(
                f"{app_dir.name}: {len(index)} classes indexed (rails-aware), "
                f"avg {avg_chars:.0f} chars/class → {out_path}"
            )
        return

    # legacy mode
    results_root = Path(args.results_dir)
    for app_dir in sorted(results_root.iterdir()):
        if not app_dir.is_dir() or not (app_dir / "input").is_dir():
            continue
        if args.apps and app_dir.name not in args.apps:
            continue
        index = build_index(app_dir / "input")
        out_path = out_root / f"{app_dir.name}.json"
        save_index(index, out_path)
        avg_chars = (
            sum(len(cc.code) for cc in index.values()) / max(1, len(index))
        )
        print(
            f"{app_dir.name}: {len(index)} classes indexed, "
            f"avg {avg_chars:.0f} chars/class → {out_path}"
        )


if __name__ == "__main__":
    main()
