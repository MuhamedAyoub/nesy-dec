"""Regression tests for the Phase 2 call-site classifier (java_pipeline.audit).

Each test pins one fault found while reviewing the audit samples
(results/AUDIT.md, section 1.4), on synthetic records shaped like the
analyzer's callsites.jsonl.

Run: python3 -m pytest tests/test_audit_classify.py -q
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from java_pipeline.audit import Hierarchy, classify  # noqa: E402


def T(name, kind="class", abstract=False, extends=(), implements=(), methods=()):
    ref = lambda n: {"raw": n.split(".")[-1], "resolved": n}
    return {"name": name, "kind": kind, "abstract": abstract, "annotations": [],
            "extends": [ref(e) for e in extends], "implements": [ref(i) for i in implements],
            "fields": [], "constructors": [], "methods": [{"name": m} for m in methods]}


H = Hierarchy([
    T("a.Base", abstract=True, methods=["setMessage"]),
    T("a.Catalog", extends=["a.Base"], methods=["view"]),
    T("a.Repo", kind="interface"),
    T("a.RepoImpl", implements=["a.Repo"]),
    T("a.Mapper", kind="interface"),
    T("a.Item"),
])


def call(owner="a.Catalog", method="m", scope_kind="NameExpr", receiver=None, decl=None, static=False, arg0=None):
    return {"owner": owner, "method": method, "scope_kind": scope_kind, "receiver_type": receiver,
            "decl_type": decl, "decl_static": static, "arg0": arg0}


def test_inherited_call_is_not_interface_dispatch():
    # fault 1: setMessage() inside Catalog binds to abstract Base
    assert classify(call(method="setMessage", scope_kind="implicit", decl="a.Base"), H)[0] == "inherited"


def test_receiver_typed_by_interface_with_impl_is_J1():
    assert classify(call(receiver="a.Repo", decl="a.Repo"), H)[0] == "J1_dispatch"


def test_interface_without_java_impl_is_J4():
    assert classify(call(receiver="a.Mapper", decl="a.Mapper"), H)[0] == "J4_no_impl"


def test_unbound_implicit_call_not_declared_by_owner_is_unresolved():
    # fault 3: getSqlMapClientTemplate() inherited from an unresolved library class
    assert classify(call(method="getSqlMapClientTemplate", scope_kind="implicit"), H)[0] == "J6_unresolved"


def test_unbound_implicit_call_declared_by_owner_is_self():
    assert classify(call(method="view", scope_kind="implicit"), H)[0] == "self"


def test_newInstance_on_a_factory_is_not_reflective():
    # fault 4: DocumentBuilderFactory.newInstance()
    c = call(method="newInstance", scope_kind="NameExpr", decl="javax.xml.parsers.DocumentBuilderFactory", static=True)
    assert classify(c, H)[0] == "external"


def test_jndi_lookup_is_reflective():
    c = call(method="lookup", receiver="javax.naming.InitialContext", decl="javax.naming.InitialContext",
             arg0={"kind": "StringLiteralExpr", "value": "java:comp/env/ejb/X"})
    assert classify(c, H)[0] == "J3_reflective"


def test_concrete_app_receiver_is_an_edge():
    assert classify(call(receiver="a.Item", decl="a.Item"), H) == ("edge_concrete", "a.Item")
