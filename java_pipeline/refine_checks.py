"""Checks on the hill-climb refinement (java_pipeline/local_search.py) with
measures its objective does not use.

1. Moves. Which classes the refinement moved away from the teacher's
   service, and where to, for manual reading.
2. Independent measures, none of them part of the dual objective:
   - data cohesion: the mean pairwise Jaccard of the data map D within each
     service (RoR-MSI's f_data), averaged over services with at least 2
     classes;
   - entity spread: the mean number of services whose classes touch each
     entity (D); lower means clearer data ownership;
   - semantic cohesion: the mean pairwise cosine of the NeSy-Rep embeddings
     within each service, weighted by size, over services with at least 2
     classes;
   - must-link kept: the share of must-link fact pairs (facts_nesy.json)
     whose two classes share a service.
3. Robustness. The same hill-climb started from UnixCoder+Ward on NeSy-Rep
   embeddings and from random partitions (seeds 42, 1, 7), each scored on the
   held-out weerasinghe convention in the nine-method pool.

Usage: python3 -m java_pipeline.refine_checks > results/refine_checks.md
"""
from __future__ import annotations

import itertools
import json
import statistics as st
import sys

import numpy as np
import torch

from java_pipeline import metrics as M
from java_pipeline import rl_paths
from java_pipeline.local_search import refine
from java_pipeline.results import APPS
from java_pipeline.subjects import OUT


def independent(app: str, parts: list[list[str]]) -> dict:
    D = json.loads((OUT / app / "graph.json").read_text())["data_associations"]
    facts = json.loads((OUT / app / "facts_nesy.json").read_text())
    ck = torch.load(rl_paths.EMBEDDINGS / f"{app}.pt", weights_only=False)
    emb = {n: v / (np.linalg.norm(v) + 1e-12) for n, v in zip(ck["names"], ck["embeddings"].numpy())}
    of = {c: k for k, p in enumerate(parts) for c in p}
    jac, sem_num, sem_den = [], 0.0, 0
    for p in parts:
        if len(p) < 2:
            continue
        pairs = list(itertools.combinations(p, 2))
        js = [len(set(D.get(a, [])) & set(D.get(b, []))) / max(1, len(set(D.get(a, [])) | set(D.get(b, []))))
              for a, b in pairs]
        jac.append(st.mean(js))
        sem_num += len(p) * st.mean(float(emb[a] @ emb[b]) for a, b in pairs)
        sem_den += len(p)
    ents = {e for v in D.values() for e in v}
    spread = [len({of[c] for c, v in D.items() if e in v and c in of}) for e in ents]
    ml = [(a, b) for a, b, *_ in facts["must_link"] if a in of and b in of]
    return {"data_cohesion": st.mean(jac) if jac else 0.0, "entity_spread": st.mean(spread) if spread else 0.0,
            "semantic_cohesion": sem_num / sem_den if sem_den else 0.0,
            "must_link_kept": sum(of[a] == of[b] for a, b in ml) / len(ml) if ml else 0.0}


def held_out(app: str, parts: list[list[str]]) -> float:
    """weerasinghe-convention Score of `parts` in the nine-method pool, in place of GraphRL-Dec full."""
    import csv
    from collections import defaultdict
    from java_pipeline.results import POOL, RES
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by = defaultdict(list)
    for r in rows:
        if r["app"] == app:
            by[r["family"]].append(r)
    pool = {f: {k: st.mean(float(r[f"weerasinghe_{k}"]) for r in by[f]) for k in ("SM", "IFN", "ICP", "NED")}
            for f in POOL if f in by and f != "graphrl:full"}
    exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
    names = sorted(exp["dependency_graph"])
    calls = json.loads((OUT / app / "calls_graph.json").read_text())["dependency_graph"]
    A, lab, _ = M.from_graph(calls, parts, names)
    m = M.compute(A, lab, "weerasinghe")
    pool["x"] = {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}
    sc = M.eq5_scores(pool, "as_published")
    return sc["x"], sc["teacher"]


def main() -> None:
    sys.argv = sys.argv[:1]
    rl_paths.activate()
    from neurosymbolic.rl.eval import _random_partition
    short = lambda n: n.split(".")[-1]
    print("### 1. Classes the refinement moved (teacher service -> refined service, each named by its members)\n")
    for app in ("jpetstore-6", "daytrader7"):
        T = [c["classes"] for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]]
        R = json.loads((OUT / app / "baselines" / "local_search_dual.json").read_text())["partitions"]
        t_of = {c: k for k, p in enumerate(T) for c in p}
        r_of = {c: k for k, p in enumerate(R) for c in p}
        # match each refined service to the teacher service it overlaps most
        match = {k: max(range(len(T)), key=lambda j: len(set(R[k]) & set(T[j]))) for k in range(len(R))}
        moved = [c for c in r_of if match[r_of[c]] != t_of[c]]
        print(f"**{app}**: {len(moved)} classes moved\n")
        for c in sorted(moved, key=lambda c: (r_of[c], c)):
            dest = sorted(short(x) for x in R[r_of[c]] if x != c)[:6]
            src = sorted(short(x) for x in T[t_of[c]] if x != c)[:6]
            print(f"- `{short(c)}`: from the service of {', '.join(src)} to the service of {', '.join(dest)}")
        print()

    print("### 2. Measures outside the objective (teacher -> refined)\n")
    print("| app | data cohesion | entity spread (lower better) | semantic cohesion | must-link kept |\n|---|---|---|---|---|")
    for app in APPS:
        T = [c["classes"] for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]]
        R = json.loads((OUT / app / "baselines" / "local_search_dual.json").read_text())["partitions"]
        a, b = independent(app, T), independent(app, R)
        print(f"| {app} | {a['data_cohesion']:.3f} -> {b['data_cohesion']:.3f} | {a['entity_spread']:.2f} -> {b['entity_spread']:.2f} | "
              f"{a['semantic_cohesion']:.3f} -> {b['semantic_cohesion']:.3f} | {a['must_link_kept']:.2f} -> {b['must_link_kept']:.2f} |")

    print("\n### 3. Hill-climb from other starts (held-out weerasinghe Score in the nine-method pool; teacher's in brackets)\n")
    print("| app | from teacher | from NeSy-Rep + Ward | from random s42 | from random s1 | from random s7 |\n|---|---|---|---|---|---|")
    for app in APPS:
        exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
        K = len(exp["clusters"])
        starts = {"teacher": None,
                  "ward": json.loads((OUT / app / "baselines" / "unixcoder_ward_nesyrep.json").read_text())["partitions"]}
        for s in (42, 1, 7):
            starts[f"random{s}"] = _random_partition(sorted(exp["dependency_graph"]), K, seed=s)
        cells = []
        for name, sp in starts.items():
            r = refine(app, sp)
            x, t = held_out(app, r["partitions"])
            cells.append(f"{x:+.2f} ({t:+.2f}), {r['moves']} moves")
        print(f"| {app} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
