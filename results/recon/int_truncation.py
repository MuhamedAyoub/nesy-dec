"""How much of each graph's edge weight survives graph_env.py:685, which
stores every edge of the incremental reward tracker as int(w). For RUNS.md
section 5. Usage: python3 results/recon/int_truncation.py > int_truncation.out"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GRAPHS = [(f"rails {a}", REPO / "results" / "recon" / "rails_graphs" / a / "exp_a0.9_b0.1_n8_v2.json")  # copies of the RoR-MSI graphs
          for a in ("astuto-main", "chatwoot-develop", "canvas-lms")]
GRAPHS += [(f"java {a}", REPO / "results" / a / "exp_a0.9_b0.1_n8_java.json")
           for a in ("jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw")]
for name, p in GRAPHS:
    g = json.loads(p.read_text())["dependency_graph"]
    w = [v for s, e in g.items() for t, v in e.items() if t != s]
    kept = sum(int(v) for v in w) / sum(w)
    print(f"{name:28s} weight kept {kept:.3f}  edges zeroed {sum(1 for v in w if int(v) == 0)}/{len(w)}")
