"""Choose the RL setting for the Java follow-up runs without looking at the
apps that have cannot-link pairs (RESULTS.md, section 7).

Rule, fixed before the follow-up runs (2026-11-03): among the settings
already run, take the one that scores above the paper setting in the most
(app, convention) cells, counted over the three apps without cannot-link
pairs (jpetstore-6, plantsbywebsphere, lit-pbw), the `structural` and `full`
variants, and every convention in ablation.csv (evaluate, rldec,
weerasinghe). On these apps the paper
setting decodes to the teacher's partition, so the teacher's Score in the
same pool is the paper setting's.

Run from <repo>/:
  python3 results/recon/setting_selection.py > results/recon/setting_selection.out
"""
import csv
from collections import Counter

rows = list(csv.DictReader(open("results/results/ablation.csv")))
apps = ("jpetstore-6", "plantsbywebsphere", "lit-pbw")
wins = Counter()
cells = Counter()
for r in rows:
    if r["app"] not in apps:
        continue
    _, setting, variant = r["ablation_family"].split(":")
    if setting not in ("kl0_ep2000", "nobc_ep2000") or variant not in ("structural", "full"):
        continue
    cells[setting] += 1
    wins[setting] += float(r["Score"]) > float(r["teacher_Score_same_pool"])
    print(f"{r['app']:18s} {r['ablation_family']:34s} {r['convention']:8s} {float(r['Score']):+.3f} vs paper {float(r['teacher_Score_same_pool']):+.3f}")
for s in sorted(cells):
    print(f"{s}: above the paper setting in {wins[s]} of {cells[s]} cells")
best = max(cells, key=lambda s: wins[s])
print(f"selected: {best}" if wins[best] > cells[best] / 2 else "selected: paper setting (no setting wins a majority)")
