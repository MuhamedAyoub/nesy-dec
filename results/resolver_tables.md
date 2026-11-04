### Table R1. Call-site resolution (one resolution per site)

| app | call sites | J-L0 | J-L1 | J-L2 | external | self | refused | refused by reason |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 250 | 143 (57.2%) | 0 (0.0%) | 0 (0.0%) | 85 (34.0%) | 22 (8.8%) | 0 (0.0%) | - |
| acmeair | 1142 | 141 (12.3%) | 115 (10.1%) | 0 (0.0%) | 695 (60.9%) | 50 (4.4%) | 141 (12.3%) | lookup_nonliteral 9, unresolved 132 |
| daytrader7 | 3691 | 1119 (30.3%) | 40 (1.1%) | 7 (0.2%) | 1907 (51.7%) | 616 (16.7%) | 2 (0.1%) | lookup_nonliteral 2 |
| plantsbywebsphere | 1178 | 583 (49.5%) | 0 (0.0%) | 0 (0.0%) | 415 (35.2%) | 180 (15.3%) | 0 (0.0%) | - |
| lit-jpetstore | 913 | 316 (34.6%) | 26 (2.8%) | 39 (4.3%) | 514 (56.3%) | 18 (2.0%) | 0 (0.0%) | - |
| lit-pbw | 1264 | 587 (46.4%) | 0 (0.0%) | 0 (0.0%) | 480 (38.0%) | 197 (15.6%) | 0 (0.0%) | - |

### Table R2. Share of edge weight in G by layer

| app | total weight | J-L0 calls | J-L0 non-call refs | J-L1 | J-L2 | J-L3 | J-T |
|---|---|---|---|---|---|---|---|
| jpetstore-6 | 227.0 | 68.3% | 10.1% | 0.0% | 0.0% | 3.1% | 18.5% |
| acmeair | 629.0 | 47.5% | 18.1% | 18.3% | 0.0% | 1.0% | 15.1% |
| daytrader7 | 1535.2 | 80.8% | 9.3% | 2.1% | 0.5% | 2.0% | 5.4% |
| plantsbywebsphere | 805.0 | 75.8% | 14.2% | 0.0% | 0.0% | 3.0% | 7.1% |
| lit-jpetstore | 590.5 | 67.4% | 6.9% | 4.3% | 6.6% | 4.6% | 10.2% |
| lit-pbw | 811.0 | 75.7% | 14.4% | 0.0% | 0.0% | 3.0% | 6.9% |

### Table R3. Rule activity: call sites per site rule, class pairs per fact rule

| app | call_declared | call_inherited | call_abstraction | cha_n1 | cha_n2 | cha_n3+ | spring_xml_property | jndi_ejb | spring_getbean | lookup_resource | creation | method_ref | field_ref | class_literal | inheritance | jpa_assoc | mybatis_mapper | ibatis_sqlmap | entity_class_literal | jpa_named_query | sql_table | struts_form_bean | type_use | annotation_use |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 106 | 10 | 27 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 10 | 2 | 14 | 5 | 4 | 0 | 7 | 0 | 0 | 0 | 0 | 0 | 42 | 0 |
| acmeair | 141 | 0 | 0 | 1 | 114 | 0 | 0 | 0 | 0 | 8 | 43 | 0 | 35 | 47 | 32 | 0 | 0 | 0 | 6 | 0 | 0 | 0 | 88 | 7 |
| daytrader7 | 1119 | 0 | 0 | 3 | 2 | 35 | 0 | 7 | 0 | 12 | 81 | 0 | 105 | 30 | 8 | 9 | 0 | 0 | 6 | 1 | 5 | 0 | 80 | 3 |
| plantsbywebsphere | 583 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 27 | 0 | 94 | 20 | 0 | 4 | 0 | 0 | 9 | 7 | 0 | 0 | 57 | 0 |
| lit-jpetstore | 266 | 50 | 0 | 24 | 2 | 0 | 37 | 0 | 2 | 0 | 19 | 0 | 2 | 7 | 32 | 0 | 0 | 10 | 0 | 0 | 0 | 17 | 60 | 0 |
| lit-pbw | 584 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 27 | 0 | 96 | 20 | 1 | 4 | 0 | 0 | 9 | 7 | 0 | 0 | 56 | 0 |

### Table R4. Naive graph against the resolved graph

| app | class nodes | naive edges | call-graph edges | G edges | isolated (naive) | isolated (call graph) | isolated (G) | entities | classes with D entries |
|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 24 | 38 | 40 | 55 | 1 (4.2%) | 1 (4.2%) | 0 (0.0%) | 7 | 7 |
| acmeair | 72 | 86 | 185 | 264 | 23 (31.9%) | 10 (13.9%) | 2 (2.8%) | 6 | 3 |
| daytrader7 | 115 | 213 | 254 | 299 | 24 (20.9%) | 14 (12.2%) | 11 (9.6%) | 5 | 8 |
| plantsbywebsphere | 37 | 80 | 86 | 101 | 2 (5.4%) | 2 (5.4%) | 2 (5.4%) | 6 | 10 |
| lit-jpetstore | 73 | 128 | 168 | 219 | 9 (12.3%) | 6 (8.2%) | 2 (2.7%) | 7 | 8 |
| lit-pbw | 39 | 80 | 86 | 100 | 3 (7.7%) | 3 (7.7%) | 3 (7.7%) | 6 | 10 |

### Table R5. Classes isolated in G

| app | isolated classes |
|---|---|
| jpetstore-6 | - |
| acmeair | BigIntegerConverter, MapPutAllAgent |
| daytrader7 | ExternalContextProducer, JSFLoginFilter, PingCDIJSFBean, PingManagedExecutor, PingReentryServlet, PingServlet2IncludeRcv, PingServlet30Async, PingServletLargeContentLength, PingWebSocketBinary, PingWebSocketTextAsync, PingWebSocketTextSync |
| plantsbywebsphere | NoSupplierException, OrderKey |
| lit-jpetstore | SignoffController, SignonInterceptor |
| lit-pbw | NoSupplierException, OrderKey, RedirectionFilter |
