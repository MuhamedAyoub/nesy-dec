"""Phase 5: contrastive triplets for NeSy-Rep on a Java app.

Calls neurosymbolic.triplets.generate_triplets unchanged, with the Rails
pipeline's settings (target 1,500 per app as in run_everything_v2.py stage 4,
the default source mixes, seed 42). Its inputs are the Java fact base
(facts_nesy.json) and the teacher's experiment file, whose graph is G with
isolated classes removed, exactly the graph the RL stage reads.

The Rails CLI (triplets.main) is not used: it re-extracts Rails facts from
source and ignores its --facts-dir argument, so it cannot be pointed at
another fact base.

Usage: python3 -m java_pipeline.triplets [app ...]
Writes results/<app>/triplets.json and triplets_report.json.
"""
from __future__ import annotations

import json
import sys
from collections import Counter

from java_pipeline.subjects import OUT, SUBJECTS
from neurosymbolic.symbolic.rules import SymbolicFacts
from neurosymbolic.triplets import generate_triplets, save_triplets

TARGET = 1500
SEED = 42
TEACHER = "exp_a0.9_b0.1_n8_java.json"


def build(app: str) -> dict:
    facts = SymbolicFacts.from_json(json.loads((OUT / app / "facts_nesy.json").read_text()))
    exp = json.loads((OUT / app / TEACHER).read_text())
    graph, data = exp["dependency_graph"], exp["data_associations"]
    index = json.loads((OUT / app / "code_index.json").read_text())
    trips = generate_triplets(facts, graph, data, target_count=TARGET, seed=SEED)
    missing = {n for t in trips for n in (t.anchor, t.positive, t.negative) if n not in index}
    if missing:
        raise SystemExit(f"[triplets] {app}: {len(missing)} names missing from the code index")
    save_triplets(trips, OUT / app / "triplets.json")
    rep = {"app": app, "triplets": len(trips), "target": TARGET, "seed": SEED,
           "pos_sources": dict(Counter(t.pos_source for t in trips)),
           "neg_sources": dict(Counter(t.neg_source for t in trips)),
           "distinct_anchors": len({t.anchor for t in trips}),
           "active_classes": len(graph)}
    (OUT / app / "triplets_report.json").write_text(json.dumps(rep, indent=2))
    return rep


def main(apps: list[str]) -> None:
    for app in apps:
        r = build(app)
        print(f"{app:18s} {r['triplets']} triplets, anchors {r['distinct_anchors']}/{r['active_classes']} "
              f"pos {r['pos_sources']} neg {r['neg_sources']}")


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUBJECTS))
