# Phase 5 and 6: runs

Date: 2026-10-25. This file has three parts:
- the runs already done on this machine (CPU);
- the runs planned for the GPU box, with their settings and estimated times;
- every setting that differs from the Rails runs.

The first GPU run finished on 2026-10-26 (section 2c). After rule
CL-SIBLING added cannot-link pairs to the fact base, the stages that read
the fact base were rerun on 2026-11-03 (section 2d); those are the results.
Each output carries its config hash and wall time (`partition.json`, `rldec_s<seed>.json`,
`encoder/train/run.json`).

## 1. Runs done on this machine

| stage | command | seed | wall time | output |
|---|---|---|---|---|
| analyzer 0.2.0 | `java -jar java_analyzer/target/java-analyzer-0.2.0.jar` | - | 1.4 to 4.0 s per app (`facts/run.json`, `seconds`) | `results/<app>/facts/` |
| resolver | `python3 -m java_pipeline.resolver` | - | not timed (seconds) | `results/<app>/graph.json`, `calls_graph.json`, `resolver/` |
| teacher, α = 0.9 and 0.5 | `ruby java_pipeline/teacher.rb` | deterministic | not timed (seconds) | `results/<app>/exp_a*_n8_java.json` |
| facts | `python3 -m java_pipeline.facts` | - | not timed (seconds) | `results/<app>/facts_nesy.json` |
| code index | `python3 -m java_pipeline.code_index` | - | not timed (seconds) | `results/<app>/code_index.json` |
| triplets | `python3 -m java_pipeline.triplets` | 42 | not timed (seconds) | `results/<app>/triplets.json` |
| Sellami export | `python3 -m java_pipeline.export_sellami` | - | not timed (seconds) | `results/<app>/sellami/` |
| HierDec | `python -m java_pipeline.run_hierdec` (rldec env) | deterministic | 0.03 to 0.13 s per app (`baselines/hierdec.json`, `seconds`) | `results/<app>/baselines/hierdec.json` |
| pretrained UnixCoder bank (B0) | `python3 -m java_pipeline.run_gpu --stages b0` (CPU) | deterministic | 1 min 45 s for all six apps (`results/logs/b0_cpu.log`) | `results/_nesy/b0_pretrained/embeddings/` |
| UnixCoder+Ward and +HDBSCAN on B0, random | `python3 -m java_pipeline.run_gpu --stages baselines` | random: 42 | seconds | `results/<app>/baselines/` |

Each GPU stage was also run once end to end on CPU, at toy sizes, with
`python3 -m java_pipeline.run_gpu --smoke`. The RLDec stage was checked with
`run_rldec --iterations 1`, including two processes in parallel. The server
script was run with `SMOKE=1` from an unpacked copy of the bundle. Their
outputs were labelled smoke and deleted; none is a result.

## 2. Runs planned for the GPU box

`results/runs_plan.json` lists 164 runs, one row each, with the full
config and its hash. A hash is the first 12 hex digits of the SHA-256 of the
canonical JSON config, so the same settings always give the same hash. In
summary:

| stage | runs | seeds | settings (source) | output |
|---|---|---|---|---|
| NeSy-Rep encoder | 1, jointly over the six apps | 42 | UnixCoder-base + LoRA, 3 epochs, batch 16, lr 5e-5, max length 512, triplet margin 0.3, constraint margin 0.5, λ_ml 0.0, λ_cl 0.3 (`runner.ExpConfig` defaults and `run_everything_v2.py` BEST_ML, BEST_CL; identical to `v2_full_run_backup/encoder/train/train_log.json`) | `results/_nesy/encoder/train/` |
| GraphRL-Dec | 6 apps × 8 variants × 3 seeds = 144 | 42, 1, 7 | 600 episodes, 64 envs, BC warm start 800 epochs at lr 1e-3 from the teacher, PPO lr 1e-4, KL 0.5 (0.2 in the full variants, as in Rails), size cap 5.0, z-score reward, select by decode (`run_everything_v2.py` stage 7; variants `run_neurosym_ablation.VARIANTS`) | `results/_nesy/rl/<app>/<variant>_s<seed>/` |
| UnixCoder+Ward, UnixCoder+HDBSCAN on NeSy-Rep | 6 apps × 2 | - | K = teacher K for Ward; HDBSCAN min cluster size min(5, N/3) (`neurosymbolic/rl/eval.py`) | `results/<app>/baselines/` |
| RLDec | 6 apps × 3 seeds = 18 | 42, 1, 7 | combsequential, 20 iterations, `default_config_CombSequential.json`, seed fixed (`decomp-rldec` CLI defaults) | `results/<app>/baselines/rldec_s<seed>.json` |

Three seeds follow the Rails runbook's optional multi-seed setting
(V2_RERUN_RUNBOOK.md, step 4). The Rails v2 paper run used one seed. Seed 42
alone is a complete, comparable run.

## 2b. The server

vast.ai instance, reached at port 43499: one RTX 4090 (24,564 MiB, driver
555.52.04), 128 logical CPUs, 251 GB RAM, 16 GB disk. Started 2026-10-26 with
`SEEDS="42 1 7" RLDEC_JOBS=9 bash java_pipeline/remote.sh start`, after the
`SMOKE=1` test passed there. During the encoder fine-tune, GPU memory was
20,612 MiB in use: 15,888 MiB by the encoder and about 0.6 GB by each of the 9
RLDec processes.

## 2c. Runs completed on the server

These outputs were computed before the fact base had cannot-link pairs.
They are superseded by section 2d and archived in
`results/_archive/pre_cl_sibling_2026-10-26/`, server logs included
(`gpu_logs/` there). The RLDec outputs are the exception: RLDec reads no
fact base, so its 18 runs were kept and are still current.

Every planned run finished with exit code 0. Each output carries a config
hash that matches its row in `runs_plan.json`.

| stage | runs | wall time | source |
|---|---|---|---|
| encoder | 1 (hash d2677ae0aed9) | 289.9 s | `results/_nesy/encoder/train/run.json` |
| GraphRL-Dec | 144 | 7.3 to 30.0 s per run, 35.9 min in total | `partition.json`, field `seconds` |
| embedding baselines | 6 apps | seconds | `gpu_logs/main.log` |
| main pipeline, whole | encoder, check, rl, baselines | 40 min 45 s | `gpu_logs/main.log` |
| RLDec | 18, 9 at a time | 3,230 to 3,560 s per run, 1 h 55 min in total | `rldec_s<seed>.json`, field `wall_seconds`; `gpu_logs/rldec.log` |

After the main run, with the remaining server time, two labelled RL
ablations (`run_gpu.ABLATIONS`) and a reproducibility rerun were also run:
- `kl0_ep2000` and `nobc_ep2000`: 36 runs each (2 variants × 6 apps × 3
  seeds), in `results/_nesy/rl_ablation/`;
- `repro_check`: GraphRL-Dec `full`, seed 42, jpetstore-6 and daytrader7, with
  the main config.

All 74 outputs were checked against their intended settings (KL
coefficient, episodes, warm start, seed), and none deviates. The logs are
`gpu_logs/ablation.log`, `ablation_nobc_a.log`, `ablation_nobc_b.log` and
`repro_check.log`, now in the archive.

The estimates in section 3 below were made before the run. Measured against
them:
- the encoder took 4 min 50 s against about 6 min estimated;
- GraphRL-Dec took 36 min against about 1.4 h;
- RLDec took about 55 min per run on the server. This machine's CPU timing
  had predicted 61 to 69 min.

## 2d. Rerun with cannot-link pairs (2026-11-03)

Rule CL-SIBLING (FACTS.md, section 2) gave cannot-link pairs to AcmeAir
(169), DayTrader (684) and lit-jpetstore (352), and the triplets gained
cannot-link negatives. The encoder trains jointly on all six apps, so the
encoder, all 144 GraphRL-Dec runs, the NeSy-Rep baselines and the two
ablations were rerun. RLDec, HierDec, the pretrained embeddings and their
baselines, and random read no fact base and were kept.

The server: a vast.ai instance with one RTX 4090 (24,564 MiB, driver
580.142), 96 logical CPUs, 125 GB RAM and a 150 GB disk. The main
environment was the image's own torch 2.14.1+cu130 with transformers
4.45.2 and peft 0.13.2 (`gpu_logs/setup.log`). The first run of 2026-10-26
used a different instance and torch build, so the two runs are not
bit-for-bit comparable. An earlier instance rented for this rerun stopped
during setup, before any stage ran, and was replaced.

Started at 13:02 UTC with
`RLDEC=0 ABLATIONS="kl0_ep2000 nobc_ep2000" SEEDS="42 1 7" bash java_pipeline/remote.sh start`.
`RLDEC=0` skips RLDec and its environment; `ABLATIONS` runs the listed
ablations side by side after the main pipeline. The preflight check passed:
the environment loads the same cannot-link counts as the fact base
(`gpu_logs/check.log`).

| stage | runs | wall time | source |
|---|---|---|---|
| encoder | 1 (hash d2677ae0aed9) | 621.0 s | `_nesy/encoder/train/run.json` |
| GraphRL-Dec | 144 | 10.5 to 30.5 s per run, 43.9 min in total | `partition.json`, field `seconds` |
| main pipeline, whole | encoder, check, rl, baselines | 54 min 18 s | `gpu_logs/main.log` |
| `nobc_ep2000` | 36 | 12.1 to 62.5 s per run; 18 min 53 s for the stage | `partition.json`; `gpu_logs/run_server.out` |
| `kl0_ep2000` | 36 | 18.6 to 73.2 s per run; 23 min 51 s for the stage | `partition.json`; `gpu_logs/run_server.out` |

Every run exited with code 0. Every main output's config hash matches its
row in `runs_plan.json`. The hash covers the settings, not the input files,
so it is the same as in the run of 2026-10-26 although the fact base and
the triplets differ. Each ablation output's `argv` was checked: 2,000
episodes, KL coefficient 0.0 as the last override, 800 warm-start epochs
for `kl0_ep2000` and 0 for `nobc_ep2000`, and the run's own seed. None
deviates. The ablations change Rails hyperparameters and are reported only
in RESULTS.md section 5.

The encoder took longer than in the first run (621 s against 290 s): it has
5,975 triplets against 3,913 before. The results were packed on the server
(500 MB) and pulled with a checksum check.

After the pull, on the same server, the constraint-repair baselines of
RESULTS.md section 4.1 were built with
`.venv/bin/python -m java_pipeline.repair_baseline` (deterministic, seconds;
`gpu_logs/repair_baseline.log`). Their nine output files were copied back,
and their SHA-256 sums match those printed on the server.

## 2e. Follow-up runs (2026-11-03 to 04)

On the same server, after the rerun, `java_pipeline/run_followup.sh` ran
the follow-up of RESULTS.md section 7, four processes side by side:

| run set | runs | output |
|---|---|---|
| kl0_ep2000, the 6 variants not yet run | 108 (the 36 `structural` and `full` runs existed and were skipped) | `_nesy/rl_ablation/kl0_ep2000/` |
| nesyward (warm start from NeSy-Rep + Ward, paper setting), `structural` and `full` | 36 | `_nesy/rl_ablation/nesyward/` |
| nesyward_kl0_ep2000, `structural` and `full` | 36 | `_nesy/rl_ablation/nesyward_kl0_ep2000/` |
| rule-based repairs of the teacher and of NeSy-Rep + Ward | 18 files, deterministic | `<app>/baselines/repair_*.json` |

Started 22:57:40 UTC, all runs finished with exit code 0 at 23:39:57
(`gpu_logs/followup.out`). The outputs were packed on the server and pulled
with a checksum check (SHA-256 5777b763...). The kl0 setting was chosen
before these runs by `recon/setting_selection.py`, on the apps without
cannot-link pairs.

## 3. Estimated time

These are estimates. Each is derived from a measured time named in the
table, and none is a measurement on the box.

| stage | measured reference | estimate on the box |
|---|---|---|
| encoder | Rails v2 encoder: 621 steps per epoch, 281.9 to 282.4 s per epoch (`v2_full_run_backup/encoder/train/train_log.json`, `epoch_summaries`) | 3,913 Java triplets = 245 steps per epoch, about 110 s per epoch, about 6 min for 3 epochs on a card like the Rails one |
| GraphRL-Dec | Rails v2 stage 7 on CUDA: astuto (N = 64) 14 to 20 s per run, huginn (N = 124) 26 to 34 s per run (`v2_full_run_backup/logs/v2_run.log`, `stage7_rerun.log`) | Java N is 24 to 104, so at most about 34 s per run: about 27 min per seed, about 1.4 h for three seeds |
| RLDec | this machine, CPU only, 3-iteration runs (`results/recon/rldec_cpu_timing/<app>.log`): iteration 0 takes 3 to 4 s, since learning starts after 1,000 steps; iterations 1 and 2 take 193.7 and 194.6 s on jpetstore-6 (N = 24) and 219.3 and 215.6 s on daytrader7 (N = 104) | 19 learning iterations: about 61 to 69 min per app and seed at this CPU speed. The stage runs the six apps in parallel (`--rldec-jobs 6`, one process each, cores shared), so about 70 min per seed and about 3.5 h for three seeds. A GPU may shorten this; that is not measured |

With the two windows of GPU_RUNBOOK.md running side by side, the wall time is
the longer of the two, RLDec: about 3.5 h for three seeds, or about 70 min for seed 42 alone.

## 4. Settings that differ from the Rails runs

Everything not listed here is identical to the Rails v2 runs.

| what | Rails | Java | why |
|---|---|---|---|
| role vocabulary in the node features | 25 Rails role directories (`graph_env._build_role_vocab`) | 16 Java stereotypes (`facts.ROLES`), patched in by `rl_paths.activate` | language specific, as the phase plan asks. The policy input is 786 wide instead of 795, so Java and Rails policies are not weight-compatible, which is expected |
| encoder training set | the 8 Rails apps jointly | the 6 Java apps jointly | language specific |
| z-score peers in the RL reward | v2 teacher, v1 Rails-aware partition, UnixCoder+Ward, UnixCoder+HDBSCAN, random | teacher, UnixCoder+Ward, UnixCoder+HDBSCAN, random | Java has no second resolver to supply the v1 peer, so it is skipped, which `build_peer_metrics` already allows |
| triplets per app | up to 1,500 | the same target; 239 to 1,500 produced (5,975 in all) | the generator fills the cannot-link quota only on the three apps with cannot-link pairs; on the other three it fills the same-role and random quotas, as on Rails astuto (750) |
| cannot-link | namespace pairs, stored as one representative pair per namespace pair | rule CL-SIBLING, explicit pairs: 169 (AcmeAir), 684 (DayTrader), 352 (lit-jpetstore), none elsewhere (FACTS.md, section 2) | Java has no namespace convention; sibling peer packages with no dependency between them play that part |
| software, main env | torch 2.5.1+cu121, transformers 4.45.2, peft 0.13.2 (V2_RERUN_RUNBOOK.md) | torch 2.14.1+cu130 (the server image's), transformers 4.45.2, peft 0.13.2, scikit-learn 1.9.1 (`gpu_logs/setup.log`); the run of 2026-10-26 used torch 2.14.1+cu126 | the image's torch is the build matched to its driver; a newer wheel pulled by the resolver could not see the GPU |
| software, RLDec env | not run in Rails | Python 3.10, torch 2.1.2+cu121, ray 2.9.2, scikit-learn 1.3.2 | decomp-rldec's pins |

## 5. A Rails-side issue that also affects these runs

`neurosymbolic/rl/graph_env.py:685` stores each edge of the incremental
reward tracker as `int(w)`. Weights below 1, such as Paper 1's 1/n fan-out
edges and our J-L1 splits, become 0 in the reward. The final metrics are not
affected, since they use the float graph.

The fraction of G's edge weight the tracker keeps is computed directly from
the graph files:

| graph | weight kept | edges zeroed |
|---|---|---|
| Rails v2, astuto-main | 0.979 | 39 of 233 |
| Rails v2, chatwoot-develop | 0.919 | 707 of 2,025 |
| Rails v2, canvas-lms | 0.922 | 6,295 of 16,991 |
| Java, acmeair | 0.955 | 34 of 264 |
| Java, daytrader7 | 0.996 | 8 of 299 |
| Java, lit-jpetstore | 0.997 | 2 of 219 |
| Java, jpetstore-6, plantsbywebsphere, lit-pbw | 1.000 | 0 |

Source: `results/recon/int_truncation.py` and its `.out` file.

I left the code unchanged. Fixing it would change the Rails runs' reward, and
the Rails pipeline must stay as it is. The Java runs therefore use the same
reward as the Rails runs. Whether to fix it, for both languages, is your
decision.
