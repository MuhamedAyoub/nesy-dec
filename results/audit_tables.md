### Table A. Call-site classification under the naive graph

| app | class nodes | call sites | edge_concrete | inherited | self | external | J1_dispatch | J4_no_impl | J3_reflective | J6_unresolved |
|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 24 | 250 | 106 (42.4%) | 10 (4.0%) | 22 (8.8%) | 85 (34.0%) | 0 (0.0%) | 27 (10.8%) | 0 (0.0%) | 0 (0.0%) |
| acmeair | 72 | 1142 | 141 (12.3%) | 0 (0.0%) | 50 (4.4%) | 687 (60.2%) | 115 (10.1%) | 0 (0.0%) | 17 (1.5%) | 132 (11.6%) |
| daytrader7 | 115 | 3691 | 1119 (30.3%) | 0 (0.0%) | 616 (16.7%) | 1895 (51.3%) | 40 (1.1%) | 0 (0.0%) | 21 (0.6%) | 0 (0.0%) |
| plantsbywebsphere | 37 | 1178 | 583 (49.5%) | 0 (0.0%) | 180 (15.3%) | 415 (35.2%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) | 0 (0.0%) |
| lit-jpetstore | 73 | 913 | 266 (29.1%) | 50 (5.5%) | 18 (2.0%) | 514 (56.3%) | 63 (6.9%) | 0 (0.0%) | 2 (0.2%) | 0 (0.0%) |
| lit-pbw | 39 | 1264 | 584 (46.2%) | 3 (0.2%) | 197 (15.6%) | 479 (37.9%) | 0 (0.0%) | 0 (0.0%) | 1 (0.1%) | 0 (0.0%) |

### Table B. Defect classes: affected sites and effect on the graph

| app | J1 interface dispatch | J2 injection | J3 lookups | J4 framework-generated | J5 non-Java wiring | J6 unresolved | J7 type-use only |
|---|---|---|---|---|---|---|---|
| jpetstore-6 | 0 sites; 0/1 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 13 annotated or constructor points, 0 Spring-XML refs; 46 sites through injected fields | 0 sites (-) | 27 sites on 7 impl-less interfaces; mapper→type 7/7 missing; class-literal 0 sites; JPA assoc 0/0 missing | 4 entry points, 2 without inbound edge | 0 (0.0%) | 16/42 type-use pairs without call edge |
| acmeair | 115 sites; 3/13 abstractions with 1/≥2 impls; 87 lost caller→impl pairs | 11 annotated or constructor points, 1 Spring-XML refs; 15 sites through injected fields | 17 sites (lookup/literal 8, lookup/non-literal 9) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 6 sites; JPA assoc 0/0 missing | 9 entry points, 9 without inbound edge | 132 (11.6%) | 32/88 type-use pairs without call edge |
| daytrader7 | 40 sites; 2/2 abstractions with 1/≥2 impls; 19 lost caller→impl pairs | 46 annotated or constructor points, 0 Spring-XML refs; 91 sites through injected fields | 21 sites (lookup/literal 19, lookup/non-literal 2) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 25 sites; JPA assoc 5/9 missing | 72 entry points, 61 without inbound edge | 0 (0.0%) | 27/80 type-use pairs without call edge |
| plantsbywebsphere | 0 sites; 0/0 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 30 annotated or constructor points, 0 Spring-XML refs; 93 sites through injected fields | 0 sites (-) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 20 sites; JPA assoc 2/4 missing | 10 entry points, 5 without inbound edge | 0 (0.0%) | 12/57 type-use pairs without call edge |
| lit-jpetstore | 63 sites; 5/4 abstractions with 1/≥2 impls; 34 lost caller→impl pairs | 0 annotated or constructor points, 25 Spring-XML refs; 0 sites through injected fields | 2 sites (getBean/literal 2) | 0 sites on 0 impl-less interfaces; mapper→type 2/10 missing; class-literal 1 sites; JPA assoc 0/0 missing | 37 entry points, 33 without inbound edge | 0 (0.0%) | 29/60 type-use pairs without call edge |
| lit-pbw | 0 sites; 1/0 abstractions with 1/≥2 impls; 0 lost caller→impl pairs | 28 annotated or constructor points, 0 Spring-XML refs; 92 sites through injected fields | 1 sites (lookup/literal 1) | 0 sites on 0 impl-less interfaces; mapper→type 0/0 missing; class-literal 20 sites; JPA assoc 1/4 missing | 11 entry points, 6 without inbound edge | 0 (0.0%) | 10/56 type-use pairs without call edge |

### Table C. Naive graph size and isolation

| app | class nodes | naive edges (owner≠target pairs) | isolated nodes |
|---|---|---|---|
| jpetstore-6 | 24 | 38 | 1 (4.2%) |
| acmeair | 72 | 86 | 23 (31.9%) |
| daytrader7 | 115 | 213 | 24 (20.9%) |
| plantsbywebsphere | 37 | 80 | 2 (5.4%) |
| lit-jpetstore | 73 | 128 | 9 (12.3%) |
| lit-pbw | 39 | 80 | 3 (7.7%) |

### Table D. J6 by cause

| app | jars on classpath | unresolved call sites | unresolved supertypes | unresolved field types | top unsolved symbols |
|---|---|---|---|---|---|
| jpetstore-6 | 92 | 0 (0.0%) | 0 | 0 | - |
| acmeair | 12 | 132 (11.6%) | 3 | 5 | ObjectGrid 30, Session 29, ObjectMap 28, ObjectGridException 10, MapIndex 6 |
| daytrader7 | 6 | 0 (0.0%) | 0 | 0 | - |
| plantsbywebsphere | 7 | 0 (0.0%) | 0 | 0 | - |
| lit-jpetstore | 52 | 0 (0.0%) | 0 | 0 | - |
| lit-pbw | 1 | 0 (0.0%) | 0 | 0 | - |
