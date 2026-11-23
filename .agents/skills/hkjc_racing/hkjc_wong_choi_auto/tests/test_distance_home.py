"""返首本唔扣大幅增程（EXP-20261124-08 E5）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import distance_move as dm  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402


def dhorse(prev, hist, raw=70.0):
    return {"_data": {"prev_distance": prev, "hk_history": hist},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}



class DistanceHomeTest(unittest.TestCase):
    def test_home_exempt(self):
        warm = [{"distance": 1600, "placing": 5}, {"distance": 2000, "placing": 6}]       # 上仗 1600，上上仗 2000
        proven = [{"distance": 1600, "placing": 5}, {"distance": 1200, "placing": 7}, {"distance": 1950, "placing": 2}]
        plain = [{"distance": 1600, "placing": 5}, {"distance": 1400, "placing": 4}]
        self.assertFalse(dm.flag(dhorse(1600, warm), "2000米")[0])
        self.assertFalse(dm.flag(dhorse(1600, proven), "2000")[0])               # ±100 米上過名
        self.assertTrue(dm.flag(dhorse(1600, plain), "2000")[0])
        self.assertFalse(dm.home_distance(dhorse(1600, [{"distance": 2000, "placing": 9}]), "2000"))  # 只有上仗唔計
        dm.HOME_EXEMPT = False
        try:
            self.assertTrue(dm.flag(dhorse(1600, warm), "2000")[0])
        finally:
            dm.HOME_EXEMPT = True

    def test_apply_and_tag(self):
        hs = {"1": dhorse(1600, [{"distance": 1600, "placing": 5}, {"distance": 2000, "placing": 6}]),
              "2": dhorse(1600, [{"distance": 1600, "placing": 5}]), "3": dhorse(2000, [])}
        dm.apply(hs, {"distance": "2000"})
        a1, a2 = hs["1"]["python_auto"], hs["2"]["python_auto"]
        self.assertTrue(a1["distance_move"]["home"] and not a1["distance_move"]["up"])
        self.assertTrue(a2["distance_move"]["up"])
        self.assertGreater(a1["distance_move_delta"], a2["distance_move_delta"])
        t = tags._distance_move_tags(a1)
        self.assertEqual(t[0]["key"], "distance_up_home")


if __name__ == "__main__":
    unittest.main()
