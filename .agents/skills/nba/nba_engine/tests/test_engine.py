"""nba_engine: model maths, leg building, selection search and the publication firewall."""
import hashlib
import itertools
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
from nba_engine.select import Policy, best_combo, select  # noqa: E402


def leg(player, team="AAA", stat="REB", line=5.0, price=1.5, p=0.7, **kw):
    base = dict(player=player, team=team, opponent="BBB", stat=stat, line=line, price=price, l10=[6.0] * 10,
                minutes_l10=32.0, hit_l10=0.9, hit_l5=1.0, hit_l3=1.0, avg=6.0, l3_avg=6.0, cov=0.2,
                market=1 / price, p_c=p, p_s=p, availability="ok", flags=[])
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


# --- selection ----------------------------------------------------------------
def brute_force(legs, policy):
    best, best_p = [], 0.0
    for n in range(policy.min_legs, policy.max_legs + 1):
        for combo in itertools.combinations(legs, n):
            product = math.prod(l.price for l in combo)
            teams = [l.team for l in combo]
            pts = [l.team for l in combo if l.stat == "PTS"]
            if (policy.min_price <= product <= policy.max_price and len({l.player for l in combo}) == n
                    and max(teams.count(t) for t in teams) <= 3 and all(pts.count(t) <= 2 for t in pts)):
                p = math.prod(l.p_c for l in combo)
                if p > best_p:
                    best, best_p = list(combo), p
    return best_p


def test_branch_and_bound_equals_brute_force():
    import random
    rng = random.Random(7)
    for _ in range(40):
        legs = [leg(f"P{i % 9}", team=rng.choice("AB"), stat=rng.choice(["PTS", "REB", "AST"]),
                    line=float(i), price=round(rng.uniform(1.05, 2.6), 2), p=rng.uniform(0.3, 0.97))
                for i in range(14)]
        combo, joint = best_combo(legs, lambda l: l.p_c, lambda l: l.price, lambda l: l.player,
                                  lambda l: l.team, lambda l: l.stat == "PTS", Policy())
        assert (joint or 0.0) == pytest.approx(brute_force(legs, Policy()))
        if combo:
            assert 2.0 <= math.prod(l.price for l in combo) <= 4.0


def test_structural_rules_hold():
    legs = [leg("A", stat="PTS", price=1.5, p=0.95), leg("B", stat="PTS", price=1.5, p=0.94),
            leg("C", stat="PTS", price=1.5, p=0.93), leg("A", stat="REB", line=8.0, price=1.5, p=0.92)]
    combo, _ = select(legs)
    assert len({l.player for l in combo}) == len(combo)
    assert sum(l.stat == "PTS" for l in combo) <= 2


def test_excluded_and_unavailable_legs_never_selected():
    legs = [leg("A", price=1.5, p=0.99, flags=["bench_minutes"]), leg("B", price=1.5, p=0.98, availability="dtd"),
            leg("C", price=1.45, p=0.8), leg("D", price=1.45, p=0.79)]
    combo, diag = select(legs)
    assert {l.player for l in combo} == {"C", "D"}
    assert diag["funnel"]["bench_minutes"] == 1 and diag["funnel"]["availability"] == 1


def test_value_check_drops_legs_rated_below_price():
    legs = [leg("A", price=1.5, p=0.6), leg("B", price=1.5, p=0.9), leg("C", price=1.5, p=0.85)]
    combo, _ = select(legs, Policy(value_check=True))
    assert "A" not in {l.player for l in combo}


def test_no_combo_reaching_the_floor_is_no_bet():
    combo, diag = select([leg("A", price=1.1), leg("B", price=1.1)])
    assert combo == [] and diag["joint_probability"] is None


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
    assert all(l.p_c is not None and l.p_s is not None for l in legs)


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


def test_report_and_sidecar_are_bound_and_parse_like_the_dashboard(tmp_path):
    odds, package = game()
    ok = lambda o, legs: Quoted({"status": "ok", "decimal_odds": 2.1})  # noqa: E731
    legs, combo, quote, diag = analyse(odds, package, quote=ok, valid=lambda q, o, l: True)
    text = report.render(odds, package, legs, combo, quote, Policy(), diag)
    payload = report.sidecar(text, odds, package, legs, combo, quote, Policy(), diag)
    assert payload["report_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert publish.HEADING.findall(text) == [("1", "2.1")]
    rows = [r for r in text.splitlines() if r.startswith("| 🧩")]
    assert [r.split("|")[2].strip() for r in rows] == [l["desc"] for l in payload["combos"][0]["legs"]]
    assert sum(l["picked"] for l in payload["legs"]) == len(combo)
    for marker in ("SPORTSBET_LIVE", "Python Auto-Selection", "未填寫項目 殘留: 0", report.STEADY_MARKER):
        assert marker in text


def test_firewall_blocks_a_report_edited_after_writing(tmp_path):
    odds, package = game()
    legs, combo, quote, diag = analyse(odds, package)   # no network under pytest -> NO BET
    text = report.render(odds, package, legs, combo, quote, Policy(), diag)
    out = tmp_path / "Game_AAA_BBB_Full_Analysis.md"
    report.write(str(out), text, report.sidecar(text, odds, package, legs, combo, quote, Policy(), diag))
    (tmp_path / "Sportsbet_Odds_AAA_BBB.json").write_text(json.dumps(odds))
    assert publish.validate(out, tmp_path / "Sportsbet_Odds_AAA_BBB.json") == (True, [])
    out.write_text(text + "\nedited")
    passed, blocks = publish.validate(out, tmp_path / "Sportsbet_Odds_AAA_BBB.json")
    assert not passed and "does not belong" in blocks[0]
