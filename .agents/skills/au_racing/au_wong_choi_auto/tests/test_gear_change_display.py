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


class HealthScoreIsSpellOnlyTests(unittest.TestCase):
    """`health_score` 唯一活住嘅輸入係「距上仗日數」—— 呢個 test 講明實情。

    2026-09-07 實測 8,224 匹：分數只有 59 / 60 / 61，全部嚟自 spell 分支。
    三個警告／獸醫分支同「久休但有試閘時間」rescue 剷走咗，因為**來源冇資料**：
      * `Stewards:` / `Note:` / `Video:` 各 21,127 行、**0.0% 有內容**
      * `warning_line` 個 key 由來唔存在
      * 獸醫字眼掃描 100% 假陽性（馬名／父母名：`Heart Of Vienna`、`Vetoed`、
        母系 `Cardiac`、`Lamerican`）
      * `timing_trial_600m_avg_speed` 0% 有值；5,513 條試閘行冇一條有 L600 數字

    順帶封住一個地雷：舊 `warning_text` 包住 `gear_line`，而配備抽取
    2026-09-07 由 0% 修到 22.3%（590 種文字）。今日冇撞（2,351 匹實測乾淨），
    但 substring 比對 + 活數據 = 將來一個配備名含 `vet`／`heart` 就靜靜扣分。
    """

    def _engine(self, data: dict, *, day: str = "2026-09-04"):
        from au_racing_engine.engine_core import RacingEngine
        horse = {"horse_name": "T", "horse_number": "1",
                 "jockey": "J", "trainer": "Tr", "_data": data}
        return RacingEngine(horse, {
            "distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4", "date": day},
            "date": day,
        })

    def test_only_the_spell_gap_moves_the_score(self) -> None:
        # 場次日期 = 2026-09-04
        for last_run, expected, why in (
            ("2026-08-31", 60.0, "4 日 —— 太密，唔喺 14-45"),
            ("2026-08-25", 60.0, "10 日 —— 仍然唔夠 14"),
            ("2026-08-21", 61.0, "14 日 —— 區間下界，+1.0"),
            ("2026-08-15", 61.0, "20 日 —— 區間中間"),
            ("2026-07-21", 61.0, "45 日 —— 區間上界"),
            ("2026-07-20", 60.0, "46 日 —— 過咗界，中性"),
            ("2026-06-06", 60.0, "90 日 —— 啱啱唔扣（門檻係 >90）"),
            ("2026-06-05", 59.0, "91 日 —— 過咗門檻，−1.0"),
            ("2026-05-01", 59.0, "126 日 —— 久休 −1.0"),
        ):
            got = self._engine({"latest_official_date": last_run})._health_score()[0]
            self.assertEqual(got, expected, f"{last_run}（{why}）")

    def test_a_gear_name_containing_a_vet_token_cannot_dock_the_score(self) -> None:
        # 呢個就係剷走 substring 掃描要防嘅嘢。
        for gear in ("Velvet Nose Roll FIRST TIME", "Heart Monitor FIRST TIME",
                     "Lame Duck Bit FIRST TIME"):
            self.assertEqual(
                self._engine({"latest_official_date": "2026-08-31",
                              "gear_line": gear, "gear_changes": gear})._health_score()[0],
                60.0, gear)

    def test_a_warning_line_no_longer_docks_the_score(self) -> None:
        # 欄位由來唔存在；就算有人將來填佢，都唔應該由呢個 leaf 靜靜扣分。
        self.assertEqual(
            self._engine({"latest_official_date": "2026-08-31",
                          "warning_line": "vet examined, lame"})._health_score()[0], 60.0)

    def test_the_source_tag_says_what_it_measures(self) -> None:
        _s, text, source = self._engine(
            {"latest_official_date": "2026-08-31"})._health_score()
        self.assertEqual(source, "spell_only")
        self.assertIn("出賽間隔分", text)
        self.assertNotIn("健康", text)


class VideoNoteStewardsNewlineTests(unittest.TestCase):
    """空欄位唔准跳去捕捉下一行。

    2026-09-07：原本用 `^Video:\\s*(.+?)$`，而 `\\s` **包括換行**。Sportsbet
    三個欄實測 21,127 行 **0.0% 有內容**，於是空欄位captures 下一行：
        Video → `'Note:'`、Note → `'Stewards:'`、
        Stewards → `'====…'` 甚至 `'Belmont **(TRIAL)** R10 '`（下一場標題）
    呢個就係 Facts「備註」欄 73,452 行 100% 都係 `Note:; Stewards:` 嘅成因 ——
    一個常數扮成「100% 有數據」。而 `stewards` 會餵入走位／跑法 token 掃描，
    所以污染係活嘅。實測 73,452 個 block：修前修後冇一個 token 命中改變。
    """

    PATS = ("Video", "Note", "Stewards")

    def _extract(self, block: str) -> dict:
        out = {}
        for k in self.PATS:
            m = re.search(rf"^{k}:[^\S\n]*(.+?)$", block, re.MULTILINE)
            out[k] = m.group(1).strip() if m else ""
        return out

    def test_empty_fields_stay_empty(self) -> None:
        got = self._extract("Video: \nNote: \nStewards: \n")
        self.assertEqual(got, {"Video": "", "Note": "", "Stewards": ""})

    def test_an_empty_field_does_not_capture_the_next_label(self) -> None:
        got = self._extract("Video: \nNote: \nStewards: \n")
        self.assertNotEqual(got["Video"], "Note:")
        self.assertNotEqual(got["Note"], "Stewards:")

    def test_an_empty_stewards_does_not_capture_the_next_race(self) -> None:
        block = ("Video: \nNote: \nStewards: \n\n"
                 "============================================================\n\n"
                 "Belmont **(TRIAL)** R10 2025-11-19 800m\n")
        self.assertEqual(self._extract(block)["Stewards"], "")

    def test_real_content_is_still_captured(self) -> None:
        block = ("Video: settled midfield, ran on well\n"
                 "Note: gelding operation since last start\n"
                 "Stewards: rider reported the gelding felt indifferent\n")
        got = self._extract(block)
        self.assertEqual(got["Video"], "settled midfield, ran on well")
        self.assertEqual(got["Note"], "gelding operation since last start")
        self.assertIn("indifferent", got["Stewards"])

    def test_leading_spaces_on_the_same_line_are_stripped(self) -> None:
        self.assertEqual(self._extract("Video:     led all the way\n")["Video"],
                         "led all the way")


class ForgivenessPlaceholderTests(unittest.TestCase):
    """「寬恕認定」寫 `[-]`，唔再寫 `[需判定]`。

    `[需判定]` 係 LLM 年代嘅 placeholder；轉全 Python 之後冇人接手，所以
    73,452 行 100% 都係佢 —— 一個「待判定」講咗成年冇人判，而
    `_confidence_score` 個「條件式」`-1` 因此每匹馬都中，變咗常數。

    試過真係判（EXP-20260908-01）：由走位軌跡推三個規則，7,658 個上仗大敗嘅
    樣本，今仗入位率按馬匹數校正 —— 尾段執位 −2.3pp、全程守後 **−11.1pp**、
    搶前消耗 −6.8pp。**三個都同「寬恕」方向相反**：走位形態量緊能力唔係運氣。
    真證據（受阻／被夾／大外無遮擋）住喺 stewards，而嗰欄 0.0% 有內容。
    """

    def test_the_writer_emits_the_no_forgiveness_token(self) -> None:
        repo = Path(__file__).resolve().parents[5]
        src = (repo / ".agents" / "scripts" / "inject_fact_anchors.py").read_text(
            encoding="utf-8")
        self.assertIn("{consumption} | {notes} | [-] |", src)
        self.assertNotIn("{consumption} | {notes} | [需判定] |", src)

    def test_the_token_must_stay_bracketed(self) -> None:
        # ⚠️ `_forgiveness_count()` 嘅排除集係 {"[-]", "[需判定]"}。寫成 `-`
        # 會令每一場都算「有寬恕」，反手㨂着 sectional 嗰個 7.46 分 bonus。
        from au_racing_engine.engine_core import RacingEngine
        eng = RacingEngine(
            {"horse_name": "T", "horse_number": "1", "jockey": "J",
             "trainer": "Tr", "_data": {}},
            {"distance": "1400m", "field_summary": {"count": 10},
             "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}})
        eng._official_entry_cache = [
            {"forgiveness": "[-]", "notes": "-"} for _ in range(4)]
        self.assertEqual(eng._forgiveness_count(), 0)
        eng._official_entry_cache = [
            {"forgiveness": "-", "notes": "-"} for _ in range(4)]
        self.assertEqual(eng._forgiveness_count(), 4,
                         "裸 `-` 會被當成有寬恕 —— 所以 writer 一定要寫 `[-]`")

    def test_confidence_no_longer_carries_the_constant_penalty(self) -> None:
        import inspect
        from au_racing_engine.engine_core import RacingEngine
        src = inspect.getsource(RacingEngine._confidence_score)
        self.assertNotIn("unresolved_forgiveness", src.split("#")[0] + "".join(
            ln for ln in src.splitlines() if not ln.strip().startswith("#")))
