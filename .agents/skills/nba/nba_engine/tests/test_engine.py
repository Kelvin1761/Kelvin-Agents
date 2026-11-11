"""nba_engine: model maths, leg building, selection search and the publication firewall."""
import hashlib
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nba_engine import model, publish, report  # noqa: E402
from nba_engine.legs import Leg, build_legs  # noqa: E402
from nba_engine.run import analyse  # noqa: E402
from nba_engine import banker  # noqa: E402


def leg(player, team="AAA", stat="REB", line=5.0, price=1.5, p=0.7, **kw):
    base = dict(player=player, team=team, opponent="BBB", stat=stat, line=line, price=price, l10=[6.0] * 10,
                minutes_l10=32.0, hit_l10=0.9, hit_l5=1.0, hit_l3=1.0, avg=6.0, median=6.0, l3_avg=6.0, cov=0.2,
                market=1 / price, p_c=p, p_s=p, p_ms=None, availability="ok", flags=[])
    base.update(kw)
    return Leg(**base)


# --- model ------------------------------------------------------------------
def test_c_layer_matches_frozen_formula():
    c = model.config()["c_layer"]
    z = c["intercepts"]["PTS"] + c["beta_market"] * math.log(0.5 / 0.5) + c["gamma_l10"] * math.log(0.8 / 0.2)
    assert model.c_prob("PTS", 2.0, 0.8) == pytest.approx(1 / (1 + math.exp(-z)))


@pytest.mark.parametrize("price,hit", [(1.0, 0.5), (None, 0.5), ("x", 0.5), (2.0, None), (2.0, 1.5)])
def test_c_layer_refuses_bad_inputs(price, hit):
    assert model.c_prob("PTS", price, hit) is None


def test_nb_tail_matches_direct_sum():
    mu, k = 6.3, 9.0
    p = k / (k + mu)
    pmf = lambda x: math.comb(int(x + k - 1), x) if False else math.exp(  # noqa: E731
        math.lgamma(x + k) - math.lgamma(k) - math.lgamma(x + 1) + k * math.log(p) + x * math.log(1 - p))
    assert model.nb_tail(5, mu, k) == pytest.approx(1 - sum(pmf(x) for x in range(5)))


def season_log(n=12, minutes=30.0, reb=7.0, season="2026-27", team="AAA"):
    days = [(datetime(2026, 11, 1) - timedelta(days=2 * i)).strftime("%Y-%m-%d") for i in range(n)]
    col = lambda v: [v] * n  # noqa: E731
    return {"dates": days, "MIN": col(minutes), "PTS": col(20.0), "REB": col(reb), "AST": col(4.0),
            "FG3M": col(2.0), "FGA": col(15.0), "FG3A": col(5.0), "FTA": col(4.0), "FGM": col(7.0),
            "FTM": col(3.0), "season_types": col("Regular Season"), "seasons": col(season), "teams": col(team)}


OPP = {"status": "available", "allowed": {"REB": [44.0] * 5, "PTS": [112.0] * 5, "AST": [25.0] * 5,
                                          "FG3M": [12.0] * 5},
       "league_avg": {"REB": 44.0, "PTS": 112.0, "AST": 25.0, "FG3M": 12.0}}


def test_season_rate_mean_is_minutes_times_rate_for_flat_history():
    mu, _ = model.season_mu(season_log(), "REB", OPP, "2026-27", "AAA")
    assert mu == pytest.approx(7.0)


def test_season_rate_needs_opponent_and_history():
    assert model.s_prob(season_log(), "REB", 5, {"status": "source_unavailable"}, "2026-27", "AAA") is None
    assert model.s_prob(season_log(n=3), "REB", 5, OPP, "2026-27", "AAA") is None
    assert model.s_prob(season_log(), "REB", 5.5, OPP, "2026-27", "AAA") is None


def test_opponent_that_allows_more_raises_the_mean():
    soft = json.loads(json.dumps(OPP))
    soft["allowed"]["REB"] = [55.0] * 5
    assert model.s_prob(season_log(), "REB", 7, soft, "2026-27", "AAA") > model.s_prob(season_log(), "REB", 7, OPP, "2026-27", "AAA")


# --- MS layer ---------------------------------------------------------------
def test_ms_layer_matches_frozen_formula_and_falls_back_to_c():
    c = model.config()["ms_layer"]
    z = c["intercepts"]["REB"] + c["beta_market"] * math.log(0.6 / 0.4) + c["gamma_s"] * math.log(0.7 / 0.3)
    assert model.ms_prob("REB", 1 / 0.6, 0.7) == pytest.approx(1 / (1 + math.exp(-z)))
    assert model.ms_prob("REB", 1.5, None) is None
    assert leg("A", p=0.7, p_ms=None).p_final == 0.7
    assert leg("A", p=0.7, p_ms=0.66).p_final == 0.66


# --- B2 banker ---------------------------------------------------------------
def test_strict_pool_rules():
    good = dict(hit_l10=0.9, hit_l5=0.8, price=1.5, cov=0.3, l3_avg=7.0, avg=7.0, line=6.0)
    assert banker.pool([leg("A", **good)], banker.STRICT)
    for change in (dict(hit_l10=0.7), dict(hit_l5=0.6), dict(price=1.15), dict(cov=0.7), dict(l3_avg=5.0),
                   dict(avg=6.5), dict(availability="dtd"), dict(flags=["bench_minutes"]), dict(flags=["new_team"])):
        assert not banker.pool([leg("A", **{**good, **change})], banker.STRICT), change


def test_ast_at_or_above_median_needs_season_model_edge():
    base = dict(stat="AST", line=4.0, median=4.0, price=1.5, avg=5.0, l3_avg=5.0)
    assert not banker.ast_guard_ok(leg("A", p_s=None, **base))
    assert not banker.ast_guard_ok(leg("A", p_s=0.68, **base))           # 1.5 -> 66.7% market, +1.3pp
    assert banker.ast_guard_ok(leg("A", p_s=0.71, **base))
    assert banker.ast_guard_ok(leg("A", p_s=None, **{**base, "median": 5.0}))


def test_b2_builds_to_the_price_target_with_structural_rules():
    legs = [leg(f"P{i}", team="AB"[i % 2], stat=["PTS", "REB", "AST"][i % 3], price=1.35 + 0.05 * i,
                hit_l10=1.0 if i < 2 else 0.9, avg=8.0, l3_avg=8.0, line=6.0) for i in range(8)]
    combo, rule = banker.select_b2(legs)
    assert rule == "banker" and 2 <= len(combo) <= 4
    assert 2.0 <= banker.product(combo) <= 3.5 * banker.TOLERANCE
    assert banker.allowed(combo) and len({l.player for l in combo}) == len(combo)


def test_b2_falls_back_then_gives_up():
    legs = [leg(f"P{i}", hit_l10=0.7, hit_l5=0.7, price=1.5, avg=6.2, l3_avg=6.0, line=6.0) for i in range(3)]
    assert banker.select_b2(legs)[1] == "banker_fallback"
    assert banker.select_b2([leg("A", hit_l10=0.5)]) == ([], "none")


# --- end to end ------------------------------------------------------------------
def game():
    gamelog = {"PTS": [25.0] * 10, "REB": [8.0] * 10, "AST": [5.0] * 10, "FG3M": [2.0] * 10, "MIN": [34.0] * 10,
               "season_log": season_log(reb=8.0)}
    players = {t: [{"name": f"{t} Star{i}", "status": "Active", "gamelog": gamelog} for i in range(3)]
               for t in ("AAA", "BBB")}
    odds = {"away_team": "AAA", "home_team": "BBB", "extraction_time": "2026-11-04 18:00:00",
            "event_start_time": "2026-11-05T11:00:00+11:00",
            "player_props": {"rebounds": {f"{t} Star{i}": {"lines": {"6": "1.45", "10": "3.2", "7.5": "1.9"}}
                                          for t in ("AAA", "BBB") for i in range(3)}}}
    package = {"meta": {"roster_season": "2026-27", "season_phase": "EARLY_REGULAR"}, "players": players,
               "opponent_context": {"AAA": OPP, "BBB": OPP}, "injuries": {"BBB": {"BBB Star2": "Out"}}}
    return odds, package


def test_build_legs_skips_decimal_lines_and_out_players():
    legs, skipped = build_legs(*game())
    assert {l.line for l in legs} == {6.0, 10.0}
    assert "BBB Star2" not in {l.player for l in legs} and skipped["out"] == 1
    assert all(l.p_c is not None and l.p_s is not None and l.p_final == l.p_ms for l in legs)


class Quoted:
    def __init__(self, quote):
        self.quote = quote


def test_analyse_bets_only_on_a_valid_quote_at_or_above_two():
    odds, package = game()
    ok = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 2.1})  # noqa: E731
    low = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 1.9})  # noqa: E731
    _, combo, quote, _ = analyse(odds, package, quote=ok, valid=lambda q, o, l: True)
    assert combo and quote["decimal_odds"] == 2.1
    _, combo, _, diag = analyse(odds, package, quote=low, valid=lambda q, o, l: True)
    assert combo == [] and diag["no_bet_reason"].startswith("quote_rejected")
    _, combo, _, diag = analyse(odds, package, quote=ok, valid=lambda q, o, l: True, paused="S1")
    assert combo == [] and diag["no_bet_reason"] == "steady_paused:S1"
    package["meta"]["season_phase"] = "PRESEASON"
    _, combo, _, diag = analyse(odds, package, quote=ok, valid=lambda q, o, l: True)
    assert combo == [] and diag["no_bet_reason"] == "preseason_shadow_only"


def test_report_and_sidecar_are_bound_and_the_sidecar_carries_what_the_dashboard_shows(tmp_path):
    odds, package = game()
    ok = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 2.1})  # noqa: E731
    legs, combo, quote, diag = analyse(odds, package, quote=ok, valid=lambda q, o, l: True)
    text = report.render(odds, package, legs, combo, quote, diag)
    payload = report.sidecar(text, odds, package, legs, combo, quote, diag)
    assert payload["report_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    (combo_row,) = payload["combos"]
    assert combo_row["heading"].endswith("組合賠率 @2.1") and f"### {combo_row['heading']}" in text
    assert combo_row["sportsbet_sgm_price"] == 2.1
    assert all(row.get("cov") is not None and row.get("p_market") for row in payload["legs"])
    # The reflector still reads the leg rows (see report.py); keep them matching the sidecar.
    rows = [r for r in text.splitlines() if r.startswith("| 🧩")]
    assert [r.split("|")[2].strip() for r in rows] == [l["desc"] for l in combo_row["legs"]]
    assert sum(l["picked"] for l in payload["legs"]) == len(combo)


def test_firewall_blocks_a_report_edited_after_writing(tmp_path):
    odds, package = game()
    legs, combo, quote, diag = analyse(odds, package)   # no network under pytest -> NO BET
    text = report.render(odds, package, legs, combo, quote, diag)
    out = tmp_path / "Game_AAA_BBB_Full_Analysis.md"
    report.write(str(out), text, report.sidecar(text, odds, package, legs, combo, quote, diag))
    (tmp_path / "Sportsbet_Odds_AAA_BBB.json").write_text(json.dumps(odds))
    assert publish.validate(out, tmp_path / "Sportsbet_Odds_AAA_BBB.json") == (True, [])
    out.write_text(text + "\nedited")
    passed, blocks = publish.validate(out, tmp_path / "Sportsbet_Odds_AAA_BBB.json")
    assert not passed and "does not belong" in blocks[0]


def test_player_identity_normalises_accents_and_suffixes_but_never_guesses():
    from nba_engine.legs import _find
    players = [{"name": "Luka Dončić"}, {"name": "Gary Payton Jr."}]
    assert _find(players, "Luka Doncic")["name"] == "Luka Dončić"
    assert _find(players, "Dončić") is None
    assert _find(players, "Gary Payton Sr.") is None
    assert _find([{"name": "Luka Dončić"}, {"name": "Luka Doncic"}], "Luka Doncic") is None


def test_early_season_and_new_team_flags():
    from nba_engine.legs import _flags
    previous = {"l10_seasons": ["2026-27"] * 3 + ["2025-26"] * 7, "l10_matchups": ["BOS vs. NYK"] * 10}
    assert "l10_mostly_previous_season" in _flags("AST", previous, "BOS", "2026-27", 30.0)
    assert "l10_mostly_previous_season" not in _flags("PTS", previous, "BOS", "2026-27", 30.0)
    moved = {"l10_seasons": ["2026-27"] * 10, "l10_matchups": ["LAL vs. NYK"] * 7 + ["BOS @ MIA"] * 3}
    assert "new_team" in _flags("REB", moved, "BOS", "2026-27", 30.0)
    assert "bench_minutes" in _flags("REB", moved, "BOS", "2026-27", 22.0)


def test_paused_or_underpriced_b2_is_still_recorded_for_tracking():
    odds, package = game()
    ok = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 2.1})  # noqa: E731
    low = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 1.9})  # noqa: E731
    for quote, paused in ((ok, "S1"), (low, None)):
        legs, combo, q, diag = analyse(odds, package, quote=quote, valid=lambda *a: True, paused=paused)
        assert combo == []
        payload = report.sidecar("text", odds, package, legs, combo, q, diag)
        research = payload["review_candidates"][0]
        assert research["candidate_id"] == "steady" and research["decision"] == "OBSERVE"
        assert research["version"] == report.RESEARCH_VERSION and 2 <= len(research["legs"]) <= 4
        assert research["odds"] == q["decimal_odds"] and "research" not in payload["selection_diagnostics"]
    _, combo, q, diag = analyse(odds, package, quote=ok, valid=lambda *a: False)
    assert combo == [] and report.research_record([], q, False)["odds"] is None


# --- S2 shadow (EXP-20261111-03) ----------------------------------------------
def test_s2_with_unit_ratio_is_s_and_scales_with_minutes():
    log = season_log(reb=8.0)
    s = model.s_prob(log, "REB", 8, OPP, "2026-27", "AAA")
    assert model.s2_prob(log, "REB", 8, OPP, "2026-27", "AAA", 1.0) == pytest.approx(s)
    assert model.s2_prob(log, "REB", 8, OPP, "2026-27", "AAA", 0.8) < s < model.s2_prob(log, "REB", 8, OPP, "2026-27", "AAA", 1.2)
    assert model.s2_prob(log, "REB", 8, OPP, "2026-27", "AAA", None) is None


def test_s2_shadow_never_changes_the_published_probability():
    odds, package = game()
    odds["game_lines"] = {"spread_away": "+4.5"}
    for team, plist in package["players"].items():
        for i, p in enumerate(plist):
            p["player_id"] = f"{team}{i}"
    base, _ = build_legs(odds, package)
    feats = {"m_hl": 34.0, "m_season": 33.0, "m_l10": 34.0, "m_last": 35.0, "games": 10, "started_prev": True,
             "start_share": 1.0, "rest": 1, "gap_last": 1, "missed_prev": False, "pool_prev": 0.0}
    package["minutes_context"] = {"status": "available",
                                  "teams": {t: {f"{t}{i}": dict(feats) for i in range(3)} for t in ("AAA", "BBB")}}
    shadow, _ = build_legs(odds, package)
    assert [l.p_final for l in shadow] == [l.p_final for l in base]
    assert all(l.p_s2 is not None and l.minutes_ratio is not None for l in shadow)
    assert all(l.p_s2 is None for l in base)
    away = next(l for l in shadow if l.team == "AAA")
    home = next(l for l in shadow if l.team == "BBB")
    assert away.minutes_ratio != home.minutes_ratio        # the favourite and the underdog get different spreads


def test_season_fit_factors_multiply_to_the_same_mean_season_mu_returns():
    """Display breakdown (dashboard「點解揀」) must explain the model's own number, not a second one."""
    for stat in ("REB", "PTS"):
        fit = model.season_fit(season_log(), stat, OPP, "2026-27", "AAA")
        assert (fit["mu"], fit["k"]) == model.season_mu(season_log(), stat, OPP, "2026-27", "AAA")
        assert abs(fit["minutes"] * fit["per_minute"] * fit["opponent_factor"] - fit["mu"]) < 1e-9
    assert model.season_fit(season_log(n=3), "REB", OPP, "2026-27", "AAA") is None
