# NeSy-Dec on Java: replication package

This is the replication package of the paper *Hard Constraints in the Action
Space* (ICSA 2027 submission). It contains:

- **The Java front end.** `java_analyzer/` is a JavaParser-based fact
  extractor. `java_pipeline/` holds the layered call-site resolver (J-L0 to
  J-L2), the symbolic fact base (must-link, cannot-link rule CL-SIBLING,
  soft affinities, roles, framework noise) and the triplet generator.
- **The decomposer.** `neurosymbolic/` and `run_neurosym_ablation.py` hold
  the NeSy-Rep encoder (UnixCoder plus LoRA, trained on fact-derived
  triplets) and GraphRL-Dec, a GraphSAGE and PPO decomposer whose action
  mask forbids placing a class with a cannot-link partner.
  `java_pipeline/rl_paths.py` redirects this stack to the Java artifacts at
  run time, without editing it.
- **Shared code.** The teacher is RoR-MSI's dual-objective clustering, and
  the metrics are RoR-MSI's `evaluate.py`. Both are copied from the RoR-MSI
  artifact into `vendor/ror_msi/` (see its NOTICE).
- **Baselines and analyses.** This covers the comparison with HierDec,
  RLDec and the published pools of Weerasinghe et al. (2026), the
  rule-based repair baseline, the follow-up runs and the gaming check.
- **Results.** `results/` holds every result behind the paper: graphs, fact
  bases, partitions, metrics, tables, logs, provenance notes and the
  evaluation report (`results/report/java_evaluation_report.pdf`).

The model checkpoints are distributed separately; see `ARTIFACTS.md`.

## Requirements

| for | needs |
|---|---|
| levels 1 and 2, tests | Python 3.12 and `requirements.txt` (torch 2.14.1 CPU build, numpy 2.5.4, scipy 1.18.1, scikit-learn 1.9.1, pytest 9.2.0); Ruby ≥ 3.0, standard library only (tested with 3.2.3), for the layer ablation |
| the resolver tests and the CPU stage | JDK 21 (Temurin 21.0.13+9 was used) and Maven 3.9.9 to build `java_analyzer` |
| building the subjects | as listed in `results/SUBJECTS.md`, section 2: Temurin 8u504-b01 for AcmeAir (Gradle wrapper), DayTrader 7 and Plants, Temurin 21 for JPetStore 6 (`./mvnw`) |
| level 3 (retraining) | one CUDA GPU (an RTX 4090 was used) and `requirements-gpu.txt` (transformers 4.45.2, peft 0.13.2); for RLDec and HierDec, a second environment with Python 3.10, torch 2.1.2, ray[rllib] 2.9.2 and scikit-learn 1.3.2 (`java_pipeline/setup_gpu.sh`) |

**The decode depends on the torch build.** The reported GraphRL-Dec
partitions are reproduced exactly only with torch 2.14.1. The server decoded
them with 2.14.1+cu130, and the CPU build of 2.14.1 reproduces all 198
constrained decodes. Decoding the same checkpoints with torch 2.5.1 gives a
different partition in 72 of 108 runs, because near-tied logits flip
(`results/VERIFICATION.md`, section 1). Pin torch as well as the seed.
GraphRL-Dec training is not bit-reproducible across hardware or torch builds.

The other recorded versions come from the server:

| | value | source |
|---|---|---|
| GPU | NVIDIA GeForce RTX 4090, 24,564 MiB, driver 580.142 | `results/gpu_logs/setup.log` |
| main environment | torch 2.14.1+cu130, transformers 4.45.2, peft 0.13.2, scikit-learn 1.9.1 | `results/gpu_logs/setup.log` |
| RLDec environment | Python 3.10, torch 2.1.2+cu121, ray 2.9.2, scikit-learn 1.3.2 | `results/RUNS.md`, section 4 |

## Setup

    python3.12 -m venv .venv && . .venv/bin/activate
    pip install -r requirements.txt
    python -m pytest -q tests                 # see "Tests" below

Optional, only for the CPU stage, the resolver tests and the baselines:

    (cd java_analyzer && mvn -q package)      # builds java_analyzer/target/java-analyzer-0.2.0.jar
    bash scripts/fetch_subjects.sh            # the six Java subjects, into datasets_java/
    bash scripts/fetch_baselines.sh           # decomp-rldec, decomp-hydec, decomp-parsing-service

## Subjects

`scripts/fetch_subjects.sh` clones each subject at the commit in
`results/SUBJECTS.md`, section 2. The source trees are not redistributed.
Only the CPU stage reads them; levels 1 and 2 do not.

| folder in `datasets_java/` | repository | commit |
|---|---|---|
| `jpetstore-6` | https://github.com/mybatis/jpetstore-6 | `ce8015be2c2658d0b657be20328e53045f3a9641` |
| `acmeair` | https://github.com/acmeair/acmeair | `f16122729873ef0449ea276dfb2d2a1d45bebb40` |
| `sample.daytrader7` | https://github.com/WASdev/sample.daytrader7 | `643d04c100f75898003b5c98cde6b5f5015c613a` |
| `sample.plantsbywebsphere` | https://github.com/WASdev/sample.plantsbywebsphere | `bf5f18b0ba120dfe68a91d7e181c06e32ed6f3c4` |
| `KimJongSung__jPetStore` (lit-jpetstore) | https://github.com/KimJongSung/jPetStore | `bc3fe898326e90658e95f27052ce3004b656d975` |
| `SteeleDesmond__sample.mono-to-ms.pbw-monolith` (lit-pbw) | https://github.com/SteeleDesmond/sample.mono-to-ms.pbw-monolith | `e6f2a6a437221c2652b907a709cf0343780013f2` |

The builds that write each subject's `classpath.txt` are in
`results/SUBJECTS.md`, section 2. For the two literature variants, the
classpath comes from the classpath-only poms in `java_pipeline/classpath/`
(`mvn dependency:build-classpath`). Their shipped `classpath.txt` files
point into `~/.m2/repository`.

Two kinds of derived file are not shipped because they embed subject source
code. `java_pipeline.code_index` regenerates both from the fetched subjects:
- `results/<app>/code_index.json`, the method bodies the encoder reads;
- `results/_nesy/inputs/code_index/`.

`results/<app>/audit/sample.jsonl`, the 40-site manual audit sample per
app, and the fact files under `results/<app>/facts/` keep single source
lines and argument expressions, as recorded.

## Reproduction

### Level 1: every table from the shipped results (CPU, no checkpoints)

    bash scripts/reproduce.sh

This takes about a minute. The script copies the repository to a
temporary folder and runs there, so nothing under `results/` is overwritten.
It runs:
- `java_pipeline.results`;
- the layer ablation (re-clustering with the Ruby teacher);
- `results_tables` and `results_tables ablation`;
- `paper_tables`, `followup_report`, `repair_baseline report`,
  `sota_table`, `gaming_check` and `refine_report`;
- `resolver_tables`, `facts_tables` and `audit_tables`;
- the `results/recon/*.py` scripts whose outputs the documents cite.

It then compares each regenerated file byte for byte with the shipped one
and exits with status 1 on any difference.

`SLOW=1` adds `results/refine_checks.md`, which runs several minutes of
hill-climbs. Its section 3 starts some of those hill-climbs from random
partitions, so the cells depend on the library versions. See the
verification notes in the split report.

Not regenerated at level 1:
- `results/idea1_report.md` reads a superseded run that is not released
  (`results/OPTIMIZATION.md`, section 1);
- `results/recon/mask_replay.out` is level 2;
- `results/report/java_evaluation_report.pdf` needs `pdflatex`. Build it
  with `python -m java_pipeline.report_pdf`.

### Level 2: replay every constrained decode (CPU, needs the checkpoints)

    tar xzf nesy-dec-checkpoints.tar.gz       # at the repository root, see ARTIFACTS.md
    bash scripts/replay_decodes.sh

This runs `results/recon/mask_replay.py`. It replays the greedy decode of
the 198 GraphRL-Dec runs on the three apps with cannot-link pairs: the main
run, the two ablations and the two follow-up sets. At every step it checks
the action mask, then compares the output with
`results/recon/mask_replay.out`. Expected last line:

    TOTAL {"runs": 198, "steps": 16170, "fallback": 0, "illegal": 0, "violations": 0, "mismatch": 0}

### Level 3: full retraining (GPU; documented, not needed for review)

Run the CPU stage first (subjects, analyzer jar and baselines fetched), in
this order:
1. `java -jar java_analyzer/target/java-analyzer-0.2.0.jar` per app
   (`python -m java_pipeline.subjects` writes the configs);
2. `python -m java_pipeline.resolver`, then `ruby java_pipeline/teacher.rb`
   at α = 0.9 and 0.5;
3. `python -m java_pipeline.facts`, `code_index`, `triplets` and
   `export_sellami`;
4. `python -m java_pipeline.run_hierdec` in the RLDec environment.

`results/RUNS.md`, section 1 lists these commands with their outputs.

The GPU stages then run with one command on the server. After
`bash java_pipeline/setup_gpu.sh`:

    SEEDS="42 1 7" ABLATIONS="kl0_ep2000 nobc_ep2000" bash java_pipeline/run_server.sh
    # equivalently: python -m java_pipeline.run_gpu --stages b0,encoder,rl,baselines,rldec,pack --seeds 42 1 7
    bash java_pipeline/run_followup.sh           # the follow-up runs (F1 to F3) and the repair baselines
    python -m java_pipeline.results              # then the level-1 generators

`java_pipeline/remote.sh` drives a rented server over SSH (push, start,
status, pull). `results/GPU_RUNBOOK.md` is the runbook.

Measured run times (`results/RUNS.md`, sections 1 and 2c to 2e):

| stage | runs | wall time |
|---|---|---|
| analyzer | 6 apps | 1.4 to 4.0 s per app |
| pretrained UnixCoder bank (B0), CPU | 6 apps | 1 min 45 s |
| NeSy-Rep encoder fine-tune | 1 | 621.0 s (2026-11-03 rerun); 289.9 s in the first run |
| GraphRL-Dec | 144 (6 apps x 8 variants x 3 seeds) | 10.5 to 30.5 s per run, 43.9 min in total |
| main pipeline, whole (encoder, check, rl, baselines) | | 54 min 18 s |
| ablation `nobc_ep2000` | 36 | 18 min 53 s |
| ablation `kl0_ep2000` | 36 | 23 min 51 s |
| follow-up (`run_followup.sh`: 108 + 36 + 36 runs and 18 repairs) | | 42 min 17 s (22:57:40 to 23:39:57 UTC) |
| RLDec | 18, 9 at a time | 3,230 to 3,560 s per run, 1 h 55 min in total |
| HierDec | 6 apps | 0.03 to 0.13 s per app |

## Where each table comes from

Paper tables (current revision of the submission):

| paper | content | produced by | result file |
|---|---|---|---|
| Table `tab:resolver` | call-site resolution and isolated classes, naive graph against G | `python -m java_pipeline.resolver_tables` (Tables R1 and R4) | `results/resolver_tables.md`, from `results/<app>/resolver/provenance.json` |
| Table `tab:cannotlink` | package pairs accepted by CL-SIBLING | `python -m java_pipeline.facts`; table in `results/FACTS.md`, section 2 | `results/<app>/facts_report.json`, `results/FACTS.md` |
| Table `tab:mustlink` | must-link pairs by reason | `python -m java_pipeline.facts_tables` (Table F2) | `results/facts_tables.md` |
| Table `tab:subjects` | commits, N, K, ML, CL | `python -m java_pipeline.paper_tables` (J1); commits from `results/SUBJECTS.md` | `results/paper_tables.md` |
| Table `tab:rq1` | Score within the pool of nine methods | `python -m java_pipeline.results_tables` (Table E1) | `results/results_tables.md`, from `results/results/composite.csv` |
| Table `tab:quality` | GraphRL-Dec raw metrics and ML against the teacher | `python -m java_pipeline.paper_tables` (J2, J4) | `results/paper_tables.md` |
| Table `tab:jsota` | Score in the published pools of Weerasinghe et al. | `python -m java_pipeline.sota_table` | `results/results/sota_graphrl_only.md`, from `results/results/external.csv` |
| Table `tab:cl` | cannot-link violations | `python -m java_pipeline.paper_tables` (J5) | `results/paper_tables.md` |
| Table `tab:repair` | GraphRL-Dec against rule-based repairs | `python -m java_pipeline.repair_baseline report` | `results/repair_baseline.md` |
| Table `tab:gaming` | random partitions before and after a hill-climb | `python -m java_pipeline.gaming_check` | `results/gaming_check.md` |
| Figures 1 to 4 | architecture diagrams | drawn by hand, no data | none |

Tables kept for the revision:

| table | produced by | result file |
|---|---|---|
| J1 Java subjects; J2 decomposition quality (raw U); J3 runs equal to the teacher; J4 must-link satisfaction; J5 cannot-link violations | `python -m java_pipeline.paper_tables` | `results/paper_tables.md` |
| repair baseline | `python -m java_pipeline.repair_baseline report` | `results/repair_baseline.md` |
| F1 the three apps with cannot-link pairs; F2 kl0 against the paper setting; F3 violations of every kl0 and NeSy-Rep-start run | `python -m java_pipeline.followup_report` | `results/followup.md` |
| E1 to E4 | `python -m java_pipeline.results_tables` | `results/results_tables.md` |
| E5 ablations | `python -m java_pipeline.results_tables ablation` | `results/ablation_tables.md` |
| R1 to R5, F1 to F5, A to D | `resolver_tables`, `facts_tables`, `audit_tables` | `results/resolver_tables.md`, `facts_tables.md`, `audit_tables.md` |

All of these run in `scripts/reproduce.sh`.

## Tests

    python -m pytest -q tests

`results/verify/java_tests.out` records 447 passed. Without the analyzer
jar and a JDK at `JDK_HOME` (default `~/.local/opt/jdk-21.0.13+9`), the
resolver tests skip. Without `decomp-rldec` in `$BASELINES_DIR` (default:
the folder containing this repository), the RLDec metric-equivalence tests
skip. The Rails NeSy-Dec tests (`neurosymbolic/tests/`) are not part of this
package, because they read Rails inputs that are not shipped;
`results/verify/rails_tests.out` records their last run.

## Third-party baselines

The baselines are not included. `scripts/fetch_baselines.sh` clones them at
the commits we ran:

| tool | upstream | commit | how we ran it |
|---|---|---|---|
| RLDec | https://github.com/khaledsellami/decomp-rldec | `45187548912b324fcaf489c7af6f5172f07833c1` | `java_pipeline/run_rldec.py` imports `rldec.train_model` and `rldec.decompose` unmodified. Approach `combsequential` with `default_config_CombSequential.json` and the CLI defaults (20 iterations), seeds 42, 1, 7, on the files written by `java_pipeline/export_sellami.py` (`results/<app>/sellami/rldec/`). `java_pipeline/rldec_best.py` also reads the best state of RLDec's own reward. |
| HierDec | https://github.com/khaledsellami/decomp-hydec | `bc56be4e97f252769d19adead8cab46a9b447f05` | `java_pipeline/run_hierdec.py` calls `hydec.hydec.generate_decomposition` unmodified, at its defaults, on `results/<app>/sellami/hierdec/` |
| decomp-parsing-service | https://github.com/khaledsellami/decomp-parsing-service | `84318d712dcafa96fe40cc29bb025441fc5da2d5` | not run. Its TF-IDF transformer is copied into `java_pipeline/vendor/decparsing_tfidf.py` (Apache License 2.0, kept in `java_pipeline/vendor/LICENSE.decomp-parsing-service`), so that our export computes the same features |

The published metric values of the Weerasinghe et al. pools are
transcribed in `results/recon/eq5_reproduce.py` (`TABLE1`).

## Layout and conventions

    java_analyzer/   JavaParser fact extractor (Maven)
    java_pipeline/   resolver, facts, triplets, teacher, runs, tables
    neurosymbolic/   NeSy-Rep encoder and GraphRL-Dec (the parts the Java pipeline uses)
    vendor/ror_msi/  evaluate.py and the clustering engine, from the RoR-MSI artifact
    results/         every result (this was results_java/ in the original tree)
    tests/           unit tests (this was tests_java/)
    scripts/         fetchers, reproduce.sh, replay_decodes.sh

The documents in `results/` were written in the original working tree.
Their paths have been rewritten to this layout (`results_java/` to
`results/`, `tests_java/` to `tests/`, `evaluate.py` to
`vendor/ror_msi/evaluate.py`). The data files (JSON, JSONL, logs) keep the
paths they were written with, except that machine-specific absolute paths
were replaced by placeholders:

| placeholder | stands for |
|---|---|
| `<repo>` | the root of the original working tree (this repository's predecessor) |
| `<subjects>` | the folder holding the fetched subjects (`datasets_java/`) |
| `<baselines>` | the folder holding the decomp-* checkouts |
| `<parent>` | the folder containing the working tree |
| `<server>` | the GPU server, its run directory or its hostname |
| `<user>`, `<port>` | the server's login and SSH port |
| `~` | a home directory |

Some documents also cite material that is not part of this package:
- the Rails pipeline of RoR-MSI and of the Rails NeSy-Dec runs
  (`tools/v2/`, `experiment_v2.rb`, `neurosymbolic/output/`,
  `v2_full_run_backup/`);
- files of the third-party baselines;
- a superseded run under `results/_archive/`, which is not released.

`results/recon/rails_graphs/` holds copies of three RoR-MSI graphs read by
`results/recon/int_truncation.py`.

## License

MIT (`LICENSE`), including `vendor/ror_msi/`. The exception is
`java_pipeline/vendor/decparsing_tfidf.py` and its stopword list, which
come from decomp-parsing-service and stay under the Apache License 2.0.
