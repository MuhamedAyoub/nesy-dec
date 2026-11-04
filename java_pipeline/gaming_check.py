"""How gameable is the Eq. 5 comparison? Hill-climb (java_pipeline/local_search.py)
from random partitions and rank the results in the published pools.

The starts are three random partitions (seeds 42, 1, 7) with the teacher's K.
No decomposition knowledge enters except the graph that the metrics are
computed on. Each result is ranked in the pool of Weerasinghe Table 1 plus
our rows (as in results.py), in the weerasinghe and rldec conventions. The
last column counts the CL-SIBLING cannot-link pairs (facts_nesy.json) that the
hill-climbed partition places in one service.

Usage: python3 -m java_pipeline.gaming_check > results/gaming_check.md
"""
from __future__ import annotations

import json
import sys

from java_pipeline import metrics as M
from java_pipeline import rl_paths
from java_pipeline.local_search import refine
from java_pipeline.results import APPS, BENCHMARK
from java_pipeline.subjects import OUT

sys.path.insert(0, str(OUT / "recon"))
from eq5_reproduce import TABLE1  # noqa: E402


def main() -> None:
    sys.argv = sys.argv[:1]
    rl_paths.activate()
    from neurosymbolic.rl.eval import _random_partition
    print("### Random partition + hill-climb, ranked in the published pools\n")
    print("| app | benchmark | seed | services | rank, weighted calls | rank, binarized | random alone, weighted | random alone, binarized | cannot-link violations |")
    print("|---|---|---|---|---|---|---|---|---|")
    for app in APPS:
        exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
        names = sorted(exp["dependency_graph"])
        graphs = {"weerasinghe": json.loads((OUT / app / "calls_graph.json").read_text())["dependency_graph"],
                  "rldec": exp["dependency_graph"]}
        cl = {tuple(sorted(x[:2])) for x in json.loads((OUT / app / "facts_nesy.json").read_text())["cannot_link"]}
        for seed in (42, 1, 7):
            start = _random_partition(names, len(exp["clusters"]), seed=seed)
            parts = refine(app, start)["partitions"]
            ranks = []
            for cand in (parts, start):
                for conv in ("weerasinghe", "rldec"):
                    pool = {f"pub:{t}": dict(zip(("SM", "IFN", "ICP", "NED"), v[:4])) for t, v in TABLE1[BENCHMARK[app]].items()}
                    A, lab, _ = M.from_graph(graphs[conv], cand, names)
                    m = M.compute(A, lab, conv)
                    pool["x"] = {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}
                    sc = M.eq5_scores(pool, "as_published")
                    order = sorted(pool, key=lambda k: -sc[k])
                    ranks.append(f"#{order.index('x') + 1} of {len(pool)}")
            of = {c: k for k, p in enumerate(parts) for c in p}
            viol = sum(a in of and of[a] == of.get(b) for a, b in cl)
            print(f"| {app} | {BENCHMARK[app]} | {seed} | {len(parts)} | {ranks[0]} | {ranks[1]} | {ranks[2]} | {ranks[3]} | "
                  f"{f'{viol} of {len(cl)}' if cl else 'no pairs'} |")


if __name__ == "__main__":
    main()
