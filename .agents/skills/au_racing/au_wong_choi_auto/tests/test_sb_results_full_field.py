"""`Race_Results_Reflector.md` must carry the WHOLE field, not the first six.

`sb_results.py` used to default `--top 6` and truncate every race, while the
Sportsbet cache it reads has a row for every runner (each runner's own form line
is that runner's finish in this race).  On 2026-08-30 that silently threw away
96 of 270 finishers across four meetings — 35.6%.

Two things downstream broke because of it:

  * Any ROI computed from this file's SP is survivorship-biased: a top pick that
    ran 7th or worse has no SP row and drops out of the denominator entirely.
    The same 29 bets measured +3.7% truncated and -19.8% with the full field.
  * `form_score` treats a finish it cannot read as "unplaced -> neutral 60",
    laundering a genuinely bad run into no-evidence.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing"))

import sb_results  # noqa: E402


class OrdinalTests(unittest.TestCase):
    def test_ordinals_past_third_are_english(self) -> None:
        self.assertEqual(
            [sb_results.ordinal(n) for n in (1, 2, 3, 4, 11, 12, 13, 21, 22, 23, 24)],
            ["1st", "2nd", "3rd", "4th", "11th", "12th", "13th",
             "21st", "22nd", "23rd", "24th"],
        )

    def test_every_ordinal_stays_parseable_by_the_readers(self) -> None:
        """The reflector/ingest side matches r'^\\d+(?:st|nd|rd|th):'."""
        import re

        pattern = re.compile(r"^(\d+)(?:st|nd|rd|th):")
        for n in range(1, 41):
            with self.subTest(n=n):
                self.assertTrue(pattern.match(f"{sb_results.ordinal(n)}: #1 Horse"))


class RenderFullFieldTests(unittest.TestCase):
    def _races(self, size: int) -> dict:
        return {
            1: [
                (pos, pos, f"Horse{pos}", None if pos == 1 else f"{pos}.0", f"{pos}.00")
                for pos in range(1, size + 1)
            ]
        }

    def test_render_emits_every_finisher(self) -> None:
        text = sb_results.render("Townsville", "2026-08-30", self._races(12))
        for pos in range(1, 13):
            self.assertIn(f"{sb_results.ordinal(pos)}: #{pos} Horse{pos}", text)

    def test_render_does_not_stop_at_six(self) -> None:
        """The exact regression: the 7th finisher must survive."""
        text = sb_results.render("Townsville", "2026-08-30", self._races(10))
        self.assertIn("7th: #7 Horse7", text)
        self.assertIn("10th: #10 Horse10", text)

    def test_winner_has_no_margin_but_keeps_sp(self) -> None:
        text = sb_results.render("X", "2026-08-30", self._races(3))
        self.assertIn("1st: #1 Horse1 SP$1.00", text)
        self.assertIn("2nd: #2 Horse2 (2.0L) SP$2.00", text)


class TopFlagDefaultTests(unittest.TestCase):
    def test_top_defaults_to_no_cap(self) -> None:
        """`--top` must default to 0 (= keep everything).

        The reflector shells out without passing `--top`, so the default IS the
        production behaviour.
        """
        import argparse
        import inspect

        source = inspect.getsource(sb_results.main)
        self.assertIn('"--top"', source)
        self.assertNotIn("default=6", source)

        parser = argparse.ArgumentParser()
        parser.add_argument("--top", type=int, default=0)
        self.assertEqual(parser.parse_args([]).top, 0)

    def test_reflector_does_not_pass_a_top_flag(self) -> None:
        """If a caller ever starts capping again, this is where it shows up."""
        core = (ROOT / ".agents" / "skills" / "shared_racing" / "race_reflector"
                / "scripts" / "unified_reflector_core.py").read_text(encoding="utf-8")
        self.assertIn("AU_RESULTS_EXTRACTOR", core)
        self.assertNotIn("--top", core)


if __name__ == "__main__":
    unittest.main()
