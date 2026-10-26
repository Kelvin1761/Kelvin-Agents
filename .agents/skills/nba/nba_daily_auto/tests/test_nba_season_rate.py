"""Season-rate model S is SHADOW ONLY: correct formula, isolated, changes no pick."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest
from scipy.stats import nbinom

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_data_extractor' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_daily_auto'))
import generate_nba_reports as reports
import nba_extractor as x
import nba_market_ledger as ledger
import nba_season_rate as S

KEYS = {"season_rate_prob_S", "season_rate_version", "season_rate_status", "season_rate_inputs",
        *reports.V2_SHADOW_KEYS, *reports.V3_SHADOW_KEYS, *reports.V4_SHADOW_KEYS}


def log(pts, mins=None, kinds=None):
    n = len(pts)
    dates = [f"2026-{12 - i // 28:02d}-{28 - i % 28:02d}" for i in range(n)]  # strictly newest-first
    return {"dates": dates, "seasons": ["2026-27"] * n,
            "season_types": kinds or ["Regular Season"] * n,
            "MIN": mins or [30.0] * n, "PTS": pts, "REB": [5.0] * n, "AST": [4.0] * n,
            "FG3M": [2.0] * n, "FGA": [15.0] * n, "FG3A": [5.0] * n, "FTA": [4.0] * n,
            "FGM": [7.0] * n, "FTM": [3.0] * n}


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("NBA_SEASON_RATE_SHADOW_ENABLED", raising=False)
    reports.reset_fit_status()
    reports.reset_ml_status("legacy")


def test_constant_player_matches_nb_with_frozen_dispersion():
    p, status, inputs = S.season_rate_prob(log([20.0] * 30), "PTS", 20)
    assert status == "ok" and inputs["mu"] == 20.0
    k = S.DISPERSION_K["PTS"]
    assert p == round(float(nbinom.sf(19, k, k / (k + 20.0))), 4)


def test_recent_games_weigh_more_and_probability_falls_with_line():
    rising, _, _ = S.season_rate_prob(log([30.0] * 15 + [15.0] * 15), "PTS", 20)
    falling, _, _ = S.season_rate_prob(log([15.0] * 15 + [30.0] * 15), "PTS", 20)
    assert rising > falling
    ladder = [S.season_rate_prob(log([20.0] * 30), "PTS", line)[0] for line in (10, 15, 20, 25, 30)]
    assert ladder == sorted(ladder, reverse=True)


def test_guards_short_preseason_dnp_and_bad_inputs():
    assert S.season_rate_prob(log([20.0] * 4), "PTS", 20)[1] == "insufficient_games"
    pre = log([20.0] * 8, kinds=["Pre Season"] * 4 + ["Regular Season"] * 4)
    assert S.season_rate_prob(pre, "PTS", 20)[1] == "insufficient_games"
    dnp = log([0.0] * 3 + [20.0] * 4, mins=[0.0] * 3 + [30.0] * 4)
    assert S.season_rate_prob(dnp, "PTS", 20)[1] == "insufficient_games"
    assert S.season_rate_prob(None, "PTS", 20)[1] == "no_season_log"
    assert S.season_rate_prob(log([20.0] * 10), "STL", 2)[1] == "stat_unsupported"
    assert S.season_rate_prob(log([20.0] * 10), "PTS", 19.5)[1] == "invalid_inputs"
    unordered = log([20.0] * 10); unordered["dates"] = list(reversed(unordered["dates"]))
    assert S.season_rate_prob(unordered, "PTS", 20)[1] == "invalid_inputs"


def test_extractor_keeps_every_fetched_game_newest_first():
    rows = [{"GAME_DATE": f"OCT {28 - i}, 2026", "_season": "2026-27", "_season_type": "Regular Season",
             "MIN": 30, "PTS": 20 + i, "REB": 5, "AST": 4, "FG3M": 2, "FGA": 15, "FG3A": 5, "FTA": 4}
            for i in range(14)]
    for row in rows:
        row.update(FGM=6, FTM=3)
    assert "teams" not in x.compact_season_log(pd.DataFrame(rows))      # no MATCHUP column: no guessing
    for i, row in enumerate(rows):
        row["MATCHUP"] = "PHI vs. BOS" if i < 3 else "LAL @ GSW"
    out = x.compact_season_log(pd.DataFrame(rows))
    assert out["FGM"][0] == 6.0 and out["FTM"][0] == 3.0
    assert out["teams"][:4] == ["PHI", "PHI", "PHI", "LAL"]
    assert len(out["dates"]) == 14 and out["dates"][0] == "2026-10-28" and out["PTS"][-1] == 33.0
    assert "error" in x.compact_season_log(pd.DataFrame([{"a": 1}]))


def card_for(ext):
    return reports.build_player_card(
        "Test Star", "DET", {"lines": {"20": "1.80", "25": "2.60"}}, ext, "points",
        opponent_abbr="BOS", team_stats={}, engine_mode="legacy")


def test_card_identical_with_shadow_on_and_off(monkeypatch):
    pts = [22.0, 25, 18, 24, 21, 26, 19, 23, 20, 27, 22, 24]
    ext = {"name": "Test Star", "position": "G",
           "gamelog": {"PTS": pts[:10], "MIN": [32] * 10, "season_log": log(pts)}}
    on = card_for(ext)["line_analysis"]
    monkeypatch.setenv("NBA_SEASON_RATE_SHADOW_ENABLED", "0")
    off = card_for(ext)["line_analysis"]
    strip = lambda d: {k: v for k, v in d.items() if k not in KEYS}
    assert all(strip(on[k]) == strip(off[k]) for k in on)
    assert all(v["season_rate_prob_S"] is not None and v["season_rate_status"] == "ok" for v in on.values())
    assert all(v["season_rate_status"] == "disabled" for v in off.values())


def test_module_failure_is_isolated(monkeypatch):
    monkeypatch.setattr(S, "season_rate_prob", lambda *a: 1 / 0)
    out = reports.compute_season_rate({"gamelog": {"season_log": log([20.0] * 10)}}, "PTS", 20)
    assert out["season_rate_status"] == "error" and out["season_rate_prob_S"] is None


def test_ledger_variants_untouched():
    assert not any("season_rate" in name for name in ledger.MODEL_VARIANTS)


OPP = {"status": "available", "league_avg": {"PTS": 112.0, "REB": 44.0, "AST": 26.0, "FG3M": 13.0},
       "allowed": {"dates": ["2026-12-01"] * 0, "PTS": [], "REB": [], "AST": [], "FG3M": []}}


def test_v2_matches_hand_computation_for_a_constant_player():
    # 30 identical games: rates are exact, no opponent games -> factor 1.
    p, status, inputs = S.season_rate_prob_v2(log([20.0] * 30), "REB", 6, OPP)
    assert status == "ok" and inputs["opp_factor"] == 1.0 and inputs["mu"] == 5.0
    k = S.DISPERSION_K["REB"] * 1.6
    assert p == round(float(nbinom.sf(5, k, k / (k + 5.0))), 4)
    # PTS from shots: 30 min x (8 two-att x .5 x2 ... ) with shrunk efficiencies
    p_pts, _, i_pts = S.season_rate_prob_v2(log([20.0] * 30), "PTS", 20, OPP)
    e2 = (5 * 30 + 0.54 * 100) / (10 * 30 + 100)
    e3 = (2 * 30 + 0.36 * 100) / (5 * 30 + 100)
    eft = (3 * 30 + 0.78 * 50) / (4 * 30 + 50)
    assert abs(i_pts["mu"] - round(10 * e2 * 2 + 5 * e3 * 3 + 4 * eft, 3)) < 1e-3


def test_v2_opponent_factor_shrinks_and_requires_context():
    soft = dict(OPP, allowed={"dates": ["d"] * 10, "PTS": [], "REB": [55.0] * 10, "AST": [], "FG3M": []})
    _, _, inputs = S.season_rate_prob_v2(log([20.0] * 30), "REB", 6, soft)
    assert inputs["opp_factor"] == round(((550 + 10 * 44) / 20) / 44, 4)   # half-way to 55/44
    assert S.season_rate_prob_v2(log([20.0] * 30), "REB", 6, None)[1] == "no_opponent_context"
    assert S.season_rate_prob_v2(log([20.0] * 30), "REB", 6, {"status": "source_unavailable"})[1] == "no_opponent_context"
    missing = log([20.0] * 30); del missing["FTM"]
    assert S.season_rate_prob_v2(missing, "PTS", 20, OPP)[1] == "invalid_inputs"


def test_team_context_reports_what_the_opponent_allowed_before_the_cutoff():
    import datetime as dt
    import nba_team_context as tc
    def game(gid, day, a, b, pts_a, pts_b):
        base = {"GAME_ID": gid, "GAME_DATE": day, "REB": 40, "AST": 25, "FG3M": 12}
        return [dict(base, TEAM_ID=1, TEAM_ABBREVIATION=a, PTS=pts_a), dict(base, TEAM_ID=2, TEAM_ABBREVIATION=b, PTS=pts_b)]
    rows = game("1", "2026-10-22", "GSW", "LAL", 100, 120) + game("2", "2026-10-24", "BOS", "GSW", 90, 95) \
        + game("3", "2026-10-26", "GSW", "PHX", 80, 130)          # on/after cutoff: must be ignored
    bundle = {"tables": {"Regular Season": {"status": "available", "rows": rows},
                         "previous_regular": {"status": "available", "rows": [dict(r, PTS=110) for r in rows] * 50}},
              "captured_at": "x", "tables_sha256": "y"}
    ctx = tc.opponent_context(bundle, "GS", dt.date(2026, 10, 26))
    assert ctx["status"] == "available" and ctx["opponent"] == "GSW"
    assert ctx["allowed"]["PTS"] == [90.0, 120.0] and ctx["allowed"]["dates"] == ["2026-10-24", "2026-10-22"]
    assert ctx["league_source"] == "previous_regular" and ctx["league_avg"]["PTS"] == 110.0
    assert tc.opponent_context({"tables": {}}, "GSW", dt.date(2026, 10, 26))["status"] == "source_unavailable"


def test_v2_shadow_reaches_the_card_without_changing_it(monkeypatch):
    pts = [22.0, 25, 18, 24, 21, 26, 19, 23, 20, 27, 22, 24]
    ext = {"name": "Test Star", "position": "G",
           "gamelog": {"PTS": pts[:10], "MIN": [32] * 10, "season_log": log(pts)}}
    card = reports.build_player_card("Test Star", "DET", {"lines": {"20": "1.80"}}, ext, "points",
                                     opponent_abbr="BOS", team_stats={}, engine_mode="legacy",
                                     opponent_context=OPP)
    la = card["line_analysis"]["20"]
    assert la["season_rate_v2_status"] == "ok" and la["season_rate_v2_version"] == "nba_season_rate_S_v2"
    plain = card_for(ext)["line_analysis"]["20"]
    assert plain["season_rate_v2_status"] == "no_opponent_context"
    strip = lambda d: {k: v for k, v in d.items() if k not in KEYS}
    assert strip(la) == strip(plain)


TEAM_DATES = [f"2026-11-{d:02d}" for d in range(20, 10, -1)]   # team's last 10 games, newest first
TEAM_RECENT = {"status": "available", "dates": TEAM_DATES,
               "mean": {"PTS": 112.0, "REB": 44.0, "AST": 26.0, "FG3M": 13.0}}


def mate(name, status, pts, minutes=32.0, games=10, roster=True, kinds=None):
    lg = log([pts] * games, mins=[minutes] * games, kinds=kinds)
    lg["dates"] = TEAM_DATES[:games]
    return {"name": name, "status": status, "roster_verified": roster, "gamelog": {"season_log": lg}}


def test_absence_counts_out_only_and_reports_dtd_separately():
    from nba_availability import classify_injury_status as classify
    players = [mate("Star", "Out", 28.0), mate("Maybe", "Day-To-Day", 11.2), mate("Fine", "Active", 20.0),
               mate("Gone", "Out", 25.0, roster=False),              # traded/waived: not a teammate
               mate("Bench", "Out", 9.0, minutes=12.0),               # < 20 minutes: not key
               mate("Rare", "Out", 9.0, games=4),                     # < 5 team games: not key
               mate("Camp", "Out", 30.0, kinds=["Pre Season"] * 10)]  # preseason only: no evidence
    a = S.teammate_absence(players, TEAM_RECENT, classify)
    assert a["status"] == "available" and a["absent"] == ["Star"] and a["dtd"] == ["Maybe"]
    assert a["A"]["PTS"] == pytest.approx(28.0 / 112.0) and a["A_dtd"]["PTS"] == pytest.approx(11.2 / 112.0)
    assert S.teammate_absence(players, None, classify)["status"] == "no_team_recent"


def test_v3_is_v2_without_absences_and_rises_with_them():
    zero = {"status": "available", "A": {s: 0.0 for s in S.DISPERSION_K}, "A_dtd": {}}
    lg = log([20.0] * 30)
    assert S.season_rate_prob_v3(lg, "PTS", 20, OPP, zero)[0] == S.season_rate_prob_v2(lg, "PTS", 20, OPP)[0]
    star_out = {"status": "available", "A": {"PTS": 0.25, "REB": 0.0, "AST": 0.25, "FG3M": 0.0}, "A_dtd": {}}
    p3, status, inputs = S.season_rate_prob_v3(lg, "PTS", 20, OPP, star_out)
    assert status == "ok" and p3 > S.season_rate_prob_v2(lg, "PTS", 20, OPP)[0]
    _, _, i2 = S.season_rate_prob_v2(lg, "PTS", 20, OPP)
    assert abs(inputs["mu"] - i2["mu"] * (1 + 0.20 * 0.25 / 0.75)) < 2e-3 and inputs["k"] == i2["k"]
    assert S.season_rate_prob_v3(lg, "PTS", 20, OPP, None)[1] == "no_team_recent"
    assert S.season_rate_prob_v3(lg, "PTS", 20, OPP, {"status": "no_team_recent"})[1] == "no_team_recent"


def test_team_recent_uses_only_the_teams_games_before_cutoff():
    import datetime as dt
    import nba_team_context as tc
    rows = [{"GAME_ID": str(i), "GAME_DATE": f"2026-11-{i:02d}", "TEAM_ID": 1, "TEAM_ABBREVIATION": "GSW",
             "PTS": 100 + i, "REB": 40, "AST": 25, "FG3M": 12} for i in range(1, 15)]
    rows.append(dict(rows[0], TEAM_ABBREVIATION="LAL", TEAM_ID=2, PTS=999))
    out = tc.team_recent({"tables": {"Regular Season": {"status": "available", "rows": rows}}}, "GS", dt.date(2026, 11, 14))
    assert out["dates"][0] == "2026-11-13" and len(out["dates"]) == 10
    assert out["mean"]["PTS"] == sum(100 + i for i in range(4, 14)) / 10


def test_v3_shadow_reaches_the_card_without_changing_it(monkeypatch):
    pts = [22.0, 25, 18, 24, 21, 26, 19, 23, 20, 27, 22, 24]
    ext = {"name": "Test Star", "position": "G",
           "gamelog": {"PTS": pts[:10], "MIN": [32] * 10, "season_log": log(pts)}}
    ab = {"status": "available", "A": {"PTS": 0.2, "REB": 0.0, "AST": 0.0, "FG3M": 0.0}, "A_dtd": {}}
    card = reports.build_player_card("Test Star", "DET", {"lines": {"20": "1.80"}}, ext, "points",
                                     opponent_abbr="BOS", team_stats={}, engine_mode="legacy",
                                     opponent_context=OPP, absence_context=ab)
    la = card["line_analysis"]["20"]
    assert la["season_rate_v3_status"] == "ok" and la["season_rate_v3_version"] == "nba_season_rate_S_v3"
    assert la["season_rate_v3_prob_S"] > la["season_rate_v2_prob_S"]
    strip = lambda d: {k: v for k, v in d.items() if k not in KEYS}
    assert strip(la) == strip(card_for(ext)["line_analysis"]["20"])



def two_season_log(cur_pts, prev_pts, prev_team="PHI"):
    lg = log(list(cur_pts) + list(prev_pts))
    n_cur = len(cur_pts)
    lg["seasons"] = ["2026-27"] * n_cur + ["2025-26"] * len(prev_pts)
    lg["teams"] = ["PHI"] * n_cur + [prev_team] * len(prev_pts)
    return lg


def test_v4_equals_v2_without_previous_season_games():
    lg = two_season_log([20.0] * 12, [])
    assert S.season_rate_prob_v4(lg, "PTS", 20, OPP, "2026-27", "PHI")[0] == S.season_rate_prob_v2(lg, "PTS", 20, OPP)[0]


def test_v4_leans_on_this_season_and_more_so_after_a_move():
    lg = two_season_log([28.0] * 3, [15.0] * 40)          # hot start, cold last season
    p2 = S.season_rate_prob_v2(lg, "PTS", 20, OPP)[0]
    p4, status, inputs = S.season_rate_prob_v4(lg, "PTS", 20, OPP, "2026-27", "PHI")
    assert status == "ok" and p4 > p2 and inputs["previous_games"] == 40 and inputs["moved"] is False
    moved_log = two_season_log([28.0] * 3, [15.0] * 40, prev_team="LAL")
    p4m, _, inp = S.season_rate_prob_v4(moved_log, "PTS", 20, OPP, "2026-27", "PHI")
    assert inp["moved"] is True and inp["previous_weight"] == 0.25 * 0.25 and p4m > p4
    reb = S.season_rate_prob_v4(moved_log, "REB", 6, OPP, "2026-27", "PHI")[2]
    assert reb["previous_weight"] == 0.25                    # REB: no extra team-change factor


def test_v4_refuses_to_guess():
    lg = two_season_log([20.0] * 3, [20.0] * 10); del lg["teams"]
    assert S.season_rate_prob_v4(lg, "PTS", 20, OPP, "2026-27", "PHI")[1] == "no_team_history"
    assert S.season_rate_prob_v4(lg, "PTS", 20, OPP, None, "PHI")[1] == "no_current_season"
    ok_without_teams = log([20.0] * 12); ok_without_teams["seasons"] = ["2026-27"] * 12
    assert S.season_rate_prob_v4(ok_without_teams, "PTS", 20, OPP, "2026-27", "PHI")[1] == "ok"


def test_v4_reaches_the_card_without_changing_it():
    lg = two_season_log([22.0, 25, 18], [20.0] * 20)
    ext = {"name": "Test Star", "position": "G", "gamelog": {"PTS": [22, 25, 18] + [20] * 7, "MIN": [32] * 10,
                                                            "season_log": lg}}
    card = reports.build_player_card("Test Star", "PHI", {"lines": {"20": "1.80"}}, ext, "points",
                                     opponent_abbr="BOS", team_stats={}, engine_mode="legacy",
                                     opponent_context=OPP, current_season="2026-27")
    la = card["line_analysis"]["20"]
    assert la["season_rate_v4_status"] == "ok" and la["season_rate_v4_version"] == "nba_season_rate_S_v4"
    plain = reports.build_player_card("Test Star", "PHI", {"lines": {"20": "1.80"}}, ext, "points",
                                      opponent_abbr="BOS", team_stats={}, engine_mode="legacy")
    assert plain["line_analysis"]["20"]["season_rate_v4_status"] == "no_current_season"
    strip = lambda d: {k: v for k, v in d.items() if k not in KEYS}
    assert strip(la) == strip(plain["line_analysis"]["20"])
