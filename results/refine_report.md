### Refinement against the teacher (same nine-method pool)

| app | sizes | evaluate | rldec | weerasinghe (held out) |
|---|---|---|---|---|
| jpetstore-6 | 11 6 5 2 | +0.71 vs +0.24 (SM 1.05 vs 0.74) | +0.50 vs +0.15 (SM 0.13 vs 0.09) | +0.72 vs +0.24 (SM 0.78 vs 0.54) |
| acmeair | 16 8 7 6 6 5 5 5 5 5 2 | +0.92 vs +0.56 (SM 0.89 vs 0.65) | +0.88 vs +0.50 (SM 0.21 vs 0.15) | +0.77 vs +0.58 (SM 0.50 vs 0.42) |
| daytrader7 | 48 18 5 5 5 5 5 5 3 3 2 | +0.85 vs +0.45 (SM 0.63 vs 0.49) | +0.87 vs +0.51 (SM 0.21 vs 0.18) | +0.90 vs +0.44 (SM 0.42 vs 0.31) |
| plantsbywebsphere | 16 14 5 | +1.04 vs +0.73 (SM 1.82 vs 1.39) | +0.70 vs +0.45 (SM 0.09 vs 0.07) | +1.10 vs +0.77 (SM 1.56 vs 1.17) |
| lit-jpetstore | 19 19 10 5 5 5 5 3 | +1.02 vs +0.46 (SM 0.72 vs 0.46) | +0.83 vs +0.47 (SM 0.17 vs 0.13) | +1.09 vs +0.54 (SM 0.58 vs 0.36) |
| lit-pbw | 19 10 5 2 | +0.96 vs +0.73 (SM 1.71 vs 1.43) | +0.81 vs +0.62 (SM 0.16 vs 0.14) | +1.00 vs +0.77 (SM 1.44 vs 1.19) |

### Rank in the published pools (Weerasinghe Table 1 plus ours)

| app | benchmark | convention | pool | refinement | teacher | top row |
|---|---|---|---|---|---|---|
| jpetstore-6 | JPetStore | weerasinghe | 15 | #1 | #3 | local_search_dual |
| jpetstore-6 | JPetStore | rldec | 15 | #5 | #10 | published:HDBScan |
| acmeair | AcmeAir | weerasinghe | 16 | #1 | #6 | local_search_dual |
| acmeair | AcmeAir | rldec | 16 | #6 | #9 | published:MEM |
| daytrader7 | DayTrader | weerasinghe | 16 | #1 | #6 | local_search_dual |
| daytrader7 | DayTrader | rldec | 16 | #4 | #6 | published:CoGCN |
| plantsbywebsphere | Plants | weerasinghe | 16 | #1 | #2 | local_search_dual |
| plantsbywebsphere | Plants | rldec | 16 | #7 | #11 | published:HDBScan |
| lit-jpetstore | JPetStore | weerasinghe | 15 | #1 | #3 | local_search_dual |
| lit-jpetstore | JPetStore | rldec | 15 | #2 | #7 | published:HDBScan |
| lit-pbw | Plants | weerasinghe | 16 | #1 | #2 | local_search_dual |
| lit-pbw | Plants | rldec | 16 | #5 | #8 | published:HDBScan |
