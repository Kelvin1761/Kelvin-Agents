"""濕地往績調整嘅報告明細一定要同入分嗰個數一樣（2026-11-03：加總行之前漏印咗佢，加極都唔等於綜合分）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine import track_going as tg  # noqa: E402
from au_racing_engine.scoring import wet_form_feature  # noqa: E402

LINE = "3:1-0-0 | 軟地: 6:0-4-1 | 重地: 3:1-1-0"


class WetOverlayDisplayTests(unittest.TestCase):
    def test_dry_going_has_no_detail(self) -> None:
        self.assertIsNone(tg.wet_overlay_detail("Good 4", LINE))
        self.assertEqual(tg.wet_overlay_line(None), "")

    def test_detail_value_matches_ranking_feature(self) -> None:
        for going in ("Soft 5", "Soft 7", "Heavy 8"):
            detail = tg.wet_overlay_detail(going, LINE)
            self.assertEqual(detail["value"], wet_form_feature(going, LINE))

    def test_heavy_day_counts_heavy_in_full(self) -> None:
        detail = tg.wet_overlay_detail("Heavy 8", LINE)
        self.assertEqual((detail["today_bucket"], detail["today_record"]), ("重地", [3, 2]))
        self.assertEqual((detail["other_bucket"], detail["other_record"]), ("軟地", [6, 5]))
        self.assertIn("重地 3 戰 2 上名（全計）", tg.wet_overlay_line(detail))

    def test_no_wet_starts_reads_neutral(self) -> None:
        detail = tg.wet_overlay_detail("Soft 6", "5:1-1-0")
        self.assertIn("未有濕地出賽", tg.wet_overlay_line(detail))


if __name__ == "__main__":
    unittest.main()
