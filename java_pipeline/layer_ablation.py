"""Which resolver layers make the decomposition better?

The RoR-MSI teacher (java_pipeline/teacher.rb, alpha 0.9) is run on graphs
built from subsets of the resolver's edges (results/<app>/resolver/edges.jsonl):

  naive      the Phase 2 graph: declared receiver types only, no data map
  calls      J-L0 call, creation and method-reference edges plus J-L1 and
             J-L2 (calls_graph.json); no data map
  no_JT      everything except the type-use layer J-T
  no_L3      everything except the conventions oracle J-L3; the data map D
             comes only from J-L3, so it is empty here
  full       G as used everywhere else

Every partition is scored on the same reference graphs as RESULTS.md: G
under the evaluate and rldec conventions, calls_graph.json under
weerasinghe. A class that a variant leaves isolated, and that the teacher
therefore never assigns, is scored as a singleton service, so that dropping
classes cannot improve a variant's metrics.

Usage: python3 -m java_pipeline.layer_ablation
Writes results/<app>/layer_ablation/<variant>.json and
results/results/layer_ablation.csv.
"""
from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from pathlib import Path

from java_pipeline import metrics as M
from java_pipeline.results import APPS
from java_pipeline.subjects import OUT, REPO

CALL_RULES = {"call_declared", "call_inherited", "call_abstraction", "creation", "anon_impl", "method_ref",
              "cha", "spring_xml_property", "jndi_ejb", "spring_getbean"}
VARIANTS = ("naive", "calls", "no_JT", "no_L3", "full")


def variant_graph(app: str, variant: str) -> dict:
    G = json.loads((OUT / app / "graph.json").read_text())
    nodes = list(G["dependency_graph"])
    if variant == "full":
        return {"dependency_graph": G["dependency_graph"], "data_associations": G["data_associations"]}
    if variant == "naive":
        g = json.loads((OUT / app / "naive_graph.json").read_text())["dependency_graph"]
        return {"dependency_graph": {n: g.get(n, {}) for n in nodes}, "data_associations": {n: [] for n in nodes}}
    keep = {"calls": lambda e: e["rule"] in CALL_RULES,
            "no_JT": lambda e: e["layer"] != "J-T",
            "no_L3": lambda e: e["layer"] != "J-L3"}[variant]
    g: dict[str, dict[str, float]] = {n: defaultdict(float) for n in nodes}
    for line in (OUT / app / "resolver" / "edges.jsonl").read_text().splitlines():
        e = json.loads(line)
        if keep(e):
            g[e["src"]][e["dst"]] += e["w"]
    # D is filled only by J-L3, so variants without J-L3 have no data map
    D = {n: [] for n in nodes} if variant in ("calls", "no_L3") else G["data_associations"]
    return {"dependency_graph": {n: {d: round(w, 4) for d, w in es.items()} for n, es in g.items()},
            "data_associations": D}


def main() -> None:
    rows = []
    for app in APPS:
        d = OUT / app / "layer_ablation"
        d.mkdir(parents=True, exist_ok=True)
        exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
        ref_nodes = sorted(exp["dependency_graph"])
        G = exp["dependency_graph"]
        calls = json.loads((OUT / app / "calls_graph.json").read_text())["dependency_graph"]
        pool = {conv: {} for conv in ("evaluate", "rldec", "weerasinghe")}
        recs = {}
        for v in VARIANTS:
            inp = d / f"{v}_graph.json"
            inp.write_text(json.dumps(variant_graph(app, v)))
            out = d / f"{v}.json"
            subprocess.run(["ruby", str(REPO / "java_pipeline" / "teacher.rb"), str(inp), str(out), "0.9", "0.1"],
                           check=True, capture_output=True)
            parts = [c["classes"] for c in json.loads(out.read_text())["clusters"]]
            covered = {c for p in parts for c in p}
            missing = [n for n in ref_nodes if n not in covered]
            full_parts = [p for p in parts] + [[n] for n in missing]
            rec = {"app": app, "variant": v, "services": len(parts), "unassigned_as_singletons": len(missing)}
            for conv, graph in (("evaluate", G), ("rldec", G), ("weerasinghe", calls)):
                A, labels, _ = M.from_graph(graph, full_parts, ref_nodes)
                m = M.compute(A, labels, conv)
                for k in ("SM", "IFN", "ICP", "NED"):
                    rec[f"{conv}_{k}"] = m[k]
                pool[conv][v] = {k: m[k] for k in ("SM", "IFN", "ICP", "NED")}
            recs[v] = rec
        for conv in pool:
            sc = M.eq5_scores(pool[conv], "as_published")
            for v in VARIANTS:
                recs[v][f"{conv}_Score"] = sc[v]
        rows += [recs[v] for v in VARIANTS]
    with (OUT / "results" / "layer_ablation.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    for r in rows:
        print(f"{r['app']:18s} {r['variant']:7s} services {r['services']:3d} +{r['unassigned_as_singletons']:2d} singletons | "
              + " | ".join(f"{c} SM {r[c + '_SM']:.2f} ICP {r[c + '_ICP']:.2f} NED {r[c + '_NED']:.2f} S {r[c + '_Score']:+.2f}"
                           for c in ("evaluate", "rldec", "weerasinghe")))


if __name__ == "__main__":
    main()
