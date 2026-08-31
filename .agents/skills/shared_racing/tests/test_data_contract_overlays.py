"""Overlay 一定要入數據合約，而且中性點係 0 唔係 60。

2026-08-31：`wet_form_feature` / `proven_class_feature` 直接加落綜合戰力分，
但佢哋係 `python_auto` 嘅 sibling 而唔係 `feature_scores` 嘅 key，所以發佈閘
由來睇唔到佢哋。後果：濕地 overlay 個 prior 校錯（0.5 vs 實測 0.3758），
中位數 −1.49 咁多個月，九個 suite 全綠、發佈閘全綠 —— 冇任何閘門睇到。
見 `docs/experiments/EXP-20260831-08-au-wet-overlay-prior.md`。
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

from data_contract import (  # noqa: E402
    OVERLAY_NEUTRAL, neutral_point, observe)


def _logic(going: str, rows):
    """rows = [(feature_scores, wet, proven_class), ...]"""
    horses = {}
    for i, (fs, wet, pc) in enumerate(rows, start=1):
        horses[str(i)] = {"python_auto": {
            "feature_scores": fs,
            "wet_form_feature": wet,
            "proven_class_feature": pc,
            "race_context": {"going": going},
        }}
    return {"horses": horses}


def _write(tmp: Path, name: str, payload: dict) -> str:
    p = tmp / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


class NeutralPointTests(unittest.TestCase):
    def test_leaf_neutral_is_sixty(self):
        self.assertEqual(neutral_point("form_score"), 60.0)
        self.assertEqual(neutral_point("anything_unknown"), 60.0)

    def test_overlay_neutral_is_zero(self):
        self.assertEqual(neutral_point("wet_form_feature"), 0.0)
        self.assertEqual(neutral_point("proven_class_feature"), 0.0)
        self.assertEqual(set(OVERLAY_NEUTRAL), {"wet_form_feature",
                                                "proven_class_feature"})


class OverlayObservationTests(unittest.TestCase):
    def test_wet_overlay_is_observed_on_wet_going(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            rows = [({"form_score": 70.0}, -1.2, 0.0),
                    ({"form_score": 60.0}, 0.0, 0.0),
                    ({"form_score": 55.0}, 2.4, 1.1)]
            path = _write(tmp, "Race_1_Logic.json", _logic("Soft 6", rows))
            fields, races, horses, bad = observe([path])
        self.assertIn("wet_form_feature", fields)
        obs = fields["wet_form_feature"]
        # 3 匹入面 1 匹係 0.0（中性）
        self.assertAlmostEqual(obs.summarise()["neutral_rate"], 1 / 3, places=3)

    def test_dry_going_does_not_make_the_wet_overlay_look_dead(self):
        """乾地全場 0.0 係**正確行為** —— 唔可以當成死欄位。

        冇適用性條件嘅話，每個好地場次都會令 wet_form_feature 嘅
        neutral_rate 變 100%，發佈閘就會攔住每一個乾地場次。
        """
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            rows = [({"form_score": 70.0}, 0.0, 0.0)] * 3
            path = _write(tmp, "Race_1_Logic.json", _logic("Good 4", rows))
            fields, races, horses, bad = observe([path])
        self.assertNotIn("wet_form_feature", fields,
                         "乾地場次唔應該觀察濕地 overlay")
        # proven_class 冇地況條件，照觀察
        self.assertIn("proven_class_feature", fields)

    def test_leaves_still_observed_unchanged(self):
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            rows = [({"form_score": 60.0}, 0.0, 0.0)] * 3
            path = _write(tmp, "Race_1_Logic.json", _logic("Good 4", rows))
            fields, races, horses, bad = observe([path])
        self.assertIn("form_score", fields)
        self.assertEqual(fields["form_score"].summarise()["neutral_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
