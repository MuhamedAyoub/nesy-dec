"""Phase 4: Java symbolic facts in the Rails fact-base schema.

Ports the fact typing of neurosymbolic/symbolic/rules.py to Java. The output
has the keys SymbolicFacts.from_json reads (classes, must_link, cannot_link,
soft_affinity, framework_noise, role_groups, namespaces) plus inferred_coupling,
and every class name is a fully qualified name taken from G, so no
qualification pass is needed. The exact-match check that qualify_facts_v2.py
exists for is still run and reported (qualification.json).

Relations:

  must_link        hard same-service evidence, mirroring Rails' associations
                   and model/service lookups:
                     jpa:assoc:<Kind>     JPA association fields (J-L3 jpa_assoc)
                     jpa:entity_lookup    entity access through EntityManager
                                          class literals, named queries, SQL/JPQL
                                          literals (J-L3), the analogue of
                                          rails:model_lookup
                     mybatis:mapper, ibatis:sqlmap   binder <-> domain class
                     di:wired             a J-L2 binding (Spring XML property,
                                          JNDI EJB name, getBean id)
                     di:inject            an injection point (@Inject, @EJB,
                                          @Resource, @Autowired, @SpringBean,
                                          implicit constructor injection) typed
                                          by a concrete app class or by an
                                          abstraction with exactly one
                                          implementation, the analogue of
                                          rails:service_call
                     ejb:business_interface  a session bean and the app
                                          interfaces it implements
                     struts:form_bean     a Struts action and its form bean
  framework_noise  a documented rule, not a list:
                     N1 generic base: an app abstract class with >= 3 concrete
                        app subclasses
                     N2 constants holder: static fields only, no methods, no
                        instance fields
                     N3 ubiquitous helper: role util or config, and referenced
                        in G by >= 20% of the other active classes
  soft_affinity    graded, summed per pair and capped at 1.0 as in Rails:
                     role:<r>      same stereotype, 0.15 (Rails' role weight);
                                   not for roles other, interface, unknown
                     package:<p>   same Java package, max(0.1, min(1, 2/n)),
                                   n = classes in the package (Rails' concern
                                   co-inclusion weight)
                     page:<file>   named together on one JSP/JSF page, same
                                   2/n grading
  inferred_coupling  neurosymbolic.infer_coupling.transitive_coupling on G,
                   unchanged from Rails
  cannot_link      the Java analogue of Rails' sibling namespaces
                   (rules.py), rule CL-SIBLING. Two sibling packages A and B
                   (one parent, each counted with its sub-packages) are
                   disjoint when all of these hold:
                     1. each holds at least 2 active classes that are not
                        framework noise;
                     2. there is no direct (J-L0, J-L2, J-L3) and no
                        type-use (J-T) edge between them, in either
                        direction. J-L1 edges are the resolver's own 1/n
                        over-approximation, not code evidence, so they do
                        not count;
                     3. they are peers in one layer: either their dominant
                        layer by stereotype (LAYER_OF_ROLE) is the same, or
                        their classes implement at least one common
                        application interface (alternative
                        implementations).
                   Every pair (a, b) with a in A and b in B is stored
                   explicitly, with `namespaces` left empty, so the RL mask,
                   the RQ4 count and the encoder loss all see one set. The
                   rule was written after reviewing these six subjects
                   (FACTS.md, section 2); results/facts_survey/
                   holds that review.

Roles are Java stereotypes (ROLES), assigned by the first matching rule in
role_of(); a class no rule matched takes the role of an app service or
repository type it implements. graph_env one-hot encodes them through
java_pipeline.rl_paths.

Usage: python3 -m java_pipeline.facts [app ...]
Writes results/<app>/facts_nesy.json and results/<app>/facts_report.json.
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from java_pipeline.audit import (DI_ANNOTATIONS, MANAGED_STEREOTYPES, Hierarchy, load, mapper_xml,
                                 page_files, rel)
from java_pipeline.resolver import ann, ann_single
from java_pipeline.subjects import OUT, SUBJECTS

ROLES = ("entity", "repository", "service", "ejb_session", "message_driven", "servlet", "web_controller",
         "websocket", "ui_bean", "form", "exception", "config", "util", "interface", "other", "unknown")
ROLE_W = 0.15
NOISE_FANIN = 0.20
N1_MIN_SUBCLASSES = 3

SERVLET_SUPERS = ("javax.servlet.http.HttpServlet", "javax.servlet.GenericServlet", "javax.servlet.Servlet",
                  "javax.servlet.Filter", "javax.servlet.ServletContextListener",
                  "javax.servlet.http.HttpSessionListener")
CONTROLLER_SUPERS = ("org.apache.struts.action.Action", "net.sourceforge.stripes.action.ActionBean",
                     "org.springframework.web.servlet.mvc.Controller")
FORM_SUPERS = ("org.apache.struts.action.ActionForm",)
CONFIG_SUPERS = ("javax.ws.rs.core.Application",)


def pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a < b else (b, a)


def role_of(t: str, h: Hierarchy, mx: dict, ents: set[str]) -> tuple[str, str]:
    """(role, rule that assigned it). First match wins; the order is the
    documented precedence."""
    x = h.types[t]
    anns = {ann(a) for a in x["annotations"]}
    supers = h.all_supers(t)
    simple = t.split(".")[-1]
    hit = lambda names: any(s == n or s.startswith(n + "<") for s in supers for n in names)
    if anns & {"Entity", "Embeddable", "MappedSuperclass"} or t in ents:
        return "entity", "annotation or SQL-mapped domain type"
    if "Repository" in anns or mx["kinds"].get(t) in ("mybatis", "ibatis") \
            or re.search(r"(Dao|DAO|Repository|Mapper)$", simple) \
            or any(re.search(r"(Dao|DAO|Repository)$", s.split(".")[-1]) for s in supers if s in h.types):
        return "repository", "annotation, SQL-mapping binder, or Dao/Repository/Mapper name or supertype"
    if anns & {"MessageDriven"}:
        return "message_driven", "@MessageDriven"
    if anns & {"Stateless", "Stateful", "Singleton"}:
        return "ejb_session", "session-bean annotation"
    if anns & {"WebServlet", "WebFilter", "WebListener"} or hit(SERVLET_SUPERS):
        return "servlet", "servlet annotation or supertype"
    if anns & {"Controller", "RestController", "Path", "UrlBinding"} or hit(CONTROLLER_SUPERS) \
            or re.search(r"(Controller|ActionBean)$", simple):
        return "web_controller", "controller annotation, supertype or name"
    if anns & {"ServerEndpoint"}:
        return "websocket", "@ServerEndpoint"
    if anns & {"Named", "ManagedBean"}:
        return "ui_bean", "@Named/@ManagedBean"
    if hit(FORM_SUPERS) or re.search(r"Form$", simple):
        return "form", "ActionForm supertype or Form name"
    if any(s.endswith(("Exception", "Error", "Throwable")) for s in supers) or simple.endswith("Exception"):
        return "exception", "Throwable supertype or name"
    if anns & {"ApplicationPath", "Configuration"} or hit(CONFIG_SUPERS) \
            or re.search(r"(Config|Configuration|Constants|Producer|Factory|Locator)$", simple):
        return "config", "configuration annotation, supertype or name"
    if anns & ({"Service"} | set(MANAGED_STEREOTYPES) - {"Repository", "Controller", "RestController"}) \
            or re.search(r"(Service|ServiceImpl|Facade|Manager|Mgr|Logic)$", simple):
        return "service", "service annotation or name"
    methods = x["methods"]
    if methods and all(m["static"] for m in methods) and not any(not f["static"] for f in x["fields"]) \
            or re.search(r"(Util|Utils|Helper|Helpers)$", simple):
        return "util", "static-only members or Util/Helper name"
    if x["kind"] == "interface":
        return "interface", "interface with no other role"
    if x["kind"] in ("class", "enum", "record", "annotation"):
        return "other", "no rule matched"
    return "unknown", "unrecognised kind"


# Architectural layer of each stereotype, for CL-SIBLING's peer test. Roles
# without a layer (util, config, exception, interface, other, unknown) do not vote.
LAYER_OF_ROLE = {"servlet": "presentation", "web_controller": "presentation", "websocket": "presentation",
                 "ui_bean": "presentation", "form": "presentation",
                 "service": "business", "ejb_session": "business", "message_driven": "business",
                 "entity": "data", "repository": "data"}


def sibling_cannot_link(h: Hierarchy, roles: dict[str, str], edges: list[dict], active: set[str],
                        noise: set[str]) -> tuple[list[tuple[str, str, str]], list[dict]]:
    """Rule CL-SIBLING (module docstring). Returns the pairs and one record per
    package pair the rule accepted."""
    import itertools
    tops = {t for t, x in h.types.items() if x["top_level"]}

    def top_of(t: str) -> str:
        while t not in tops and "." in t:
            t = t.rsplit(".", 1)[0]
        return t

    pkg = {t: top_of(t).rsplit(".", 1)[0] for t in h.types}
    members = lambda p: {c for c, q in pkg.items() if (q == p or q.startswith(p + ".")) and c in active and c not in noise}
    children: dict[str, set[str]] = {}
    for q in set(pkg.values()):
        parts = q.split(".")
        for i in range(1, len(parts)):
            children.setdefault(".".join(parts[:i]), set()).add(".".join(parts[:i + 1]))
    evidence = {(e["src"], e["dst"]) for e in edges if e["layer"] != "J-L1"}

    def layer(cs: set[str]) -> str | None:
        votes = Counter(LAYER_OF_ROLE[roles[c]] for c in cs if roles.get(c) in LAYER_OF_ROLE)
        return votes.most_common(1)[0][0] if votes else None

    def app_supers(cs: set[str]) -> set[str]:
        return {s for c in cs for s in h.all_supers(c) if s in h.types and h.types[s]["kind"] == "interface"}

    pairs, accepted = [], []
    for parent, kids in sorted(children.items()):
        for a, b in itertools.combinations(sorted(kids), 2):
            A, B = members(a), members(b)
            if len(A) < 2 or len(B) < 2:
                continue
            if any((x, y) in evidence or (y, x) in evidence for x in A for y in B):
                continue
            la, lb = layer(A), layer(B)
            shared = app_supers(A) & app_supers(B)
            if not ((la is not None and la == lb) or shared):
                continue
            accepted.append({"a": a, "b": b, "classes": [len(A), len(B)], "layer": [la, lb],
                             "shared_interfaces": sorted(x.split(".")[-1] for x in shared)})
            tag = f"cl_sibling:{a.split('.')[-1]}|{b.split('.')[-1]}"
            pairs += [(*pair(x, y), tag) for x in sorted(A) for y in sorted(B)]
    return pairs, accepted


def page_references(app: str, h: Hierarchy) -> dict[str, set[str]]:
    """Page file -> application classes it names, by fully qualified name
    (beanclass, useBean, import) or through JSF/CDI EL (#{name}/${name}
    resolved against @Named/@ManagedBean names)."""
    named = {}
    for t, x in h.types.items():
        for a in x["annotations"]:
            if ann(a) in ("Named", "ManagedBean"):
                simple = t.split(".")[-1]
                named[ann_single(a) or simple[0].lower() + simple[1:]] = t
    fq = re.compile(r"\b([a-z][\w]*(?:\.[a-z][\w]*)+\.[A-Z][\w$]*)")
    out: dict[str, set[str]] = {}
    for p in page_files(app):
        text = p.read_text(encoding="utf-8", errors="replace")
        refs = {m.group(1) for m in fq.finditer(text) if m.group(1) in h.types}
        refs |= {named[m.group(1)] for m in re.finditer(r"[#$]\{\s*([A-Za-z_]\w*)", text) if m.group(1) in named}
        if len(refs) >= 2:
            out[rel(str(p))] = refs
    return out


def build(app: str) -> dict:
    inv, calls, creations, run = load(app)
    h = Hierarchy(inv)
    app_calls = [c for c in calls if c["owner"] in h.types]
    G = json.loads((OUT / app / "graph.json").read_text())
    graph = G["dependency_graph"]
    nodes = set(graph)
    edges = [json.loads(l) for l in (OUT / app / "resolver" / "edges.jsonl").read_text().splitlines() if l.strip()]
    prov = json.loads((OUT / app / "resolver" / "provenance.json").read_text())
    ents = set(prov["entities"])
    mx = mapper_xml(app, h, app_calls)
    isolated = set(G["isolated_classes"])
    active = nodes - isolated

    # roles -------------------------------------------------------------------
    roles, role_rule = {}, {}
    for t in sorted(h.types):
        roles[t], role_rule[t] = role_of(t, h, mx, ents)
    # a class that implements an app type of role service or repository, and
    # matched no rule of its own, takes that role
    for t in sorted(h.types):
        if roles[t] == "other":
            inherited = sorted({roles[s] for s in h.all_supers(t) if s in roles and roles[s] in ("service", "repository")})
            if len(inherited) == 1:
                roles[t], role_rule[t] = inherited[0], f"implements an app {inherited[0]} type"
    role_groups: dict[str, list[str]] = defaultdict(list)
    for t, r in roles.items():
        role_groups[r].append(t)

    # must-link ---------------------------------------------------------------
    raw_ml: list[tuple[str, str, str]] = []
    jpa_kind = {}
    for t, x in h.types.items():
        for f in x["fields"]:
            k = next((ann(a) for a in f["annotations"] if ann(a) in ("OneToMany", "ManyToOne", "OneToOne", "ManyToMany")), None)
            if k:
                for ty in [f["type"].get("erasure")] + list(f["type"].get("args") or []):
                    jpa_kind[(t, ty)] = k
    for e in edges:
        a, b, r = e["src"], e["dst"], e["rule"]
        if r == "jpa_assoc":
            raw_ml.append((a, b, f"jpa:assoc:{jpa_kind.get((a, b), '?')}"))
        elif r in ("entity_class_literal", "jpa_named_query", "sql_table"):
            raw_ml.append((a, b, "jpa:entity_lookup"))
        elif r == "mybatis_mapper":
            raw_ml.append((a, b, "mybatis:mapper"))
        elif r == "ibatis_sqlmap":
            raw_ml.append((a, b, "ibatis:sqlmap"))
        elif r in ("spring_xml_property", "jndi_ejb", "spring_getbean"):
            raw_ml.append((a, b, "di:wired"))
        elif r == "struts_form_bean":
            raw_ml.append((a, b, "struts:form_bean"))
    for t, x in h.types.items():
        points = [f["type"].get("erasure") for f in x["fields"]
                  if any(ann(a) in DI_ANNOTATIONS for a in f["annotations"])]
        managed = any(ann(a) in MANAGED_STEREOTYPES for a in x["annotations"])
        for k in x["constructors"]:
            if any(ann(a) in DI_ANNOTATIONS for a in k["annotations"]) or (managed and len(x["constructors"]) == 1):
                points += [p["type"].get("erasure") for p in k["params"]]
        for ty in points:
            if ty not in h.types or ty == t:
                continue
            if h.is_abstraction(ty):
                impls = h.concrete_impls(ty)
                if len(impls) == 1 and impls[0] != t:
                    raw_ml.append((t, impls[0], "di:inject"))
            else:
                raw_ml.append((t, ty, "di:inject"))
        if any(ann(a) in ("Stateless", "Stateful", "Singleton") for a in x["annotations"]):
            for s in h.supers.get(t, ()):
                if s in h.types and h.types[s]["kind"] == "interface":
                    raw_ml.append((t, s, "ejb:business_interface"))

    # framework noise ---------------------------------------------------------
    inbound: dict[str, set[str]] = defaultdict(set)
    for s, es in graph.items():
        for d in es:
            if d != s:
                inbound[d].add(s)
    noise: dict[str, str] = {}
    for t, x in h.types.items():
        if x["kind"] == "class" and x["abstract"]:
            subs = [s for s in h.subs.get(t, ()) if s in h.types and not h.is_abstraction(s)]
            if len(subs) >= N1_MIN_SUBCLASSES:
                noise[t] = f"N1 generic base ({len(subs)} concrete subclasses)"
                continue
        if x["fields"] and all(f["static"] or x["kind"] == "interface" for f in x["fields"]) \
                and not x["methods"] and not x["constructors"] \
                and x["kind"] in ("class", "interface"):
            noise[t] = "N2 constants holder"
            continue
        if roles[t] in ("util", "config") and t in active and len(active) > 1:
            frac = len(inbound[t] & active) / (len(active) - 1)
            if frac >= NOISE_FANIN:
                noise[t] = f"N3 ubiquitous {roles[t]} (referenced by {frac:.0%} of active classes)"

    # soft affinity -----------------------------------------------------------
    raw_soft: list[tuple[str, str, float, str]] = []
    for r, members in role_groups.items():
        if r in ("other", "interface", "unknown") or len(members) < 2:
            continue
        ms = sorted(members)
        for i in range(len(ms)):
            for j in range(i + 1, len(ms)):
                raw_soft.append((ms[i], ms[j], ROLE_W, f"role:{r}"))
    by_pkg: dict[str, list[str]] = defaultdict(list)
    for t in h.types:
        by_pkg[t.rsplit(".", 1)[0] if h.types[t]["top_level"] else (h.types[t]["enclosing"] or t).rsplit(".", 1)[0]].append(t)
    for pkg, members in by_pkg.items():
        n = len(members)
        if n < 2:
            continue
        w = max(0.1, min(1.0, 2.0 / n))
        ms = sorted(members)
        for i in range(n):
            for j in range(i + 1, n):
                raw_soft.append((ms[i], ms[j], w, f"package:{pkg}"))
    pages = page_references(app, h)
    for page, refs in pages.items():
        n = len(refs)
        w = max(0.1, min(1.0, 2.0 / n))
        ms = sorted(refs)
        for i in range(n):
            for j in range(i + 1, n):
                raw_soft.append((ms[i], ms[j], w, f"page:{page}"))

    # inferred coupling (unchanged Rails code) ------------------------------
    from neurosymbolic.infer_coupling import transitive_coupling
    ic = transitive_coupling(graph, max_hops=2)

    # qualification: every endpoint must be a node of G, exactly ------------
    report: dict = {"app": app, "nodes": len(nodes), "active_nodes": len(active)}

    def qualify(rel_name: str, items: list[tuple], ends: int = 2) -> list[tuple]:
        kept, dropped = [], Counter()
        for it in items:
            a, b = it[0], it[1]
            if a == b:
                dropped["self_pair"] += 1
            elif a not in nodes or b not in nodes:
                dropped["endpoint_not_in_G"] += 1
            else:
                kept.append(it)
        report[rel_name] = {"raw": len(items), "matched": len(kept), "dropped": dict(dropped),
                            "both_endpoints_active": sum(1 for it in kept if it[0] in active and it[1] in active)}
        return kept

    ml = qualify("must_link", [(*pair(a, b), r) for a, b, r in raw_ml])
    ml = sorted(set(ml))
    report["must_link"]["unique_after_dedup"] = len(ml)
    report["must_link"]["by_reason"] = dict(Counter(r for _, _, r in ml))
    # one pair may carry several reasons; the env and the loss see pairs
    report["must_link"]["unique_pairs"] = len({(a, b) for a, b, _ in ml})
    soft = qualify("soft_affinity", raw_soft)
    agg: dict[tuple[str, str], tuple[float, list[str]]] = {}
    for a, b, w, r in soft:
        pw, pr = agg.get((a, b), (0.0, []))
        agg[(a, b)] = (min(1.0, pw + w), pr + [r])
    soft = sorted((a, b, round(w, 4), ";".join(rs)) for (a, b), (w, rs) in agg.items())
    report["soft_affinity"]["unique_pairs"] = len(soft)
    report["soft_affinity"]["by_source"] = dict(Counter(r.split(":")[0] for _, _, _, rr in soft for r in rr.split(";")))
    inferred = qualify("inferred_coupling", [(a, b, round(c, 4), "inferred:transitive_flow") for (a, b), c in sorted(ic.items())])
    raw_cl, accepted = sibling_cannot_link(h, roles, edges, active, set(noise))
    cl = sorted(set(qualify("cannot_link", raw_cl)))
    report["cannot_link"]["unique_pairs"] = len({(a, b) for a, b, _ in cl})
    report["cannot_link"]["rule"] = "CL-SIBLING"
    report["cannot_link"]["package_pairs"] = accepted
    report["framework_noise"] = {"count": len(noise), "by_rule": dict(Counter(v.split()[0] for v in noise.values())),
                                 "classes": {k: v for k, v in sorted(noise.items())}}
    report["roles"] = {r: len(role_groups.get(r, [])) for r in ROLES}
    report["role_rules"] = dict(Counter(role_rule.values()))
    report["pages_with_two_or_more_classes"] = len(pages)
    ml_pairs = {(a, b) for a, b, _ in ml}
    report["must_link_cannot_link_conflicts"] = len(ml_pairs & {(a, b) for a, b, _ in cl})
    report["must_link_pairs_on_framework_noise"] = sum(1 for a, b in ml_pairs if a in noise or b in noise)

    facts = {
        "app": app,
        "classes": sorted(nodes),
        "must_link": [list(x) for x in ml],
        "cannot_link": [list(x) for x in cl],
        "soft_affinity": [list(x) for x in soft],
        "framework_noise": sorted(noise),
        "role_groups": {r: sorted(role_groups[r]) for r in ROLES if role_groups.get(r)},
        "namespaces": {},
        "inferred_coupling": [list(x) for x in inferred],
        "roles_vocabulary": list(ROLES),
    }
    (OUT / app / "facts_nesy.json").write_text(json.dumps(facts, indent=2))
    (OUT / app / "facts_report.json").write_text(json.dumps(report, indent=2))
    return report


def main(apps: list[str]) -> None:
    for app in apps:
        r = build(app)
        print(f"{app:18s} ML {r['must_link']['unique_pairs']} pairs {r['must_link']['by_reason']} | "
              f"soft {r['soft_affinity']['unique_pairs']} | inferred {r['inferred_coupling']['matched']} | "
              f"noise {r['framework_noise']['by_rule']} | roles {{{', '.join(f'{k}:{v}' for k, v in r['roles'].items() if v)}}}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUBJECTS))
