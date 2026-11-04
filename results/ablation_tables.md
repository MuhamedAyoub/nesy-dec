### Table E5. GraphRL-Dec ablations (run_gpu.ABLATIONS) in place of GraphRL-Dec full

Each ablation family replaces GraphRL-Dec full in the nine-method pool of Tables E1 and E2; Score and rank are within that pool. Means over 3 seeds.

| app | ablation | variant | identical to teacher | SM | ICP | NED | Score, evaluate | Score, rldec convention |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | kl0_ep2000 | full | 0/3 | 0.93 | 0.36 | 0.50 | +0.52 (#2; teacher +0.29) | +0.32 (#2; teacher +0.18) |
| jpetstore-6 | kl0_ep2000 | structural | 0/3 | 0.88 | 0.36 | 0.25 | +0.57 (#2; teacher +0.29) | +0.38 (#2; teacher +0.17) |
| jpetstore-6 | nobc_ep2000 | full | 0/3 | 0.39 | 0.00 | 1.00 | +0.15 (#6; teacher +0.39) | -0.08 (#6; teacher +0.24) |
| jpetstore-6 | nobc_ep2000 | structural | 0/3 | 0.39 | 0.00 | 1.00 | +0.15 (#6; teacher +0.39) | -0.08 (#6; teacher +0.24) |
| acmeair | kl0_ep2000 | full | 0/3 | 0.67 | 0.51 | 0.30 | +0.66 (#3; teacher +0.67) | +0.48 (#3; teacher +0.64) |
| acmeair | kl0_ep2000 | structural | 0/3 | 0.64 | 0.50 | 0.24 | +0.65 (#3; teacher +0.68) | +0.54 (#3; teacher +0.62) |
| acmeair | nobc_ep2000 | full | 0/3 | 0.00 | 0.00 | 1.00 | -0.11 (#5; teacher +0.80) | -0.09 (#5; teacher +0.72) |
| acmeair | nobc_ep2000 | structural | 0/3 | -0.04 | 0.42 | 0.80 | -0.64 (#9; teacher +0.87) | -0.69 (#9; teacher +0.78) |
| daytrader7 | kl0_ep2000 | full | 0/3 | 0.91 | 0.29 | 0.62 | +0.89 (#1; teacher +0.33) | +0.66 (#1; teacher +0.54) |
| daytrader7 | kl0_ep2000 | structural | 0/3 | 0.84 | 0.33 | 0.65 | +0.81 (#1; teacher +0.36) | +0.20 (#3; teacher +0.73) |
| daytrader7 | nobc_ep2000 | full | 0/3 | 0.19 | 0.04 | 1.00 | -0.10 (#6; teacher +0.68) | -0.27 (#6; teacher +0.79) |
| daytrader7 | nobc_ep2000 | structural | 0/3 | 0.32 | 0.12 | 1.00 | -0.12 (#6; teacher +0.70) | -0.50 (#8; teacher +0.85) |
| plantsbywebsphere | kl0_ep2000 | full | 0/3 | 1.77 | 0.15 | 0.00 | +1.01 (#1; teacher +0.74) | +0.58 (#1; teacher +0.48) |
| plantsbywebsphere | kl0_ep2000 | structural | 0/3 | 1.82 | 0.14 | 0.00 | +1.01 (#1; teacher +0.73) | +0.58 (#1; teacher +0.47) |
| plantsbywebsphere | nobc_ep2000 | full | 0/3 | 0.66 | 0.00 | 1.00 | +0.35 (#3; teacher +1.03) | -0.26 (#8; teacher +0.55) |
| plantsbywebsphere | nobc_ep2000 | structural | 0/3 | 0.66 | 0.00 | 1.00 | +0.35 (#3; teacher +1.03) | -0.26 (#8; teacher +0.55) |
| lit-jpetstore | kl0_ep2000 | full | 0/3 | 0.56 | 0.41 | 0.38 | +0.75 (#1; teacher +0.58) | +0.64 (#1; teacher +0.52) |
| lit-jpetstore | kl0_ep2000 | structural | 0/3 | 0.61 | 0.44 | 0.42 | +0.76 (#1; teacher +0.55) | +0.43 (#3; teacher +0.57) |
| lit-jpetstore | nobc_ep2000 | full | 0/3 | 0.10 | 0.00 | 1.00 | +0.05 (#5; teacher +0.76) | -0.06 (#5; teacher +0.64) |
| lit-jpetstore | nobc_ep2000 | structural | 0/3 | 0.08 | 0.15 | 0.50 | -0.21 (#5; teacher +0.79) | -0.14 (#5; teacher +0.68) |
| lit-pbw | kl0_ep2000 | full | 0/3 | 1.53 | 0.15 | 0.08 | +0.84 (#1; teacher +0.78) | +0.30 (#3; teacher +0.78) |
| lit-pbw | kl0_ep2000 | structural | 1/3 | 1.36 | 0.15 | 0.17 | +0.77 (#2; teacher +0.83) | +0.51 (#2; teacher +0.73) |
| lit-pbw | nobc_ep2000 | full | 0/3 | 0.63 | 0.00 | 1.00 | +0.37 (#3; teacher +1.00) | -0.18 (#7; teacher +0.80) |
| lit-pbw | nobc_ep2000 | structural | 0/3 | 0.63 | 0.00 | 1.00 | +0.37 (#3; teacher +1.00) | -0.18 (#7; teacher +0.80) |
