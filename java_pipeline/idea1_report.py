"""Idea 1 (dual reward, java_pipeline/dual_reward.py) against the teacher, per seed.

Each run takes GraphRL-Dec full's place in the nine-method pool of RESULTS.md
(Tables E1, E2), and its Eq. 5 Score (as published) is compared with the
teacher's Score in that same pool. The comparison is made in three
conventions:
  evaluate     in the reward (first term)
  rldec        in the reward (second term)
  weerasinghe  in neither: the held-out check

For contrast, the same is reported for the old reward without the anchor
(kl0_ep2000).

Usage: python3 -m java_pipeline.idea1_report > results/idea1_report.md
"""
from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict

from java_pipeline import metrics as M
from java_pipeline.results import APPS, POOL, RES

CONVS = ("evaluate", "rldec", "weerasinghe")
FAMILIES = (("ablation:dual_kl0_ep2000:full", "dual reward, no anchor, full"),
            ("ablation:dual_kl0_ep2000:structural", "dual reward, no anchor, structural"),
            ("ablation:kl0_ep2000:full", "old reward, no anchor, full"),
            ("ablation:kl0_ep2000:structural", "old reward, no anchor, structural"),
            ("ablation:dual_kl05:full", "dual reward, paper's anchor, full"))


def main() -> None:
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["app"], r["family"])].append(r)

    def vec(rs, conv):
        return {k: st.mean(float(r[f"{conv}_{k}"]) for r in rs) for k in ("SM", "IFN", "ICP", "NED")}

    print("### Idea 1: per-seed Score against the teacher (seed runs scored one at a time in the nine-method pool)\n")
    print("Cells: seeds where the run's Score exceeds the teacher's / seeds run; mean Score delta (run minus teacher).\n")
    print("| app | setting | " + " | ".join(CONVS) + " |")
    print("|---|---|" + "---|" * len(CONVS))
    totals = defaultdict(lambda: [0, 0])
    for app in APPS:
        for fam, label in FAMILIES:
            runs = by.get((app, fam), [])
            if not runs:
                continue
            cells = []
            for conv in CONVS:
                wins, deltas = 0, []
                for run in runs:
                    pool = {f: vec(by[(app, f)], conv) for f in POOL if (app, f) in by and f != "graphrl:full"}
                    pool["run"] = vec([run], conv)
                    sc = M.eq5_scores(pool, "as_published")
                    d = sc["run"] - sc["teacher"]
                    deltas.append(d)
                    wins += d > 1e-9
                totals[(fam, conv)][0] += wins
                totals[(fam, conv)][1] += len(runs)
                cells.append(f"{wins}/{len(runs)}; {st.mean(deltas):+.2f}")
            print(f"| {app} | {label} | " + " | ".join(cells) + " |")
    print("\n### Totals over the apps run\n")
    print("| setting | " + " | ".join(CONVS) + " |")
    print("|---|" + "---|" * len(CONVS))
    for fam, label in FAMILIES:
        if any(totals[(fam, c)][1] for c in CONVS):
            print(f"| {label} | " + " | ".join(f"{totals[(fam, c)][0]}/{totals[(fam, c)][1]}" for c in CONVS) + " |")


if __name__ == "__main__":
    main()
