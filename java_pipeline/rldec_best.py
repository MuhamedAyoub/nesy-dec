"""RLDec's best training state, as a second RLDec row beside its CLI decode.

RLDec's greedy decode (decompose CLI defaults: one episode, explore off)
returned a single service for every app and seed. During training, RLDec's
own MonitoringCallback records, per episode, the state with the best score by
RLDec's own reward (decomp-rldec/rldec/callbacks.py:116-150, written to
episode_results.json). This script takes, for each run, the state with the
highest best_score over all training episodes. The selection uses RLDec's
reward only, never our metrics.

Usage: python3 -m java_pipeline.rldec_best
Writes results/<app>/baselines/rldec_best_s<seed>.json.
"""
from __future__ import annotations

import json
from pathlib import Path

from java_pipeline.subjects import OUT

APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]


def main() -> None:
    for app in APPS:
        for run in sorted((OUT / app / "baselines" / "rldec_models" / app).glob("rldec_combsequential_s*")):
            if run.name.endswith("_smoke"):
                continue
            seed = int(run.name.rsplit("_s", 1)[1])
            atoms = json.loads((run / "env_config.json").read_text())["atoms"]
            eps = json.loads((run / "episode_results.json").read_text())
            best = max(eps, key=lambda e: e["best_score"])
            parts: dict[int, list[str]] = {}
            for name, lab in zip(atoms, best["best_state"]):
                parts.setdefault(int(lab), []).append(name)
            out = {"method": "rldec_best", "app": app, "seed": seed, "source": "decomp-rldec@4518754",
                   "selection": "max best_score over training episodes (RLDec's own reward)",
                   "episode": best["episode_number"], "episodes": len(eps), "rldec_score": best["best_score"],
                   "partitions": [sorted(parts[k]) for k in sorted(parts)], "outliers": []}
            (OUT / app / "baselines" / f"rldec_best_s{seed}.json").write_text(json.dumps(out, indent=2))
            print(f"{app:18s} s{seed}: episode {best['episode_number']}/{len(eps)}, {len(parts)} services, "
                  f"sizes {sorted(map(len, parts.values()), reverse=True)[:8]}")


if __name__ == "__main__":
    main()
