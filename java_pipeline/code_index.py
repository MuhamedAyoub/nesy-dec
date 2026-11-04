"""Phase 5: class-name -> source snippet index for NeSy-Rep, Java version.

The Java counterpart of neurosymbolic/code_reader.py, with the same output
schema ({fqcn: {path, code, raw_lines}}) and the same budget: the declaration
plus at most 30 non-blank body lines or 1,800 characters, whichever binds
first (code_reader._MAX_BODY_LINES, _MAX_CHARS; about 400 UnixCoder tokens).
Only the boilerplate stripping is language specific:

  * comments (/* */, /** */ and //) are removed, string literals kept;
  * package and import lines are removed;
  * blank-line runs are compressed, as in Rails.

A snippet starts at the type's declaration (annotations included, since they
carry the stereotype) and is cut at its closing brace, so a named member type
gets its own body and a top-level type's window is its own head.

Usage: python3 -m java_pipeline.code_index [app ...]
Writes results/<app>/code_index.json.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from java_pipeline.audit import rel
from java_pipeline.subjects import OUT, SUBJECTS
from neurosymbolic.code_reader import _MAX_BODY_LINES, _MAX_CHARS, _compress_blank_runs, _truncate_to_window

TOKEN = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|/\*.*?\*/|//[^\n]*', re.S)


def strip_comments(src: str) -> str:
    """Remove comments, keep strings, keep line breaks so lines still align."""
    def repl(m: re.Match) -> str:
        s = m.group(0)
        if s.startswith(("/*", "//")):
            return re.sub(r"[^\n]", "", s)
        return s
    return TOKEN.sub(repl, src)


def body_end(lines: list[str], start: int) -> int:
    """Index of the line holding the brace that closes the first block opened
    at or after `start`. Strings and char literals are masked first."""
    depth, opened = 0, False
    for i in range(start, len(lines)):
        masked = re.sub(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'', '""', lines[i])
        for ch in masked:
            if ch == "{":
                depth += 1
                opened = True
            elif ch == "}":
                depth -= 1
                if opened and depth == 0:
                    return i
    return len(lines) - 1


def snippet(file: str, line: int, simple: str) -> tuple[str, int]:
    text = strip_comments(Path(file).read_text(encoding="utf-8", errors="replace"))
    lines = text.splitlines()
    start = max(0, line - 1)
    # brace matching starts at the declaration keyword, so braces inside
    # annotations above it (@NamedQueries({...})) are not taken for the body
    decl = re.compile(rf"\b(class|interface|enum|record|@interface)\s+{re.escape(simple)}\b")
    head = next((i for i in range(start, len(lines)) if decl.search(lines[i])), start)
    end = body_end(lines, head)
    block = [l for l in lines[start:end + 1] if not re.match(r"\s*(package|import)\s+[\w.*]+\s*;", l)]
    block = _compress_blank_runs(block)
    while block and not block[0].strip():
        block.pop(0)
    return _truncate_to_window(block, _MAX_BODY_LINES, _MAX_CHARS), end - start + 1


def build(app: str) -> dict:
    inv = json.loads((OUT / app / "facts" / "inventory.json").read_text())
    nodes = set(json.loads((OUT / app / "graph.json").read_text())["dependency_graph"])
    out = {}
    for t in inv:
        if t["name"] not in nodes:
            continue
        code, raw = snippet(t["file"], t["line"], t["name"].split(".")[-1])
        out[t["name"]] = {"path": rel(t["file"]), "code": code, "raw_lines": raw}
    missing = sorted(nodes - set(out))
    if missing:
        raise SystemExit(f"[code_index] {app}: no snippet for {len(missing)} nodes, e.g. {missing[:3]}")
    (OUT / app / "code_index.json").write_text(json.dumps(dict(sorted(out.items())), indent=2))
    return out


def main(apps: list[str]) -> None:
    for app in apps:
        idx = build(app)
        chars = [len(v["code"]) for v in idx.values()]
        print(f"{app:18s} {len(idx)} classes, mean {sum(chars) / len(chars):.0f} chars, max {max(chars)}, "
              f"empty {sum(1 for c in chars if c < 20)}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUBJECTS))
