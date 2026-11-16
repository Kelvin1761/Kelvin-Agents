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
