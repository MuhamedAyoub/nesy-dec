"""Phase 6: run RLDec on our exported Java inputs.

RLDec is run unmodified from the sibling checkout ../decomp-rldec (commit
45187548912b324fcaf489c7af6f5172f07833c1) with its CLI defaults: approach
combsequential, 20 training iterations, default_config_CombSequential.json.
Two settings are ours and are written to the run's config file:

  seed      RLDec's default is null; we fix it (RECON.md section 4)
  num_gpus  1 when CUDA is available, else 0 (the default is 1)

The decomposition is RLDec's own decompose step: one greedy episode with the
"last" selection strategy, its CLI defaults.

Needs Python 3.10 with decomp-rldec's requirements (ray[rllib] 2.9.2); the
GPU-box setup script creates that environment, locally ~/miniconda3/envs/rldec.

Usage: python -m java_pipeline.run_rldec [--seed 42] [app ...]
Writes results/<app>/baselines/rldec_s<seed>.json and the trained model
under results/<app>/baselines/rldec_models/.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RLDEC = Path(os.environ.get("BASELINES_DIR", REPO.parent)) / "decomp-rldec"   # scripts/fetch_baselines.sh
OUT = Path(os.environ.get("JAVA_RESULTS_DIR", REPO / "results"))
sys.path.insert(0, str(RLDEC))

APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
ITERATIONS = 20


def run(app: str, seed: int, iterations: int = ITERATIONS) -> dict:
    import torch
    from rldec.decompose import generate_decomposition
    from rldec.train_model import train_model

    base = OUT / app / "baselines"
    models = base / "rldec_models"
    models.mkdir(parents=True, exist_ok=True)
    cfg = {"seed": seed, "num_gpus": 1 if torch.cuda.is_available() else 0}
    cfg_path = models / f"config_s{seed}.json"
    cfg_path.write_text(json.dumps(cfg, indent=2))
    smoke = iterations != ITERATIONS
    name = f"rldec_combsequential_s{seed}" + ("_smoke" if smoke else "")
    t0 = time.time()
    train_model(app, "combsequential", n_iterations=iterations, config_path=str(cfg_path),
                data_path=str(OUT / app / "sellami" / "rldec"), output_path=str(models),
                model_name=name, data_format="csv")
    train_s = time.time() - t0
    parts = generate_decomposition(app, str(models), name, verbose=False, num_episodes=1, select_strategy="last")
    out = {"method": "rldec", "app": app, "source": "decomp-rldec@4518754", "approach": "combsequential",
           "iterations": iterations, "smoke": smoke, "seed": seed, "num_gpus": cfg["num_gpus"], "train_seconds": round(train_s, 1),
           "partitions": [sorted(v) for k, v in sorted(parts.items()) if not k.endswith("_-1")],
           "outliers": sorted(parts.get("partition_-1", []))}
    (base / f"rldec_s{seed}{'_smoke' if smoke else ''}.json").write_text(json.dumps(out, indent=2))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("apps", nargs="*", default=APPS)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--iterations", type=int, default=ITERATIONS,
                    help="anything but the default 20 is a smoke test and is labelled as one")
    a = ap.parse_args()
    for app in a.apps:
        r = run(app, a.seed, a.iterations)
        print(f"{app:18s} {len(r['partitions'])} services, sizes {sorted(map(len, r['partitions']), reverse=True)}, "
              f"outliers {len(r['outliers'])}, train {r['train_seconds']}s")


if __name__ == "__main__":
    main()
