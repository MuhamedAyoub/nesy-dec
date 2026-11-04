# Phase 1: benchmark subjects

Date: 2026-10-24. Sources live in `datasets_java/`. Build logs are in
`results/build_logs/`. The survey behind every count below is
`results/subjects/survey.py`, and its output is `survey.json`. Copies of
the papers read for published counts are in `results/sources/`.

## 1. Main finding: Table 1 does not rest on one set of subject versions

Weerasinghe's footnotes link mybatis/jpetstore-6 and
WASdev/sample.plantsbywebsphere. The papers that supplied seven of the nine
rows of their Table 1 used other repositories for JPetStore and Plants:

| source | JPetStore | Plants | DayTrader | AcmeAir |
|---|---|---|---|---|
| Mono2Micro [10] (2107.09698, footnotes 2-5) | KimJongSung/jPetStore | WASdev/sample.mono-to-ms.pbw-monolith | WASdev/sample.daytrader7 | acmeair/acmeair |
| HierDec = "HDBScan" [21] (3530019.3530040, footnotes 4-7) | KimJongSung/jPetStore | WASdev/sample.mono-to-ms.pbw-monolith | WASdev/sample.daytrader7 | acmeair/acmeair |
| Saied 2024 [18] (2402.08481, Table I) | not stated | not stated | sample.daytrader7 (footnote 2) | not stated |
| MonoEmbed [20] (2502.04604, refs 5, 57, 81, 92) | mybatis/jpetstore-6 @4a07a02 | SteeleDesmond/sample.mono-to-ms.pbw-monolith @e6f2a6a | sample.daytrader7 @6df9bab | acmeair @f161227 |
| Weerasinghe footnotes 3-6 | mybatis/jpetstore-6 | WASdev/sample.plantsbywebsphere | sample.daytrader7 | acmeair/acmeair |

Saied 2024's Table I footnote markers point to footnotes that were never
printed, and the PDF has no link annotations. Its metadata row for each app
(version, SLOC and class count) is identical to HierDec's Table 2. That
suggests the same subjects, but it is an inference.

The rows Weerasinghe copied ([10], [18], [21]) were therefore most likely
measured on KimJongSung/jPetStore and the pbw-monolith. The two rows they ran
themselves (CHGNN, MonoEmbed) used MonoEmbed's pinned versions. Their
footnoted repositories match neither group for Plants.

`WASdev/sample.mono-to-ms.pbw-monolith` no longer exists: the GitHub API
returns 404. Its recorded parent, `CNXTEoEorg/sample.mono-to-ms.pbw-monolith`,
also returns 404. The only public copy is the SteeleDesmond fork, whose HEAD
is MonoEmbed's cited commit `e6f2a6a`.

## 2. Pinned commits and builds

| subject | repository | commit | branch or tag | JDK | build | result |
|---|---|---|---|---|---|---|
| jpetstore-6 | mybatis/jpetstore-6 | ce8015be2c2658d0b657be20328e53045f3a9641 | tag jpetstore-6.3.0 (provisional, see 4.1) | Temurin 21.0.13+9 | `./mvnw` (Maven 3.9.16) | success, 91 classpath jars |
| acmeair | acmeair/acmeair | f16122729873ef0449ea276dfb2d2a1d45bebb40 | master | Temurin 8u504-b01 | `./gradlew` (Gradle 2.6) `-Pservice=morphia` | success without wxs (see 3.2) |
| daytrader7 | WASdev/sample.daytrader7 | 643d04c100f75898003b5c98cde6b5f5015c613a | master | Temurin 8u504-b01 | Maven 3.9.9 | success, all 4 modules |
| plantsbywebsphere | WASdev/sample.plantsbywebsphere | bf5f18b0ba120dfe68a91d7e181c06e32ed6f3c4 | main | Temurin 8u504-b01 | Maven 3.9.9 | success |
| lit: jPetStore | KimJongSung/jPetStore | bc3fe898326e90658e95f27052ce3004b656d975 | master (2013-02-02) | Temurin 21.0.13+9 (Maven only) | classpath-only pom, not compiled | 52 classpath jars |
| lit: pbw-monolith | SteeleDesmond/sample.mono-to-ms.pbw-monolith | e6f2a6a437221c2652b907a709cf0343780013f2 | master (2016-01-06) | Temurin 21.0.13+9 (Maven only) | classpath-only pom, not compiled | 1 classpath jar |

The machine had only Java runtimes (OpenJDK 17 and 21 JREs, no `javac`). The
two Temurin JDKs and Maven 3.9.9 were installed under `~/.local/opt/`, each
checked against its published SHA-256 or SHA-512.

JPetStore's enforcer requires Maven 3.9.16 or newer, so it is built with its
own wrapper. The AcmeAir build uses a Gradle init script kept outside
the repository to export classpaths. No benchmark file was modified.

The two literature variants are not built: the tool sandbox refused to run
their build scripts. The symbol solver gets their libraries instead from a
classpath-only pom per variant, written by us
(`java_pipeline/classpath/<variant>/pom.xml`), resolved with
`mvn dependency:build-classpath`. No code from the variants is executed.

- lit-pbw declares only `javax:javaee-api:6.0`, which resolves from Maven
  Central unchanged.
- lit-jpetstore declares `spring.version` 3.1.1.BUILD-SNAPSHOT, never
  released, and several `com.springsource.*` bundles from the retired
  SpringSource EBR repository. The pom uses Spring 3.1.1.RELEASE and the
  Maven Central artifacts of the same libraries: `struts:struts:1.2.9`,
  `org.apache.ibatis:ibatis-sqlmap:2.3.4.726`, `commons-dbcp:1.2.2`,
  `javax.xml:jaxrpc-api:1.1`, `axis:axis:1.4`, `com.caucho:hessian:3.1.5`
  (3.2.1 is not on Central), plus `javax.mail:mail:1.4.7` for
  `org.springframework.mail`. The servlet, JSP and JSTL APIs, Tiles,
  urlrewrite, spring-js, aspectjweaver and slf4j keep their declared
  versions.

With these classpaths every call site in both variants resolves (Phase 2,
Table D).

## 3. Class counts and layout

### 3.1 Counts

"Sources" means `.java` files outside test directories. "Compiled" means
`.class` files from the build: top-level classes, plus named nested classes,
plus anonymous or local classes.

| subject | sources | compiled total | top-level | named nested | anonymous or local |
|---|---|---|---|---|---|
| jpetstore-6 @6.3.0 | 24 | 24 | 24 | 0 | 0 |
| acmeair, default app modules (common, services, services-morphia, loader, webapp) | 52 | 57 | 52 | 3 | 2 |
| acmeair, + services-wxs (source only) | 69 | n/a | | | |
| acmeair, + reporter (source only, not in `settings.gradle`) | 81 | n/a | | | |
| daytrader7 (ejb + web) | 108 | 121 | 108 | 7 | 6 |
| plantsbywebsphere | 36 | 37 | 36 | 1 | 0 |
| lit: KimJongSung/jPetStore | 72 | not built | | | |
| lit: pbw-monolith @e6f2a6a (PlantsByWebSphere + pbw-lib) | 38 | not built | | | |

There are no test sources in acmeair, daytrader7 or plantsbywebsphere.
jpetstore-6 has 18 test sources at 6.3.0. The pbw-monolith has one test
source, in `pbw-test`.

### 3.2 Per subject

**jpetstore-6 @6.3.0.** A single Maven module. There are four packages:
`domain` (9 classes), `mapper` (7 MyBatis mapper interfaces), `service` (3)
and `web/actions` (5 Stripes ActionBeans). Wiring:

- seven MyBatis mapper XML files bind the mapper interfaces to SQL and domain
  classes;
- Spring `applicationContext.xml` and three Spring stereotype annotations;
- Stripes ActionBeans bound by URL convention, plus `web.xml`.

There are no DI annotations in the regex inventory.

**acmeair @f161227.** A Gradle multi-module build:

- `acmeair-common` holds entity and service interfaces.
- `acmeair-services` holds service abstractions, with CDI and JNDI lookups.
- Two alternative data back ends: `acmeair-services-morphia` (MongoDB) and
  `acmeair-services-wxs` (WebSphere eXtreme Scale).
- `acmeair-loader` and `acmeair-webapp` (JAX-RS resources, 8 `@Path`
  classes).

`acmeair-reporter` is a separate load-test reporting tool and is not listed
in `settings.gradle`. `acmeair-mobile` contains no Java. The wxs back end
needs IBM's proprietary `objectgrid` 8.6.0.2 jar, which is not on Maven
Central. The build documentation says to obtain a trial copy of WebSphere
eXtreme Scale. The default build property `service=ALL` therefore fails, and
`-Pservice=morphia` succeeds.

Wiring: back ends are chosen at runtime through CDI (`@Inject`, 7 sites in
the app modules) and JNDI lookups (16 sites). Each data back end implements
the same `acmeair-common` interfaces, so an interface call has two candidate
implementations whenever wxs is included.

**daytrader7 @643d04c.** A Maven EAR with an EJB module and a web module.

- The EJB module (25 sources): JPA entities (5), session beans, two
  message-driven beans, and JMS.
- The web module (83 sources): servlets (47 classes with `@WebServlet`,
  `@WebFilter` or `@WebListener`), JSF managed beans (9 `@Named`), websocket
  endpoints (5).

`web/prims` holds 54 "primitive" micro-benchmark servlets and EJBs (43 in
`prims`, 11 in `prims/ejb3`). They test container features rather than
trading logic.

Wiring:

- injection: `@EJB` 11, `@Resource` 19, `@Inject` 17, `@PersistenceContext` 3;
- 21 JNDI `lookup(` call sites;
- config files: `ejb-jar.xml`, `web.xml`, `faces-config.xml`,
  3 × `persistence.xml`.

No Java file was added, deleted or renamed between 2020 and HEAD. The commit
MonoEmbed cites (6df9bab, 2022-04-04) has the same 108 sources.

**plantsbywebsphere @bf5f18b.** A single module with four packages: `bean`
(12), `jpa` (7: 6 entities plus one helper), `utils` (2) and `war` (15).

- JSF and CDI dominate: 21 `@Inject` sites and 9 `@Named` beans.
- There is one session bean and 7 `@PersistenceContext` sites.
- Config files: `persistence.xml`, `faces-config.xml`, `web.xml`.

No Java file was added, deleted or renamed between 2020 and HEAD.

**lit: KimJongSung/jPetStore @bc3fe89.** Spring's classic jpetstore sample:

- iBatis DAOs: 5 interfaces plus 9 `SqlMap*` implementations, with 8 SqlMap
  XML files;
- `domain` (8) and `domain/logic` (6, including `PetStoreImpl`);
- two alternative web layers: Spring MVC (18) and Struts (24, with
  `struts-config.xml`).

All DI is in Spring XML (`applicationContext.xml`, `petstore-servlet.xml`,
`remoting-servlet.xml`). The regex inventory finds no DI annotations. The
names `PetStoreImpl` and `SqlMapCategory…` in Mono2Micro's JPetStore example
(2107.09698, Fig. 1) match this code base.

**lit: pbw-monolith @e6f2a6a.** Maven modules `PlantsByWebSphere`, `pbw-lib`,
`pbw-test` and `pbw-ear`.

- 11 classes in an `ejb` package, 7 session beans, and 18 `@EJB` injection
  sites.
- JPA entities (6) and JSF.

It is EJB-centred, while the current WASdev Plants is CDI-centred (1 session
bean, no `@EJB`). The two are different architectures, not versions of one
code base.

## 4. Our counts against published counts

Published class counts, each with its source:

| app | HierDec [21] Table 2 | Saied [18] Table I | Sellami dissertation Table 2.1 | Mono2Micro [10] Table | MonoEmbed [20] Table | ours |
|---|---|---|---|---|---|---|
| JPetStore | 73 | 73 | 73 | 66 | 43 | 24 (jpetstore-6); 72 sources (KimJongSung) |
| Plants | 40 | 40 | 40 | 37 | 40 | 36 / 37 compiled (WASdev); 38 sources (pbw-monolith) |
| DayTrader | 118 | 118 | 118 | 109 | 118 | 108 sources / 121 compiled |
| AcmeAir | 86 | 86 | 86 | 33 | 86 | 52 sources / 57 compiled (default app); 69 with wxs; 81 with reporter |

The dissertation is `<parent>/prev/these_khaled_sellami.pdf`. MonoEmbed's
JPetStore figure (43) cannot be the 24 main classes at its pinned commit. The
whole tree at that commit has 42 Java files, so MonoEmbed most likely counted
test classes. How each paper counted nested classes is not stated anywhere.

### 4.1 Comparability threats

- **JPetStore.** mybatis/jpetstore-6 (24 classes) is a different application
  from the one behind the copied rows (KimJongSung, 72 sources, 73
  published). Comparing our JPetStore numbers with those rows compares two
  programs.

  The default branch of jpetstore-6 also moved from Stripes to Spring MVC on
  2026-08-10 (commit `53e4499d`, released as 6.4.0). Every published result
  predates that, so I pinned 6.3.0, the last Stripes release. Its 24-file set
  is identical to 6.0.2 (2016); only the build moved to Java 17.
- **Plants.** The copied rows used the pbw-monolith (EJB-centred, 38 sources,
  40 published). The current WASdev Plants is CDI-centred (36 sources).
- **DayTrader.** Same repository, and the source set has not changed since
  2020. 108 sources and 121 compiled classes bracket the published 118. The
  difference is about how nested and anonymous classes are counted. Phase 2
  will fix the rule and report it.
- **AcmeAir.** Same repository and commit as MonoEmbed. None of our natural
  scopes gives 86. Mono2Micro's 33 is much smaller and was probably limited to
  one deployment configuration. Which modules the other papers included is
  not stated.
- **Alternative implementations.** AcmeAir (morphia vs wxs) and KimJongSung
  jPetStore (Spring MVC vs Struts) each contain two interchangeable
  implementations of one layer. Including both creates interfaces with two
  implementations and structurally duplicate clusters. Excluding one changes
  the class set relative to the papers. That matters for J1 in the Phase 2
  audit.

## 5. Decisions needed

1. **Which versions are primary?** I recommend running both sets and
   labelling them:
   - (a) the literature versions as primary for JPetStore and Plants
     (KimJongSung/jPetStore @bc3fe89, pbw-monolith @e6f2a6a), because they
     match the rows we will be compared against;
   - (b) mybatis/jpetstore-6 @6.3.0 and WASdev/sample.plantsbywebsphere
     @bf5f18b as a secondary set, matching Weerasinghe's footnotes and
     MonoEmbed's JPetStore.

   DayTrader and AcmeAir are the same in both sets.
2. **Permission to build the two literature variants.** The tool sandbox
   blocked running their Maven builds. A classpath is needed for the symbol
   solver; without one, J6 failures are inflated. If you agree, you can allow
   it, or run it yourself:
   `! cd <repo>/datasets_java/KimJongSung__jPetStore && JAVA_HOME=~/.local/opt/jdk8u504-b01 ~/.local/opt/apache-maven-3.9.9/bin/mvn -B -DskipTests package`
   and the same in `SteeleDesmond__sample.mono-to-ms.pbw-monolith`.
3. **AcmeAir scope.** I propose the six `settings.gradle` modules: the
   default app plus wxs, 69 sources. wxs is parsed from source, and its
   objectgrid types count as unresolved under J6. The reporter is excluded as
   a separate tool.
4. **Class-counting rule.** I propose top-level plus named nested types as
   nodes, with anonymous and local classes folded into their enclosing class.
   An anonymous class is not a deployable unit, and Spoon-based tools list
   them with `$1` names. The rule will be reported next to the counts above.
