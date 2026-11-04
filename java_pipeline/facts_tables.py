"""Render the Phase 4 fact tables from results/<app>/facts_report.json.

Usage: python3 -m java_pipeline.facts_tables > results/facts_tables.md
"""
from __future__ import annotations

import json

from java_pipeline.audit_tables import table
from java_pipeline.facts import ROLES
from java_pipeline.subjects import OUT, SUBJECTS

APPS = list(SUBJECTS)
ML_REASONS = ("jpa:assoc", "jpa:entity_lookup", "mybatis:mapper", "ibatis:sqlmap", "di:wired", "di:inject",
              "ejb:business_interface", "struts:form_bean")


def load(app: str) -> dict:
    return json.loads((OUT / app / "facts_report.json").read_text())


def main() -> None:
    R = {a: load(a) for a in APPS}

    print("### Table F1. Facts per relation: raw, matched to a node of G, dropped, both endpoints active\n")
    rows = []
    for a in APPS:
        r = R[a]
        for rel_name in ("must_link", "cannot_link", "soft_affinity", "inferred_coupling"):
            x = r[rel_name]
            dropped = ", ".join(f"{k} {v}" for k, v in x["dropped"].items()) or "0"
            uniq = x.get("unique_pairs", x["matched"])
            rows.append([a, rel_name, x["raw"], x["matched"], dropped, uniq, x["both_endpoints_active"]])
    print(table(["app", "relation", "raw", "matched", "dropped", "unique pairs", "both endpoints active"], rows))

    print("\n### Table F2. Must-link facts by reason (a pair may carry several reasons)\n")
    rows = []
    for a in APPS:
        by = R[a]["must_link"]["by_reason"]
        rows.append([a] + [sum(v for k, v in by.items() if k.startswith(m)) for m in ML_REASONS]
                    + [R[a]["must_link"]["unique_pairs"]])
    print(table(["app"] + list(ML_REASONS) + ["unique pairs"], rows))

    print("\n### Table F3. Soft-affinity pairs by source, framework noise, and conflicts\n")
    rows = []
    for a in APPS:
        r = R[a]
        src = r["soft_affinity"]["by_source"]
        rows.append([a, src.get("role", 0), src.get("package", 0), src.get("page", 0),
                     r["soft_affinity"]["unique_pairs"], r["pages_with_two_or_more_classes"],
                     r["framework_noise"]["count"], r["must_link_cannot_link_conflicts"],
                     r["must_link_pairs_on_framework_noise"]])
    print(table(["app", "role", "package", "page", "unique soft pairs", "pages naming ≥2 classes",
                 "framework noise", "must/cannot conflicts", "must-link pairs touching noise"], rows))

    print("\n### Table F4. Roles (Java stereotypes)\n")
    rows = [[a] + [R[a]["roles"].get(x, 0) for x in ROLES] for a in APPS]
    print(table(["app"] + list(ROLES), rows))

    print("\n### Table F5. Framework-noise classes and the rule that selected each\n")
    rows = [[a, "; ".join(f"{k.split('.')[-1]} ({v})" for k, v in R[a]["framework_noise"]["classes"].items()) or "-"]
            for a in APPS]
    print(table(["app", "classes"], rows))


if __name__ == "__main__":
    main()
