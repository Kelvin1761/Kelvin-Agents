"""au_walkforward_refit：合約 §8 B arm 產生器嘅不變量。"""
from copy import deepcopy
import json
from pathlib import Path
import random
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))
import au_walkforward_refit as wf  # noqa: E402
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from au_racing_engine.scoring import FEATURE_KEYS, MATRIX_WEIGHTS, compose_matrix_score  # noqa: E402

SMALL = {**wf.PROCEDURE, "warmup_days": 5, "window_days": 3, "draws": 24}


def race(day, number, rng, flat=False):
    rows = []
    for n in range(1, 9):
        features = {k: 60.0 if flat else round(rng.uniform(35, 90), 6) for k in FEATURE_KEYS}
        rows.append({"n": n, "name": f"H{day}-{number}-{n}", "features": features,
                     "wet": 0.0 if flat else round(rng.uniform(-1, 1), 4),
                     "proven_class": 0.0 if flat else round(rng.uniform(-.5, .5), 4),
                     "full_time": 0.0 if flat else round(rng.uniform(-.3, .3), 4)})
    order = list(range(1, 9))
    rng.shuffle(order)
    for row, pos in zip(rows, order):
        row["pos"] = pos
        row["ability"] = wf.exact_score(row, MATRIX_WEIGHTS)
    rows.reverse()  # dump order must not matter: loader sorts by saddlecloth
    return {"date": f"2026-08-{day:02d}", "meeting": f"M{day}", "race": number,
            "field": 8, "rows": rows}


def corpus(days=range(5, 19), flat=False, seed=3):
    rng = random.Random(seed)
    return [race(d, k, rng, flat) for d in days for k in (1, 2, 3)]


def dump(tmp_path, races, name="leaves.json"):
    path = tmp_path / name
    path.write_text(json.dumps({"races": races}))
    return path


def test_exact_score_is_production_order_and_rounding():
    row = corpus()[0]["rows"][0]
    pure = round(compose_matrix_score(map_features_to_matrix_scores(row["features"])), 4)
    expected = round(round(pure + row["wet"] + row["proven_class"], 4) + row["full_time"], 4)
    assert wf.exact_score(row, MATRIX_WEIGHTS) == expected


def test_load_clean_drops_pre_capture_era_and_bad_labels(tmp_path):
    races = corpus()
    old = deepcopy(races[0]); old["date"] = "2026-08-04"
    no_winner = deepcopy(races[1]); no_winner["meeting"] = "X"
    for r in no_winner["rows"]:
        r["pos"] = r["pos"] + 1 if r["pos"] == 1 else r["pos"]
    clean = wf.load_clean(dump(tmp_path, races + [old, no_winner]))
    assert len(clean) == len(races)
    assert all(r["date"] >= "2026-08-05" for r in clean)
    assert all([x["n"] for x in r["rows"]] == sorted(x["n"] for x in r["rows"]) for r in clean)


def test_verify_accepts_replica_and_rejects_drift(tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus()))
    assert wf.verify(races)["ok"]
    races[0]["rows"][0]["ability"] += 0.01
    assert not wf.verify(races)["ok"]


def test_each_window_only_sees_earlier_dates(monkeypatch, tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus()))
    seen = []
    real = wf.fit_window

    def spy(train, matrix, procedure):
        seen.append({r["date"] for r in train})
        return real(train, matrix, procedure)

    monkeypatch.setattr(wf, "fit_window", spy)
    windows, predictions = wf.walk_forward(races, SMALL, log=lambda *_: None)
    for w, train_dates in zip(windows, seen):
        assert max(train_dates) < min(w["test_dates"])
    dates = sorted({r["date"] for r in races})
    predicted = [p["date"] for p in predictions]
    assert sorted(set(predicted)) == dates[SMALL["warmup_days"]:]
    assert len(predictions) == sum(r["date"] >= dates[SMALL["warmup_days"]] for r in races)
    assert len(windows) == -(-(len(dates) - SMALL["warmup_days"]) // SMALL["window_days"])


def test_future_dates_cannot_change_past_predictions(tmp_path):
    short = wf.load_clean(dump(tmp_path, corpus(range(5, 15)), "a.json"))
    long = wf.load_clean(dump(tmp_path, corpus(range(5, 15)) + corpus(range(15, 19), seed=9),
                              "b.json"))
    _, a = wf.walk_forward(short, SMALL, log=lambda *_: None)
    _, b = wf.walk_forward(long, SMALL, log=lambda *_: None)
    # 最後一個短窗可能被長語料延長（尾窗），只比較兩邊都完整嘅窗口。
    complete = {p["window"] for p in a if p["window"] < max(x["window"] for x in a)}
    pa = [p for p in a if p["window"] in complete]
    assert pa and pa == [p for p in b if p["window"] in complete]


def test_flat_leaves_fall_back_to_live_weights(tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus(flat=True)))
    windows, predictions = wf.walk_forward(races, SMALL, log=lambda *_: None)
    assert all(w["fallback"] == "no_consensus" for w in windows)
    assert all(r["ability_refit"] == r["ability_live"] for p in predictions for r in p["rows"])


def test_consensus_keeps_total_and_registry_order(tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus()))
    weights, meta = wf.fit_window(races[:30], wf.Matrix(races), SMALL)
    assert list(weights) == list(MATRIX_WEIGHTS)
    assert sum(weights.values()) == pytest.approx(sum(MATRIX_WEIGHTS.values()), abs=1e-9)
    again, meta2 = wf.fit_window(races[:30], wf.Matrix(races), SMALL)
    assert (weights, meta) == (again, meta2)


def test_fit_refuses_fewer_dates_than_blocks(tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus()))
    with pytest.raises(ValueError, match="fewer dates"):
        wf.fit_window(races[:12], wf.Matrix(races), SMALL)


def test_procedure_hash_is_stable_and_sensitive():
    assert wf.procedure_hash() == wf.procedure_hash()
    assert wf.procedure_hash({**wf.PROCEDURE, "draws": 255}) != wf.procedure_hash()


def test_aa_stale_check_rejects(tmp_path):
    races = wf.load_clean(dump(tmp_path, corpus(flat=True)))
    _, predictions = wf.walk_forward(races, SMALL, log=lambda *_: None)
    result = wf.stale_check(predictions)
    assert result["verdict"]["verdict"] == "REJECT"
    assert result["counts_live"] == result["counts_refit"]
    rows = wf.arm_metric_rows(predictions, "refit")
    assert len(rows) == len(predictions) and "gold" in rows[0]
