"""Binarized SM (rldec convention) of the hill-climb partitions with and
without self-edges for classes that call their own methods, plus graph and
service densities. For OPTIMIZATION.md section 3.
Usage (from <repo>/): python3 results/recon/binarized_selfcalls.py > results/recon/binarized_selfcalls.out"""
import json
import statistics as st
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from java_pipeline import metrics as M  # noqa: E402
from java_pipeline.audit import Hierarchy, classify, load  # noqa: E402

for app in ("lit-jpetstore", "daytrader7", "acmeair", "lit-pbw"):
    exp = json.loads((REPO / f"results/{app}/exp_a0.9_b0.1_n8_java.json").read_text())
    names = sorted(exp["dependency_graph"])
    parts = json.loads((REPO / f"results/{app}/baselines/local_search_dual.json").read_text())["partitions"]
    A, lab, _ = M.from_graph(exp["dependency_graph"], parts, names)
    B = (A > 0).astype(float)
    dens = [B[np.ix_(np.where(lab == k)[0], np.where(lab == k)[0])].sum() / (lab == k).sum() ** 2 for k in range(lab.max() + 1)]
    inv, calls, _, _ = load(app)
    h = Hierarchy(inv)
    selfc = {c["owner"] for c in calls if c["owner"] in h.types and classify(c, h)[0] == "self"}
    A2 = A.copy()
    for n in selfc & set(names):
        A2[names.index(n), names.index(n)] = 1
    print(f"{app:14s} graph density {B.sum() / len(names) ** 2:.3f}  mean service size {len(names) / (lab.max() + 1):.1f}  "
          f"mean intra-service density {st.mean(dens):.3f}  binarized SM {M.compute(A, lab, 'rldec')['SM']:.2f} -> "
          f"{M.compute(A2, lab, 'rldec')['SM']:.2f} with self-calls ({len(selfc & set(names))} classes)")
