# Phase 4: Java symbolic facts

Date: 2026-10-25, cannot-link revised 2026-11-03. The extractor is `java_pipeline/facts.py`. It writes, per
app:

- `results/<app>/facts_nesy.json`: the fact base, in the schema that
  `SymbolicFacts.from_json` reads, plus `inferred_coupling`;
- `results/<app>/facts_report.json`: the counts behind the tables below.

The tables are rendered by `java_pipeline/facts_tables.py` into
`results/facts_tables.md`, and inserted here unchanged.

Every class name is a fully qualified name taken from G, so no qualification
pass is needed. The exact-match check that `qualify_facts_v2.py` exists for is
still run (section 4).

## 1. The relations

**must_link.** It mirrors what Rails treated as hard same-service evidence:
associations, model lookups and service calls (`rules.py`, reasons `assoc:*`,
`rails:model_lookup`, `rails:service_call`). The Java reasons are:

- `jpa:assoc:<Kind>`: a JPA association field;
- `jpa:entity_lookup`: entity access through an `EntityManager` class
  literal, a named query, or a SQL or JPQL literal (the J-L3 rules
  entity_class_literal, jpa_named_query and sql_table), the analogue of
  `rails:model_lookup`;
- `mybatis:mapper` and `ibatis:sqlmap`: a binder and its domain class;
- `di:wired`: a J-L2 binding (Spring XML property, JNDI EJB name, `getBean`
  id);
- `di:inject`: an injection point (`@Inject`, `@EJB`, `@Resource`,
  `@Autowired`, `@SpringBean`, implicit constructor injection) typed by a
  concrete app class, or by an abstraction with exactly one implementation.
  This is the analogue of `rails:service_call`.
- `ejb:business_interface`: a session bean and the app interfaces it
  implements;
- `struts:form_bean`: a Struts action and its form bean.

**framework_noise.** Assigned by a documented rule, not a hand-picked list.

- N1, generic base: an app abstract class with at least 3 concrete app
  subclasses.
- N2, constants holder: static fields only, with no methods, constructors or
  instance fields.
- N3, ubiquitous helper: a class of role util or config that at least 20% of
  the other active classes reference in G.

Table F5 lists what each rule selected. The selections are DayTrader's `Log`
and `TradeConfig`, Plants' `Util`, the Struts and Stripes base actions, and
AcmeAir's two back-end constants holders.

**soft_affinity.** Graded, summed per pair and capped at 1.0, as in Rails.

- `role:<r>`, 0.15. This is Rails' role weight. It is not applied to the
  catch-all roles other, interface and unknown.
- `package:<p>`, weight max(0.1, min(1, 2/n)) for n classes in the package.
  This is Rails' concern co-inclusion weight, which grades a two-class
  package high and a 48-class package low.
- `page:<file>`, with the same grading, for classes named together on one
  JSP or JSF page. This is the page co-reference that Phase 3 kept out of G
  (RESOLVER.md, section 2.3).

**inferred_coupling.** `neurosymbolic.infer_coupling.transitive_coupling`,
unchanged, applied to G.

**Roles.** Java stereotypes replace the 24 Rails role directories. There are
16 roles (`facts.ROLES`), each class taking the first matching rule in
`role_of()`:

- entity (`@Entity`/`@Embeddable` or a SQL-mapped domain type);
- repository (`@Repository`, a SQL-mapping binder, or a Dao, Repository or
  Mapper name or supertype);
- message_driven, ejb_session;
- servlet (annotation or supertype);
- web_controller (Struts Action, Stripes ActionBean, Spring Controller,
  JAX-RS `@Path`, or a Controller or ActionBean name);
- websocket;
- ui_bean (`@Named`/`@ManagedBean`);
- form;
- exception;
- config;
- service (an annotation, or a Service, Facade, Manager, Mgr or Logic name);
- util (static members only, or a Util or Helper name);
- interface;
- other.

A class that matches no rule takes the role of an app service or repository
type it implements. Table F4 gives the counts. The role vocabulary reaches
the RL policy's one-hot through `java_pipeline/rl_paths.py`.

## 2. Cannot-link: rule CL-SIBLING

In Rails, cannot-link came from disjoint top-level namespaces. Java code has
no such namespace convention, so the first version of this phase stored no
cannot-link at all. A second review of the six subjects
(`results/facts_survey/constraint_review.py` and
`cannot_link_candidates.py`, outputs in `.out` files beside them) found a
boundary that Java does have: sibling packages that are peers and never
reference each other. That boundary is rule CL-SIBLING in
`java_pipeline/facts.py` (`sibling_cannot_link`).

Two sibling packages A and B (one parent package; each counted with its
sub-packages) are disjoint when all three conditions hold:

1. each holds at least 2 active classes that are not framework noise;
2. no direct edge (J-L0, J-L2, J-L3) and no type-use edge (J-T) joins them,
   in either direction. J-L1 edges are the resolver's own 1/n
   over-approximation of dynamic dispatch, not code evidence, so they do not
   count;
3. they are peers: the same dominant layer by stereotype (`LAYER_OF_ROLE`:
   presentation, business or data), or their classes implement at least one
   common application interface, which makes them alternative
   implementations.

Every pair (a, b) with a in A and b in B is stored explicitly, tagged
`cl_sibling:<A>|<B>`. `namespaces` stays empty, so the RL mask, the RQ4 count
and the encoder loss all see one and the same set. This avoids the Rails
inconsistency between stored and expanded pairs (RECON.md, section 5).

Condition 3 is what keeps technical layers out. A web package and a data
package with no edge between them are not disjoint: a service may need both.
Condition 2 keeps out any pair the code itself couples.

The package pairs the rule accepted (`<app>/facts_report.json`, field
`cannot_link.package_pairs`):

| subject | package A (active classes) | package B (active classes) | why they are peers | pairs |
|---|---|---|---|---|
| daytrader7 | `web.jsf` (12) | `web.prims` (50) | both presentation | 600 |
| daytrader7 | `web.jsf` (12) | `web.websocket` (7) | both presentation | 84 |
| acmeair | `morphia` (13) | `wxs` (13) | 8 common application interfaces (`BookingService`, `Customer`, `Flight`, ...) | 169 |
| lit-jpetstore | `web.spring` (16) | `web.struts` (22) | both presentation | 352 |

jpetstore-6, plantsbywebsphere and lit-pbw have no package pair that meets
all three conditions, so their cannot-link set is empty. No accepted pair
conflicts with a must-link fact (Table F3).

What each boundary means in the code:

- DayTrader: the JSF front end is separate from the two other web entry
  points, the servlet and JSP primitives used for benchmarking (`web.prims`)
  and the WebSocket endpoints. No edge of G joins `web.jsf` to either.
  `web.prims` and `web.websocket` are joined by 3 edges (`graph.json`), so
  the rule does not separate those two.
- AcmeAir: the MongoDB (`morphia`) and WebSphere eXtreme Scale (`wxs`) back
  ends implement the same service interfaces. `build.gradle:65-91` packages
  both into one WAR, and `ServiceLocator` picks one at run time. The first
  version of this section rejected this boundary because both are deployed.
  The rule takes the other reading: two implementations of one interface are
  alternatives, and a service that holds one need not hold the other.
- lit-jpetstore: the Spring MVC and Struts web layers both front the same
  `PetStoreFacade`. `web.xml:88-102` deploys both servlets, and neither
  references the other.

Boundaries the review looked at and the rule does not produce:

- the jpetstore-6 and plantsbywebsphere packages, which are technical layers;
- the AcmeAir Gradle modules (webapp → services → common) and the DayTrader
  EAR split (146 edges web → EJB, 0 EJB → web), which are tiers crossed in one
  direction;
- `pbw-lib` in lit-pbw, which holds 2 utility classes used from the WAR.

The rule was written after the review of these six subjects. Applying it
unchanged to Java systems it was not designed on is still to be done.

The consequences for the pipeline:

- NeSy-Rep's design rule is (λ_ml, λ_cl) = (0.0, 0.3), as in the Rails runs.
  The cannot-link term is a hinge with margin 0.5 on the distance between
  unit-norm embeddings. Most pairs already meet it: on the pretrained
  embeddings, 13 of the 1,205 pairs are closer than 0.5 (7 in AcmeAir, 0 in
  DayTrader, 6 in lit-jpetstore). The fact base acts on the encoder mainly
  through the triplets. `java_pipeline/triplets.py` now draws cannot-link
  negatives: 562 in AcmeAir, 750 in DayTrader and 750 in lit-jpetstore.
- The RL environment masks every action that would place a class with a
  cannot-link partner. `run_gpu.py --stages check` confirms the environment
  loads the same number of cannot-link pairs as the fact base (section 4).

## 3. Counts

#### Table F1. Facts per relation: raw, matched to a node of G, dropped, both endpoints active

| app | relation | raw | matched | dropped | unique pairs | both endpoints active |
|---|---|---|---|---|---|---|
| jpetstore-6 | must_link | 12 | 12 | 0 | 12 | 12 |
| jpetstore-6 | cannot_link | 0 | 0 | 0 | 0 | 0 |
| jpetstore-6 | soft_affinity | 136 | 136 | 0 | 70 | 136 |
| jpetstore-6 | inferred_coupling | 15 | 15 | 0 | 15 | 15 |
| acmeair | must_link | 13 | 13 | 0 | 13 | 13 |
| acmeair | cannot_link | 169 | 169 | 0 | 169 | 169 |
| acmeair | soft_affinity | 347 | 347 | 0 | 307 | 343 |
| acmeair | inferred_coupling | 66 | 66 | 0 | 66 | 66 |
| daytrader7 | must_link | 50 | 50 | 0 | 41 | 50 |
| daytrader7 | cannot_link | 684 | 684 | 0 | 684 | 684 |
| daytrader7 | soft_affinity | 2670 | 2670 | 0 | 2053 | 1972 |
| daytrader7 | inferred_coupling | 86 | 86 | 0 | 86 | 86 |
| plantsbywebsphere | must_link | 41 | 41 | 0 | 38 | 41 |
| plantsbywebsphere | cannot_link | 0 | 0 | 0 | 0 | 0 |
| plantsbywebsphere | soft_affinity | 261 | 261 | 0 | 213 | 242 |
| plantsbywebsphere | inferred_coupling | 41 | 41 | 0 | 41 | 41 |
| lit-jpetstore | must_link | 66 | 66 | 0 | 44 | 66 |
| lit-jpetstore | cannot_link | 352 | 352 | 0 | 352 | 352 |
| lit-jpetstore | soft_affinity | 1208 | 1208 | 0 | 864 | 1142 |
| lit-jpetstore | inferred_coupling | 139 | 139 | 0 | 139 | 139 |
| lit-pbw | must_link | 40 | 40 | 0 | 37 | 40 |
| lit-pbw | cannot_link | 0 | 0 | 0 | 0 | 0 |
| lit-pbw | soft_affinity | 253 | 253 | 0 | 198 | 232 |
| lit-pbw | inferred_coupling | 40 | 40 | 0 | 40 | 40 |

#### Table F2. Must-link facts by reason (a pair may carry several reasons)

| app | jpa:assoc | jpa:entity_lookup | mybatis:mapper | ibatis:sqlmap | di:wired | di:inject | ejb:business_interface | struts:form_bean | unique pairs |
|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 0 | 0 | 7 | 0 | 0 | 5 | 0 | 0 | 12 |
| acmeair | 0 | 6 | 0 | 0 | 0 | 7 | 0 | 0 | 13 |
| daytrader7 | 8 | 11 | 0 | 0 | 6 | 19 | 3 | 0 | 41 |
| plantsbywebsphere | 4 | 13 | 0 | 0 | 0 | 21 | 0 | 0 | 38 |
| lit-jpetstore | 0 | 0 | 0 | 10 | 17 | 0 | 0 | 17 | 44 |
| lit-pbw | 4 | 13 | 0 | 0 | 0 | 20 | 0 | 0 | 37 |

#### Table F3. Soft-affinity pairs by source, framework noise, and conflicts

| app | role | package | page | unique soft pairs | pages naming ≥2 classes | framework noise | must/cannot conflicts | must-link pairs touching noise |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 55 | 70 | 11 | 70 | 7 | 1 | 0 | 0 |
| acmeair | 129 | 218 | 0 | 307 | 0 | 2 | 0 | 0 |
| daytrader7 | 1197 | 1393 | 80 | 2053 | 21 | 2 | 0 | 0 |
| plantsbywebsphere | 51 | 200 | 10 | 213 | 6 | 1 | 0 | 0 |
| lit-jpetstore | 681 | 527 | 0 | 864 | 0 | 2 | 0 | 1 |
| lit-pbw | 53 | 190 | 10 | 198 | 6 | 1 | 0 | 0 |

#### Table F4. Roles (Java stereotypes)

| app | entity | repository | service | ejb_session | message_driven | servlet | web_controller | websocket | ui_bean | form | exception | config | util | interface | other | unknown |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 7 | 7 | 3 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| acmeair | 6 | 0 | 13 | 0 | 0 | 1 | 6 | 0 | 0 | 0 | 0 | 7 | 0 | 9 | 30 | 0 |
| daytrader7 | 5 | 0 | 1 | 3 | 2 | 48 | 0 | 5 | 9 | 0 | 0 | 3 | 4 | 4 | 31 | 0 |
| plantsbywebsphere | 7 | 0 | 5 | 1 | 0 | 3 | 0 | 0 | 6 | 0 | 2 | 0 | 2 | 0 | 11 | 0 |
| lit-jpetstore | 7 | 13 | 4 | 0 | 0 | 0 | 34 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 9 | 0 |
| lit-pbw | 7 | 0 | 0 | 7 | 0 | 4 | 0 | 0 | 3 | 0 | 2 | 0 | 2 | 0 | 14 | 0 |

#### Table F5. Framework-noise classes and the rule that selected each

| app | classes |
|---|---|
| jpetstore-6 | AbstractActionBean (N1 generic base (4 concrete subclasses)) |
| acmeair | MorphiaConstants (N2 constants holder); WXSConstants (N2 constants holder) |
| daytrader7 | Log (N3 ubiquitous util (referenced by 60% of active classes)); TradeConfig (N3 ubiquitous config (referenced by 41% of active classes)) |
| plantsbywebsphere | Util (N3 ubiquitous util (referenced by 71% of active classes)) |
| lit-jpetstore | BaseAction (N1 generic base (18 concrete subclasses)); SecureBaseAction (N1 generic base (6 concrete subclasses)) |
| lit-pbw | Util (N3 ubiquitous util (referenced by 63% of active classes)) |

## 4. Qualification check

Every fact endpoint is a node of G: no fact of any relation was dropped in
any app (Table F1, column dropped). The check that matters for the RL stage
is the environment's own filter. The environment keeps classes present in
both the graph and the embedding bank, by exact name (`graph_env.py`).

`python3 -m java_pipeline.run_gpu --stages check` loads every app into the
real environment with the pretrained embedding bank. For every app, the
environment keeps all N active classes and all must-link pairs (12, 13, 41,
38, 44 and 37), equal to the active pairs in the fact base. It also keeps
every cannot-link pair (0, 169, 684, 0, 352 and 0). The Chatwoot
failure mode, where 1 of 1,891 cannot-link facts survived, cannot occur
silently here: the check fails when the counts differ.

Soft-affinity pairs touching an isolated class are kept in the fact base but
are dropped by the environment, which only sees active classes. Table F1
reports them in the column "both endpoints active".

## 5. Differences from the Rails facts

- **Must-link evidence comes from different sources.** Rails must-link came
  almost entirely from model lookups and associations: 4,322 of 4,416 facts
  over the eight `facts_v2` files. Service calls contributed 30 and mailer or
  job triggers 64. On Java, injection (di:inject plus di:wired) supplies the
  following share of the unique must-link pairs (`facts_nesy.json`): 21 of 41
  in DayTrader, 21 of 38 in Plants, 20 of 37 in lit-pbw, 17 of 44 in
  lit-jpetstore, 7 of 13 in AcmeAir and 5 of 12 in jpetstore-6.
- **Cannot-link comes from sibling packages, not namespaces.** Rule
  CL-SIBLING (section 2) gives 684 pairs in DayTrader, 169 in AcmeAir and 352
  in lit-jpetstore, and none in the other three subjects. In Rails the pairs
  came from disjoint top-level namespaces.
- **Splitting dispatch 1/n couples the two AcmeAir back ends.** It creates
  edges between their classes: 10 morphia → wxs and 11 wxs → morphia
  (`module_edges.json`). This is the cost of keeping both alternatives
  (RESOLVER.md, section 2.3). Those pairs receive no must-link: no rule
  relates them.
