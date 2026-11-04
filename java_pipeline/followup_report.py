"""Report of the follow-up runs of 2026-11-03 (RESULTS.md, section 7): GraphRL-Dec
with the kl0_ep2000 setting (all 8 variants), GraphRL-Dec warm-started from
NeSy-Rep + Ward, and the rule-based repairs they are compared with.

Every row is scored like refine_report.py and repair_baseline.py do: it
takes GraphRL-Dec full's place in the nine-method pool (results.POOL), so
every row competes against the same eight other methods, and Eq. 5 as
published is computed there, in each convention. A row that is itself one
of the eight (the teacher, NeSy-Rep + Ward) then appears twice in its pool. Means over seeds where a family has
several runs.

Columns:
  violations   cannot-link pairs in one service (metrics.csv)
  must-link    share of must-link pairs kept together (metrics.csv). Every
               GraphRL-Dec variant has a must-link shaping term (lambda 0.1),
               so this is not outside its reward.
  semantic     mean pairwise cosine of the NeSy-Rep embeddings within
               services, weighted by size (refine_checks.independent). Outside
               the reward of `structural` only; the other variants have a
               semantic term.
  evaluate     the reward's own metric family on G
  rldec, weerasinghe   the same family under binarized SM, and on the call
               graph: not the reward's definitions

Usage: python -m java_pipeline.followup_report > results/followup.md   (needs torch, for the embeddings)
"""
from __future__ import annotations

import csv
import json
import statistics as st
from collections import defaultdict

from java_pipeline import metrics as M
from java_pipeline.results import APPS, POOL, RES
from java_pipeline.subjects import OUT

CL_APPS = ["acmeair", "daytrader7", "lit-jpetstore"]
VARIANTS = ["structural", "semantic", "affinity", "noise", "full", "fullC2", "fullC1", "fullC1C2"]
CONV = ("evaluate", "rldec", "weerasinghe")


def main() -> None:
    from java_pipeline.refine_checks import independent
    rows = list(csv.DictReader((RES / "metrics.csv").open()))
    by: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        by[(r["app"], r["family"])].append(r)

    def score(app: str, fam: str, conv: str) -> float:
        pool = {f: {k: st.mean(float(r[f"{conv}_{k}"]) for r in by[(app, f)]) for k in ("SM", "IFN", "ICP", "NED")}
                for f in POOL if f != "graphrl:full"}
        pool["x"] = {k: st.mean(float(r[f"{conv}_{k}"]) for r in by[(app, fam)]) for k in ("SM", "IFN", "ICP", "NED")}
        return M.eq5_scores(pool, "as_published")["x"]

    def parts_of(app: str, fam: str) -> list[list[list[str]]]:
        if fam == "teacher":
            return [[c["classes"] for c in json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]]]
        if fam.startswith("graphrl:"):
            return [json.loads(p.read_text())["partitions"] for p in sorted((OUT / "_nesy" / "rl" / app).glob(f"{fam[8:]}_s*/partition.json"))]
        if fam.startswith("ablation:"):
            _, abl, var = fam.split(":")
            return [json.loads(p.read_text())["partitions"]
                    for p in sorted((OUT / "_nesy" / "rl_ablation" / abl / app).glob(f"{var}_s*/partition.json"))]
        return [json.loads((OUT / app / "baselines" / f"{fam}.json").read_text())["partitions"]]

    sem_cache: dict[tuple[str, str], float] = {}

    def semantic(app: str, fam: str) -> float:
        if (app, fam) not in sem_cache:
            sem_cache[(app, fam)] = st.mean(independent(app, p)["semantic_cohesion"] for p in parts_of(app, fam))
        return sem_cache[(app, fam)]

    def best_repair(app: str, prefix: str) -> str:
        fams = [f"{prefix}_{x}" for x in ("masked", "connect", "post") if by.get((app, f"{prefix}_{x}"))]
        return max(fams, key=lambda f: score(app, f, "evaluate"))

    def line(app: str, fam: str, label: str) -> str:
        rs = by[(app, fam)]
        m = lambda k: st.mean(float(r[k]) for r in rs)
        viol = f"{m('cannot_link_violations'):.0f}" if rs[0]["cannot_link_pairs"] != "0" else "-"
        return (f"| {app} | {label} | {len(rs)} | {viol} | {m('must_link_satisfaction'):.3f} | {semantic(app, fam):.3f} | "
                + " | ".join(f"{score(app, fam, c):+.2f}" for c in CONV) + " |")

    head = ("| app | method | runs | cannot-link violations | must-link kept | semantic cohesion | "
            "Score, evaluate | Score, rldec | Score, weerasinghe |\n|---|---|---|---|---|---|---|---|---|")

    print("### F1. The three apps with cannot-link pairs\n")
    print("`kl0` is the setting chosen by `results/recon/setting_selection.py` (no KL anchor, 2,000 episodes). "
          "The best repair is the one of the three with the highest evaluate Score.\n")
    print(head)
    for app in CL_APPS:
        rt, rn = best_repair(app, "repair"), best_repair(app, "repair_nesyward")
        for fam, lab in (("teacher", "RoR-MSI teacher"),
                         ("graphrl:full", "GraphRL-Dec full, paper setting"),
                         (rt, f"best repair of the teacher ({rt})"),
                         ("ablation:kl0_ep2000:full", "GraphRL-Dec full, kl0"),
                         ("ablation:kl0_ep2000:structural", "GraphRL-Dec structural, kl0"),
                         ("unixcoder_ward_nesyrep", "NeSy-Rep + Ward"),
                         (rn, f"best repair of NeSy-Rep + Ward ({rn})"),
                         ("ablation:nesyward:full", "GraphRL-Dec full from NeSy-Rep + Ward, paper setting"),
                         ("ablation:nesyward_kl0_ep2000:full", "GraphRL-Dec full from NeSy-Rep + Ward, kl0"),
                         ("ablation:nesyward_kl0_ep2000:structural", "GraphRL-Dec structural from NeSy-Rep + Ward, kl0")):
            if by.get((app, fam)):
                print(line(app, fam, lab))

    print("\n### F2. All six apps: the kl0 setting against the paper setting, every variant\n")
    print("Cells: kl0 Score minus paper-setting Score, evaluate / rldec / weerasinghe, each scored in place of "
          "GraphRL-Dec full; means over 3 seeds.\n")
    print("| app | " + " | ".join(VARIANTS) + " |\n|---|" + "---|" * len(VARIANTS))
    wins = defaultdict(int)
    n = 0
    for app in APPS:
        cells = []
        for v in VARIANTS:
            a, b = f"ablation:kl0_ep2000:{v}", f"graphrl:{v}"
            if not by.get((app, a)):
                cells.append("missing")
                continue
            d = [score(app, a, c) - score(app, b, c) for c in CONV]
            n += 1
            for c, x in zip(CONV, d):
                wins[c] += x > 0
            cells.append(" / ".join(f"{x:+.2f}" for x in d))
        print(f"| {app} | " + " | ".join(cells) + " |")
    print(f"\nkl0 above the paper setting: " + ", ".join(f"{c} {wins[c]} of {n}" for c in CONV) + " (app, variant) pairs.")

    print("\n### F3. Cannot-link violations of every kl0 and NeSy-Rep-start run\n")
    tot = viol = 0
    for app in CL_APPS:
        for r in rows:
            if r["app"] == app and r["family"].split(":")[1:2] and r["family"].split(":")[1] in ("kl0_ep2000", "nesyward", "nesyward_kl0_ep2000"):
                tot += 1
                viol += float(r["cannot_link_violations"]) > 0
    print(f"{tot} runs on the apps with cannot-link pairs; {viol} with any violation.")


if __name__ == "__main__":
    main()
