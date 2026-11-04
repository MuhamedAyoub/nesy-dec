#!/usr/bin/env bash
# Level 2: replay the greedy decode of every GraphRL-Dec run on the three apps
# with cannot-link pairs (results/recon/mask_replay.py), check the action mask
# at every step, and compare with the shipped results/recon/mask_replay.out.
#
# Needs the checkpoint archive (ARTIFACTS.md) extracted at the repository root:
#   tar xzf nesy-dec-checkpoints.tar.gz
# and torch 2.14.1, CPU build (requirements-replay.txt). Another torch build
# decodes some runs differently (results/VERIFICATION.md, section 1).
#
# Expected: TOTAL {"runs": 198, "steps": 16170, "fallback": 0, "illegal": 0, "violations": 0, "mismatch": 0}
set -uo pipefail
cd "$(dirname "$0")/.."
PY="${PYTHON:-python3}"
export PYTHONDONTWRITEBYTECODE=1

n=$(find results/_nesy/rl results/_nesy/rl_ablation -name policy_best.pt 2>/dev/null | wc -l)
if [[ "$n" -lt 198 ]]; then
  echo "replay: found $n policy_best.pt files; extract nesy-dec-checkpoints.tar.gz at the repository root first (ARTIFACTS.md)" >&2
  exit 2
fi
tv=$("$PY" -c 'import torch; print(torch.__version__)')
[[ "$tv" == 2.14.1* ]] || echo "replay: WARNING torch $tv; the reported partitions are reproduced exactly only with 2.14.1 (CPU build)" >&2

OUT="$(mktemp "${TMPDIR:-/tmp}/mask_replay.XXXXXX.out")"
time "$PY" results/recon/mask_replay.py > "$OUT"
tail -1 "$OUT"
if cmp -s "$OUT" results/recon/mask_replay.out; then
  echo "replay: output equals results/recon/mask_replay.out"; rm -f "$OUT"; exit 0
else
  echo "replay: output differs from results/recon/mask_replay.out (kept in $OUT):"
  diff results/recon/mask_replay.out "$OUT" | head -20; exit 1
fi
