#!/usr/bin/env python3
"""Phase 5 and 6 GPU stages: NeSy-Rep, GraphRL-Dec and the learned baselines on Java.

Every CPU stage (analysis, resolver, teacher, facts, code index, triplets,
Sellami export, HierDec) has already written its outputs under results/.
This driver runs what needs a GPU, or benefits from one, with the Rails
hyperparameters unchanged (results/RUNS.md lists them with their source).

Stages (run in this order; each is resumable):

  check      preflight: inputs present, every app loads into the RL env, fact
             counts survive the env's exact-name filter, CUDA visible
  b0         pretrained UnixCoder embeddings, no fine-tuning (baseline input)
  encoder    NeSy-Rep: UnixCoder + LoRA fine-tune on the Java triplets
  rl         GraphRL-Dec: 8 reward variants x apps x seeds, decoded partitions
  baselines  UnixCoder+Ward and UnixCoder+HDBSCAN (fine-tuned and pretrained),
             random, from the embedding banks
  rldec      RLDec (combsequential, 20 iterations) per app and seed, run with
             the Python given by --rldec-python
  pack       tarball of everything the GPU box produced

Outputs under results/_nesy/ (encoder/, b0_pretrained/, rl/) and
results/<app>/baselines/.

Usage on the GPU server (normally through java_pipeline/run_server.sh; see results/GPU_RUNBOOK.md):
  python -m java_pipeline.run_gpu --stages check
  python -m java_pipeline.run_gpu --stages b0,encoder,rl,baselines,rldec,pack --seeds 42 1 7
CPU smoke test (minutes, tiny settings, nothing it writes is a result):
  python -m java_pipeline.run_gpu --smoke
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from java_pipeline import rl_paths  # noqa: E402
from java_pipeline.subjects import OUT  # noqa: E402

APPS = ["jpetstore-6", "acmeair", "daytrader7", "plantsbywebsphere", "lit-jpetstore", "lit-pbw"]
RUN = rl_paths.RUN
B0 = RUN / "b0_pretrained" / "embeddings"

# NeSy-Rep: neurosymbolic/experiments/runner.py ExpConfig defaults, with the
# paper's design rule (lambda_ml, lambda_cl) = (0.0, 0.3) from
# run_everything_v2.py BEST_ML / BEST_CL, and 1,500 target triplets (stage 4).
ENCODER = dict(epochs=3, batch_size=16, lr=5e-5, max_length=512, use_lora=True, seed=42,
               triplet_margin=0.3, constraint_margin=0.5, lambda_must_link=0.0, lambda_cannot_link=0.3)
# GraphRL-Dec: run_everything_v2.py stage 7 and its argument defaults.
RL = dict(episodes="600", num_envs="64", warmstart_epochs="800", warmstart_lr="1e-3", lr="1e-4",
          kl_coef="0.5", size_cap_factor="5.0", reward_mode="zscore", log_every="300")


def config_hash(cfg: dict) -> str:
    """First 12 hex digits of the SHA-256 of the canonical JSON config."""
    import hashlib
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:12]


def encoder_config(apps: list[str]) -> dict:
    return {"stage": "encoder", "apps": apps, **ENCODER}


def rl_config(app: str, name: str, seed: int, extra: list[str]) -> dict:
    return {"stage": "rl", "app": app, "variant": name, "seed": seed, **RL, "extra": extra,
            "teacher": rl_paths.TEACHER, "select_by_decode": True}


def rldec_config(app: str, seed: int) -> dict:
    return {"stage": "rldec", "app": app, "approach": "combsequential", "iterations": 20, "seed": seed,
            "source": "decomp-rldec@45187548"}


def fmt(sec: float) -> str:
    h, r = divmod(int(sec), 3600)
    m, s = divmod(r, 60)
    return f"{h}h{m:02d}m{s:02d}s" if h else f"{m}m{s:02d}s"


def banner(t: str) -> None:
    print(f"\n{'=' * 78}\n# {t}\n{'=' * 78}", flush=True)


# ------------------------------------------------------------------ check

def check(apps: list[str], embeddings_dir: Path | None) -> bool:
    banner("check")
    import torch
    rl_paths.activate(embeddings_dir)        # Java role vocabulary, as the rl stage uses
    ok = True
    print(f"  torch {torch.__version__}, cuda available: {torch.cuda.is_available()}"
          + (f" ({torch.cuda.get_device_name(0)})" if torch.cuda.is_available() else ""))
    for m in ("transformers", "peft", "sklearn", "numpy"):
        try:
            __import__(m)
        except ImportError:
            print(f"  FAIL  missing python package {m}")
            ok = False
    for app in apps:
        need = [OUT / app / f for f in ("graph.json", "calls_graph.json", rl_paths.TEACHER, "facts_nesy.json",
                                        "code_index.json", "triplets.json")]
        miss = [str(p.relative_to(REPO)) for p in need if not p.is_file()]
        if miss:
            print(f"  FAIL  {app}: missing {miss}")
            ok = False
            continue
        trip = json.loads((OUT / app / "triplets.json").read_text())
        facts = json.loads((OUT / app / "facts_nesy.json").read_text())
        exp = json.loads(rl_paths.teacher(app).read_text())
        active = set(exp["dependency_graph"])
        ml_active = {tuple(sorted(x[:2])) for x in facts["must_link"] if x[0] in active and x[1] in active}
        cl_active = {tuple(sorted(x[:2])) for x in facts["cannot_link"] if x[0] in active and x[1] in active}
        line = (f"  {app:18s} N={len(active):4d} teacher K={len(exp['clusters']):3d} triplets={len(trip):5d} "
                f"must_link(active pairs)={len(ml_active):3d} cannot_link(active pairs)={len(cl_active):4d}")
        emb = (embeddings_dir or rl_paths.EMBEDDINGS) / f"{app}.pt"
        if emb.is_file():
            from neurosymbolic.rl.graph_env import EnvConfig, load_env_for_app
            env = load_env_for_app(app, facts_path=OUT / app / "facts_nesy.json", graph_exp_json=rl_paths.teacher(app),
                                   embeddings_pt=emb, config=EnvConfig(n_clusters=len(exp["clusters"])))
            line += (f" | env N={len(env.names)} E={env.edge_index.shape[1]} feat={env.node_features.shape[1]} "
                     f"ML={len(env.must_link)} CL={len(env.cannot_link)}")
            if (len(env.names) != len(active) or len(env.must_link) != len(ml_active)
                    or len(env.cannot_link) != len(cl_active)):
                line += "  <- MISMATCH"
                ok = False
        else:
            line += f" | env not loaded (no {emb.name} yet)"
        if not trip:
            line += "  <- NO TRIPLETS"
            ok = False
        print(line)
    print("\n[check] " + ("OK" if ok else "FAILED"))
    return ok


# --------------------------------------------------------------- encoders

def stage_inputs(apps: list[str]) -> Path:
    """neural.train.train reads <dir>/<app>.json from three directories."""
    root = RUN / "inputs"
    for sub, name in (("triplets", "triplets.json"), ("code_index", "code_index.json"), ("facts", "facts_nesy.json")):
        (root / sub).mkdir(parents=True, exist_ok=True)
        for app in apps:
            shutil.copy2(OUT / app / name, root / sub / f"{app}.json")
    return root


def b0(apps: list[str], device: str) -> None:
    banner("b0: pretrained UnixCoder embeddings")
    import torch
    from neurosymbolic.neural.model import build_model
    model, tok = build_model(use_lora=False)
    model.to(device).eval()
    B0.mkdir(parents=True, exist_ok=True)
    for app in apps:
        idx = json.loads((OUT / app / "code_index.json").read_text())
        names = sorted(idx)
        embs = []
        with torch.no_grad():
            for i in range(0, len(names), ENCODER["batch_size"]):
                chunk = [idx[n]["code"] for n in names[i:i + ENCODER["batch_size"]]]
                enc = tok(chunk, max_length=ENCODER["max_length"], padding=True, truncation=True,
                          return_tensors="pt").to(device)
                embs.append(model(enc["input_ids"], enc["attention_mask"]).cpu())
        torch.save({"names": names, "embeddings": torch.cat(embs)}, B0 / f"{app}.pt")
        print(f"  {app}: {len(names)} classes -> {B0 / (app + '.pt')}")


def encoder(apps: list[str], smoke: bool) -> None:
    banner("encoder: NeSy-Rep fine-tune")
    from neurosymbolic.neural.loss import LossConfig
    from neurosymbolic.neural.train import train
    root = stage_inputs(apps)
    lc = LossConfig(triplet_margin=ENCODER["triplet_margin"], constraint_margin=ENCODER["constraint_margin"],
                    lambda_must_link=ENCODER["lambda_must_link"], lambda_cannot_link=ENCODER["lambda_cannot_link"])
    out = RUN / ("encoder_smoke" if smoke else "encoder") / "train"
    t0 = time.time()
    train(apps=apps, triplets_dir=root / "triplets", code_index_dir=root / "code_index", facts_dir=root / "facts",
          out_dir=out, epochs=1 if smoke else ENCODER["epochs"],
          # smoke only: small batches so a CPU box without 16 GB to spare can run it
          batch_size=2 if smoke else ENCODER["batch_size"], lr=ENCODER["lr"],
          max_length=256 if smoke else ENCODER["max_length"], use_lora=ENCODER["use_lora"],
          use_constraint_loss=True, loss_config=lc,
          smoke=smoke, seed=ENCODER["seed"])
    (out / "run.json").write_text(json.dumps({"apps": apps, "config": ENCODER, "smoke": smoke,
                                              "config_hash": config_hash(encoder_config(apps)),
                                              "seconds": round(time.time() - t0, 1)}, indent=2))
    print(f"[encoder] done in {fmt(time.time() - t0)}")


# ---------------------------------------------------------------------- rl

def score(parts: list[list[str]], graph: dict) -> dict:
    from vendor.ror_msi.evaluate import compute_composite_score, compute_icp, compute_ifn, compute_ned, compute_sm
    sm, ifn, icp, ned = (compute_sm(parts, graph), compute_ifn(parts, graph), compute_icp(parts, graph),
                         compute_ned(parts))
    return {"SM": sm, "IFN": ifn, "ICP": icp, "NED": ned, "Score": compute_composite_score(sm, ifn, icp, ned, len(parts))}


def decode(app: str, ckpt: Path, device: str) -> list[list[str]]:
    import torch
    from neurosymbolic.rl.decompose import greedy_decompose
    from neurosymbolic.rl.eval import _load_policy
    from neurosymbolic.rl.graph_env import EnvConfig, load_env_for_app
    raw = torch.load(ckpt, weights_only=False, map_location=device)
    meta = raw.get("env_meta", {})
    pol = _load_policy(ckpt, torch.device(device))
    cfg = (EnvConfig(n_clusters=int(meta["n_real_clusters"]), allow_outliers=True) if meta.get("allow_outliers")
           else EnvConfig(n_clusters=int(pol.cfg.n_clusters)))
    p = rl_paths.paths(app)
    env = load_env_for_app(app, facts_path=p["facts"], graph_exp_json=p["graph_exp"],
                           embeddings_pt=p["embeddings"], config=cfg)
    return greedy_decompose(env, pol, torch.device(device))


# Labelled ablations of the RL stage. They change Rails hyperparameters, so
# they are reported separately from the main sweep, never in its place. The
# override flags come after the variant's own flags (argparse keeps the last).
ABLATIONS = {
    # no KL anchor to the behaviour-cloned policy, 2,000 episodes
    "kl0_ep2000": {"episodes": "2000", "override": ["--kl-coef", "0.0"]},
    # no behaviour-cloning warm start at all, 2,000 episodes
    "nobc_ep2000": {"episodes": "2000", "warmstart_epochs": "0", "override": ["--kl-coef", "0.0"]},
    # idea 1 (java_pipeline/dual_reward.py): reward = mean of the evaluate and
    # rldec z-scores; with the paper's anchoring, and without it
    "dual_kl05": {"dual": True, "override": []},
    "dual_kl0_ep2000": {"dual": True, "episodes": "2000", "override": ["--kl-coef", "0.0"]},
    # the main config unchanged: a second run of a reported run, for VERIFICATION.md
    # (results.py skips this family)
    "repro_check": {"override": []},
    # warm start from NeSy-Rep + Ward instead of the RoR-MSI teacher
    # (teacher_file); graph and z-score peers stay the RoR-MSI ones. With the
    # paper's anchoring, and with the kl0_ep2000 setting (results/recon/setting_selection.out)
    "nesyward": {"teacher": "nesyward", "override": []},
    "nesyward_kl0_ep2000": {"teacher": "nesyward", "episodes": "2000", "override": ["--kl-coef", "0.0"]},
}


def teacher_file(app: str, teacher: str | None) -> Path:
    """The partition behaviour cloning imitates: the RoR-MSI teacher, or NeSy-Rep + Ward
    written in the teacher's file format (only `clusters` is read by the warm start)."""
    if teacher is None:
        return rl_paths.paths(app)["graph_exp"]
    if teacher != "nesyward":
        raise SystemExit(f"unknown teacher {teacher}")
    out = OUT / app / "exp_nesyward_java.json"
    if not out.is_file():
        exp = json.loads(rl_paths.paths(app)["graph_exp"].read_text())
        parts = json.loads((OUT / app / "baselines" / "unixcoder_ward_nesyrep.json").read_text())["partitions"]
        exp["clusters"] = [{"id": i + 1, "name": f"NeSyWard{i + 1}", "classes": sorted(c)} for i, c in enumerate(parts)]
        exp["cluster_metrics"] = None
        exp["parameters"] = dict(exp.get("parameters", {}), source="baselines/unixcoder_ward_nesyrep.json")
        out.write_text(json.dumps(exp, indent=2))
    return out


def rl(apps: list[str], seeds: list[int], device: str, variants: list[str] | None, smoke: bool,
       ablation: str | None = None) -> None:
    banner(f"rl: GraphRL-Dec {'ablation ' + ablation if ablation else 'sweep'}")
    import run_neurosym_ablation as ab
    rl_paths.activate(B0 if smoke else None)
    from neurosymbolic.rl import train as train_mod
    names = variants or list(ab.VARIANTS)
    abl = ABLATIONS[ablation] if ablation else {}
    if abl.get("dual"):
        from java_pipeline import dual_reward
        dual_reward.activate()
    cfg = dict(RL, **{k: v for k, v in abl.items() if k not in ("override", "dual", "teacher")})
    if smoke:
        cfg.update(episodes="8", num_envs="2", warmstart_epochs="5", log_every="4")
    override = abl.get("override", [])
    root = RUN / ("rl_smoke" if smoke else f"rl_ablation/{ablation}" if ablation else "rl")
    total, done, t_all = len(apps) * len(seeds) * len(names), 0, time.time()
    # seeds outermost, so an interrupted run leaves whole seeds complete
    for seed in seeds:
        for app in apps:
            p = rl_paths.paths(app)
            for name in names:
                done += 1
                run = root / app / f"{name.replace('+', '')}_s{seed}"
                if (run / "partition.json").is_file():
                    print(f"[{done}/{total}] {app} {name} s{seed}: done, skipping")
                    continue
                print(f"\n{'#' * 72}\n# [{done}/{total}] {app} | {name} | seed {seed}\n{'#' * 72}", flush=True)
                argv = ["train", "--app", app, "--device", device, "--num-envs", cfg["num_envs"],
                        "--episodes", cfg["episodes"], "--reward-mode", cfg["reward_mode"],
                        "--facts-path", str(p["facts"]), "--graph-exp", str(p["graph_exp"]),
                        "--embeddings", str(p["embeddings"]), "--warmstart-rails", str(teacher_file(app, abl.get("teacher"))),
                        "--warmstart-epochs", cfg["warmstart_epochs"], "--warmstart-lr", cfg["warmstart_lr"],
                        "--lr", cfg["lr"], "--seed", str(seed), "--kl-coef", cfg["kl_coef"],
                        "--size-cap-factor", cfg["size_cap_factor"], "--log-every", cfg["log_every"],
                        "--select-by-decode", "--output-dir", str(run), "--force-overwrite"] + ab.VARIANTS[name] + override
                old, t0 = sys.argv, time.time()
                sys.argv = argv
                try:
                    train_mod.main()
                finally:
                    sys.argv = old
                ckpt = run / "policy_best.pt"
                parts = decode(app, ckpt, device)
                graph = json.loads(p["graph_exp"].read_text())["dependency_graph"]
                hcfg = rl_config(app, name, seed, ab.VARIANTS[name])
                if ablation:
                    hcfg = dict(hcfg, ablation=ablation, **{k: v for k, v in cfg.items() if k in RL}, override=override,
                                **({"reward": "dual"} if abl.get("dual") else {}),
                                **({"teacher": abl["teacher"]} if abl.get("teacher") else {}))
                rec = {"method": "graphrl", "app": app, "variant": name, "seed": seed, "smoke": smoke,
                       "ablation": ablation, "config_hash": None if smoke else config_hash(hcfg),
                       "seconds": round(time.time() - t0, 1), "argv": argv[1:], "partitions": parts,
                       "raw_composite_on_G": score(parts, graph)}
                if ablation and (run / "policy.pt").is_file():
                    # the last policy too, so drift away from the best decode is visible
                    last = decode(app, run / "policy.pt", device)
                    rec["final_policy_partitions"] = last
                    rec["final_policy_raw_composite_on_G"] = score(last, graph)
                (run / "partition.json").write_text(json.dumps(rec, indent=2))
                print(f"  -> Score {rec['raw_composite_on_G']['Score']:+.4f} sizes "
                      f"{sorted(map(len, parts), reverse=True)[:10]} [{fmt(time.time() - t0)}]", flush=True)
    print(f"\n[rl] finished in {fmt(time.time() - t_all)}")


# --------------------------------------------------------------- baselines

def baselines(apps: list[str], seeds: list[int], smoke: bool) -> None:
    banner("baselines: UnixCoder+Ward, UnixCoder+HDBSCAN, random")
    from neurosymbolic.rl.eval import _phase1_clustering_partition, _phase1_hdbscan_partition, _random_partition
    banks = {"pretrained": B0} if smoke else {"nesyrep": rl_paths.EMBEDDINGS, "pretrained": B0}
    for app in apps:
        exp = json.loads(rl_paths.teacher(app).read_text())
        K = max(2, len(exp["clusters"]))
        d = OUT / app / "baselines"
        d.mkdir(parents=True, exist_ok=True)
        for tag, bank in banks.items():
            if not (bank / f"{app}.pt").is_file():
                print(f"  {app}: no {tag} bank, skipped")
                continue
            p = rl_paths.paths(app, bank)
            w, _ = _phase1_clustering_partition(app, p, K)
            h, _ = _phase1_hdbscan_partition(app, p)
            for method, parts in ((f"unixcoder_ward_{tag}", w), (f"unixcoder_hdbscan_{tag}", h)):
                (d / f"{method}{'_smoke' if smoke else ''}.json").write_text(json.dumps(
                    {"method": method, "app": app, "embeddings": str(bank.relative_to(REPO)), "K": K if "ward" in method else None,
                     "partitions": parts}, indent=2))
        for seed in seeds:
            parts = _random_partition(sorted(exp["dependency_graph"]), K, seed=seed)
            (d / f"random_s{seed}.json").write_text(json.dumps({"method": "random", "app": app, "seed": seed, "K": K,
                                                                "partitions": parts}, indent=2))
        print(f"  {app}: K={K} written to {d.relative_to(REPO)}")


def rldec(apps: list[str], seeds: list[int], python: str, jobs: int) -> None:
    """One RLDec process per (app, seed), at most `jobs` at a time. Each
    process is mostly single-core (RLlib DQN, num_workers 0), so parallel
    apps do not change any run's settings."""
    banner(f"rldec ({jobs} parallel)")
    todo = [(app, seed) for seed in seeds for app in apps
            if not (OUT / app / "baselines" / f"rldec_s{seed}.json").is_file()]
    logs = RUN / "rldec_logs"
    logs.mkdir(parents=True, exist_ok=True)
    # share the cores between the parallel processes instead of letting each
    # torch/numpy start one thread per core
    import os
    threads = str(max(1, (os.cpu_count() or jobs) // jobs))
    env = dict(os.environ, OMP_NUM_THREADS=threads, MKL_NUM_THREADS=threads, OPENBLAS_NUM_THREADS=threads)
    running: list[tuple[str, int, subprocess.Popen, float]] = []
    failed = []
    while todo or running:
        while todo and len(running) < jobs:
            app, seed = todo.pop(0)
            log = open(logs / f"{app}_s{seed}.log", "w")
            proc = subprocess.Popen([python, "-m", "java_pipeline.run_rldec", "--seed", str(seed), app],
                                    cwd=REPO, stdout=log, stderr=subprocess.STDOUT, env=env)
            running.append((app, seed, proc, time.time()))
            print(f"  started {app} s{seed} (log {log.name})", flush=True)
        time.sleep(10)
        for item in list(running):
            app, seed, proc, t0 = item
            if proc.poll() is None:
                continue
            running.remove(item)
            print(f"  {app} s{seed}: rc={proc.returncode} [{fmt(time.time() - t0)}]", flush=True)
            if proc.returncode != 0:
                failed.append((app, seed))
                continue
            f = OUT / app / "baselines" / f"rldec_s{seed}.json"
            d = json.loads(f.read_text())
            d["config_hash"], d["wall_seconds"] = config_hash(rldec_config(app, seed)), round(time.time() - t0, 1)
            f.write_text(json.dumps(d, indent=2))
    if failed:
        raise SystemExit(f"[rldec] failed: {failed}; see {logs}")


def pack() -> None:
    banner("pack")
    out = REPO / "results_java_gpu.tar.gz"
    items = ["results/_nesy"] + [f"results/{a}/baselines" for a in APPS]
    items = [i for i in items if (REPO / i).exists()]
    subprocess.run(["tar", "czf", str(out), "--exclude=*.pt.tmp", *items], cwd=REPO, check=True)
    print(f"[pack] {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--apps", nargs="+", default=APPS)
    ap.add_argument("--stages", default="check")
    ap.add_argument("--seeds", nargs="+", type=int, default=[42])
    ap.add_argument("--variants", nargs="*", default=None, help="subset of run_neurosym_ablation.VARIANTS")
    ap.add_argument("--ablations", nargs="*", default=list(ABLATIONS), help="for --stages ablation")
    ap.add_argument("--device", default=None)
    ap.add_argument("--rldec-python", default=sys.executable)
    ap.add_argument("--rldec-jobs", type=int, default=6, help="RLDec processes at a time")
    ap.add_argument("--smoke", action="store_true", help="CPU smoke test of every stage on one app")
    a = ap.parse_args()
    import torch
    device = a.device or ("cuda" if torch.cuda.is_available() else "cpu")
    if a.smoke:
        apps = a.apps if a.apps != APPS else ["jpetstore-6"]
        b0(apps, device)
        if not check(apps, B0):
            raise SystemExit(1)
        encoder(apps, smoke=True)
        rl(apps, [42], device, ["structural", "full"], smoke=True)
        baselines(apps, [42], smoke=True)
        print("\n[smoke] every stage ran; outputs under *_smoke are not results")
        return
    stages = a.stages.split(",")
    t0 = time.time()
    for s in stages:
        if s == "check" and not check(a.apps, None if (rl_paths.EMBEDDINGS / f"{a.apps[0]}.pt").is_file() else B0):
            raise SystemExit(1)
        if s == "b0":
            b0(a.apps, device)
        if s == "encoder":
            encoder(a.apps, smoke=False)
        if s == "ablation":
            for name in a.ablations:
                rl(a.apps, a.seeds, device, a.variants or ["structural", "full"], smoke=False, ablation=name)
        if s == "rl":
            rl(a.apps, a.seeds, device, a.variants, smoke=False)
        if s == "baselines":
            baselines(a.apps, a.seeds, smoke=False)
        if s == "rldec":
            rldec(a.apps, a.seeds, a.rldec_python, a.rldec_jobs)
        if s == "pack":
            pack()
    print(f"\n[run_gpu] stages {stages} done in {fmt(time.time() - t0)}")


if __name__ == "__main__":
    main()
