"""EXP-20261018-10：長休馬晨操判讀要睇實際課數，唔可以因為模板有「快操」就一律「充足」。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402


def readout(gallops, trials, trainer="", days=120):
    digest = (f"晨操資料已提取，分類為「狀態延續」。近21日快操{gallops}課、試閘{trials}課、踱步5課、游水3課，空白日2日")
    engine = RacingEngine({"_data": {"days_since_last": days, "trackwork_digest": digest,
                                     "trackwork_trainer": trainer, "medical_flags": "✅ 無醫療事故記錄"}},
                          {"venue": "沙田", "distance": "1200m", "race_date": "2026-10-19"})
    return " ".join(engine._health_readout()["lines"])


class LayoffReadoutTests(unittest.TestCase):
    """2026-11-20 起「夠唔夠」跟 _trackwork_type（快操 ≥5 = 操練密），唔再另有 3＋1 門檻。"""

    def test_only_dense_work_is_sufficient(self):
        text = readout(5, 0)
        self.assertIn("操練密", text)
        self.assertIn("備戰充足", text)
        self.assertNotIn("充足", readout(3, 1))   # 舊門檻叫「充足」，而家同晨操格一致 = 操練正常

    def test_normal_with_trial(self):
        text = readout(3, 1)
        self.assertIn("操練正常＋試閘1次", text)
        self.assertIn("備戰正常", text)

    def test_no_work_is_not_called_sufficient(self):
        text = readout(0, 0)
        self.assertNotIn("充足", text)
        self.assertIn("偏保守", text)
        self.assertIn("快操0課、試閘0課", text)

    def test_middle_is_neutral(self):
        text = readout(3, 0)
        self.assertNotIn("充足", text)
        self.assertNotIn("偏保守", text)
        self.assertIn("未見試閘", text)

    def test_real_work_with_slowing_trend_says_both(self):
        text = readout(4, 1, trainer="操練趨勢放緩")
        self.assertIn("操練正常", text)
        self.assertIn("放緩", text)
        self.assertNotIn("偏保守", text)
        text = readout(6, 1, trainer="操練趨勢放緩")
        self.assertNotIn("充足", text)
        self.assertIn("放緩", text)

    def test_light_work_with_slowing_is_conservative(self):
        self.assertIn("偏保守", readout(1, 0, trainer="操練趨勢放緩"))

    def test_short_rest_has_no_layoff_line(self):
        self.assertNotIn("長休", readout(0, 0, days=20))


if __name__ == "__main__":
    unittest.main()
