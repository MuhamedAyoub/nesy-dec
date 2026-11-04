"""Edges of G between source modules, per subject: evidence for FACTS.md
section 2 (a module boundary that the code calls across in one direction is a
layer, not a bounded context). Output: module_edges.json next to this file."""
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from java_pipeline.subjects import DATA, OUT, SUBJECTS  # noqa: E402

out = {}
for app, s in SUBJECTS.items():
    inv = json.loads((OUT / app / "facts" / "inventory.json").read_text())
    mod = {t["name"]: next((r.split("/src/main/java")[0].split("/")[-1] for r in s["roots"] if str(DATA / r) in t["file"]), "?")
           for t in inv}
    G = json.loads((OUT / app / "graph.json").read_text())["dependency_graph"]
    c = Counter()
    for a, es in G.items():
        for b, w in es.items():
            if a != b:
                c[f"{mod[a]} -> {mod[b]}"] += 1
    out[app] = dict(sorted(c.items()))
(Path(__file__).parent / "module_edges.json").write_text(json.dumps(out, indent=2))
for app, d in out.items():
    if len({k.split(' -> ')[0] for k in d}) > 1:
        print(app)
        for k, v in d.items():
            print(f"    {k}: {v}")
