"""java_pipeline.metrics must reproduce the code and the table it claims to.

  * preset "evaluate"  == evaluate.py on random weighted graphs, partial partitions
  * preset "rldec"     == decomp-rldec/rldec/metrics (imported read-only)
  * eq5 as_written     == evaluate.compute_weerasinghe_scores
  * eq5 as_published   reproduces all 35 Score cells of Weerasinghe Table 1

Run: python3 -m pytest tests/test_metrics.py -q
"""
import os
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
RLDEC = Path(os.environ.get("BASELINES_DIR", REPO.parent)) / "decomp-rldec"   # scripts/fetch_baselines.sh
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "results" / "recon"))

from vendor.ror_msi import evaluate  # noqa: E402
from java_pipeline import metrics as M  # noqa: E402

SEEDS = range(200)


def _random_case(seed, n_max=40, weighted=True):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(3, n_max))
    density = rng.uniform(0.05, 0.5)
    A = (rng.random((n, n)) < density) * (rng.random((n, n)) * 3 if weighted
                                          else rng.integers(1, 6, (n, n)))
    k = int(rng.integers(1, min(n, 8) + 1))
    labels = rng.integers(0, k, n)
    labels[rng.random(n) < 0.1] = -1          # some unassigned classes
    if (labels == -1).all():
        labels[0] = 0
    return A, labels


def _to_dicts(A, labels):
    names = [f"c{i}" for i in range(len(labels))]
    graph = {names[i]: {names[j]: float(A[i, j]) for j in np.nonzero(A[i])[0]}
             for i in range(len(names))}
    parts = {}
    for i, l in enumerate(labels):
        if l != -1:
            parts.setdefault(int(l), []).append(names[i])
    return graph, [parts[k] for k in sorted(parts)]


@pytest.mark.parametrize("seed", SEEDS)
def test_evaluate_preset_matches_evaluate_py(seed):
    A, labels = _random_case(seed)
    graph, parts = _to_dicts(A, labels)
    got = M.compute(A, labels, "evaluate")
    assert got["SM"] == pytest.approx(evaluate.compute_sm(parts, graph), abs=1e-12)
    assert got["IFN"] == pytest.approx(evaluate.compute_ifn(parts, graph), abs=1e-12)
    assert got["ICP"] == pytest.approx(evaluate.compute_icp(parts, graph), abs=1e-12)
    assert got["NED"] == pytest.approx(evaluate.compute_ned(parts), abs=1e-12)


def test_from_graph_round_trip():
    A, labels = _random_case(7)
    graph, parts = _to_dicts(A, labels)
    A2, l2, nodes = M.from_graph(graph, parts, nodes=[f"c{i}" for i in range(len(labels))])
    assert np.allclose(A2, A)
    # cluster ids are renumbered by _to_dicts; compare the grouping, not the ids
    same = lambda l: {(i, j) for i in range(len(l)) for j in range(len(l)) if l[i] == l[j] != -1}
    assert same(l2) == same(labels) and ((l2 == -1) == (labels == -1)).all()


@pytest.fixture(scope="module")
def rldec_metrics():
    if not RLDEC.is_dir():
        pytest.skip("decomp-rldec not present")
    sys.path.insert(0, str(RLDEC))
    from rldec import metrics as R
    return R


@pytest.mark.parametrize("seed", SEEDS)
def test_rldec_preset_matches_rldec_code(seed, rldec_metrics):
    R = rldec_metrics
    A, labels = _random_case(seed, weighted=False)   # RLDec works on counts
    got = M.compute(A, labels, "rldec")
    assert got["SM"] == pytest.approx(R.vectorized_modularity(labels, A, True), abs=1e-12)
    assert got["IFN"] == pytest.approx(R.interface_number(labels, A, True), abs=1e-12)
    assert got["ICP"] == pytest.approx(R.inter_call_percentage(labels, A, True), abs=1e-12)
    assert got["NED"] == pytest.approx(R.non_extreme_distribution(labels, exclude_outliers=True),
                                       abs=1e-12)


def test_eq5_as_written_matches_evaluate_py():
    rng = np.random.default_rng(0)
    pool = {f"t{i}": {m: float(rng.random()) for m in ("SM", "IFN", "ICP", "NED")}
            for i in range(9)}
    ours = M.eq5_scores(pool, "as_written")
    ref = evaluate.compute_weerasinghe_scores(pool)
    for t in pool:
        assert ours[t] == pytest.approx(ref[t], abs=1e-12)


def test_eq5_as_published_reproduces_weerasinghe_table1():
    from eq5_reproduce import TABLE1
    hits = total = 0
    for rows in TABLE1.values():
        pool = {t: dict(zip(("SM", "IFN", "ICP", "NED"), v[:4])) for t, v in rows.items()}
        s = M.eq5_scores(pool, "as_published")
        for t, v in rows.items():
            hits += round(s[t], 2) == round(v[4], 2)
            total += 1
    assert (hits, total) == (35, 35)
