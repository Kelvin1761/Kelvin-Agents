"""EXP-20261111-01: the frozen pick-penalty evaluator builds its two groups as the protocol says."""
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_spec = importlib.util.spec_from_file_location("nba_pick_penalty_evaluate", REPO / "docs/experiments/patches/nba_pick_penalty/evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_forward_tracker as tracker  # noqa: E402


def _model(player, line, p=0.7, price=1.3, h10=0.9, h5=0.8, role="production", at="2026-11-11T10:00:00+00:00"):
    return {"row_type": "model_obs", "target_date": "2026-11-12", "game_tag": "X_Y", "player": player,
            "market": "reb", "line": line, "p_final": p, "price_at_model": price, "post_tip": False,
            "snapshot_role": role, "recorded_at": at, "prop_training": {"inputs": {"hit_l10": h10, "hit_l5": h5}}}


def _settle(player, line, actual):
    return {"row_type": "settlement", "game_tag": "X_Y", "player": player, "market": "reb", "line": line,
            "actual": actual, "outcome": "void" if actual is None else "hit" if actual >= line else "miss",
            "y": None if actual is None else int(actual >= line)}


def _banker(legs, at="2026-11-11T10:00:00+00:00", combo="1", role="production"):
    return {"row_type": "sgm_obs", "target_date": "2026-11-12", "game_tag": "X_Y", "combo_id": combo,
            "snapshot_role": role, "post_tip": False, "recorded_at": at,
            "legs": [{"player": p, "market": "reb", "line": line, "p_final": prob} for p, line, prob in legs]}


def test_groups_follow_the_protocol():
    rows = [
        _banker([("A", 6.0, 0.75)]),
        _banker([("Z", 6.0, 0.75)], at="2026-11-11T19:00:00+00:00"),      # a later run is not the 21:00 banker
        _banker([("Q", 6.0, 0.75)], combo="2"),                           # not the banker
        _model("A", 6.0), _settle("A", 6.0, 5),                           # picked, missed by exactly one
        _model("B", 4.0), _model("B", 6.0), _settle("B", 4.0, 9), _settle("B", 6.0, 9),   # control: highest line only
        _model("C", 6.0, h10=0.7), _settle("C", 6.0, 9),                  # L10 too low
        _model("D", 6.0, price=1.9), _settle("D", 6.0, 9),                # price outside the band
        _model("E", 6.0), _settle("E", 6.0, None),                        # void
        _model("F", 6.0, role="warmup"), _settle("F", 6.0, 9),            # not a production row
    ]
    legs = ev.day_legs(rows)
    assert [(x["group"], x["p"], x["y"], x["near_miss"]) for x in legs] == [
        ("control", 0.7, 1, False), ("picked", 0.75, 0, True)]


def test_checkpoint_needs_both_legs_and_days_and_the_result_is_frozen(tmp_path):
    def day(i, n_picked, y):
        d = f"2026-{11 + (11 + i) // 31:02d}-{(11 + i) % 30 + 1:02d}"
        return ([{"day": d, "group": "picked", "market": "reb", "p": 0.8, "y": y, "near_miss": not y}] * n_picked
                + [{"day": d, "group": "control", "market": "reb", "p": 0.7, "y": 1, "near_miss": False}] * 5)
    few_days = [x for i in range(10) for x in day(i, 50, 0)]
    assert ev.status(legs=few_days)["P"]["ready"] is False             # 500 legs but only 10 days
    assert ev.evaluate(out_dir=tmp_path, legs=few_days)["P"]["status"] == "not_ready"
    enough = [x for i in range(25) for x in day(i, 20, 0)]
    state = ev.status(legs=enough)["P"]
    assert state["ready"] and state["days"] == 20 and state["flagged_legs"] == 400   # stops at the checkpoint day
    out = ev.evaluate(out_dir=tmp_path, legs=enough)["P"]
    assert out["n_flagged"] == 400 and out["pass"] is True and out["ci95"][1] < 0
    assert abs(out["primary_delta_resid"] - (-0.8 - 0.3)) < 1e-9
    assert ev.evaluate(out_dir=tmp_path, legs=[])["P"] == out
    line = tracker._numbers(next(t for t in tracker.FORWARD_TESTS if t.test == "P"), out)
    assert "揀中 400 腿" in line and "差一 100.0%" in line
