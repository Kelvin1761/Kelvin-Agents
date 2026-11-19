"""連續兩仗有藉口（EXP-20261119-06 X1）：兩仗都要有藉口＋都未入位、嚴格早過今仗、冇報告／冇名次唔套用、外隊中性、場內置中、chip。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import excuse_streak as ex  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402

TABLE = {"horses": {
    "J437": [["2026-09-13", ""], ["2026-10-07", "W"], ["2026-11-01", "BS"], ["2026-11-18", "R"]],
    "K001": [["2026-10-07", "B"], ["2026-11-01", "B"]],          # 上仗入位 → 唔套用
    "K002": [["2026-10-07", None], ["2026-11-01", "B"]],         # 上上仗冇報告 → 唔套用
    "K003": [["2026-10-07", "M"], ["2026-11-01", "B"]],          # 醫療唔係藉口
}}


def horse(code, placings, raw=60.0):
    hist = [{"date": d, "placing": p} for d, p in placings]
    return {"horse_code": f"HK_2024_{code}", "_data": {"hk_history": hist},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class ExcuseStreakTest(unittest.TestCase):
    def test_streak_conditions(self):
        h = horse("J437", [("2026-11-01", 5), ("2026-10-07", 7)])
        s = ex.streak(h, "2026-11-18", TABLE)
        self.assertEqual(s, {"dates": ["2026-11-01", "2026-10-07"], "flags": ["BS", "W"], "placings": [5, 7]})
        self.assertIsNone(ex.streak(horse("K001", [("2026-11-01", 2), ("2026-10-07", 6)]), "2026-11-18", TABLE))
        self.assertIsNone(ex.streak(horse("K002", [("2026-11-01", 6), ("2026-10-07", 6)]), "2026-11-18", TABLE))
        self.assertIsNone(ex.streak(horse("K003", [("2026-11-01", 6), ("2026-10-07", 6)]), "2026-11-18", TABLE))
        self.assertIsNone(ex.streak(horse("J437", [("2026-11-01", 5)]), "2026-11-18", TABLE))      # 搵唔到名次 → 唔估
        self.assertIsNone(ex.streak(dict(horse("J437", [("2026-11-01", 5), ("2026-10-07", 7)]), horse_code="HK_2025_J937"),
                                    "2026-11-18", TABLE))                                           # 外隊烙號 ≥800
        # 今仗當日嘅報告唔可以用（嚴格早過今仗）：11-01 賽日只睇 09-13、10-07
        self.assertIsNone(ex.streak(horse("J437", [("2026-10-07", 7), ("2026-09-13", 5)]), "2026-11-01", TABLE))

    def test_apply_centred_and_chip(self):
        hs = {"1": horse("J437", [("2026-11-01", 5), ("2026-10-07", 7)]), "2": horse("K001", [("2026-11-01", 2), ("2026-10-07", 6)]),
              "3": horse("K009", [])}
        self.assertEqual(ex.apply(hs, "2026-11-18", TABLE), 3)
        adds = [hs[k]["python_auto"]["excuse_streak_delta"] for k in hs]
        self.assertAlmostEqual(sum(adds), 0.0, places=3)
        self.assertGreater(adds[0], 0)
        chip = tags._excuse_streak_tag(hs["1"]["python_auto"])[0]
        self.assertEqual((chip["key"], chip["scored"], chip["tone"], chip["label"]), ("excuse_streak", True, "good", "連續兩仗有藉口"))
        self.assertIn("11-01 第5名（受阻）", chip["why"])
        self.assertIn("10-07 第7名（走外疊）", chip["why"])

    def test_disabled_and_no_member(self):
        hs = {"1": horse("K001", [("2026-11-01", 2), ("2026-10-07", 6)])}
        self.assertEqual(ex.apply(hs, "2026-11-18", TABLE), 0)
        ex.ENABLED = False
        try:
            hs = {"1": horse("J437", [("2026-11-01", 5), ("2026-10-07", 7)])}
            self.assertEqual(ex.apply(hs, "2026-11-18", TABLE), 0)
        finally:
            ex.ENABLED = True


if __name__ == "__main__":
    unittest.main()
