"""Focused regression tests for official-source routing and parsing."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from au_official_free_data import (  # noqa: E402
    match_trial_runner,
    parse_trial_heat,
    public_results_url,
    route_for_venue,
)


class OfficialFreeDataTests(unittest.TestCase):
    def test_state_authority_routes(self) -> None:
        randwick = route_for_venue("Randwick")
        doomben = route_for_venue("Doomben")
        sandown = route_for_venue("Sandown Lakeside")
        self.assertEqual((randwick.authority, randwick.result_host, randwick.state), ("racing_nsw", "racing_nsw", "NSW"))
        self.assertEqual((doomben.authority, doomben.result_host, doomben.state), ("racing_queensland", "racing_australia", "QLD"))
        self.assertEqual((sandown.authority, sandown.result_host, sandown.state), ("racing_victoria", "racing_australia", "VIC"))
        self.assertIn("JumpOut", public_results_url("2026-06-30", sandown) or "")

    def test_other_states_and_unknown_venue_are_never_guessed(self) -> None:
        self.assertEqual(route_for_venue("Morphettville").authority, "racing_sa")
        self.assertEqual(route_for_venue("Ascot").authority, "racing_wa")
        self.assertEqual(route_for_venue("Launceston").authority, "tasracing")
        unknown = route_for_venue("Example Park")
        self.assertEqual(unknown.authority, "unresolved")
        self.assertIsNone(public_results_url("2026-06-30", unknown))

    def test_trial_l600_is_event_level(self) -> None:
        page = """<html><body>Race 2 - Example (1000 METRES)
        Time: 1:00.25 Last 600m: 0:34.12 Timing Method: Electronic
        Race 3 - Other (800 METRES)</body></html>"""
        self.assertEqual(parse_trial_heat(page, 2), {
            "heat": 2, "distance_m": 1000, "time": "1:00.25",
            "last_600": "0:34.12", "timing_method": "Electronic",
        })

    def test_trial_runner_extracts_jockey_from_official_heat_table(self) -> None:
        page = """
        <a name="Race2"></a><table><tr class='OddRow'>
          <td></td><td><span class='Finish F4'>4</span></td><td>7</td>
          <td class='horse'><a>EXAMPLE HORSE (NZ)</a></td>
          <td class='trainer'><a>Example Trainer</a></td>
          <td class='jockey'><a><span class='Hilite'>Ms Example Rider</span></a></td>
        </tr></table>
        <!-- start of races --><a name="Race3"></a>
        """
        self.assertEqual(match_trial_runner(page, 2, "Example Horse"), {
            "horse_name": "EXAMPLE HORSE (NZ)",
            "jockey": "Ms Example Rider",
            "trainer": "Example Trainer",
            "finish": "4",
            "saddlecloth_number": "7",
        })

    def test_trial_runner_supports_racing_nsw_column_classes(self) -> None:
        page = """
        <a name="Race5"></a><table><tr class='EvenRow-nontab'>
          <td class="jockey-silk"></td><td class="finish-results"><span class='Finish F5'>5</span></td><td>8</td>
          <td class="horsename-results"><a><strong>SOFT LOVE</strong></a></td><td class="bonus-results"></td>
          <td class="trainer-results"><a>Matt Laurie</a></td><td><a><span>Sam Clipperton</span></a></td>
        </tr></table><!-- start of races --><a name="Race6"></a>
        """
        self.assertEqual(match_trial_runner(page, 5, "Soft Love"), {
            "horse_name": "SOFT LOVE",
            "jockey": "Sam Clipperton",
            "trainer": "Matt Laurie",
            "finish": "5",
            "saddlecloth_number": "8",
        })


if __name__ == "__main__":
    unittest.main()
