from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE))

from engine_core import _load_meeting_intelligence, _parse_meeting_intelligence  # noqa: E402


class MeetingIntelligenceFormatTests(unittest.TestCase):
    def test_inline_bold_header_and_chinese_sections(self) -> None:
        text = """# Meeting Intelligence Package
**Date:** 2026-04-04 | **Venue:** Randwick

## 預測掛牌 (Predicted Going)
Soft 5

## 官方掛牌 (Official Going)
Soft 6

## 跑道偏差 (Track Bias)
No clear bias known pre-meeting.

## 欄位 (Rail Position)
+3m Entire Circuit

## 天氣 (Weather)
Overcast 19°C
"""
        parsed = _parse_meeting_intelligence(text)
        self.assertEqual(parsed["venue"], "Randwick")
        self.assertEqual(parsed["date"], "2026-04-04")
        self.assertEqual(parsed["going"], "Soft 6")
        self.assertEqual(parsed["rail_position"], "+3m Entire Circuit")
        self.assertEqual(parsed["weather_summary"], "Overcast 19°C")
        self.assertNotIn("**", parsed["venue"])

    def test_current_bullet_generator_format(self) -> None:
        text = """# 🏟️ 賽事天氣與場地情報 (Meeting Intelligence Package)
## 📍 賽場基本資訊
- **賽場**: Cranbourne
- **日期**: 2026-04-24
- **移欄 (Rail)**: Out 9m Entire Circuit
- **天氣 (Weather)**: Overcast Clouds 21°C
- **場地狀況 (Track Condition)**: Good 4
"""
        parsed = _parse_meeting_intelligence(text)
        self.assertEqual(parsed["venue"], "Cranbourne")
        self.assertEqual(parsed["date"], "2026-04-24")
        self.assertEqual(parsed["going"], "Good 4")
        self.assertEqual(parsed["rail_position"], "Out 9m Entire Circuit")
        self.assertEqual(parsed["weather_summary"], "Overcast Clouds 21°C")

    def test_original_bilingual_format_remains_supported(self) -> None:
        text = """# Warwick Farm Meeting Intelligence Package
Date: 2026-05-06
Venue: Warwick Farm

## Weather / 天氣狀況
Clear Sky, 18°C.

## Track Condition / 場地狀況
Track condition extracted: Soft 5 (Turf).
Rail position (欄位): True.

## Track Bias / 賽道偏差預測
Relatively fair.

## Sources / 資料來源
Official extractor.
"""
        parsed = _parse_meeting_intelligence(text)
        self.assertEqual(parsed["venue"], "Warwick Farm")
        self.assertEqual(parsed["date"], "2026-05-06")
        self.assertEqual(parsed["going"], "Soft 5")
        self.assertEqual(parsed["rail_position"], "True")
        self.assertIn("Clear Sky", parsed["weather_summary"])

    def test_fallback_venue_is_used_when_package_omits_identity(self) -> None:
        parsed = _parse_meeting_intelligence(
            "## 官方掛牌 (Official Going)\nHeavy 8\n",
            "Eagle Farm",
        )
        self.assertEqual(parsed["venue"], "Eagle Farm")
        self.assertEqual(parsed["going"], "Heavy 8")

    def test_compact_chinese_format_uses_embedded_date(self) -> None:
        parsed = _parse_meeting_intelligence(
            "# Randwick Meeting Intelligence\n"
            "- 賽事：Randwick 2026-04-11\n"
            "- 場地：Good 4\n"
            "- 偏差：內外欄公平\n",
            "Randwick",
        )
        self.assertEqual(parsed["venue"], "Randwick")
        self.assertEqual(parsed["date"], "2026-04-11")
        self.assertEqual(parsed["going"], "Good 4")

    def test_chinese_value_with_english_going_is_canonicalised(self) -> None:
        parsed = _parse_meeting_intelligence(
            "# Warwick Farm 2026-04-15 Meeting Intelligence\n"
            "- **賽道 (Track):** Warwick Farm\n"
            "- **跑道狀況 (Track Condition):** 好地 (Good 4)\n"
            "- **移欄 (Rail Position):** +3m Entire\n"
        )
        self.assertEqual(parsed["venue"], "Warwick Farm")
        self.assertEqual(parsed["date"], "2026-04-15")
        self.assertEqual(parsed["going"], "Good 4")
        self.assertEqual(parsed["rail_position"], "+3m Entire")

    def test_current_racecard_going_overrides_older_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-04-04 Randwick Race 1-1"
            meeting.mkdir()
            facts = meeting / "04-04 Race 1 Facts.md"
            facts.write_text("# Facts\n", encoding="utf-8")
            (meeting / "_Meeting_Intelligence_Package.md").write_text(
                "**Date:** 2026-04-04 | **Venue:** Randwick\n"
                "## 官方掛牌 (Official Going)\nSoft 6\n",
                encoding="utf-8",
            )
            (meeting / "04-04 Race 1 Racecard.md").write_text(
                "RACE 1\nTrack: Soft 7 | Weather: Light Rain | Rail: True\n",
                encoding="utf-8",
            )
            parsed = _load_meeting_intelligence(facts, 1)
        self.assertEqual(parsed["venue"], "Randwick")
        self.assertEqual(parsed["date"], "2026-04-04")
        self.assertEqual(parsed["going"], "Soft 7")

    def test_package_fills_unknown_racecard_going(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            meeting = Path(tmp) / "2026-04-03 Ballarat Race 1-1"
            meeting.mkdir()
            facts = meeting / "04-03 Race 1 Facts.md"
            facts.write_text("# Facts\n", encoding="utf-8")
            (meeting / "_Meeting_Intelligence_Package.md").write_text(
                "**Date:** 2026-04-03 | **Venue:** Ballarat\n"
                "## 官方掛牌 (Official Going)\nGood 4\n",
                encoding="utf-8",
            )
            (meeting / "04-03 Race 1 Racecard.md").write_text(
                "RACE 1\nTrack: Unknown | Weather: Unknown | Rail: True\n",
                encoding="utf-8",
            )
            parsed = _load_meeting_intelligence(facts, 1)
        self.assertEqual(parsed["going"], "Good 4")


if __name__ == "__main__":
    unittest.main()
