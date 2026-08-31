from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
ENGINE_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "au_racing_engine"
sys.path.insert(0, str(ENGINE_DIR.parent))

from au_racing_engine.engine_core import RacingEngine
from au_racing_engine.scoring import PACE_MICRO_WEIGHTS


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

        from au_racing_engine.engine_core import _draw_pool_baseline

        matrix = json.loads((ENGINE_DIR / "au_draw_bias_matrix.json").read_text(encoding="utf-8"))
        peers = matrix["tracks"]["Rosehill Gardens"]["distances"]["1200"]
        cell = peers["inside"]
        self.assertGreaterEqual(cell["sample_size"], 10)  # cascade accepts this cell
        w = PACE_MICRO_WEIGHTS
        # 2026-08-16: the baseline is the cell's OWN pool, not 1/field_size. The
        # track and track+distance levels are not field-size bucketed, so
        # 1/field_size subtracted two different denominators (see _pace_map_score).
        expected_wr = _draw_pool_baseline(peers, 1.0 / 11)
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
        """密集 cell 唔會被收縮吞掉 —— 測機制，唔測幅度。

        2026-08-31：原本呢個測試 assert `modifier > 0.5`，即係一個**隨語料變**
        嘅幅度。檔位偏差表由 8,619 個樣本重建到 19,178 個之後，全域內檔勝率由
        10.80% 變 10.20%，幅度跌到 0.396，測試就爆 —— 但機制完全冇壞。
        一個綁死數據值嘅測試會喺每次正常重建時嗌，然後人就會習慣忽略佢。
        改為 assert 收縮**幾乎冇削弱**同**符號保住**，兩者都係唔應該變嘅性質。
        """
        import json

        from au_racing_engine.engine_core import _draw_pool_baseline

        matrix = json.loads((ENGINE_DIR / "au_draw_bias_matrix.json").read_text(encoding="utf-8"))
        peers = matrix["global_general"]["field_9_12"]
        cell = peers["inside"]
        n = cell["sample_size"]
        w = PACE_MICRO_WEIGHTS
        shrink = n / (n + w.get("shrinkage_k", 25.0))
        self.assertGreater(n, 1000, "全域內檔應該係最密嘅 cell")
        self.assertGreater(shrink, 0.95, "密集 cell 嘅收縮係數應該近 1")

        base = w["base"]
        score, _ = _score(barrier=2, venue="Nowhere Park", distance="9999m", field_count=11)
        modifier = score - base
        expected_wr = _draw_pool_baseline(peers, 1.0 / 11)
        raw = (cell["win_rate"] - expected_wr) * 100 * w["modifier_multiplier"]
        # 收縮之後應該仍然保住原始幅度嘅九成半以上，同埋唔轉符號。
        self.assertAlmostEqual(modifier, raw * shrink, places=1)
        self.assertGreater(abs(modifier), abs(raw) * 0.95)
        if raw:
            self.assertEqual(modifier > 0, raw > 0)


if __name__ == "__main__":
    unittest.main()
