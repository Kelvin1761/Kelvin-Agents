"""上仗事件報告組件（EXP-20261116-06）：只睇嚴格早過今仗嘅最近一仗、旗分類、場內置中、外隊馬中性、退回開關。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import incident_history as ih  # noqa: E402

TABLE = {"horses": {"L001": [["2026-10-01", "M"], ["2026-11-01", "W"], ["2026-11-15", "M"]],
                    "L002": [["2026-10-01", "W"], ["2026-11-01", None]],
                    "L003": [["2026-11-01", "M"]]}}


def horse(code, raw=60.0):
    return {"horse_code": code, "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class IncidentHistoryTest(unittest.TestCase):
    def test_flags(self):
        self.assertEqual(ih.flags("大部分途程在沒有遮擋下走外疊。"), "W")
        self.assertEqual(ih.flags("賽後獸醫檢查，發現喘鳴。"), "M")
        self.assertEqual(ih.flags("無特別報告。"), "")
        self.assertIsNone(ih.flags(None))
        # R = 騎法被查詢類，只顯示（EXP-20261116-08）；唔影響 W／M 加減
        self.assertEqual(ih.flags("被查詢時，周俊樂表示，他獲指示讓坐騎留後。"), "R")
        self.assertEqual(ih.flags("走外疊。騎師承認違反賽事規例第100(2)條。"), "WR")

    def test_wording_check_flags_silent_drop(self):
        ok = {"last_date": "2026-11-15", "horses": {f"L{i:03d}": [["2026-11-01", f]] for i, f in
              enumerate(["W"] * 30 + ["M"] * 10 + ["R"] * 10 + [""] * 300)}}
        self.assertEqual(ih.wording_check(ok), [])
        dead = {"last_date": "2026-11-15", "horses": {f"L{i:03d}": [["2026-11-01", f]] for i, f in
                enumerate(["M"] * 10 + ["R"] * 10 + [""] * 330)}}
        self.assertEqual(len(ih.wording_check(dead)), 1)          # W 跌到 0 → 報警
        self.assertEqual(ih.wording_check({"last_date": "2026-11-15", "horses": {"L1": [["2026-11-01", ""]]}}), [])

    def test_ride_flag_not_scored(self):
        table = {"horses": {"L001": [["2026-11-01", "R"]], "L002": [["2026-11-01", ""]]}}
        adj = ih.adjustments({"1": horse("L001"), "2": horse("L002")}, "2026-11-15", table)
        self.assertEqual(adj, {"1": 0.0, "2": 0.0})

    def test_wide_two_back_display_only(self):
        """EXP-20261116-18：上上仗走外疊（上仗有報告但冇走外疊）只顯示，唔入分。"""
        t = {"horses": {"L001": [["2026-10-01", "W"], ["2026-10-20", None], ["2026-11-01", ""]],
                        "L002": [["2026-10-01", "W"], ["2026-11-01", "W"]],
                        "L003": [["2026-10-01", "W"], ["2026-11-01", None]],
                        "L004": [["2026-10-01", "W"], ["2026-11-01", ""], ["2026-11-15", ""]]}}
        self.assertTrue(ih.prev_wide_two_back("L001", "2026-11-15", t))   # 跳過冇報告嗰場
        self.assertFalse(ih.prev_wide_two_back("L002", "2026-11-15", t))  # 上仗已經 W（入分）
        self.assertFalse(ih.prev_wide_two_back("L003", "2026-11-15", t))  # 上仗冇報告
        self.assertFalse(ih.prev_wide_two_back("L004", "2026-11-30", t))  # 上上仗係 ""，唔係 W
        self.assertTrue(ih.prev_wide_two_back("L004", "2026-11-15", t))   # 嚴格早過今仗
        hs = {"1": horse("L001"), "2": horse("L003")}
        self.assertEqual(ih.adjustments(hs, "2026-11-15", t), {"1": 0.0, "2": 0.0})
        ih.apply(hs, "2026-11-15", t)
        self.assertTrue(hs["1"]["python_auto"]["incident_wide_two_back"])
        self.assertFalse(hs["2"]["python_auto"]["incident_wide_two_back"])
        self.assertEqual(hs["1"]["python_auto"]["ability_score_raw"], 60.0)

    def test_blocked_and_slow_flags_are_not_scored(self):
        """EXP-20261117-05：B（受阻）／S（出閘慢）只俾 forward shadow 用，唔入 adjustments。"""
        self.assertEqual(ih.flags("出閘緩慢，其後未能望空。"), "BS")
        t = {"horses": {"L001": [["2026-11-01", "BS"]], "L002": [["2026-11-01", ""]]}}
        self.assertEqual(ih.adjustments({"1": horse("L001"), "2": horse("L002")}, "2026-11-15", t), {"1": 0.0, "2": 0.0})

    def test_prev_two(self):
        t = {"horses": {"A": [["2026-10-01", "B"], ["2026-10-20", None], ["2026-11-01", "R"]]}}
        self.assertEqual(ih.prev_two("A", "2026-11-15", t), ("R", "B"))
        self.assertEqual(ih.prev_two("A", "2026-11-01", t), (None, "B"))
        self.assertEqual(ih.prev_two("A", "2026-10-01", t), (None, None))

    def test_last_run_strictly_before(self):
        self.assertEqual(ih.prev_flags("L001", "2026-11-15", TABLE), "W")      # 唔用今仗 M
        self.assertEqual(ih.prev_flags("L002", "2026-11-15", TABLE), "")       # 最近一仗冇報告 → 冇旗（唔回頭搵舊旗）
        self.assertEqual(ih.prev_flags("L001", "2026-10-01", TABLE), "")
        self.assertEqual(ih.prev_flags("L999", "2026-11-15", TABLE), "")

    def test_centred_and_direction(self):
        hs = {"1": horse("L001"), "2": horse("L002"), "3": horse("L003")}
        adj = ih.adjustments(hs, "2026-11-15", TABLE)
        self.assertAlmostEqual(sum(adj.values()), 0.0, places=9)
        self.assertGreater(adj["1"], adj["2"])     # 走外疊 → 加
        self.assertLess(adj["3"], adj["2"])        # 醫療 → 扣
        self.assertAlmostEqual(adj["1"] - adj["2"], ih.BETA_WIDE, places=9)

    def test_foreign_neutral(self):
        hs = {"1": horse("Z901"), "2": horse("L002")}
        TABLE["horses"]["Z901"] = [["2026-11-01", "M"]]
        try:
            self.assertEqual(ih.adjustments(hs, "2026-11-15", TABLE), {"1": 0.0, "2": 0.0})
        finally:
            del TABLE["horses"]["Z901"]

    def test_apply_shadow_and_disable(self):
        hs = {"1": horse("L001"), "2": horse("L002")}
        for h in hs.values():
            h["python_auto"]["shadow_profiles"] = {"p": {"ability_score_raw": 61.0, "ability_score": 61.0, "grade": "B"}}
        self.assertEqual(ih.apply(hs, "2026-11-15", TABLE), 2)
        a = hs["1"]["python_auto"]
        self.assertEqual(a["incident_history_flags"], "W")
        self.assertAlmostEqual(a["shadow_profiles"]["p"]["ability_score_raw"] - a["ability_score_raw"], 1.0, places=3)
        hs2 = {"1": horse("L001"), "2": horse("L002")}
        ih.ENABLED = False
        try:
            self.assertEqual(ih.apply(hs2, "2026-11-15", TABLE), 0)
            self.assertEqual(hs2["1"]["python_auto"]["ability_score_raw"], 60.0)
        finally:
            ih.ENABLED = True


if __name__ == "__main__":
    unittest.main()
