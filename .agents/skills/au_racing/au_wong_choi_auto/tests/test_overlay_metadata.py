"""EXP-20261101-38：報告嘅 overlay metadata 一定要加得返綜合分（七維 + overlay = 綜合分）。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.renderer import OVERLAYS, overlay_metadata  # noqa: E402


def _horse(pure, wet, proven, full, trip=None):
    auto = {"pure_7d_score": pure, "wet_form_feature": wet, "proven_class_feature": proven,
            "full_time_speed_feature": full, "ability_score": round(pure + wet + proven + full, 4),
            "stability_detail": {"form_quality": {"trip_change": trip} if trip else {}}}
    return {"horse_name": "H", "python_auto": auto}


class OverlayMetadataTests(unittest.TestCase):
    def test_overlays_add_up_to_ability(self):
        # 高班實績證明 2026-11-13 退出（EXP-20261113-22）→ 引擎永遠 0
        meta = overlay_metadata({"1": _horse(70.1234, 0.5, 0.0, 1.1)})
        h = meta["horses"]["1"]
        self.assertEqual(meta["schema"], "au/overlays-v1")
        self.assertAlmostEqual(h["pure_7d_score"] + sum(o["value"] for o in h["overlays"]), h["ability_score"], places=4)

    def test_every_engine_overlay_is_listed_with_a_dimension(self):
        h = overlay_metadata({"1": _horse(60, 0, 0, 0)})["horses"]["1"]
        self.assertEqual([o["key"] for o in h["overlays"]], [k for k, *_ in OVERLAYS])
        self.assertTrue(all(o["dimension"] for o in h["overlays"]))
        self.assertNotIn("proven_class", [o["key"] for o in h["overlays"]])

    def test_trip_change_is_flagged_not_added(self):
        trip = {"today": 1600, "last": 1100.0, "delta": -5.0}
        h = overlay_metadata({"1": _horse(60, 0, 0, 0, trip)})["horses"]["1"]
        self.assertEqual(h["trip_change"]["delta"], -5.0)
        self.assertEqual(h["ability_score"], 60)


if __name__ == "__main__":
    unittest.main()
