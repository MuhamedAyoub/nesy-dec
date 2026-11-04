### J1. Java subjects

| system | version set | classes | services K (RoR-MSI) | must-link | cannot-link |
|---|---|---|---|---|---|
| JPetStore 6 | footnote | 24 | 4 | 12 | 0 |
| AcmeAir | both | 70 | 11 | 13 | 169 |
| DayTrader 7 | both | 104 | 11 | 41 | 684 |
| Plants | footnote | 35 | 3 | 38 | 0 |
| JPetStore (lit.) | literature | 71 | 8 | 44 | 352 |
| Plants (lit.) | literature | 36 | 4 | 37 | 0 |

### J2. Decomposition quality on the resolved graph (evaluate.py), raw composite U; GraphRL-Dec is the mean of 3 seeds

| system | method | SM | IFN | ICP | NED | U | max |m| |
|---|---|---|---|---|---|---|---|
| JPetStore 6 | GraphRL-Dec | 0.736 | 3.50 | 0.357 | 0.500 | +0.080 | 11 |
| JPetStore 6 | RoR-MSI | 0.736 | 3.50 | 0.357 | 0.500 | +0.080 | 11 |
| JPetStore 6 | UnixCoder+Ward | 0.929 | 3.25 | 0.432 | 0.250 | +0.216 | 9 |
| AcmeAir | GraphRL-Dec | 0.664 | 4.73 | 0.471 | 0.273 | +0.136 | 11 |
| AcmeAir | RoR-MSI | 0.648 | 4.73 | 0.466 | 0.273 | +0.129 | 11 |
| AcmeAir | UnixCoder+Ward | 0.711 | 4.45 | 0.483 | 0.455 | +0.132 | 13 |
| DayTrader 7 | GraphRL-Dec | 0.662 | 2.58 | 0.320 | 0.545 | +0.148 | 40 |
| DayTrader 7 | RoR-MSI | 0.487 | 2.55 | 0.254 | 0.545 | +0.072 | 40 |
| DayTrader 7 | UnixCoder+Ward | 0.467 | 2.27 | 0.456 | 0.273 | +0.078 | 22 |
| Plants | GraphRL-Dec | 1.386 | 4.67 | 0.137 | 0.000 | +0.411 | 17 |
| Plants | RoR-MSI | 1.386 | 4.67 | 0.137 | 0.000 | +0.411 | 17 |
| Plants | UnixCoder+Ward | 0.687 | 6.00 | 0.529 | 0.000 | -0.078 | 15 |
| JPetStore (lit.) | GraphRL-Dec | 0.516 | 2.88 | 0.418 | 0.375 | +0.066 | 15 |
| JPetStore (lit.) | RoR-MSI | 0.457 | 2.88 | 0.405 | 0.250 | +0.059 | 16 |
| JPetStore (lit.) | UnixCoder+Ward | 0.428 | 3.38 | 0.559 | 0.125 | +0.030 | 12 |
| Plants (lit.) | GraphRL-Dec | 1.432 | 3.25 | 0.144 | 0.250 | +0.515 | 19 |
| Plants (lit.) | RoR-MSI | 1.432 | 3.25 | 0.144 | 0.250 | +0.515 | 19 |
| Plants (lit.) | UnixCoder+Ward | 0.598 | 4.50 | 0.530 | 0.000 | +0.023 | 11 |

### J3. GraphRL-Dec runs whose partition equals the teacher's, per setting (6 apps x 3 seeds unless noted)

| setting | runs | identical to teacher |
|---|---|---|
| main sweep, all 8 variants (paper settings) | 144 | 72 |
| no KL anchor, 2,000 episodes (structural, full) | 36 | 1 |
| no behaviour-cloning warm start (structural, full) | 36 | 0 |

### J4. Must-link satisfaction (share of must-link pairs placed in one service)

| system | must-link pairs | GraphRL-Dec | RoR-MSI | UnixCoder+Ward |
|---|---|---|---|---|
| JPetStore 6 | 12 | 0.583 | 0.583 | 0.833 |
| AcmeAir | 13 | 0.538 | 0.538 | 0.615 |
| DayTrader 7 | 41 | 0.585 | 0.732 | 0.634 |
| Plants | 38 | 0.579 | 0.579 | 0.579 |
| JPetStore (lit.) | 44 | 0.568 | 0.568 | 0.773 |
| Plants (lit.) | 37 | 0.514 | 0.514 | 0.568 |

### J5. Cannot-link violations (pairs of rule CL-SIBLING placed in one service; mean over seeds where a method has several)

| system | cannot-link pairs | GraphRL-Dec | RoR-MSI | UnixCoder+Ward (NeSy-Rep) | UnixCoder+Ward (pretrained) | HierDec | RLDec (best state) | RLDec (CLI) |
|---|---|---|---|---|---|---|---|---|
| AcmeAir | 169 | 0 | 2 | 11 | 21 | 13 | 25.7 (18 to 35) | 169 |
| DayTrader 7 | 684 | 0 | 118 | 32 | 12 | 0 | 42.0 (21 to 71) | 684 |
| JPetStore (lit.) | 352 | 0 | 10 | 0 | 110 | 18 | 52.7 (12 to 98) | 352 |
