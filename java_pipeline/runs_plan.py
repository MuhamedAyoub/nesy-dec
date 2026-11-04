"""The planned GPU-stage runs with a config hash each, for results/RUNS.md.

A run's hash is the first 12 hex digits of the SHA-256 of its canonical JSON
config (sorted keys), so the same settings always give the same hash and any
change to a hyperparameter changes it.

Usage: python3 -m java_pipeline.runs_plan [--seeds 42 1 7]
Writes results/runs_plan.json.
"""
from __future__ import annotations

import argparse
import json

from java_pipeline.run_gpu import APPS, ENCODER, config_hash as h, encoder_config, rl_config, rldec_config
from java_pipeline.subjects import OUT


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", nargs="+", type=int, default=[42, 1, 7])
    a = ap.parse_args()
    import run_neurosym_ablation as ab
    runs = []
    enc = encoder_config(APPS)
    runs.append({"stage": "encoder", "app": "all six", "seed": ENCODER["seed"], "config_hash": h(enc),
                 "output": "results/_nesy/encoder/train/", "config": enc})
    b0 = {"stage": "b0", "model": "microsoft/unixcoder-base", "max_length": ENCODER["max_length"], "lora": False}
    runs.append({"stage": "b0", "app": "all six", "seed": None, "config_hash": h(b0),
                 "output": "results/_nesy/b0_pretrained/embeddings/", "config": b0})
    for seed in a.seeds:
        for app in APPS:
            for name, extra in ab.VARIANTS.items():
                cfg = rl_config(app, name, seed, extra)
                runs.append({"stage": "rl", "app": app, "variant": name, "seed": seed, "config_hash": h(cfg),
                             "output": f"results/_nesy/rl/{app}/{name.replace('+', '')}_s{seed}/", "config": cfg})
            cfg = rldec_config(app, seed)
            runs.append({"stage": "rldec", "app": app, "seed": seed, "config_hash": h(cfg),
                         "output": f"results/{app}/baselines/rldec_s{seed}.json", "config": cfg})
    (OUT / "runs_plan.json").write_text(json.dumps(runs, indent=2))
    by = {}
    for r in runs:
        by[r["stage"]] = by.get(r["stage"], 0) + 1
    print(f"[runs_plan] {len(runs)} runs {by} -> {OUT / 'runs_plan.json'}")


if __name__ == "__main__":
    main()
