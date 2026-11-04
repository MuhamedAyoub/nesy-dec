#!/usr/bin/env bash
# Build the upload bundle for the GPU box: code plus every CPU-stage output
# the GPU stages read. No benchmark sources, no Rails outputs.
#
# Usage (from <repo>/): bash java_pipeline/make_bundle.sh
# Writes ../java_gpu_bundle.tar.gz, laid out like the parent folder (this repo next to its decomp-* checkouts), so that
# REPO.parent / "decomp-rldec" still resolves on the box.
set -euo pipefail
R="$(basename "$(cd "$(dirname "$0")/.." && pwd)")"   # this repository's folder name
cd "$(dirname "$0")/../.."
OUT=java_gpu_bundle.tar.gz
tar czf "$OUT" \
  --exclude='__pycache__' --exclude='*.pyc' \
  --exclude="$R/neurosymbolic/output" --exclude="$R/neurosymbolic/output_old1" \
  --exclude="$R/neurosymbolic/output.zip" \
  --exclude="$R/results/*/baselines/rldec_models" --exclude="$R/results/_archive" \
  "$R/vendor" "$R/run_neurosym_ablation.py" "$R/neurosymbolic" \
  "$R/java_pipeline" "$R/tests" "$R/results" \
  decomp-rldec decomp-hydec
ls -la "$OUT"
sha256sum "$OUT" | tee "$OUT.sha256"
