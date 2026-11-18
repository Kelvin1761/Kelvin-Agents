"""同程上名要同場地（EXP-20261119-01 V2）：只喺另一場地上名先有旗、場內置中、冇往績中性、退回開關。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import venue_distance as vd  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402

HV = {"venue": "跑馬地", "track": "Turf", "distance": "1000"}


def horse(*runs, raw=60.0):
    hist = [{"date": f"2026-10-{20 - i:02d}", "surface": s, "distance": d, "placing": p} for i, (s, d, p) in enumerate(runs)]
    return {"_data": {"hk_history": hist},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B", "shadow_profiles": {"x": {"ability_score_raw": raw}}}}


class VenueDistanceTest(unittest.TestCase):
    def test_flag(self):
        self.assertTrue(vd.flag(horse(("田草", 1000, 1)), "谷草", 1000)["on"])            # 沙田直路贏過、今仗谷草
        self.assertFalse(vd.flag(horse(("田草", 1000, 1), ("谷草", 1000, 3)), "谷草", 1000)["on"])  # 谷草都上過名
        self.assertFalse(vd.flag(horse(("田草", 1000, 5)), "谷草", 1000)["on"])            # 冇上名 = 唔關事
        self.assertFalse(vd.flag(horse(("田草", 1200, 1)), "谷草", 1000)["on"])            # 唔同路程
        self.assertFalse(vd.flag(horse(), "谷草", 1000)["on"])                             # 初出 = 冇旗
        self.assertEqual(vd.flag(horse(("田草", 1000, 2), ("泥地", 1000, 1)), "谷草", "1000米")["placed_at"], ["田草", "泥地"])

    def test_apply_centred_shadow_and_disable(self):
        hs = {"1": horse(("田草", 1000, 1)), "2": horse(("谷草", 1000, 1))}
        self.assertEqual(vd.apply(hs, HV), 2)
        a1, a2 = hs["1"]["python_auto"], hs["2"]["python_auto"]
        self.assertAlmostEqual(a1["same_distance_venue_delta"] + a2["same_distance_venue_delta"], 0.0, places=6)
        self.assertAlmostEqual(a1["same_distance_venue_delta"] - a2["same_distance_venue_delta"], vd.BETA, places=4)
        self.assertAlmostEqual(a1["shadow_profiles"]["x"]["ability_score_raw"], a1["ability_score_raw"], places=4)
        t = tags._same_distance_venue_tags(a1)
        self.assertEqual(t[0]["label"], "1000米上名只喺沙田草地")
        self.assertTrue(t[0]["scored"] and t[0]["tone"] == "bad")
        self.assertEqual(tags._same_distance_venue_tags(a2), [])
        vd.ENABLED = False
        try:
            self.assertEqual(vd.apply({"1": horse(("田草", 1000, 1)), "2": horse()}, HV), 0)
        finally:
            vd.ENABLED = True


if __name__ == "__main__":
    unittest.main()
