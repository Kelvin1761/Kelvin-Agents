"""PI 覆蓋解鎖：`Settled` 缺失時用 800m 檢查點。

守住三樣：格式解析啱、優先次序啱（settled 先）、唔夠資料就唔猜。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_racing_engine.engine_core import parse_trajectory, pi_from_trajectory  # noqa: E402


class TestTrajectoryParse(unittest.TestCase):
    def test_marks_are_checkpoints_not_ordinals(self):
        """`8th5` = 800m 第 5 位。當成序數詞讀就會全錯。"""
        self.assertEqual(parse_trajectory("S5→8th5→4th4→F2"),
                         {"S": 5, 8: 5, 4: 4, "F": 2})

    def test_partial_trajectory(self):
        self.assertEqual(parse_trajectory("8th7→4th8→F5"), {8: 7, 4: 8, "F": 5})

    def test_junk_is_ignored_not_guessed(self):
        for text in ("", None, "-", "未知", "→→", "F"):
            self.assertNotIn("F", parse_trajectory(text))


class TestPiFallback(unittest.TestCase):
    def test_settled_is_preferred(self):
        """PI = 落後位置 − 終點（8,852 條實測 100% 吻合）。"""
        self.assertEqual(pi_from_trajectory("S5→8th5→4th4→F2"), (3.0, "settled"))

    def test_800m_used_only_when_settled_missing(self):
        self.assertEqual(pi_from_trajectory("8th7→4th8→F5"), (2.0, "800m"))

    def test_400m_is_never_used(self):
        """400m 代理偏差 +0.277 / SD 1.684，明顯差過 800m —— 唔用。"""
        self.assertEqual(pi_from_trajectory("4th8→F5"), (None, ""))

    def test_no_finish_means_no_pi(self):
        for text in ("S5→8th5→4th4", "S5", "8th7"):
            self.assertEqual(pi_from_trajectory(text), (None, ""))

    def test_negative_pi_is_preserved(self):
        """失位（PI 負）係真證據，唔可以當缺失。"""
        self.assertEqual(pi_from_trajectory("S2→8th2→4th1→F6"), (-4.0, "settled"))
        self.assertEqual(pi_from_trajectory("8th2→F6"), (-4.0, "800m"))

    def test_zero_pi_is_a_value_not_a_gap(self):
        value, mark = pi_from_trajectory("S3→8th3→F3")
        self.assertEqual(value, 0.0)
        self.assertEqual(mark, "settled")

    def test_junk_returns_no_value(self):
        for text in ("", None, "-", "未知"):
            self.assertEqual(pi_from_trajectory(text), (None, ""))


if __name__ == "__main__":
    unittest.main()
