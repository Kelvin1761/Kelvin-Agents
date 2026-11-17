"""轉場組件（EXP-20261117-06 K2）：谷草／田草／泥地、場內置中、冇往績中性、退回開關。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import surface_move as sm  # noqa: E402


def horse(*surfaces, raw=60.0):
    hist = [{"date": f"2026-10-{20 - i:02d}", "surface": s} for i, s in enumerate(surfaces)]
    return {"_data": {"hk_history": hist},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B", "shadow_profiles": {"x": {"ability_score_raw": raw}}}}


class SurfaceMoveTest(unittest.TestCase):
    def test_surface_parsing(self):
        self.assertEqual(sm.surface_of('跑馬地草地"B"'), "谷草")
        self.assertEqual(sm.surface_of('沙田草地"A+3"'), "田草")
        self.assertEqual(sm.surface_of("沙田全天候"), "泥地")
        self.assertIsNone(sm.surface_of("蘭域/草地"))
        self.assertEqual(sm.today_surface({"venue": "沙田AWT", "track": "AWT"}), "泥地")
        self.assertEqual(sm.today_surface({"venue": "跑馬地", "track": "Turf"}), "谷草")
        self.assertEqual(sm.today_surface({"venue": "沙田", "track": "Turf"}), "田草")

    def test_flags(self):
        f = sm.flags(horse("谷草", "谷草"), "田草")
        self.assertTrue(f["hv_to_st"] and f["first_st"])
        f = sm.flags(horse("田草", "谷草"), "谷草")
        self.assertTrue(f["st_to_hv"] and not f["first_st"])
        f = sm.flags(horse("谷草", "田草"), "泥地")
        self.assertTrue(f["first_awt"] and not f["hv_to_st"])
        self.assertFalse(any(sm.flags(horse(), "田草").values()))          # 初出 = 冇旗

    def test_apply_centred_shadow_and_disable(self):
        hs = {"1": horse("谷草"), "2": horse("田草")}
        self.assertEqual(sm.apply(hs, {"venue": "沙田", "track": "Turf"}), 2)
        a1, a2 = hs["1"]["python_auto"], hs["2"]["python_auto"]
        self.assertAlmostEqual(a1["surface_move_delta"] + a2["surface_move_delta"], 0.0, places=6)
        # 1 號：跑馬地轉沙田草地＋初次沙田草地；2 號：冇旗
        self.assertAlmostEqual(a1["surface_move_delta"] - a2["surface_move_delta"], sm.BETA["hv_to_st"] + sm.BETA["first_st"], places=4)
        self.assertAlmostEqual(a1["shadow_profiles"]["x"]["ability_score_raw"], a1["ability_score_raw"], places=4)
        sm.ENABLED = False
        try:
            hs = {"1": horse("谷草"), "2": horse("田草")}
            self.assertEqual(sm.apply(hs, {"venue": "沙田", "track": "Turf"}), 0)
        finally:
            sm.ENABLED = True


if __name__ == "__main__":
    unittest.main()
