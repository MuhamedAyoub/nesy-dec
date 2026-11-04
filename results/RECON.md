# Phase 0 reconnaissance: Java front end for NeSy-Dec

Date: 2026-10-19. Read only, apart from this file and two small check scripts
under `results/recon/`. No code in the repository was changed. Paths are
relative to `<repo>/` unless they start with
`decomp-`, which means the sibling folders in `<parent>/`.

`results/` sits next to `results/` inside the repository, because every
driver resolves paths from the repository root.

## 0. Environment facts that constrain later phases

The analysis service source (`decomp-java-analysis-service`) is not present.
Nothing has been cloned. A compiled copy is shipped inside the parsing service:
`decomp-parsing-service/decparsing/analysis/resources/java-analysis-service-1-3-0.jar`
(36.8 MB). Its manifest says `Build-Jdk-Spec: 11`, `Main-Class: Main`, and it
bundles Spoon (`spoon/`) and Eclipse JDT (`org/eclipse/jdt/`). The parsing
service runs it as `java -jar <jar> analyze <app> -p <path> -o <out>`
(`analysisJarClient.py:24-26`). This jar would let us produce Sellami's own
analysis of each benchmark without the source repository. Whether to use it is
a decision for you (see section 6).

The machine has OpenJDK 21.0.12. Maven, Gradle and Ant are not on the PATH.
Phase 1 builds will need either a Maven download or the `mvnw` wrappers that
some benchmarks ship. Both mean network access.

## 1. Rails-specific code in NeSy-Dec

The Java path has to replace or bypass each place below. Items marked
"neutral" carry over unchanged.

### Graph construction (Paper 1, Ruby)

- `tools/v2/AstFactsV2.rb` is a Ruby AST walker as a whole (`parser` gem,
  lines 12 and 45). Rails-specific parts: class names joined with `::`
  (line 69), association and mixin macros (55-56), and the macro handling for
  `scope`, `delegate`, `alias_method` and `define_method` (144-173).
- `tools/v2/RailsAwareGraphV2.rb:20-25` fixes the 24 Rails role directories.
  Lines 78-81 walk `app/<role>/**/*.rb`. Line 29 drops `/spec/` and `/test/`.
  Line 43 defines the model set as the roles `models` and `data`.
- `tools/v2/ConventionOracleV2.rb:14-23` holds the ActiveRecord method
  vocabulary, mailer and job triggers, and the service-suffix regex.
  Lines 133-141 approximate Ruby constant lookup, innermost namespace first.
- `tools/v2/ResolverV2.rb:17-27`: both noise lists are Ruby and Rails method
  names. Lines 259-271: constant resolution splits on `::` and falls back to a
  unique basename. Lines 199-207: the L3 naming rule (`current_` prefix,
  singularize, classify) depends on the inflector. Neutral: the cascade
  structure, the per-layer counters (`bump`, 279-282), and the fan-out rule
  with cap K = 5 and weight 1/n (28, 209-220).
- `tools/v2/InflectorV2.rb` is English pluralization for Rails conventions.
  JPA declares target types explicitly, so Java does not need it.
- `experiment_v2.rb:37-44` refuses to run without `--rails-aware` and always
  builds the graph through `RailsAwareGraphV2`. Neutral: the JSON contract
  (146-167: `dependency_graph`, `data_associations`, `clusters`,
  `resolver_report`, `isolated_classes`), the isolated-class filter (55-91) and
  the call to `ClusterEngine.get_microservices` (94-97). The engine takes a
  `DependencyAnalyzer` populated by `instance_variable_set` (84-89). A Java run
  of the teacher therefore needs only a new Ruby driver that loads G and D from
  JSON. The engine's data term is a Jaccard index over `@data` lists
  (`vendor/ror_msi/tools/DependencyAnalyzer.rb:134-137`), which a Java D can fill.

### Symbolic facts (Paper 2)

- `neurosymbolic/symbolic/rules.py`
  - 29-61: Ruby regexes (associations, `include`/`extend`, `class`/`module`
    definitions, ActiveRecord lookups, mailers, jobs, services,
    `before_action`).
  - 65-71: `RAILS_APP_DIRS`.
  - 75-86: `FRAMEWORK_BASES` (`ApplicationRecord`, `ActiveRecord::Base`, and
    similar).
  - 92-117: `_looks_like_app_base`, a naming rule built on `Base*` and `*Base`.
  - 120-142: depluralization.
  - 225-230: walks `*.rb` files.
  - 233-245 and 274-287: role taken from the directory.
  - 290-306: the class name is the last `::` segment.
  - 339-353 and 538-543: namespace taken from the directory after the role.
  - 444-468 and 601-616: namespace cannot-link, stored as one representative
    pair per namespace pair.
  - 512 and 649-658: expects `datasets/<app>/app/`.
- `qualify_facts_v2.py`
  - 64-65: the eight Rails apps.
  - 74-82: snake_case vs CamelCase normalization.
  - 85-147: `::` resolution from bare to qualified names.
  - 223-228: namespace set to the first `::` segment, and added for every
    qualified node.

  If the Java facts use fully qualified names from the start, this rewrite is
  not needed. The exact-match check it exists for is still mandatory.
- `neurosymbolic/triplets.py:41-45` imports the Rails extractors. Line 81
  prefers `_mvc.json`, then `_rails_aware.json`. Line 403 expects
  `datasets/<app>/app`. The hard negatives at 216-218 come from the same role,
  so they inherit the role vocabulary.
- `neurosymbolic/infer_coupling.py:48` hardcodes
  `results/<app>/exp_a0.5_b0.5_n8_mvc.json`. The rest (52-89) is neutral.

### Representation (NeSy-Rep)

- `neurosymbolic/code_reader.py`
  - 40-42: `#` comment regex. The budget is 30 body lines and 1,800
    characters, which is about 400 UnixCoder tokens.
  - 104-131: class and module regexes, `::`.
  - 144 and 172-196: `*.rb` files and the Rails subdirectories.
  - 190: the `app/` layout.

  Java needs `/* */`, `//`, `import` and `package` stripping under the same
  budget.
- `neurosymbolic/experiments/runner.py:103, 116, 174-176, 211` hardcode
  `results/`, `app/` and the v1 `facts`, `triplets` and `code_index`
  directories. `run_everything_v2.py:203-253` works around this with a
  symlink shim.

### RL stage (GraphRL-Dec)

- `neurosymbolic/rl/graph_env.py`
  - 419-435: the role vocabulary, 24 Rails roles plus `unknown`, so the
    one-hot is 25 wide.
  - 438-472: features are `[emb d | one-hot R | log in-degree | log
    out-degree]`. Changing R changes the policy input size (`policy.py:34, 92`),
    so Java policies are not weight-compatible with Rails ones. That is
    expected and harmless.
  - 615: NED band [5, 20].
  - 624-634: K = max(teacher K, round(N / 12.5), 2).
  - 639-650: size cap floored at 20.

  These size rules are language neutral, but they behave differently on small
  apps: a 25-class app gets K = 2 from the N term.
- `neurosymbolic/rl/train.py:587, 591-594, 733`; `eval.py:229-235`;
  `constraint_eval.py:98`; `decompose.py:138-141`; `search.py:218`: all
  resolve inputs under `results/<app>/` and `phase1_rails_aware/`. Hard rule 3
  puts Java outputs in `results/`, so the Java path needs a redirect
  module in the style of `v2_paths.py`, which patches `_default_paths` and
  `_find_baseline`.
- `run_everything_v2.py:54-55` lists the Rails apps. Lines 102-120 run stage 0
  in Ruby on `datasets/<app>/app`. Lines 125-161 pass `--mode rails-aware`.
  Lines 630-655 check for Ruby and `app/`.

## 2. Sellami input formats, and whether our G and D can be exported

HierDec (`decomp-hydec`) takes three folders, each holding
`class_names.json` (row order) and one matrix (README; `dataHandler.py:20-24`;
`hydec.py:39-53`):

- `structural_data/class_calls.npy`, N×N;
- `semantic_data/class_tfidf.npy`, N×V;
- optionally `dynamic_data/class_calls.npy`.

HierDec is the pipeline `[["structural", "semantic"]]` (`hydec.py:12-15`).
Its defaults (`default_hyperparams.py:31-63`) are:

- structural: `call` similarity, epsilon 0.65;
- semantic: `mean` aggregation, epsilon 0.65;
- clustering: `alternating_epsilon`, `max_iterations` 1000, `min_samples` 2,
  `epsilon_step` 0.05, `include_outliers` false.

`call_similarity` (`similarity.py:4-16`) normalizes each column by the
callee's incoming total and symmetrizes. It accepts real weights.

RLDec (`decomp-rldec`) reads two parquet files indexed by class name
(README; `features.py:58-91`):

- `class_interactions.parquet`, N×N;
- `class_word_count.parquet`.

The README describes the second as N×M bag-of-words. The parsing service
actually writes an N×N word-intersection matrix: TF-IDF rows restricted to
terms in at most half the classes, multiplied by their transpose
(`decomp-parsing-service/decparsing/parsers/semParser.py:49-67`, with the
comment "misleading name"). RLDec's modularity requires a square matrix, so
our export must follow the code, not the README.

The CLI default is `combsequential` (`train_cli.py:29-30`). It uses the
structural and semantic features together. Its config
(`default_config_CombSequential.json`) sets:

- `max_microservices` 20, `use_ned` false, `use_coverage` false, outliers off;
- DQN with double and dueling heads;
- lr 0.005, gamma 0.99, epsilon from 1.0 to 0.02 over 10,000 steps;
- `num_gpus` 1, `seed` null;
- 20 iterations by default.

Granularity in both tools is the Spoon class `fullName`. The test fixture for
PetClinic (`decomp-hydec/tests/tests_data/petclinic-legacy/layers.pickle`)
contains test classes (`*Tests`, `AbstractClinicServiceTests`), anonymous
inner classes (`JdbcVetRepositoryImpl$1`, `PetTypeFormatterTests$2`) and
`MavenWrapperDownloader`. Sellami's class set is therefore not "application
classes only" by default. The proto has an `includeTest` flag
(`protos/analyze/v3/analyze.proto:86`), and its default is unknown.

The two tools also use different structural matrices
(`decparsing/parsers/structParser.py`):

- HierDec's `class_calls` counts method invocations by the static type of the
  invoked object, plus field calls (52-98).
- RLDec's `class_interactions` is the sum of seven matrices: field types,
  parameter types, return types, nested types, inheritance, calls, and
  referenced types (130-181). It is much denser than a call graph.

On reading, field-call edges in `class_calls` look dropped in non-distributed
mode. Line 91 tests `if self.classes:` where `if self.is_distributed:` is
evidently meant. That prefixes `serviceName + "."` to every target, so line 93
never matches. I have not run it to confirm.

Exporting our G is straightforward. Fix one order of the FQCN node list, write
it as `class_names.json`, and densify G into an N×N float matrix for both
`class_calls.npy` and `class_interactions.parquet`. Building the TF-IDF and
word-intersection matrices ourselves needs a tokenizer. The parsing service's
`TFIDFTransformer` (camelCase and `_` splitting, its own stopword list) can be
copied with attribution and fed our class bodies. D has no counterpart in
either tool, which is fine because neither uses one.

Using our G as the "same graph" changes what RLDec sees: interactions become
resolved calls rather than Sellami's seven-way union. That is the point of the
within-pipeline comparison, but it must be stated. RLDec on its own
interactions matrix would be a separate, labelled run.

## 3. Metric definitions compared

HierDec ships no metric code. The evaluation block in
`decomp-hydec/hydec/experiment.py:67-135` is commented out, so its reported
numbers came from elsewhere. RLDec's metrics live in
`decomp-rldec/rldec/metrics/` and are applied in `callbacks.py:189-222`.
Weerasinghe's definitions are Eq. 1 to 4 on pages 4-5 of `2601.23141v1.pdf`.

### SM

- Weerasinghe Eq. 1: scoh_i = μ_i / m_i², where μ_i is the number of calls
  inside partition i. scop_ij = γ_ij / (2 m_i m_j). SM is the mean scoh minus
  Σ_{i≠j} scop_ij divided by M(M−1)/2. The text leaves open whether i≠j means
  ordered or unordered pairs, and whether self-calls count in μ_i.
- `vendor/ror_msi/evaluate.py:32-94`: μ_i is a weighted sum of edge weights with self-calls
  excluded (line 63). γ_ij sums both directions over unordered pairs
  (lines 79-81), divided by M(M−1)/2. When M = 1 the denominator falls back to
  1 and SM = scoh.
- RLDec (`metrics/modularity.py:6-42`):
  - Binarizes the matrix first (`features > 0`), so it counts distinct edges,
    not calls.
  - Keeps the diagonal, so a class calling its own methods adds to cohesion.
  - Sums coupling over ordered pairs divided by M(M−1). That is the same as
    the unordered form with both directions.
  - Returns 0 when M < 2.
  - Computes SM on the interactions matrix, not on calls.

### IFN

- Eq. 2 is the mean over services of ifn_i. Weerasinghe does not define an
  interface. It cites FoSCI [8]. I have not checked FoSCI's definition, which
  may count exposed operations rather than classes.
- `vendor/ror_msi/evaluate.py:97-131`: an interface is a class called from another partition;
  IFN is the mean count over partitions.
- RLDec (`coupling.py:45-75`): the same class-level definition, on the
  interactions matrix, and IFN is 0 when M ≤ 1.

### ICP

- Eq. 3 defines a per-pair quantity c_ij / Σ_{i≠j} c_ij. Its denominator holds
  only cross-partition calls, so the values sum to 1 over pairs. The paper
  never says how the single ICP per tool in Table 1 is obtained. The prose
  calls it "the percentage of runtime calls occurring between two partitions".
- `vendor/ror_msi/evaluate.py:134-163`: cross-partition weight divided by total weight,
  self-calls excluded.
- RLDec (`coupling.py:6-42`): the same ratio but on log(1 + w) weights, with
  the diagonal included in the total.

These are three different numbers for the same partition.

### NED

- Eq. 4: 1 − n_nonextreme / N, with 5 ≤ |k| ≤ 20.
- `vendor/ror_msi/evaluate.py:166-186`: the same, [5, 20] inclusive.
- RLDec (`granularity.py:6-46`): the default `s_max = 19`, so a 20-class
  service counts as extreme there and not in Eq. 4.

### Shared issues

Outliers and coverage: `vendor/ror_msi/evaluate.py` silently ignores any class missing from
the partition list, together with its edges. RLDec excludes outliers when
`exclude_outliers` is set and also reports coverage. HierDec can leave
outliers when `include_outliers` is set. A method that drops classes can
improve all four metrics, so every comparison must report coverage.

Edge semantics: our G is not a call-count graph. Edges carry 1/n weights and
oracle coupling facts with weight 2 for associations and 1 for lookups
(`ConventionOracleV2.rb`, added to G at `RailsAwareGraphV2.rb:100-111`). Under `vendor/ror_msi/evaluate.py`, SM and ICP on G
therefore measure resolved evidence, not "calls" in Weerasinghe's sense. The
same applies to the Java G.

Eq. 5 and Weerasinghe's Score column: `vendor/ror_msi/evaluate.py:199-249` implements Eq. 5
with population std, W = (3, −1, −1, −1) and division by 6. I could not
reproduce the published Score column from the SM, IFN, ICP and NED cells
printed beside it. With that convention, 0 of 35 scores match at two
decimals, with a maximum absolute difference of 0.241. With sample std it is
also 0 of 35, maximum 0.163. Twelve variants were tried (four weight vectors,
three normalizations, two divisors), and the best matches 2 of 35. Source:
`results/recon/eq5_reproduce.py` and `eq5_reproduce.out`.

A least-squares fit of the published Scores on the per-benchmark z-scores
explains the gap (`results/recon/eq5_implied_weights.py` and
`eq5_implied_weights.out`). The fitted weights have the shape
(3, −1, −1, −1), with a residual of at most 0.006, which is rounding level.
The only difference is a constant scale factor. With sample-std z-scores
(ddof = 1) and division by 7 instead of 6, all 35 published Scores reproduce
exactly at two decimals. The divisors 6, 6.5 and 7.5 reproduce 0, 0 and 3 of
35. Both differences from the text only rescale the scores, so rankings
within a benchmark do not change.

Phase 7 will therefore compute Eq. 5 both ways: "as written" (population std,
divide by 6) and "as published" (sample std, divide by 7). Our rows are
comparable with their printed Score column only in the "as published" form.

The metrics are implemented in `java_pipeline/metrics.py`, with one core and
three named presets:

- `evaluate` matches `vendor/ror_msi/evaluate.py`;
- `weerasinghe` uses the same formulas, but its input must be call counts;
- `rldec` matches `decomp-rldec/rldec/metrics`.

Eq. 5 is available in both conventions. `tests/test_metrics.py` checks:

- the `evaluate` preset against `vendor/ror_msi/evaluate.py`, on 200 random weighted graphs
  with partial partitions;
- the `rldec` preset against RLDec's own functions, imported read-only, on
  200 random cases;
- Eq. 5 "as written" against `evaluate.compute_weerasinghe_scores`;
- Eq. 5 "as published" against all 35 cells of Table 1.

All 403 tests pass (`results/recon/test_metrics.out`). `vendor/ror_msi/evaluate.py` is
unchanged, because Rails results depend on it.

Provenance of Table 1, from the shaded cells on the page-8 render:

- Shaded, meaning Weerasinghe's own runs: the CHGNN and MonoEmbed rows, the
  HDBScan "Micro" dashes, and the whole Score column.
- Copied from cited papers: every other cell. Sources are [18] for Bunch, MEM,
  FoSCI, CoGCN and a-BMSC, [10] for Mono2Micro and [21] for HDBScan.
- Mono2Micro mixes sources within its row: metrics from [10], service count
  from [18].
- CHGNN on JPetStore is missing from the table.

## 4. What a fair comparison needs

Within our pipeline (Phase 6), the comparisons are fair when four things
hold:

1. Every method partitions the same class set: the same FQCN list, the same
   handling of inner and anonymous classes, the same test exclusion, and the
   same isolated-class filter.
2. Every method sees the same G: HierDec gets our G as `class_calls`, RLDec
   gets it as `class_interactions`, and so do the teacher and GraphRL-Dec.
3. One piece of metric code scores every partition. That is `vendor/ror_msi/evaluate.py`,
   with the Weerasinghe variant reported beside it where section 3 found
   differences.
4. Coverage is reported for every method.

Seeds and run counts must also match. RLDec's default seed is null, so we set
it.

Against the published numbers, none of these four can be guaranteed. The
published tools used their own class sets, and some used dynamic traces:
Mono2Micro needs traces, and AcmeAir and DayTrader results often come from
runtime data. Their numbers were mostly copied from papers rather than re-run,
and their metric code is unknown. Section 3 shows that even ICP has at least
three incompatible definitions in circulation. The external table can show
where we land, but it cannot support a claim of superiority. Phase 7 has to
present it that way.

## 5. Findings that bear on the Rails results

The Rails pipeline stores cannot-link as one representative pair per
namespace pair (`rules.py:451-468`) and offers the full cross-product through
`iter_cannot_link()` (`rules.py:158-173`). The two consumers disagree:

- The full expansion is used by the triplet negatives (`triplets.py:141-149`)
  and the encoder loss (`neural/loss.py:166`).
- Only the stored pairs are used by the RL action mask (`graph_env.py:601-605`)
  and the RQ4 violation count (`rl/constraint_eval.py:48`).

On the current `neurosymbolic/output/facts_v2/` files:

| app | stored (masked, counted) | expanded (encoder, triplets) |
|---|---|---|
| chatwoot-develop | 1,225 | 67,363 |
| canvas-lms | 1,540 | 205,124 |
| astuto-main | 0 | 143 |

Source: `results/recon/cannot_link_representation.out`.

If the paper's RQ4 claim reads as "zero violations of the namespace
boundary", it is measured on the stored pairs, not on the boundary. I have
not changed anything on the Rails side. The Java fact base should store
cannot-link as explicit pairs, so that the mask, the count and the loss all
see the same set.

## 6. Decisions needed before Phase 1

Answered on 2026-10-19:

- The analysis will be our own, not Sellami's jar.
- Network access for Maven is granted. Maven 3.9.9 is installed at
  `~/.local/opt/apache-maven-3.9.9`, with its SHA-512 checked.
- The metrics must be matched; section 3 records how.

The original questions follow.

1. **Sellami's analysis jar.** Should we run the bundled
   `java-analysis-service-1-3-0.jar` on each benchmark? It is Sellami's tool,
   already in the folder, so no cloning is needed. It would give a second,
   labelled set of inputs: RLDec and HierDec on their native analysis, next to
   both on our G. It would also give their class counts to compare with ours.
   It needs JDK 11 compatibility, which is untested on our JDK 21.
2. **Build tooling.** Maven is not installed. Can I download Maven, or use the
   benchmarks' `mvnw` wrappers, which fetch Maven and dependencies from the
   network? Without a classpath, the symbol solver's J6 failure count will be
   inflated by missing libraries rather than real ambiguity.
3. **RLDec's "default configuration".** The CLI default is `combsequential`
   (structural plus semantic, 20 iterations, `max_microservices` 20). I
   propose to use exactly that, with an explicit seed. Its default
   `num_gpus: 1` makes it a GPU run under your rule, so I will ask again
   before launching it.
4. **Which ICP and NED go in the headline table.** I propose `vendor/ror_msi/evaluate.py` as
   primary, since it is the Rails paper's metric code. The Weerasinghe-literal
   variants (NED [5, 20], ICP as cross over total calls on unweighted call
   counts) and the RLDec variants (binarized SM, log-weighted ICP, NED [5, 19])
   would go in a secondary table. Confirm or choose otherwise.
