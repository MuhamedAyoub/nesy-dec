# GPU runbook: the Java experiments on a rented server

This file covers everything that has to run on a GPU, or benefits from one:
- NeSy-Rep, the encoder fine-tune;
- GraphRL-Dec, the 8 reward variants;
- RLDec;
- the embedding baselines built from the fine-tuned encoder.

Every CPU stage has already run, and its outputs travel in the bundle. That
covers the analysis, resolver, teacher, facts, code index, triplets, the
Sellami export, HierDec and the pretrained-encoder baselines. The run plan,
with a config hash per run, is `results/runs_plan.json`. RUNS.md
summarises it and gives the time estimates: about 3.5 h for three seeds, and
about 70 min for seed 42 alone.

## 1. What to rent

- GPU: one card with at least 16 GB of VRAM. The encoder fine-tune ran out
  of memory on a 6 GB card in the Rails work (GPU_RUNS_TODO.md).
- CPU and RAM: at least 8 cores, ideally 12 or more, and 32 GB. RLDec runs
  six DQN processes at once and is mostly CPU-bound.
- Disk: 30 GB is ample.
- Image: a CUDA 12 PyTorch image with Python 3.10 or 3.11, with SSH and
  internet access. vast.ai's PyTorch template is fine.

## 2. The four commands, from this machine

From `<repo>/`, with HOST and PORT taken from the
vast.ai SSH line (`ssh -p PORT <user>@HOST`):

```bash
bash java_pipeline/remote.sh push   HOST PORT    # build the bundle, upload, check its sha256, unpack in <server>
SMOKE=1 bash java_pipeline/remote.sh start HOST PORT    # optional 5-minute plumbing test (setup runs first, about 10 min)
bash java_pipeline/remote.sh start  HOST PORT    # the real run, detached; survives a dropped SSH session
bash java_pipeline/remote.sh status HOST PORT    # progress, any time
bash java_pipeline/remote.sh pull   HOST PORT    # when status shows "done": fetch, unpack, build the Phase 7 tables
```

For a single seed, use `SEEDS=42 bash java_pipeline/remote.sh start HOST PORT`.
Add seeds 1 and 7 later by starting again with `SEEDS="42 1 7"`. Finished
runs are skipped.

`remote.sh start` calls `java_pipeline/run_server.sh` on the server. That
script:
1. creates the two Python environments on first use (`setup_gpu.sh`);
2. runs the preflight check and stops if it fails;
3. runs the main pipeline (encoder, check, GraphRL-Dec, embedding baselines)
   and RLDec side by side;
4. packs `results_java_gpu.tar.gz` together with all logs.

Its own log is `logs/run_server.out` on the server.

To work on the server directly, use `bash java_pipeline/remote.sh ssh HOST PORT`.
Then `bash java_pipeline/run_server.sh status`, or read `logs/main.log` and
`logs/rldec.log`.

## 3. What the preflight must show

`logs/check.log` ends with `[check] OK`. In each app's line, the
environment's N and must-link count must equal the fact base's:

| app | N | teacher K | triplets | must-link pairs |
|---|---|---|---|---|
| jpetstore-6 | 24 | 4 | 239 | 12 |
| acmeair | 70 | 11 | 750 | 13 |
| daytrader7 | 104 | 11 | 750 | 41 |
| plantsbywebsphere | 35 | 3 | 674 | 38 |
| lit-jpetstore | 71 | 8 | 750 | 44 |
| lit-pbw | 36 | 4 | 750 | 37 |

## 4. After `pull`

The results land in `results/`, and the server logs in
`results/gpu_logs/`. `pull` also runs `python3 -m java_pipeline.results`,
which writes `results/results/*.csv`. RESULTS.md and VERIFICATION.md are
written from those files. You can stop renting the server once `pull` has
finished.

## 5. What can go wrong

- **The preflight fails with MISMATCH.** The environment dropped classes or
  facts. Nothing is trained. Send `logs/check.log` back.
- **PPO never beats the behaviour-cloning start.** The decoded score is then
  the teacher's score for every variant. In the Rails v2 run this happened on
  astuto: all 8 variants decoded to +0.1702
  (`v2_full_run_backup/logs/v2_run.log`). It is a result, not a crash. It will
  be reported as such.
- **An RLDec run fails.** Its log is
  `results/_nesy/rldec_logs/<app>_s<seed>.log`. The other runs carry on.
  Starting again reruns only the missing ones.
- **The encoder runs out of memory.** The card has less than 16 GB. Do not
  lower the batch size without recording it: batch 16 is the Rails setting,
  so changing it is a hyperparameter change.
- **The instance is preempted.** Start again with the same command.
  Everything resumes from the finished runs.
