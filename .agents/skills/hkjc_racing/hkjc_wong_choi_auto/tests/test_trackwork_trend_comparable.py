"""EXP-20261018-11：首尾快操時間相差 >4 秒（唔同路程）唔計加強／放緩。"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from hkjc_racing_engine import scoring  # noqa: E402
from hkjc_racing_engine.engine_core import RacingEngine  # noqa: E402

W = scoring.TRACKWORK_MICRO_WEIGHTS


def score(trend_word, times):
    digest = f"晨操資料已提取，分類為「狀態延續」。近21日快操{len(times)}課、試閘0課、踱步0課、游水0課，空白日0日；操練趨勢{trend_word}。"
    horse = {"_data": {"trackwork_digest": digest},
             "trackwork": {"summary": {"gallops_21d": 0, "trials_21d": 0, "trotting_21d": 0,
                                       "swimming_21d": 0, "gallop_times": times}}}
    return RacingEngine(horse, {"venue": "沙田"})._trackwork_trend_score()


class TrackworkTrendTests(unittest.TestCase):
    """舊讀法（TRACKWORK_SCORING="on"）嘅行為；live 預設係 off。"""

    def setUp(self):
        self._saved = scoring.TRACKWORK_SCORING
        scoring.TRACKWORK_SCORING = "on"

    def tearDown(self):
        scoring.TRACKWORK_SCORING = self._saved

    def test_comparable_times_keep_trend(self):
        self.assertEqual(score("加強", [56.0, 55.0])[0], W["improving_base"])
        self.assertEqual(score("放緩", [55.0, 56.0])[0], W["slowing_base"])

    def test_different_distance_times_are_neutral(self):
        self.assertEqual(score("加強", [84.0, 55.0])[0], W["neutral_base"])
        self.assertEqual(score("放緩", [26.3, 55.0])[0], W["neutral_base"])

    def test_missing_times_keep_label(self):
        self.assertEqual(score("加強", [])[0], W["improving_base"])


class TrackworkRetiredTests(unittest.TestCase):
    """EXP-20261029-02：晨操退出排名，leaf 同初出備戰分都係中性。"""

    def test_live_default_is_off(self):
        self.assertEqual(scoring.TRACKWORK_SCORING, "off")

    def test_leaf_and_debut_prep_are_neutral(self):
        self.assertEqual(score("加強", [56.0, 55.0])[0], 60.0)
        horse = {"_data": {"trackwork_digest": "維持分85、備戰分100、復刻分98。"}}
        self.assertEqual(RacingEngine(horse, {"venue": "沙田"})._prep_score(), 60.0)


if __name__ == "__main__":
    unittest.main()
