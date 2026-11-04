"""Render the Phase 3 provenance tables from results/<app>/resolver/provenance.json.

Every number in the tables of results/RESOLVER.md is produced here.

Usage: python3 -m java_pipeline.resolver_tables > results/resolver_tables.md
"""
from __future__ import annotations

import json

from java_pipeline.audit_tables import pct, table
from java_pipeline.subjects import OUT, SUBJECTS

APPS = list(SUBJECTS)
CALL_RULES = ("call_declared", "call_inherited", "call_abstraction", "creation", "anon_impl", "method_ref")
NONCALL_RULES = ("field_ref", "class_literal", "inheritance")
L3_RULES = ("jpa_assoc", "mybatis_mapper", "ibatis_sqlmap", "entity_class_literal", "jpa_named_query",
            "sql_table", "struts_form_bean")


def load(app: str) -> dict:
    return json.loads((OUT / app / "resolver" / "provenance.json").read_text())


def main() -> None:
    R = {a: load(a) for a in APPS}
    A = {a: json.loads((OUT / a / "audit" / "audit.json").read_text()) for a in APPS}

    print("### Table R1. Call-site resolution (one resolution per site)\n")
    rows = []
    for a in APPS:
        r, n = R[a], R[a]["call_sites"]
        s = r["site_resolution"]
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(r["refused_by_reason"].items())) or "-"
        rows.append([a, n] + [pct(s.get(k, 0), n) for k in ("J-L0", "J-L1", "J-L2", "external", "self", "refused")]
                    + [reasons])
    print(table(["app", "call sites", "J-L0", "J-L1", "J-L2", "external", "self", "refused", "refused by reason"], rows))

    print("\n### Table R2. Share of edge weight in G by layer\n")
    rows = []
    for a in APPS:
        r = R[a]
        wr, tot = r["weight_by_rule"], sum(r["weight_by_rule"].values())
        share = lambda rules: f"{100 * sum(wr.get(x, 0) for x in rules) / tot:.1f}%"
        rows.append([a, f"{tot:.1f}", share(CALL_RULES), share(NONCALL_RULES), share(("cha",)),
                     share(("spring_xml_property", "jndi_ejb", "spring_getbean")), share(L3_RULES),
                     share(("type_use", "annotation_use"))])
    print(table(["app", "total weight", "J-L0 calls", "J-L0 non-call refs", "J-L1", "J-L2", "J-L3", "J-T"], rows))

    print("\n### Table R3. Rule activity: call sites per site rule, class pairs per fact rule\n")
    site_rules = ["call_declared", "call_inherited", "call_abstraction", "cha_n1", "cha_n2", "cha_n3+",
                  "spring_xml_property", "jndi_ejb", "spring_getbean", "lookup_resource"]
    rows = []
    for a in APPS:
        r = R[a]
        sr, cr, nr, fr = r["sites_by_rule"], r["creation_and_ref_sites"], r["non_call_reference_sites"], r["fact_pairs_by_rule"]
        rows.append([a] + [sr.get(k, 0) for k in site_rules]
                    + [cr.get("creation", 0) + cr.get("anon_impl", 0), cr.get("method_ref", 0),
                       nr.get("field_ref", 0), nr.get("class_literal", 0), nr.get("inheritance", 0)]
                    + [fr.get(k, 0) for k in L3_RULES] + [fr.get("type_use", 0), fr.get("annotation_use", 0)])
    print(table(["app"] + site_rules + ["creation", "method_ref", "field_ref", "class_literal", "inheritance"]
                + list(L3_RULES) + ["type_use", "annotation_use"], rows))

    print("\n### Table R4. Naive graph against the resolved graph\n")
    rows = []
    for a in APPS:
        r, au = R[a], A[a]
        rows.append([a, r["class_nodes"], au["naive_edges"], r["call_edges"], r["edges"],
                     pct(au["isolated_nodes"], r["class_nodes"]),
                     pct(len(r["isolated_calls_graph"]), r["class_nodes"]),
                     pct(len(r["isolated"]), r["class_nodes"]),
                     len(r["entities"]), r["data_map_classes"]])
    print(table(["app", "class nodes", "naive edges", "call-graph edges", "G edges", "isolated (naive)",
                 "isolated (call graph)", "isolated (G)", "entities", "classes with D entries"], rows))

    print("\n### Table R5. Classes isolated in G\n")
    rows = [[a, ", ".join(x.split(".")[-1] for x in R[a]["isolated"]) or "-"] for a in APPS]
    print(table(["app", "isolated classes"], rows))


if __name__ == "__main__":
    main()
