# Phase 7: results on the Java benchmarks

Date: 2026-11-03. This replaces the version of 2026-10-26, which was computed
before the Java fact base had cannot-link pairs. The runs are those in
RUNS.md: the encoder, 144 GraphRL-Dec runs and 72 ablation runs on the GPU
server on 2026-11-03, the 18 RLDec runs of 2026-10-26 (RLDec reads no fact
base, so they were kept), and the CPU baselines on this machine. The outputs
of the earlier run are in `results/_archive/pre_cl_sibling_2026-10-26/`.

Every number comes from `results/results/metrics.csv`, `composite.csv`
and `external.csv`, which `python3 -m java_pipeline.results` builds from the
partitions on disk. The tables are rendered by
`java_pipeline/results_tables.py` into `results/results_tables.md` and
`ablation_tables.md`, and by `java_pipeline/paper_tables.py` into
`paper_tables.md`. They are inserted here unchanged.

## 1. Setup in brief

- **Class sets.** All methods partition the same class set per app, the
  active classes of G (24 to 104 classes), and every method covers all of
  them (coverage 1.00).
- **Graph.** All methods read the same G: our resolved graph (RESOLVER.md).
  HierDec and RLDec get it in their own input formats.
- **Metrics.** One piece of code (`java_pipeline/metrics.py`) scores every
  partition, in three conventions:
  - evaluate: `vendor/ror_msi/evaluate.py`'s definitions on G. This is the primary one.
  - rldec: RLDec's metric code on G. SM is binarized and self-loops are kept.
  - weerasinghe: Eq. 1 to 4 on the call graph.
- **Composite.** Eq. 5 in the form that reproduces Weerasinghe's published
  Score column: sample std, divided by 7. It is computed within each app's
  pool of nine methods.

The methods:

| method | what it is |
|---|---|
| RoR-MSI clustering (teacher) | Paper 1's dual-objective clustering on G and D, α = 0.9 |
| GraphRL-Dec, full | Paper 2's RL decomposer: the full reward, warm-started from the teacher; 3 seeds |
| NeSy-Rep + Ward | Ward clustering of the fine-tuned NeSy-Rep embeddings, K = teacher K |
| UnixCoder + Ward | the same with pretrained, not fine-tuned, UnixCoder |
| NeSy-Rep + HDBSCAN | HDBSCAN on the fine-tuned embeddings, automatic K |
| HierDec | decomp-hydec, static pipeline, default hyperparameters |
| RLDec, CLI decode | decomp-rldec, combsequential, 20 iterations, its default greedy decode; 3 seeds |
| RLDec, best training state | the best state RLDec's own callback recorded during training, by its own reward; 3 seeds |
| random | K = teacher K; 3 seeds |

## 2. Findings

1. **GraphRL-Dec is the only method with no cannot-link violation on every
   app that has cannot-link pairs** (Table E6, section 4). The pairs come
   from rule CL-SIBLING (FACTS.md, section 2): 169 in AcmeAir, 684 in
   DayTrader and 352 in lit-jpetstore. Every GraphRL-Dec run, all 8 variants
   and 3 seeds, violates none of them. The teacher violates 2, 118 and 10.
   Every other method of the comparison pool violates pairs on at least one
   of the three apps. Rule-based repairs run inside the same mask also have
   none (section 4.1): the compliance comes from the mask.
2. **GraphRL-Dec is the teacher, repaired where the constraints forbid it.**
   - On the three apps without cannot-link pairs, all 72 runs decode to
     exactly the teacher's partition (Table E3).
   - On the three apps with pairs, none of the 72 runs does. GraphRL-Dec full
     moves 2 of AcmeAir's 70 classes, 21 of DayTrader's 104 and 5 of
     lit-jpetstore's 71, the same classes in each seed. Of those, 2, 15 and
     5 belong to a cannot-link pair that the teacher violates; the rest
     follow them (`results/recon/graphrl_repairs.out`).
   - The cause of the stickiness is unchanged from the Rails runs: KL
     anchoring to the behaviour-cloned teacher, a PPO learning rate of 1e-4
     and 600 episodes. The action mask is what makes the policy deviate.
   - A rule-based repair of the teacher in the same masked environment
     reaches the same compliance and about the same quality (section 4.1).
     With the paper's settings the learned policy adds little on these
     benchmarks. Without the KL anchor, a setting chosen on the
     unconstrained apps, it beats the rule on DayTrader and lit-jpetstore in
     all three conventions, but not on AcmeAir (section 7).
3. **The repair raises the primary score.** In the evaluate convention,
   GraphRL-Dec has the highest Score of the nine methods on AcmeAir (+0.68,
   teacher +0.67), DayTrader (+0.74, teacher +0.45) and lit-jpetstore
   (+0.68, teacher +0.60). It ties the teacher on Plants and lit-pbw, and on
   jpetstore-6 NeSy-Rep + Ward is ahead (+0.68 against +0.34) (Table E1).
   - Under binarized SM the repair is neutral: +0.59 against the teacher's
     +0.61 on AcmeAir, +0.59 against +0.59 on DayTrader and +0.57 against
     +0.54 on lit-jpetstore (Table E2).
   - It costs must-link pairs on DayTrader: 24 of 41 are kept together,
     against the teacher's 30 (Table J4 in `paper_tables.md`;
     `recon/graphrl_repairs.out` lists the pairs). The 6 lost
     pairs are benchmark servlets of `web.prims` that inject the EJB
     `TradeSLSBBean` (5) or look up the entity `QuoteDataBean` (1); the mask moves those
     servlets out of the service that holds the JSF classes and the bean.
   - Part of the SM gain is built into the rule. CL-SIBLING separates
     packages that have no edge between them in G, and SM is computed on G,
     so separating them tends to raise SM. The gain is therefore not
     independent evidence of better quality (section 8).
4. **Fine-tuning helps the embeddings.** NeSy-Rep + Ward has a higher SM
   than pretrained UnixCoder + Ward on all six apps (Table E1, evaluate),
   for example 0.71 against 0.33 on AcmeAir and 0.69 against −0.24 on
   Plants. Under binarized SM, NeSy-Rep + Ward is the best method of the
   pool on four apps (Table E2), so the ranking between the RL method and
   the embedding method depends on the convention.
5. **The two Sellami baselines do poorly on this input.**
   - HierDec at its defaults fragments each app into 12 to 62 services,
     most of them singletons. It ranks near the bottom everywhere.
   - RLDec's own greedy decode returns a single service on every app and
     seed, so it violates every cannot-link pair. Its best training state
     has 2 to 18 services per run, but scores below the teacher and near
     random on most apps.
   - Both were run unmodified, at their defaults, on our G, not on Sellami's
     analysis. Section 8 lists what that implies.
6. **The Eq. 5 comparison can be gamed, and the constraints expose it**
   (section 6).
   - A hill-climb on SM, IFN, ICP and NED, started from a random partition
     and using no architectural knowledge, ranks #1 in every published pool
     on weighted calls: 18 of 18 runs. Under binarized SM it ranks #2 to #9.
   - On the three apps with cannot-link pairs, each of those 9 partitions
     violates 8 to 91 pairs. GraphRL-Dec violates none.
   - Cross-paper comparisons on these metrics therefore cannot establish
     state-of-the-art quality on their own. Constraint compliance is the
     measure that separates an architecturally informed decomposition from
     metric optimization.

## 3. Within-pipeline tables

#### Table E1. Within-pipeline results, on G with evaluate.py's definitions (primary)

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

#### Table E2. Within-pipeline results, on G with RLDec's metric code (binarized SM)

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

#### Table E3. GraphRL-Dec against its teacher

| app | GraphRL-Dec runs (8 variants x 3 seeds) | partition identical to the teacher's | different |
|---|---|---|---|
| jpetstore-6 | 24 | 24 | 0 |
| acmeair | 24 | 0 | 24 |
| daytrader7 | 24 | 0 | 24 |
| plantsbywebsphere | 24 | 24 | 0 |
| lit-jpetstore | 24 | 0 | 24 |
| lit-pbw | 24 | 24 | 0 |

#### Table E4. Against Weerasinghe et al. 2026, Table 1 (pool of published tools plus ours, Eq. 5 as published)

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

## 4. Cannot-link compliance (RQ4)

A violation is a cannot-link pair placed in one service. Table E6 counts
them per method, from `metrics.csv` (column `cannot_link_violations`). The
three apps without cannot-link pairs are left out.

#### Table E6. Cannot-link violations (pairs of rule CL-SIBLING placed in one service; mean over seeds where a method has several)

| system | cannot-link pairs | GraphRL-Dec | RoR-MSI | UnixCoder+Ward (NeSy-Rep) | UnixCoder+Ward (pretrained) | HierDec | RLDec (best state) | RLDec (CLI) |
|---|---|---|---|---|---|---|---|---|
| AcmeAir | 169 | 0 | 2 | 11 | 21 | 13 | 25.7 (18 to 35) | 169 |
| DayTrader 7 | 684 | 0 | 118 | 32 | 12 | 0 | 42.0 (21 to 71) | 684 |
| JPetStore (lit.) | 352 | 0 | 10 | 0 | 110 | 18 | 52.7 (12 to 98) | 352 |

- **GraphRL-Dec** violates no pair in any of its 72 runs on these apps, nor
  in any of the 36 ablation runs there. Why, and how far it is guaranteed:
  - The environment masks every action that would place a class in a
    service holding one of its cannot-link partners (`graph_env.py`,
    `legal_actions`). The greedy decode takes the argmax over the masked
    logits, and `step` snaps any illegal action to a legal one.
  - The mask can admit a violation in one case only: when every service is
    forbidden for the current class (by cannot-link or by the size cap), it
    falls back to all services legal so the episode can finish.
  - In the variants that allow outliers (`+noise`, `full` and the three
    `full+` variants), the "leave unassigned" action is always legal, so
    the fallback cannot fire and a violation is impossible by construction.
  - For every run, the fallback was checked directly. Replaying all 198
    decodes on the constrained apps (main run, ablations and the follow-up
    of section 7) reproduces every reported partition exactly, and across
    their 16,170 steps the fallback fired 0 times and the policy never chose
    an illegal action (`results/recon/mask_replay.py` and `.out`).
  - The guarantee is relative to the fact base: it covers exactly the
    pairs CL-SIBLING produced.
- **The teacher** does not see cannot-link at all. Its violations are what
  the RL stage has to repair.
- **The embedding baselines** see the pairs only through the encoder's
  training. NeSy-Rep + Ward violates fewer pairs than pretrained UnixCoder +
  Ward on AcmeAir (11 against 21) and lit-jpetstore (0 against 110), and
  more on DayTrader (32 against 12).
- **HierDec** has no violation on DayTrader because it splits that app into
  62 services, 41 of them single classes.
- **RLDec's CLI decode** puts every class in one service and so violates
  every pair.

The encoder's cannot-link term barely acts. It is a hinge with margin 0.5 on
the distance between unit-norm embeddings, and the pairs are already
further apart: its mean loss per epoch was 0.00035, 0.00031 and 0.00023,
against a triplet loss of 0.109, 0.057 and 0.041
(`gpu_logs/main.log`). The Rails encoder shows the same, with 0.0,
0.0000016 and 0.000042 (`v2_full_run_backup/encoder/train/train_log.json`).
Cannot-link reaches the encoder through the triplets, which draw
cannot-link negatives (FACTS.md, section 2), and reaches the decomposition
through the RL mask.

### 4.1 Repair by rule: what the learning adds

GraphRL-Dec keeps its teacher except where the mask forbids it, so the
question is whether a rule does the same. `java_pipeline/repair_baseline.py`
repairs the teacher with no learning, in the environment GraphRL-Dec decodes
in (same class order, mask and size cap), in three ways:

- `repair_masked`: walk the classes in the environment's order, take the
  teacher's service, or the lowest-index legal one when it is forbidden.
  This is the target sequence behaviour cloning trains on.
- `repair_connect`: the same walk, but a forbidden class goes to the legal
  service it has the most edge weight with.
- `repair_post`: start from the teacher's partition and move violating
  classes, most violations first, to their best-connected legal service.

They were run on the GPU server's environment on 2026-11-03
(`gpu_logs/repair_baseline.log`) and scored like every other partition.

#### Constraint repair by rule against GraphRL-Dec full

Score: Eq. 5 as published, in the nine-method pool with the row in GraphRL-Dec full's place (GraphRL-Dec full's own Score in that pool in brackets). Means over 3 seeds for GraphRL-Dec.

| app | method | equals GraphRL-Dec full (seeds) | classes moved from teacher | cannot-link violations | must-link kept | Score, evaluate | Score, rldec | Score, weerasinghe |
|---|---|---|---|---|---|---|---|---|
| acmeair | teacher | - | 0 | 2 of 169 | 0.538 | +0.67 (+0.68) | +0.61 (+0.59) | +0.64 (+0.66) |
| acmeair | graphrl:full | - | 2 / 2 / 2 | 0 of 169 | 0.538 | +0.68 (+0.68) | +0.59 (+0.59) | +0.66 (+0.66) |
| acmeair | repair_masked | 0/3 | 2 | 0 of 169 | 0.538 | +0.67 (+0.68) | +0.58 (+0.59) | +0.64 (+0.66) |
| acmeair | repair_connect | 0/3 | 2 | 0 of 169 | 0.538 | +0.68 (+0.68) | +0.60 (+0.59) | +0.66 (+0.66) |
| acmeair | repair_post | 0/3 | 2 | 0 of 169 | 0.615 | +0.70 (+0.68) | +0.63 (+0.59) | +0.70 (+0.66) |
| daytrader7 | teacher | - | 0 | 118 of 684 | 0.732 | +0.54 (+0.74) | +0.60 (+0.59) | +0.57 (+0.80) |
| daytrader7 | graphrl:full | - | 21 / 21 / 21 | 0 of 684 | 0.585 | +0.74 (+0.74) | +0.59 (+0.59) | +0.80 (+0.80) |
| daytrader7 | repair_masked | 0/3 | 14 | 0 of 684 | 0.585 | +0.77 (+0.74) | +0.60 (+0.59) | +0.83 (+0.80) |
| daytrader7 | repair_connect | 0/3 | 14 | 0 of 684 | 0.585 | +0.76 (+0.74) | +0.59 (+0.59) | +0.83 (+0.80) |
| daytrader7 | repair_post | 0/3 | 9 | 0 of 684 | 0.634 | +0.43 (+0.74) | +0.49 (+0.59) | +0.44 (+0.80) |
| lit-jpetstore | teacher | - | 0 | 10 of 352 | 0.568 | +0.64 (+0.68) | +0.55 (+0.57) | +0.75 (+0.81) |
| lit-jpetstore | graphrl:full | - | 5 / 5 / 5 | 0 of 352 | 0.568 | +0.68 (+0.68) | +0.57 (+0.57) | +0.81 (+0.81) |
| lit-jpetstore | repair_masked | 0/3 | 5 | 0 of 352 | 0.568 | +0.66 (+0.68) | +0.53 (+0.57) | +0.81 (+0.81) |
| lit-jpetstore | repair_connect | 0/3 | 5 | 0 of 352 | 0.568 | +0.66 (+0.68) | +0.55 (+0.57) | +0.79 (+0.81) |
| lit-jpetstore | repair_post | 0/3 | 2 | 0 of 352 | 0.591 | +0.66 (+0.68) | +0.56 (+0.57) | +0.76 (+0.81) |

- **Compliance comes from the mask, not from the learning.** All three
  repairs violate no pair, as GraphRL-Dec does.
- **On quality the best rule matches GraphRL-Dec.** On every app and in
  every convention, the best of the three repairs is at most 0.02 below
  GraphRL-Dec, and it is above it on AcmeAir and DayTrader. The rules are
  not all equal: `repair_post` falls well behind on DayTrader (+0.43
  against +0.74 under evaluate). `repair_post` beats GraphRL-Dec on AcmeAir
  in all three conventions and keeps more must-link pairs (0.615 against
  0.538). `repair_masked` is ahead on DayTrader under evaluate and
  weerasinghe. GraphRL-Dec is ahead on lit-jpetstore under evaluate and
  rldec. No repair equals GraphRL-Dec's partition.
- So on these benchmarks the RL stage behaves as a learned constraint
  repair of its teacher, and a rule does about as well. The paper's
  contribution on Java is the masked action space, not the learned policy.

## 5. Ablation: can PPO leave the teacher?

The main runs leave the teacher only where the mask forces them, so two
labelled ablations test whether PPO can leave it on its own. They change
Rails hyperparameters and are reported here only, never in place of the
main results. Both were run on the `structural` and `full` variants, 6 apps
and 3 seeds, 72 runs in all, with the same cannot-link mask as the main runs
(`results/_nesy/rl_ablation/`, `gpu_logs/ablation_*.log`):

- `kl0_ep2000`: no KL anchor to the behaviour-cloned teacher, and 2,000
  episodes instead of 600;
- `nobc_ep2000`: no behaviour-cloning warm start at all, no KL anchor, and
  2,000 episodes.

Each ablation family takes GraphRL-Dec full's place in the nine-method pool,
so its Score can be read against the teacher's in the same pool.

#### Table E5. GraphRL-Dec ablations (run_gpu.ABLATIONS) in place of GraphRL-Dec full

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

What the ablation shows (`results/ablation.csv`):

- **Without the anchor, PPO moves away from the teacher.**
  - Only 1 of the 36 runs keeps the teacher's partition, on lit-pbw.
  - Under evaluate, the ablation scores above the teacher in 9 of the 12 app
    and variant pairs. It is below on AcmeAir (both variants) and on lit-pbw
    structural. For example, DayTrader full scores +0.89 against the
    teacher's +0.33.
  - Under RLDec's binarized SM, it is ahead in 6 of 12. On DayTrader
    structural it falls from the teacher's +0.73 to +0.20.
  - GraphRL-Dec's reward is built on evaluate.py's SM, IFN, ICP and NED
    (`graph_env.py`), the same functions as the evaluate convention, so its
    gains there are expected. They transfer to the binarized convention in
    only half of the cases.
  - In some `full` runs PPO leaves classes unassigned (the `full` variant
    allows outliers): coverage is 0.91 to 0.97 on Plants, 0.97 on
    lit-jpetstore and 0.96 in one jpetstore-6 run (`metrics.csv`, column
    `coverage`).
- **Without the warm start, PPO fails.** It is below the teacher in all 12
  pairs under both conventions. In 8 of its 12 app and variant means, NED is
  1.00 and ICP 0.00: the runs end with one service, or with no class
  assigned at all (coverage 0 in 5 `full` runs). Behaviour cloning from the
  RoR-MSI teacher is what makes GraphRL-Dec produce usable decompositions.

## 6. Experiments after the main run

These ran on this machine: the RTX 3060 for GraphRL-Dec, the CPU for the
rest. The full account is `results/OPTIMIZATION.md`. They are labelled
experiments and do not replace any result above.

### 6.1 A reward that is not the evaluation metric (idea 1)

This experiment was run on 2026-10-26, before the fact base had cannot-link
pairs, and was not repeated. Its partitions are in
`results/_archive/pre_cl_sibling_2026-10-26/_nesy/rl_ablation/dual_*`,
and its scores are within the pools of that run. It is kept as a record of
a negative result. On the three apps that now have cannot-link pairs, the
mask could change its numbers.

The dual reward is the mean of the evaluate and rldec z-scores
(`java_pipeline/dual_reward.py`). The weerasinghe convention is in neither
term, so it is the held-out check. Each seed is scored alone in the
nine-method pool (`java_pipeline/idea1_report.py`):

#### Idea 1: per-seed Score against the teacher (seed runs scored one at a time in the nine-method pool)

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

#### Totals over the apps run

| setting | evaluate | rldec | weerasinghe |
|---|---|---|---|
| dual reward, no anchor, full | 7/18 | 6/18 | 7/18 |
| dual reward, no anchor, structural | 8/18 | 6/18 | 5/18 |
| old reward, no anchor, full | 9/18 | 5/18 | 9/18 |
| old reward, no anchor, structural | 13/18 | 6/18 | 11/18 |
| dual reward, paper's anchor, full | 0/3 | 0/3 | 0/3 |

The dual reward does not make GraphRL-Dec better than its teacher across
apps.
- Without the anchor it beats the teacher on the held-out convention in 7
  of 18 runs (`full`). The old reward did so in 9 of 18.
- On AcmeAir and DayTrader it returns to the teacher's exact partition in
  every run.
- Its losses are small: the mean held-out delta is never below −0.05.

### 6.2 Hill-climbing the same objective, and what it reveals

`java_pipeline/local_search.py` starts from a partition and repeatedly makes
the best single-class move under the RL environment's size cap. It does not
apply the cannot-link mask. Its objective is the dual reward of 6.1, scored
against the same peers as GraphRL-Dec's reward.

From the teacher, it beats the teacher on all six apps in all three
conventions (`java_pipeline/refine_report.py`):

#### Refinement against the teacher (same nine-method pool)

| app | sizes | evaluate | rldec | weerasinghe (held out) |
|---|---|---|---|---|
| jpetstore-6 | 11 6 5 2 | +0.71 vs +0.24 (SM 1.05 vs 0.74) | +0.50 vs +0.15 (SM 0.13 vs 0.09) | +0.72 vs +0.24 (SM 0.78 vs 0.54) |
| acmeair | 16 8 7 6 6 5 5 5 5 5 2 | +0.92 vs +0.56 (SM 0.89 vs 0.65) | +0.88 vs +0.50 (SM 0.21 vs 0.15) | +0.77 vs +0.58 (SM 0.50 vs 0.42) |
| daytrader7 | 48 18 5 5 5 5 5 5 3 3 2 | +0.85 vs +0.45 (SM 0.63 vs 0.49) | +0.87 vs +0.51 (SM 0.21 vs 0.18) | +0.90 vs +0.44 (SM 0.42 vs 0.31) |
| plantsbywebsphere | 16 14 5 | +1.04 vs +0.73 (SM 1.82 vs 1.39) | +0.70 vs +0.45 (SM 0.09 vs 0.07) | +1.10 vs +0.77 (SM 1.56 vs 1.17) |
| lit-jpetstore | 19 19 10 5 5 5 5 3 | +1.02 vs +0.46 (SM 0.72 vs 0.46) | +0.83 vs +0.47 (SM 0.17 vs 0.13) | +1.09 vs +0.54 (SM 0.58 vs 0.36) |
| lit-pbw | 19 10 5 2 | +0.96 vs +0.73 (SM 1.71 vs 1.43) | +0.81 vs +0.62 (SM 0.16 vs 0.14) | +1.00 vs +0.77 (SM 1.44 vs 1.19) |

#### Rank in the published pools (Weerasinghe Table 1 plus ours)

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

The checks that follow show the gain is optimization of the metric itself.

- **Start.** From random partitions, the search ends above the teacher on
  the held-out convention in all 18 runs, and above the search started from
  the teacher in 12 of them (`results/refine_checks.md`, section 3).
- **Published pools.** Ranked there, a random partition after hill-climbing
  is #1 in all 18 runs on weighted calls, while the random partitions alone
  rank mostly last (`java_pipeline/gaming_check.py`).
- **Constraints.** The same partitions violate 8 to 91 cannot-link pairs on
  the three apps that have them (last column). The refinement from the
  teacher violates 9 of 169 on AcmeAir, 167 of 684 on DayTrader and 4 of 352
  on lit-jpetstore (`metrics.csv`, family `local_search_dual`).

#### Random partition + hill-climb, ranked in the published pools

| app | benchmark | seed | services | rank, weighted calls | rank, binarized | random alone, weighted | random alone, binarized | cannot-link violations |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | JPetStore | 42 | 4 | #1 of 9 | #2 of 9 | #7 of 9 | #9 of 9 | no pairs |
| jpetstore-6 | JPetStore | 1 | 4 | #1 of 9 | #2 of 9 | #9 of 9 | #9 of 9 | no pairs |
| jpetstore-6 | JPetStore | 7 | 4 | #1 of 9 | #5 of 9 | #1 of 9 | #9 of 9 | no pairs |
| acmeair | AcmeAir | 42 | 11 | #1 of 10 | #6 of 10 | #10 of 10 | #10 of 10 | 17 of 169 |
| acmeair | AcmeAir | 1 | 11 | #1 of 10 | #7 of 10 | #10 of 10 | #10 of 10 | 16 of 169 |
| acmeair | AcmeAir | 7 | 11 | #1 of 10 | #7 of 10 | #10 of 10 | #10 of 10 | 8 of 169 |
| daytrader7 | DayTrader | 42 | 11 | #1 of 10 | #5 of 10 | #10 of 10 | #10 of 10 | 87 of 684 |
| daytrader7 | DayTrader | 1 | 11 | #1 of 10 | #5 of 10 | #10 of 10 | #10 of 10 | 91 of 684 |
| daytrader7 | DayTrader | 7 | 11 | #1 of 10 | #5 of 10 | #9 of 10 | #10 of 10 | 91 of 684 |
| plantsbywebsphere | Plants | 42 | 3 | #1 of 10 | #7 of 10 | #10 of 10 | #10 of 10 | no pairs |
| plantsbywebsphere | Plants | 1 | 3 | #1 of 10 | #7 of 10 | #10 of 10 | #10 of 10 | no pairs |
| plantsbywebsphere | Plants | 7 | 3 | #1 of 10 | #7 of 10 | #9 of 10 | #10 of 10 | no pairs |
| lit-jpetstore | JPetStore | 42 | 8 | #1 of 9 | #5 of 9 | #9 of 9 | #9 of 9 | 46 of 352 |
| lit-jpetstore | JPetStore | 1 | 8 | #1 of 9 | #3 of 9 | #9 of 9 | #9 of 9 | 63 of 352 |
| lit-jpetstore | JPetStore | 7 | 8 | #1 of 9 | #5 of 9 | #9 of 9 | #9 of 9 | 71 of 352 |
| lit-pbw | Plants | 42 | 4 | #1 of 10 | #7 of 10 | #10 of 10 | #10 of 10 | no pairs |
| lit-pbw | Plants | 1 | 4 | #1 of 10 | #7 of 10 | #9 of 10 | #10 of 10 | no pairs |
| lit-pbw | Plants | 7 | 4 | #1 of 10 | #9 of 10 | #10 of 10 | #10 of 10 | no pairs |

- **Moves.** Some are sensible: on jpetstore-6, `Item` and `Product` join
  the catalog service. Others are not: on DayTrader, benchmark servlets such
  as `PingJDBCRead` move into the account-data service (`refine_checks.md`,
  section 1).
- **Measures the search does not optimize.** NeSy-Rep embedding similarity
  and must-link facts kept together improve on some apps and fall on others
  (`refine_checks.md`, section 2).

The refinement is therefore not reported as a method. The held-out
convention applies the same formulas to a subgraph of G, so it cannot tell
architectural quality from metric optimization. Cannot-link compliance can.

### 6.3 Why our rows rank lower under binarized SM

Binarized SM is the dependency density inside each service: distinct
internal edges divided by m². Two causes account for our lower ranks
(`results/recon/binarized_selfcalls.out`):

- **Self-calls.** RLDec's metric code keeps the diagonal, and our G has no
  self-edges. Counting a self-edge for each class that calls its own
  methods raises binarized SM from 0.16 to 0.30 on lit-pbw and from 0.21 to
  0.30 on DayTrader.
- **Density rewards tiny services.** Our graph densities are 0.028 to 0.077.
  A service of about 9 classes then has an internal density near 0.2, below
  that of a 2-class service with one edge (0.25). Eq. 5 weights SM 3 to 1,
  so tools emitting many tiny services gain. An example is the published
  HDBScan row: NED 0.70 to 0.90, SM 0.22 to 0.60.

### 6.4 Resolver layers

The teacher was run on graphs built from subsets of the resolver's layers
(`java_pipeline/layer_ablation.py`, `results/layer_ablation.csv`).

- On the naive Phase 2 graph, 21 of AcmeAir's 70 classes, 13 of DayTrader's
  104 and 7 of lit-jpetstore's 71 are isolated, and cannot be placed. With
  the resolved graph, all classes are placed.
- Plants and lit-pbw change little; their naive graphs are already
  connected.

## 7. Follow-up: can the RL stage do better than a rule?

Section 4.1 showed that with the paper's settings, a rule-based repair of
the teacher does as well as GraphRL-Dec. Two follow-up experiments, run on
the GPU server on 2026-11-03 (`java_pipeline/run_followup.sh`,
`gpu_logs/followup*.log`), test whether the RL stage can do better:

1. **GraphRL-Dec with the kl0_ep2000 setting** (no KL anchor, 2,000
   episodes), all 8 variants, 6 apps, 3 seeds. The setting was chosen before
   these runs, on the three apps without cannot-link pairs only:
   `results/recon/setting_selection.py` takes the setting that scores
   above the paper setting in the most cells there. kl0_ep2000 did so in 14
   of 18 cells, nobc_ep2000 in 0 (`setting_selection.out`). It was then
   applied unchanged to the three apps with cannot-link pairs.
2. **GraphRL-Dec warm-started from NeSy-Rep + Ward** instead of the RoR-MSI
   teacher (`run_gpu.ABLATIONS`, `nesyward` and `nesyward_kl0_ep2000`),
   `structural` and `full`, 3 seeds. Its rule-based counterparts are the
   same three repairs applied to NeSy-Rep + Ward (`repair_nesyward_*`).

The table is rendered by `java_pipeline/followup_report.py` into
`results/followup.md` and inserted here unchanged.

#### F1. The three apps with cannot-link pairs

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

#### F2. All six apps: the kl0 setting against the paper setting, every variant

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

#### F3. Cannot-link violations of every kl0 and NeSy-Rep-start run

108 runs on the apps with cannot-link pairs; 0 with any violation.

What the follow-up shows:

- **Without the anchor, the RL stage beats the rule on two of the three
  constrained apps.** GraphRL-Dec full with kl0 scores above the best
  repair of the teacher on DayTrader (+0.89 against +0.77 under evaluate,
  +0.66 against +0.60 binarized, +0.90 against +0.83 on weighted calls) and
  on lit-jpetstore (+0.75 against +0.66, +0.64 against +0.53, +0.87 against
  +0.81), in all three conventions. On DayTrader it also keeps more
  must-link pairs (0.675 against 0.585). On AcmeAir the post-hoc repair
  stays ahead in all three.
- **Across all apps and variants, the gain is mostly in the reward's own
  metric family.** kl0 scores above the paper setting in 33 of 48 (app,
  variant) pairs under evaluate and 33 of 48 on weighted calls, but in only
  15 of 48 under binarized SM (Table F2). For the `full` variant it is
  above the paper setting on 5 of 6 apps under evaluate, 4 of 6 binarized
  and 5 of 6 on weighted calls.
- **The NeSy-Rep warm start does not help.** From NeSy-Rep + Ward,
  GraphRL-Dec at best ties the rule-based repair of that partition, and on
  AcmeAir it falls well below it (+0.33 against +0.71 under evaluate, paper
  setting). Its partitions keep more must-link pairs and have higher
  embedding similarity, as an embedding-based start would. On the
  structural metrics, the RoR-MSI teacher is the better start.
- **Compliance holds in every new run.** None of the 108 new runs on the
  constrained apps violates a cannot-link pair, and the mask replay
  reproduces all 198 runs on those apps with no fallback and no illegal
  action (`recon/mask_replay.out`).
- **What this does not show.** The kl0 gains are on the Eq. 5 metric
  family, which section 6.2 shows can be optimized directly. Two of the
  three conventions are not the reward's definitions, and the gains on
  DayTrader and lit-jpetstore hold in all three, but none of them is a
  quality criterion independent of the family. The setting was chosen on
  three apps of the same benchmark set, not on separate data.

## 8. Threats to validity

- **Metric conventions disagree.** On G, evaluate.py's SM weights edges and
  can exceed 1: the teacher reaches 1.39 on Plants. The published SMs in
  Weerasinghe Table 1 are all at most 0.60. Our rows rank near the top of
  the external pool in the weighted conventions and mid-table in the
  binarized one (Table E4). Section 6.2 shows that a knowledge-free search
  also tops the weighted pools. Neither convention is the one the published rows
  used: those rows come from several papers, each with its own code, and
  RECON.md section 3 shows that even ICP has three definitions in use. Table
  E4 therefore places us in that pool. It does not show that we beat it.
- **Class sets differ from the published ones** (SUBJECTS.md, section 4).
  - jpetstore-6 (24 classes) and plantsbywebsphere (35) are the repositories
    Weerasinghe's footnotes link. The copied rows were measured on
    KimJongSung/jPetStore and the pbw-monolith, which are the literature
    variants here: 71 and 36 active classes, against 73 and 40 published.
  - Our DayTrader has 104 active classes and AcmeAir 70, against 118 and 86
    published.
- **Static against dynamic inputs.** Mono2Micro and some published rows use
  execution traces. Every method here is static.
- **Copied against re-run numbers.** All published rows are copied from
  Table 1. Weerasinghe ran only CHGNN and MonoEmbed themselves. The others
  are copied from [10], [18] and [21] (RECON.md, section 3).
- **The Sellami baselines did not get their native inputs.** HierDec and
  RLDec read our G instead of their analysis service's matrices, and our
  TF-IDF stands in for the Spoon `textAndNames` field (export_sellami.py).
  Both used default hyperparameters, because their papers' per-app tuning
  is not available. This is the fair within-pipeline comparison the plan
  asks for: same graph, same classes. It is not a reproduction of their
  papers.
- **The cannot-link rule was written on these six subjects.** CL-SIBLING
  was defined after reviewing them (FACTS.md, section 2), and it has not
  yet been applied unchanged to Java systems it was not designed on. It
  fires on three of the six.
- **The rule and SM read the same graph.** CL-SIBLING separates packages
  with no edge between them in G, and every convention computes SM on G
  or on its call subgraph. Separating such packages tends to raise SM, so
  the SM gain of GraphRL-Dec over the teacher on the three constrained apps
  is partly built in. The compliance result (Table E6) does not have this
  problem: no other method sees the constraint as a hard rule.
- **Reward truncation.** `graph_env.py:685` truncates edge weights below 1
  in the RL reward tracker. This affects 4.5% of AcmeAir's edge weight and
  at most 0.4% elsewhere (RUNS.md, section 5).
- **Single runs.** The teacher, HierDec and the embedding baselines are
  deterministic, so there is one run each. GraphRL-Dec, RLDec and random
  have 3 seeds, and the tables report means.
