Measured on 2026-10-26, before the fact base had cannot-link pairs; the partitions are in
`results/_archive/pre_cl_sibling_2026-10-26/_nesy/rl_ablation/dual_*`. Not repeated.

### Idea 1: per-seed Score against the teacher (seed runs scored one at a time in the nine-method pool)

Cells: seeds where the run's Score exceeds the teacher's / seeds run; mean Score delta (run minus teacher).

| app | setting | evaluate | rldec | weerasinghe |
|---|---|---|---|---|
| jpetstore-6 | dual reward, no anchor, full | 3/3; +0.35 | 3/3; +0.25 | 3/3; +0.20 |
| jpetstore-6 | dual reward, no anchor, structural | 3/3; +0.31 | 3/3; +0.34 | 0/3; -0.05 |
| jpetstore-6 | old reward, no anchor, full | 2/3; +0.18 | 2/3; -0.10 | 2/3; +0.07 |
| jpetstore-6 | old reward, no anchor, structural | 3/3; +0.31 | 2/3; +0.20 | 1/3; +0.02 |
| jpetstore-6 | dual reward, paper's anchor, full | 0/3; +0.00 | 0/3; +0.00 | 0/3; +0.00 |
| acmeair | dual reward, no anchor, full | 0/3; +0.00 | 0/3; -0.00 | 0/3; +0.00 |
| acmeair | dual reward, no anchor, structural | 0/3; +0.00 | 0/3; -0.00 | 0/3; +0.00 |
| acmeair | old reward, no anchor, full | 0/3; +0.00 | 0/3; -0.00 | 0/3; +0.00 |
| acmeair | old reward, no anchor, structural | 0/3; -0.04 | 0/3; -0.10 | 0/3; -0.02 |
| daytrader7 | dual reward, no anchor, full | 0/3; +0.00 | 0/3; -0.00 | 0/3; +0.00 |
| daytrader7 | dual reward, no anchor, structural | 0/3; +0.00 | 0/3; -0.00 | 0/3; +0.00 |
| daytrader7 | old reward, no anchor, full | 2/3; +0.11 | 0/3; -0.20 | 1/3; -0.03 |
| daytrader7 | old reward, no anchor, structural | 3/3; +0.40 | 0/3; -0.85 | 3/3; +0.39 |
| plantsbywebsphere | dual reward, no anchor, full | 2/3; +0.12 | 2/3; +0.02 | 2/3; +0.10 |
| plantsbywebsphere | dual reward, no anchor, structural | 3/3; +0.29 | 3/3; +0.08 | 3/3; +0.31 |
| plantsbywebsphere | old reward, no anchor, full | 3/3; +0.29 | 2/3; +0.14 | 3/3; +0.27 |
| plantsbywebsphere | old reward, no anchor, structural | 3/3; +0.21 | 2/3; +0.06 | 3/3; +0.23 |
| lit-jpetstore | dual reward, no anchor, full | 2/3; +0.14 | 1/3; +0.06 | 2/3; +0.17 |
| lit-jpetstore | dual reward, no anchor, structural | 1/3; +0.04 | 0/3; -0.01 | 1/3; +0.06 |
| lit-jpetstore | old reward, no anchor, full | 1/3; -0.06 | 1/3; -0.09 | 2/3; -0.07 |
| lit-jpetstore | old reward, no anchor, structural | 3/3; +0.15 | 2/3; -0.03 | 3/3; +0.20 |
| lit-pbw | dual reward, no anchor, full | 0/3; +0.00 | 0/3; +0.00 | 0/3; +0.00 |
| lit-pbw | dual reward, no anchor, structural | 1/3; +0.05 | 0/3; -0.02 | 1/3; +0.06 |
| lit-pbw | old reward, no anchor, full | 1/3; -0.01 | 0/3; -0.21 | 1/3; +0.01 |
| lit-pbw | old reward, no anchor, structural | 1/3; -0.04 | 0/3; -0.08 | 1/3; -0.04 |

### Totals over the apps run

| setting | evaluate | rldec | weerasinghe |
|---|---|---|---|
| dual reward, no anchor, full | 7/18 | 6/18 | 7/18 |
| dual reward, no anchor, structural | 8/18 | 6/18 | 5/18 |
| old reward, no anchor, full | 9/18 | 5/18 | 9/18 |
| old reward, no anchor, structural | 13/18 | 6/18 | 11/18 |
| dual reward, paper's anchor, full | 0/3 | 0/3 | 0/3 |
