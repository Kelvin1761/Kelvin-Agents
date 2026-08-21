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


if __name__ == "__main__":
    unittest.main()
