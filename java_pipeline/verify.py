"""Phase 8: rebuild one app from its sources and compare with the reported outputs.

Runs every CPU stage again with JAVA_RESULTS_DIR pointing at
results/verify/rerun/:
- analyzer, audit, resolver;
- the teacher at both alphas, facts, code index, triplets;
- the Sellami export and HierDec.

It then compares each output file with the one under results/<app>/.
JSON is compared after dropping wall-time fields (seconds, train_seconds);
JSON Lines and .npy files byte for byte.

The GPU stages are not part of this check, since they need the server.
Their reproducibility is checked by rerunning one GraphRL-Dec run there
(VERIFICATION.md).

Usage: python3 -m java_pipeline.verify [app]       (default jpetstore-6)
Writes results/verify/<app>_rerun.json.
"""
from __future__ import annotations

import filecmp
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORTED = REPO / "results"
RERUN = REPORTED / "verify" / "rerun"
JDK = Path(os.environ.get("JDK_HOME", Path.home() / ".local/opt/jdk-21.0.13+9"))
RLDEC_PY = os.environ.get("RLDEC_PYTHON", str(Path.home() / "miniconda3/envs/rldec/bin/python"))
VOLATILE = {"seconds", "train_seconds", "wall_seconds"}
FILES = ["facts/inventory.json", "facts/callsites.jsonl", "facts/creations.jsonl", "facts/methodrefs.jsonl",
         "facts/fieldrefs.jsonl", "facts/run.json", "audit/audit.json", "naive_graph.json", "graph.json",
         "calls_graph.json", "resolver/edges.jsonl", "resolver/provenance.json", "resolver/lookups.json",
         "exp_a0.9_b0.1_n8_java.json", "exp_a0.5_b0.5_n8_java.json", "facts_nesy.json", "facts_report.json",
         "code_index.json", "triplets.json", "triplets_report.json",
         "sellami/hierdec/structural_data/class_calls.npy", "sellami/hierdec/semantic_data/class_tfidf.npy",
         "sellami/rldec/{app}/class_interactions.csv", "sellami/rldec/{app}/class_word_count.csv",
         "baselines/hierdec.json"]


def strip(x):
    if isinstance(x, dict):
        return {k: strip(v) for k, v in x.items() if k not in VOLATILE}
    if isinstance(x, list):
        return [strip(v) for v in x]
    return x


def run(cmd: list[str], **kw) -> None:
    env = dict(os.environ, JAVA_RESULTS_DIR=str(RERUN))
    r = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise SystemExit(f"[verify] failed: {' '.join(cmd)}\n{r.stderr[-2000:]}")


def main(app: str) -> None:
    if RERUN.exists():
        shutil.rmtree(RERUN)
    (RERUN / app / "facts").mkdir(parents=True)
    py = sys.executable
    jar = next(iter(sorted((REPO / "java_analyzer" / "target").glob("java-analyzer-*.jar"))))
    run([py, "-m", "java_pipeline.subjects"])
    f = RERUN / app / "facts"
    run([str(JDK / "bin" / "java"), "-Xss8m", "-jar", str(jar), str(f / "config.json"), str(f)])
    for mod in ("audit", "resolver"):
        run([py, "-m", f"java_pipeline.{mod}", app])
    for a, b in (("0.9", "0.1"), ("0.5", "0.5")):
        run(["ruby", "java_pipeline/teacher.rb", str(RERUN / app / "graph.json"),
             str(RERUN / app / f"exp_a{a}_b{b}_n8_java.json"), a, b])
    for mod in ("facts", "code_index", "triplets", "export_sellami"):
        run([py, "-m", f"java_pipeline.{mod}", app])
    run([RLDEC_PY, "-m", "java_pipeline.run_hierdec", app])

    results = {}
    for rel in (x.format(app=app) for x in FILES):
        a, b = REPORTED / app / rel, RERUN / app / rel
        if not a.is_file() or not b.is_file():
            results[rel] = "missing"
        elif rel == "triplets.json":
            # same multiset expected; the order of tied entries follows Python
            # set iteration in neurosymbolic/triplets.py (PYTHONHASHSEED)
            ka, kb = (sorted(json.dumps(x, sort_keys=True) for x in json.loads(p.read_text())) for p in (a, b))
            results[rel] = ("identical" if a.read_bytes() == b.read_bytes()
                            else "same multiset, order differs" if ka == kb else "DIFFERENT")
        elif rel.endswith(".json"):
            ja, jb = strip(json.loads(a.read_text())), strip(json.loads(b.read_text()))
            if rel.startswith("exp_"):
                # parameters.graph records the input path, which is the rerun directory
                ja["parameters"].pop("graph", None)
                jb["parameters"].pop("graph", None)
            results[rel] = "identical" if ja == jb else "DIFFERENT"
        else:
            results[rel] = "identical" if filecmp.cmp(a, b, shallow=False) else "DIFFERENT"
    out = {"app": app, "files": results,
           "all_identical": all(v in ("identical", "same multiset, order differs") for v in results.values()),
           "normalisations": ["wall-time fields dropped", "exp_*: parameters.graph (input path) dropped",
                              "triplets.json: compared as a multiset when the byte order differs"]}
    (REPORTED / "verify").mkdir(exist_ok=True)
    (REPORTED / "verify" / f"{app}_rerun.json").write_text(json.dumps(out, indent=2))
    for k, v in results.items():
        print(f"  {v:10s} {k}")
    print(f"[verify] {app}: {'all identical' if out['all_identical'] else 'DIFFERENCES FOUND'}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "jpetstore-6")
