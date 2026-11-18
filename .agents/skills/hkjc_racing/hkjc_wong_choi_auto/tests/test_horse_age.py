"""馬齡組件（EXP-20261119-01 A2）：6 歲以下中性、每歲 β、場內置中、冇馬齡中性、退回開關。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import horse_age as ha  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402


def horse(age, raw=60.0):
    return {"_data": {"age": age}, "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class HorseAgeTest(unittest.TestCase):
    def test_years_over(self):
        self.assertEqual(ha.years_over(horse(9)), 3)
        self.assertEqual(ha.years_over(horse(6)), 0)
        self.assertEqual(ha.years_over(horse(4)), 0)
        self.assertEqual(ha.years_over(horse(None)), 0)
        self.assertEqual(ha.years_over(horse("8")), 2)

    def test_apply_centred_tag_and_disable(self):
        hs = {"1": horse(9), "2": horse(5), "3": horse(None)}
        self.assertEqual(ha.apply(hs), 3)
        d = {k: h["python_auto"]["horse_age_delta"] for k, h in hs.items()}
        self.assertAlmostEqual(sum(d.values()), 0.0, places=6)
        self.assertAlmostEqual(d["1"] - d["2"], 3 * ha.BETA_PER_YEAR, places=4)
        self.assertAlmostEqual(d["2"], d["3"], places=6)
        t = tags._horse_age_tag(hs["1"]["python_auto"])
        self.assertEqual(t[0]["label"], "9 歲")
        self.assertEqual(tags._horse_age_tag(hs["2"]["python_auto"]), [])
        ha.ENABLED = False
        try:
            self.assertEqual(ha.apply({"1": horse(9), "2": horse(5)}), 0)
        finally:
            ha.ENABLED = True


if __name__ == "__main__":
    unittest.main()
