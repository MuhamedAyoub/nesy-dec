#!/usr/bin/env python3
"""Phase 1 subject survey: class counts, frameworks and wiring per benchmark.

Read only over datasets_java/. Counts come from two sources:

  compiled   .class files under each module's build output, split into
             top-level (no '$'), named nested ('$Name') and anonymous or
             local ('$1', '$1Local'). Only for modules that built.
  source     .java files outside test directories, plus a regex inventory of
             framework imports and wiring annotations. Regexes are an
             inventory, not a parse; Phase 2's parser gives exact numbers.

Usage: python3 results/subjects/survey.py > results/subjects/survey.json
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "datasets_java"

# subject -> list of (module label, source root, compiled root or None, role)
# role: "app" = part of the application as built; "alt" = alternative
# implementation not in the default build; "tool" = not part of the app.
SUBJECTS = {
    "jpetstore-6": [("jpetstore", "jpetstore-6/src/main/java", "jpetstore-6/target/classes", "app")],
    "acmeair": [
        ("acmeair-common", "acmeair/acmeair-common/src/main/java", "acmeair/acmeair-common/build/classes/main", "app"),
        ("acmeair-services", "acmeair/acmeair-services/src/main/java", "acmeair/acmeair-services/build/classes/main", "app"),
        ("acmeair-services-morphia", "acmeair/acmeair-services-morphia/src/main/java", "acmeair/acmeair-services-morphia/build/classes/main", "app"),
        ("acmeair-loader", "acmeair/acmeair-loader/src/main/java", "acmeair/acmeair-loader/build/classes/main", "app"),
        ("acmeair-webapp", "acmeair/acmeair-webapp/src/main/java", "acmeair/acmeair-webapp/build/classes/main", "app"),
        ("acmeair-services-wxs", "acmeair/acmeair-services-wxs/src/main/java", None, "alt"),
        ("acmeair-reporter", "acmeair/acmeair-reporter/src/main/java", None, "tool"),
    ],
    "daytrader7": [
        ("daytrader-ee7-ejb", "sample.daytrader7/daytrader-ee7-ejb/src/main/java", "sample.daytrader7/daytrader-ee7-ejb/target/classes", "app"),
        ("daytrader-ee7-web", "sample.daytrader7/daytrader-ee7-web/src/main/java", "sample.daytrader7/daytrader-ee7-web/target/classes", "app"),
    ],
    "plantsbywebsphere": [("pbw", "sample.plantsbywebsphere/src/main/java", "sample.plantsbywebsphere/target/classes", "app")],
    # literature variants: source inventory only (not built)
    "lit:KimJongSung/jPetStore": [("jpetstore", "KimJongSung__jPetStore/src/main/java", None, "app")],
    "lit:pbw-monolith@e6f2a6a": [
        ("PlantsByWebSphere", "SteeleDesmond__sample.mono-to-ms.pbw-monolith/PlantsByWebSphere/src/main/java", None, "app"),
        ("pbw-lib", "SteeleDesmond__sample.mono-to-ms.pbw-monolith/pbw-lib/src/main/java", None, "app"),
    ],
}

FRAMEWORKS = {
    "EJB": r"javax\.ejb\.", "JPA": r"javax\.persistence\.", "Servlet": r"javax\.servlet\.",
    "JSF": r"javax\.faces\.", "JAX-RS": r"javax\.ws\.rs\.", "CDI": r"javax\.(inject|enterprise)\.",
    "WebSocket": r"javax\.websocket\.", "JMS": r"javax\.jms\.", "JNDI": r"javax\.naming\.",
    "Stripes": r"net\.sourceforge\.stripes\.", "MyBatis": r"org\.mybatis\.|org\.apache\.ibatis\.",
    "iBatis(Spring)": r"orm\.ibatis\.|com\.ibatis\.", "Spring": r"org\.springframework\.",
    "Struts": r"org\.apache\.struts\.", "Morphia/Mongo": r"org\.mongodb\.morphia|com\.mongodb\.",
    "WXS(objectgrid)": r"com\.ibm\.websphere\.objectgrid", "JAX-WS": r"javax\.xml\.ws\.",
}
WIRING = {
    "@Entity": r"@Entity\b", "@Stateless/@Stateful/@Singleton": r"@(Stateless|Stateful|Singleton)\b",
    "@MessageDriven": r"@MessageDriven\b", "@WebServlet/@WebFilter/@WebListener": r"@Web(Servlet|Filter|Listener)\b",
    "@Path/@ApplicationPath": r"@(Path|ApplicationPath)\b", "@Named/@ManagedBean": r"@(Named|ManagedBean)\b",
    "@ServerEndpoint": r"@ServerEndpoint\b", "Stripes ActionBean": r"implements\s+[\w, ]*ActionBean|extends\s+AbstractActionBean",
    "Spring stereotype": r"@(Controller|RestController|Service|Repository|Component|Configuration)\b",
    "Struts Action": r"extends\s+\w*Action\b",
}
INJECTION = {"@Inject": r"@Inject\b", "@EJB": r"@EJB\b", "@Resource": r"@Resource\b",
             "@Autowired": r"@Autowired\b", "@PersistenceContext": r"@PersistenceContext\b",
             "JNDI lookup(": r"\.lookup\s*\(", "Class.forName(": r"Class\.forName\s*\("}
XML = ("web.xml", "persistence.xml", "ejb-jar.xml", "faces-config.xml", "beans.xml",
       "struts-config.xml", "server.xml", "orm.xml")


def compiled_counts(d: Path) -> dict:
    files = [p for p in d.rglob("*.class")] if d and d.is_dir() else []
    c = Counter()
    for p in files:
        name = p.stem
        if "$" not in name:
            c["top_level"] += 1
        elif re.search(r"\$\d", name):
            c["anonymous_or_local"] += 1
        else:
            c["named_nested"] += 1
    c["total"] = len(files)
    return dict(c)


def source_inventory(d: Path) -> dict:
    files = [p for p in d.rglob("*.java") if "/test/" not in str(p)] if d.is_dir() else []
    fw, wi, inj = Counter(), Counter(), Counter()
    pkgs = Counter()
    for p in files:
        t = p.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^\s*package\s+([\w.]+)\s*;", t, re.M)
        pkgs[m.group(1) if m else "(default)"] += 1
        for k, rx in FRAMEWORKS.items():
            if re.search(r"^\s*import\s+(static\s+)?(" + rx + ")", t, re.M):
                fw[k] += 1
        for k, rx in WIRING.items():
            if re.search(rx, t):
                wi[k] += 1
        for k, rx in INJECTION.items():
            inj[k] += len(re.findall(rx, t))
    return {"java_files": len(files), "packages": dict(sorted(pkgs.items())),
            "framework_import_files": dict(fw), "wiring_annotation_files": dict(wi),
            "injection_and_lookup_sites": dict(inj)}


def xml_configs(subject_dirs: set[Path]) -> dict:
    out = Counter()
    for base in subject_dirs:
        for p in base.rglob("*.xml"):
            s = str(p)
            if "/.git/" in s or "/target/" in s or "/build/" in s or "/test/" in s:
                continue
            if p.name in XML or p.name.startswith("applicationContext") or p.name.endswith("-servlet.xml"):
                out[p.name] += 1
            elif re.search(r"<mapper\s+namespace=|<sqlMap\b", p.read_text(errors="replace")[:4000]):
                out["(mybatis/ibatis mapper xml)"] += 1
    return dict(out)


def main():
    report = {}
    for subj, modules in SUBJECTS.items():
        mods = {}
        for label, src, cls, role in modules:
            mods[label] = {"role": role, "source": source_inventory(ROOT / src),
                           "compiled": compiled_counts(ROOT / cls) if cls else None}
        tops = {(ROOT / m[1]).parts[len(ROOT.parts)] for m in modules}
        report[subj] = {"modules": mods, "xml_configs": xml_configs({ROOT / t for t in tops})}
    json.dump(report, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
