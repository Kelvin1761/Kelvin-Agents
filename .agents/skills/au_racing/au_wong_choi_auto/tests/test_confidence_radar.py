from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))

from renderer import ensure_verdict


def _logic(scores: list[float]) -> dict:
    horses = {}
    for idx, score in enumerate(scores, start=1):
        horses[str(idx)] = {
            "horse_name": f"Horse {idx}",
            "python_auto": {"ability_score": score, "grade": "C"},
        }
    return {"race_analysis": {"race_number": 1}, "horses": horses}


class ConfidenceRadarTests(unittest.TestCase):
    def test_tight_race_widens_radar_to_five(self) -> None:
        logic = _logic([64.0, 63.5, 62.5, 62.0, 61.5, 60.0])  # top1-top3 gap 1.5
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "tight")
        self.assertEqual(verdict["radar_size"], 5)
        self.assertEqual(len(verdict["radar"]), 5)
        statuses = [logic["horses"][str(i)]["python_auto"]["model_pick_status"] for i in range(1, 7)]
        self.assertEqual(statuses, ["MODEL_TOP_PICK", "MODEL_TOP_PICK", "WATCH", "WATCH", "WATCH", "NO_PICK"])

    def test_clear_race_keeps_standard_radar(self) -> None:
        logic = _logic([70.0, 66.0, 62.0, 61.0, 60.0, 59.0])  # gap 8.0
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "clear")
        self.assertEqual(verdict["radar_size"], 4)
        statuses = [logic["horses"][str(i)]["python_auto"]["model_pick_status"] for i in range(1, 7)]
        self.assertEqual(statuses, ["MODEL_TOP_PICK", "MODEL_TOP_PICK", "WATCH", "WATCH", "NO_PICK", "NO_PICK"])

    def test_medium_race(self) -> None:
        logic = _logic([66.0, 64.0, 63.0, 61.0, 60.0])  # gap 3.0
        verdict = ensure_verdict(logic)
        self.assertEqual(verdict["confidence_tier"], "medium")
        self.assertEqual(verdict["radar_size"], 4)
        self.assertEqual(verdict["top1_top3_gap"], 3.0)


if __name__ == "__main__":
    unittest.main()
