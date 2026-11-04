"""Compare the repro_check GraphRL-Dec reruns with the reported runs (VERIFICATION.md section 1).
Run from <repo>/: python3 results/verify/repro_check.py"""
import json, glob
for p in sorted(glob.glob("results/_nesy/rl_ablation/repro_check/*/*/partition.json")):
    app, run = p.split("/")[-3], p.split("/")[-2]
    a = json.load(open(f"results/_nesy/rl/{app}/{run}/partition.json"))
    b = json.load(open(p))
    same = {frozenset(x) for x in a["partitions"]} == {frozenset(x) for x in b["partitions"]}
    la = json.load(open(f"results/_nesy/rl/{app}/{run}/train_log.json"))
    lb = json.load(open(p.replace("partition.json", "train_log.json")))
    print(app, run, "partition identical:", same, "| decode trajectory identical:",
          [r["decode_score"] for r in la] == [r["decode_score"] for r in lb],
          "| score", a["raw_composite_on_G"]["Score"], b["raw_composite_on_G"]["Score"])
