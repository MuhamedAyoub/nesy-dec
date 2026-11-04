"""Regression tests for rule CL-SIBLING (java_pipeline.facts.sibling_cannot_link).

Run: python3 -m pytest tests/test_cannot_link.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from java_pipeline.audit import Hierarchy  # noqa: E402
from java_pipeline.facts import sibling_cannot_link  # noqa: E402


def T(name, kind="class", implements=()):
    ref = lambda n: {"raw": n.split(".")[-1], "resolved": n}
    return {"name": name, "kind": kind, "abstract": False, "top_level": True, "enclosing": None, "annotations": [],
            "extends": [], "implements": [ref(i) for i in implements], "fields": [], "constructors": [], "methods": []}


TYPES = [T("app.web.spring.A1"), T("app.web.spring.A2"), T("app.web.struts.B1"), T("app.web.struts.B2"),
         T("app.web.solo.S1"), T("app.data.D1"), T("app.data.D2"),
         T("app.Port", kind="interface"),
         T("app.mongo.M1", implements=["app.Port"]), T("app.mongo.M2"),
         T("app.grid.G1", implements=["app.Port"]), T("app.grid.G2")]
H = Hierarchy(TYPES)
ROLES = {t["name"]: "web_controller" for t in TYPES if ".web." in t["name"]}
ROLES |= {"app.data.D1": "entity", "app.data.D2": "entity"}
ACTIVE = {t["name"] for t in TYPES}


def edge(a, b, layer="J-L0"):
    return {"src": a, "dst": b, "layer": layer, "rule": "x", "w": 1.0}


def package_pairs(edges, noise=()):
    _, accepted = sibling_cannot_link(H, ROLES, edges, ACTIVE, set(noise))
    return {(p["a"].split(".")[-1], p["b"].split(".")[-1]) for p in accepted}


def test_peer_packages_without_dependencies_are_disjoint():
    pairs, _ = sibling_cannot_link(H, ROLES, [], ACTIVE, set())
    tags = {t for *_, t in pairs}
    assert "cl_sibling:spring|struts" in tags
    assert sum(1 for *_, t in pairs if t == "cl_sibling:spring|struts") == 4      # 2 x 2 classes


def test_one_direct_edge_removes_the_boundary():
    assert ("spring", "struts") not in package_pairs([edge("app.web.spring.A1", "app.web.struts.B2")])


def test_type_use_edge_removes_the_boundary():
    assert ("spring", "struts") not in package_pairs([edge("app.web.struts.B1", "app.web.spring.A2", "J-T")])


def test_hierarchy_split_edges_do_not_count():
    assert ("spring", "struts") in package_pairs([edge("app.web.spring.A1", "app.web.struts.B2", "J-L1")])


def test_different_layers_are_not_disjoint():
    # web (presentation) and data (entity) share no dependency here, but a service needs both layers
    assert ("data", "web") not in package_pairs([])


def test_alternative_implementations_of_one_interface_are_disjoint():
    assert ("grid", "mongo") in package_pairs([])


def test_single_class_packages_and_noise_are_excluded():
    assert not any("solo" in p for pr in package_pairs([]) for p in pr)
    assert ("spring", "struts") not in package_pairs([], noise=["app.web.spring.A1"])   # leaves 1 class
