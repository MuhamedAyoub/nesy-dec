#!/usr/bin/env bash
# Clone the three third-party tools at the commits we ran. They are not part of
# this repository (see README, "Third-party baselines").
#
#   bash scripts/fetch_baselines.sh                 # into the parent folder (the default layout)
#   BASELINES_DIR=/some/dir bash scripts/fetch_baselines.sh
#
# java_pipeline/run_rldec.py, run_hierdec.py and tests/test_metrics.py look in
# $BASELINES_DIR (default: the folder that contains this repository).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${BASELINES_DIR:-..}"
mkdir -p "$DEST"
BASELINES=(
  "decomp-rldec            https://github.com/khaledsellami/decomp-rldec.git            45187548912b324fcaf489c7af6f5172f07833c1"
  "decomp-hydec            https://github.com/khaledsellami/decomp-hydec.git            bc56be4e97f252769d19adead8cab46a9b447f05"
  "decomp-parsing-service  https://github.com/khaledsellami/decomp-parsing-service.git  84318d712dcafa96fe40cc29bb025441fc5da2d5"
)
for line in "${BASELINES[@]}"; do
  read -r dir url commit <<<"$line"
  [[ -d "$DEST/$dir/.git" ]] || git clone --quiet "$url" "$DEST/$dir"
  git -C "$DEST/$dir" -c advice.detachedHead=false checkout --quiet "$commit"
  [[ "$(git -C "$DEST/$dir" rev-parse HEAD)" == "$commit" ]] || { echo "[fetch] $dir: wrong commit" >&2; exit 1; }
  echo "[fetch] $dir @ ${commit:0:7} ok"
done
