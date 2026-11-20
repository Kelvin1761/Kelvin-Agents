"""EXP-20261120-60: the frozen 大細盤精選 v2 paper arm picks and settles what the protocol says."""
import importlib.util
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_spec = importlib.util.spec_from_file_location("nba_featured_v2_evaluate", REPO / "docs/experiments/patches/nba_featured_v2/evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nba_forward_tracker as tracker  # noqa: E402

SEEN = "2026-11-21T10:00:00+00:00"


def _model(player, line, p, market="pts", game="X_Y", role="production", at=SEEN):
    return {"row_type": "model_obs", "target_date": "2026-11-21", "game_tag": game, "player": player, "market": market,
            "line": line, "p_final": p, "post_tip": False, "snapshot_role": role, "recorded_at": at, "odds_captured_at": SEEN}


def _price(player, ou, over, under, market="pts", game="X_Y", at="2026-11-21T09:00:00+00:00"):
    return {"row_type": "price_obs", "price_source": "ou_two_way", "game_tag": game, "player": player, "market": market,
            "ou_line": ou, "side": "over", "price": over, "complement_price": under, "captured_at": at,
            "post_tip": False, "tip_unknown": False}


def _settle(player, actual, market="pts", game="X_Y", outcome="hit"):
    return {"row_type": "settlement", "game_tag": game, "player": player, "market": market, "actual": actual, "outcome": outcome}


def test_bias_correction_matches_the_frozen_formula():
    p = 0.45
    z = math.log(p / (1 - p)) + ev.DELTA["pts"]
    assert abs(ev.p_over("pts", p) - 1 / (1 + math.exp(-z))) < 1e-12
    assert ev.p_over("pts", 0.45) > 0.45 and ev.MIN_EDGE == 0.03 and ev.LOOKS == {"V2_250": 250, "V2_600": 600}


def test_v2_can_pick_an_over_skips_low_lines_and_takes_one_bet_per_game():
    rows = [
        _model("A", 20.0, 0.50), _price("A", 19.5, 1.95, 1.85), _settle("A", 24),        # corrected 59.6% vs fair 48.7% -> over
        _model("B", 15.0, 0.36), _price("B", 14.5, 1.90, 1.90), _settle("B", 10),        # under edge 4.6pp < A, same game
        _model("C", 2.0, 0.20, market="ast", game="Z_W"), _price("C", 1.5, 1.90, 1.90, market="ast", game="Z_W"),  # line 1.5: skipped
        _price("A", 19.5, 1.20, 4.00, at="2026-11-21T11:00:00+00:00"),                    # after the model saw prices: ignored
    ]
    picks = ev.day_picks(rows)
    assert [(p["player"], p["side"], p["odds"], p["state"], p["profit"]) for p in picks] == [("A", "over", 1.95, "won", 0.95)]


def test_void_is_no_bet_and_results_freeze(tmp_path):
    rows = [_model("A", 20.0, 0.50), _price("A", 19.5, 1.95, 1.85), _settle("A", None, outcome="void")]
    assert ev.day_picks(rows)[0]["state"] == "void"
    done = [{"day": f"2026-11-{21 + i % 9:02d}", "id": f"{i:04d}", "side": "over", "odds": 2.0,
             "state": "won" if i % 2 else "lost", "profit": 1.0 if i % 2 else -1.0} for i in range(700)]
    out = ev.evaluate(out_dir=tmp_path, rows=done)
    assert out["V2_250"]["pass"] is False and out["V2_600"]["n_bets"] == 600
    assert ev.evaluate(out_dir=tmp_path, rows=[]) == out
    line = tracker._numbers(next(t for t in tracker.FORWARD_TESTS if t.test == "V2_600"), out["V2_600"])
    assert "600 注" in line
