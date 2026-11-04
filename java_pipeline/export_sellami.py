"""Phase 6: export one Java app to the input formats of HierDec and RLDec.

The class set is the teacher's active set (G without isolated classes), in
sorted order, so every method in the comparison partitions the same classes.

  results/<app>/sellami/hierdec/structural_data/class_calls.npy   G, N x N
  results/<app>/sellami/hierdec/structural_data/class_names.json
  results/<app>/sellami/hierdec/semantic_data/class_tfidf.npy     N x V TF-IDF
  results/<app>/sellami/hierdec/semantic_data/class_names.json
  results/<app>/sellami/rldec/<app>/class_interactions.csv        G, N x N
  results/<app>/sellami/rldec/<app>/class_word_count.csv          N x N word intersection
  results/<app>/sellami/rldec/<app>/class_tfidf.csv               N x V (RLDec reads names from it)

Both structural matrices are our G, so HierDec and RLDec see the same graph
as the teacher and GraphRL-Dec (RECON.md section 4). Rows are callers,
columns callees.

The semantic features come from the parsing service's own TFIDFTransformer
(vendored in java_pipeline/vendor/), fed with each class's full source text,
comments included. That stands in for the Spoon analyzer's `textAndNames`,
whose exact content we cannot reproduce without the analysis service. The
word-intersection matrix follows SemParser.get_count_data: TF-IDF columns
for terms that occur in at most half the classes, times the transpose.

Usage: python3 -m java_pipeline.export_sellami [app ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from java_pipeline.code_index import body_end, strip_comments
from java_pipeline.subjects import OUT, SUBJECTS
from java_pipeline.vendor.decparsing_tfidf import TFIDFTransformer

TEACHER = "exp_a0.9_b0.1_n8_java.json"


def class_text(file: str, line: int, simple: str) -> str:
    import re
    raw = Path(file).read_text(encoding="utf-8", errors="replace").splitlines()
    clean = strip_comments("\n".join(raw)).splitlines()
    start = max(0, line - 1)
    decl = re.compile(rf"\b(class|interface|enum|record|@interface)\s+{re.escape(simple)}\b")
    head = next((i for i in range(start, len(clean)) if decl.search(clean[i])), start)
    end = body_end(clean, head)
    return "\n".join(raw[start:end + 1])


def export(app: str) -> dict:
    exp = json.loads((OUT / app / TEACHER).read_text())
    names = sorted(exp["dependency_graph"])
    idx = {n: i for i, n in enumerate(names)}
    G = json.loads((OUT / app / "graph.json").read_text())["dependency_graph"]
    A = np.zeros((len(names), len(names)), dtype=np.float64)
    for s in names:
        for d, w in G[s].items():
            if d in idx:
                A[idx[s], idx[d]] += w
    inv = {t["name"]: t for t in json.loads((OUT / app / "facts" / "inventory.json").read_text())}
    texts = [[class_text(inv[n]["file"], inv[n]["line"], n.split(".")[-1])] for n in names]
    tf = TFIDFTransformer(texts)
    tf.build()
    tfidf = tf.get_matrix()
    vocab = list(tf.get_vocabulary())
    counts = tf.word_counts
    wi = tfidf[:, counts <= tfidf.shape[0] // 2]
    wi = wi.dot(wi.T)

    root = OUT / app / "sellami"
    for sub in ("structural_data", "semantic_data"):
        (root / "hierdec" / sub).mkdir(parents=True, exist_ok=True)
        (root / "hierdec" / sub / "class_names.json").write_text(json.dumps(names))
    np.save(root / "hierdec" / "structural_data" / "class_calls.npy", A)
    np.save(root / "hierdec" / "semantic_data" / "class_tfidf.npy", tfidf)
    r = root / "rldec" / app
    r.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(A, index=names, columns=names).to_csv(r / "class_interactions.csv")
    pd.DataFrame(wi, index=names, columns=names).to_csv(r / "class_word_count.csv")
    pd.DataFrame(tfidf, index=names, columns=vocab).to_csv(r / "class_tfidf.csv")
    rep = {"app": app, "classes": len(names), "vocabulary": len(vocab), "edges": int((A > 0).sum()),
           "weight": float(A.sum()), "rare_terms_for_word_intersection": int((counts <= tfidf.shape[0] // 2).sum())}
    (root / "export.json").write_text(json.dumps(rep, indent=2))
    return rep


def main(apps: list[str]) -> None:
    for app in apps:
        print(export(app))


if __name__ == "__main__":
    main(sys.argv[1:] or list(SUBJECTS))
