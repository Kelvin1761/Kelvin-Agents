"""EXP-20261018-08：「(強組比例: …)」入面個「強」字唔可以令弱組變 strong。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


def signal(label):
    engine = RacingEngine.__new__(RacingEngine)
    engine.horse_data = {"formline_strength": label}
    engine.data = {}
    return engine._formline_strength_signal()


class FormlineLabelTests(unittest.TestCase):
    def test_real_labels(self):
        cases = {
            "✅✅ 極強 (強組比例: 4/5)": "elite",
            "✅ 強 (強組比例: 3/5)": "strong",
            "中強 (強組比例: 2/5)": "strong",
            "中弱 (強組比例: 1/5)": "weak",
            "❌ 弱 (強組比例: 0/5)": "weak",
            "無資料 (強組比例: N/A)": "unknown",
            "N/A": "unknown",
            "": "unknown",
        }
        for label, expected in cases.items():
            self.assertEqual(signal(label), expected, label)


if __name__ == "__main__":
    unittest.main()
