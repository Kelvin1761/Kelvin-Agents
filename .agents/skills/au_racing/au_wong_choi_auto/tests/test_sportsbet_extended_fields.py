"""Sportsbet raw fields must survive extraction without entering scoring by accident."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
AU_RACING = ROOT / ".agents" / "skills" / "au_racing"
ENGINE = AU_RACING / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(AU_RACING))
sys.path.insert(0, str(ENGINE.parent))

from claw_sportsbet_form import (  # noqa: E402
    parse_race,
    parse_runner_blocks,
    run_line,
    write_meeting,
)
from au_racing_engine.engine_core import _parse_formguide_entries, _parse_time_to_seconds  # noqa: E402


def _history(in_running: str) -> str:
    return (
        "Randwick ( Soft 6 ) 06/06/2026 Race 5 2000m 3Y BM72 "
        "Finished 8/10 4.15L $3,500 (of $160,000), Jockey Nash Rawiller, "
        "Barrier 10, Weight 60.0kg 11.00 "
        f"In running {in_running} Sectionals 600m 35.110s "
        "1st Decalogue (Chad Schofield 56.0kg) Winning Time 2:05.790 "
        "2nd Agent Zero (Jason Collett 57.0kg) 0.2L "
        "3rd Matias (Tommy Berry 56.5kg) 0.4L"
    )


class InRunningCheckpointTest(unittest.TestCase):
    def test_1200_checkpoint_does_not_drop_the_whole_position_chain(self):
        run = parse_race(_history(
            "Settled 3rd, 1200m 3rd, 800m 5th, 400m 7th"
        ))["runs"][0]
        self.assertEqual(
            {key: run[key] for key in ("settled", "p1200", "p800", "p400")},
            {"settled": "3rd", "p1200": "3rd", "p800": "5th", "p400": "7th"},
        )
        self.assertEqual(run["winning_time"], "2:05.790")
        line, _ = run_line(run)
        self.assertIn("3rd@1200m 5th@800m 7th@400m 3rd@Settled", line)
        self.assertIn("WinningTime:2:05.790", line)
        self.assertIn("RaceClass:[3Y BM72]", line)

    def test_a_400m_only_position_is_still_kept(self):
        run = parse_race(_history("400m 2nd"))["runs"][0]
        self.assertEqual(run["p400"], "2nd")
        self.assertIsNone(run["p800"])
        self.assertIn("2nd@400m", run_line(run)[0])

    def test_a_winner_has_zero_margin_instead_of_missing_evidence(self):
        html = _history("Settled 2nd, 800m 2nd, 400m 1st").replace(
            "Finished 8/10 4.15L", "Finished 1/10"
        )
        run = parse_race(html)["runs"][0]
        self.assertEqual(run["margin"], "0")
        self.assertIn("margin:0L", run_line(run)[0])

    def test_a_displayed_winning_margin_is_not_a_beaten_margin(self):
        html = _history("Settled 2nd, 800m 2nd, 400m 1st").replace(
            "Finished 8/10 4.15L", "Finished 1/10 5.75L"
        )
        run = parse_race(html)["runs"][0]
        self.assertEqual(run["margin"], "0")
        self.assertIn("margin:0L", run_line(run)[0])

    def test_archived_formguide_winner_margin_is_normalised(self):
        section = (
            "Randwick R2 2026-07-20 1400m cond:Good $150000 J Doe (2) 57kg "
            "margin:5.75L starters:10 finish:1/10\n"
            "1-Test Horse (57kg), 2-Rival (57kg) 5.75L\n"
        )
        entry = _parse_formguide_entries(section, "Test Horse")[0]
        self.assertEqual(entry["finish_pos"], 1)
        self.assertEqual(entry["margin"], 0.0)

    def test_finish_token_keeps_non_top3_trial_position(self):
        section = (
            "Southside Cranbourne **(TRIAL)** R4 2026-07-20 1000m cond:Good "
            "$0 J Doe (2) 57kg margin:4.2L starters:8 finish:5/8\n"
            "1-Rival (57kg), 2-Other (57kg) 1.0L, 3-Third (57kg) 2.0L\n"
        )
        entry = _parse_formguide_entries(section, "Test Horse")[0]
        self.assertTrue(entry["is_trial"])
        self.assertEqual(entry["finish_pos"], 5)


class RunnerProfileTest(unittest.TestCase):
    HTML = """
    <div>Engine Of War</div><div>(7)</div><div>T</div><div>W</div><div>58.5kg</div>
    <div class="runner-comment"><strong>Gear Changes:</strong>
      <span>Cross-over Nose Band FIRST TIME</span></div>
    <div><span>3 year old bay gelding (male)</span><br><span>Foaled:</span> 05/11/2022</div>
    <div><span>Sire:</span> Circus Maximus<br><span>Dam:</span> Prove Your Worth</div>
    <div><span>Breeder:</span> Ben Kwok<br><span>Colours:</span> Red and Black</div>
    <div>Career</div><div>4: 1-0-1</div>
    """

    def test_pedigree_identity_and_gear_are_extracted(self):
        block = parse_runner_blocks(self.HTML)[0]
        self.assertEqual(block["stats"]["Weight"], "58.5kg")
        self.assertEqual(
            block["profile"],
            {
                "gear_changes": "Cross-over Nose Band FIRST TIME",
                "foaled": "05/11/2022",
                "sire": "Circus Maximus",
                "dam": "Prove Your Worth",
                "breeder": "Ben Kwok",
                "colours": "Red and Black",
            },
        )

    def test_writer_keeps_gear_report_only(self):
        block = parse_runner_blocks(self.HTML)[0]
        parsed = {
            "meta": {"distance": 1400, "track_condition": "Good 4"},
            "overview": {7: {"name": "Engine Of War", "fixed_win": "-"}},
            "runs": [],
            "text": "",
        }
        with tempfile.TemporaryDirectory() as directory:
            write_meeting(
                [(1, parsed, [block])], directory, "2026-08-09", "Randwick",
                verbose=False,
            )
            formguide = next(Path(directory).glob("*Formguide.md")).read_text()
        self.assertIn("Sire: Circus Maximus | Dam: Prove Your Worth", formguide)
        self.assertIn("SportsbetGear: Changes: Cross-over Nose Band FIRST TIME", formguide)
        self.assertNotIn("\nGear:", formguide)


class RaceMetadataAndTimeTest(unittest.TestCase):
    def test_event_name_supplies_distance_and_race_class(self):
        html = (
            '<html><head><title>Randwick Race 5</title></head><body>'
            '<div class="eventname"><span title="FOUNDATION FEMALE MEMBER HANDICAP">'
            '2000m FOUNDATION FEMALE MEMBER HANDICAP.</span></div></body></html>'
        )
        meta = parse_race(html)["meta"]
        self.assertEqual(meta["distance"], 2000)
        self.assertEqual(meta["race_class"], "FOUNDATION FEMALE MEMBER HANDICAP")

    def test_one_digit_minute_winning_time_is_valid(self):
        self.assertEqual(_parse_time_to_seconds("WinningTime:1:52.590"), 112.59)
        section = (
            "Randwick R5 2026-06-06 1800m cond:Soft $160000 J (2) 58kg "
            "WinningTime:1:52.590 starters:10.\n"
        )
        self.assertEqual(
            _parse_formguide_entries(section, "Test Horse")[0]["winner_time_seconds"],
            112.59,
        )


class SubMinuteWinningTimeTests(unittest.TestCase):
    """跑少過一分鐘嘅賽事寫 `Winning Time 58.420`（冇 `M:`）。

    2026-08-31：舊 regex 硬要 `M:SS.mmm`，於是**所有短途賽**（≈≤1000m）嘅冠軍
    時間靜靜咁被丟走。實測 60 個 cache 頁面 2,603 個 `Winning Time`：捉到
    1,868、漏走 735 = **28.2%**，而漏走嘅每一個都係 <60 秒（54.810 … 59.770）
    —— 唔係隨機丟失，係同距離相關嘅系統性偏差。修完 71.5% → 99.0%。

    同 `Settled` / `L600 Delta` / 試閘 header / finish 名次 / `margin` 的 `L`
    一模一樣嘅失敗模式，第七次。
    """

    def test_regex_accepts_both_shapes(self):
        from claw_sportsbet_form import RE_WINNING_TIME
        cases = {
            "Winning Time 1:13.370": "1:13.370",   # 有分鐘
            "Winning Time 58.420": "58.420",       # 冇分鐘 ← 舊 regex 漏走
            "Winning Time 59.08": "59.08",         # 兩位小數
            "Winning Time 2:05.150": "2:05.150",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                m = RE_WINNING_TIME.search(text)
                self.assertIsNotNone(m, f"{text} 應該 match")
                self.assertEqual(m.group("time"), expected)

    def test_regex_still_rejects_garbage(self):
        from claw_sportsbet_form import RE_WINNING_TIME
        for text in ("Winning Time abc", "Winning Time", "Winning Time 58"):
            with self.subTest(text=text):
                self.assertIsNone(RE_WINNING_TIME.search(text))

    def test_sub_minute_time_survives_to_the_form_line(self):
        """由 parse 到 form line 都唔可以掉。"""
        from claw_sportsbet_form import RE_WINNING_TIME, run_line
        m = RE_WINNING_TIME.search("Winning Time 58.420")
        run = {"header": {"track": "Ballarat", "dist": "1000", "going": "Good",
                          "race": "3", "cls": "MDN", "date": "01/08/2026"},
               "jockey": "A Jockey", "barrier": "4", "weight": "57.0",
               "pos": "2", "field": "9", "margin": "1.2",
               "winning_time": m.group("time")}
        # `run_line` 返 (往績行, 對手行) tuple，唔係 string。
        line, _opponents = run_line(run)
        self.assertIn("WinningTime:58.420", line)


if __name__ == "__main__":
    unittest.main()
