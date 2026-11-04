"""Render the Phase 2 audit tables from results/<app>/audit/audit.json.

Every number in the tables of results/AUDIT.md is produced here, so the
document never transcribes a count by hand.

Usage: python3 -m java_pipeline.audit_tables > results/audit_tables.md
"""
from __future__ import annotations

import json

from java_pipeline.subjects import OUT, SUBJECTS

APPS = list(SUBJECTS)


def load(app: str) -> dict:
    return json.loads((OUT / app / "audit" / "audit.json").read_text())


def pct(a: int, b: int) -> str:
    return f"{a} ({100 * a / b:.1f}%)" if b else str(a)


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def main() -> None:
    R = {a: load(a) for a in APPS}

    print("### Table A. Call-site classification under the naive graph\n")
    cats = ["edge_concrete", "inherited", "self", "external", "J1_dispatch", "J4_no_impl", "J3_reflective", "J6_unresolved"]
    rows = []
    for a in APPS:
        r = R[a]
        n = r["call_sites"]
        rows.append([a, r["class_nodes"], n] + [pct(r["categories"].get(c, 0), n) for c in cats])
    print(table(["app", "class nodes", "call sites"] + cats, rows))

    print("\n### Table B. Defect classes: affected sites and effect on the graph\n")
    rows = []
    for a in APPS:
        r = R[a]
        rows.append([
            a,
            f"{r['J1']['call_sites']} sites; {r['J1']['with_1_impl']}/{r['J1']['with_2plus_impl']} abstractions with 1/≥2 impls; {r['J1']['lost_owner_impl_pairs']} lost caller→impl pairs",
            f"{r['J2']['annotated_injection_points']} annotated or constructor points, {r['J2']['spring_xml_injections_involving_app_classes']} Spring-XML refs; {r['J2']['call_sites_through_injected_fields']} sites through injected fields",
            f"{r['J3']['call_sites']} sites ({', '.join(f'{k} {v}' for k, v in r['J3']['by_method_and_argument'].items()) or '-'})",
            f"{r['J4']['call_sites_on_interfaces_without_impl']} sites on {len(r['J4']['interfaces_without_java_impl'])} impl-less interfaces; mapper→type {r['J4']['binder_to_mapped_type_pairs_missing_in_naive_graph']}/{r['J4']['binder_to_mapped_type_pairs']} missing; class-literal {r['J4']['class_literal_sites_on_external_receivers']} sites; JPA assoc {r['J4']['jpa_association_pairs_missing_in_naive_graph']}/{r['J4']['jpa_associations']} missing",
            f"{r['J5']['entry_point_classes']} entry points, {r['J5']['entry_points_without_inbound_naive_edge']} without inbound edge",
            f"{pct(r['J6']['call_sites'], r['call_sites'])}",
            f"{r['J7']['type_use_pairs_without_call_edge']}/{r['J7']['type_use_pairs']} type-use pairs without call edge",
        ])
    print(table(["app", "J1 interface dispatch", "J2 injection", "J3 lookups", "J4 framework-generated", "J5 non-Java wiring",
                 "J6 unresolved", "J7 type-use only"], rows))

    print("\n### Table C. Naive graph size and isolation\n")
    rows = [[a, R[a]["class_nodes"], R[a]["naive_edges"], pct(R[a]["isolated_nodes"], R[a]["class_nodes"])] for a in APPS]
    print(table(["app", "class nodes", "naive edges (owner≠target pairs)", "isolated nodes"], rows))

    print("\n### Table D. J6 by cause\n")
    rows = []
    for a in APPS:
        j = R[a]["J6"]
        top = ", ".join(f"{k} {v}" for k, v in list(j["top_unsolved_symbols"].items())[:5]) or "-"
        rows.append([a, j["jars_loaded"], pct(j["call_sites"], R[a]["call_sites"]), j["unresolved_supertype_refs"],
                     j["unresolved_field_types"], top])
    print(table(["app", "jars on classpath", "unresolved call sites", "unresolved supertypes", "unresolved field types", "top unsolved symbols"], rows))


if __name__ == "__main__":
    main()
