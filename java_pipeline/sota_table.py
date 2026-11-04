"""One table per benchmark: every published tool of Weerasinghe et al. 2026
Table 1 (values copied exactly), plus GraphRL-Dec full only (mean of 3
seeds). Eq. 5 as published is recomputed over that pool; our row is scored
on weighted calls, and its rank with binarized SM is given below each table.
JPetStore and Plants use the literature versions.

Usage: python3 -m java_pipeline.sota_table > results/results/sota_graphrl_only.md
"""
import csv
import statistics as st
import sys

from java_pipeline import metrics as M
from java_pipeline.subjects import OUT

sys.path.insert(0, str(OUT / "recon"))
from eq5_reproduce import TABLE1  # noqa: E402

K = ("SM", "IFN", "ICP", "NED")
OURS = "GraphRL-Dec full (ours)"
rows = [r for r in csv.DictReader((OUT / "results" / "metrics.csv").open()) if r["family"] == "graphrl:full"]
for app, bench in [("daytrader7", "DayTrader"), ("acmeair", "AcmeAir"), ("lit-jpetstore", "JPetStore"), ("lit-pbw", "Plants")]:
    rs = [r for r in rows if r["app"] == app]
    ours = {c: {k: st.mean(float(r[f"{c}_{k}"]) for r in rs) for k in K} for c in ("weerasinghe", "rldec")}
    res = {}
    for c in ours:
        pool = {t: dict(zip(K, v[:4])) for t, v in TABLE1[bench].items()}
        pool[OURS] = ours[c]
        s = M.eq5_scores(pool, "as_published")
        res[c] = (s, sorted(pool, key=lambda k: -s[k]), pool)
    s, order, pool = res["weerasinghe"]
    print(f"\n### {bench} ({app})\n\n| rank | method | SM | IFN | ICP | NED | Score |\n|---|---|---|---|---|---|---|")
    for i, t in enumerate(order):
        v = pool[t]
        print(f"| {i + 1} | {'**' + t + '**' if t == OURS else t} | {v['SM']:.2f} | {v['IFN']:.2f} | {v['ICP']:.2f} | {v['NED']:.2f} | {s[t]:+.2f} |")
    sb, ob, _ = res["rldec"]
    print(f"\nWith binarized SM our row is SM {ours['rldec']['SM']:.2f}, ICP {ours['rldec']['ICP']:.2f}: rank "
          f"#{ob.index(OURS) + 1} of {len(ob)} (Score {sb[OURS]:+.2f}); first is {ob[0]} ({sb[ob[0]]:+.2f}).")
