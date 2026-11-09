"""EXP-20261110-01: the 大細盤精選 paper card and postgame lines."""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parents[1]))
import nba_featured_card as fc  # noqa: E402


def _pick(player, edge, side="under"):
    return {"rule": "nba-featured-ou-v1", "player": player, "team": "BOS", "market": "pts", "stat": "PTS",
            "ou_line": 24.5, "side": side, "price": 1.9, "other_price": 1.9, "p_model": 0.5 + edge,
            "p_fair": 0.5, "edge": edge, "milestone_line": 25.0}


def test_snapshot_picks_reads_every_game_and_caps_the_day(tmp_path):
    for i in range(12):
        (tmp_path / f"Game_G{i:02d}_H_Full_Analysis.md.market_legs.json").write_text(
            json.dumps({"featured": [_pick(f"P{i}", 0.05 + i / 100)]}))
    (tmp_path / "Game_X_Y_Full_Analysis.md.market_legs.json").write_text(json.dumps({"featured": []}))
    picks = fc.snapshot_picks(tmp_path)
    assert len(picks) == 10 and picks[0]["player"] == "P11" and picks[0]["game_tag"] == "G11_H"


def test_card_says_paper_only_and_lists_each_pick():
    text = fc.card("2026-11-11", [{**_pick("Jayson Tatum", 0.1), "game_tag": "BOS_LAL"}])
    assert "紙上盤" in text and "唔好落真錢" in text
    assert "BOS@LAL｜Jayson Tatum 得分 細 24.5 @1.9" in text and "+10.0pp" in text
    assert "冇大細盤" in fc.card("2026-11-11", [])


def test_postgame_reports_hits_but_never_roi():
    records = [
        {"day": "2026-11-11", "tracking_kind": "featured", "state": "won", "odds": 1.9,
         "legs": [{"player": "A", "stat": "PTS", "side": "under", "ou_line": 24.5, "actual": 20}]},
        {"day": "2026-11-11", "tracking_kind": "featured", "state": "void", "odds": 1.9,
         "legs": [{"player": "B", "stat": "AST", "side": "over", "ou_line": 5.5, "actual": "void"}]},
        {"day": "2026-11-10", "tracking_kind": "featured", "state": "lost", "odds": 1.9, "legs": [{}]},
    ]
    text = fc.postgame_lines("2026-11-11", records)
    assert text.startswith("⭐ 大細盤精選（紙上盤）：2 注｜中 1｜未中 0")
    assert "✅ A PTS 細 24.5 @1.9（實際 20）" in text and "➖ B AST 大 5.5" in text
    assert "ROI" not in text and "%" not in text
    assert fc.postgame_lines("2026-11-12", records) is None
