"""Render the Phase 7 tables from results/results/*.csv.

Every number in results/RESULTS.md comes from here.

Usage: python3 -m java_pipeline.results_tables > results/results_tables.md
"""
from __future__ import annotations

import csv
import json
import statistics as st
from collections import defaultdict

from java_pipeline.audit_tables import table
from java_pipeline.subjects import OUT

RES = OUT / "results"
APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
SHOW = [("teacher", "RoR-MSI clustering (teacher)"), ("graphrl:full", "GraphRL-Dec, full"),
        ("unixcoder_ward_nesyrep", "NeSy-Rep + Ward"), ("unixcoder_ward_pretrained", "UnixCoder + Ward"),
        ("unixcoder_hdbscan_nesyrep", "NeSy-Rep + HDBSCAN"), ("hierdec", "HierDec"),
        ("rldec", "RLDec, CLI decode"), ("rldec_best", "RLDec, best training state"), ("random", "random")]
LABEL = dict(SHOW)


def f2(x: str | float) -> str:
    return f"{float(x):.2f}"


def main() -> None:
    metrics = list(csv.DictReader((RES / "metrics.csv").open()))
    comp = list(csv.DictReader((RES / "composite.csv").open()))
    ext = list(csv.DictReader((RES / "external.csv").open()))

    fam_runs: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in metrics:
        fam_runs[(r["app"], r["family"])].append(r)

    for conv, title in (("evaluate", "on G with evaluate.py's definitions (primary)"),
                        ("rldec", "on G with RLDec's metric code (binarized SM)")):
        print(f"### Table E{1 if conv == 'evaluate' else 2}. Within-pipeline results, {title}\n")
        print("Means over seeds where a method has several runs. Score is Eq. 5 as published "
              "(sample std, divided by 7) within each app's pool of these methods. Coverage is 1.00 for every row.\n")
        for app in APPS:
            sc = {r["family"]: float(r["Score"]) for r in comp
                  if r["app"] == app and r["convention"] == conv and r["eq5"] == "as_published"}
            rows = []
            for fam, label in SHOW:
                rs = fam_runs.get((app, fam))
                if not rs:
                    continue
                m = lambda k: st.mean(float(r[f"{conv}_{k}"]) for r in rs)
                k = st.mean(int(r["num_ms"]) for r in rs)
                rows.append([label, len(rs), f"{k:.1f}".rstrip("0").rstrip("."), f2(m("SM")), f2(m("IFN")),
                             f2(m("ICP")), f2(m("NED")), f"{sc[fam]:+.2f}" if fam in sc else "-"])
            rows.sort(key=lambda r: -float(r[-1]) if r[-1] != "-" else 9)
            print(f"**{app}**\n")
            print(table(["method", "runs", "services", "SM", "IFN", "ICP", "NED", "Score"], rows))
            print()

    print("### Table E3. GraphRL-Dec against its teacher\n")
    rows = []
    for app in APPS:
        teacher = {frozenset(c["classes"]) for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]}
        same = diff = 0
        for p in sorted((OUT / "_nesy" / "rl" / app).glob("*/partition.json")):
            parts = {frozenset(x) for x in json.loads(p.read_text())["partitions"]}
            same, diff = (same + 1, diff) if parts == teacher else (same, diff + 1)
        rows.append([app, same + diff, same, diff])
    print(table(["app", "GraphRL-Dec runs (8 variants x 3 seeds)", "partition identical to the teacher's", "different"], rows))
    print()

    print("### Table E4. Against Weerasinghe et al. 2026, Table 1 (pool of published tools plus ours, Eq. 5 as published)\n")
    print("Rank of each of our rows in the pool; the published rows' metric values are copied from Table 1. "
          "Our rows enter once per convention.\n")
    rows = []
    for app in APPS:
        for conv in ("weerasinghe", "rldec"):
            r = sorted((x for x in ext if x["app"] == app and x["our_convention"] == conv),
                       key=lambda x: -float(x["Score_pool"]))
            rank = {x["row"]: i + 1 for i, x in enumerate(r)}
            best = next(x for x in r if x["row"].startswith("published:"))
            cell = lambda fam: (f"#{rank['ours:' + fam]} ({float(next(x for x in r if x['row'] == 'ours:' + fam)['Score_pool']):+.2f})"
                                if "ours:" + fam in rank else "-")
            rows.append([app, r[0]["benchmark"], r[0]["version_set"], conv, len(r), cell("teacher"), cell("graphrl:full"),
                         cell("unixcoder_ward_nesyrep"), cell("rldec_best"), cell("hierdec"),
                         f"{best['row'].split(':', 1)[1]} #{rank[best['row']]} ({float(best['Score_pool']):+.2f})"])
    print(table(["app", "benchmark", "version set", "our convention", "pool", "teacher", "GraphRL-Dec full",
                 "NeSy-Rep + Ward", "RLDec best", "HierDec", "best published row"], rows))


def ablation() -> None:
    """Table E5, from results/results/ablation.csv (empty until the ablation ran)."""
    path = RES / "ablation.csv"
    if not path.is_file():
        print("(no ablation results yet)")
        return
    rows_in = list(csv.DictReader(path.open()))
    print("### Table E5. GraphRL-Dec ablations (run_gpu.ABLATIONS) in place of GraphRL-Dec full\n")
    print("Each ablation family replaces GraphRL-Dec full in the nine-method pool of Tables E1 and E2; "
          "Score and rank are within that pool. Means over 3 seeds.\n")
    rows = []
    for app in APPS:
        teacher = {frozenset(c["classes"]) for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]}
        # section 5's scope: the two ablations of the paper's question, structural and full;
        # the follow-up families (other kl0 variants, NeSy-Rep warm start) are in followup_report.py
        fams = sorted({r["ablation_family"] for r in rows_in if r["app"] == app
                       and r["ablation_family"].split(":")[1] in ("kl0_ep2000", "nobc_ep2000")
                       and r["ablation_family"].split(":")[2] in ("structural", "full")})
        for fam in fams:
            _, abl, var = fam.split(":")
            same = n = 0
            for p in sorted((OUT / "_nesy" / "rl_ablation" / abl / app).glob(f"{var}_s*/partition.json")):
                n += 1
                same += {frozenset(x) for x in json.loads(p.read_text())["partitions"]} == teacher
            ev = next(r for r in rows_in if r["app"] == app and r["ablation_family"] == fam and r["convention"] == "evaluate")
            rl = next(r for r in rows_in if r["app"] == app and r["ablation_family"] == fam and r["convention"] == "rldec")
            rows.append([app, abl, var, f"{same}/{n}", f2(ev["SM"]), f2(ev["ICP"]), f2(ev["NED"]),
                         f"{float(ev['Score']):+.2f} (#{ev['rank_in_pool']}; teacher {float(ev['teacher_Score_same_pool']):+.2f})",
                         f"{float(rl['Score']):+.2f} (#{rl['rank_in_pool']}; teacher {float(rl['teacher_Score_same_pool']):+.2f})"])
    print(table(["app", "ablation", "variant", "identical to teacher", "SM", "ICP", "NED",
                 "Score, evaluate", "Score, rldec convention"], rows))


if __name__ == "__main__":
    import sys
    ablation() if sys.argv[1:] == ["ablation"] else main()
