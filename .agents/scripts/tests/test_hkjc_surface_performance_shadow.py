from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


facts = _load("inject_hkjc_fact_anchors_surface_test", ROOT / ".agents/scripts/inject_hkjc_fact_anchors.py")
logic = _load(
    "create_hkjc_logic_skeleton_surface_test",
    ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py",
)


def _race(date: str, venue: str, distance: int, finish: int, field_size: int = 12) -> dict:
    return {
        "date_dt": datetime.strptime(date, "%Y-%m-%d"),
        "venue": venue,
        "distance": distance,
        "finish": finish,
        "field_size": field_size,
    }


def test_surface_shadow_separates_st_turf_hv_and_awt() -> None:
    payload = facts.compute_surface_performance_shadow(
        [
            _race("2026-05-01", "沙田草地", 1200, 1),
            _race("2026-05-08", "跑馬地", 1200, 12),
            _race("2026-05-15", "沙田全天候", 1200, 2),
        ],
        today_venue="沙田AWT",
        today_dist=1200,
        race_date="2026-06-01",
    )

    assert payload["target"] == "沙田AWT"
    assert payload["surfaces"]["沙田草地"]["runs"] == 1
    assert payload["surfaces"]["跑馬地草地"]["runs"] == 1
    assert payload["surfaces"]["沙田AWT"]["runs"] == 1
    assert payload["surfaces"]["沙田AWT"]["score"] > 60.0


def test_surface_shadow_is_strictly_point_in_time_and_distance_matched() -> None:
    payload = facts.compute_surface_performance_shadow(
        [
            _race("2026-04-01", "跑馬地", 1200, 1),
            _race("2026-05-01", "跑馬地", 1650, 1),
            _race("2026-06-02", "跑馬地", 1200, 1),
        ],
        today_venue="跑馬地",
        today_dist=1200,
        race_date="2026-06-01",
    )

    target = payload["surfaces"]["跑馬地草地"]
    assert target["runs"] == 1
    assert target["score"] > 60.0


def test_surface_shadow_missing_history_is_neutral() -> None:
    payload = facts.compute_surface_performance_shadow(
        [], today_venue="沙田", today_dist=1400, race_date="2026-06-01"
    )
    assert payload["target"] == "沙田草地"
    assert payload["target_score"] == 60.0
    assert payload["target_effective_n"] == 0.0


def test_surface_shadow_round_trips_from_facts_summary() -> None:
    line = (
        "- **個別場地性能 (Shadow):** 今場=跑馬地草地 64.2分 | "
        "沙田草地 58.0分(有效樣本2.0/原始3) | 暫不入分"
    )
    parsed = logic.parse_summary(line)
    assert parsed["surface_performance_shadow"].startswith("今場=跑馬地草地 64.2分")


def test_pdf_overseas_parser_ignores_local_form_and_keeps_surface() -> None:
    text = """本地往績
1 錶之極光 K97
2/9 *621 19/4/26 3 85-60 泥 — 1200 GD 130

Overseas Form of 24/25, 25/26 & 26/27 PPs declared to start today (Last 10 starts)
錶之極光 AURORA PATCH (AUS) K97 6 br g Kwyjibo 1 start 1-0-0-0-0
6/6/2024 AUS Wyong, NSW RH 1100 H 1/6 - Mdn Hcp 130 1.05.69 +1.74L
螢影飛馳 FLYING TING LOK (AUS) K228 6 br g Flying Ting Lok 2 starts 1-1-0-0-0
20/7/2024 AUS Gold Coast, QLD RH 1200 Synthetic 2/8 - Mdn Hcp 126 1.08.48 -6L SR
27/7/2024 AUS Gold Coast, QLD RH 1100 Synthetic 1/8 - Mdn 121 1.04.28 +0.5L
"""
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / "meeting.pdf.md"
        pdf.write_text(text, encoding="utf-8")
        rows = facts.parse_pdf_overseas_races(pdf, "K0228", "螢影飛馳")

    assert len(rows) == 2
    assert rows[0]["Racecourse"] == "Gold Coast, QLD"
    assert rows[0]["Surface"] == "SYNTHETIC"
    assert rows[0]["Distance"] == 1200
    assert rows[0]["Placing"] == 2
    assert rows[0]["Field_Size"] == 8


def test_foreign_dirt_is_only_used_as_awt_fallback_without_local_history() -> None:
    overseas = [
        {
            "Date": "08/06/2025",
            "Surface": "DIRT",
            "Distance": 1200,
            "Placing": 1,
            "Field_Size": 8,
        }
    ]
    payload = facts.compute_surface_performance_shadow(
        [],
        today_venue="沙田AWT",
        today_dist=1200,
        race_date="2026-06-01",
        overseas_races=overseas,
    )
    assert payload["fallback_source"] == "foreign_dirt_synthetic"
    assert payload["foreign_awt"]["runs"] == 1
    assert payload["target_score"] > 60.0

    local_payload = facts.compute_surface_performance_shadow(
        [_race("2026-05-01", "沙田全天候", 1200, 12)],
        today_venue="沙田AWT",
        today_dist=1200,
        race_date="2026-06-01",
        overseas_races=overseas,
    )
    assert local_payload["fallback_source"] == "local_history"
    assert local_payload["target_score"] < 60.0


def test_new_overseas_table_round_trips_structured_surface() -> None:
    block = """🌍 **海外賽績 (來自 PDF):**
| # | 日期 | 地區 | 馬場 | 表面 | 路程 | 場地 | 賽事 | 名次/馬匹數 | 負磅 | 締速 | 勝負距離 |
|---|------|------|------|------|------|------|------|-------------|------|------|----------|
| 1 | 20/07/2024 | AUS | Gold Coast, QLD | SYNTHETIC | 1200 | Synthetic | Mdn Hcp | 2/8 | 126 | 1.08.48 | -6L |
"""
    rows = logic.parse_overseas_races_table(block)
    assert rows == [
        {
            "date": "20/07/2024",
            "region": "AUS",
            "racecourse": "Gold Coast, QLD",
            "surface": "SYNTHETIC",
            "distance": "1200",
            "going": "Synthetic",
            "class_level": "Mdn Hcp",
            "rank": "2/8",
            "placing": "2",
            "field_size": "8",
            "weight": "126",
            "time": "1.08.48",
            "margin": "-6L",
        }
    ]
