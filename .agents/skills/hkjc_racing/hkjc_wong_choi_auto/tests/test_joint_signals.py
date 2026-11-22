"""聯合訊號（EXP-20261122-34 J3）：同程四項、場內置中、退回開關、chip 升級（一樣嘢一個 chip）。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[5]))   # repo 根：wongchoi_paths（form_patterns 贏馬分表）
from hkjc_racing_engine import joint_signals as js  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402


def horse(*runs, raw=60.0):
    hist = [{"date": f"2026-10-{20 - i:02d}", "surface": "田草", "distance": d, "placing": p, "class": c} for i, (d, p, c) in enumerate(runs)]
    return {"_data": {"hk_history": hist}, "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class SameDistanceTest(unittest.TestCase):
    def test_worse_than_own_average(self):
        # 整體 6 戰 3 上名（50%）；1200 米 3 戰 0 上名 → 差 −0.5
        h = horse((1200, 6, "4"), (1400, 1, "4"), (1200, 7, "4"), (1400, 2, "4"), (1200, 9, "4"), (1400, 3, "4"))
        f = js.same_distance(h, 1200, 4)
        self.assertEqual(f["sd_worse"], 1.0)
        self.assertEqual(f["sd_rate"], 0.0)

    def test_rate_and_class(self):
        h = horse((1200, 1, "3"), (1200, 2, "4"), (1200, 3, "4"))
        f = js.same_distance(h, 1200, 4)
        self.assertEqual((f["sd_rate"], f["sd_hicls"], f["sd_locls"]), (1.0, 1.0, 0.0))
        f = js.same_distance(horse((1200, 2, "5"), (1200, 9, "4")), 1200, 4)
        self.assertEqual((f["sd_hicls"], f["sd_locls"]), (0.0, 1.0))
        self.assertEqual(js.same_distance(horse(), 1200, 4), dict.fromkeys(f, 0.0))

    def test_class_no(self):
        self.assertEqual(js._class_no("第四班"), 4)
        self.assertEqual(js._class_no("二級賽"), 0)
        self.assertEqual(js._class_no("3"), 3)
        self.assertIsNone(js._class_no(""))
        self.assertEqual(js._class_no("G1"), 0)       # 同回放：非數字班次當最高
        self.assertEqual(js._class_no("4R"), 0)


class ApplyTest(unittest.TestCase):
    def test_centred_and_disable(self):
        hs = {"1": horse((1200, 1, "4"), (1200, 2, "4")), "2": horse((1200, 9, "4"), (1400, 1, "4"), (1200, 8, "4"), (1400, 2, "4"))}
        ctx = {"race_class": "第四班", "race_date": "2026-11-22", "distance": "1200"}
        js.apply(hs, ctx, None)
        a1, a2 = hs["1"]["python_auto"], hs["2"]["python_auto"]
        self.assertAlmostEqual(a1["joint_signals_delta"] + a2["joint_signals_delta"], 0.0, places=4)
        self.assertGreater(a1["joint_signals_delta"], 0)       # 同程上名率高
        self.assertIn("sd_worse", a2["joint_signals"]["flags"])
        js.ENABLED = False
        try:
            self.assertEqual(js.apply({"1": horse(), "2": horse()}, ctx, None), 0)
        finally:
            js.ENABLED = True

    def test_chip_upgrade_and_new_chip(self):
        auto = {"joint_signals": {"flags": {"old_won": 1.0, "sd_worse": 1.0}, "parts": {"old_won": -3.2, "sd_worse": -2.2, "ride_q": -0.1}}}
        special = [tags._tag("old_won_last", "老馬贏後（在港 40 仗）", "bad", why="……未入分，forward 觀察中。")]
        out = tags._apply_joint_signals(special, auto)
        old = next(t for t in out if t["key"] == "old_won_last")
        self.assertTrue(old["scored"]) and self.assertAlmostEqual(old["impact"], -3.2)
        self.assertNotIn("未入分", old["why"])
        self.assertEqual([t["label"] for t in out if t["key"].startswith("joint:")], ["同程表現差過自己平均"])


if __name__ == "__main__":
    unittest.main()
