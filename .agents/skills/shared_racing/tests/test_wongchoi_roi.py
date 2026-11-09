"""wongchoi_roi：所有旺財同一個 ROI 格式（Kelvin 2026-11-05）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import wongchoi_roi as roi  # noqa: E402


def _seed(path):
    roi.record_days("au", {
        "2026-11-03": {"bets": 10, "hits": 4, "stake": 10, "pnl": -2.5},
        "2026-11-04": {"bets": 8, "hits": 5, "stake": 8, "pnl": 1.2},
    }, day="2026-11-04", since="2026-08-12", path=path)
    roi.record("tennis", day="2026-11-04",
               latest={"bets": 4, "hits": 3, "stake": 4, "pnl": 1.4},
               cumulative={"bets": 57, "hits": 29, "stake": 57, "pnl": -4.765}, path=path)


def test_board_shows_only_bets_hits_roi_and_pct_for_every_wong_choi(tmp_path):
    path = tmp_path / "roi_board.json"
    _seed(path)
    text = roi.render(updated="tennis", today="2026-11-05", path=path)
    assert text.splitlines()[0] == "📊 旺財 ROI｜2026-11-05"
    assert "🆕 啱啱結算：🎾 網球" in text
    assert "🇦🇺 AU 賽馬\n  昨日（11-04）：8 注｜中 5｜ROI +1.20u｜+15.0%" in text
    assert "  累計（2026-08-12 起）：18 注｜中 9｜ROI −1.30u｜−7.2%" in text
    # 冇紀錄嘅旺財照列，等兩個人知佢未有數，唔係漏咗。
    assert "🏀 NBA 大細盤精選（紙上盤）\n  未有紀錄" in text
    assert "合共累計：75 注｜中 38｜ROI −6.07u｜−8.1%" in text or \
        "合共累計：75 注｜中 38｜ROI −6.06u｜−8.1%" in text
    # HKJC 未有落注定義，唔出現。
    assert "HKJC" not in text


def test_record_days_merge_keeps_old_days_and_recomputes_cumulative(tmp_path):
    path = tmp_path / "roi_board.json"
    _seed(path)
    # 11-04 遲到賽果改咗數；11-03 唔俾，要保留。
    entry = roi.record_days("au", {"2026-11-04": {"bets": 9, "hits": 5, "stake": 9, "pnl": 0.2}},
                            day="2026-11-04", since="2026-08-12", path=path, merge=True)
    assert entry["latest"]["bets"] == 9
    assert entry["cumulative"]["bets"] == 19
    assert roi.known_days("au", path) == {"2026-11-03", "2026-11-04"}


def test_rewriting_a_domain_is_idempotent_and_leaves_others(tmp_path):
    path = tmp_path / "roi_board.json"
    _seed(path)
    for _ in range(2):
        roi.record("nba", day="2026-11-04", latest={"bets": 2, "hits": 1, "pnl": 0.8},
                   cumulative={"bets": 40, "hits": 25, "pnl": 3.0}, path=path)
    data = roi.load(path)
    assert set(data["domains"]) == {"au", "nba", "tennis"}
    assert data["domains"]["nba"]["cumulative"]["stake"] == 40.0  # 冇 stake = 平注


def test_zero_bet_day_says_no_bets_not_a_fake_percentage(tmp_path):
    path = tmp_path / "roi_board.json"
    roi.record("nba", day="2026-11-05", latest={}, cumulative={"bets": 3, "hits": 1, "pnl": -1},
               path=path)
    text = roi.render(today="2026-11-05", path=path)
    assert "今日（11-05）：冇注" in text


def test_publish_goes_to_kelvin_and_heison(tmp_path, monkeypatch):
    path = tmp_path / "roi_board.json"
    _seed(path)
    import racing_telegram

    calls = []
    monkeypatch.setattr(racing_telegram, "send_message",
                        lambda text, **kw: calls.append(kw) or {"ok": True, "status": "sent"})
    result = roi.publish("au", today="2026-11-05", path=path)
    assert result["ok"] and calls == [{"audience": "content", "dry_run": False}]


def test_missing_or_corrupt_ledger_renders_empty_board(tmp_path):
    path = tmp_path / "roi_board.json"
    path.write_text("{not json")
    text = roi.render(today="2026-11-05", path=path)
    assert text.count("未有紀錄") == len(roi.DOMAINS)
