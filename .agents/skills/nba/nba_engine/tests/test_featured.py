"""EXP-20261110-01 大細盤精選: candidate maths, one pick per game, daily cap, sidecar wiring."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from nba_engine import featured, report  # noqa: E402
from nba_engine.legs import Leg  # noqa: E402


def _leg(player="Jayson Tatum", stat="PTS", line=25.0, p=0.40, availability="ok"):
    return Leg(player=player, team="BOS", opponent="LAL", stat=stat, line=line, price=2.5,
               l10=[24.0] * 10, minutes_l10=36.0, hit_l10=0.4, hit_l5=0.4, hit_l3=0.3, avg=24.0,
               median=24.0, l3_avg=24.0, cov=0.2, market=0.4, p_c=p, p_s=None, p_ms=p,
               availability=availability, flags=[])


def _odds(two_way):
    return {"away_team": "BOS", "home_team": "LAL", "player_props_two_way": two_way}


def test_over_x5_borrows_the_ceil_milestone_and_devigs_both_sides():
    odds = _odds({"points": {"Jayson Tatum": {"24.5": {"over": "1.90", "under": "1.90"}}}})
    rows = {c["side"]: c for c in featured.candidates(odds, [_leg(line=25.0, p=0.40)])}
    assert rows["over"]["p_fair"] == 0.5 and rows["under"]["p_fair"] == 0.5
    assert rows["over"]["edge"] == -0.1 and rows["under"]["edge"] == 0.1
    assert rows["under"]["milestone_line"] == 25.0 and rows["under"]["other_price"] == 1.9


def test_one_pick_per_game_needs_five_points_of_edge():
    odds = _odds({"points": {"Jayson Tatum": {"24.5": {"over": "1.90", "under": "1.90"}}},
                  "assists": {"Jayson Tatum": {"5.5": {"over": "1.90", "under": "1.90"}}}})
    legs = [_leg(line=25.0, p=0.40), _leg(stat="AST", line=6.0, p=0.47)]
    pick = featured.game_pick(odds, legs)
    assert (pick["market"], pick["side"], pick["ou_line"]) == ("pts", "under", 24.5)
    assert featured.game_pick(odds, [_leg(line=25.0, p=0.47)]) is None   # 3pp edge: no pick


def test_unavailable_or_unmatched_players_never_qualify():
    odds = _odds({"points": {"Jayson Tatum": {"24.5": {"over": "1.90", "under": "1.90"}},
                             "Nobody": {"10.5": {"over": "1.90", "under": "1.90"}}}})
    assert featured.candidates(odds, [_leg(line=25.0, p=0.2, availability="dtd")]) == []


def test_daily_cap_keeps_the_ten_largest_edges():
    picks = [{"edge": e / 100, "player": f"P{e}", "game_tag": f"G{e}"} for e in range(5, 20)]
    top = featured.daily_top(picks)
    assert len(top) == 10 and top[0]["edge"] == 0.19 and min(p["edge"] for p in top) == 0.10


def test_sidecar_and_report_carry_the_pick():
    pick = featured.game_pick(_odds({"points": {"Jayson Tatum": {"24.5": {"over": "1.90", "under": "1.90"}}}}),
                              [_leg(line=25.0, p=0.40)])
    diagnostics = {"rule": "b2", "featured": pick, "no_bet_reason": "no_b2_combo"}
    odds = {"away_team": "BOS", "home_team": "LAL", "extraction_time": "x"}
    text = report.render(odds, {}, [], [], None, diagnostics)
    assert "大細盤精選" in text and "Jayson Tatum PTS 細 24.5" in text
    payload = report.sidecar(text, odds, {}, [], [], None, diagnostics)
    assert payload["featured"] == [pick]
    empty = report.sidecar(text, odds, {}, [], [], None, {"rule": "b2"})
    assert empty["featured"] == []
