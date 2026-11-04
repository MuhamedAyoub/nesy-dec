# Phase 8: verification

Date: 2026-10-26, updated 2026-11-03 for the rerun with cannot-link pairs
(RUNS.md, section 2d).

## 1. Reruns

**CPU stages, from source.** `python3 -m java_pipeline.verify jpetstore-6`
rebuilds jpetstore-6 from its sources into `results/verify/rerun/` and
compares 25 output files with the reported ones (last rerun 2026-11-03,
after rule CL-SIBLING was added)
(`results/verify/jpetstore-6_rerun.json`). The stages are:
- analyzer, audit, resolver;
- the teacher at both α, facts, code index, triplets;
- the Sellami export and HierDec.

The comparison:
- 24 files are identical, after dropping wall-time fields and the
  `parameters.graph` input path in the two teacher files.
- `triplets.json` holds the same multiset of 239 triplets, but its order
  can differ: 37 entries were out of order on 2026-10-26, and in 4 of 5
  reruns on 2026-11-03 (the fifth was byte-identical). The ties come from
  Python set iteration in the shared `neurosymbolic/triplets.py`, which
  follows `PYTHONHASHSEED`.

As a result, the encoder's training order is not bit-reproducible across
processes, for Rails and Java alike. The triplet content is.

**GPU stage, across machines.** GraphRL-Dec `full` with seed 42 was run a
second time with the same config on this machine's RTX 3060 (torch
2.5.1+cu121), for daytrader7 and lit-jpetstore, two of the apps with
cannot-link pairs. The reported runs come from the server's RTX 4090 (torch
2.14.1+cu130). The output is in `results/_nesy/rl_ablation/repro_check/`,
and the comparison script is `results/verify/repro_check.py`.
- daytrader7: the identical partition, the identical decoded score (0.1505,
  raw composite on G) and an identical `decode_score` at every logged
  episode.
- lit-jpetstore: one class of 71, `ProductSearch`, is placed in a different
  service, and the decoded score is 0.0705 against 0.0660. The two
  trajectories first differ at the third logged episode. Both runs violate
  no cannot-link pair.

So GraphRL-Dec is not bit-reproducible across hardware and torch builds,
though the difference here is one class.

**The decode depends on the torch build.** Decoding the server's saved
checkpoints here with torch 2.5.1 gives a different partition in 72 of the
108 main and ablation runs on the constrained apps, on CPU and GPU alike: near-tied logits
flip, and each flip changes the later steps. With the server's version,
torch 2.14.1 (CPU build), every reported partition is reproduced exactly,
198 of 198 including the follow-up runs (`results/recon/mask_replay.out`). A rerun must
therefore pin the torch version as well as the seed. Under both versions
no decode violated a cannot-link pair. On the first run's outputs, the
same check on the same server gave identical partitions and trajectories
for jpetstore-6 and daytrader7 (archived in
`results/_archive/pre_cl_sibling_2026-10-26/_nesy/rl_ablation/repro_check/`).

**Not rerun.** The encoder fine-tune and RLDec. Their runs are one per
setting (encoder) and 3 seeds (RLDec), and they are reported as such.

## 2. Tests

- `tests/`: 447 passed (`results/verify/java_tests.out`). That is
  403 metric tests, 8 audit-classifier tests, 29 resolver fixtures and 7
  tests of the cannot-link rule CL-SIBLING.
- `neurosymbolic/tests/` (the Rails pipeline): 47 passed, 1 skipped and 4
  failed (`results/verify/rails_tests.out`).
  - `test_rl_smoke.py::test_ppo_loop_runs` and `test_greedy_decompose_runs`
    pass a `rollout_episodes` argument that `PPOConfig` no longer accepts.
  - `test_triplets.py::test_pyx4_degrades_gracefully` and
    `test_per_class_concentration_capped` fail on their own assertions.

  The failures predate this work. No file under `neurosymbolic/`, `vendor/ror_msi/tools/`,
  `vendor/ror_msi/evaluate.py`, `run_neurosym_ablation.py` or `experiment_v2.rb` has a
  modification time after 2026-10-19, when the Java work began (checked
  again on 2026-11-03). The Java
  pipeline patches the Rails code at run time (`java_pipeline/rl_paths.py`)
  and never edits it.

## 3. Claims in RESULTS.md and their sources

| claim | source |
|---|---|
| every method of the main pool partitions the same class set with coverage 1.00 | `results/metrics.csv`, columns `coverage`, `classes_outside_class_set` |
| CL-SIBLING gives 169, 684 and 352 pairs on AcmeAir, DayTrader and lit-jpetstore, none elsewhere | `<app>/facts_nesy.json`, `cannot_link`; `<app>/facts_report.json`; `gpu_logs/check.log` |
| GraphRL-Dec violates no cannot-link pair in any run; the other methods' counts | `results/metrics.csv`, `cannot_link_violations`; Table E6 (`paper_tables.py`, J5) |
| rule-based repairs of the teacher reach 0 violations; the best of them is at most 0.02 below GraphRL-Dec in any app and convention | `repair_baseline.md` (`java_pipeline/repair_baseline.py`); partitions in `<app>/baselines/repair_*.json`, built on the server (`gpu_logs/repair_baseline.log`) |
| the mask's fallback never fired and no illegal action was taken in the 198 decodes on the constrained apps (main run, ablations, follow-up); replay reproduces every reported partition | `recon/mask_replay.py` and `.out` (torch 2.14.1) |
| the kl0 setting was chosen on the apps without cannot-link pairs only | `recon/setting_selection.py` and `.out` |
| GraphRL-Dec full with kl0 beats the best repair on DayTrader and lit-jpetstore in all three conventions, not on AcmeAir; the NeSy-Rep warm start at best ties its repair | `followup.md` (`java_pipeline/followup_report.py`), Table F1 |
| kl0 above the paper setting in 33, 15 and 33 of 48 (app, variant) pairs | `followup.md`, Table F2 |
| 72 of 144 GraphRL-Dec runs decode to the teacher's partition, all on the apps without cannot-link pairs | `_nesy/rl/<app>/<run>/partition.json` against `exp_a0.9_b0.1_n8_java.json`; Table E3 |
| GraphRL-Dec full moves 2, 21 and 5 classes, 2, 15 and 5 of them in a pair the teacher violates | `recon/graphrl_repairs.py` and `.out` |
| GraphRL-Dec has the highest evaluate Score on AcmeAir, DayTrader and lit-jpetstore, ties the teacher on Plants and lit-pbw, and NeSy-Rep + Ward leads on jpetstore-6 | `results/composite.csv`, convention evaluate, eq5 as_published; Table E1 |
| GraphRL-Dec keeps 24 of 41 must-link pairs on DayTrader, the teacher 30 | `paper_tables.md`, Table J4; `facts_nesy.json`, `must_link` |
| NeSy-Rep + Ward has a higher SM than UnixCoder + Ward on all six apps | `results/metrics.csv`, evaluate_SM |
| NeSy-Rep + Ward leads four apps under the rldec convention | `results/composite.csv`, convention rldec |
| HierDec gives 12 to 62 services | `<app>/baselines/hierdec.json` |
| RLDec's CLI decode gives one service on every app and seed | `<app>/baselines/rldec_s<seed>.json` |
| RLDec's best training state gives 2 to 18 services | `<app>/baselines/rldec_best_s<seed>.json` |
| the ranks against Weerasinghe Table 1 | `results/external.csv`; `results/sota_graphrl_only.md`; the published values in `recon/eq5_reproduce.py`, transcribed from 2601.23141v1.pdf p. 8 |
| the ablation results | `results/ablation.csv`; `_nesy/rl_ablation/<ablation>/` |
| random partition + hill-climb ranks #1 in all 18 weighted pools and violates 8 to 91 cannot-link pairs | `gaming_check.md` (`java_pipeline/gaming_check.py`) |
| the encoder's cannot-link loss per epoch | `gpu_logs/main.log`, `epoch ... done` lines; Rails: `v2_full_run_backup/encoder/train/train_log.json` |
| the run times and config hashes | RUNS.md section 2d; `runs_plan.json`; `gpu_logs/` |

## 4. Missing or approximate

- **Phase 2 to 4 class counts** are measured on our class-counting rule.
  How the published papers counted classes is unknown (SUBJECTS.md,
  section 4).
- **`textAndNames`.** The TF-IDF features for HierDec and RLDec use the full
  class source in place of the Spoon analyzer's `textAndNames`. Its exact
  content is unknown.
- **RLDec's best-state row** is a selection we made from RLDec's own
  training records. It is not an output of RLDec's decompose command.
- **CL-SIBLING on unseen systems.** The rule was written on these six
  subjects and has not been applied to other Java systems.
- **Encoder variance** is not measured: one encoder run.
- **Published rows** are copied from Weerasinghe Table 1, not re-run.
