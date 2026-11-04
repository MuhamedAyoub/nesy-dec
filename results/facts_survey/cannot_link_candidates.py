"""Candidate Java cannot-link pairs from the second review, and how many of
them each method's partition violates.

Rule under test: sibling packages A, B with at least 2 classes each that sit in
one architectural layer (under a shared web package, or implementing the same
application interfaces), with zero direct edges and zero type-use edges between
them. J-L1 edges do not count, since they are the resolver's own 1/n
over-approximation and not code evidence. Pairs cover active classes that
are not framework noise.

Usage: python3 results/facts_survey/cannot_link_candidates.py > results/facts_survey/cannot_link_candidates.out
"""
import glob
import itertools
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from java_pipeline.audit import Hierarchy  # noqa: E402
from java_pipeline.subjects import OUT  # noqa: E402

B = {"daytrader7": [("com.ibm.websphere.samples.daytrader.web.jsf", "com.ibm.websphere.samples.daytrader.web.prims"),
                    ("com.ibm.websphere.samples.daytrader.web.jsf", "com.ibm.websphere.samples.daytrader.web.websocket")],
     "acmeair": [("com.acmeair.morphia", "com.acmeair.wxs")],
     "lit-jpetstore": [("org.springframework.samples.jpetstore.web.spring", "org.springframework.samples.jpetstore.web.struts")]}

for app, pairs in B.items():
    exp = json.loads((OUT / app / "exp_a0.9_b0.1_n8_java.json").read_text())
    active = set(exp["dependency_graph"])
    facts = json.loads((OUT / app / "facts_nesy.json").read_text())
    noise = set(facts["framework_noise"])
    ml = {tuple(sorted(x[:2])) for x in facts["must_link"]}
    inv = json.loads((OUT / app / "facts" / "inventory.json").read_text())
    h = Hierarchy(inv)
    cl = set()
    print(f"\n=== {app}")
    for a, b in pairs:
        A = {c for c in active - noise if c.startswith(a + ".")}
        Bb = {c for c in active - noise if c.startswith(b + ".")}
        shared = sorted({s.split(".")[-1] for x in A for s in h.all_supers(x) if s in h.types}
                        & {s.split(".")[-1] for x in Bb for s in h.all_supers(x) if s in h.types})
        new = {tuple(sorted(p)) for p in itertools.product(A, Bb)}
        cl |= new
        print(f"  {a.split('.')[-1]} ({len(A)}) x {b.split('.')[-1]} ({len(Bb)}): {len(new)} pairs; shared app supertypes: {len(shared)} {shared[:8]}")
    print(f"  total pairs {len(cl)}; conflicts with must-link {len(cl & ml)}")
    methods = {"teacher": [c["classes"] for c in exp["clusters"]]}
    for f in ("unixcoder_ward_nesyrep", "unixcoder_ward_pretrained", "hierdec"):
        methods[f] = json.loads((OUT / app / "baselines" / f"{f}.json").read_text())["partitions"]
    for s in (42, 1, 7):
        methods[f"rldec_best_s{s}"] = json.loads((OUT / app / "baselines" / f"rldec_best_s{s}.json").read_text())["partitions"]
        methods[f"rldec_cli_s{s}"] = json.loads((OUT / app / "baselines" / f"rldec_s{s}.json").read_text())["partitions"]
        methods[f"graphrl_full_s{s}"] = json.loads((OUT / "_nesy" / "rl" / app / f"full_s{s}" / "partition.json").read_text())["partitions"]
    for m, parts in methods.items():
        of = {c: k for k, p in enumerate(parts) for c in p}
        v = sum(1 for x, y in cl if x in of and y in of and of[x] == of[y])
        print(f"    {m:28s} violations {v:5d} of {len(cl)} ({100 * v / len(cl):.1f}%)")
