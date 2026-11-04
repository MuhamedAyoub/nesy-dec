#!/usr/bin/env bash
# Level 1: regenerate every table from the shipped results, on CPU, without
# checkpoints, a GPU or the subject sources, and diff each regenerated file
# against the shipped one.
#
#   bash scripts/reproduce.sh               # the tables (about 1 min)
#   SLOW=1 bash scripts/reproduce.sh        # also refine_checks.md (several minutes, see README)
#   KEEP=1 bash scripts/reproduce.sh        # keep the work copy for inspection
#
# The generators write into results/, so they run on a temporary copy of the
# repository and the shipped files are never overwritten. Exit status 1 if any
# regenerated file differs from the shipped one.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"
W="$(mktemp -d "${TMPDIR:-/tmp}/nesy-dec-repro.XXXXXX")"
trap '[[ "${KEEP:-0}" == 1 ]] && echo "work copy kept in $W" || rm -rf "$W"' EXIT

# code and results; leave out git metadata, subject sources and the large checkpoints
(cd "$REPO" && tar cf - --exclude=./.git --exclude=./datasets_java --exclude='policy*.pt' --exclude='*.pkl' \
   --exclude=__pycache__ .) | (cd "$W" && tar xf -)
cd "$W"
export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0

FAIL=0
check() {  # check FILE: compare the regenerated FILE in the work copy with the shipped one
  if cmp -s "$W/$1" "$REPO/$1"; then echo "  same     $1"
  else echo "  DIFFERS  $1"; diff "$REPO/$1" "$W/$1" | head -20 | sed 's/^/           /'; FAIL=1; fi
}
gen() {    # gen FILE CMD...: run CMD with stdout to FILE, then check
  local out="$1"; shift
  if ! "$@" > "$W/$out" 2> "$W/.err"; then echo "  FAILED   $out: $*"; tail -5 "$W/.err" | sed 's/^/           /'; FAIL=1; return; fi
  check "$out"
}

echo "[1/4] metrics and composite scores (java_pipeline.results)"
"$PY" -m java_pipeline.results > /dev/null || FAIL=1
for f in metrics.csv composite.csv external.csv ablation.csv summary.json; do check "results/results/$f"; done

if command -v ruby > /dev/null; then
  # reruns RoR-MSI's clustering (vendor/ror_msi/tools, via java_pipeline/teacher.rb) on each layer
  # variant of G; the per-variant JSON files also record their input path, so only the CSV is compared
  "$PY" -m java_pipeline.layer_ablation > /dev/null 2> "$W/.err" || { echo "  FAILED   layer_ablation"; FAIL=1; }
  check results/results/layer_ablation.csv
else
  echo "  skipped  results/results/layer_ablation.csv (needs ruby)"
fi

echo "[2/4] tables"
gen results/results_tables.md          "$PY" -m java_pipeline.results_tables
gen results/ablation_tables.md         "$PY" -m java_pipeline.results_tables ablation
gen results/paper_tables.md            "$PY" -m java_pipeline.paper_tables
gen results/followup.md                "$PY" -m java_pipeline.followup_report
gen results/repair_baseline.md         "$PY" -m java_pipeline.repair_baseline report
gen results/results/sota_graphrl_only.md "$PY" -m java_pipeline.sota_table
gen results/gaming_check.md            "$PY" -m java_pipeline.gaming_check
gen results/refine_report.md           "$PY" -m java_pipeline.refine_report
gen results/resolver_tables.md         "$PY" -m java_pipeline.resolver_tables
gen results/facts_tables.md            "$PY" -m java_pipeline.facts_tables
gen results/audit_tables.md            "$PY" -m java_pipeline.audit_tables
if [[ "${SLOW:-0}" == 1 ]]; then
  gen results/refine_checks.md         "$PY" -m java_pipeline.refine_checks
else
  echo "  skipped  results/refine_checks.md (SLOW=1 to run it)"
fi

echo "[3/4] reconnaissance scripts cited by the documents"
for s in binarized_selfcalls graphrl_repairs int_truncation setting_selection; do
  gen "results/recon/$s.out" "$PY" "results/recon/$s.py"
done
for s in eq5_implied_weights eq5_reproduce; do   # these two are run from their own folder
  (cd results/recon && "$PY" "$s.py" > "$s.out" 2> "$W/.err") || { echo "  FAILED   results/recon/$s.out"; FAIL=1; }
  check "results/recon/$s.out"
done

echo "[4/4] not regenerated here"
echo "  results/idea1_report.md      reads the superseded run in results/_archive/, which is not released"
echo "  results/recon/mask_replay.out  needs the checkpoints: scripts/replay_decodes.sh"
echo "  results/report/*.pdf         python -m java_pipeline.report_pdf (needs pdflatex)"

if [[ $FAIL == 0 ]]; then echo "reproduce: every regenerated file equals the shipped one"; else echo "reproduce: DIFFERENCES above"; fi
exit $FAIL
