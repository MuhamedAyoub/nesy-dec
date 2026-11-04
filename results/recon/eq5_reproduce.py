#!/usr/bin/env python3
"""Try to reproduce the Score column of Weerasinghe et al. 2026, Table 1, from
the SM/IFN/ICP/NED cells printed in the same table.

Source: 2601.23141v1.pdf, page 8, Table 1 (transcribed by hand, checked
against a 110 dpi render of the page). CHGNN on JPetStore is "-" in the paper
and is left out.

For each benchmark the pool is the tools listed for that benchmark. Variants
tried: weight vector W, z-score with population or sample std, or min-max,
and division by sum|W| or not. A published Score counts as reproduced when the
recomputed value rounds to it at two decimals.

Usage: python3 eq5_reproduce.py > eq5_reproduce.out
"""
import statistics as st

# tool: (SM, IFN, ICP, NED, published Score)
TABLE1 = {
    "DayTrader": {
        "Bunch": (.18, 11.00, .50, .65, -.58), "MEM": (.32, 3.50, .25, .95, .04),
        "FoSCI": (.30, 7.00, .82, .55, -.17), "CoGCN": (.49, 3.00, .35, .70, .73),
        "Mono2Micro": (.08, 1.92, .35, .34, -.15), "HDBScan": (.30, .05, .05, .70, .47),
        "a-BMSC": (.43, 1.20, .63, .65, .49), "CHGNN": (.13, 5.70, .55, .50, -.42),
        "MonoEmbed": (.13, 1.35, .59, .66, -.40)},
    "Plants": {
        "Bunch": (.22, 5.50, .30, .10, -.18), "MEM": (.54, 3.30, .22, .25, .71),
        "FoSCI": (.33, 4.00, .47, .70, -.20), "CoGCN": (.33, 3.50, .55, .50, -.13),
        "Mono2Micro": (.08, 6.00, .38, .04, -.57), "HDBScan": (.60, 1.00, .03, .80, .93),
        "a-BMSC": (.49, 1.80, .68, .75, .17), "CHGNN": (.17, 3.60, .51, .20, -.33),
        "MonoEmbed": (.11, 1.55, .26, .82, -.39)},
    "JPetStore": {
        "Bunch": (.10, 2.70, .00, .38, .05), "MEM": (.17, 3.00, 1.00, .43, .04),
        "FoSCI": (.08, 2.80, .45, .55, -.40), "CoGCN": (.09, 2.00, .60, .45, -.21),
        "Mono2Micro": (.05, 1.86, .33, .26, -.24), "HDBScan": (.22, .30, .02, .90, .97),
        "a-BMSC": (.18, 1.40, .65, .92, .23), "MonoEmbed": (.08, 2.56, .50, .67, -.45)},
    "AcmeAir": {
        "Bunch": (.25, 1.50, .45, .30, .24), "MEM": (.30, .70, .05, .38, .69),
        "FoSCI": (.33, 1.60, .65, .70, .19), "CoGCN": (.42, .90, .60, 1.00, .46),
        "Mono2Micro": (.07, 3.38, .53, .43, -.67), "HDBScan": (.30, .30, .02, .90, .53),
        "a-BMSC": (.15, 1.30, .80, .77, -.45), "CHGNN": (.11, 2.50, .37, .00, -.15),
        "MonoEmbed": (.01, 3.06, .47, .56, -.85)},
}

WEIGHTS = [(3, -1, -1, -1), (3, -1, -1, -0.5), (2, -1, -1, -0.5), (1, -1, -1, -1)]
NORMS = ("pop", "sample", "minmax")


def normalise(x, col, how):
    if how == "pop":
        return (x - st.mean(col)) / st.pstdev(col)
    if how == "sample":
        return (x - st.mean(col)) / st.stdev(col)
    return (x - min(col)) / (max(col) - min(col))


def scores(rows, w, how, div):
    cols = list(zip(*[v[:4] for v in rows.values()]))
    return {t: sum(wi * normalise(x, c, how) for wi, x, c in zip(w, v[:4], cols)) / div
            for t, v in rows.items()}


def main():
    print("W\tnorm\tdivisor\treproduced\ttotal\tmax_abs_diff")
    for w in WEIGHTS:
        for how in NORMS:
            for div in (sum(abs(x) for x in w), 1):
                hit = n = 0
                worst = 0.0
                for rows in TABLE1.values():
                    s = scores(rows, w, how, div)
                    for t, v in rows.items():
                        d = abs(s[t] - v[4])
                        hit += round(s[t], 2) == round(v[4], 2)
                        n += 1
                        worst = max(worst, d)
                print(f"{w}\t{how}\t{div}\t{hit}\t{n}\t{worst:.3f}")


if __name__ == "__main__":
    main()
