### F1. The three apps with cannot-link pairs

`kl0` is the setting chosen by `results/recon/setting_selection.py` (no KL anchor, 2,000 episodes). The best repair is the one of the three with the highest evaluate Score.

| app | method | runs | cannot-link violations | must-link kept | semantic cohesion | Score, evaluate | Score, rldec | Score, weerasinghe |
|---|---|---|---|---|---|---|---|---|
| acmeair | RoR-MSI teacher | 1 | 2 | 0.538 | 0.453 | +0.67 | +0.61 | +0.64 |
| acmeair | GraphRL-Dec full, paper setting | 3 | 0 | 0.538 | 0.432 | +0.68 | +0.59 | +0.66 |
| acmeair | best repair of the teacher (repair_post) | 1 | 0 | 0.615 | 0.440 | +0.70 | +0.63 | +0.70 |
| acmeair | GraphRL-Dec full, kl0 | 3 | 0 | 0.564 | 0.406 | +0.66 | +0.48 | +0.65 |
| acmeair | GraphRL-Dec structural, kl0 | 3 | 0 | 0.538 | 0.417 | +0.65 | +0.54 | +0.61 |
| acmeair | NeSy-Rep + Ward | 1 | 11 | 0.615 | 0.634 | +0.66 | +0.65 | +0.68 |
| acmeair | best repair of NeSy-Rep + Ward (repair_nesyward_connect) | 1 | 0 | 0.615 | 0.564 | +0.71 | +0.67 | +0.74 |
| acmeair | GraphRL-Dec full from NeSy-Rep + Ward, paper setting | 3 | 0 | 0.615 | 0.564 | +0.33 | +0.56 | +0.24 |
| acmeair | GraphRL-Dec full from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.641 | 0.457 | +0.41 | +0.27 | +0.30 |
| acmeair | GraphRL-Dec structural from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.615 | 0.433 | +0.57 | +0.23 | +0.58 |
| daytrader7 | RoR-MSI teacher | 1 | 118 | 0.732 | 0.356 | +0.54 | +0.60 | +0.57 |
| daytrader7 | GraphRL-Dec full, paper setting | 3 | 0 | 0.585 | 0.435 | +0.74 | +0.59 | +0.80 |
| daytrader7 | best repair of the teacher (repair_masked) | 1 | 0 | 0.585 | 0.419 | +0.77 | +0.60 | +0.83 |
| daytrader7 | GraphRL-Dec full, kl0 | 3 | 0 | 0.675 | 0.437 | +0.89 | +0.66 | +0.90 |
| daytrader7 | GraphRL-Dec structural, kl0 | 3 | 0 | 0.667 | 0.425 | +0.81 | +0.20 | +0.92 |
| daytrader7 | NeSy-Rep + Ward | 1 | 32 | 0.634 | 0.608 | +0.57 | +0.50 | +0.46 |
| daytrader7 | best repair of NeSy-Rep + Ward (repair_nesyward_post) | 1 | 0 | 0.683 | 0.590 | +0.55 | +0.50 | +0.38 |
| daytrader7 | GraphRL-Dec full from NeSy-Rep + Ward, paper setting | 3 | 0 | 0.683 | 0.591 | +0.56 | +0.49 | +0.40 |
| daytrader7 | GraphRL-Dec full from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.683 | 0.594 | +0.56 | +0.50 | +0.40 |
| daytrader7 | GraphRL-Dec structural from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.683 | 0.594 | +0.56 | +0.50 | +0.40 |
| lit-jpetstore | RoR-MSI teacher | 1 | 10 | 0.568 | 0.456 | +0.64 | +0.55 | +0.75 |
| lit-jpetstore | GraphRL-Dec full, paper setting | 3 | 0 | 0.568 | 0.453 | +0.68 | +0.57 | +0.81 |
| lit-jpetstore | best repair of the teacher (repair_masked) | 1 | 0 | 0.568 | 0.437 | +0.66 | +0.53 | +0.81 |
| lit-jpetstore | GraphRL-Dec full, kl0 | 3 | 0 | 0.561 | 0.460 | +0.75 | +0.64 | +0.87 |
| lit-jpetstore | GraphRL-Dec structural, kl0 | 3 | 0 | 0.788 | 0.451 | +0.76 | +0.43 | +0.90 |
| lit-jpetstore | NeSy-Rep + Ward | 1 | 0 | 0.773 | 0.686 | +0.51 | +0.61 | +0.42 |
| lit-jpetstore | best repair of NeSy-Rep + Ward (repair_nesyward_masked) | 1 | 0 | 0.773 | 0.686 | +0.51 | +0.61 | +0.42 |
| lit-jpetstore | GraphRL-Dec full from NeSy-Rep + Ward, paper setting | 3 | 0 | 0.773 | 0.686 | +0.51 | +0.61 | +0.42 |
| lit-jpetstore | GraphRL-Dec full from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.758 | 0.665 | +0.54 | +0.60 | +0.47 |
| lit-jpetstore | GraphRL-Dec structural from NeSy-Rep + Ward, kl0 | 3 | 0 | 0.788 | 0.672 | +0.55 | +0.62 | +0.47 |

### F2. All six apps: the kl0 setting against the paper setting, every variant

Cells: kl0 Score minus paper-setting Score, evaluate / rldec / weerasinghe, each scored in place of GraphRL-Dec full; means over 3 seeds.

| app | structural | semantic | affinity | noise | full | fullC2 | fullC1 | fullC1C2 |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | +0.23 / +0.18 / +0.16 | -0.03 / -0.22 / -0.13 | +0.22 / +0.05 / +0.08 | +0.22 / +0.18 / +0.10 | +0.18 / +0.12 / +0.10 | +0.05 / -0.04 / -0.01 | +0.28 / +0.17 / +0.16 | +0.25 / +0.14 / +0.15 |
| acmeair | -0.04 / -0.05 / -0.05 | +0.00 / +0.00 / +0.00 | +0.01 / -0.08 / +0.01 | -0.04 / -0.09 / -0.03 | -0.03 / -0.12 / -0.01 | -0.02 / -0.07 / +0.03 | +0.03 / -0.04 / +0.03 | -0.04 / -0.10 / -0.04 |
| daytrader7 | +0.07 / -0.40 / +0.12 | +0.03 / -0.43 / +0.05 | +0.01 / -0.09 / +0.02 | +0.03 / -0.07 / +0.04 | +0.15 / +0.07 / +0.10 | +0.00 / +0.00 / +0.00 | +0.08 / -0.04 / +0.05 | +0.00 / +0.00 / +0.00 |
| plantsbywebsphere | +0.16 / +0.08 / +0.16 | +0.05 / +0.08 / +0.05 | +0.19 / -0.01 / +0.16 | +0.17 / +0.18 / +0.17 | +0.16 / +0.08 / +0.16 | +0.03 / -0.03 / +0.01 | +0.13 / +0.14 / +0.12 | +0.12 / +0.08 / +0.12 |
| lit-jpetstore | +0.08 / -0.15 / +0.09 | +0.10 / -0.08 / +0.11 | +0.03 / -0.06 / +0.03 | +0.07 / +0.02 / +0.07 | +0.07 / +0.06 / +0.06 | +0.00 / +0.00 / +0.00 | -0.08 / -0.10 / -0.11 | +0.00 / +0.00 / +0.00 |
| lit-pbw | -0.04 / -0.15 / -0.03 | -0.01 / -0.07 / -0.01 | +0.01 / -0.02 / +0.01 | +0.05 / -0.09 / +0.06 | +0.02 / -0.37 / +0.04 | -0.03 / -0.25 / -0.02 | +0.06 / -0.34 / +0.07 | +0.02 / -0.18 / +0.03 |

kl0 above the paper setting: evaluate 33 of 48, rldec 15 of 48, weerasinghe 33 of 48 (app, variant) pairs.

### F3. Cannot-link violations of every kl0 and NeSy-Rep-start run

108 runs on the apps with cannot-link pairs; 0 with any violation.
