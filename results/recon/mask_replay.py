"""Replay the greedy decode of every GraphRL-Dec run on the apps with
cannot-link pairs, and check the action mask at every step (RESULTS.md,
section 4).

The mask can admit a violation only through its fallback: when every
service is forbidden for the current class (by cannot-link or by the size
cap) and there is no outlier slot, legal_actions() makes every service legal.
For each run this script counts:
  steps     decode steps
  fallback  steps where that fallback fired
  illegal   steps where the policy's argmax was not a legal action
and checks that the replayed partition equals the reported partition.json,
and counts cannot-link violations in it.

The decode's argmax depends on the torch build: the same checkpoint can give a
different partition under another torch version, because near-tied logits
flip. The runs were decoded on the server with torch 2.14.1, so replay with
that version (the CPU build reproduces every reported partition):
  uv venv -p 3.10 venv214 && uv pip install --python venv214/bin/python \
      torch==2.14.1 numpy scipy scikit-learn --index-url https://download.pytorch.org/whl/cpu
Run from <repo>/:
  venv214/bin/python results/recon/mask_replay.py > results/recon/mask_replay.out
"""
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import torch  # noqa: E402

from java_pipeline import rl_paths  # noqa: E402

rl_paths.activate()
from neurosymbolic.rl import graph_env  # noqa: E402
from java_pipeline.run_gpu import decode  # noqa: E402

COUNT = {"steps": 0, "fallback": 0, "illegal": 0}
ENV_CLS = next(c for c in vars(graph_env).values() if isinstance(c, type) and hasattr(c, "legal_actions"))
_orig_legal, _orig_step = ENV_CLS.legal_actions, ENV_CLS.step


def legal_actions(self):
    mask = _orig_legal(self)
    node = self.current_node
    forbidden = {c for j, c in enumerate(self.assignments) if c >= 0 and j in self._cannot_partners[node]}
    if self._size_cap is not None:
        forbidden |= {k for k in range(self.K) if 0 < self._util.size[k] >= self._size_cap}
    if len(mask) == self.K and all(k in forbidden for k in range(self.K)):
        self._fallback_now = True
    else:
        self._fallback_now = False
    return mask


def step(self, action):
    COUNT["steps"] += 1
    legal = _orig_legal(self)
    COUNT["illegal"] += not bool(legal[action])
    self.legal_actions()
    COUNT["fallback"] += bool(getattr(self, "_fallback_now", False))
    return _orig_step(self, action)


ENV_CLS.legal_actions, ENV_CLS.step = legal_actions, step

OUT = "results"
device = "cpu"
print(f"torch {torch.__version__}, device {device}")
total = {"runs": 0, "steps": 0, "fallback": 0, "illegal": 0, "violations": 0, "mismatch": 0}
for pattern in ("_nesy/rl/{a}/*", "_nesy/rl_ablation/kl0_ep2000/{a}/*", "_nesy/rl_ablation/nobc_ep2000/{a}/*",
                "_nesy/rl_ablation/nesyward/{a}/*", "_nesy/rl_ablation/nesyward_kl0_ep2000/{a}/*"):
    for app in ("acmeair", "daytrader7", "lit-jpetstore"):
        cl = {tuple(sorted(x[:2])) for x in json.load(open(f"{OUT}/{app}/facts_nesy.json"))["cannot_link"]}
        for run in sorted(glob.glob(f"{OUT}/" + pattern.format(a=app))):
            for k in COUNT:
                COUNT[k] = 0
            parts = decode(app, Path(run) / "policy_best.pt", device)
            reported = json.load(open(f"{run}/partition.json"))["partitions"]
            same = {frozenset(p) for p in parts} == {frozenset(p) for p in reported}
            of = {c: i for i, p in enumerate(parts) for c in p}
            viol = sum(a in of and b in of and of[a] == of[b] for a, b in cl)
            print(f"{run[len(OUT) + 7:]:55s} steps {COUNT['steps']:4d}  fallback {COUNT['fallback']}  "
                  f"illegal {COUNT['illegal']}  violations {viol}  matches partition.json {same}")
            total["runs"] += 1
            total["mismatch"] += not same
            total["violations"] += viol
            for k in ("steps", "fallback", "illegal"):
                total[k] += COUNT[k]
print("TOTAL", json.dumps(total))
