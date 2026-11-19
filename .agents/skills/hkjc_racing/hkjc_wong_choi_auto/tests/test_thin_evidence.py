"""薄證據收窄（EXP-20261119-05）：群組條件、收窄唔係扣分、場均唔變、外隊／初出唔套用、退回開關、chip。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import tags  # noqa: E402
from hkjc_racing_engine import thin_evidence as te  # noqa: E402


def horse(raw, hist=(), code="HK_2025_L183"):
    return {"horse_code": code, "_data": {"hk_history": [{"date": d} for d in hist]},
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


CTX = {"race_date": "2026-11-18"}


class ThinEvidenceTest(unittest.TestCase):
    def test_profile_conditions(self):
        self.assertEqual(te.profile(horse(70, ["2026-04-12"]), "2026-11-18"), {"starts": 1, "gap": 220})
        self.assertIsNone(te.profile(horse(70, ["2026-08-12"]), "2026-11-18"))              # 休唔夠 180 日
        self.assertIsNone(te.profile(horse(70, ["2026-04-12"] * 3), "2026-11-18"))          # 3 仗
        self.assertIsNone(te.profile(horse(70, []), "2026-11-18"))                          # 初出
        self.assertIsNone(te.profile(horse(70, ["2026-04-12"], code="HK_2026_M999"), "2026-11-18"))  # 外隊

    def test_shrink_not_penalty_and_mean_kept(self):
        raws = {"1": 80.0, "2": 72.0, "3": 60.0, "4": 52.0}
        top = te.adjustments(raws, {"2"})
        low = te.adjustments(raws, {"4"})
        self.assertLess(top["2"], 0)            # 高過場均 → 跌
        self.assertGreater(low["4"], 0)         # 低過場均 → 升（唔壓冷門）
        for adds in (top, low):
            self.assertAlmostEqual(sum(adds.values()), 0.0, places=9)

    def test_apply_moves_member_toward_mean(self):
        hs = {"1": horse(80, ["2026-10-01"] * 5), "2": horse(72, ["2026-04-12"]), "3": horse(60, ["2026-10-01"] * 5),
              "4": horse(52, ["2026-10-01"] * 5)}
        self.assertEqual(te.apply(hs, CTX), 4)
        a = hs["2"]["python_auto"]
        self.assertEqual(a["thin_evidence"], {"starts": 1, "gap": 220, "lam": 0.5})
        self.assertLess(a["ability_score_raw"], 72.0)
        chip = tags._thin_evidence_tag(a)[0]
        self.assertEqual((chip["key"], chip["scored"], chip["tone"]), ("thin_evidence", True, "bad"))
        self.assertIn("香港 1 仗、休 220 日", chip["label"])

    def test_disabled_and_no_member(self):
        hs = {"1": horse(80, ["2026-10-01"]), "2": horse(60, ["2026-10-01"])}
        self.assertEqual(te.apply(hs, CTX), 0)
        te.ENABLED = False
        try:
            hs = {"1": horse(80, ["2026-04-12"]), "2": horse(60, ["2026-10-01"])}
            self.assertEqual(te.apply(hs, CTX), 0)
        finally:
            te.ENABLED = True


if __name__ == "__main__":
    unittest.main()
