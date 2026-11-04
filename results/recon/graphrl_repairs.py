"""Which classes GraphRL-Dec full moves away from the teacher's partition, and
what that does to the fact pairs (RESULTS.md, findings 2 and 3).

A GraphRL-Dec service is matched to the teacher service it overlaps most; a
class is moved when its service's match is not its teacher service.

Run from <repo>/:
  python3 results/recon/graphrl_repairs.py > results/recon/graphrl_repairs.out
"""
import glob
import json

OUT = "results"
for app in ("acmeair", "daytrader7", "lit-jpetstore"):
    exp = json.load(open(f"{OUT}/{app}/exp_a0.9_b0.1_n8_java.json"))
    active = set(exp["dependency_graph"])
    T = [c["classes"] for c in exp["clusters"]]
    t_of = {c: k for k, p in enumerate(T) for c in p}
    facts = json.load(open(f"{OUT}/{app}/facts_nesy.json"))
    cl = {tuple(sorted(x[:2])) for x in facts["cannot_link"]}
    ml = {tuple(sorted(x[:2])) for x in facts["must_link"] if x[0] in active and x[1] in active}
    violated = {c for a, b in cl if t_of[a] == t_of[b] for c in (a, b)}
    print(f"=== {app}: {len(active)} classes; teacher violates {sum(t_of[a] == t_of[b] for a, b in cl)} of {len(cl)} "
          f"cannot-link pairs, keeps {sum(t_of[a] == t_of[b] for a, b in ml)} of {len(ml)} must-link pairs")
    for p in sorted(glob.glob(f"{OUT}/_nesy/rl/{app}/full_s*/partition.json")):
        R = json.load(open(p))["partitions"]
        r_of = {c: k for k, q in enumerate(R) for c in q}
        match = {k: max(range(len(T)), key=lambda j: len(set(R[k]) & set(T[j]))) for k in range(len(R))}
        moved = sorted(c for c in r_of if match[r_of[c]] != t_of[c])
        lost = sorted((a.split(".")[-1], b.split(".")[-1]) for a, b in ml if t_of[a] == t_of[b] and r_of[a] != r_of[b])
        print(f"  {p.split('/')[-2]}: moved {len(moved)}, of them in a violated cannot-link pair {len(set(moved) & violated)}; "
              f"cannot-link violations {sum(r_of[a] == r_of[b] for a, b in cl)}; "
              f"must-link kept {sum(r_of[a] == r_of[b] for a, b in ml)} of {len(ml)}")
        print(f"    moved: {[c.split('.')[-1] for c in moved]}")
        print(f"    must-link pairs lost: {lost}")
