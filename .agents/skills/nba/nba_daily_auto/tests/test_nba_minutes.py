"""Minutes model v2 features (EXP-20261111-03): strictly as-of and the frozen population."""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import nba_minutes as M  # noqa: E402
from nba_engine import model  # noqa: E402


def _game(day, eid, minutes, starters=(), team="AAA", opp="BBB"):
    players = [{"espn_id": pid, "team": team, "MIN": m} for pid, m in minutes.items()]
    return {"date": day, "event_id": eid, "teams": {team: {}, opp: {}}, "players": players, "_starters": set(starters)}


def test_features_use_only_games_before_the_day_and_count_absences():
    games = [_game(f"2026-11-0{i}", str(i), {"p1": 30.0 + i, "p2": 20.0, "p3": 25.0}, starters=("p1",)) for i in range(1, 7)]
    games.append(_game("2026-11-07", "7", {"p1": 36.0, "p2": 22.0}, starters=("p1",)))      # p3 missed the last game
    games.append(_game("2026-11-08", "8", {"p1": 99.0}, starters=("p1",)))                # the game day itself: never read
    f = M.team_features(games, "AAA", date(2026, 11, 8), lambda g: g["_starters"])
    assert f["p1"]["m_last"] == 36.0 and f["p1"]["games"] == 7 and f["p1"]["started_prev"] is True
    assert f["p1"]["rest"] == 1 and f["p1"]["pool_prev"] == 25.0
    assert f["p3"]["missed_prev"] is True and f["p3"]["gap_last"] == 2
    assert f["p2"]["start_share"] == 0.0


def test_ratio_is_none_outside_the_fitted_population_and_clipped_inside():
    coef = model.config()["minutes_v2"]["coefficients"]
    assert len(coef) == len(M.FEATURE_NAMES)
    base = {"m_hl": 30.0, "m_season": 30.0, "m_l10": 30.0, "m_last": 30.0, "games": 8, "started_prev": True,
            "start_share": 1.0, "rest": 2, "gap_last": 2, "missed_prev": False, "pool_prev": 0.0}
    assert M.minutes_ratio({**base, "games": 4}, 3.0, True, coef) is None
    assert M.minutes_ratio({**base, "m_hl": 12.0}, 3.0, True, coef) is None
    assert M.minutes_ratio(base, None, True, coef) is None
    close, blowout = M.minutes_ratio(base, 2.0, True, coef), M.minutes_ratio(base, 15.0, True, coef)
    assert 0.5 <= blowout < close <= 1.6                       # a starter loses minutes in a lopsided game
    rested = M.minutes_ratio({**base, "gap_last": 10}, 2.0, True, coef)
    assert rested < close                                       # back from more than a week out
