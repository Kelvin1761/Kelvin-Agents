import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import nba_featured_availability as fa  # noqa: E402

PICK = {"game_tag": "GSW_NOP", "player": "Herbert Jones", "market": "ast", "stat": "AST",
        "ou_line": 1.5, "side": "under", "price": 1.96}
T1 = datetime(2026, 11, 17, 6, 30, tzinfo=timezone.utc)
T2 = datetime(2026, 11, 17, 8, 30, tzinfo=timezone.utc)


def _odds(folder, assists):
    (folder / "Sportsbet_Odds_GSW_NOP.json").write_text(json.dumps({"player_props_two_way": {"assists": assists}}))


def test_classify_open_line_moved_withdrawn_unknown():
    other = {"Zion Williamson": {"4.5": {"over": "1.9", "under": "1.9"}}}
    assert fa.classify({"player_props_two_way": {"assists": {**other, "Herbert Jones": {"1.5": {"over": "1.8", "under": "1.96"}}}}}, PICK) == "open"
    assert fa.classify({"player_props_two_way": {"assists": {**other, "Herbert Jones": {"1.5": {"over": "1.8"}}}}}, PICK) == "line_moved"
    assert fa.classify({"player_props_two_way": {"assists": {**other, "Herbert Jones": {"2.5": {"over": "1.8", "under": "2"}}}}}, PICK) == "line_moved"
    assert fa.classify({"player_props_two_way": {"assists": other}}, PICK) == fa.WITHDRAWN
    # Nobody has an assists O/U: an extraction gap, not evidence the market was pulled.
    assert fa.classify({"player_props_two_way": {"points": other}}, PICK) == "unknown"


def test_withdrawal_is_sticky_and_reported_once(tmp_path):
    _odds(tmp_path, {"Zion Williamson": {"4.5": {"over": "1.9", "under": "1.9"}}})
    assert [p["player"] for p in fa.check(tmp_path, [PICK], {"GSW_NOP"}, now=T1)] == ["Herbert Jones"]
    _odds(tmp_path, {"Herbert Jones": {"1.5": {"over": "1.8", "under": "1.96"}}})  # market reappears
    assert fa.check(tmp_path, [PICK], {"GSW_NOP"}, now=T2) == []
    entry = fa.withdrawn([tmp_path])["GSW_NOP"]
    assert entry["withdrawn_at"] == T1.isoformat() and entry["last_status"] == "open"
    assert fa.matches(entry, PICK) and not fa.matches(entry, {**PICK, "side": "over"})


def test_started_games_and_open_markets_are_not_voided(tmp_path):
    _odds(tmp_path, {"Zion Williamson": {"4.5": {"over": "1.9", "under": "1.9"}}})
    assert fa.check(tmp_path, [PICK], set(), now=T1) == []  # game already started
    _odds(tmp_path, {"Herbert Jones": {"1.5": {"over": "1.8", "under": "1.96"}}})
    assert fa.check(tmp_path, [PICK], {"GSW_NOP"}, now=T1) == []
    assert fa.withdrawn([tmp_path]) == {}


def test_message_names_the_bet_and_says_not_counted():
    text = fa.message("2026-11-17", [PICK])
    assert "GSW@NOP｜Herbert Jones - Assists｜Under 1.5" in text and "作廢不計" in text
