"""Fixtures for the Phase 3 resolver (java_pipeline.resolver).

One synthetic project, tests/fixtures/resolver_app/, holds one minimal
instance of every resolver rule and every refusal reason. The analyzer runs on
it for real (compiled stubs for javax.persistence, javax.ejb and
Spring's ApplicationContext stand in for the libraries), then the resolver.
Each test below names the rule it covers; RESOLVER.md lists them.

Needs the analyzer jar (java_analyzer/target) and a JDK at JDK_HOME, default
~/.local/opt/jdk-21.0.13+9. Skipped when either is missing.

Run: python3 -m pytest tests/test_resolver.py -q
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from java_pipeline import audit, resolver, subjects  # noqa: E402

FIX = REPO / "tests" / "fixtures"
APP_SRC = FIX / "resolver_app" / "src" / "main" / "java"
JDK = Path(os.environ.get("JDK_HOME", Path.home() / ".local/opt/jdk-21.0.13+9"))
JAR = next(iter(sorted((REPO / "java_analyzer" / "target").glob("java-analyzer-*.jar"))), None) \
    if (REPO / "java_analyzer" / "target").is_dir() else None
APP = "fx-resolver"


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    if JAR is None or not (JDK / "bin" / "javac").is_file():
        pytest.skip("analyzer jar or JDK missing")
    tmp = tmp_path_factory.mktemp("resolver")
    classes = tmp / "stub-classes"
    srcs = [str(p) for p in (FIX / "stubs").rglob("*.java")]
    subprocess.run([str(JDK / "bin" / "javac"), "-d", str(classes)] + srcs, check=True)
    stub_jar = tmp / "stubs.jar"
    subprocess.run([str(JDK / "bin" / "jar"), "cf", str(stub_jar), "-C", str(classes), "."], check=True)

    out = tmp / "out"
    facts = out / APP / "facts"
    facts.mkdir(parents=True)
    cfg = {"app": APP, "sourceRoots": [str(APP_SRC)], "classpath": [str(stub_jar)], "languageLevel": "JAVA_17"}
    (facts / "config.json").write_text(json.dumps(cfg))
    subprocess.run([str(JDK / "bin" / "java"), "-Xss8m", "-jar", str(JAR), str(facts / "config.json"), str(facts)],
                   check=True, capture_output=True)

    saved = (subjects.OUT, audit.OUT, resolver.OUT, audit.facts_dir)
    subjects.SUBJECTS[APP] = {"roots": [str(APP_SRC)], "classpath_files": [], "set": "fixture"}
    subjects.OUT = audit.OUT = resolver.OUT = out
    audit.facts_dir = lambda app: out / app / "facts"
    try:
        report = resolver.resolve(APP)
    finally:
        subjects.OUT, audit.OUT, resolver.OUT, audit.facts_dir = saved
        del subjects.SUBJECTS[APP]
    edges = [json.loads(l) for l in (out / APP / "resolver" / "edges.jsonl").read_text().splitlines()]
    graph = json.loads((out / APP / "graph.json").read_text())
    calls = json.loads((out / APP / "calls_graph.json").read_text())
    return {"report": report, "edges": edges, "graph": graph, "calls": calls, "out": out}


def rules(run, src, dst):
    return sorted({(e["layer"], e["rule"], e["w"]) for e in run["edges"]
                   if e["src"] == "fx." + src and e["dst"] == "fx." + dst})


# --------------------------------------------------------------- J-L0

def test_call_declared(run):
    assert ("J-L0", "call_declared", 1.0) in rules(run, "service.Checkout", "domain.Item")


def test_call_abstraction_on_local(run):
    # n.send() in Drawer: a local typed by the interface
    assert ("J-L0", "call_abstraction", 1.0) in rules(run, "service.Drawer", "service.Notifier")


def test_call_inherited(run):
    assert ("J-L0", "call_inherited", 1.0) in rules(run, "service.LegacyOrderService", "service.BaseService")


def test_creation(run):
    assert ("J-L0", "creation", 1.0) in rules(run, "service.Checkout", "domain.Order")


def test_anon_impl(run):
    assert ("J-L0", "anon_impl", 1.0) in rules(run, "service.Drawer", "service.Notifier")


def test_method_ref(run):
    assert ("J-L0", "method_ref", 1.0) in rules(run, "service.Checkout", "domain.Item")


def test_field_ref(run):
    assert ("J-L0", "field_ref", 1.0) in rules(run, "service.Checkout", "Constants")


def test_class_literal(run):
    assert ("J-L0", "class_literal", 1.0) in rules(run, "repo.OrderRepo", "domain.Order")


def test_inheritance(run):
    assert ("J-L0", "inheritance", 1.0) in rules(run, "service.LegacyOrderService", "service.BaseService")
    assert ("J-L0", "inheritance", 1.0) in rules(run, "service.OrderServiceImpl", "service.OrderService")


def test_call_abstraction_without_java_impl(run):
    assert ("J-L0", "call_abstraction", 1.0) in rules(run, "service.CustomerService", "mapper.CustomerMapper")


# --------------------------------------------------------------- J-L1

def test_cha_one_implementation_weight_1(run):
    assert ("J-L1", "cha", 1.0) in rules(run, "service.OrderServiceImpl", "service.EmailNotifier")


def test_cha_two_implementations_split(run):
    assert ("J-L1", "cha", 0.5) in rules(run, "service.Checkout", "service.FlatPricing")
    assert ("J-L1", "cha", 0.5) in rules(run, "service.Checkout", "service.TieredPricing")


def test_fanout_above_cap_refused(run):
    for impl in ("Circle", "Square", "Triangle", "Hexagon", "Pentagon", "Star"):
        assert not [r for r in rules(run, "service.Drawer", "service." + impl) if r[0] == "J-L1"]
    assert run["report"]["refused_by_reason"].get("fanout") == 1


# --------------------------------------------------------------- J-L2

def test_spring_xml_property_binds_the_wired_bean_only(run):
    assert ("J-L2", "spring_xml_property", 1.0) in rules(run, "web.OrderAction", "service.OrderServiceImpl")
    assert rules(run, "web.OrderAction", "service.LegacyOrderService") == []


def test_spring_getbean_ignores_commented_out_bean(run):
    assert rules(run, "web.SpringClient", "service.OrderServiceImpl") == [("J-L2", "spring_getbean", 1.0)]
    assert rules(run, "web.SpringClient", "service.LegacyOrderService") == []


def test_jndi_ejb_literal(run):
    assert ("J-L2", "jndi_ejb", 1.0) in rules(run, "ejb.BillingClient", "ejb.BillingBean")


def test_lookup_nonliteral_refused_and_resource_external(run):
    assert run["report"]["refused_by_reason"].get("lookup_nonliteral") == 1
    assert run["report"]["sites_by_rule"].get("lookup_resource") == 1


# --------------------------------------------------------------- J-L3

def test_jpa_assoc_both_sides_weight_2(run):
    assert ("J-L3", "jpa_assoc", 2.0) in rules(run, "domain.Order", "domain.Item")
    assert ("J-L3", "jpa_assoc", 2.0) in rules(run, "domain.Item", "domain.Order")


def test_entity_class_literal(run):
    assert ("J-L3", "entity_class_literal", 1.0) in rules(run, "repo.OrderRepo", "domain.Order")


def test_jpa_named_query(run):
    assert ("J-L3", "jpa_named_query", 1.0) in rules(run, "repo.OrderRepo", "domain.Order")


def test_sql_table_joins_concatenation_and_skips_comments(run):
    assert rules(run, "repo.JdbcItemDao", "domain.Item") == [("J-L3", "sql_table", 1.0)]
    assert rules(run, "repo.JdbcItemDao", "domain.Order") == []


def test_mybatis_mapper_through_type_alias_package(run):
    assert ("J-L3", "mybatis_mapper", 1.0) in rules(run, "mapper.CustomerMapper", "domain.Customer")


def test_struts_form_bean(run):
    assert ("J-L3", "struts_form_bean", 1.0) in rules(run, "web.OrderAction", "web.OrderForm")


# ---------------------------------------------------------------- J-T

def test_type_use(run):
    assert rules(run, "service.Checkout", "domain.Customer") == [("J-T", "type_use", 1.0)]


def test_annotation_use(run):
    assert ("J-T", "annotation_use", 1.0) in rules(run, "service.OrderServiceImpl", "Audited")


# ------------------------------------------------------- refusals, D, schema

def test_unresolved_refused(run):
    assert run["report"]["refused_by_reason"].get("unresolved") == 1


def test_data_map(run):
    d = {k.removeprefix("fx."): sorted(x.removeprefix("fx.") for x in v)
         for k, v in run["graph"]["data_associations"].items() if v}
    assert d == {
        "domain.Item": ["domain.Order"],
        "domain.Order": ["domain.Item"],
        "mapper.CustomerMapper": ["domain.Customer"],
        "repo.JdbcItemDao": ["domain.Item"],
        "repo.OrderRepo": ["domain.Order"],
    }


def test_calls_graph_keeps_only_call_evidence(run):
    c = run["calls"]["dependency_graph"]
    assert "fx.domain.Customer" not in c["fx.service.Checkout"]        # type use only
    assert "fx.Constants" not in c["fx.service.Checkout"]              # field read, not a call
    assert c["fx.service.Checkout"]["fx.service.FlatPricing"] == 0.5
    assert "fx.domain.Item" not in c["fx.domain.Order"]                # association fact, not a call


def test_graph_schema_matches_rails_contract(run):
    g = run["graph"]
    assert {"parameters", "summary", "resolver_report", "dependency_graph", "data_associations",
            "clusters", "isolated_classes"} <= set(g)
    assert set(g["dependency_graph"]) == set(g["data_associations"])
    for es in g["dependency_graph"].values():
        assert all(dst in g["dependency_graph"] for dst in es)          # every endpoint is a node
