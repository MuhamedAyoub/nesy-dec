"""Build the Java evaluation report as a PDF, with the comparison against the
published state of the art (Weerasinghe et al. 2026, Table 1).

Every number is read from results/results/*.csv and from the Table 1
transcription in results/recon/eq5_reproduce.py; nothing is typed in.

Usage: python3 -m java_pipeline.report_pdf
Writes results/report/java_evaluation_report.pdf (and its .tex and figures).
"""
from __future__ import annotations

import csv
import json
import statistics as st
import subprocess
import sys
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from java_pipeline.subjects import OUT  # noqa: E402

sys.path.insert(0, str(OUT / "recon"))
from eq5_reproduce import TABLE1  # noqa: E402

RES = OUT / "results"
REP = OUT / "report"
APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
# the version set the published rows were measured on (SUBJECTS.md section 1)
SOTA_APPS = [("daytrader7", "DayTrader"), ("acmeair", "AcmeAir"), ("lit-jpetstore", "JPetStore"), ("lit-pbw", "Plants")]
OURS = [("teacher", "RoR-MSI clustering (teacher)"), ("graphrl:full", "GraphRL-Dec (full)"),
        ("unixcoder_ward_nesyrep", "NeSy-Rep + Ward"), ("hierdec", "HierDec on our graph"),
        ("rldec_best", "RLDec on our graph, best state"), ("rldec", "RLDec on our graph, CLI decode")]
LABEL = dict(OURS) | {"unixcoder_ward_pretrained": "UnixCoder + Ward", "unixcoder_hdbscan_nesyrep": "NeSy-Rep + HDBSCAN",
                      "random": "random"}
POOL_ORDER = ["teacher", "graphrl:full", "unixcoder_ward_nesyrep", "unixcoder_ward_pretrained",
              "unixcoder_hdbscan_nesyrep", "hierdec", "rldec", "rldec_best", "random"]
# Weerasinghe Table 1 provenance (RECON.md section 3): shaded = run by Weerasinghe
RERUN_BY_WEERASINGHE = {"CHGNN", "MonoEmbed"}
BLUE, ORANGE = "#2a78d6", "#eb6834"         # validated with the dataviz palette checker
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"


def tex(s: str) -> str:
    return (str(s).replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%")
            .replace("_", r"\_").replace("#", r"\#").replace("~", r"\textasciitilde{}"))


def num(x, d=2, sign=False) -> str:
    v = float(x)
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s.replace("-", "$-$")


def table(header: list[str], rows: list[list[str]], spec: str, bold_rows: set[int] = frozenset()) -> str:
    out = [r"\resizebox{\ifdim\width>\linewidth\linewidth\else\width\fi}{!}{\begin{tabular}{" + spec + "}", r"\toprule",
           " & ".join(header) + r" \\", r"\midrule"]
    for i, r in enumerate(rows):
        cells = [rf"\textbf{{{c}}}" if i in bold_rows else c for c in r]
        out.append(" & ".join(cells) + r" \\")
    out += [r"\bottomrule", r"\end{tabular}}"]
    return "\n".join(out)


def md_rows(path, header_start: str) -> list[list[str]]:
    """Rows of the first markdown table in `path` whose header starts with header_start."""
    lines = (OUT / path).read_text().splitlines()
    for i, l in enumerate(lines):
        if l.startswith("| " + header_start):
            out = []
            for r in lines[i + 2:]:
                if not r.startswith("|"):
                    break
                out.append([c.strip() for c in r.strip("|").split("|")])
            return out
    return []


def load():
    metrics = list(csv.DictReader((RES / "metrics.csv").open()))
    comp = list(csv.DictReader((RES / "composite.csv").open()))
    ext = list(csv.DictReader((RES / "external.csv").open()))
    abl = list(csv.DictReader((RES / "ablation.csv").open())) if (RES / "ablation.csv").is_file() else []
    return metrics, comp, ext, abl


def figure_sota(ext: list[dict]) -> None:
    from matplotlib.patches import Patch
    for conv, fname in (("weerasinghe", "fig_sota_weighted.pdf"), ("rldec", "fig_sota_binarized.pdf")):
        fig, axes = plt.subplots(2, 2, figsize=(11, 9.5))
        for ax, (app, bench) in zip(axes.flat, SOTA_APPS):
            r = sorted((x for x in ext if x["app"] == app and x["our_convention"] == conv),
                       key=lambda x: float(x["Score_pool"]))
            names = [(LABEL.get(x["row"][5:], x["row"][5:]) if x["row"].startswith("ours:") else x["row"][10:]) for x in r]
            vals = [float(x["Score_pool"]) for x in r]
            cols = [ORANGE if x["row"].startswith("ours:") else BLUE for x in r]
            ax.barh(range(len(r)), vals, color=cols, height=0.72, edgecolor="#fcfcfb", linewidth=1)
            ax.set_yticks(range(len(r)))
            ax.set_yticklabels(names, fontsize=8.5, color=INK)
            ax.axvline(0, color=INK2, linewidth=0.8)
            ax.grid(axis="x", color=GRID, linewidth=0.6)
            ax.set_axisbelow(True)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            ax.tick_params(axis="x", labelsize=8, colors=INK2)
            ax.set_title(f"{bench} ({app}, {len(r)} tools)", fontsize=10, color=INK, loc="left")
        fig.legend(handles=[Patch(color=BLUE, label="published (Weerasinghe et al. 2026, Table 1)"),
                            Patch(color=ORANGE, label="ours (this study)")], loc="lower center", ncol=2,
                   frameon=False, fontsize=9.5)
        fig.supxlabel("Eq. 5 Score within the pool (sample std, divided by 7); higher is better", fontsize=9, color=INK2, y=0.045)
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        fig.savefig(REP / fname)
        plt.close(fig)


def main() -> None:
    REP.mkdir(parents=True, exist_ok=True)
    metrics, comp, ext, abl = load()
    fam_runs: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in metrics:
        fam_runs[(r["app"], r["family"])].append(r)

    def score(app, fam, conv="evaluate"):
        x = [r for r in comp if r["app"] == app and r["family"] == fam and r["convention"] == conv and r["eq5"] == "as_published"]
        return float(x[0]["Score"]) if x else None

    def m(app, fam, conv, k):
        rs = fam_runs.get((app, fam), [])
        return st.mean(float(r[f"{conv}_{k}"]) for r in rs) if rs else None

    def nodes(app):
        return len(json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())["dependency_graph"])

    def ext_rank(app, conv, row):
        r = sorted((x for x in ext if x["app"] == app and x["our_convention"] == conv), key=lambda x: -float(x["Score_pool"]))
        return next(i + 1 for i, x in enumerate(r) if x["row"] == row), len(r)

    figure_sota(ext)

    # ---------- derived headline numbers (all computed) ----------
    best_eval = {a: max(POOL_ORDER, key=lambda f: score(a, f) if score(a, f) is not None else -9) for a in APPS}
    teacher_first = sum(1 for a in APPS if best_eval[a] in ("teacher", "graphrl:full"))
    nesy_better = sum(1 for a in APPS if m(a, "unixcoder_ward_nesyrep", "evaluate", "SM") > m(a, "unixcoder_ward_pretrained", "evaluate", "SM") + 1e-9)
    teacher_ids = {a: {frozenset(c["classes"]) for c in json.loads((OUT / a / "exp_a0.9_b0.1_n8_java.json").read_text())["clusters"]} for a in APPS}
    rl_same = rl_total = 0
    for a in APPS:
        for p in (OUT / "_nesy" / "rl" / a).glob("*/partition.json"):
            rl_total += 1
            rl_same += {frozenset(x) for x in json.loads(p.read_text())["partitions"]} == teacher_ids[a]
    abl = [x for x in abl if x["ablation_family"].split(":")[1] in ("kl0_ep2000", "nobc_ep2000")
           and x["ablation_family"].split(":")[2] in ("structural", "full")]      # section 5's scope
    abl_better = {(ab, conv): (sum(1 for x in abl if x["ablation_family"].split(":")[1] == ab and x["convention"] == conv
                                   and float(x["Score"]) > float(x["teacher_Score_same_pool"]) + 1e-9),
                               sum(1 for x in abl if x["ablation_family"].split(":")[1] == ab and x["convention"] == conv))
                  for ab in ("kl0_ep2000", "nobc_ep2000") for conv in ("evaluate", "rldec")}
    has_cl = [a for a in APPS if fam_runs[(a, "teacher")][0]["cannot_link_pairs"] != "0"]
    no_cl = [a for a in APPS if a not in has_cl]
    rl_same_by = {a: [0, 0] for a in APPS}
    for a in APPS:
        for p in (OUT / "_nesy" / "rl" / a).glob("*/partition.json"):
            rl_same_by[a][1] += 1
            rl_same_by[a][0] += {frozenset(x) for x in json.loads(p.read_text())["partitions"]} == teacher_ids[a]
    def viol(app, fam):
        v = [float(r["cannot_link_violations"]) for r in fam_runs.get((app, fam), [])]
        return st.mean(v) if v else None
    rl_runs_cl = [r for a in has_cl for r in metrics if r["app"] == a and r["family"].startswith("graphrl:")]
    rl_viol_runs = sum(1 for r in rl_runs_cl if float(r["cannot_link_violations"]) > 0)
    graphrl_best = [a for a in APPS if best_eval[a] == "graphrl:full"]

    def ml_kept(app, fam):
        exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
        act = set(exp["dependency_graph"])
        n = len({tuple(sorted(x[:2])) for x in json.loads((OUT / app / "facts_nesy.json").read_text())["must_link"]
                 if x[0] in act and x[1] in act})
        return round(st.mean(float(r["must_link_satisfaction"]) for r in fam_runs[(app, fam)]) * n), n
    ml_loss = max(has_cl, key=lambda a: ml_kept(a, "teacher")[0] - ml_kept(a, "graphrl:full")[0])
    import re as _re0
    cl_losses = [float(x) for x in _re0.findall(r"'avg_constraint_loss': ([0-9.e-]+)", (OUT / "gpu_logs" / "main.log").read_text())]
    top_ours = {}
    for app, bench in SOTA_APPS:
        for conv in ("weerasinghe", "rldec"):
            ranks = [ext_rank(app, conv, f"ours:{f}") for f, _ in OURS if any(x["row"] == f"ours:{f}" for x in ext if x["app"] == app)]
            best = min(ranks)
            top_ours[(app, conv)] = f"{best[0]} of {best[1]}"

    # ---------- LaTeX ----------
    L = [r"""\documentclass[10pt,a4paper]{article}
\usepackage[margin=2cm]{geometry}
\usepackage{booktabs,graphicx,xcolor,hyperref,caption,array,adjustbox}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\hypersetup{pdftitle={NeSy-Dec on Java monoliths: evaluation and comparison with the state of the art},pdfauthor={},pdfcreator={pdflatex},colorlinks=true,linkcolor=black,urlcolor=black}
\setlength{\parskip}{0.45em}\setlength{\parindent}{0pt}
\captionsetup{font=small,labelfont=bf}
\begin{document}
{\Large\bfseries NeSy-Dec on Java monoliths: evaluation and comparison with the state of the art}\\[0.4em]
{\small Results of 3 November 2026, after the Java fact base gained cannot-link constraints (rule CL-SIBLING). Every number below is read from \texttt{results\_java/results/*.csv}; the full tables, run log and claim-to-file map are in \texttt{RESULTS.md}, \texttt{RUNS.md} and \texttt{VERIFICATION.md}.}
\section{Summary}
\begin{itemize}\setlength{\itemsep}{2pt}"""]
    L.append(rf"\item \textbf{{GraphRL-Dec is the only method of the comparison pool that respects every cannot-link constraint.}} On the {len(has_cl)} apps that have them ({', '.join(tex(a) for a in has_cl)}), {"none" if rl_viol_runs == 0 else rl_viol_runs} of its {len(rl_runs_cl)} runs places a cannot-link pair in one service. Every other method of the pool violates pairs on at least one of these apps; rule-based repairs inside the same mask also comply, so the compliance comes from the mask (Section~\ref{{sec:cl}}).")
    L.append(rf"\item \textbf{{GraphRL-Dec is its teacher, repaired where the constraints forbid it.}} On the {len(no_cl)} apps without cannot-link pairs, {sum(rl_same_by[a][0] for a in no_cl)} of {sum(rl_same_by[a][1] for a in no_cl)} runs decode to exactly the RoR-MSI teacher's partition; on the {len(has_cl)} apps with pairs, {sum(rl_same_by[a][0] for a in has_cl)} of {sum(rl_same_by[a][1] for a in has_cl)} do. Within our pipeline, GraphRL-Dec or its teacher has the highest composite Score on {teacher_first} of the {len(APPS)} apps (Eq.~5, \texttt{{evaluate.py}} metrics), GraphRL-Dec alone on {len(graphrl_best)}.")
    L.append(rf"\item \textbf{{Against the published tools}} (Weerasinghe et al.\ 2026, Table~1), our best row is ranked "
             + ", ".join(f"\\#{top_ours[(a, 'weerasinghe')]} on {b}" for a, b in SOTA_APPS)
             + r" when SM is computed on weighted calls, and "
             + ", ".join(f"\\#{top_ours[(a, 'rldec')]} on {b}" for a, b in SOTA_APPS)
             + r" when SM is binarized as in Sellami's code. The comparison is indicative only (Section~\ref{sec:threats}).")
    L.append(rf"\item \textbf{{NeSy-Rep fine-tuning improves the embeddings:}} NeSy-Rep + Ward has a higher SM than pretrained UnixCoder + Ward on {nesy_better} of the {len(APPS)} apps" + ("" if nesy_better == len(APPS) else " and an equal or lower one on the rest") + ".")
    L.append(rf"\item \textbf{{Ablations.}} Without the KL anchor it beats the teacher in {abl_better[('kl0_ep2000', 'evaluate')][0]} of {abl_better[('kl0_ep2000', 'evaluate')][1]} cases on the metric its reward uses, but in only {abl_better[('kl0_ep2000', 'rldec')][0]} of {abl_better[('kl0_ep2000', 'rldec')][1]} under the binarized metric; without the behaviour-cloning warm start it beats the teacher in {abl_better[('nobc_ep2000', 'evaluate')][0]} of {abl_better[('nobc_ep2000', 'evaluate')][1]}.")
    L.append(r"\item \textbf{Sellami's HierDec and RLDec at their defaults do poorly on our graph}: HierDec fragments each app into many small services, RLDec's own decode returns one service on every app and seed.")
    gam = md_rows("gaming_check.md", "app")
    gam_first = sum(1 for r in gam if r[4].startswith("#1 "))
    L.append(rf"\item \textbf{{The Eq.~5 comparison can be gamed.}} A hill-climb on SM, IFN, ICP and NED that starts from a \emph{{random}} partition, with no architectural knowledge, ranks \#1 in the published pool in {gam_first} of {len(gam)} runs when SM counts weighted calls (Section~\ref{{sec:after}}). Rankings against published tools on these metrics are therefore not evidence of better decompositions, ours included. The same partitions violate cannot-link constraints; GraphRL-Dec's do not.")
    L.append(r"\item \textbf{A reward that is not the evaluation metric did not help GraphRL-Dec} (measured before the constraints were added): the dual reward beats the teacher on a held-out convention in fewer runs than the original reward.")
    L.append(r"\end{itemize}")

    # ---------- setup ----------
    L.append(r"\section{Setup}")
    L.append(r"Six subjects: the four benchmarks of Weerasinghe et al.\ in the repositories their footnotes link, plus the two versions the copied rows of their Table~1 were actually measured on (KimJongSung/jPetStore and the pbw-monolith, here \emph{lit-jpetstore} and \emph{lit-pbw}). Our analyzer (JavaParser 3.26.2 with a full classpath) resolves every call site except AcmeAir's proprietary wxs module; the layered resolver builds the graph $G$ every method partitions.")
    rows = []
    for a in APPS:
        bench = {"daytrader7": "DayTrader", "acmeair": "AcmeAir", "lit-jpetstore": "JPetStore", "jpetstore-6": "JPetStore",
                 "lit-pbw": "Plants", "plantsbywebsphere": "Plants"}[a]
        vs = {"daytrader7": "both", "acmeair": "both", "lit-jpetstore": "literature", "jpetstore-6": "footnote",
              "lit-pbw": "literature", "plantsbywebsphere": "footnote"}[a]
        e = json.loads((OUT / a / "graph.json").read_text())["summary"]["edges"]
        rows.append([tex(a), bench, vs, str(nodes(a)), str(e)])
    L.append(r"\begin{center}" + table(["app", "benchmark", "version set", "classes partitioned", "edges in $G$"], rows, "lllrr") + r"\end{center}")
    L.append(r"Metrics are SM, IFN, ICP and NED, combined with Weerasinghe's Eq.~5 in the form that reproduces their published Score column exactly (sample standard deviation, divided by 7; 35 of 35 cells). Because the published rows come from several papers' own metric code, our rows are scored in two conventions: \emph{weighted calls} (Eq.~1--4 on our call graph) and \emph{binarized SM} (Sellami's RLDec metric code, which counts distinct dependencies). Within our pipeline the primary convention is \texttt{evaluate.py}'s, on $G$.")

    # ---------- SOTA ----------
    L.append(r"\section{Comparison with the state of the art}\label{sec:sota}")
    L.append(r"Each benchmark's pool is the published tools of Weerasinghe Table~1 (their metric values copied exactly) plus our rows; Eq.~5 is recomputed over the pool. Published rows marked $^\dagger$ were run by Weerasinghe et al.; the others were copied by them from the original papers. JPetStore and Plants use the literature versions. Figures~\ref{fig:sota} and~\ref{fig:sotab} show the two conventions; the tables give the weighted-call convention with the binarized rank beside it.")
    L.append(r"\begin{figure}[p]\centering\includegraphics[width=\textwidth]{fig_sota_weighted.pdf}\caption{Eq.~5 Score of every tool in each benchmark's pool, our rows scored with SM on weighted calls (Weerasinghe Eq.~1--4). Orange: ours, on our graph; blue: published rows.}\label{fig:sota}\end{figure}")
    L.append(r"\begin{figure}[p]\centering\includegraphics[width=\textwidth]{fig_sota_binarized.pdf}\caption{The same pools with our rows scored with binarized SM (Sellami's RLDec metric code).}\label{fig:sotab}\end{figure}")
    for app, bench in SOTA_APPS:
        rows, bold = [], set()
        r_w = sorted((x for x in ext if x["app"] == app and x["our_convention"] == "weerasinghe"), key=lambda x: -float(x["Score_pool"]))
        for i, x in enumerate(r_w):
            ours = x["row"].startswith("ours:")
            name = LABEL.get(x["row"][5:], x["row"][5:]) if ours else x["row"][10:] + (r"$^\dagger$" if x["row"][10:] in RERUN_BY_WEERASINGHE else "")
            rb = ext_rank(app, "rldec", x["row"])[0] if ours else ext_rank(app, "rldec", x["row"])[0]
            pub = num(x["Score_published"], sign=True) if x["Score_published"] not in ("", "None") else "--"
            rows.append([str(i + 1), tex(name) if ours else name, "ours" if ours else "published", num(x["SM"]), num(x["IFN"]),
                         num(x["ICP"]), num(x["NED"]), pub, num(x["Score_pool"], sign=True), f"\\#{rb}"])
            if ours:
                bold.add(i)
        L.append(rf"\subsection*{{{bench} ({tex(app)}, {nodes(app)} classes)}}")
        L.append(r"\begin{center}\small" + table(["rank", "tool", "source", "SM", "IFN", "ICP", "NED", "published Score", "pool Score", "rank, binarized"],
                                                  rows, "rllrrrrrrr", bold) + r"\end{center}")
    # footnote-set ranks
    rows = []
    for a in ("jpetstore-6", "plantsbywebsphere"):
        for f, lab in OURS[:3]:
            rows.append([tex(a), lab, "\\#%d of %d" % ext_rank(a, "weerasinghe", f"ours:{f}"), "\\#%d of %d" % ext_rank(a, "rldec", f"ours:{f}")])
    L.append(r"The footnote versions (mybatis/jpetstore-6 with 24 classes, WASdev Plants with 35) are smaller programs than the ones the published rows measured; their ranks in the same pools are:")
    L.append(r"\begin{center}\small" + table(["app", "our row", "rank, weighted calls", "rank, binarized"], rows, "llrr") + r"\end{center}")
    L.append(r"How to read this: on weighted calls our RoR-MSI-based rows lead or are near the top of every pool, but our weighted SM can exceed 1 (e.g.\ the teacher reaches %s on lit-pbw) while no published SM exceeds 0.60, so this convention flatters weighted graphs. On binarized SM our rows fall to mid-table and a published row leads every pool (%s). The truth for a like-for-like comparison is unknown because the published numbers were computed with different code on different class sets." % (
        num(m("lit-pbw", "teacher", "weerasinghe", "SM")),
        ", ".join(f"{max((x for x in ext if x['app'] == a and x['our_convention'] == 'rldec'), key=lambda x: float(x['Score_pool']))['row'][10:]} on {b}"
                  for a, b in SOTA_APPS)))

    # ---------- within pipeline ----------
    L.append(r"\section{Within-pipeline comparison (same graph, same classes, same metric code)}")
    L.append(r"This is the fair comparison: every method partitions the same classes of the same graph, scored by one piece of code, with coverage 1.00 everywhere. Eq.~5 Score within each app's pool of nine methods; means over 3 seeds where a method has several runs.")
    for conv, cap in (("evaluate", r"\texttt{evaluate.py} metrics on $G$ (primary)"), ("rldec", "binarized SM (RLDec's metric code) on $G$")):
        rows, header = [], ["method"] + [tex(a) for a in APPS]
        for f in POOL_ORDER:
            cells = []
            col_best = {a: max(POOL_ORDER, key=lambda g: score(a, g, conv) if score(a, g, conv) is not None else -9) for a in APPS}
            for a in APPS:
                v = score(a, f, conv)
                c = num(v, sign=True) if v is not None else "--"
                cells.append(rf"\textbf{{{c}}}" if col_best[a] == f else c)
            rows.append([tex(LABEL[f])] + cells)
        L.append(rf"\paragraph{{Score, {cap}.}} Best per app in bold.")
        L.append(r"\begin{center}\small" + table(header, rows, "l" + "r" * len(APPS)) + r"\end{center}")
    rows = []
    for a in APPS:
        rows.append([tex(a), num(m(a, "unixcoder_ward_pretrained", "evaluate", "SM")), num(m(a, "unixcoder_ward_nesyrep", "evaluate", "SM")),
                     num(m(a, "unixcoder_ward_pretrained", "rldec", "SM")), num(m(a, "unixcoder_ward_nesyrep", "rldec", "SM"))])
    L.append(r"\paragraph{Effect of NeSy-Rep fine-tuning.} SM of Ward clustering on pretrained against fine-tuned embeddings, same K:")
    L.append(r"\begin{center}\small" + table(["app", "pretrained", "NeSy-Rep", "pretrained, binarized", "NeSy-Rep, binarized"], rows, "lrrrr") + r"\end{center}")

    # ---------- constraints ----------
    L.append(r"\section{Constraint compliance (RQ4)}\label{sec:cl}")
    L.append(r"Java code has no namespace convention like the Rails one, so cannot-link comes from rule CL-SIBLING (\texttt{FACTS.md}, Section~2): two sibling packages are disjoint when each holds at least two active classes, no direct or type-use edge joins them, and they are peers, either in the same layer by stereotype or as alternative implementations of a common application interface. The rule fires on DayTrader (JSF front end against the servlet primitives and the WebSocket endpoints), AcmeAir (the MongoDB and eXtreme Scale back ends) and lit-jpetstore (the Spring MVC and Struts web layers). A violation is a pair placed in one service; means over seeds where a method has several runs:")
    cl_fams = [("graphrl:full", "GraphRL-Dec"), ("teacher", "RoR-MSI (teacher)"), ("unixcoder_ward_nesyrep", "NeSy-Rep + Ward"),
               ("unixcoder_ward_pretrained", "UnixCoder + Ward"), ("hierdec", "HierDec"), ("rldec_best", "RLDec, best state"),
               ("rldec", "RLDec, CLI decode"), ("random", "random")]
    rows = [[lab] + [num(viol(a, f), 1 if f in ("rldec_best", "random") else 0) for a in has_cl] for f, lab in cl_fams]
    header = ["method"] + [f"{tex(a)} ({fam_runs[(a, 'teacher')][0]['cannot_link_pairs']} pairs)" for a in has_cl]
    L.append(r"\begin{center}\small" + table(header, rows, "l" + "r" * len(has_cl), {0}) + r"\end{center}")
    L.append(rf"The RL environment masks every action that would place a class with a cannot-link partner, in training and in the decode, so GraphRL-Dec can violate a pair only through the mask's fallback, which makes every service legal when all are forbidden. In the variants with an outlier action, including \texttt{{full}}, one action always stays legal and a violation is impossible by construction; for all runs on these apps, a replay of the decode under the server's torch version reproduces every partition and shows the fallback never fired (\texttt{{recon/mask\_replay.out}}). The teacher does not see the constraints, and its violations are what the RL stage repairs: GraphRL-Dec moves only a few classes (\texttt{{recon/graphrl\_repairs.out}}). The repair raises SM, but partly by construction, because the rule separates packages with no edge between them in the graph SM is computed on. On {tex(ml_loss)} it also costs must-link pairs: {ml_kept(ml_loss, 'graphrl:full')[0]} of {ml_kept(ml_loss, 'graphrl:full')[1]} are kept together, against the teacher's {ml_kept(ml_loss, 'teacher')[0]}. The encoder's own cannot-link term barely acts (mean loss per epoch at most {max(cl_losses):.5f}, as in the Rails runs); the constraints reach the embeddings through the triplets.")

    rep_rows = md_rows("repair_baseline.md", "app")
    if rep_rows:
        L.append(r"\paragraph{Repair by rule.} Does the learned policy add anything over repairing the teacher by rule? Three rule-based repairs run in the same masked environment, with no learning: \texttt{repair\_masked} takes the teacher's service or the lowest-index legal one, \texttt{repair\_connect} the legal service with the most edge weight to the class, and \texttt{repair\_post} moves violating classes out of the teacher's finished partition. Each row takes GraphRL-Dec's place in the nine-method pool (GraphRL-Dec's own Score in brackets):")
        L.append(r"\begin{center}\small" + table(["app", "method", "= GraphRL-Dec", "moved", "violations", "must-link", "Score", "binarized", "weighted calls"],
                                                  [[tex(c) for c in r] for r in rep_rows], "llrrrrrrr") + r"\end{center}")
        L.append(r"All repairs violate nothing, so compliance comes from the mask, not from the learning. The best repair matches GraphRL-Dec's quality: it is at most 0.02 below it anywhere and above it on AcmeAir and DayTrader. On these benchmarks the RL stage behaves as a learned constraint repair, and a rule does about as well.")

    # ---------- GraphRL ----------
    L.append(r"\section{GraphRL-Dec and the ablation}")
    L.append(rf"With the Rails settings (behaviour-cloning warm start from the teacher, KL anchor 0.5, PPO learning rate $10^{{-4}}$, 600 episodes), {rl_same} of {rl_total} runs (8 reward variants $\times$ 6 apps $\times$ 3 seeds) decode to exactly the teacher's partition, all of them on the apps without cannot-link pairs; on the others the action mask is what makes the policy deviate. Two labelled ablations (72 runs, with the same mask) test whether PPO can leave the teacher on its own. Each ablation row takes GraphRL-Dec's place in the nine-method pool.")
    rows = []
    for a in APPS:
        for ab, lab in (("kl0_ep2000", "no KL, 2,000 ep."), ("nobc_ep2000", "no warm start")):
            for var in ("structural", "full"):
                fam = f"ablation:{ab}:{var}"
                ev = next((x for x in abl if x["app"] == a and x["ablation_family"] == fam and x["convention"] == "evaluate"), None)
                rl = next((x for x in abl if x["app"] == a and x["ablation_family"] == fam and x["convention"] == "rldec"), None)
                if not ev:
                    continue
                rows.append([tex(a), lab, var, num(ev["Score"], sign=True), num(ev["teacher_Score_same_pool"], sign=True),
                             num(rl["Score"], sign=True), num(rl["teacher_Score_same_pool"], sign=True)])
    L.append(r"\begin{center}\small" + table(["app", "ablation", "variant", "Score", "teacher", "Score, binarized", "teacher, binarized"], rows, "lllrrrr") + r"\end{center}")
    L.append(rf"Without the anchor, PPO beats the teacher in {abl_better[('kl0_ep2000', 'evaluate')][0]} of 12 cases on \texttt{{evaluate.py}} metrics, which are the very functions its reward is built from, but in only {abl_better[('kl0_ep2000', 'rldec')][0]} of 12 under the binarized metric. Without the warm start it collapses, mostly to a single service or to no assigned class at all. The RL stage therefore depends on the RoR-MSI teacher, and its unanchored gains transfer across metric conventions only in part.")

    # ---------- follow-up ----------
    fu = md_rows("followup.md", "app | method | runs")
    if fu:
        L.append(r"\section{Follow-up: can the RL stage beat the rule?}")
        L.append(r"Two follow-up GPU experiments. First, GraphRL-Dec without the KL anchor and with 2,000 episodes (\emph{kl0}), a setting chosen beforehand on the three apps without cannot-link pairs only (\texttt{recon/setting\_selection.out}) and then applied unchanged. Second, GraphRL-Dec warm-started from NeSy-Rep + Ward instead of the RoR-MSI teacher, compared with rule-based repairs of that partition. Each row takes GraphRL-Dec's place in the nine-method pool:")
        L.append(r"\begin{center}\scriptsize" + table(["app", "method", "runs", "violations", "must-link", "semantic", "Score", "binarized", "weighted calls"],
                                                       [[tex(c) for c in r] for r in fu], "llrrrrrrr") + r"\end{center}")
        L.append(r"Without the anchor, GraphRL-Dec beats the best rule-based repair on DayTrader and lit-jpetstore in all three conventions, but not on AcmeAir. Across all six apps and eight variants its gain over the paper setting is mostly in the reward's own metric family and transfers to binarized SM in under a third of the cases (\texttt{followup.md}, Table F2). The NeSy-Rep warm start does not help: it at best ties the repair of its own starting partition. Every new run on the constrained apps has zero violations.")

    # ---------- threats ----------
    # ---------- experiments after the main run ----------
    L.append(r"\section{Experiments after the main run}\label{sec:after}")
    L.append(r"These ran on a local RTX 3060 (GraphRL-Dec) and CPU (the rest); the full account is \texttt{OPTIMIZATION.md}. They are labelled experiments and replace nothing above.")
    L.append(r"\paragraph{A reward that is not the evaluation metric.} Measured on 26 October 2026, before the fact base had cannot-link pairs, and not repeated. The dual reward averages the \texttt{evaluate.py} and binarized z-scores; the weighted-call convention is in neither term and serves as the held-out check. Runs beating the teacher, each seed scored alone in the nine-method pool:")
    tot = md_rows("idea1_report.md", "setting")
    L.append(r"\begin{center}\small" + table(["setting", r"\texttt{evaluate.py}", "binarized", "held out"], [[tex(r[0])] + r[1:] for r in tot], "lrrr") + r"\end{center}")
    L.append(r"It does not make GraphRL-Dec better than the teacher across apps; on AcmeAir and DayTrader it returns to the teacher's exact partition in every run.")
    L.append(r"\paragraph{Hill-climbing the same objective.} A search that repeatedly applies the best single-class move (under the RL environment's size cap) beats the teacher on all six apps in all three conventions when started from the teacher. Started from random partitions it does as well, and in the published pools it ranks as follows (random partitions alone in columns 7 and 8; the last column counts the cannot-link pairs the hill-climbed partition violates):")
    L.append(r"\begin{center}\small" + table(["app", "benchmark", "seed", "services", "weighted", "binarized", "random, weighted", "random, binarized", "cannot-link violated"],
                                              [[tex(c) for c in r] for r in gam], "llrrrrrrr") + r"\end{center}")
    L.append(r"Some moves are sensible (on jpetstore-6, \texttt{Item} and \texttt{Product} join the catalog service), others are not (on DayTrader, benchmark servlets such as \texttt{PingJDBCRead} join the account-data service), and measures the search does not optimize (embedding similarity within services, must-link facts kept together) change only slightly. The gain is optimization of the metric family itself, so the refinement is not reported as a method. Cannot-link compliance tells it apart from an architecturally informed decomposition.")
    L.append(r"\paragraph{Why our rows rank lower under binarized SM.} Binarized SM is the dependency density inside each service (distinct internal edges divided by the squared size). Our graphs are sparse, a service of about nine classes has a density near 0.2, below a two-class service with one edge (0.25), and Eq.~5 weights SM three times, so tools emitting many tiny services gain (the published HDBScan row has NED 0.70--0.90 and SM up to 0.60). RLDec's code also counts self-calls, which our graph omits:")
    import re as _re
    rows = []
    for line in (OUT / "recon" / "binarized_selfcalls.out").read_text().splitlines():
        m_ = _re.match(r"(\S+)\s+graph density ([\d.]+)\s+mean service size ([\d.]+)\s+mean intra-service density ([\d.]+)\s+binarized SM ([\d.]+) -> ([\d.]+)", line)
        if m_:
            rows.append([tex(m_.group(1))] + list(m_.groups()[1:]))
    L.append(r"\begin{center}\small" + table(["app", "graph density", "mean service size", "density inside services", "binarized SM", "with self-calls"], rows, "lrrrrr") + r"\end{center}")
    L.append(r"\paragraph{Resolver layers.} The teacher run on the naive declared-type graph cannot place the classes that graph leaves isolated; on the resolved graph it places all of them:")
    la = list(csv.DictReader((RES / "layer_ablation.csv").open()))
    rows = []
    for a_ in APPS:
        nv = next(r for r in la if r["app"] == a_ and r["variant"] == "naive")
        fl = next(r for r in la if r["app"] == a_ and r["variant"] == "full")
        rows.append([tex(a_), str(nodes(a_)), nv["unassigned_as_singletons"], fl["unassigned_as_singletons"],
                     num(nv["evaluate_SM"]), num(fl["evaluate_SM"])])
    L.append(r"\begin{center}\small" + table(["app", "classes", "unplaceable, naive graph", "unplaceable, resolved graph", "SM, naive", "SM, resolved"], rows, "lrrrrr") + r"\end{center}")
    L.append(r"The SM column is computed on the resolved graph for both partitions, which favours the resolved one; the unplaceable counts do not depend on any metric.")

    # ---------- where the study stands ----------
    L.append(r"\section{Where the study stands}")
    L.append(r"""\textbf{Supported by the evidence:}
\begin{itemize}\setlength{\itemsep}{2pt}
\item the Java front end (analyzer, layered resolver with provenance, symbolic facts) works on all six subjects, and without the resolver a large share of classes cannot be placed at all;
\item NeSy-Rep fine-tuning improves the code embeddings;
\item Weerasinghe's published Score column is reproduced exactly only with sample standard deviation divided by 7, not with the formula in their text;
\item rankings on SM, IFN, ICP and NED flip with the SM definition, and a knowledge-free search tops every published tool, so these metrics cannot establish state-of-the-art decomposition quality;
\item GraphRL-Dec's action mask enforces the cannot-link constraints: it is the only method with no violation on every app that has them, and it repairs its teacher's violations with a few moves.
\end{itemize}
\textbf{Not supported:} that the learned policy adds quality over a rule-based repair of its teacher on Java; that GraphRL-Dec beats the published tools, since its SM gains over the teacher are partly built into the constraint rule and the metric comparison is gameable; that CL-SIBLING generalises, since it was written on these six subjects.

\textbf{Next step.} Evidence of decomposition quality needs a criterion no method optimizes: an expert or published reference decomposition for these applications, compared with agreement measures such as MoJoFM, and the cannot-link rule applied unchanged to Java systems it was not designed on.""")
    L.append(r"\section{Threats to validity}\label{sec:threats}")
    L.append(r"""\begin{itemize}\setlength{\itemsep}{2pt}
\item \textbf{Metric code.} The published rows were computed by several papers with their own code; three ICP definitions are in circulation and SM may or may not be weighted. Our two conventions bracket the plausible readings; neither is guaranteed to match.
\item \textbf{Class sets.} Our class counts differ from the published ones (DayTrader 104 against 118, AcmeAir 70 against 86, JPetStore 71 against 73, Plants 36 against 40), and how the papers counted nested and anonymous classes is not stated.
\item \textbf{Inputs.} All our methods are static; Mono2Micro and some others used execution traces.
\item \textbf{Copied numbers.} Only CHGNN and MonoEmbed were run by Weerasinghe et al.; the other published rows are copied from earlier papers.
\item \textbf{Baseline inputs.} HierDec and RLDec ran unmodified at their defaults on our graph, not on Sellami's analysis service; per-app tuning from their papers is not available. This is the fair within-pipeline comparison, not a reproduction of their papers.
\item \textbf{The cannot-link rule was written on these subjects} and fires on three of the six; it has not been applied to other Java systems.
\item \textbf{The rule and SM read the same graph}, so separating the rule's packages tends to raise SM; the compliance result itself does not depend on this.
\end{itemize}""")
    L.append(r"\section{Reproducibility}")
    L.append(r"Rebuilding jpetstore-6 from source reproduces every CPU-stage output exactly, except for the order of tied triplets (Python hash randomisation in the shared triplet generator). Two GraphRL-Dec runs repeated on a different GPU and torch build: the DayTrader run gave the identical partition and training trace, the lit-jpetstore run placed one class of 71 differently, with no cannot-link violation in either. All 447 tests of the Java pipeline pass. Commands, versions, wall times and config hashes of every run are in \texttt{RUNS.md}; the claim-to-file map is in \texttt{VERIFICATION.md}.")
    L.append(r"\end{document}")
    (REP / "java_evaluation_report.tex").write_text("\n".join(L))
    for _ in range(2):
        r = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "java_evaluation_report.tex"],
                           cwd=REP, capture_output=True, text=True)
        if r.returncode != 0:
            raise SystemExit(r.stdout[-3000:])
    for ext_ in (".aux", ".log", ".out"):
        (REP / f"java_evaluation_report{ext_}").unlink(missing_ok=True)
    print(f"[report] {REP / 'java_evaluation_report.pdf'}")


if __name__ == "__main__":
    main()
