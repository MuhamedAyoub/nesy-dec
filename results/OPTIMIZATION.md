# Optimization experiments after the main run

Date: 2026-10-26, updated 2026-11-03. Section 1 was measured before the
fact base had cannot-link pairs and was not repeated: its outputs and
`idea1_report.md` refer to the archived run
(`results/_archive/pre_cl_sibling_2026-10-26/`). Sections 2 and 3 were
recomputed on 2026-11-03 against the current outputs. All of this ran on
this machine: the RTX 3060 through the
`develop` environment for GraphRL-Dec, the CPU for the rest. Each number
traces to the file named beside it.

## 1. Idea 1: a dual reward for GraphRL-Dec

The reward is the mean of the evaluate and rldec z-scores
(`java_pipeline/dual_reward.py`). The weerasinghe convention is held out.
Results are in `results/idea1_report.md` (per seed, scored in the
nine-method pool).

- With the paper's KL anchor, it reproduces the teacher in 3 of 3 runs on
  jpetstore-6.
- Without the anchor (`dual_kl0_ep2000`), it beats the teacher on the
  held-out convention in 7 of 18 runs (`full`) and 5 of 18 (`structural`).
  The old reward without the anchor did so in 9 and 11 of 18.
- On AcmeAir and DayTrader it returns to the teacher's exact partition in
  all 6 runs of each.
- The jpetstore-6 gain (3 of 3 held out) does not generalise.

## 2. Hill-climbing on the dual objective

The search makes single-class moves under the RL environment's size cap
(`java_pipeline/local_search.py`).

- **From the teacher.** It beats the teacher on all six apps in all three
  conventions (`results/refine_report.md`).
- **From random partitions.** It ends above the teacher on the held-out
  convention in all 18 runs, and above the search from the teacher in 12
  (`results/refine_checks.md`, section 3). Ranked in the published
  pools, a random partition hill-climbed this way is #1 in 18 of 18 runs on
  weighted calls, and between #2 and #9 on binarized SM. The random
  partitions alone rank between #1 and #10, mostly last
  (`results/gaming_check.md`). On the three apps with cannot-link
  pairs, the hill-climbed random partitions violate 8 to 91 of them.
- **Moves.** Some are sensible: on jpetstore-6, `Item` and `Product` move to
  the catalog service. Some are not: on DayTrader, benchmark servlets such
  as `PingJDBCRead` move into the account-data service
  (`refine_checks.md`, section 1).
- **Measures outside the objective** (`refine_checks.md`, section 2).
  - NeSy-Rep embedding similarity rises slightly on 5 apps and falls on
    lit-jpetstore.
  - Must-link facts kept together rise on 5 apps and fall on AcmeAir.
  - The data-entity measures cannot tell the partitions apart, because D is
    too sparse.

Conclusion: these gains are optimization of the metric family itself. The
held-out convention is computed with the same formulas on a subgraph of G,
so it is not independent. The refinement is not evidence of better
architecture, and it is not reported as a method.

## 3. Why our rows rank lower under binarized SM

Binarized SM is the density of dependencies inside each service: distinct
internal edges divided by m². Two causes, measured on the refined
partitions:

- **Self-calls.** RLDec's metric code keeps the diagonal, and our G has no
  self-edges. Adding a self-edge for each class that calls its own methods
  raises binarized SM:

  | app | without self-calls | with self-calls |
  |---|---|---|
  | lit-pbw | 0.16 | 0.30 |
  | DayTrader | 0.21 | 0.30 |
  | lit-jpetstore | 0.17 | 0.20 |
  | AcmeAir | 0.21 | 0.23 |

  Source: `results/recon/binarized_selfcalls.py` and its `.out` file.
- **Density rewards tiny services.** Our graphs have a density of 0.028 to
  0.077. A 9-class service then has an internal density of about 0.2, while
  a 2-class service with one edge has 0.25. Eq. 5 weights SM 3 to 1, so
  tools with many tiny services score high. The published HDBScan row fits
  this: NED 0.70 to 0.90, SM 0.22 to 0.60.

## 4. Resolver layers

The teacher was run on graphs built from subsets of the resolver's layers
(`java_pipeline/layer_ablation.py`, `results/layer_ablation.csv`).

- On the naive graph, 21 of AcmeAir's 70 classes, 13 of DayTrader's 104 and
  7 of lit-jpetstore's 71 are isolated, so they cannot be placed. On the
  full graph, all of them are placed.
- Plants and lit-pbw change little, because their naive graphs are already
  well connected.

## 5. What this means

Eq. 5 on SM, IFN, ICP and NED can be optimized directly by search. Once that
is done on the graph the scores are computed on, a decomposition with no
architectural knowledge outranks every published tool. Three consequences:

- Comparisons across papers on these metrics cannot establish
  state-of-the-art quality.
- Within one pipeline, a method that optimizes Eq. 5 on G wins by
  construction.
- Evidence of decomposition quality needs a criterion the method does not
  optimize, such as an expert reference decomposition, or architectural
  constraints the metric does not see. Cannot-link compliance is one: the
  hill-climbed partitions top the pools and violate the constraints, while
  GraphRL-Dec violates none (RESULTS.md, sections 4 and 6.2).
