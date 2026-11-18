"""EXP-20261118-03：回放馬匹頁往績改讀存檔 —— 行原版 enrich、as-of、唔留低 horseid、唔上網。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "scripts"))
sys.path.insert(0, str(HERE.parents[1] / "hkjc_wong_choi_auto" / "scripts"))

import hkjc_auto_orchestrator as orch  # noqa: E402
import hkjc_history_replay_profile as rp  # noqa: E402


def _install(monkeypatch, entries, index):
    monkeypatch.setattr(rp, "_archive", lambda: entries)
    monkeypatch.setattr(rp, "_name_index", lambda: index)
    orig_enrich, orig_get = orch._enrich_profile_history, orch._get_profile_scraper
    rp.install()
    return orig_enrich, orig_get


def test_replay_enrich_builds_history_as_of_and_restores(monkeypatch):
    entries = {"C127": [
        {"date": "05/02/2023", "venue_track": "沙田草地", "distance": 1400, "class_grade": "4", "placing": 2, "jockey": "A", "weight_carried": 120, "rating": 50},
        {"date": "15/01/2023", "venue_track": "跑馬地草地", "distance": 1200, "class_grade": "4", "placing": 5, "jockey": "A", "weight_carried": 120, "rating": 50},
        {"date": "01/01/2023", "venue_track": "沙田全天候跑道", "distance": 1650, "class_grade": "4", "placing": 1, "jockey": "B", "weight_carried": 118, "rating": 48},
    ]}
    horses = {"1": {"horse_name": "跑得威", "jockey": "A", "trackwork": {"x": 1}}, "2": {"horse_name": "冇紀錄", "jockey": "C"}}
    orig_enrich, orig_get = _install(monkeypatch, entries, {("2023-02-01", "跑得威"): "C127"})
    try:
        orch._enrich_profile_history(horses, as_of_date=date(2023, 2, 1))
    finally:
        monkeypatch.setattr(orch, "_enrich_profile_history", orig_enrich)
        monkeypatch.setattr(orch, "_get_profile_scraper", orig_get)
    hist = horses["1"]["_data"]["hk_history"]
    assert [h["date"] for h in hist] == ["2023-01-15", "2023-01-01"]       # 02-05 係之後，唔准見到
    assert [h["surface"] for h in hist] == ["谷草", "泥地"]
    assert horses["1"]["_data"]["prev_distance"] == 1200
    assert horses["1"]["trackwork"] == {"x": 1}                              # horseid 已還原
    assert "trackwork" not in horses["2"] and "_data" not in horses["2"]


def test_replay_scraper_never_uses_network(monkeypatch):
    import requests

    def boom(*a, **k):
        raise AssertionError("回放唔准上網")
    monkeypatch.setattr(requests, "get", boom)
    monkeypatch.setattr(rp, "_archive", lambda: {"C1": []})
    assert rp._scraper("C1")["entries"] == []
