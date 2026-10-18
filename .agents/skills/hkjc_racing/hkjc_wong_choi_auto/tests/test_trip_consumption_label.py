"""EXP-20261018-05：「中低消耗」唔可以當「低消耗」。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine, _consumption_label  # noqa: E402

MAP = scoring.RACE_SHAPE_TRIP_CONSUMPTION_SCORES


def window(*labels):
    return " | ".join(
        f"第{i}仗(01/01/2026 沙田 1200): 沿途位=3-3-2, XW=(1W1W), 消耗={lab}, 名次=2, 距離=1"
        for i, lab in enumerate(labels, 1)
    )


class ConsumptionLabelTests(unittest.TestCase):
    def test_each_label_maps_to_its_own_key(self):
        cases = {"低消耗": "低消耗", "中低消耗": "中低", "中等消耗": "中等", "高消耗": "高", "極高消耗": "極高"}
        for value, key in cases.items():
            self.assertEqual(_consumption_label(window(value), MAP), key, value)

    def test_missing_label_is_none(self):
        for value in ("-", "N/A"):
            self.assertIsNone(_consumption_label(window(value), MAP))

    def test_trip_score_uses_medium_low_value(self):
        engine = RacingEngine({"_data": {"position_window": window("中低消耗", "中低消耗", "中低消耗")}},
                              {"venue": "沙田", "distance": "1200m"})
        score, note = engine._trip_consumption_score()
        self.assertEqual(score, MAP["中低"])
        self.assertIn("中低", note)


if __name__ == "__main__":
    unittest.main()
