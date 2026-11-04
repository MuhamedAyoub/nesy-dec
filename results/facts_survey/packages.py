"""Package and module structure per subject, for FACTS.md section 2 (the
cannot-link source question). Output: packages.json next to this file."""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from java_pipeline.subjects import DATA, OUT, SUBJECTS  # noqa: E402

out = {}
for app, s in SUBJECTS.items():
    inv = json.loads((OUT / app / "facts" / "inventory.json").read_text())
    pk = Counter()
    mods = Counter()
    for t in inv:
        top = t if t["top_level"] else None
        name = t["name"] if t["top_level"] else (t["enclosing"] or t["name"])
        pk[name.rsplit(".", 1)[0]] += 1
        root = next((r for r in s["roots"] if str(DATA / r) in t["file"]), "?")
        mods[root.split("/src/main/java")[0]] += 1
    out[app] = {"packages": dict(sorted(pk.items())), "source_modules": dict(mods)}
(Path(__file__).parent / "packages.json").write_text(json.dumps(out, indent=2))
for app, d in out.items():
    print(app, d["source_modules"])
    for p, n in d["packages"].items():
        print(f"    {p}: {n}")
