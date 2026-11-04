### Table F1. Facts per relation: raw, matched to a node of G, dropped, both endpoints active

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

### Table F2. Must-link facts by reason (a pair may carry several reasons)

| app | jpa:assoc | jpa:entity_lookup | mybatis:mapper | ibatis:sqlmap | di:wired | di:inject | ejb:business_interface | struts:form_bean | unique pairs |
|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 0 | 0 | 7 | 0 | 0 | 5 | 0 | 0 | 12 |
| acmeair | 0 | 6 | 0 | 0 | 0 | 7 | 0 | 0 | 13 |
| daytrader7 | 8 | 11 | 0 | 0 | 6 | 19 | 3 | 0 | 41 |
| plantsbywebsphere | 4 | 13 | 0 | 0 | 0 | 21 | 0 | 0 | 38 |
| lit-jpetstore | 0 | 0 | 0 | 10 | 17 | 0 | 0 | 17 | 44 |
| lit-pbw | 4 | 13 | 0 | 0 | 0 | 20 | 0 | 0 | 37 |

### Table F3. Soft-affinity pairs by source, framework noise, and conflicts

| app | role | package | page | unique soft pairs | pages naming ≥2 classes | framework noise | must/cannot conflicts | must-link pairs touching noise |
|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 55 | 70 | 11 | 70 | 7 | 1 | 0 | 0 |
| acmeair | 129 | 218 | 0 | 307 | 0 | 2 | 0 | 0 |
| daytrader7 | 1197 | 1393 | 80 | 2053 | 21 | 2 | 0 | 0 |
| plantsbywebsphere | 51 | 200 | 10 | 213 | 6 | 1 | 0 | 0 |
| lit-jpetstore | 681 | 527 | 0 | 864 | 0 | 2 | 0 | 1 |
| lit-pbw | 53 | 190 | 10 | 198 | 6 | 1 | 0 | 0 |

### Table F4. Roles (Java stereotypes)

| app | entity | repository | service | ejb_session | message_driven | servlet | web_controller | websocket | ui_bean | form | exception | config | util | interface | other | unknown |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| jpetstore-6 | 7 | 7 | 3 | 0 | 0 | 0 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | 0 |
| acmeair | 6 | 0 | 13 | 0 | 0 | 1 | 6 | 0 | 0 | 0 | 0 | 7 | 0 | 9 | 30 | 0 |
| daytrader7 | 5 | 0 | 1 | 3 | 2 | 48 | 0 | 5 | 9 | 0 | 0 | 3 | 4 | 4 | 31 | 0 |
| plantsbywebsphere | 7 | 0 | 5 | 1 | 0 | 3 | 0 | 0 | 6 | 0 | 2 | 0 | 2 | 0 | 11 | 0 |
| lit-jpetstore | 7 | 13 | 4 | 0 | 0 | 0 | 34 | 0 | 0 | 6 | 0 | 0 | 0 | 0 | 9 | 0 |
| lit-pbw | 7 | 0 | 0 | 7 | 0 | 4 | 0 | 0 | 3 | 0 | 2 | 0 | 2 | 0 | 14 | 0 |

### Table F5. Framework-noise classes and the rule that selected each

| app | classes |
|---|---|
| jpetstore-6 | AbstractActionBean (N1 generic base (4 concrete subclasses)) |
| acmeair | MorphiaConstants (N2 constants holder); WXSConstants (N2 constants holder) |
| daytrader7 | Log (N3 ubiquitous util (referenced by 60% of active classes)); TradeConfig (N3 ubiquitous config (referenced by 41% of active classes)) |
| plantsbywebsphere | Util (N3 ubiquitous util (referenced by 71% of active classes)) |
| lit-jpetstore | BaseAction (N1 generic base (18 concrete subclasses)); SecureBaseAction (N1 generic base (6 concrete subclasses)) |
| lit-pbw | Util (N3 ubiquitous util (referenced by 63% of active classes)) |
