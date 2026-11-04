# Large artifacts

The model checkpoints are too large for the repository and are distributed
as a separate archive. Extract it at the repository root; its paths are the
repository's own, so the files land where the code expects them:

    tar xzf nesy-dec-checkpoints.tar.gz      # creates results/_nesy/... files

Archive link: **[ARCHIVE LINK TO BE ADDED: Zenodo or similar]**

## nesy-dec-checkpoints.tar.gz

| | |
|---|---|
| size | 937,285,962 bytes (894 MiB); 1,020.7 MB extracted |
| SHA-256 | `22a11822a8a24a1f67acea2eae346292f9896182333c207d02efd4e4a134d930` |
| members | 1,166 files |
| needed by | `scripts/replay_decodes.sh` (level 2); also any re-decode or re-embedding |

Contents, by folder:

| folder | files | what |
|---|---|---|
| `results/_nesy/rl/<app>/<variant>_s<seed>/` | 432 (6 apps x 8 variants x 3 seeds x 3 files) | GraphRL-Dec policies of the main run: `policy_bc.pt` (after the warm start), `policy.pt` (last), `policy_best.pt` (the one decoded) |
| `results/_nesy/rl_ablation/kl0_ep2000/` | 432 | ablation and follow-up runs, setting `kl0_ep2000` (8 variants) |
| `results/_nesy/rl_ablation/nobc_ep2000/` | 72 | ablation without warm start (`policy.pt`, `policy_best.pt`; no BC checkpoint) |
| `results/_nesy/rl_ablation/nesyward/` | 108 | follow-up: warm start from NeSy-Rep + Ward |
| `results/_nesy/rl_ablation/nesyward_kl0_ep2000/` | 108 | follow-up: warm start from NeSy-Rep + Ward, setting `kl0_ep2000` |
| `results/_nesy/rl_ablation/repro_check/` | 6 | the reproducibility rerun of RUNS.md, section 2c |
| `results/_nesy/encoder/train/adapter/` | 8 | the NeSy-Rep LoRA adapter (`adapter_model.safetensors`, `adapter_config.json`, a generated model card) and the tokenizer files of the base model `microsoft/unixcoder-base`, saved with it |

`scripts/replay_decodes.sh` reads the 198 `policy_best.pt` files of the
three apps with cannot-link pairs (acmeair, daytrader7, lit-jpetstore) in
`rl/` and in the four `rl_ablation/` run sets other than `repro_check`.
The partitions, training logs and configs of every run are in the
repository itself (`partition.json`, `train_log.json`, `run.json`), so
levels 1 and 3 do not need the archive.

The twelve embedding banks (`results/_nesy/encoder/train/embeddings/*.pt`
and `results/_nesy/b0_pretrained/embeddings/*.pt`, 2.4 MB in all) are in the
repository rather than the archive, because the level-1 table
`results/followup.md` reads them.

## Not archived

| what | size | why |
|---|---|---|
| RLDec trained models: `results/<app>/baselines/rldec_models/<app>/rldec_combsequential_s<seed>/{algorithm_state.pkl, policies/default_policy/policy_state.pkl}`, 18 runs | 36 files, 1,196,884,470 bytes | Not needed by any check here: the RLDec partitions and scores are in `rldec_s<seed>.json` and `rldec_best_s<seed>.json`, and the run metadata (`result.json`, `episode_results.json`, `train_config.json`, `env_config.json`, `rllib_checkpoint.json`, `logs.log`) is in the repository. Rerunning `java_pipeline/run_rldec.py` recreates them (about 1 h per run on CPU, RUNS.md). |
