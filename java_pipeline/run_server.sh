#!/usr/bin/env bash
# One command for the GPU server: set up, check, run every GPU stage, pack.
#
#   bash java_pipeline/run_server.sh                 # full plan: seeds 42 1 7
#   SEEDS="42" bash java_pipeline/run_server.sh      # one seed only (a complete, comparable run)
#   bash java_pipeline/run_server.sh status          # progress, read from the output files
#   RLDEC=0 bash java_pipeline/run_server.sh         # skip RLDec and its environment (its outputs
#                                                    # already exist)
#   ABLATIONS="kl0_ep2000 nobc_ep2000" bash ...      # also run these labelled RL ablations, side by
#                                                    # side, after the main pipeline
#   SMOKE=1 bash java_pipeline/run_server.sh         # 5-minute plumbing test first; outputs are
#                                                    # labelled smoke and are not results
#
# Two pipelines run side by side, each with its own log under logs/:
#   main   encoder -> check -> GraphRL-Dec (8 variants x apps x seeds) -> embedding baselines
#   rldec  RLDec per app and seed, RLDEC_JOBS processes at a time
# Both resume: rerunning this script skips every run whose output exists.
# At the end it packs results_java_gpu.tar.gz together with the logs.
#
# Run it detached so a dropped SSH session does not stop it:
#   nohup bash java_pipeline/run_server.sh > logs/run_server.out 2>&1 &
# (java_pipeline/remote.sh start does exactly that.)
set -uo pipefail
cd "$(dirname "$0")/.."

SEEDS="${SEEDS:-42 1 7}"
RLDEC_JOBS="${RLDEC_JOBS:-6}"
SMOKE="${SMOKE:-0}"
RLDEC="${RLDEC:-1}"
ABLATIONS="${ABLATIONS:-}"
mkdir -p logs

status() {
  python3 - "$SEEDS" <<'EOF'
import json, sys
from pathlib import Path
seeds = [int(s) for s in sys.argv[1].split()]
apps = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
variants = ["structural", "semantic", "affinity", "noise", "full", "fullC2", "fullC1", "fullC1C2"]
R = Path("results")
enc = (R / "_nesy/encoder/train/run.json").is_file()
rl = sum((R / f"_nesy/rl/{a}/{v}_s{s}/partition.json").is_file() for a in apps for v in variants for s in seeds)
rd = sum((R / f"{a}/baselines/rldec_s{s}.json").is_file() for a in apps for s in seeds)
bl = sum((R / f"{a}/baselines/unixcoder_ward_nesyrep.json").is_file() for a in apps)
print(f"encoder {'done' if enc else 'pending'} | GraphRL-Dec {rl}/{len(apps)*len(variants)*len(seeds)} | "
      f"NeSy-Rep baselines {bl}/{len(apps)} | RLDec {rd}/{len(apps)*len(seeds)}")
EOF
}

if [[ "${1:-}" == "status" ]]; then
  status
  for f in logs/main.log logs/rldec.log; do [[ -f $f ]] && { echo "--- tail $f"; tail -n 3 "$f"; }; done
  exit 0
fi

echo "[run_server] $(date -Is) seeds: $SEEDS, RLDec jobs: $RLDEC_JOBS"

# 1. setup, once
if [[ ! -x .venv/bin/python || ( "$RLDEC" != "0" && ! -x .venv-rldec/bin/python ) ]]; then
  RLDEC="$RLDEC" bash java_pipeline/setup_gpu.sh 2>&1 | tee logs/setup.log || { echo "[run_server] setup failed, see logs/setup.log"; exit 1; }
fi
PY=.venv/bin/python

# 2. preflight; stop on any mismatch
$PY -m java_pipeline.run_gpu --stages check 2>&1 | tee logs/check.log
grep -q "^\[check\] OK" logs/check.log || { echo "[run_server] preflight failed; nothing was trained"; exit 1; }

if [[ "$SMOKE" == "1" ]]; then
  echo "[run_server] SMOKE: every stage at toy size on jpetstore-6"
  $PY -m java_pipeline.run_gpu --smoke > logs/smoke_main.log 2>&1 && echo "  main stages OK" || { echo "  main FAILED, see logs/smoke_main.log"; exit 1; }
  .venv-rldec/bin/python -m java_pipeline.run_rldec --iterations 1 jpetstore-6 > logs/smoke_rldec.log 2>&1 \
    && echo "  RLDec OK" || { echo "  RLDec FAILED, see logs/smoke_rldec.log"; exit 1; }
  rm -rf results/_nesy/rl_smoke results/_nesy/encoder_smoke results/*/baselines/*_smoke.json \
         results/*/baselines/rldec_models
  echo "[run_server] smoke passed; smoke outputs removed. Now run without SMOKE=1."
  exit 0
fi

# 3. both pipelines
if [[ "$RLDEC" != "0" ]]; then
  # shellcheck disable=SC2086
  $PY -m java_pipeline.run_gpu --stages rldec --seeds $SEEDS --rldec-python .venv-rldec/bin/python \
      --rldec-jobs "$RLDEC_JOBS" > logs/rldec.log 2>&1 &
  RLDEC_PID=$!
  echo "[run_server] RLDec running in the background (pid $RLDEC_PID, logs/rldec.log)"
else
  echo "[run_server] RLDEC=0: RLDec skipped"
fi

# shellcheck disable=SC2086
$PY -m java_pipeline.run_gpu --stages encoder,check,rl,baselines --seeds $SEEDS > logs/main.log 2>&1
MAIN_RC=$?
echo "[run_server] main pipeline finished with rc=$MAIN_RC (logs/main.log)"

# shellcheck disable=SC2086
declare -A ABL_PID=()
[[ $MAIN_RC -eq 0 ]] || ABLATIONS=""   # they read the encoder's embeddings
for name in $ABLATIONS; do      # side by side; each is a small RL job
  echo "[run_server] $(date -Is) ablation $name started (logs/ablation_$name.log)"
  $PY -m java_pipeline.run_gpu --stages ablation --ablations "$name" --seeds $SEEDS > "logs/ablation_$name.log" 2>&1 &
  ABL_PID[$name]=$!
done
for name in "${!ABL_PID[@]}"; do
  wait "${ABL_PID[$name]}"
  rc=$?
  echo "[run_server] $(date -Is) ablation $name finished with rc=$rc"
  [[ $rc -eq 0 ]] || MAIN_RC=$rc
done

RLDEC_RC=0
if [[ "$RLDEC" != "0" ]]; then
  wait $RLDEC_PID
  RLDEC_RC=$?
  echo "[run_server] RLDec finished with rc=$RLDEC_RC (logs/rldec.log)"
fi

# 4. pack, including the logs (RUNS.md reads wall times from them)
$PY -m java_pipeline.run_gpu --stages pack > logs/pack.log 2>&1
gunzip -f results_java_gpu.tar.gz && tar rf results_java_gpu.tar logs && gzip -f results_java_gpu.tar
status
ls -la results_java_gpu.tar.gz
echo "[run_server] $(date -Is) done: main rc=$MAIN_RC, rldec rc=$RLDEC_RC"
[[ $MAIN_RC -eq 0 && $RLDEC_RC -eq 0 ]]
