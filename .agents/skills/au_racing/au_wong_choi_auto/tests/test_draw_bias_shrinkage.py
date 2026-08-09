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
    def test_modifier_matches_shrunk_formula(self) -> None:
        # The applied modifier must equal (win_rate − 1/field) × 110 × n/(n+k),
        # capped — verified against whatever the live matrix holds for the
        # Rosehill Gardens 1200m inside cell, so the test survives matrix
        # rebuilds as backfill data grows.
        import json
        from pathlib import Path

        matrix = json.loads((ENGINE_DIR / "au_draw_bias_matrix.json").read_text(encoding="utf-8"))
        cell = matrix["tracks"]["Rosehill Gardens"]["distances"]["1200"]["inside"]
        self.assertGreaterEqual(cell["sample_size"], 10)  # cascade accepts this cell
        w = PACE_MICRO_WEIGHTS
        expected_wr = 1.0 / 11
        raw = (cell["win_rate"] - expected_wr) * 100 * w["modifier_multiplier"]
        n = cell["sample_size"]
        raw *= n / (n + w.get("shrinkage_k", 25.0))
        expected_mod = max(w["modifier_cap_min"], min(w["modifier_cap_max"], raw))

        score, note = _score(barrier=2, venue="Rosehill Gardens", distance="1200m", field_count=11)
        self.assertAlmostEqual(score - w["base"], expected_mod, places=1)
        self.assertIn("收縮", note + "")

    def test_thin_cell_cannot_reach_cap_min(self) -> None:
        # Mechanism guarantee: even a 0%-win cell at the n>=10 acceptance
        # threshold cannot reach the raw cap_min once shrunk — n=10 keeps at
        # most 10/35 = 29% of the raw modifier.
        w = PACE_MICRO_WEIGHTS
        expected_wr = 1.0 / 11
        raw = (0.0 - expected_wr) * 100 * w["modifier_multiplier"]  # worst case ≈ −10
        shrunk = raw * 10 / (10 + w.get("shrinkage_k", 25.0))
        self.assertGreater(shrunk, -3.5)
        self.assertGreater(shrunk, w["modifier_cap_min"])

    def test_dense_cell_keeps_most_of_its_signal(self) -> None:
        # Global field_9_12 inside: n=1499 — shrinkage factor ~0.98, near-unchanged.
        base = PACE_MICRO_WEIGHTS["base"]
        score, _ = _score(barrier=2, venue="Nowhere Park", distance="9999m", field_count=11)
        modifier = score - base
        # global inside win rate 10.3% vs 1/11 baseline → small positive, not zeroed
        self.assertGreater(modifier, 0.5)


if __name__ == "__main__":
    unittest.main()
