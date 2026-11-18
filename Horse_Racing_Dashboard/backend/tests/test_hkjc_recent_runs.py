"""HKJC 近績格逐仗表（Kelvin 2026-11-18）：賽績.md ＋ 馬匹頁往績合併，純顯示。"""
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services import hkjc_recent_runs as rr  # noqa: E402

FORMGUIDE = """#### 全場馬匹分析 (Full Field Analysis)
馬號: 1
馬名: 禾道威

往績紀錄:
  [1] 08/11/2026 | 日數: 20 | 沙田 "C+3" 1800 好
      檔位: 14 | 馬重: 1213 | 負磅: 135 | 騎師: 潘頓 | 名次: 2 / 14
      能量: 92 | 分段時間: 14.46, 22.79, 24.68, 24.11, 23.77
      短評: 慢步速(-)(2W4W) 自大外檔出閘普通。
  [2] 19/10/2026 | 日數: 18 | 沙田 "C+3" 1800 好
      檔位: 8 | 馬重: 1218 | 負磅: 135 | 騎師: 潘頓 | 名次: 5 / 13
      能量: 91 | 分段時間: 14.37, 21.86, 23.57, 24.14, 23.84
      短評: 快步速;(1W4W) 出閘一般。
"""

PROFILE = [
    {"race_date_full": "2026/11/18", "race_no": 1, "racecourse": "HV", "date": "18/11/26", "placing_raw": "01"},
    {"race_date_full": "2026/11/08", "race_no": 1, "racecourse": "ST", "date": "08/11/26", "class_grade": "5",
     "rating": 40, "trainer": "大衛希斯", "margin_raw": "1", "_win_odds": 3.8,
     "running_positions_raw": "10 10 12 11 2", "finish_time_raw": "1.49.81", "gear": "CP/TT"},
]


def test_parse_formguide_reads_energy_sectionals_and_comment(tmp_path):
    p = tmp_path / "11-18 Race 1 賽績.md"
    p.write_text(FORMGUIDE, encoding="utf-8")
    runs = rr.parse_formguide(p)[1]
    assert [r["date"] for r in runs] == ["08/11/2026", "19/10/2026"]
    assert runs[0]["energy"] == "92" and runs[0]["placing"] == "2 / 14" and runs[0]["jockey"] == "潘頓"
    assert runs[0]["sectionals"].startswith("14.46")
    assert runs[1]["comment"] == "快步速;(1W4W) 出閘一般。"


def test_merge_adds_profile_fields_and_replay_link(tmp_path):
    p = tmp_path / "11-18 Race 1 賽績.md"
    p.write_text(FORMGUIDE, encoding="utf-8")
    row = rr.merge_runs(rr.parse_formguide(p)[1], PROFILE[1:])[0]
    assert row["rating"] == 40 and row["trainer"] == "大衛希斯" and row["positions"] == "10 10 12 11 2"
    assert "date=20261108&no=01" in row["replay_url"]
    assert "RaceNo=1" in row["result_url"]


def test_cache_fallback_never_shows_the_race_being_predicted(tmp_path, monkeypatch):
    meeting = tmp_path / "2026-11-18_HappyValley"
    (meeting / ".hkjc_cache").mkdir(parents=True)
    (meeting / "11-18 Race 1 賽績.md").write_text(FORMGUIDE, encoding="utf-8")
    (meeting / ".hkjc_cache" / "profile_cache.json").write_text(
        json.dumps({"HK_2023_J463": {"_ts": 0, "data": {"entries": PROFILE}}}), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(rr.Path, "home", staticmethod(lambda: tmp_path))
    rows = rr.load_meeting_recent_runs([meeting], {1: {1: "HK_2023_J463"}}, "2026-11-18")[1][1]
    assert [r["date"] for r in rows] == ["08/11/2026", "19/10/2026"]
    assert rows[0]["rating"] == 40


def test_logic_profile_runs_take_priority(tmp_path):
    meeting = tmp_path / "m"
    meeting.mkdir()
    (meeting / "11-18 Race 1 賽績.md").write_text(FORMGUIDE, encoding="utf-8")
    (meeting / "Race_1_Logic.json").write_text(json.dumps(
        {"horses": {"1": {"_data": {"profile_runs": [dict(PROFILE[1], rating=41)]}}}}), encoding="utf-8")
    rows = rr.load_meeting_recent_runs([meeting])[1][1]
    assert rows[0]["rating"] == 41


def test_incident_report_attached_by_brand_and_date(tmp_path):
    meeting = tmp_path / "2026-11-18_HappyValley"
    meeting.mkdir()
    (meeting / "11-18 Race 1 賽績.md").write_text(FORMGUIDE, encoding="utf-8")
    (tmp_path / "HKJC_Sections").mkdir()
    (tmp_path / "HKJC_Sections" / "incident_reports.json").write_text(json.dumps(
        {"version": 1, "horses": {"J463": {"2026-11-08": "早段搶口。", "2026-11-18": "今仗唔應該出現"}}}),
        encoding="utf-8")
    rows = rr.load_meeting_recent_runs([meeting], {1: {1: "HK_2023_J463"}}, "2026-11-18")[1][1]
    assert rows[0]["incident"] == "早段搶口。"
    assert "incident" not in rows[1]
