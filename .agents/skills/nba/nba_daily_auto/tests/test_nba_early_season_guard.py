"""Early-season banker guard (EXP-20261026-06): stricter only, AST/3PM and new-team legs."""
from __future__ import annotations

import json
import sys
from pathlib import Path

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_daily_auto'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import generate_nba_reports as r
import nba_early_season_guard_monitor as monitor

CUR, PREV = "2026-27", "2025-26"


def card(team="PHI", seasons=None, teams=None):
    return {"team": team, "l10_seasons": seasons or [], "l10_teams": teams or []}


def test_role_stats_need_current_season_evidence():
    mostly_prev = card(seasons=[CUR] * 4 + [PREV] * 6, teams=["PHI"] * 10)
    assert r.early_season_guard(mostly_prev, "AST", CUR) == ["l10_mostly_previous_season"]
    assert r.early_season_guard(mostly_prev, "3PM", CUR) == ["l10_mostly_previous_season"]
    assert r.early_season_guard(mostly_prev, "PTS", CUR) is None       # PTS/REB unaffected in the data
    assert r.early_season_guard(mostly_prev, "REB", CUR) is None
    five_current = card(seasons=[CUR] * 5 + [PREV] * 5, teams=["PHI"] * 10)
    assert r.early_season_guard(five_current, "AST", CUR) is None
    assert r.early_season_guard(mostly_prev, "AST", None) is None      # unknown season: no claim


def test_new_team_blocks_every_stat_until_five_games():
    lebron = card(seasons=[CUR] * 2 + [PREV] * 8, teams=["PHI"] * 2 + ["LAL"] * 8)
    assert r.early_season_guard(lebron, "PTS", CUR) == ["new_team_under_5_games"]
    assert r.early_season_guard(lebron, "AST", CUR) == ["l10_mostly_previous_season", "new_team_under_5_games"]
    settled = card(seasons=[CUR] * 5 + [PREV] * 5, teams=["PHI"] * 5 + ["LAL"] * 5)
    assert r.early_season_guard(settled, "PTS", CUR) is None
    alias = card(team="GS", seasons=[CUR] * 10, teams=["GSW"] * 10)    # ESPN vs NBA abbreviations
    assert r.early_season_guard(alias, "PTS", CUR) is None


def candidate(name, guard):
    return {"market_type": r.PLAYER_MARKET, "player": name, "team": "PHI", "category": "PTS", "line_val": 10,
            "hit_l10": 100, "hit_l5": 100, "edge": 5, "odds": 1.3, "cov": 0.1, "avg": 20, "l3_avg": 20,
            "early_season_guard": guard}


def test_both_banker_rules_drop_guarded_legs():
    pool = [candidate("Fine", None), candidate("Moved", ["new_team_under_5_games"])]
    assert [c["player"] for c in r.banker_pool(pool, "banker")] == ["Fine"]
    assert [c["player"] for c in r.banker_pool(pool, "banker_fallback")] == ["Fine"]


def test_card_and_candidate_carry_the_guard():
    ext = {"name": "LeBron James", "advanced": {"USG_PCT": 25},
           "gamelog": {"PTS": [20, 22, 25, 18, 24, 26, 21, 23, 19, 27], "MIN": [34] * 10,
                       "l10_seasons": [CUR] * 2 + [PREV] * 8,
                       "l10_matchups": ["PHI vs. CLE", "PHI @ NYK"] + ["LAL vs. OKC"] * 8}}
    c = r.build_player_card("LeBron James", "PHI", {"lines": {"15": "1.3"}}, ext, "points", engine_mode="legacy")
    assert c["l10_teams"][:3] == ["PHI", "PHI", "LAL"]
    legs = r.build_leg_candidates([c], meta={"roster_season": CUR})
    assert legs and legs[0]["early_season_guard"] == ["new_team_under_5_games"]


def test_monitor_splits_guarded_from_unguarded(tmp_path):
    day = "2026-10-28"
    base = {"target_date": day, "game_tag": "A_B", "snapshot_id": "s", "snapshot_role": "production",
            "snapshot_created_at": f"{day}T08:00:00+00:00", "post_tip": False, "late_write": False,
            "tip_unknown": False, "side": "over"}
    rows = []
    for player, market, guard, y in (("a", "ast", ["l10_mostly_previous_season"], 0), ("b", "ast", None, 1),
                                     ("c", "pts", None, 1)):
        rows.append(dict(base, row_type="model_obs", player=player, market=market, line=4.0, p_final=0.75,
                         p_l10_base_rate=0.9, price_at_model=1.25, early_season_guard=guard))
        rows.append(dict(base, row_type="settlement", player=player, market=market, line=4.0, y=y,
                         outcome="hit" if y else "miss"))
    rows.append(dict(base, row_type="model_obs", player="old", market="pts", line=4.0, p_final=0.75,
                     p_l10_base_rate=0.9, price_at_model=1.25))                 # pre-guard snapshot
    (tmp_path / "ledger").mkdir()
    (tmp_path / "ledger" / f"{day}.jsonl").write_text("".join(json.dumps(x) + "\n" for x in rows))
    table = monitor.summarise(monitor.legs(tmp_path, None, None))["table"]
    assert set(table) == {"ast | l10_mostly_previous_season", "ast | none", "pts | none"}
    assert table["ast | l10_mostly_previous_season"]["hit"] == 0.0 and table["ast | none"]["games"] == 1
