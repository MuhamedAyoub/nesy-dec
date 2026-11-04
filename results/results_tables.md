### Table E1. Within-pipeline results, on G with evaluate.py's definitions (primary)

Means over seeds where a method has several runs. Score is Eq. 5 as published (sample std, divided by 7) within each app's pool of these methods. Coverage is 1.00 for every row.

**jpetstore-6**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| NeSy-Rep + Ward | 1 | 4 | 0.93 | 3.25 | 0.43 | 0.25 | +0.68 |
| RoR-MSI clustering (teacher) | 1 | 4 | 0.74 | 3.50 | 0.36 | 0.50 | +0.34 |
| GraphRL-Dec, full | 3 | 4 | 0.74 | 3.50 | 0.36 | 0.50 | +0.34 |
| UnixCoder + Ward | 1 | 4 | 0.70 | 4.00 | 0.34 | 0.50 | +0.26 |
| NeSy-Rep + HDBSCAN | 1 | 1 | 0.39 | 0.00 | 0.00 | 1.00 | +0.15 |
| RLDec, CLI decode | 3 | 1 | 0.39 | 0.00 | 0.00 | 1.00 | +0.15 |
| random | 3 | 4 | 0.13 | 5.17 | 0.72 | 0.25 | -0.62 |
| RLDec, best training state | 3 | 5.3 | -0.05 | 2.87 | 0.37 | 0.58 | -0.63 |
| HierDec | 1 | 12 | 0.07 | 1.25 | 0.70 | 0.83 | -0.67 |

**acmeair**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| GraphRL-Dec, full | 3 | 11 | 0.66 | 4.73 | 0.47 | 0.27 | +0.68 |
| RoR-MSI clustering (teacher) | 1 | 11 | 0.65 | 4.73 | 0.47 | 0.27 | +0.67 |
| NeSy-Rep + Ward | 1 | 11 | 0.71 | 4.45 | 0.48 | 0.45 | +0.67 |
| UnixCoder + Ward | 1 | 11 | 0.33 | 5.18 | 0.59 | 0.36 | +0.11 |
| RLDec, CLI decode | 3 | 1 | 0.13 | 0.00 | 0.00 | 1.00 | +0.04 |
| RLDec, best training state | 3 | 12.3 | -0.01 | 4.90 | 0.80 | 0.55 | -0.53 |
| HierDec | 1 | 32 | -0.00 | 1.59 | 0.75 | 0.94 | -0.54 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.15 | 14.00 | 0.21 | 1.00 | -0.55 |
| random | 3 | 11 | -0.06 | 6.03 | 0.91 | 0.24 | -0.55 |

**daytrader7**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| GraphRL-Dec, full | 3 | 11 | 0.66 | 2.58 | 0.32 | 0.55 | +0.74 |
| NeSy-Rep + Ward | 1 | 11 | 0.47 | 2.27 | 0.46 | 0.27 | +0.47 |
| RoR-MSI clustering (teacher) | 1 | 11 | 0.49 | 2.55 | 0.25 | 0.55 | +0.45 |
| UnixCoder + Ward | 1 | 11 | 0.35 | 3.27 | 0.75 | 0.09 | +0.12 |
| NeSy-Rep + HDBSCAN | 1 | 3 | 0.18 | 1.67 | 0.03 | 0.67 | +0.02 |
| RLDec, CLI decode | 3 | 1 | 0.14 | 0.00 | 0.00 | 1.00 | -0.00 |
| HierDec | 1 | 62 | 0.11 | 0.44 | 0.90 | 0.97 | -0.44 |
| RLDec, best training state | 3 | 15.7 | 0.03 | 2.61 | 0.85 | 0.54 | -0.63 |
| random | 3 | 11 | -0.03 | 4.42 | 0.93 | 0.00 | -0.72 |

**plantsbywebsphere**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| RoR-MSI clustering (teacher) | 1 | 3 | 1.39 | 4.67 | 0.14 | 0.00 | +0.85 |
| GraphRL-Dec, full | 3 | 3 | 1.39 | 4.67 | 0.14 | 0.00 | +0.85 |
| RLDec, CLI decode | 3 | 1 | 0.66 | 0.00 | 0.00 | 1.00 | +0.29 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.69 | 6.00 | 0.18 | 0.50 | +0.05 |
| NeSy-Rep + Ward | 1 | 3 | 0.69 | 6.00 | 0.53 | 0.00 | +0.04 |
| RLDec, best training state | 3 | 7.3 | 0.20 | 2.76 | 0.63 | 0.60 | -0.39 |
| HierDec | 1 | 19 | 0.31 | 0.95 | 0.79 | 0.95 | -0.40 |
| random | 3 | 3 | 0.05 | 7.44 | 0.62 | 0.00 | -0.58 |
| UnixCoder + Ward | 1 | 3 | -0.24 | 5.67 | 0.64 | 0.00 | -0.70 |

**lit-jpetstore**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| GraphRL-Dec, full | 3 | 8 | 0.52 | 2.88 | 0.42 | 0.38 | +0.68 |
| RoR-MSI clustering (teacher) | 1 | 8 | 0.46 | 2.88 | 0.40 | 0.25 | +0.60 |
| NeSy-Rep + Ward | 1 | 8 | 0.43 | 3.38 | 0.56 | 0.12 | +0.46 |
| UnixCoder + Ward | 1 | 8 | 0.35 | 3.25 | 0.61 | 0.12 | +0.28 |
| RLDec, CLI decode | 3 | 1 | 0.12 | 0.00 | 0.00 | 1.00 | +0.11 |
| HierDec | 1 | 36 | 0.08 | 0.72 | 0.82 | 0.94 | -0.44 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.10 | 4.00 | 0.28 | 1.00 | -0.48 |
| RLDec, best training state | 3 | 12 | 0.07 | 2.51 | 0.75 | 0.72 | -0.53 |
| random | 3 | 8 | -0.00 | 4.17 | 0.88 | 0.04 | -0.68 |

**lit-pbw**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| RoR-MSI clustering (teacher) | 1 | 4 | 1.43 | 3.25 | 0.14 | 0.25 | +0.81 |
| GraphRL-Dec, full | 3 | 4 | 1.43 | 3.25 | 0.14 | 0.25 | +0.81 |
| RLDec, CLI decode | 3 | 1 | 0.63 | 0.00 | 0.00 | 1.00 | +0.30 |
| NeSy-Rep + Ward | 1 | 4 | 0.60 | 4.50 | 0.53 | 0.00 | +0.04 |
| RLDec, best training state | 3 | 4.3 | 0.42 | 1.65 | 0.20 | 0.90 | -0.02 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.28 | 5.00 | 0.40 | 0.00 | -0.17 |
| HierDec | 1 | 21 | 0.34 | 0.95 | 0.81 | 0.95 | -0.32 |
| UnixCoder + Ward | 1 | 4 | -0.22 | 4.75 | 0.71 | 0.00 | -0.64 |
| random | 3 | 4 | -0.28 | 5.50 | 0.81 | 0.08 | -0.81 |

### Table E2. Within-pipeline results, on G with RLDec's metric code (binarized SM)

Means over seeds where a method has several runs. Score is Eq. 5 as published (sample std, divided by 7) within each app's pool of these methods. Coverage is 1.00 for every row.

**jpetstore-6**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| NeSy-Rep + Ward | 1 | 4 | 0.19 | 3.25 | 0.42 | 0.25 | +0.93 |
| UnixCoder + Ward | 1 | 4 | 0.11 | 4.00 | 0.41 | 0.50 | +0.29 |
| RoR-MSI clustering (teacher) | 1 | 4 | 0.09 | 3.50 | 0.43 | 0.50 | +0.20 |
| GraphRL-Dec, full | 3 | 4 | 0.09 | 3.50 | 0.43 | 0.50 | +0.20 |
| NeSy-Rep + HDBSCAN | 1 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.09 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.09 |
| RLDec, best training state | 3 | 5.3 | -0.01 | 2.87 | 0.40 | 0.58 | -0.38 |
| random | 3 | 4 | 0.00 | 5.17 | 0.74 | 0.25 | -0.51 |
| HierDec | 1 | 12 | -0.01 | 1.25 | 0.69 | 0.83 | -0.55 |

**acmeair**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| NeSy-Rep + Ward | 1 | 11 | 0.17 | 4.45 | 0.53 | 0.45 | +0.69 |
| RoR-MSI clustering (teacher) | 1 | 11 | 0.15 | 4.73 | 0.57 | 0.27 | +0.61 |
| GraphRL-Dec, full | 3 | 11 | 0.15 | 4.73 | 0.58 | 0.27 | +0.59 |
| UnixCoder + Ward | 1 | 11 | 0.08 | 5.18 | 0.64 | 0.36 | +0.13 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.11 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.06 | 14.00 | 0.21 | 1.00 | -0.39 |
| RLDec, best training state | 3 | 12.3 | 0.01 | 4.90 | 0.80 | 0.55 | -0.44 |
| HierDec | 1 | 32 | 0.00 | 1.59 | 0.76 | 0.94 | -0.50 |
| random | 3 | 11 | -0.02 | 6.03 | 0.92 | 0.24 | -0.59 |

**daytrader7**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| RoR-MSI clustering (teacher) | 1 | 11 | 0.18 | 2.55 | 0.36 | 0.55 | +0.59 |
| GraphRL-Dec, full | 3 | 11 | 0.18 | 2.58 | 0.47 | 0.55 | +0.59 |
| NeSy-Rep + Ward | 1 | 11 | 0.14 | 2.27 | 0.52 | 0.27 | +0.44 |
| UnixCoder + Ward | 1 | 11 | 0.10 | 3.27 | 0.73 | 0.18 | +0.09 |
| NeSy-Rep + HDBSCAN | 1 | 3 | 0.06 | 1.67 | 0.06 | 0.67 | +0.07 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.18 |
| HierDec | 1 | 62 | 0.03 | 0.44 | 0.88 | 0.97 | -0.39 |
| RLDec, best training state | 3 | 15.7 | 0.01 | 2.61 | 0.82 | 0.54 | -0.55 |
| random | 3 | 11 | -0.01 | 4.42 | 0.93 | 0.00 | -0.66 |

**plantsbywebsphere**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| NeSy-Rep + Ward | 1 | 3 | 0.09 | 6.00 | 0.47 | 0.00 | +0.57 |
| RoR-MSI clustering (teacher) | 1 | 3 | 0.07 | 4.67 | 0.30 | 0.00 | +0.49 |
| GraphRL-Dec, full | 3 | 3 | 0.07 | 4.67 | 0.30 | 0.00 | +0.49 |
| RLDec, best training state | 3 | 7.3 | 0.06 | 2.76 | 0.63 | 0.60 | -0.01 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.05 | 6.00 | 0.29 | 0.50 | -0.06 |
| HierDec | 1 | 19 | 0.06 | 0.95 | 0.75 | 0.95 | -0.08 |
| UnixCoder + Ward | 1 | 3 | 0.04 | 5.67 | 0.52 | 0.00 | -0.18 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.33 |
| random | 3 | 3 | -0.01 | 7.44 | 0.65 | 0.00 | -0.90 |

**lit-jpetstore**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| NeSy-Rep + Ward | 1 | 8 | 0.15 | 3.38 | 0.55 | 0.12 | +0.63 |
| GraphRL-Dec, full | 3 | 8 | 0.14 | 2.88 | 0.50 | 0.38 | +0.57 |
| RoR-MSI clustering (teacher) | 1 | 8 | 0.13 | 2.88 | 0.48 | 0.25 | +0.54 |
| UnixCoder + Ward | 1 | 8 | 0.10 | 3.25 | 0.69 | 0.25 | +0.23 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.03 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.02 | 4.00 | 0.28 | 1.00 | -0.42 |
| HierDec | 1 | 36 | 0.01 | 0.72 | 0.82 | 0.94 | -0.42 |
| RLDec, best training state | 3 | 12 | 0.01 | 2.51 | 0.77 | 0.72 | -0.54 |
| random | 3 | 8 | 0.00 | 4.17 | 0.88 | 0.04 | -0.55 |

**lit-pbw**

| method | runs | services | SM | IFN | ICP | NED | Score |
|---|---|---|---|---|---|---|---|
| RoR-MSI clustering (teacher) | 1 | 4 | 0.14 | 3.25 | 0.31 | 0.25 | +0.67 |
| GraphRL-Dec, full | 3 | 4 | 0.14 | 3.25 | 0.31 | 0.25 | +0.67 |
| NeSy-Rep + Ward | 1 | 4 | 0.12 | 4.50 | 0.49 | 0.00 | +0.37 |
| RLDec, best training state | 3 | 4.3 | 0.07 | 1.65 | 0.25 | 0.90 | +0.08 |
| NeSy-Rep + HDBSCAN | 1 | 2 | 0.07 | 5.00 | 0.29 | 0.50 | -0.09 |
| HierDec | 1 | 21 | 0.07 | 0.95 | 0.77 | 0.95 | -0.17 |
| RLDec, CLI decode | 3 | 1 | 0.00 | 0.00 | 0.00 | 1.00 | -0.22 |
| UnixCoder + Ward | 1 | 4 | 0.01 | 4.75 | 0.63 | 0.00 | -0.51 |
| random | 3 | 4 | -0.01 | 5.50 | 0.76 | 0.08 | -0.80 |

### Table E3. GraphRL-Dec against its teacher

| app | GraphRL-Dec runs (8 variants x 3 seeds) | partition identical to the teacher's | different |
|---|---|---|---|
| jpetstore-6 | 24 | 24 | 0 |
| acmeair | 24 | 0 | 24 |
| daytrader7 | 24 | 0 | 24 |
| plantsbywebsphere | 24 | 24 | 0 |
| lit-jpetstore | 24 | 0 | 24 |
| lit-pbw | 24 | 24 | 0 |

### Table E4. Against Weerasinghe et al. 2026, Table 1 (pool of published tools plus ours, Eq. 5 as published)

Rank of each of our rows in the pool; the published rows' metric values are copied from Table 1. Our rows enter once per convention.

| app | benchmark | version set | our convention | pool | teacher | GraphRL-Dec full | NeSy-Rep + Ward | RLDec best | HierDec | best published row |
|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | JPetStore | footnote | weerasinghe | 14 | #3 (+0.60) | #2 (+0.60) | #1 (+1.04) | #11 (-0.37) | #10 (-0.36) | HDBScan #5 (+0.24) |
| jpetstore-6 | JPetStore | footnote | rldec | 14 | #9 (-0.13) | #8 (-0.13) | #2 (+0.62) | #13 (-0.67) | #14 (-0.76) | HDBScan #1 (+0.99) |
| acmeair | AcmeAir | both | weerasinghe | 15 | #4 (+0.47) | #3 (+0.51) | #2 (+0.58) | #15 (-0.97) | #14 (-0.81) | MEM #1 (+0.64) |
| acmeair | AcmeAir | both | rldec | 15 | #8 (-0.14) | #9 (-0.16) | #7 (-0.11) | #15 (-0.86) | #14 (-0.77) | MEM #1 (+0.90) |
| daytrader7 | DayTrader | both | weerasinghe | 15 | #5 (+0.40) | #1 (+0.75) | #6 (+0.31) | #14 (-0.75) | #15 (-0.84) | CoGCN #2 (+0.74) |
| daytrader7 | DayTrader | both | rldec | 15 | #5 (+0.10) | #7 (+0.06) | #6 (+0.09) | #14 (-0.64) | #15 (-0.78) | CoGCN #1 (+0.89) |
| plantsbywebsphere | Plants | footnote | weerasinghe | 15 | #2 (+1.16) | #1 (+1.16) | #7 (-0.22) | #15 (-0.59) | #13 (-0.44) | HDBScan #3 (+0.45) |
| plantsbywebsphere | Plants | footnote | rldec | 15 | #10 (-0.18) | #11 (-0.18) | #13 (-0.35) | #14 (-0.52) | #15 (-0.59) | HDBScan #1 (+1.11) |
| lit-jpetstore | JPetStore | literature | weerasinghe | 14 | #2 (+0.88) | #1 (+1.03) | #4 (+0.44) | #14 (-0.56) | #13 (-0.47) | HDBScan #3 (+0.48) |
| lit-jpetstore | JPetStore | literature | rldec | 14 | #6 (+0.21) | #5 (+0.22) | #3 (+0.30) | #14 (-0.87) | #13 (-0.72) | HDBScan #1 (+1.05) |
| lit-pbw | Plants | literature | weerasinghe | 15 | #2 (+1.17) | #1 (+1.17) | #10 (-0.31) | #6 (-0.12) | #14 (-0.50) | HDBScan #3 (+0.43) |
| lit-pbw | Plants | literature | rldec | 15 | #7 (-0.08) | #8 (-0.08) | #12 (-0.26) | #13 (-0.33) | #15 (-0.64) | HDBScan #1 (+1.12) |
