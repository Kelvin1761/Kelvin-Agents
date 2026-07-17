from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))

from engine_core import RacingEngine
from scoring import PACE_MICRO_WEIGHTS


def _score(barrier: int, venue: str, distance: str, field_count: int) -> tuple[float, str]:
    horse = {"horse_name": "Test Horse", "barrier": barrier, "horse_number": "1"}
    race_context = {
        "distance": distance,
        "field_summary": {"count": field_count},
        "meeting_intelligence": {"venue": venue},
    }
    engine = RacingEngine(horse, race_context)
    score, _note, _tag = engine._pace_map_score()
    detail_text = "\n".join(engine.pace_map_detail.get("lines", []))
    return score, detail_text


class DrawBiasShrinkageTests(unittest.TestCase):
    def test_thin_sample_cell_no_longer_slams(self) -> None:
        # Rosehill Gardens 1200m inside: n=16, win_rate 0.0 — previously the raw
        # −10 modifier hit cap_min (−9.43); with n/(n+25) shrinkage it must be
        # a bounded, sane deduction.
        base = PACE_MICRO_WEIGHTS["base"]
        score, note = _score(barrier=2, venue="Rosehill Gardens", distance="1200m", field_count=11)
        modifier = score - base
        self.assertLess(modifier, 0.0)  # still a negative signal
        self.assertGreater(modifier, -5.0)  # but no cap-min slam
        self.assertIn("收縮", note + "")

    def test_dense_cell_keeps_most_of_its_signal(self) -> None:
        # Global field_9_12 inside: n=1499 — shrinkage factor ~0.98, near-unchanged.
        base = PACE_MICRO_WEIGHTS["base"]
        score, _ = _score(barrier=2, venue="Nowhere Park", distance="9999m", field_count=11)
        modifier = score - base
        # global inside win rate 10.3% vs 1/11 baseline → small positive, not zeroed
        self.assertGreater(modifier, 0.5)


if __name__ == "__main__":
    unittest.main()
