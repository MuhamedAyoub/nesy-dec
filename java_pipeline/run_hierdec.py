"""Phase 6: run HierDec (static-only HyDec) on our exported Java inputs.

HierDec is run unmodified from the sibling checkout ../decomp-hydec (commit
bc56be4e97f252769d19adead8cab46a9b447f05) with its default hyperparameters
(utils/default_hyperparams.py) and the pipeline [["structural", "semantic"]].
The only input we set is the atom list, so that HierDec partitions exactly
the teacher's class set.

Run it in an environment that satisfies decomp-hydec's requirements
(scikit-learn < 1.4); the setup script for the GPU box creates one, and
locally it is ~/miniconda3/envs/rldec.

HyDec proper is not run: it needs execution traces, and no traces exist for
these subjects.

Usage: python -m java_pipeline.run_hierdec [app ...]
Writes results/<app>/baselines/hierdec.json.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

# decomp-hydec's generated gRPC stubs need protobuf < 4, RLDec needs >= 4.25.
# The stubs are imported but never used on this path (no parsing service is
# called), so the pure-Python protobuf implementation lets both share one env.
os.environ.setdefault("PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION", "python")

REPO = Path(__file__).resolve().parents[1]
HYDEC = Path(os.environ.get("BASELINES_DIR", REPO.parent)) / "decomp-hydec"   # scripts/fetch_baselines.sh
OUT = Path(os.environ.get("JAVA_RESULTS_DIR", REPO / "results"))
sys.path.insert(0, str(HYDEC))
sys.path.insert(0, str(REPO))

APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]


def run(app: str) -> dict:
    import numpy as np
    from hydec.hydec import generate_decomposition

    root = OUT / app / "sellami" / "hierdec"
    names = json.loads((root / "semantic_data" / "class_names.json").read_text())
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        final, layers, atoms, _ = generate_decomposition(
            app, decomp_approach="hierDec", hyperparams_path={"clustering": {"atoms": names}},
            structural_path=str(root / "structural_data"), semantic_path=str(root / "semantic_data"),
            use_parsing_module=False, data_path=tmp)
    labels = np.asarray(final).tolist()
    assert list(atoms) == names, "HierDec reordered the atoms"
    parts: dict[int, list[str]] = {}
    outliers = []
    for n, lab in zip(names, labels):
        (outliers.append(n) if lab == -1 else parts.setdefault(int(lab), []).append(n))
    out = {"method": "hierdec", "app": app, "source": "decomp-hydec@bc56be4", "seconds": round(time.time() - t0, 2),
           "layers": len(layers), "partitions": [parts[k] for k in sorted(parts)], "outliers": outliers,
           "coverage": round(1 - len(outliers) / len(names), 4)}
    d = OUT / app / "baselines"
    d.mkdir(parents=True, exist_ok=True)
    (d / "hierdec.json").write_text(json.dumps(out, indent=2))
    return out


def main(apps: list[str]) -> None:
    for app in apps:
        r = run(app)
        print(f"{app:18s} {len(r['partitions'])} services, sizes {sorted(map(len, r['partitions']), reverse=True)}, "
              f"outliers {len(r['outliers'])}, coverage {r['coverage']}, {r['seconds']}s")


if __name__ == "__main__":
    main(sys.argv[1:] or APPS)
