"""Phase 3: the layered Java resolver, J-L0 to J-L3, with provenance.

Designed from the Phase 2 audit (results/AUDIT.md) on Paper 1's
principles: strongest evidence first, every edge tagged with the layer and
rule that produced it, refusal instead of guessing, bounded ambiguity
(weight 1/n, fan-out cap K).

Per call site, exactly one resolution:

  J-L0 declared    the receiver's declared type is a concrete application
                   class (call_declared), or a this/super call binds to an
                   application supertype (call_inherited). Object creations
                   (creation, anon_impl) and method references (method_ref)
                   on application classes also land here.
  J-L2 injection   the collaborator is fixed by configuration: a call through
                   a field whose bean is wired in Spring XML
                   (spring_xml_property), a JNDI lookup whose literal name
                   binds to an EJB (jndi_ejb), a Spring getBean whose literal
                   id binds to a bean class (spring_getbean).
  J-L1 hierarchy   the receiver is an application interface or abstract class
                   and no injection binding applies: class hierarchy analysis
                   links the caller to each of its n concrete application
                   subtypes with weight 1/n; n > K is refused (fanout).
  refused          unresolved (J6), lookup_nonliteral, lookup_unbound, fanout.
  no edge          external (JDK or library receiver), self.

A call through an abstraction also keeps its declared edge to the
abstraction (rule call_abstraction, J-L0): the contract type is a real
dependency, and for container-implemented interfaces (MyBatis mappers) it is
the only Java-side endpoint.

Non-call references, also J-L0 but not counted as calls:
  field_ref        a read or write of a field declared by another application
                   class (constants, public fields), one per site
  class_literal    X.class naming another application class, one per site
  inheritance      a direct extends/implements between application classes,
                   once per pair

J-L3 is the framework conventions oracle. Its rules add fact edges once per
class pair, as Paper 1's ConventionOracleV2 does, and feed the data map D:

  jpa_assoc            @OneToMany/@ManyToOne/@OneToOne/@ManyToMany field in E
                       typed by entity T                     E -> T, weight 2
  mybatis_mapper       <mapper namespace="M"> names domain type T  M -> T, 1
  ibatis_sqlmap        DAO names a statement id of a sqlMap that maps T
                                                             DAO -> T, 1
  entity_class_literal a call passes T.class for entity T (em.find,
                       createQuery, Morphia createQuery)     owner -> T, 1
  jpa_named_query      createNamedQuery("q") where entity T declares
                       @NamedQuery(name = "q")               owner -> T, 1
  sql_table            a string literal in the owner's file is SQL or JPQL
                       naming T's table or entity name       owner -> T, 1
  struts_form_bean     <action type="A" name="f"> with <form-bean name="f"
                       type="F">                             A -> F, 1

J-T is the type-use layer found by the audit (J7): one edge of weight 1 per
distinct (owner, type) pair over field, constructor and method parameter,
return and type-argument types (type_use), and over application annotation
types used on a class or its members (annotation_use). It is kept as its own
layer so that results can be reported with and without it.

Outputs, per app, under results/<app>/:
  graph.json             G and D in the Rails pipeline's schema
                         (dependency_graph, data_associations, resolver_report,
                         isolated_classes), all classes as nodes
  calls_graph.json       the call graph: call, creation and method-reference
                         evidence of J-L0/J-L1/J-L2 only (CALL_RULES), for
                         the Weerasinghe-style metrics, which are defined on
                         calls
  resolver/edges.jsonl   one line per edge contribution with layer, rule,
                         weight and source position
  resolver/provenance.json  the per-layer counts behind RESOLVER.md
  resolver/lookups.json  every literal lookup name and what it bound to

Usage: python3 -m java_pipeline.resolver [app ...]
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from java_pipeline.audit import (IBATIS_CALLS, JPA_ASSOC, Hierarchy, classify, load, mapper_xml,
                                 rel, xml_files, xml_text)
from java_pipeline.subjects import OUT, SUBJECTS

K = 5                 # fan-out cap, as Paper 1 (ResolverV2.rb FANOUT_CAP)
W_ASSOC = 2.0         # association facts, as Paper 1 (ConventionOracleV2.rb)
W_FACT = 1.0          # lookup-style facts, as Paper 1
W_TYPE = 1.0          # one per distinct type-use pair

EJB_ANNOTATIONS = ("Stateless", "Stateful", "Singleton", "MessageDriven")
ENTITY_ANNOTATIONS = ("Entity",)
CALL_RULES = ("call_declared", "call_inherited", "call_abstraction", "creation", "anon_impl", "method_ref",
              "cha", "spring_xml_property", "jndi_ejb", "spring_getbean")


def ann(a: str) -> str:
    """Simple name of an annotation as the analyzer prints it, ignoring any
    comment the source placed before it."""
    m = re.search(r"@([\w.]+)", a)
    return m.group(1).split(".")[-1] if m else ""


def ann_value(a: str, key: str) -> str | None:
    m = re.search(rf'\b{key}\s*=\s*"([^"]*)"', a)
    return m.group(1) if m else None


def ann_single(a: str) -> str | None:
    """@Named("x"), @Named(value = "x"), @Entity(name = "x")."""
    m = re.search(r'\(\s*(?:\w+\s*=\s*)?"([^"]*)"', a)
    return m.group(1) if m else None


class Edges:
    """G as weighted contributions with provenance."""

    def __init__(self) -> None:
        self.g: dict[str, Counter] = defaultdict(Counter)
        self.contrib: list[dict] = []
        self.pairs: set[tuple[str, str, str]] = set()      # (rule, src, dst) for once-per-pair rules

    def add(self, src: str, dst: str, w: float, layer: str, rule: str, where: str) -> None:
        if src == dst or w <= 0:
            return
        self.g[src][dst] += w
        self.contrib.append({"src": src, "dst": dst, "w": round(w, 6), "layer": layer, "rule": rule, "where": where})

    def add_once(self, src: str, dst: str, w: float, layer: str, rule: str, where: str) -> bool:
        if src == dst or (rule, src, dst) in self.pairs:
            return False
        self.pairs.add((rule, src, dst))
        self.add(src, dst, w, layer, rule, where)
        return True


# ------------------------------------------------------------ configuration

def spring_beans(app: str) -> tuple[dict[str, set[str]], dict[tuple[str, str], set[str]]]:
    """Bean id -> classes (over every Spring XML file, so alternative
    configurations both count), and (bean class, property) -> classes of the
    referenced beans."""
    files = []
    for p in xml_files(app):
        t = xml_text(p)
        if re.search(r"<bean\b", t):
            files.append((p, t))
    ids: dict[str, set[str]] = defaultdict(set)
    for _, t in files:
        for b in re.finditer(r"<bean\b([^>]*?)/?>", t):
            i = re.search(r'\b(?:id|name)="([^"]+)"', b.group(1))
            c = re.search(r'\bclass="([^"]+)"', b.group(1))
            if i and c:
                for name in re.split(r"[,; ]+", i.group(1)):
                    ids[name].add(c.group(1))
    props: dict[tuple[str, str], set[str]] = defaultdict(set)
    for _, t in files:
        for b in re.finditer(r"<bean\b([^>]*?)(?<!/)>(.*?)</bean>", t, re.S):
            cls = re.search(r'\bclass="([^"]+)"', b.group(1))
            if not cls:
                continue
            for tag in re.finditer(r"<property\b([^>]*?)(/>|>(.*?)</property>)", b.group(2), re.S):
                name = re.search(r'\bname="([^"]+)"', tag.group(1))
                ref = re.search(r'\bref="([^"]+)"', tag.group(1)) or re.search(
                    r'<ref\s+(?:bean|local)="([^"]+)"', tag.group(3) or "")
                if name and ref:
                    props[(cls.group(1), name.group(1))] |= ids.get(ref.group(1), set())
    return ids, props


def ejb_names(app: str, h: Hierarchy) -> tuple[dict[str, str], dict[str, str]]:
    """EJB name -> bean class (annotations and ejb-jar.xml), and ejb-ref name ->
    linked EJB name (web.xml / ejb-jar.xml <ejb-ref>/<ejb-local-ref>)."""
    beans: dict[str, str] = {}
    for t, x in h.types.items():
        for a in x["annotations"]:
            if ann(a) in EJB_ANNOTATIONS:
                beans[ann_value(a, "name") or ann_value(a, "mappedName") or t.split(".")[-1]] = t
    refs: dict[str, str] = {}
    for p in xml_files(app):
        t = xml_text(p)
        for m in re.finditer(r"<ejb-name>\s*([^<\s]+)\s*</ejb-name>\s*(?:<[^>]+>[^<]*</[^>]+>\s*)*?<ejb-class>\s*([^<\s]+)\s*</ejb-class>", t):
            if m.group(2) in h.types:
                beans[m.group(1)] = m.group(2)
        for m in re.finditer(r"<ejb-(?:local-)?ref>(.*?)</ejb-(?:local-)?ref>", t, re.S):
            n = re.search(r"<ejb-ref-name>\s*([^<\s]+)", m.group(1))
            link = re.search(r"<ejb-link>\s*([^<\s]+)", m.group(1))
            if n and link:
                refs[n.group(1)] = link.group(1).split("#")[-1]
    return beans, refs


def bind_jndi(name: str, beans: dict[str, str], refs: dict[str, str]) -> str | None:
    n = re.sub(r"^java:(comp/env/|comp/|module/|app/[^/]+/|global/[^/]+/[^/]+/|global/[^/]+/)", "", name)
    n = n.split("!")[0]
    if n in refs:
        return beans.get(refs[n])
    last = n.split("/")[-1]
    return beans.get(last)


def struts_form_beans(app: str, h: Hierarchy) -> list[tuple[str, str, str]]:
    out = []
    for p in xml_files(app):
        if p.name != "struts-config.xml":
            continue
        t = xml_text(p)
        forms = {m.group(1): m.group(2) for m in re.finditer(r'<form-bean\s+[^>]*?name="([^"]+)"[^>]*?type="([^"]+)"', t)}
        for m in re.finditer(r"<action\b([^>]*)>", t):
            ty = re.search(r'\btype="([^"]+)"', m.group(1))
            nm = re.search(r'\bname="([^"]+)"', m.group(1))
            if ty and nm and ty.group(1) in h.types and forms.get(nm.group(1)) in h.types:
                out.append((ty.group(1), forms[nm.group(1)], f"{rel(str(p))}:{t[:m.start()].count(chr(10)) + 1}"))
    return out


# --------------------------------------------------------------- entities

def entities(h: Hierarchy, mx: dict) -> tuple[set[str], dict[str, str]]:
    """Entity classes and, for each, the lower-cased names SQL or JPQL may use
    for it (table name, entity name, simple class name)."""
    ents = {t for t, x in h.types.items() if any(ann(a) in ENTITY_ANNOTATIONS for a in x["annotations"])}
    ents |= {ty for tys in mx["binders"].values() for ty in tys}
    names: dict[str, str] = {}
    clash: set[str] = set()
    for t in sorted(ents):
        cand = {t.split(".")[-1].lower()}
        for a in h.types[t]["annotations"]:
            if ann(a) in ("Table", "Entity") and (v := ann_value(a, "name") or ann_value(a, "value") or ann_single(a)):
                cand.add(v.lower())
        for c in cand:
            if c in names and names[c] != t:
                clash.add(c)
            names[c] = t
    for c in clash:
        names.pop(c, None)          # a name two entities share binds neither
    return ents, names


STRING_LIT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
SQL_NAME = re.compile(r"\b(?:from|into|update|join)\s+(?:[A-Za-z_]\w*\.)?([A-Za-z_]\w*)", re.I)
SQL_SHAPE = re.compile(r"^\s*(?:select|insert|update|delete)\b|\bfrom\s+\w", re.I)
JAVA_COMMENT = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def sql_mentions(file: str) -> list[tuple[str, int]]:
    """(name, line) for every table or entity name in a SQL/JPQL-shaped
    string literal of a source file. String concatenations are joined first,
    so "select * from " + "quoteejb" counts."""
    src = Path(file).read_text(encoding="utf-8", errors="replace")
    src = JAVA_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), src)
    out = []
    # join adjacent literals: "a" + "b"  ->  one logical literal at the first line
    for m in re.finditer(r'"(?:[^"\\\n]|\\.)*"(?:\s*\+\s*"(?:[^"\\\n]|\\.)*")*', src):
        text = "".join(STRING_LIT.findall(m.group(0)))
        if SQL_SHAPE.search(text):
            line = src[:m.start()].count("\n") + 1
            out += [(n.lower(), line) for n in SQL_NAME.findall(text)]
    return out


# ----------------------------------------------------------------- resolve

def resolve(app: str) -> dict:
    inv, calls, creations, run = load(app)
    refs_path = OUT / app / "facts" / "methodrefs.jsonl"
    mrefs = [json.loads(l) for l in refs_path.read_text().splitlines() if l.strip()]
    h = Hierarchy(inv)
    app_calls = [c for c in calls if c["owner"] in h.types]
    E = Edges()
    site_res: Counter = Counter()          # resolution per call site
    refused: Counter = Counter()
    rule_sites: Counter = Counter()

    ids, props = spring_beans(app)
    beans, ejb_refs = ejb_names(app, h)
    mx = mapper_xml(app, h, app_calls)
    ents, ent_names = entities(h, mx)
    D: dict[str, set[str]] = defaultdict(set)
    lookups: list[dict] = []

    def where(c: dict) -> str:
        return f"{rel(c['file'])}:{c['line']}"

    simple = defaultdict(list)
    for t in h.types:
        simple[t.split(".")[-1]].append(t)

    def class_of_literal(a0: dict, owner: str) -> str | None:
        """The application class an X.class argument names: the solver's
        answer when it has one, else a unique simple name, else the unique
        candidate under the owner's own source root."""
        if a0.get("resolved"):
            return a0["resolved"] if a0["resolved"] in h.types else None
        name = a0["value"].split("<")[0]
        if name in h.types:
            return name
        cands = simple.get(name.split(".")[-1], [])
        if len(cands) > 1:
            root = next((r for r in SUBJECTS[app]["roots"] if r in h.types[owner]["file"]), None)
            cands = [x for x in cands if root and root in h.types[x]["file"]]
        return cands[0] if len(cands) == 1 else None

    def binding(owner: str, field: str | None) -> set[str]:
        """Classes Spring XML wires into `field` of `owner`, for bean
        definitions whose class is the owner or one of its subclasses."""
        if not field:
            return set()
        out: set[str] = set()
        for (bean_cls, prop), classes in props.items():
            if prop == field and (bean_cls == owner or owner in h.all_supers(bean_cls)):
                out |= classes
        return out

    for c in app_calls:
        cat, t = classify(c, h)
        o, w = c["owner"], where(c)
        if cat == "J3_reflective":
            a0 = c.get("arg0") or {}
            literal = a0.get("value") if a0.get("kind") == "StringLiteralExpr" else None
            if literal is None:
                refused["lookup_nonliteral"] += 1
                site_res["refused"] += 1
                continue
            if c["method"] == "getBean":
                target = sorted(x for x in ids.get(literal, ()) if x in h.types)
                rule = "spring_getbean"
            else:
                b = bind_jndi(literal, beans, ejb_refs)
                target = [b] if b else []
                rule = "jndi_ejb"
            lookups.append({"where": w, "method": c["method"], "name": literal, "bound_to": target})
            if target:
                for x in target:
                    E.add(o, x, 1.0 / len(target), "J-L2", rule, w)
                site_res["J-L2"] += 1
                rule_sites[rule] += 1
            elif c["method"] == "getBean" or literal.split("/")[-1] in beans or "/ejb/" in literal:
                refused["lookup_unbound"] += 1
                site_res["refused"] += 1
            else:
                site_res["external"] += 1          # a container resource (JMS, UserTransaction, BeanManager)
                rule_sites["lookup_resource"] += 1
            continue
        if cat == "J6_unresolved":
            refused["unresolved"] += 1
            site_res["refused"] += 1
            continue
        if cat == "self":
            site_res["self"] += 1
            continue
        if cat == "external":
            site_res["external"] += 1
            continue
        if cat == "edge_concrete":
            E.add(o, t, 1.0, "J-L0", "call_declared", w)
            site_res["J-L0"] += 1
            rule_sites["call_declared"] += 1
            continue
        if cat == "inherited":
            E.add(o, t, 1.0, "J-L0", "call_inherited", w)
            site_res["J-L0"] += 1
            rule_sites["call_inherited"] += 1
            continue
        # an application abstraction: J1 (has implementations) or J4 (none)
        E.add(o, t, 1.0, "J-L0", "call_abstraction", w)
        impls = h.concrete_impls(t)
        if cat == "J4_no_impl":
            site_res["J-L0"] += 1
            rule_sites["call_abstraction"] += 1
            continue
        wired = sorted(x for x in binding(o, c.get("scope_field")) if x in impls)
        if wired:
            for x in wired:
                E.add(o, x, 1.0 / len(wired), "J-L2", "spring_xml_property", w)
            site_res["J-L2"] += 1
            rule_sites["spring_xml_property"] += 1
        elif len(impls) <= K:
            for x in impls:
                E.add(o, x, 1.0 / len(impls), "J-L1", "cha", w)
            site_res["J-L1"] += 1
            rule_sites[f"cha_n{len(impls) if len(impls) < 3 else '3+'}"] += 1
        else:
            refused["fanout"] += 1
            site_res["refused"] += 1

    # creations and method references (J-L0) ----------------------------------
    creation_sites = Counter()
    for x in creations:
        o, ty = x["owner"], x.get("type")
        if o not in h.types or ty not in h.types or ty == o:
            continue
        w = f"{rel(x['file'])}:{x['line']}"
        rule = "anon_impl" if x.get("anonymous_body") else "creation"
        E.add(o, ty, 1.0, "J-L0", rule, w)
        creation_sites[rule] += 1
    for x in mrefs:
        o, ty = x["owner"], x.get("decl_type")
        if o in h.types and ty in h.types and ty != o:
            E.add(o, ty, 1.0, "J-L0", "method_ref", f"{rel(x['file'])}:{x['line']}")
            creation_sites["method_ref"] += 1

    field_sites = Counter()
    frefs_path = OUT / app / "facts" / "fieldrefs.jsonl"
    for x in (json.loads(l) for l in frefs_path.read_text().splitlines() if l.strip()):
        o, ty = x["owner"], x.get("decl_type")
        if o in h.types and ty in h.types and ty != o:
            E.add(o, ty, 1.0, "J-L0", x["kind"] if x["kind"] == "class_literal" else "field_ref",
                  f"{rel(x['file'])}:{x['line']}")
            field_sites["class_literal" if x["kind"] == "class_literal" else "field_ref"] += 1
    for t in h.types:
        for s in sorted(h.supers.get(t, ())):
            if s in h.types and E.add_once(t, s, 1.0, "J-L0", "inheritance", rel(h.types[t]["file"])):
                field_sites["inheritance"] += 1

    # J-L3 framework conventions oracle ------------------------------------
    l3 = Counter()
    for t, x in h.types.items():
        for f in x["fields"]:
            if not any(ann(a) in JPA_ASSOC for a in f["annotations"]):
                continue
            for ty in [f["type"].get("erasure")] + list(f["type"].get("args") or []):
                if ty in ents and ty != t:
                    if E.add_once(t, ty, W_ASSOC, "J-L3", "jpa_assoc", f"{rel(x['file'])}:{f['line']}"):
                        l3["jpa_assoc"] += 1
                    D[t].add(ty)
    for b, tys in mx["binders"].items():
        if b not in h.types:
            continue
        rule = "mybatis_mapper" if mx["kinds"].get(b) == "mybatis" else "ibatis_sqlmap"
        for ty in tys:
            if ty != b:
                if E.add_once(b, ty, W_FACT, "J-L3", rule, mx["files"][b]):
                    l3[rule] += 1
                D[b].add(ty)
    named_queries: dict[str, str] = {}
    for t in ents:
        for a in h.types[t]["annotations"]:
            for m in re.finditer(r'@NamedQuery\s*\(\s*name\s*=\s*"([^"]+)"', a):
                named_queries[m.group(1)] = t
            for m in re.finditer(r'@NamedNativeQuery\s*\(\s*name\s*=\s*"([^"]+)"', a):
                named_queries[m.group(1)] = t
    for c in app_calls:
        a0 = c.get("arg0") or {}
        o = c["owner"]
        if a0.get("kind") == "ClassExpr":
            tgt = class_of_literal(a0, o)
            if tgt in ents and tgt != o:
                if E.add_once(o, tgt, W_FACT, "J-L3", "entity_class_literal", where(c)):
                    l3["entity_class_literal"] += 1
                D[o].add(tgt)
                rule_sites["entity_class_literal"] += 1
        if c["method"] in ("createNamedQuery", "createNamedStoredProcedureQuery") and a0.get("kind") == "StringLiteralExpr":
            tgt = named_queries.get(a0.get("value"))
            if tgt and tgt != o:
                if E.add_once(o, tgt, W_FACT, "J-L3", "jpa_named_query", where(c)):
                    l3["jpa_named_query"] += 1
                D[o].add(tgt)
                rule_sites["jpa_named_query"] += 1
    by_file: dict[str, str] = {}
    for t, x in h.types.items():
        if x["top_level"]:
            by_file.setdefault(x["file"], t)
    for file, owner in by_file.items():
        for name, line in sql_mentions(file):
            tgt = ent_names.get(name)
            if tgt and tgt != owner:
                if E.add_once(owner, tgt, W_FACT, "J-L3", "sql_table", f"{rel(file)}:{line}"):
                    l3["sql_table"] += 1
                D[owner].add(tgt)
    for a, f, w in struts_form_beans(app, h):
        if E.add_once(a, f, W_FACT, "J-L3", "struts_form_bean", w):
            l3["struts_form_bean"] += 1

    # J-T type use -----------------------------------------------------------
    def note(owner: str, ti: dict, w: str) -> None:
        for ty in [ti.get("erasure")] + list(ti.get("args") or []):
            if ty and ty.endswith("[]"):
                ty = ty[:-2]
            if ty in h.types and E.add_once(owner, ty, W_TYPE, "J-T", "type_use", w):
                l3["type_use"] += 1
    annotation_types = defaultdict(list)
    for t, x in h.types.items():
        if x["kind"] == "annotation":
            annotation_types[t.split(".")[-1]].append(t)

    def note_annotations(owner: str, anns: list[str], w: str) -> None:
        for a in anns:
            hit = annotation_types.get(ann(a), [])
            if len(hit) == 1 and E.add_once(owner, hit[0], W_TYPE, "J-T", "annotation_use", w):
                l3["annotation_use"] += 1

    for t, x in h.types.items():
        note_annotations(t, x["annotations"], f"{rel(x['file'])}:{x['line']}")
        for member in x["fields"] + x["methods"] + x["constructors"]:
            note_annotations(t, member.get("annotations", []), f"{rel(x['file'])}:{member['line']}")
        for f in x["fields"]:
            note(t, f["type"], f"{rel(x['file'])}:{f['line']}")
        for k in x["constructors"]:
            for pp in k["params"]:
                note(t, pp["type"], f"{rel(x['file'])}:{k['line']}")
        for m in x["methods"]:
            note(t, m["returns"], f"{rel(x['file'])}:{m['line']}")
            for pp in m["params"]:
                note(t, pp["type"], f"{rel(x['file'])}:{m['line']}")

    # outputs ------------------------------------------------------------------
    nodes = sorted(h.types)
    graph = {n: {d: round(v, 4) for d, v in sorted(E.g.get(n, {}).items())} for n in nodes}
    calls_graph: dict[str, Counter] = defaultdict(Counter)
    for e in E.contrib:
        if e["rule"] in CALL_RULES:
            calls_graph[e["src"]][e["dst"]] += e["w"]
    cgraph = {n: {d: round(v, 4) for d, v in sorted(calls_graph.get(n, {}).items())} for n in nodes}

    def isolated(g: dict) -> list[str]:
        inbound = {d for s, es in g.items() for d in es if d != s}
        return [n for n in nodes if not any(d != n for d in g[n]) and n not in inbound]

    n_sites = len(app_calls)
    weight_by_layer = Counter()
    pairs_by_layer: dict[str, set] = defaultdict(set)
    weight_by_rule = Counter()
    for e in E.contrib:
        weight_by_layer[e["layer"]] += e["w"]
        weight_by_rule[e["rule"]] += e["w"]
        pairs_by_layer[e["layer"]].add((e["src"], e["dst"]))
    total_w = sum(weight_by_layer.values())
    report = {
        "app": app,
        "class_nodes": len(nodes),
        "entities": sorted(ents),
        "call_sites": n_sites,
        "site_resolution": dict(site_res),
        "refused_by_reason": dict(refused),
        "sites_by_rule": dict(rule_sites),
        "creation_and_ref_sites": dict(creation_sites),
        "non_call_reference_sites": dict(field_sites),
        "fact_pairs_by_rule": dict(l3),
        "weight_by_layer": {k: round(v, 4) for k, v in weight_by_layer.items()},
        "weight_share_by_layer": {k: round(v / total_w, 4) for k, v in weight_by_layer.items()} if total_w else {},
        "weight_by_rule": {k: round(v, 4) for k, v in weight_by_rule.items()},
        "pairs_by_layer": {k: len(v) for k, v in pairs_by_layer.items()},
        "edges": sum(len(v) for v in graph.values()),
        "call_edges": sum(len(v) for v in cgraph.values()),
        "isolated": isolated(graph),
        "isolated_calls_graph": isolated(cgraph),
        "data_map_classes": sum(1 for v in D.values() if v),
        "fanout_cap": K,
    }
    rr = {f"sites_{k}": v for k, v in site_res.items()}
    rr.update({f"refused_{k}": v for k, v in refused.items()})
    rr.update({f"rule_{k}": v for k, v in sorted(rule_sites.items())})
    rr.update({f"fact_{k}": v for k, v in sorted(l3.items())})
    payload = {
        "parameters": {"resolver": "java-layered", "fanout_cap": K, "w_assoc": W_ASSOC, "w_fact": W_FACT,
                       "w_type": W_TYPE, "analyzer": run.get("analyzer_version"),
                       "javaparser": run.get("javaparser_version")},
        "summary": {"total_classes_original": len(nodes), "total_data_entities": len(ents),
                    "edges": report["edges"], "isolated_classes": len(report["isolated"])},
        "resolver_report": rr,
        "dependency_graph": graph,
        "data_associations": {n: sorted(D.get(n, ())) for n in nodes},
        "clusters": [],
        "isolated_classes": report["isolated"],
    }
    od = OUT / app
    (od / "resolver").mkdir(parents=True, exist_ok=True)
    (od / "graph.json").write_text(json.dumps(payload, indent=2))
    (od / "calls_graph.json").write_text(json.dumps({
        "parameters": {"resolver": "java-layered", "layers": ["J-L0", "J-L1", "J-L2"], "rules": list(CALL_RULES)},
        "dependency_graph": cgraph, "isolated_classes": report["isolated_calls_graph"]}, indent=2))
    with (od / "resolver" / "edges.jsonl").open("w") as f:
        for e in E.contrib:
            f.write(json.dumps(e) + "\n")
    (od / "resolver" / "provenance.json").write_text(json.dumps(report, indent=2))
    (od / "resolver" / "lookups.json").write_text(json.dumps(lookups, indent=2))
    return report


def main(apps: list[str]) -> None:
    for app in apps:
        r = resolve(app)
        print(f"{app:18s} nodes={r['class_nodes']} sites={r['call_sites']} {r['site_resolution']} "
              f"refused={r['refused_by_reason']} facts={r['fact_pairs_by_rule']} edges={r['edges']} "
              f"isolated={len(r['isolated'])} (calls only {len(r['isolated_calls_graph'])})")


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUBJECTS))
