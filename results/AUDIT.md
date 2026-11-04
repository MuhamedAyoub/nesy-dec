# Phase 2: the naive Java graph and the audit of how it fails

Date: 2026-10-24. Scope decisions are those recommended in SUBJECTS.md
section 5, which the user approved ("do your best and be agentic"):

- both version sets, labelled;
- AcmeAir's six `settings.gradle` modules, with wxs parsed from source;
- top-level and named member types as nodes, with anonymous and local classes
  folded into their enclosing class.

The two literature variants (`lit-jpetstore` = KimJongSung/jPetStore @bc3fe89,
`lit-pbw` = pbw-monolith @e6f2a6a) are not built. Their symbol solver gets a
classpath from a classpath-only pom per variant
(`java_pipeline/classpath/<variant>/pom.xml`). Each lists the libraries the
variant's own `pom.xml` declares, mapped to Maven Central coordinates where the
declared SpringSource bundles no longer exist (SUBJECTS.md, section 2).

All numbers below come from `results/<app>/audit/audit.json`. The tables
are rendered from those files by `java_pipeline/audit_tables.py` into
`results/audit_tables.md`, and inserted here unchanged.
`results/audit_table.csv` holds the same counts as one row per app.

## 1. Method

### 1.1 Parser choice

I used JavaParser 3.26.2 with its symbol solver rather than Spoon, for three
reasons:

- **Per-call-site failures.** JavaParser resolves one expression at a time and
  reports why each resolution failed. That gives the per-call-site refusal
  count (J6) Paper 1's discipline requires. Spoon builds a whole model and, in
  no-classpath mode, fills gaps silently.
- **Exact positions.** Every fact keeps its file and line, which the audit
  examples need.
- **Independence.** Sellami's analysis service is built on Spoon. A different
  front end keeps our graph independent of theirs, which matters when the two
  are later compared.

The solver chain is:

1. JDK types through the platform class loader;
2. the application's own source roots;
3. the jars on the app's build classpath (`results/<app>/facts/config.json`).

The analyzer is `java_analyzer/` (`nesydec.analyzer.Main`). It records facts
only:

- types with supertypes, annotations, fields, constructors and methods;
- every method call, with the receiver's declared static type, the bound
  declaration, or the exception explaining why neither resolved;
- object creations and method references.

It never runs the analyzed code. All six subjects parsed with zero failures
(`results/<app>/facts/run.json`).

### 1.2 The naive graph

The naive graph (`java_pipeline/audit.py`) is the Java analogue of Paper 1's
L0/L1. A method call adds an edge from its owner class to T, the declared
static type of the receiver. Calls on `this` or `super`, explicit or implicit,
and static calls through a type name bind to the declaring type of the
resolved method.

It uses nothing else: no hierarchy, no injection, no XML. Edge weight is the
call count. The result is written to `results/<app>/naive_graph.json` in
the Rails pipeline's schema.

### 1.3 Classification

Every call site whose owner is an application class falls into exactly one
category:

| category | meaning |
|---|---|
| edge_concrete | T is a concrete app class other than the owner |
| inherited | a call on this or super bound to an app supertype; a real edge, like Paper 1's L2 |
| self | T is the owner |
| external | T is a JDK or library type |
| J1_dispatch | T is an app interface or abstract class with at least one concrete app subtype |
| J4_no_impl | T is an app interface with no Java implementation |
| J3_reflective | a JNDI `lookup`, Spring `getBean`, or `Class.forName`, `newInstance` or `loadClass` on reflection types |
| J6_unresolved | neither the receiver type nor the method binding resolved |

J2 (injection), J5 (non-Java wiring) and J7 (type use) cut across these
categories and are counted separately.

### 1.4 How the classifier was checked

A seeded random sample of 40 call sites per app is stored in
`results/<app>/audit/sample.jsonl` (seed 42). I read 160 of them by hand:
all 40 for jpetstore-6 and daytrader7, and the first 20 for each of the other
four apps. The review, and the Phase 3 work that followed it, found seven
faults in my own tooling, and the Phase 3 fixtures an eighth. All eight were
fixed and every count was regenerated afterwards:

1. **Inherited calls counted as J1.** Implicit calls to an inherited method
   were counted as interface dispatch. Example: `setMessage(...)` in
   `CatalogActionBean` binding to its abstract superclass. They now have their
   own category, `inherited`.
2. **Unnormalized lambda parameter types.** Lambda parameter types came back as
   `? super T` and were not normalized, so 12 calls on app classes looked
   external. Fixed in the analyzer.
3. **Unbound implicit calls counted as self.** An implicit call that failed to
   bind was attributed to its owner. That hid failures inherited from
   unresolved supertypes, for example `getSqlMapClientTemplate()` in the iBatis
   DAOs. Such a call now counts as self only if the owner declares the method.
4. **J3 by method name only.** `newInstance` was counted as reflective
   regardless of receiver, for example `DocumentBuilderFactory.newInstance()`.
   J3 now also requires a reflective receiver type.
5. **Missed injection mechanisms.** Stripes `@SpringBean` fields and implicit
   single-constructor injection in `@Service` classes were not counted as
   injection points, and CDI `beans.xml` was mistaken for Spring XML.
6. **JDK types outside `java.*` and `javax.*`.** The analyzer's JDK solver
   admitted only those packages, which left 7 DayTrader calls on `org.w3c.dom`
   unresolved. It now uses the platform class loader, and DayTrader's J6 is 0.
7. **XML comments read as configuration.** lit-jpetstore's
   `dataAccessContext-local.xml` keeps an alternative `orderDao` bean
   (`MsSqlOrderDao`, line 69) inside an XML comment. All XML is now read with
   comments blanked out.
8. **Self-closing beans.** The Spring XML pattern for a bean with a body also
   matched a self-closing `<bean .../>`, so the properties of the next bean
   were credited to it. The resolver fixtures caught it
   (`tests/test_resolver.py`, `test_spring_xml_property_binds_the_wired_bean_only`).
   With faults 7 and 8 fixed, lit-jpetstore's Spring XML references between
   beans involving app classes are 25, not the 30 first reported.

## 2. The defect table

#### Table A. Call-site classification under the naive graph

| app | class nodes | call sites | edge_concrete | inherited | self | external | J1_dispatch | J4_no_impl | J3_reflective | J6_unresolved |
|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 24 | 250 | 106 (42.4%) | 10 (4.0%) | 22 (8.8%) | 85 (34.0%) | 0 (0.0%) | 27 (10.8%) | 0 (0.0%) | 0 (0.0%) |
| acmeair | 72 | 1142 | 141 (12.3%) | 0 (0.0%) | 50 (4.4%) | 687 (60.2%) | 115 (10.1%) | 0 (0.0%) | 17 (1.5%) | 132 (11.6%) |
| daytrader7 | 115 | 3691 | 1119 (30.3%) | 0 (0.0%) | 616 (16.7%) | 1895 (51.3%) | 40 (1.1%) | 0 (0.0%) | 21 (0.6%) | 0 (0.0%) |
| plantsbywebsphere | 37 | 1178 | 583 (49.5%) | 0 (0.0%) | 180 (15.3%) | 415 (35.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| lit-jpetstore | 73 | 913 | 266 (29.1%) | 50 (5.5%) | 18 (2.0%) | 514 (56.3%) | 63 (6.9%) | 0 (0.0%) | 2 (0.2%) | 0 (0.0%) |
| lit-pbw | 39 | 1264 | 584 (46.2%) | 3 (0.2%) | 197 (15.6%) | 479 (37.9%) | 0 (0.0%) | 0 (0.0%) | 1 (0.1%) | 0 (0.0%) |

#### Table B. Defect classes: affected sites and effect on the graph

| app | J1 interface dispatch | J2 injection | J3 lookups | J4 framework-generated | J5 non-Java wiring | J6 unresolved | J7 type-use only |
|---|---|---|---|---|---|---|---|
| jpetstore-6 | 0 sites; 0/1 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 13 annotated or constructor points, 0 Spring-XML refs; 46 sites through injected fields | 0 sites (-) | 27 sites on 7 impl-less interfaces; mapper→type 7/7 missing; class-literal 0 sites; JPA assoc 0/0 missing | 4 entry points, 2 without inbound edge | 0 (0.0%) | 16/42 type-use pairs without call edge |
| acmeair | 115 sites; 3/13 abstractions with 1/≥2 impls; 87 lost caller→impl pairs | 11 annotated or constructor points, 1 Spring-XML refs; 15 sites through injected fields | 17 sites (lookup/literal 8, lookup/non-literal 9) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 6 sites; JPA assoc 0/0 missing | 9 entry points, 9 without inbound edge | 132 (11.6%) | 32/88 type-use pairs without call edge |
| daytrader7 | 40 sites; 2/2 abstractions with 1/≥2 impls; 19 lost caller→impl pairs | 46 annotated or constructor points, 0 Spring-XML refs; 91 sites through injected fields | 21 sites (lookup/literal 19, lookup/non-literal 2) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 25 sites; JPA assoc 5/9 missing | 72 entry points, 61 without inbound edge | 0 (0.0%) | 27/80 type-use pairs without call edge |
| plantsbywebsphere | 0 sites; 0/0 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 30 annotated or constructor points, 0 Spring-XML refs; 93 sites through injected fields | 0 sites (-) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 20 sites; JPA assoc 2/4 missing | 10 entry points, 5 without inbound edge | 0 (0.0%) | 12/57 type-use pairs without call edge |
| lit-jpetstore | 63 sites; 5/4 abstractions with 1/≥2 impls; 34 lost caller→impl pairs | 0 annotated or constructor points, 25 Spring-XML refs; 0 sites through injected fields | 2 sites (getBean/literal 2) | 0 sites on 0 impl-less interfaces; mapper→type 2/10 missing; class-literal 1 sites; JPA assoc 0/0 missing | 37 entry points, 33 without inbound edge | 0 (0.0%) | 29/60 type-use pairs without call edge |
| lit-pbw | 0 sites; 1/0 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 28 annotated or constructor points, 0 Spring-XML refs; 92 sites through injected fields | 1 sites (lookup/literal 1) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 20 sites; JPA assoc 1/4 missing | 11 entry points, 6 without inbound edge | 0 (0.0%) | 10/56 type-use pairs without call edge |

#### Table C. Naive graph size and isolation

| app | class nodes | naive edges (owner≠target pairs) | isolated nodes |
|---|---|---|---|
| jpetstore-6 | 24 | 38 | 1 (4.2%) |
| acmeair | 72 | 86 | 23 (31.9%) |
| daytrader7 | 115 | 213 | 24 (20.9%) |
| plantsbywebsphere | 37 | 80 | 2 (5.4%) |
| lit-jpetstore | 73 | 128 | 9 (12.3%) |
| lit-pbw | 39 | 80 | 3 (7.7%) |

#### Table D. J6 by cause

| app | jars on classpath | unresolved call sites | unresolved supertypes | unresolved field types | top unsolved symbols |
|---|---|---|---|---|---|
| jpetstore-6 | 92 | 0 (0.0%) | 0 | 0 | - |
| acmeair | 12 | 132 (11.6%) | 3 | 5 | ObjectGrid 30, Session 29, ObjectMap 28, ObjectGridException 10, MapIndex 6 |
| daytrader7 | 6 | 0 (0.0%) | 0 | 0 | - |
| plantsbywebsphere | 7 | 0 (0.0%) | 0 | 0 | - |
| lit-jpetstore | 52 | 0 (0.0%) | 0 | 0 | - |
| lit-pbw | 1 | 0 (0.0%) | 0 | 0 | - |

## 3. Defect classes, confirmed or rejected

### J1. Interface dispatch: confirmed in AcmeAir, DayTrader and lit-jpetstore; absent in jpetstore-6 and Plants

When a call's receiver is typed by an interface or abstract class, the naive
edge lands on the abstraction. The implementation that actually runs gets no
edge from that caller.

**DayTrader.** `TradeAction.java:165`, `return trade.getMarketSummary();`.
Here `trade` is declared `TradeServices` (`TradeAction.java:64`), which has
three implementations in the app: `TradeAction`, `TradeDirect` and
`TradeSLSBBean`. 37 of its 40 J1 sites target an abstraction with two or more
implementations.

**AcmeAir.** `CustomerService.java:50`, `c.setPassword(null);`. The receiver is
the `Customer` entity interface from `acmeair-common`. It has one
implementation in the morphia back end and one in wxs. 114 of AcmeAir's 115 J1
sites are of this two-implementation kind, because the two data back ends
implement the same interfaces.

The count of abstractions with two or more implementations (13 in AcmeAir)
includes `AcmeAirConstants`, a constants-only interface. It is "implemented" by
four classes but is never a call receiver, so it adds no J1 sites.

**lit-jpetstore.** `PetStoreImpl.java:96`, `return this.accountDao.getAccount(username);`.
`AccountDao` has one implementation, `SqlMapAccountDao`. 58 of its 63 J1 sites
target an abstraction with exactly one implementation, which a hierarchy layer
can resolve at weight 1. `OrderDao` (`SqlMapOrderDao`, `MsSqlOrderDao`) and
`OrderService` (`PetStoreImpl`, `JaxRpcOrderService`) have two each.

**Effect.** Lost caller-to-implementation pairs: 87 in AcmeAir, 19 in
DayTrader, 34 in lit-jpetstore. The structural consequence is worse than the
pair count suggests. Implementations reached only through their interface
become isolated nodes: 8 of AcmeAir's 23 isolated classes (`AirportCodeMappingImpl`,
`CustomerAddressImpl`, `CustomerSessionImpl` and `FlightSegmentImpl`, once in each back end) and 2 of lit-jpetstore's 9
(`SqlMapCategoryDao` and `SqlMapProductDao`). The Rails
pipeline drops isolated classes before clustering (`experiment_v2.rb:55-91`),
so these classes would vanish from the decomposition.

jpetstore-6's only abstraction is `AbstractActionBean`, and every call to it is
an inherited self-call. Plants declares no interfaces at all.

### J2. Dependency injection: confirmed as a binding mechanism, but on its own it rarely loses edges here

The injection points per app:

| app | injection points | breakdown |
|---|---|---|
| jpetstore-6 | 13 | 5 Stripes `@SpringBean` fields (e.g. `CatalogActionBean.java:46`); 8 implicit constructor parameters in `@Service` classes (e.g. `AccountService.java:35`), wired by `<context:component-scan>` and `<mybatis:scan>` |
| daytrader7 | 46 | 11 `@EJB`, 15 `@Resource`, 17 `@Inject`, 3 `@PersistenceContext`; e.g. `DTBroker3MDB.java:50`, `@EJB TradeSLSBLocal tradeSLSB` |
| plantsbywebsphere | 30 | 21 `@Inject`, 7 `@PersistenceContext`, 2 `@Resource` |
| acmeair | 11 | 10 `@Inject`, 1 `@Resource` |
| lit-pbw | 28 | 18 `@EJB`, 7 `@PersistenceContext`, 1 `@Resource`, 2 `@Inject` |
| lit-jpetstore | 0 annotated | 25 Spring XML references between beans that involve app classes; e.g. `applicationContext.xml:54-55`, bean `petStore` = `PetStoreImpl` with `property accountDao ref="accountDao"` |

Whether injection loses edges depends on the declared type of the injection
point.

- **Concrete app classes.** These make up most of the declared types (16 of 46
  in DayTrader, 21 of 30 in Plants, 7 of 11 in AcmeAir). Calls through such
  fields already produce correct edges: 22 such sites in DayTrader, 41 in
  Plants, 7 in AcmeAir.
- **Abstractions.** Edges are lost only when the point is typed by an
  abstraction, and then the loss is counted under J1 or J4:
  - jpetstore-6's 8 constructor parameters are all mapper interfaces (J4,
    27 sites);
  - DayTrader has 5 abstraction-typed points (4 J1 sites through them);
  - lit-jpetstore's XML decides which implementation backs `PetStoreFacade`
    and each DAO interface (J1 above).
- **External container objects** (`EntityManager`, `SessionContext`, JMS):
  65 sites in DayTrader and 52 in Plants. These feed J4b.

J2 is therefore the information a resolver needs to fix J1 and J4 (which bean
is wired), rather than a separate source of lost edges in these subjects.

### J3. Reflection and lookups: confirmed for JNDI and Spring getBean; Class.forName rejected

- **DayTrader:** 21 JNDI lookups, 19 with literal names. Example:
  `TradeAction.java:115`,
  `tradeLocal = (TradeSLSBLocal) context.lookup("java:comp/env/ejb/TradeSLSBBean");`.
  The literal names include `java:comp/env/ejb/TradeSLSBBean`,
  `…/TradeSLSBBeanRemote` and the JMS queue and topic factories.
- **AcmeAir:** 17 lookups, 8 literal and 9 non-literal, concentrated in
  `ServiceLocator`, which picks the data back end at run time (e.g.
  `ServiceLocator.java:68`).
- **lit-jpetstore:** 2 `getBean("petStore")` calls (`BaseAction.java:38`,
  `JaxRpcOrderService.java:44`).
- **lit-pbw:** 1 lookup.

No application class calls `Class.forName`.

Effect: the lookup returns `Object`, and the cast types the variable as an
interface (`TradeSLSBLocal`). Later calls therefore become J1, and the bean
behind the name (`TradeSLSBBean`) receives no edge from the looking-up class.
The literal names are resolvable against `ejb-jar.xml`, `web.xml` and the bean
annotations. The non-literal ones (AcmeAir's 9) are not, and must be refused.

### J4. Framework-generated members: MyBatis, iBatis and JPA confirmed; Spring Data rejected

**MyBatis (jpetstore-6).** All 7 mapper interfaces (`AccountMapper`,
`CategoryMapper`, `ItemMapper`, `LineItemMapper`, `OrderMapper`,
`ProductMapper`, `SequenceMapper`) have no Java implementation. Their bodies
are mapper XML resolved through `typeAliasesPackage = org.mybatis.jpetstore.domain`.
Example: `AccountService.java:40`, `return accountMapper.getAccountByUsername(username);`.

This covers 27 call sites, 10.8% of the app. All 7 mapper-to-domain pairs
(`AccountMapper -> Account`, ...) are absent from the naive graph. jpetstore-6's
`Category` is isolated in the naive graph: Java code never calls a method on
it, its getters are reached only from `Category.jsp:26`
(`${actionBean.category.name}`), and its type appears only in signatures.

**iBatis 2 (lit-jpetstore).** The DAO reaches its SQL by a statement-id string
(`getSqlMapClientTemplate().insert("insertAccount", account)`), and the SqlMap
names domain classes in `<resultMap class="…">`. Linking the two through
statement ids gives 10 DAO-to-SqlMap links. Of the 10 DAO-to-domain pairs, 2
are absent from the naive graph (`SqlMapCategoryDao -> Category`,
`SqlMapProductDao -> Product`).

**JPA associations.** Absent from the naive graph in either direction:

| app | association pairs missing |
|---|---|
| daytrader7 | 5 of 9 (e.g. `AccountDataBean.java:80`, `@OneToMany orders -> OrderDataBean`) |
| plantsbywebsphere | 2 of 4 (e.g. `Order.java:75`, `@ManyToOne customer -> Customer`) |
| lit-pbw | 1 of 4 |

**J4b, entity access through class literals.** Calls on the external
`EntityManager` and Criteria API name the entity by a class literal, for
example `BackOrderMgr.java:74` (Plants), `em.find(Inventory.class, inventoryID)`:

| app | sites |
|---|---|
| daytrader7 | 25 |
| plantsbywebsphere | 20 |
| lit-pbw | 20 |
| acmeair | 6 (Morphia `Datastore`) |

In most of these cases the owner already has a call edge to the entity, so
few pairs are missing (1 in DayTrader, 1 in Plants, 1 in lit-pbw, 6 in AcmeAir). The
importance is for the data map D: these are the Java analogue of Rails'
`User.find`, the evidence that a class touches an entity.

**Rejected.** Spring Data derived queries: no subject uses Spring Data (0
files).

### J5. Non-Java wiring: confirmed in every subject

Entry points named from outside Java code (web.xml, faces-config,
struts-config, Spring dispatcher XML, JSP or JSF pages, entry annotations),
and how many of them have no inbound naive edge:

| app | entry points | without inbound edge | composition |
|---|---|---|---|
| daytrader7 | 72 | 61 | 54 classes with entry annotations (`@WebServlet` etc.), 44 of them the `web/prims` micro-benchmarks (e.g. `PingServlet.java:37`); 130 JSF EL references to 7 `@Named` beans |
| lit-jpetstore | 37 | 33 | Struts actions (`struts-config.xml:23`, `type="…AddItemToCartAction"`) and Spring MVC controllers |
| acmeair | 9 | 9 | JAX-RS resources |
| plantsbywebsphere | 10 | 5 | 128 EL references |
| jpetstore-6 | 4 | 2 | Stripes action beans named in JSPs (`catalog/Main.jsp:32`, `beanclass="…CatalogActionBean"`) |

An entry point with no inbound edge is not wrong in itself: a servlet is not
called by Java code. The problem is that page-to-bean and request-to-action
links are invisible, so the use cases that tie a page to its actions and
domain beans contribute nothing to the graph. JSP and JSF EL also navigate
domain getters, `${actionBean.category.name}`, which is how
`Category` ends up isolated (J4 above).

### J6. Unresolved types: zero wherever the libraries are available

Every call site resolved in jpetstore-6, daytrader7, plantsbywebsphere and both
literature variants (0 unresolved).

AcmeAir has 132 unresolved sites (11.6%), all in `acmeair-services-wxs`. They
fail on types from IBM's proprietary objectgrid jar (`ObjectGrid` 30,
`Session` 29, `ObjectMap` 28, ...), which no public repository provides.

An earlier run of the literature variants without any classpath left 463
(50.7%) and 276 (21.8%) sites unresolved, all on library types
(`HttpServletRequest`, `ActionForm`, `EntityManager`). With the classpath-only
poms both drop to 0, which confirms those failures measured the missing
libraries and not the code.

### J7. Type use without calls: found by this audit, confirmed in every subject

A method-call graph omits dependencies that exist only as declared types:
fields, parameters, return types and type arguments. Example: `CartItem.java:31`
declares a field of type `Item`, but no call connects the two classes.

Pairs with no call edge in either direction, against all type-use pairs:

| app | pairs without a call edge | all type-use pairs |
|---|---|---|
| jpetstore-6 | 16 | 42 |
| acmeair | 32 | 88 |
| daytrader7 | 27 | 80 |
| plantsbywebsphere | 12 | 57 |
| lit-jpetstore | 29 | 60 |
| lit-pbw | 10 | 56 |

For jpetstore-6, 16 such pairs sit beside a naive graph of only 38 edges.
Sellami's `class_interactions` matrix counts field, parameter and return
types (`structParser.py:130-181`). Whether our G should include them is a
design decision for Phase 3, not a defect to fix silently.

## 4. Comparison with the Rails findings

The Rails audit (Paper 1, C1 to C5) found that untyped receivers forced name
and arity guessing, so the dominant failure was false edges.

Java removes that problem. Every call site resolves to a declared type. The only
exception is AcmeAir's wxs module, whose proprietary jar is missing. The Java failures are of a different kind. They are lost and
misdirected edges caused by indirection:

- interfaces with several implementations (J1);
- container-generated implementations (J4);
- string-named collaborators (J3);
- wiring that lives in XML and pages (J5);
- dependencies that live only in declarations (J7).

Inflation is not the risk here. The naive Java graph is too sparse, not too
dense: 20.9% of DayTrader's classes and 31.9% of AcmeAir's are isolated (Table C).

## 5. What Phase 3 has to decide

Phase 3 is not designed here. The audit points to these candidate layers:

- class hierarchy analysis for J1, with weight 1 for one implementation and a
  stated policy for two or more;
- bean resolution from annotations, Spring XML and JNDI literal names, for J2
  and J3;
- a framework oracle for MyBatis and iBatis XML, JPA associations and
  EntityManager class literals (J4), which also feeds the data map D;
- page and descriptor wiring for J5;
- an explicit choice on type-use edges (J7).

The open policy question that changes results is how to treat AcmeAir's
morphia/wxs duplication and lit-jpetstore's Spring-MVC/Struts duplication. A
1/n split keeps both alternatives in one service. Refusing above a fan-out cap
leaves them unconnected. Excluding one alternative changes the class set.
