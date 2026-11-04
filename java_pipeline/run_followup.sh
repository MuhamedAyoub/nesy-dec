#!/usr/bin/env bash
# Follow-up GPU runs of 2026-11-03 (RESULTS.md, section 7), on the server that
# already holds the main run:
#   1. GraphRL-Dec with the kl0_ep2000 setting, all 8 variants (the structural
#      and full runs already exist and are skipped), setting chosen by
#      results/recon/setting_selection.py;
#   2. GraphRL-Dec warm-started from NeSy-Rep + Ward, paper setting and kl0_ep2000,
#      structural and full;
#   3. the rule-based repairs of the teacher and of NeSy-Rep + Ward.
# Then packs the new outputs into results_java_followup.tar.gz.
#
# Usage (from <repo>/, detached):
#   setsid nohup bash java_pipeline/run_followup.sh > logs/followup.out 2>&1 < /dev/null &
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
SEEDS="42 1 7"
ALL="structural +semantic +affinity +noise full full+C2 full+C1 full+C1+C2"
echo "[followup] $(date -Is) start"

$PY -m java_pipeline.repair_baseline > logs/repair_baseline.log 2>&1 || { echo "[followup] repair baselines failed"; exit 1; }
echo "[followup] repair baselines done"

pids=()
# shellcheck disable=SC2086
$PY -m java_pipeline.run_gpu --stages ablation --ablations kl0_ep2000 --variants $ALL --seeds $SEEDS \
    --apps jpetstore-6 acmeair daytrader7 > logs/followup_kl0_a.log 2>&1 & pids+=($!)
# shellcheck disable=SC2086
$PY -m java_pipeline.run_gpu --stages ablation --ablations kl0_ep2000 --variants $ALL --seeds $SEEDS \
    --apps plantsbywebsphere lit-jpetstore lit-pbw > logs/followup_kl0_b.log 2>&1 & pids+=($!)
# shellcheck disable=SC2086
$PY -m java_pipeline.run_gpu --stages ablation --ablations nesyward --variants structural full --seeds $SEEDS \
    > logs/followup_nesyward.log 2>&1 & pids+=($!)
# shellcheck disable=SC2086
$PY -m java_pipeline.run_gpu --stages ablation --ablations nesyward_kl0_ep2000 --variants structural full --seeds $SEEDS \
    > logs/followup_nesyward_kl0.log 2>&1 & pids+=($!)
rc=0
for p in "${pids[@]}"; do wait "$p" || rc=1; done
echo "[followup] $(date -Is) runs finished, rc=$rc"

tar czf results_java_followup.tar.gz results/_nesy/rl_ablation/kl0_ep2000 results/_nesy/rl_ablation/nesyward \
    results/_nesy/rl_ablation/nesyward_kl0_ep2000 results/*/baselines/repair_*.json \
    results/*/exp_nesyward_java.json logs/followup_*.log logs/repair_baseline.log logs/followup.out
sha256sum results_java_followup.tar.gz
echo "[followup] $(date -Is) done rc=$rc"
