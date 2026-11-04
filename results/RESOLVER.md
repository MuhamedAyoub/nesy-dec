# Phase 3: the layered Java resolver

Date: 2026-10-25. The user approved the Phase 2 audit and left the Phase 3
design decisions to me ("do what other SOTA did before"). Each decision below
says what was chosen, which prior work it follows, and how to reverse it.

The resolver is `java_pipeline/resolver.py`. It reads the analyzer's facts
(`results/<app>/facts/`) and the application's XML, and writes, per app:

- `graph.json`: G = (V, E, w) over fully qualified class names, and the data
  map D, in the Rails pipeline's schema (`dependency_graph`,
  `data_associations`, `resolver_report`, `isolated_classes`, `clusters`);
- `calls_graph.json`: the subgraph of call evidence only, for metrics defined
  on calls;
- `resolver/edges.jsonl`: one line per edge contribution, with layer, rule,
  weight and source position;
- `resolver/provenance.json`: the counts behind the tables below;
- `resolver/lookups.json`: every literal lookup name and what it bound to.

The tables are rendered from `provenance.json` and `audit.json` by
`java_pipeline/resolver_tables.py` into `results/resolver_tables.md`,
and inserted here unchanged.

## 1. Changes made to earlier phases

Three fixes upstream of the resolver. Every count in AUDIT.md and SUBJECTS.md
was regenerated after them.

- **Literature variants now have a classpath.** A classpath-only pom per
  variant (`java_pipeline/classpath/<variant>/pom.xml`) lists the libraries
  the variant's own `pom.xml` declares. No code from the variants is executed
  (SUBJECTS.md, section 2). Unresolved call sites fell from 463 to 0 in
  lit-jpetstore and from 276 to 0 in lit-pbw.
- **Analyzer 0.2.0.** It now also records field reads and writes that resolve
  to a field (`fieldrefs.jsonl`), every class literal, and the solver's type
  for an `X.class` argument. Without the last, AcmeAir's `CustomerImpl.class`
  was ambiguous between its two back ends. Call-site records are unchanged,
  and the Phase 2 tables regenerate identically.
- **Two XML-reading faults** (AUDIT.md section 1.4, faults 7 and 8):
  - commented-out beans were read as configuration;
  - a self-closing `<bean/>` absorbed the next bean's properties.

  The second was caught by the fixtures in section 6.

## 2. Design

### 2.1 Order of evidence

Every call site whose owner is an application class receives exactly one
resolution, tried strongest evidence first.

1. **J-L0, declared types.** The receiver's declared static type is a concrete
   application class, or a call on this or super binds to an application
   supertype.
2. **J-L2, injection.** The collaborator is fixed by configuration:
   - Spring XML wires a bean into the field the call goes through;
   - a JNDI name binds to an EJB, through `<ejb-ref>`/`<ejb-link>`,
     `@Stateless(name=...)` or the bean's simple name;
   - a Spring `getBean("id")` names a declared bean.
3. **J-L1, class hierarchy analysis.** The receiver is an application
   interface or abstract class, and no J-L2 binding applies.
4. **Refused**, when none of the above holds:
   - the solver could not type the call (unresolved);
   - a lookup name is not a literal (lookup_nonliteral);
   - an EJB or bean name is not declared (lookup_unbound);
   - an abstraction has more than K implementations (fanout).
5. **No edge** for calls on JDK or library types (external), calls a class
   makes to itself (self), and lookups of container resources (JMS factories,
   `UserTransaction`, `BeanManager`; rule lookup_resource).

J-L2 is tried before J-L1 although its number is higher. Configuration names
the one bean the container injects, while hierarchy analysis only names every
bean it could inject. Paper 1's principle of strongest evidence first decides
this, and the layer numbers follow the order given in the phase plan.

A call through an abstraction also keeps its declared edge to the
abstraction, at weight 1 (rule call_abstraction). The contract type is a real
compile-time dependency. For container-implemented interfaces, such as the 7
MyBatis mappers of jpetstore-6, it is the only Java-side endpoint.

Object creations, method references, field references, class literals and
direct inheritance between application classes are also J-L0. Field
references, class literals and inheritance are not calls, so they are left
out of `calls_graph.json`.

### 2.2 Bounded ambiguity

A J-L1 site with n concrete implementations contributes weight 1/n to each,
so that one site never weighs more than one call. With n > K the site is
refused. K = 5 is Paper 1's cap (`tools/v2/ResolverV2.rb`, `FANOUT_CAP`).
In these six apps no abstraction that is called has more than 5
implementations, so no site is refused for fan-out (Table R1). The cap is
exercised by a fixture (section 6).

### 2.3 Decisions taken for the user

**Alternative implementations (AcmeAir's morphia and wxs back ends,
lit-jpetstore's two DAO dialects and two web layers).** I kept every class
and split each ambiguous site 1/n. I did not exclude one alternative, for two
reasons.

- The comparison rows of Weerasinghe Table 1 come from tools that analyse the
  whole source tree: Spoon in HierDec and RLDec, and the MonoEmbed and CHGNN
  pipelines. The published AcmeAir count, 86, is larger than the morphia-only
  build. All seven AcmeAir modules give 84 named types, 81 of them top level
  (`results/recon/acmeair_all_modules/run.json`). The six-module scope
  used here gives 72. Which 86 classes the papers counted cannot be
  reconstructed exactly. It certainly includes both back ends, because the
  morphia-only scope has 57 compiled classes (SUBJECTS.md, section 3).
- A 1/n split is Paper 1's rule for genuinely multi-valued sites, and it keeps
  each site's total weight at one.

Excluding an alternative would need a single line in `SUBJECTS`. It would
change the class set, so it would be reported as a separate, labelled run.

**Type-use edges (the audit's J7).** They are included in G as their own
layer, J-T: weight 1 per distinct (owner, type) pair, plus annotation types
used on a class or its members. Sellami's `class_interactions` matrix counts
field, parameter, return and referenced types (`structParser.py:130-181`), so
RLDec's published numbers already rest on this kind of evidence. It is kept
out of `calls_graph.json`, and the layer label allows a run without it.

**Pages and request mappings (J5).** Struts form beans are linked to their
actions. Nothing else from pages or request mappings is turned into an edge:
JSP and JSF EL bean references, and Stripes and JAX-RS URL bindings.

- A page links an entry point to the classes it displays. That is evidence of
  co-use, not of a dependency between those classes.
- No prior static tool in the comparison links classes through pages.

Page co-reference goes to Phase 4 as a candidate soft-affinity fact instead.
An entry point therefore still has no inbound edge, which is correct for a
servlet.

## 3. The rules

Each rule as a typing rule in the style of Paper 1, Table I: premise, then
what it adds. Every rule's edge carries its layer and rule name in
`edges.jsonl`.

| layer | rule | premise | conclusion | weight |
|---|---|---|---|---|
| J-L0 | call_declared | call `e.m()` in C, declared type of `e` is a concrete app class T | C → T | 1 per site |
| J-L0 | call_inherited | call `m()`, `this.m()` or `super.m()` in C binds to `m` declared by app supertype S | C → S | 1 per site |
| J-L0 | call_abstraction | call `e.m()` in C, declared type of `e` is an app interface or abstract class A | C → A | 1 per site |
| J-L0 | creation, anon_impl | `new T(...)` or `new T() {...}` in C, T an app class | C → T | 1 per site |
| J-L0 | method_ref | `T::m` in C, `m` declared by app class T | C → T | 1 per site |
| J-L0 | field_ref | C reads or writes field `f` declared by app class T ≠ C | C → T | 1 per site |
| J-L0 | class_literal | `T.class` in C, T an app class | C → T | 1 per site |
| J-L0 | inheritance | C extends or implements app type S | C → S | 1 per pair |
| J-L2 | spring_xml_property | call through field `f` of C; Spring XML bean of class C (or a subclass) has `<property name="f" ref="r">`, bean `r` has class B, B a subtype of the declared type | C → B (one of the k wired classes) | 1/k per site |
| J-L2 | jndi_ejb | `lookup("…/n")` in C with a literal name; `n` maps through `<ejb-ref-name>`/`<ejb-link>` or directly to an EJB named `n` with class B | C → B | 1 per site |
| J-L2 | spring_getbean | `getBean("r")` in C; bean `r` has app class B (in any of k XML files) | C → B | 1/k per site |
| J-L1 | cha | call through app abstraction A with concrete app subtypes I₁…Iₙ, n ≤ K, no J-L2 binding | C → Iᵢ for each i | 1/n per site |
| J-L3 | jpa_assoc | field of entity E annotated `@OneToMany`, `@ManyToOne`, `@OneToOne` or `@ManyToMany`, typed (or type argument) entity T | E → T; T ∈ D(E) | 2 per pair |
| J-L3 | mybatis_mapper | `<mapper namespace="M">` whose result, parameter or `ofType` types name domain class T, directly or through `typeAliasesPackage`/`<typeAlias>` | M → T; T ∈ D(M) | 1 per pair |
| J-L3 | ibatis_sqlmap | DAO C calls `insert/update/delete/queryFor*("s")` with literal statement id `s` of a `<sqlMap>` mapping class T | C → T; T ∈ D(C) | 1 per pair |
| J-L3 | entity_class_literal | a call in C passes `T.class` for entity T (`em.find`, `createQuery`, Morphia `createQuery`) | C → T; T ∈ D(C) | 1 per pair |
| J-L3 | jpa_named_query | `createNamedQuery("q")` in C, entity T declares `@NamedQuery(name = "q")` | C → T; T ∈ D(C) | 1 per pair |
| J-L3 | sql_table | a SQL- or JPQL-shaped string literal in C's file (concatenations joined, comments skipped) names T's table, entity name or class name after `from`, `into`, `update` or `join`; names shared by two entities are dropped | C → T; T ∈ D(C) | 1 per pair |
| J-L3 | struts_form_bean | `<action type="A" name="f">` and `<form-bean name="f" type="F">` | A → F | 1 per pair |
| J-T | type_use | C declares a field, parameter, return or type argument of app type T | C → T | 1 per pair |
| J-T | annotation_use | C or one of its members carries annotation `@T`, T an app annotation type | C → T | 1 per pair |

The weights 2 and 1 for association and lookup facts are Paper 1's
(`ConventionOracleV2.rb`). Entities are the classes annotated `@Entity`
(JPA or Morphia) plus the domain classes named by MyBatis or iBatis XML.
D(C) is filled only by the J-L3 rules, as in Paper 1, where D came only from
association and model-lookup facts.

EJB home/remote ↔ bean (listed in the phase plan) needs no rule of its own
here. DayTrader's and lit-pbw's beans implement their business interfaces
directly, so J-L1 links them, and the JNDI names bind through jndi_ejb. No
subject uses EJB 2 home interfaces outside comments. Spring Data repositories were rejected in
Phase 2 (no subject uses them).

## 4. Provenance

#### Table R1. Call-site resolution (one resolution per site)

| app | call sites | J-L0 | J-L1 | J-L2 | external | self | refused | refused by reason |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 250 | 143 (57.2%) | 0 (0.0%) | 0 (0.0%) | 85 (34.0%) | 22 (8.8%) | 0 (0.0%) | - |
| acmeair | 1142 | 141 (12.3%) | 115 (10.1%) | 0 (0.0%) | 695 (60.9%) | 50 (4.4%) | 141 (12.3%) | lookup_nonliteral 9, unresolved 132 |
| daytrader7 | 3691 | 1119 (30.3%) | 40 (1.1%) | 7 (0.2%) | 1907 (51.7%) | 616 (16.7%) | 2 (0.1%) | lookup_nonliteral 2 |
| plantsbywebsphere | 1178 | 583 (49.5%) | 0 (0.0%) | 0 (0.0%) | 415 (35.2%) | 180 (15.3%) | 0 (0.0%) | - |
| lit-jpetstore | 913 | 316 (34.6%) | 26 (2.8%) | 39 (4.3%) | 514 (56.3%) | 18 (2.0%) | 0 (0.0%) | - |
| lit-pbw | 1264 | 587 (46.4%) | 0 (0.0%) | 0 (0.0%) | 480 (38.0%) | 197 (15.6%) | 0 (0.0%) | - |

#### Table R2. Share of edge weight in G by layer

| app | total weight | J-L0 calls | J-L0 non-call refs | J-L1 | J-L2 | J-L3 | J-T |
|---|---|---|---|---|---|---|---|
| jpetstore-6 | 227.0 | 68.3% | 10.1% | 0.0% | 0.0% | 3.1% | 18.5% |
| acmeair | 629.0 | 47.5% | 18.1% | 18.3% | 0.0% | 1.0% | 15.1% |
| daytrader7 | 1535.2 | 80.8% | 9.3% | 2.1% | 0.5% | 2.0% | 5.4% |
| plantsbywebsphere | 805.0 | 75.8% | 14.2% | 0.0% | 0.0% | 3.0% | 7.1% |
| lit-jpetstore | 590.5 | 67.4% | 6.9% | 4.3% | 6.6% | 4.6% | 10.2% |
| lit-pbw | 811.0 | 75.7% | 14.4% | 0.0% | 0.0% | 3.0% | 6.9% |

#### Table R3. Rule activity: call sites per site rule, class pairs per fact rule

| app | call_declared | call_inherited | call_abstraction | cha_n1 | cha_n2 | cha_n3+ | spring_xml_property | jndi_ejb | spring_getbean | lookup_resource | creation | method_ref | field_ref | class_literal | inheritance | jpa_assoc | mybatis_mapper | ibatis_sqlmap | entity_class_literal | jpa_named_query | sql_table | struts_form_bean | type_use | annotation_use |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 106 | 10 | 27 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 10 | 2 | 14 | 5 | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 42 | 0 |
| acmeair | 141 | 0 | 0 | 1 | 114 | 0 | 0 | 0 | 0 | 8 | 43 | 0 | 35 | 47 | 32 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 88 | 7 |
| daytrader7 | 1119 | 0 | 0 | 3 | 2 | 35 | 0 | 7 | 0 | 12 | 81 | 0 | 105 | 30 | 8 | 9 | 0 | 0 | 6 | 1 | 5 | 0 | 80 | 3 |
| plantsbywebsphere | 583 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 94 | 20 | 0 | 4 | 0 | 0 | 9 | 7 | 0 | 0 | 57 | 0 |
| lit-jpetstore | 266 | 50 | 0 | 24 | 2 | 0 | 37 | 0 | 2 | 0 | 19 | 0 | 2 | 7 | 32 | 0 | 0 | 10 | 0 | 0 | 0 | 17 | 60 | 0 |
| lit-pbw | 584 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 27 | 0 | 96 | 20 | 1 | 4 | 0 | 0 | 9 | 7 | 0 | 0 | 56 | 0 |

#### Table R4. Naive graph against the resolved graph

| app | class nodes | naive edges | call-graph edges | G edges | isolated (naive) | isolated (call graph) | isolated (G) | entities | classes with D entries |
|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 24 | 38 | 40 | 55 | 1 (4.2%) | 1 (4.2%) | 0 (0.0%) | 7 | 7 |
| acmeair | 72 | 86 | 185 | 264 | 23 (31.9%) | 10 (13.9%) | 2 (2.8%) | 6 | 3 |
| daytrader7 | 115 | 213 | 254 | 299 | 24 (20.9%) | 14 (12.2%) | 11 (9.6%) | 5 | 8 |
| plantsbywebsphere | 37 | 80 | 86 | 101 | 2 (5.4%) | 2 (5.4%) | 2 (5.4%) | 6 | 10 |
| lit-jpetstore | 73 | 128 | 168 | 219 | 9 (12.3%) | 6 (8.2%) | 2 (2.7%) | 7 | 8 |
| lit-pbw | 39 | 80 | 86 | 100 | 3 (7.7%) | 3 (7.7%) | 3 (7.7%) | 6 | 10 |

#### Table R5. Classes isolated in G

| app | isolated classes |
|---|---|
| jpetstore-6 | - |
| acmeair | BigIntegerConverter, MapPutAllAgent |
| daytrader7 | ExternalContextProducer, JSFLoginFilter, PingCDIJSFBean, PingManagedExecutor, PingReentryServlet, PingServlet2IncludeRcv, PingServlet30Async, PingServletLargeContentLength, PingWebSocketBinary, PingWebSocketTextAsync, PingWebSocketTextSync |
| plantsbywebsphere | NoSupplierException, OrderKey |
| lit-jpetstore | SignoffController, SignonInterceptor |
| lit-pbw | NoSupplierException, OrderKey, RedirectionFilter |

## 5. What the resolver changes

The Phase 2 audit found that the naive Java graph was too sparse rather than
wrong. The resolver mostly adds evidence; it does not remove any naive edge.

- Isolated classes drop from 23 to 2 in AcmeAir, 24 to 11 in DayTrader, 9 to
  2 in lit-jpetstore and 1 to 0 in jpetstore-6 (Table R4).
- The remaining isolated classes are listed in Table R5 and were checked by
  hand:
  - Plants' `OrderKey` and `NoSupplierException` are referenced only from
    their own files and from comments.
  - 9 of DayTrader's 11 are `web/prims` micro-benchmark servlets and
    websocket endpoints that touch no other application class.
  - AcmeAir's two are a wxs agent and a Morphia converter.

  The pipeline drops isolated classes before clustering, as the Rails
  pipeline does. They are listed in `graph.json` under `isolated_classes`.
- The data map D is now non-empty in every app: 7 classes in jpetstore-6, 3
  in AcmeAir, 8 in DayTrader, 10 in Plants and lit-pbw, 8 in lit-jpetstore
  (Table R4). The naive graph had none.
- Refusals are small and named:
  - 9 non-literal lookups in AcmeAir's `ServiceLocator` and 2 in DayTrader;
  - AcmeAir's 132 wxs call sites on IBM's proprietary objectgrid types.

  No site was refused for fan-out.

AcmeAir is the subject the resolver changes most. J-L1 carries 18.3% of its
edge weight, and 114 of its 115 dispatch sites split between the two back
ends (Tables R2, R3).

## 6. Fixtures

`tests/fixtures/resolver_app/` is a synthetic project of 33 Java files
and 3 XML files. `tests/fixtures/stubs/` holds annotation and interface
stubs for `javax.persistence`, `javax.ejb` and Spring's `ApplicationContext`.
`tests/test_resolver.py` compiles the stubs, runs the real analyzer jar
and the resolver, and checks one assertion group per rule. Rules with a
fixture:

- **J-L0:** call_declared, call_inherited, call_abstraction (on a local and
  on an interface with no Java implementation), creation, anon_impl,
  method_ref, field_ref, class_literal, inheritance.
- **J-L1:** cha with one implementation (weight 1), with two (weight 0.5
  each), and with six (refused, fanout).
- **J-L2:** spring_xml_property (only the wired bean, not the other
  implementation), spring_getbean (a commented-out alternative bean is
  ignored), jndi_ejb.
- **J-L3:** jpa_assoc (both sides, weight 2), entity_class_literal,
  jpa_named_query, sql_table (a concatenated literal counts, a comment does
  not), mybatis_mapper (through `typeAliasesPackage`), struts_form_bean.
- **J-T:** type_use, annotation_use.
- **Refusals and no-edge outcomes:** unresolved, lookup_nonliteral,
  lookup_resource.
- **Outputs:** the exact data map D, the call graph's exclusion of non-call
  evidence, and the schema contract: every edge endpoint is a node and the
  key sets match.

Without a fixture:

- lookup_unbound, a literal EJB or bean name that no declaration binds. It
  occurs in no subject.
- cha with 3 to 5 implementations. The weight code is the same as for 2, and
  DayTrader exercises it with `TradeServices` (35 sites, Table R3).

All 29 resolver tests pass, as do the 403 metric tests and the 8 audit
classifier tests: 440 in `tests/` (`python3 -m pytest tests -q`).

## 7. Limits

- A lookup result stored in a field does not bind later calls through that
  field. They go through J-L1 instead. DayTrader's `TradeAction.tradeLocal`
  is typed `TradeSLSBLocal`, which has one implementation, so this costs
  nothing there.
- CDI qualifiers are not resolved. AcmeAir's `@DataService` qualifier selects
  a back end at run time from a system property (`ServiceLocator`), so 1/2 is
  the static truth.
- No call sites are resolved in AcmeAir's wxs module (proprietary jar), and
  they are refused as unresolved. Its classes stay in the graph through
  inheritance, type use and creations.
- G's weights mix calls (1 per site) with facts (1 or 2 per pair). G is
  therefore resolved evidence, not a call count, exactly as in Paper 1.
  Metrics that Weerasinghe defines on calls are computed on
  `calls_graph.json` in Phase 7.
