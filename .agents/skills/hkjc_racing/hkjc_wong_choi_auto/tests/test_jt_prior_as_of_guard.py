"""J/T priors must never read a full-season snapshot for a race that is not live.

EXP-20261014-10: a missing `race_date` used to count as "live", so every replay
caller that skipped it scored trainer_signal from a snapshot that contained the
race's own result (騎練分 in-race AUC +0.016 [+0.009, +0.024]).  Archived Logic
also embedded a combo aggregate that some 2026-04/05 files rewrote post-race.
"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import live_priors  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402

EMBEDDED = {"starts": 85.0, "wins": 9.0, "places": 25.0, "win_rate": 10.59, "place_rate": 29.41}


class _Snapshot:
    temporal_mode = "latest_season_snapshot"
    as_of_date = None


class AsOfGuardTest(unittest.TestCase):
    def test_missing_date_fails_closed(self) -> None:
        self.assertFalse(live_priors.temporal_source_is_safe(_Snapshot(), None))
        self.assertFalse(live_priors.temporal_source_is_safe(_Snapshot(), ""))
        self.assertFalse(live_priors.temporal_source_is_safe(_Snapshot(), "not-a-date"))

    def test_live_and_future_cards_may_use_latest_snapshot(self) -> None:
        today = date.today()
        self.assertTrue(live_priors.temporal_source_is_safe(_Snapshot(), today.isoformat()))
        self.assertTrue(live_priors.temporal_source_is_safe(_Snapshot(), (today + timedelta(days=2)).isoformat()))

    def test_historical_race_needs_matching_point_in_time_source(self) -> None:
        self.assertFalse(live_priors.temporal_source_is_safe(_Snapshot(), "2026-04-12"))


class EmbeddedComboPriorTest(unittest.TestCase):
    def _prior(self, race_context: dict):
        horse = {"horse_name": "測試", "_data": {"jockey_trainer_combo_prior": dict(EMBEDDED)}}
        return RacingEngine(horse, race_context)._jockey_trainer_prior()

    def test_live_card_keeps_embedded_prior(self) -> None:
        self.assertEqual(self._prior({"race_date": date.today().isoformat()}), EMBEDDED)

    def test_replayed_race_ignores_embedded_prior(self) -> None:
        self.assertIsNone(self._prior({"race_date": "2026-04-12"}))

    def test_undated_race_ignores_embedded_prior(self) -> None:
        self.assertIsNone(self._prior({}))


if __name__ == "__main__":
    unittest.main()
