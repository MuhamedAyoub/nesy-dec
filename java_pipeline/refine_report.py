"""Score the hill-climb refinement (local_search_dual) against the teacher and
in the published pools.

Within the pipeline, the refinement takes GraphRL-Dec full's place in the
nine-method pool, and its Eq. 5 Score is compared with the teacher's in the
same pool, in all three conventions. Weerasinghe is the held-out one.

Against the published tools, the pool is Weerasinghe Table 1 plus our rows,
as in results.py's external table, with local_search_dual added.

Usage: python3 -m java_pipeline.refine_report > results/refine_report.md
"""
from __future__ import annotations

import csv
import statistics as st
import sys
from collections import defaultdict

from java_pipeline import metrics as M
from java_pipeline.results import APPS, BENCHMARK, POOL, RES
from java_pipeline.subjects import OUT

sys.path.insert(0, str(OUT / "recon"))
from eq5_reproduce import TABLE1  # noqa: E402

OURS_EXT = ("teacher", "local_search_dual", "graphrl:full", "unixcoder_ward_nesyrep", "hierdec", "rldec", "rldec_best")


def main() -> None:
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["app"], r["family"])].append(r)

    def vec(rs, c):
        return {k: st.mean(float(r[f"{c}_{k}"]) for r in rs) for k in ("SM", "IFN", "ICP", "NED")}

    print("### Refinement against the teacher (same nine-method pool)\n")
    print("| app | sizes | evaluate | rldec | weerasinghe (held out) |\n|---|---|---|---|---|")
    for app in APPS:
        cells = []
        for c in ("evaluate", "rldec", "weerasinghe"):
            pool = {f: vec(by[(app, f)], c) for f in POOL if (app, f) in by and f != "graphrl:full"}
            pool["ls"] = vec(by[(app, "local_search_dual")], c)
            sc = M.eq5_scores(pool, "as_published")
            sm_l, sm_t = pool["ls"]["SM"], pool["teacher"]["SM"]
            cells.append(f"{sc['ls']:+.2f} vs {sc['teacher']:+.2f} (SM {sm_l:.2f} vs {sm_t:.2f})")
        print(f"| {app} | {by[(app, 'local_search_dual')][0]['sizes']} | " + " | ".join(cells) + " |")

    print("\n### Rank in the published pools (Weerasinghe Table 1 plus ours)\n")
    print("| app | benchmark | convention | pool | refinement | teacher | top row |\n|---|---|---|---|---|---|---|")
    for app in APPS:
        for c in ("weerasinghe", "rldec"):
            pool = {f"published:{t}": dict(zip(("SM", "IFN", "ICP", "NED"), v[:4])) for t, v in TABLE1[BENCHMARK[app]].items()}
            for f in OURS_EXT:
                pool[f] = vec(by[(app, f)], c)
            sc = M.eq5_scores(pool, "as_published")
            order = sorted(pool, key=lambda k: -sc[k])
            print(f"| {app} | {BENCHMARK[app]} | {c} | {len(pool)} | #{order.index('local_search_dual') + 1} | "
                  f"#{order.index('teacher') + 1} | {order[0]} |")


if __name__ == "__main__":
    main()
