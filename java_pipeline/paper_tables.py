"""The Java numbers in the formats of the ICSA paper (paper2_icsa2027_v3), so
the paper can copy them rather than recompute them.

  J1  subjects (the analogue of Table I)
  J2  decomposition quality, raw composite U (the analogue of Table III):
      evaluate.py's definitions on G, one row per method, max |m| = largest service
  J3  GraphRL-Dec against its teacher: identical partitions, and the ablations
  J4  must-link satisfaction (the analogue of Table V, right half)
  J5  cannot-link violations, rule CL-SIBLING (the analogue of Table V, left half; RQ4)

Every value is read from results/ (results/*.csv, the partitions and the
fact bases).

Usage: python3 -m java_pipeline.paper_tables > results/paper_tables.md
"""
from __future__ import annotations

import csv
import glob
import json
import statistics as st
from collections import defaultdict

from java_pipeline.results import APPS
from java_pipeline.subjects import OUT

RES = OUT / "results"
METHODS = [("graphrl:full", "GraphRL-Dec"), ("teacher", "RoR-MSI"), ("unixcoder_ward_nesyrep", "UnixCoder+Ward")]
LABEL = {"jpetstore-6": "JPetStore 6", "acmeair": "AcmeAir", "daytrader7": "DayTrader 7",
         "plantsbywebsphere": "Plants", "lit-jpetstore": "JPetStore (lit.)", "lit-pbw": "Plants (lit.)"}


def main() -> None:
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by = defaultdict(list)
    for r in rows:
        by[(r["app"], r["family"])].append(r)

    print("### J1. Java subjects\n\n| system | version set | classes | services K (RoR-MSI) | must-link | cannot-link |\n|---|---|---|---|---|---|")
    vs = {"daytrader7": "both", "acmeair": "both", "lit-jpetstore": "literature", "jpetstore-6": "footnote",
          "lit-pbw": "literature", "plantsbywebsphere": "footnote"}
    for a in APPS:
        exp = json.loads((OUT / a / "exp_a0.9_b0.1_n8_java.json").read_text())
        f = json.loads((OUT / a / "facts_nesy.json").read_text())
        active = set(exp["dependency_graph"])
        ml = {tuple(sorted(x[:2])) for x in f["must_link"] if x[0] in active and x[1] in active}
        print(f"| {LABEL[a]} | {vs[a]} | {len(active)} | {len(exp['clusters'])} | {len(ml)} | {len(f['cannot_link'])} |")

    print("\n### J2. Decomposition quality on the resolved graph (evaluate.py), raw composite U; GraphRL-Dec is the mean of 3 seeds\n")
    print("| system | method | SM | IFN | ICP | NED | U | max |m| |\n|---|---|---|---|---|---|---|---|")
    for a in APPS:
        for fam, lab in METHODS:
            rs = by[(a, fam)]
            m = lambda k: st.mean(float(r[f"evaluate_{k}"]) for r in rs)
            big = st.mean(max(int(s) for s in r["sizes"].split()) for r in rs)
            print(f"| {LABEL[a]} | {lab} | {m('SM'):.3f} | {m('IFN'):.2f} | {m('ICP'):.3f} | {m('NED'):.3f} | {m('U'):+.3f} | {big:.0f} |")

    print("\n### J3. GraphRL-Dec runs whose partition equals the teacher's, per setting (6 apps x 3 seeds unless noted)\n")
    print("| setting | runs | identical to teacher |\n|---|---|---|")
    teach = {a: {frozenset(c["classes"]) for c in json.loads((OUT / a / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]}
             for a in APPS}
    for label, pattern in (("main sweep, all 8 variants (paper settings)", "_nesy/rl/{a}/*/partition.json"),
                           ("no KL anchor, 2,000 episodes (structural, full)", "_nesy/rl_ablation/kl0_ep2000/{a}/*/partition.json"),
                           ("no behaviour-cloning warm start (structural, full)", "_nesy/rl_ablation/nobc_ep2000/{a}/*/partition.json")):
        n = same = 0
        for a in APPS:
            for p in glob.glob(str(OUT / pattern.format(a=a))):
                if "rl_ablation" in p and p.split("/")[-2].rsplit("_s", 1)[0] not in ("structural", "full"):
                    continue          # J3's scope; the other kl0 variants are in followup.md
                n += 1
                same += {frozenset(x) for x in json.loads(open(p).read())["partitions"]} == teach[a]
        print(f"| {label} | {n} | {same} |")

    print("\n### J4. Must-link satisfaction (share of must-link pairs placed in one service)\n")
    print("| system | must-link pairs | GraphRL-Dec | RoR-MSI | UnixCoder+Ward |\n|---|---|---|---|---|")
    for a in APPS:
        f = json.loads((OUT / a / "facts_nesy.json").read_text())
        exp = json.loads((OUT / a / "exp_a0.9_b0.1_n8_java.json").read_text())
        active = set(exp["dependency_graph"])
        ml = {tuple(sorted(x[:2])) for x in f["must_link"] if x[0] in active and x[1] in active}
        cells = []
        for fam, _ in METHODS:
            sats = []
            paths = (glob.glob(str(OUT / f"_nesy/rl/{a}/full_s*/partition.json")) if fam == "graphrl:full" else
                     [None])
            for p in paths:
                parts = (json.loads(open(p).read())["partitions"] if p else
                         [c["classes"] for c in exp["clusters"]] if fam == "teacher" else
                         json.loads((OUT / a / "baselines" / f"{fam}.json").read_text())["partitions"])
                of = {c: k for k, pt in enumerate(parts) for c in pt}
                sats.append(sum(of.get(x) == of.get(y) and x in of for x, y in ml) / len(ml) if ml else 0.0)
            cells.append(f"{st.mean(sats):.3f}")
        print(f"| {LABEL[a]} | {len(ml)} | " + " | ".join(cells) + " |")

    print("\n### J5. Cannot-link violations (pairs of rule CL-SIBLING placed in one service; mean over seeds where a method has several)\n")
    J5 = [("graphrl:full", "GraphRL-Dec"), ("teacher", "RoR-MSI"), ("unixcoder_ward_nesyrep", "UnixCoder+Ward (NeSy-Rep)"),
          ("unixcoder_ward_pretrained", "UnixCoder+Ward (pretrained)"), ("hierdec", "HierDec"),
          ("rldec_best", "RLDec (best state)"), ("rldec", "RLDec (CLI)")]
    print("| system | cannot-link pairs | " + " | ".join(l for _, l in J5) + " |\n|---|---|" + "---|" * len(J5))
    for a in APPS:
        rs0 = by[(a, "teacher")]
        if not rs0 or rs0[0]["cannot_link_pairs"] == "0":
            continue
        cells = []
        for fam, _ in J5:
            v = [float(r["cannot_link_violations"]) for r in by[(a, fam)]]
            cells.append(f"{st.mean(v):.0f}" if len(set(v)) <= 1 else f"{st.mean(v):.1f} ({min(v):.0f} to {max(v):.0f})")
        print(f"| {LABEL[a]} | {rs0[0]['cannot_link_pairs']} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
