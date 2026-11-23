"""初出馬練馬師初出紀錄入分（EXP-20261123-13）：只限初出馬、場內置中、as-of、冇初出馬唔郁、退回開關、chip 入分。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hkjc_racing_engine import debut_trainer as dt  # noqa: E402
from hkjc_racing_engine import tags  # noqa: E402

EV = [["2026-01-01", "甲", 1], ["2026-02-01", "甲", 1], ["2026-03-01", "乙", 0], ["2026-11-22", "甲", 0]]


def horse(trainer, debut, raw=60.0):
    return {"trainer": trainer, "is_debut": debut,
            "python_auto": {"ability_score_raw": raw, "ability_score": 60.0, "grade": "B"}}


class DebutTrainerScoringTest(unittest.TestCase):
    def test_as_of_and_centred(self):
        r = dt.rate("甲", "2026-11-22", EV)
        self.assertEqual((r["places"], r["starts"]), (2, 2))         # 同日唔計
        hs = {"1": horse("甲", True), "2": horse("乙", True), "3": horse("丙", False)}
        adj = dt.adjustments(hs, "2026-11-22", EV)
        self.assertAlmostEqual(sum(a for a, _ in adj.values()), 0.0, places=6)
        self.assertGreater(adj["1"][0], adj["2"][0])
        self.assertIsNone(adj["3"][1])

    def test_apply_tag_and_disable(self):
        dt._EVENTS = EV
        try:
            hs = {"1": horse("甲", True), "2": horse("乙", False)}
            self.assertEqual(dt.apply(hs, {"race_date": "2026-11-22"}), 2)
            self.assertIn("debut_trainer_delta", hs["1"]["python_auto"])
            t = tags._debut_trainer_tag(hs["1"], {"date": "2026-11-22"})
            self.assertTrue(t and t[0]["scored"])
            self.assertEqual(dt.apply({"1": horse("甲", False), "2": horse("乙", False)}, {"race_date": "2026-11-22"}), 0)
            dt.ENABLED = False
            self.assertEqual(dt.apply({"1": horse("甲", True), "2": horse("乙", False)}, {"race_date": "2026-11-22"}), 0)
        finally:
            dt.ENABLED = True
            dt._EVENTS = None


if __name__ == "__main__":
    unittest.main()
