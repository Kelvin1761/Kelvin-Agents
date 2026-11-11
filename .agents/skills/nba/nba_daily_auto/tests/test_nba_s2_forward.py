"""EXP-20261111-05: the frozen S2 blend evaluator scores what the protocol says, once."""
import importlib.util
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_spec = importlib.util.spec_from_file_location("nba_s2_evaluate", REPO / "docs/experiments/patches/nba_s2_forward/evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_forward_tracker as tracker  # noqa: E402


def _model(player, line, p_s2, role="production", at="2026-11-12T10:00:00+00:00"):
    return {"row_type": "model_obs", "target_date": "2026-11-13", "game_tag": "X_Y", "player": player, "market": "reb",
            "line": line, "p_final": 0.6, "p_s": 0.55, "p_s2": p_s2, "price_at_model": 1.6, "post_tip": False,
            "snapshot_role": role, "recorded_at": at}


def test_blend_matches_the_frozen_formula():
    c = ev.BLENDS["MS2"]
    z = c["intercepts"]["REB"] + c["beta"] * math.log((1 / 1.6) / (1 - 1 / 1.6)) + c["gamma"] * math.log(0.7 / 0.3)
    assert abs(ev.blend("MS2", "REB", 1.6, 0.7) - 1 / (1 + math.exp(-z))) < 1e-12


def test_only_first_production_legs_with_s2_and_a_result_are_scored():
    rows = [_model("A", 6.0, 0.7), _model("A", 6.0, 0.1, at="2026-11-12T20:00:00+00:00"),
            _model("B", 6.0, None), _model("C", 6.0, 0.7, role="final_refresh"), _model("D", 6.0, 0.7),
            {"row_type": "settlement", "game_tag": "X_Y", "player": "A", "market": "reb", "line": 6.0, "y": 1},
            {"row_type": "settlement", "game_tag": "X_Y", "player": "B", "market": "reb", "line": 6.0, "y": 1},
            {"row_type": "settlement", "game_tag": "X_Y", "player": "C", "market": "reb", "line": 6.0, "y": 1}]
    legs = ev.day_legs(rows)
    assert len(legs) == 1 and abs(legs[0]["s2"] - (-math.log(0.7))) < 1e-12


def test_checkpoint_and_frozen_result(tmp_path):
    legs = [{"day": f"2026-11-{12 + i:02d}", "stat": "REB", "pub": 0.50, "ms2": 0.49, "msr": 0.495, "s": 0.52, "s2": 0.51}
            for i in range(14) for _ in range(800)]
    assert ev.status(legs=legs[:800 * 10])["S2"]["ready"] is False
    out = ev.evaluate(out_dir=tmp_path, legs=legs)["S2"]
    assert out["n_legs"] == 11200 and out["days"] == 14 and out["pass"] is True
    assert abs(out["primary_delta"] + 0.01) < 1e-9 and abs(out["ms2_vs_msr"]["delta"] + 0.005) < 1e-9
    assert ev.evaluate(out_dir=tmp_path, legs=[])["S2"] == out
    line = tracker._numbers(next(t for t in tracker.FORWARD_TESTS if t.test == "S2"), out)
    assert "11200 腿、14 日" in line and "差 -0.0100" in line
