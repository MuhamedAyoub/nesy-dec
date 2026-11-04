#!/usr/bin/env python3
"""Which weights and normalisation does Weerasinghe's Score column imply?

For each benchmark, z-score the four metric columns over that benchmark's
pool, then least-squares fit Score = sum_m b_m z_m (no intercept, since
z-scores have mean 0, and so does Score if computed as Eq. 5). The implied
b_m * 6 should be (3, -1, -1, -1) if Eq. 5 was applied as written. Also
reports the fit residual and whether the published Scores sum to ~0 per
benchmark, which Eq. 5 forces (sum of z over a pool is 0).

Usage: python3 eq5_implied_weights.py > eq5_implied_weights.out
"""
import numpy as np
from eq5_reproduce import TABLE1

for norm in ("pop", "sample"):
    print(f"== std={norm}")
    print("benchmark\tsum_published_score\timplied_6b(SM,IFN,ICP,NED)\tmax_resid")
    for app, rows in TABLE1.items():
        X = np.array([v[:4] for v in rows.values()], float)
        y = np.array([v[4] for v in rows.values()], float)
        Z = (X - X.mean(0)) / X.std(0, ddof=0 if norm == "pop" else 1)
        b, *_ = np.linalg.lstsq(Z, y, rcond=None)
        r = np.abs(Z @ b - y).max()
        print(f"{app}\t{y.sum():+.2f}\t{np.round(6 * b, 2).tolist()}\t{r:.3f}")


def exact_check():
    """Test the hypothesis the fit suggests: sample std, divide by D."""
    print("\n== exact reproduction at 2 decimals: W=(3,-1,-1,-1), z with sample std")
    print("divisor\treproduced\ttotal\tmax_abs_diff")
    W = np.array([3, -1, -1, -1], float)
    for D in (6, 6.5, 7, 7.5):
        hit = n = 0
        worst = 0.0
        for rows in TABLE1.values():
            X = np.array([v[:4] for v in rows.values()], float)
            y = np.array([v[4] for v in rows.values()], float)
            s = ((X - X.mean(0)) / X.std(0, ddof=1)) @ W / D
            hit += int((np.round(s, 2) == np.round(y, 2)).sum())
            n += len(y)
            worst = max(worst, float(np.abs(s - y).max()))
        print(f"{D}\t{hit}\t{n}\t{worst:.3f}")


exact_check()
