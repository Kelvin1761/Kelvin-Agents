"""上仗賠率組件（EXP-20261115-07）：只用嚴格早過今仗嘅賠率、外隊馬中性、場內置中、退回開關。"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import market_history as mh  # noqa: E402

TABLE = {"horses": {"L001": [["2026-10-01", 3.0], ["2026-11-01", 10.0], ["2026-11-15", 99.0]],
                    "L002": [["2026-10-20", 5.0]]}}


def horse(code, raw=60.0):
    return {"horse_code": code, "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class MarketHistoryTest(unittest.TestCase):
    def test_strictly_before_race_date(self):
        self.assertAlmostEqual(mh.prev_log_odds("L001", "2026-11-15", TABLE), math.log(10.0))   # 唔用今仗 99
        self.assertIsNone(mh.prev_log_odds("L001", "2026-10-01", TABLE))
        self.assertIsNone(mh.prev_log_odds("L999", "2026-11-15", TABLE))

    def test_centred_and_missing(self):
        hs = {"1": horse("L001"), "2": horse("L002"), "3": horse("L003")}
        adj = mh.adjustments(hs, "2026-11-15", TABLE)
        self.assertAlmostEqual(sum(adj.values()), 0.0, places=9)
        self.assertGreater(adj["2"], adj["1"])          # 上仗較熱（5 vs 10）→ 加分較多
        self.assertLess(adj["3"], min(adj["1"], adj["2"]))   # 冇上仗 → 扣分

    def test_foreign_neutral(self):
        hs = {"1": horse("L001"), "2": horse("L002"), "3": horse("Z901")}
        adj = mh.adjustments(hs, "2026-11-15", TABLE)
        self.assertGreater(adj["3"], mh.adjustments({"1": horse("L001"), "2": horse("L002"), "3": horse("L003")},
                                                    "2026-11-15", TABLE)["3"])   # 外隊馬唔受「冇上仗」扣分

    def test_apply_and_disable(self):
        hs = {"1": horse("L001"), "2": horse("L002")}
        self.assertEqual(mh.apply(hs, "2026-11-15", TABLE), 2)
        self.assertIn("market_history_delta", hs["1"]["python_auto"])
        hs2 = {"1": horse("L001"), "2": horse("L002")}
        mh.ENABLED = False
        try:
            self.assertEqual(mh.apply(hs2, "2026-11-15", TABLE), 0)
            self.assertEqual(hs2["1"]["python_auto"]["ability_score_raw"], 60.0)
        finally:
            mh.ENABLED = True


if __name__ == "__main__":
    unittest.main()
