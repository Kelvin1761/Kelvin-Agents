"""配備變更由 Racecard 一路帶到報告，而且**唔准**影響評分。

點解要鎖：呢個訊號係真嘅（除下 OFF FIRST TIME −3.86pp [−6.94,−0.75]，817 場）
但同 `form_score` 重複（有變更嘅馬 form 平均 59.83 vs 冇嘅 62.10），所以刻意
只出報告唔入排名（EXP-20260826-07）。如果將來有人「順手」把佢餵入 leaf，
呢個測試會爆。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "au_racing"))

from au_racing_engine.engine_core import _load_racecard_profiles  # noqa: E402

RACECARD = """RACE 1 — 1200m | TEST HANDICAP
Track: Good 4 | Weather: Fine | Rail: True
============================================================
1. Alpha Horse (3)
Trainer: A Trainer | Jockey: A Jockey | Weight: 58.0kg | Age: 4yoG | Rating: 72
Career: 10 : 2-1-1 | Win: 20% | Place: 40%
Gear: Blinkers OFF FIRST TIME
Silk: https://example.invalid/a.svg
----------------------------------------
2. Beta Horse (7)
Trainer: B Trainer | Jockey: B Jockey | Weight: 56.0kg | Age: 5yoM | Rating: 66
Career: 8 : 1-2-0 | Win: 12% | Place: 37%
Silk: https://example.invalid/b.svg
----------------------------------------
"""


class GearChangeTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        d = Path(self.tmp.name)
        (d / "08-26 Race 1 Racecard.md").write_text(RACECARD, encoding="utf-8")
        self.facts = d / "08-26 Race 1 Facts.md"
        self.facts.write_text("placeholder", encoding="utf-8")

    def test_gear_change_is_parsed_for_the_right_horse(self) -> None:
        profiles = _load_racecard_profiles(self.facts, 1)
        self.assertTrue(profiles, "Racecard profiles 讀唔到")
        alpha = next(v for k, v in profiles.items() if "alpha" in k)
        beta = next(v for k, v in profiles.items() if "beta" in k)
        self.assertEqual(alpha.get("gear_change"), "Blinkers OFF FIRST TIME")
        # 冇 Gear: 行嘅馬唔可以「借」到隔籬匹嘅
        self.assertIsNone(beta.get("gear_change"))

    def test_gear_line_does_not_break_rating_or_weight(self) -> None:
        """`Silk:` 嗰個註釋警告過：插錯位會令官方讓磅分靜靜消失。"""
        profiles = _load_racecard_profiles(self.facts, 1)
        alpha = next(v for k, v in profiles.items() if "alpha" in k)
        self.assertEqual(alpha["horse_rating"], 72.0)
        self.assertEqual(alpha["declared_weight"], 58.0)

    def test_gear_change_is_not_a_scored_leaf(self) -> None:
        from au_racing_engine.matrix_mapper import MATRIX_FORMULAS
        leaves = {n for comps in MATRIX_FORMULAS.values() for n, _ in comps}
        self.assertNotIn("gear_change", leaves)
        self.assertNotIn("gear_score", leaves)

    def test_scraper_extracts_gear_from_race_html(self) -> None:
        import claw_sportsbet_form as claw
        html = ('<html><head><title>Testville Race 3</title></head><body>'
                '<a class="anchorlink" href="#01">Alpha Horse</a> Blinkers OFF FIRST TIME. '
                '<a class="anchorlink" href="#02">Beta Horse</a> Tongue Tie FIRST TIME.'
                '</body></html>')
        gear = (claw.parse_race(html).get("meta") or {}).get("gear_changes") or {}
        self.assertEqual(gear.get("Alpha Horse"), "Blinkers OFF FIRST TIME")
        self.assertEqual(gear.get("Beta Horse"), "Tongue Tie FIRST TIME")


if __name__ == "__main__":
    unittest.main()
