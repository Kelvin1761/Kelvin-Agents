"""EXP-20261124-61: the frozen weekly recalibration evaluator scores what the protocol says, once."""
import importlib.util
import json
import math
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_spec = importlib.util.spec_from_file_location("nba_recal_evaluate", REPO / "docs/experiments/patches/nba_recal_forward/evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def _write(path, rows):
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _model(player, line, pf, *, role="production", at="2026-11-25T10:00:00+00:00", mid=ev.MS_ID, post=False):
    return {"row_type": "model_obs", "game_tag": "X_Y", "player": player, "market": "reb", "line": line,
            "p_final": pf, "price_at_model": 1.6, "post_tip": post, "snapshot_role": role, "recorded_at": at,
            "probability_model_id": mid}


def _settle(player, line, y, outcome="hit"):
    return {"row_type": "settlement", "game_tag": "X_Y", "player": player, "market": "reb", "line": line,
            "y": y, "outcome": outcome}


def test_day_legs_takes_first_pre_tip_production_obs_with_a_result(tmp_path):
    p = tmp_path / "2026-11-25.jsonl"
    _write(p, [_model("A", 6.0, 0.7), _model("A", 6.0, 0.1, at="2026-11-25T20:00:00+00:00"),
               _model("B", 6.0, 0.7, role="final_refresh"), _model("C", 6.0, 0.7, post=True),
               _model("D", 6.0, 0.7), _model("E", 6.0, 0.7),
               _settle("A", 6.0, 1), _settle("B", 6.0, 1), _settle("C", 6.0, 1), _settle("D", 6.0, 0, "void")])
    legs = ev.day_legs(p)
    assert [(x["pf"], x["y"]) for x in legs] == [(0.7, 1)]
    assert abs(legs[0]["m"] - 1 / 1.6) < 1e-12 and legs[0]["d"] == "2026-11-25"


def test_frozen_coefficients_are_the_protocols():
    assert ev.FROZEN_R2F == [-0.130982, -0.190218, -0.132677, -0.021445, 0.028416, 0.94972, -0.059996]
    leg = {"s": "pts", "pf": 0.6, "m": 0.55}
    lf, lm = math.log(0.6 / 0.4), math.log(0.55 / 0.45)
    w = ev.FROZEN_R2F
    z = w[0] + w[4] * lf + w[5] * lm + w[6] * lm * lm
    assert abs(ev.predict(leg, w, "R2") - 1 / (1 + math.exp(-z))) < 1e-12


def test_monday_and_weekly_fit_uses_only_earlier_weeks():
    assert ev.monday("2026-11-25") == "2026-11-23" and ev.monday("2026-11-29") == "2026-11-23"
    assert ev.monday("2026-11-30") == "2026-11-30"
    rnd = random.Random(1)
    hist = [{"d": "2026-11-10", "s": "reb", "pf": p, "m": p, "y": int(rnd.random() < p), "id": ev.MS_ID}
            for p in (rnd.uniform(0.1, 0.9) for _ in range(400))]
    fwd = [{"d": "2026-11-25", "s": "reb", "pf": 0.5, "m": 0.5, "y": 1, "id": ev.MS_ID}]
    # a same-week leg with an absurd label must not change the forecast for its own week
    poison = [{"d": "2026-11-24", "s": "reb", "pf": 0.5, "m": 0.5, "y": 1, "id": ev.MS_ID}] * 300
    a = ev.score(hist + fwd, fwd)[0]["rw"]
    b = ev.score(hist + poison + fwd, fwd)[0]["rw"]
    assert a == b


def test_population_stops_when_the_model_changes():
    rows = [{"d": d, "s": "reb", "pf": 0.5, "m": 0.5, "y": 1, "id": mid}
            for d, mid in (("2026-11-24", ev.MS_ID), ("2026-11-25", ev.MS_ID), ("2026-11-26", "other"),
                           ("2026-11-27", ev.MS_ID))]
    fwd, stop = ev.forward(rows)
    assert stop == "2026-11-26" and [r["d"] for r in fwd] == ["2026-11-25"]


def test_checkpoint_cut_and_frozen_result(tmp_path):
    rnd = random.Random(2)
    rows = []
    for i in range(20):
        d = f"2026-11-{5 + i:02d}" if i < 20 else None
        for _ in range(60):
            p = rnd.uniform(0.05, 0.95)
            rows.append({"d": d, "s": rnd.choice(ev.STATS), "pf": p, "m": p, "y": int(rnd.random() < p), "id": ev.MS_ID})
    for i in range(16):  # forward days 11-25..12-10
        d = (ev.date(2026, 11, 25) + ev.timedelta(days=i)).isoformat()
        for _ in range(800):
            p = rnd.uniform(0.05, 0.95)
            rows.append({"d": d, "s": rnd.choice(ev.STATS), "pf": p, "m": p, "y": int(rnd.random() < p), "id": ev.MS_ID})
    st = ev.status(rows=rows)["RC"]
    assert st["days"] == 16 and st["ready"] is True
    out = ev.evaluate(out_dir=tmp_path, rows=rows)["RC"]
    assert out["days"] == 14 and out["n_legs"] == 14 * 800 and out["complete"] is True
    assert set(out["secondary"]) == {"r2f", "r1w", "mkt", "rw_minus_mkt"}
    assert ev.evaluate(out_dir=tmp_path, rows=[])["RC"] == out  # frozen: judged once


def test_not_ready_and_dashboard_without_forward_data(tmp_path):
    rows = [{"d": "2026-11-20", "s": "reb", "pf": 0.5, "m": 0.5, "y": 1, "id": ev.MS_ID}]
    assert ev.evaluate(out_dir=tmp_path, rows=rows)["RC"]["status"] == "not_ready"
    view = ev.dashboard(rows=rows)
    assert view["progress"]["days"] == 0 and "calibration" not in view
