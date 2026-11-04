"""Second review of cannot-link sources in the Java subjects (FACTS.md section 2).

The Rails rule (rules.py) takes the sub-directory under a role directory as a
namespace, and treats distinct namespaces as disjoint. The Java analogue is
sibling packages under one parent. For every pair of sibling packages (and
top-level groupings) this lists the edges of G across the pair, split by
evidence: direct code evidence (J-L0, J-L2, J-L3), hierarchy splits (J-L1),
and type use (J-T), excluding framework-noise classes.

Usage: python3 results/facts_survey/constraint_review.py > results/facts_survey/constraint_review.out
"""
import itertools
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from java_pipeline.subjects import OUT, SUBJECTS  # noqa: E402

for app in SUBJECTS:
    inv = json.loads((OUT / app / "facts" / "inventory.json").read_text())
    facts = json.loads((OUT / app / "facts_nesy.json").read_text())
    noise = set(facts["framework_noise"])
    pkg = {}
    for t in inv:
        top = t["name"] if t["top_level"] else (t["enclosing"] or t["name"])
        while top not in {x["name"] for x in inv if x["top_level"]} and "." in top:
            top = top.rsplit(".", 1)[0]
        pkg[t["name"]] = top.rsplit(".", 1)[0]
    groups = defaultdict(list)
    for c, p in pkg.items():
        groups[p].append(c)
    edges = [json.loads(l) for l in (OUT / app / "resolver" / "edges.jsonl").read_text().splitlines()]
    print(f"\n=== {app}: {len(groups)} packages")
    for p, cs in sorted(groups.items()):
        print(f"  {p}: {len(cs)}")
    # sibling pairs: packages sharing a parent; a package's subtree counts as one group
    pkgs = sorted(groups)
    parents = defaultdict(set)
    for p in pkgs:
        parts = p.split(".")
        for i in range(1, len(parts)):
            parents[".".join(parts[:i])].add(".".join(parts[:i + 1]))
    print("  sibling pairs (subtrees) with cross evidence [direct / J-L1 / J-T, excluding noise]:")
    for parent, kids in sorted(parents.items()):
        kids = sorted(kids)
        if len(kids) < 2:
            continue
        sub = lambda k: {c for c, p in pkg.items() if p == k or p.startswith(k + ".")}
        for a, b in itertools.combinations(kids, 2):
            A, B = sub(a), sub(b)
            c = Counter()
            for e in edges:
                if e["src"] in noise or e["dst"] in noise:
                    continue
                if (e["src"] in A and e["dst"] in B) or (e["src"] in B and e["dst"] in A):
                    c["JL1" if e["layer"] == "J-L1" else "JT" if e["layer"] == "J-T" else "direct"] += 1
            print(f"    {a.removeprefix(parent + '.')} ({len(A)}) x {b.removeprefix(parent + '.')} ({len(B)}) under {parent}: "
                  f"direct {c['direct']}, J-L1 {c['JL1']}, J-T {c['JT']}")
