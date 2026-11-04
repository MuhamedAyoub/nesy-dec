"""Phase 7: score every decomposition and build the comparison tables.

Every method partitions the same class set: the teacher's active classes (G
without isolated classes). Coverage is reported for every row.

Metric conventions (java_pipeline/metrics.py, RECON.md section 3):
  evaluate     on G, the resolved graph (primary; the Rails papers' metric code)
  weerasinghe  on calls_graph.json, the call evidence only, since Eq. 1-4 are
               defined on calls
  rldec        on G, RLDec's own metric code

Composites (Eq. 5): within each app's pool of our methods, in both the
"as_written" and the "as_published" form. The external table pools our rows
with the rows of Weerasinghe et al. 2026 Table 1, copied from
results/recon/eq5_reproduce.py, and uses "as_published", the only form
that reproduces their Score column. Our rows enter that pool once in the
weerasinghe convention and once in the rldec convention, because the
published rows were computed by several papers' own metric code.

Methods found on disk:
  teacher          results/<app>/exp_a0.9_b0.1_n8_java.json (RoR-MSI clustering)
  teacher_a0.5     results/<app>/exp_a0.5_b0.5_n8_java.json
  hierdec, rldec_s<seed>, unixcoder_{ward,hdbscan}_{pretrained,nesyrep}, random_s<seed>
                   results/<app>/baselines/*.json
  graphrl:<variant>_s<seed>   results/_nesy/rl/<app>/<variant>_s<seed>/partition.json

Usage: python3 -m java_pipeline.results
Writes results/results/{metrics.csv, composite.csv, external.csv, summary.json}.
"""
from __future__ import annotations

import csv
import json
import re
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from java_pipeline import metrics as M
from java_pipeline.subjects import OUT, REPO

sys.path.insert(0, str(OUT / "recon"))
from eq5_reproduce import TABLE1  # noqa: E402

APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
BENCHMARK = {"daytrader7": "DayTrader", "acmeair": "AcmeAir", "lit-jpetstore": "JPetStore",
             "jpetstore-6": "JPetStore", "lit-pbw": "Plants", "plantsbywebsphere": "Plants"}
VERSION_SET = {"daytrader7": "both", "acmeair": "both", "lit-jpetstore": "literature",
               "jpetstore-6": "footnote", "lit-pbw": "literature", "plantsbywebsphere": "footnote"}
# Our rows in the external pool: one per method family, the headline variant
EXTERNAL_METHODS = ("graphrl:full", "teacher", "hierdec", "rldec", "rldec_best", "unixcoder_ward_nesyrep")
# The within-pipeline Eq. 5 pool: one row per distinct method. The other
# GraphRL-Dec variants, the alpha 0.5 teacher and HDBSCAN on pretrained
# embeddings are scored in metrics.csv but kept out of the pool, since
# near-duplicates of one decomposition would weigh it several times in the
# z-scores.
POOL = ("teacher", "graphrl:full", "unixcoder_ward_nesyrep", "unixcoder_ward_pretrained", "unixcoder_hdbscan_nesyrep",
        "hierdec", "rldec", "rldec_best", "random")
RES = OUT / "results"


def partitions(app: str) -> dict[str, list[list[str]]]:
    out = {}
    for tag, f in (("teacher", "exp_a0.9_b0.1_n8_java.json"), ("teacher_a0.5", "exp_a0.5_b0.5_n8_java.json")):
        p = OUT / app / f
        if p.is_file():
            out[tag] = [c["classes"] for c in json.loads(p.read_text())["clusters"]]
    for p in sorted((OUT / app / "baselines").glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("smoke"):
            continue
        out[p.stem] = d["partitions"]
    for p in sorted((OUT / "_nesy" / "rl" / app).glob("*/partition.json")):
        d = json.loads(p.read_text())
        if not d.get("smoke"):
            out[f"graphrl:{p.parent.name}"] = d["partitions"]
    # labelled RL ablations (run_gpu.ABLATIONS); never part of the main pool
    for p in sorted((OUT / "_nesy" / "rl_ablation").glob(f"*/{app}/*/partition.json")):
        if p.parts[-4] == "repro_check":      # a reproducibility rerun (VERIFICATION.md), not an ablation
            continue
        d = json.loads(p.read_text())
        out[f"ablation:{p.parts[-4]}:{p.parent.name}"] = d["partitions"]
    return out


def family(method: str) -> str:
    """rldec_s42 -> rldec, graphrl:full_s7 -> graphrl:full, random_s1 -> random."""
    return re.sub(r"_s\d+$", "", method)


def main() -> None:
    RES.mkdir(parents=True, exist_ok=True)
    rows, by_app = [], {}
    for app in APPS:
        exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
        nodes = sorted(exp["dependency_graph"])
        G = exp["dependency_graph"]
        calls = json.loads((OUT / app / "calls_graph.json").read_text())["dependency_graph"]
        facts = json.loads((OUT / app / "facts_nesy.json").read_text())
        cl_pairs = {tuple(x[:2]) for x in facts["cannot_link"] if x[0] in nodes and x[1] in nodes}
        ml_pairs = {tuple(sorted(x[:2])) for x in facts["must_link"] if x[0] in nodes and x[1] in nodes}
        by_app[app] = {}
        for method, parts in partitions(app).items():
            extra = sorted({c for p in parts for c in p} - set(nodes))
            rec = {"app": app, "method": method, "family": family(method)}
            for conv, graph in (("evaluate", G), ("weerasinghe", calls), ("rldec", G)):
                A, labels, _ = M.from_graph(graph, parts, nodes)
                m = M.compute(A, labels, conv)
                for k in ("SM", "IFN", "ICP", "NED"):
                    rec[f"{conv}_{k}"] = m[k]
                rec["num_ms"], rec["coverage"] = m["num_ms"], m["coverage"]
                # raw composite U of Eq. 9 in the paper, (3 SM - IFN/K - ICP - NED) / 6,
                # the per-method number the Rails tables report
                rec[f"{conv}_U"] = (3 * m["SM"] - m["IFN"] / max(1, m["num_ms"]) - m["ICP"] - m["NED"]) / 6
            rec["classes_outside_class_set"] = len(extra)
            # RQ4: cannot-link pairs placed in one service, and must-link pairs kept together
            of = {c: k for k, p in enumerate(parts) for c in p}
            rec["cannot_link_pairs"] = len(cl_pairs)
            rec["cannot_link_violations"] = sum(1 for x, y in cl_pairs if x in of and y in of and of[x] == of[y])
            rec["must_link_satisfaction"] = (sum(1 for x, y in ml_pairs if x in of and y in of and of[x] == of[y])
                                             / len(ml_pairs)) if ml_pairs else None
            rec["sizes"] = " ".join(map(str, sorted((len(p) for p in parts), reverse=True)))
            rows.append(rec)
            by_app[app][method] = rec
    with (RES / "metrics.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    # within-pipeline composites: one row per method family (seeds averaged)
    comp_rows = []
    for app in APPS:
        fam: dict[str, list[dict]] = defaultdict(list)
        for rec in by_app[app].values():
            fam[rec["family"]].append(rec)
        for conv in ("evaluate", "weerasinghe", "rldec"):
            pool = {f: {k: st.mean(r[f"{conv}_{k}"] for r in rs) for k in ("SM", "IFN", "ICP", "NED")}
                    for f, rs in fam.items() if f in POOL}
            if len(pool) < 3:
                continue
            for form in ("as_written", "as_published"):
                sc = M.eq5_scores(pool, form)
                for f, v in sc.items():
                    comp_rows.append({"app": app, "convention": conv, "eq5": form, "family": f,
                                      "runs": len(fam[f]), **{k: pool[f][k] for k in pool[f]}, "Score": v})
    with (RES / "composite.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(comp_rows[0]))
        w.writeheader()
        w.writerows(comp_rows)

    # ablations: each ablation family takes GraphRL-Dec full's place in the
    # pool, so the pool stays the nine methods and the Score is comparable
    abl_rows = []
    for app in APPS:
        fam: dict[str, list[dict]] = defaultdict(list)
        for rec in by_app[app].values():
            fam[rec["family"]].append(rec)
        for af in sorted(f for f in fam if f.startswith("ablation:")):
            for conv in ("evaluate", "weerasinghe", "rldec"):
                pool = {f: {k: st.mean(r[f"{conv}_{k}"] for r in fam[f]) for k in ("SM", "IFN", "ICP", "NED")}
                        for f in POOL if f in fam and f != "graphrl:full"}
                pool[af] = {k: st.mean(r[f"{conv}_{k}"] for r in fam[af]) for k in ("SM", "IFN", "ICP", "NED")}
                sc = M.eq5_scores(pool, "as_published")
                rank = sorted(pool, key=lambda f: -sc[f])
                abl_rows.append({"app": app, "ablation_family": af, "convention": conv, "runs": len(fam[af]),
                                 **pool[af], "Score": sc[af], "rank_in_pool": rank.index(af) + 1,
                                 "teacher_Score_same_pool": sc["teacher"]})
    if abl_rows:
        with (RES / "ablation.csv").open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(abl_rows[0]))
            w.writeheader()
            w.writerows(abl_rows)

    # external pool: Table 1 rows plus ours, as_published. Our rows in two
    # conventions, since the published rows come from several papers' own
    # metric code: weerasinghe (weighted calls) and rldec (binarized, Sellami's)
    ext = []
    for app, conv in ((a, c) for a in APPS for c in ("weerasinghe", "rldec")):
        bench = BENCHMARK[app]
        pool = {f"published:{t}": dict(zip(("SM", "IFN", "ICP", "NED"), v[:4])) for t, v in TABLE1[bench].items()}
        fam: dict[str, list[dict]] = defaultdict(list)
        for rec in by_app[app].values():
            fam[rec["family"]].append(rec)
        ours = [f for f in EXTERNAL_METHODS if f in fam]
        for f in ours:
            pool[f"ours:{f}"] = {k: st.mean(r[f"{conv}_{k}"] for r in fam[f]) for k in ("SM", "IFN", "ICP", "NED")}
        sc = M.eq5_scores(pool, "as_published")
        for t, v in sc.items():
            ext.append({"app": app, "benchmark": bench, "version_set": VERSION_SET[app], "our_convention": conv, "row": t,
                        **{k: pool[t][k] for k in ("SM", "IFN", "ICP", "NED")}, "Score_pool": v,
                        "Score_published": dict((k, v[4]) for k, v in TABLE1[bench].items()).get(t.split(":", 1)[1])
                        if t.startswith("published:") else None})
    with (RES / "external.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(ext[0]))
        w.writeheader()
        w.writerows(ext)
    (RES / "summary.json").write_text(json.dumps({"methods_per_app": {a: sorted(by_app[a]) for a in APPS}}, indent=2))
    print(f"[results] {len(rows)} method rows, {len(comp_rows)} composite rows, {len(ext)} external rows -> {RES}")


if __name__ == "__main__":
    main()
