"""B2B: was true for every team every day (any historical PPG drop counted)."""
from __future__ import annotations

import sys
from pathlib import Path

NBA = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA))
sys.path.insert(0, str(NBA / "nba_data_extractor/scripts"))
sys.path.insert(0, str(NBA / "nba_wong_choi/scripts"))
import generate_nba_reports as reports  # noqa: E402
import nba_extractor as x  # noqa: E402

LATE_WEST_COAST_TIP = "2026-10-22T02:00Z"  # 7pm PT on Oct 21


def test_local_game_date_uses_us_date_not_utc():
    assert x.nba_local_game_date(LATE_WEST_COAST_TIP) == "2026-10-21"
    assert x.nba_local_game_date("2026-10-21T23:00Z") == "2026-10-21"   # 7pm ET
    assert x.nba_local_game_date("2026-10-22") == "2026-10-22"          # plain date untouched
    assert x.nba_local_game_date(None) == ""


def test_back_to_back_detected_for_late_west_coast_game():
    # last game Oct 20 (US), today's game Oct 21 (US) = B2B. Raw UTC date (10-22) said 2 days.
    info = x.compute_rest_info({"l10_dates": ["OCT 20, 2026"]}, LATE_WEST_COAST_TIP)
    assert info["is_b2b"] is True and info["rest_known"] is True


def test_not_b2b_after_a_real_rest_and_unknown_when_no_log():
    assert x.compute_rest_info({"l10_dates": ["APR 12, 2026"]}, "2026-10-22T00:00Z")["is_b2b"] is False
    unknown = x.compute_rest_info({"l10_dates": []}, "2026-10-22T00:00Z")
    assert unknown["is_b2b"] is False and unknown["rest_known"] is False


def test_fatigue_dict_exists_without_rest_splits():
    out = x.compute_fatigue_adjustment({}, {"l10_dates": ["OCT 20, 2026"]}, LATE_WEST_COAST_TIP)
    assert out and out["is_b2b"] is True and out["fatigue_pct"] == 0 and out["warning"] == ""
    assert x.compute_fatigue_adjustment({}, {"l10_dates": []}, LATE_WEST_COAST_TIP) is None


def _player(is_b2b, fatigue_pct=8.0, known=True):
    return {"fatigue": {"is_b2b": is_b2b, "fatigue_pct": fatigue_pct, "warning": "x", "rest_known": known}}


def test_team_flag_ignores_historical_fatigue_and_needs_majority():
    players = {
        "AAA": [_player(False) for _ in range(12)],                       # all have a past PPG drop; none on B2B
        "BBB": [_player(True) for _ in range(7)] + [_player(False) for _ in range(5)],
        "CCC": [_player(True, known=False) for _ in range(5)],            # unknown rest never counts
        "DDD": [],
    }
    out = reports.detect_team_b2b(players, ["AAA", "BBB", "CCC", "DDD"])
    assert out == {"AAA": False, "BBB": True, "CCC": False, "DDD": False}
