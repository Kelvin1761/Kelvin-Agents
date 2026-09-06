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


class GearSourcePrecedenceTests(unittest.TestCase):
    """配備變更：抽取兩個缺陷 + 來源優先次序。

    2026-09-07（`docs/audits/AU_TRACK_JHF_DATA_QUALITY_2026-09-05.md`）：
    `claw_sportsbet_form` 寫落 Formguide 嘅係 `SportsbetGear: Changes: …`，
    而 parser 要 `^Gear:` —— `^` 錨定令佢**永遠對唔上**，`gear_line` 全語料
    8,224 匹 **0% 有值**（key 100% 存在）。而 `has_blinkers` 查嘅
    `Blinkers: Yes` 呢個格式**根本唔存在**（真實文字係 `Blinkers FIRST TIME`）。

    來源優先：2,366 個 runner 位實測，只有 Formguide 有 94 匹、只有 Racecard
    有 **0** 匹，而兩邊都有嗰 434 匹入面 140 匹（32%）Racecard 截短咗。
    """

    def _summary(self, section: str):
        from au_racing_engine.engine_core import _summarize_formguide_section
        return _summarize_formguide_section(section, "Test Horse")

    def test_the_sportsbet_prefix_is_accepted(self) -> None:
        d = self._summary(
            "[3] Test Horse (3)\n"
            "SportsbetGear: Changes: Blinkers FIRST TIME, Tongue Tie OFF\n"
        )
        self.assertEqual(d["gear_line"], "Blinkers FIRST TIME, Tongue Tie OFF")

    def test_the_bare_racecard_prefix_still_works(self) -> None:
        d = self._summary("[3] Test Horse (3)\nGear: Winkers FIRST TIME\n")
        self.assertEqual(d["gear_line"], "Winkers FIRST TIME")

    def test_no_gear_line_stays_empty(self) -> None:
        self.assertEqual(self._summary("[3] Test Horse (3)\nFlucs:$- $4.60\n")["gear_line"], "")

    def test_a_run_comment_mentioning_gear_is_not_picked_up(self) -> None:
        # 行頭錨定：往績行同備註都可能提到配備，只有行頭嗰個先係今仗公告。
        d = self._summary("[3] Test Horse (3)\nNote: raced without Gear: blinkers today\n")
        self.assertEqual(d["gear_line"], "")

    def test_blinkers_detection_uses_the_real_wording(self) -> None:
        for text, expected in (
            ("Blinkers FIRST TIME", True),
            ("Blinkers AGAIN", True),
            ("Blinkers OFF", False),
            ("Blinkers OFF FIRST TIME", False),
            ("Tongue Tie FIRST TIME", False),
            ("", False),
        ):
            d = self._summary(f"[3] Test Horse (3)\nSportsbetGear: Changes: {text}\n")
            self.assertEqual(d["has_blinkers"], expected, text)


class GearStaysOutOfScoringTests(unittest.TestCase):
    """配備變更**唔准入分**。

    EXP-20260826-07 REJECT：訊號真（除下配備 −3.86pp [−6.94, −0.75]）但同
    `form_score` 重複（有變更嘅馬 form 平均 59.83 vs 62.10），四個扣分幅度
    冇一個過閘。修好 regex 之前 `health_score` 有兩個 gear 分支，佢哋因為
    `gear_line` 一直空所以由來冇 fire 過 —— regex 一修好就會突然生效，
    所以一併剷走。呢個 test 就係防止有人「順手」加返。
    """

    def _health(self, gear_line: str, gear_changes: str = "") -> float:
        from au_racing_engine.engine_core import RacingEngine
        horse = {
            "horse_name": "T", "horse_number": "1",
            "jockey": "J", "trainer": "T",
            "_data": {"gear_line": gear_line, "gear_changes": gear_changes},
        }
        return RacingEngine(horse, {
            "distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
        })._health_score()[0]

    def test_gear_does_not_move_the_health_score(self) -> None:
        base = self._health("")
        for gear in ("Blinkers FIRST TIME", "Blinkers OFF FIRST TIME",
                     "Tongue Tie FIRST TIME, Winkers OFF"):
            self.assertEqual(self._health(gear, gear), base, gear)

    def test_the_source_note_no_longer_claims_gear(self) -> None:
        from au_racing_engine.engine_core import RacingEngine
        horse = {"horse_name": "T", "horse_number": "1", "jockey": "J",
                 "trainer": "T", "_data": {"gear_line": "Blinkers FIRST TIME"}}
        _score, _text, source = RacingEngine(horse, {
            "distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"},
        })._health_score()
        self.assertNotIn("gear", source)
