"""EXP-20261110-03: the frozen under-arm evaluator reads the ledger the way the protocol says."""
import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
_spec = importlib.util.spec_from_file_location("nba_under_evaluate", REPO / "docs/experiments/patches/nba_under/evaluate.py")
ev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ev)


def _model(line, p, l10, role="production", seen="2026-11-10T10:00:00+00:00", player="A"):
    return {"row_type": "model_obs", "target_date": "2026-11-11", "game_tag": "X_Y", "player": player,
            "market": "pts", "line": line, "p_final": p, "post_tip": False, "snapshot_role": role,
            "recorded_at": "2026-11-10T10:01:00+00:00", "odds_captured_at": seen,
            "prop_training": {"inputs": {"l10_values": l10}}}


def _price(ou, over, under, at, player="A"):
    return {"row_type": "price_obs", "price_source": "ou_two_way", "game_tag": "X_Y", "player": player,
            "market": "pts", "ou_line": ou, "line": ou + 0.5, "side": "over", "price": over,
            "complement_price": under, "captured_at": at, "post_tip": False, "tip_unknown": False}


def _settle(actual, outcome="miss", player="A"):
    return {"row_type": "settlement", "game_tag": "X_Y", "player": player, "market": "pts",
            "line": 20.0, "actual": actual, "outcome": outcome}


def test_arms_price_and_settlement_follow_the_protocol():
    rows = [
        _model(20.0, 0.40, [15] * 10),                               # avg 15 vs 19.5 -> FU_AVG; fair .5 - .40 -> FU_EDGE
        _price(19.5, 1.90, 1.90, "2026-11-10T09:00:00+00:00"),
        _price(19.5, 1.50, 2.60, "2026-11-10T12:00:00+00:00"),       # after the model's odds: never used
        _settle(18),
        _model(10.0, 0.50, [10] * 10, player="B"),                   # neither arm
        _price(9.5, 1.90, 1.90, "2026-11-10T09:00:00+00:00", player="B"),
        _model(30.0, 0.30, [20] * 4, role="warmup", player="C"),     # not a production row
        _price(29.5, 1.90, 1.90, "2026-11-10T09:00:00+00:00", player="C"),
    ]
    bets = ev.day_bets(rows)
    assert [(b["id"], b["arms"], b["odds"], b["state"]) for b in bets] == [
        ("X_Y|A|pts|19.5", ["FU_AVG", "FU_EDGE"], 1.90, "won")]


def test_void_and_unsettled_bets_never_count():
    base = [_model(20.0, 0.40, [15] * 10), _price(19.5, 1.90, 1.90, "2026-11-10T09:00:00+00:00")]
    assert ev.day_bets(base)[0]["state"] == "pending"
    assert ev.day_bets(base + [_settle(None, "void")])[0]["state"] == "void"
    assert ev.day_bets(base + [_settle(25)])[0]["state"] == "lost"
    assert ev.status(rows=ev.day_bets(base))["FU_AVG"] == {"bets": 0, "checkpoint": {"bets": 1200}, "ready": False}


def test_judge_uses_exactly_the_first_n_and_a_wider_than_95_interval(tmp_path):
    rows = [{"day": f"2026-11-{11 + i % 15:02d}", "id": f"{i:04d}", "arms": ["FU_EDGE"], "odds": 1.9,
             "state": "won" if i % 2 else "lost"} for i in range(400)]
    out = ev.evaluate(out_dir=tmp_path, rows=rows, only="FU_EDGE")["FU_EDGE"]
    assert out["n_bets"] == 300 and out["ci_level"] == 0.975 and out["pass"] is False
    assert ev.evaluate(out_dir=tmp_path, rows=[], only="FU_EDGE")["FU_EDGE"] == out   # frozen
