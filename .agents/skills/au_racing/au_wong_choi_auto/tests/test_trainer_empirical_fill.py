from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[5]
ENGINE = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(ENGINE.parent))

from au_racing_engine import engine_core
from au_racing_engine.engine_core import RacingEngine


def _ctx():
    return {"distance": "1400m", "field_summary": {"count": 10},
            "meeting_intelligence": {"venue": "Randwick", "going": "Good 4"}}


def _score(trainer: str, ly: dict) -> float:
    horse = {"horse_name": "T", "horse_number": "1", "barrier": 5,
             "trainer": trainer, "_data": {"trainer_ly": ly}}
    score, _note, _src = RacingEngine(horse, _ctx())._trainer_score()
    return score


class TrainerLastYearTests(unittest.TestCase):
    """練馬師分由自己去年官方紀錄計（≥10 場，`jockey_trainer.rate_score`）；薄樣本中性。

    舊「empirical fill」（名單外練馬師 × 0.25）喺統一上名率之後由來冇觸發過（EXP-20261103-05：
    要 ≥10 場，而 ≥10 場已經行統一率），已剷。"""

    UNLISTED = "Zzz Unlisted Smalltime Trainer"

    def test_unlisted_trainer_is_scored_from_own_record(self) -> None:
        strong = _score(self.UNLISTED, {"rides": 60, "wins": 10, "places": 24})
        weak = _score(self.UNLISTED, {"rides": 60, "wins": 1, "places": 4})
        self.assertGreater(strong, 60.0)
        self.assertLess(weak, 60.0)
        self.assertGreater(strong, weak)

    def test_places_already_includes_wins(self) -> None:
        # 官方上名 = 冠＋亞＋季；冠軍唔可以再加一次。上名率啱啱等於 prior → 60。
        from au_racing_engine import jockey_trainer as jt
        runs = 100
        places = jt.PLACE_PRIOR["trainer"] * runs
        self.assertAlmostEqual(jt.rate_score("trainer", {"rides": runs, "wins": 20, "places": places})[0], 60.0)

    def test_thin_or_missing_record_stays_neutral(self) -> None:
        for ly in ({"rides": 5, "wins": 2, "places": 1}, {"rides": 0}, {}):
            self.assertAlmostEqual(_score(self.UNLISTED, ly), 60.0, places=1)

    def test_thin_official_record_is_not_described_as_missing(self) -> None:
        horse = {
            "horse_name": "Patriot Wolf",
            "horse_number": "6",
            "trainer": "Brian Lawlor",
            "_data": {"trainer_ly": {"rides": 6, "wins": 0, "places": 0}},
        }
        score, note, _source = RacingEngine(horse, _ctx())._trainer_score()
        self.assertEqual(score, 60.0)
        self.assertIn("去年官方僅 6 場", note)
        self.assertIn("未達 10 場可信門檻", note)
        self.assertNotIn("未有官方記錄", note)


class ComboStatsResilienceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine_core.JOCKEY_TRAINER_COMBO_CACHE = None
        engine_core.TRAINER_TRACK_CACHE = None

    def tearDown(self) -> None:
        engine_core.JOCKEY_TRAINER_COMBO_CACHE = None
        engine_core.TRAINER_TRACK_CACHE = None

    def test_combo_stats_snapshot_is_bundled_and_cached(self) -> None:
        self.assertEqual(
            engine_core.JOCKEY_TRAINER_COMBO_STATS_PATH.parent,
            ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "resources",
        )
        real_open = Path.open
        with patch.object(Path, "open", autospec=True, side_effect=real_open) as mocked_open:
            combo, trainer = engine_core._load_jockey_trainer_combo_stats()
            again = engine_core._load_jockey_trainer_combo_stats()
        self.assertGreater(len(combo), 100)
        self.assertGreater(len(trainer), 50)
        self.assertIs(again[0], combo)
        self.assertIs(again[1], trainer)
        self.assertEqual(mocked_open.call_count, 1)

    def test_scoring_survives_unavailable_combo_stats(self) -> None:
        # The Drive-hosted combo-stats CSV is optional enrichment; an I/O failure
        # must not crash scoring or trigger repeated probes.
        unavailable = Mock()
        unavailable.exists.side_effect = TimeoutError("resource unavailable")
        horse = {"horse_name": "T", "horse_number": "1", "barrier": 5, "trainer": "Chris Waller"}
        with patch.object(engine_core, "JOCKEY_TRAINER_COMBO_STATS_PATH", unavailable):
            auto = RacingEngine(horse, _ctx()).analyze_horse()
            engine_core._load_jockey_trainer_combo_stats()
        self.assertIn("ability_score", auto)
        self.assertGreater(auto["ability_score"], 0)
        self.assertEqual(unavailable.exists.call_count, 1)


if __name__ == "__main__":
    unittest.main()
