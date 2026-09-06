"""騎練組合獨立一節 —— 恆等變換，一分都唔准改。

背景：組合喺計分上面攤入騎師分（55%）／練馬師分（45%），而維度公式又係
0.55·騎師 + 0.45·練馬師，所以佢對維度分嘅**淨**貢獻係 0.55²+0.45² = 50.5%。
以前份報告淨係印「騎師分 X x 55%、練馬師分 Y x 45%」，讀者見唔到組合出咗幾多力。

2026-09-06 實測（EXP-20260905-03，193 場 / 2,438 runner）：呢 50.5% **唔係損耗**。
組合超額同 `jockey_score` ρ=+0.79、同 `trainer_score` ρ=+0.60 —— 攤分係喺度
防止同一份證據數兩次。七個放大幅度嘅 A/B arm 全部令 gold 跌（×1.98 → −2.08pp）。

所以呢一節純粹係**報告**：反解出嚟獨立列，唔郁任何分。呢個檔守住三件事：
  1. 拆解係恆等式（加返埋一定等於原本嘅維度貢獻）
  2. 傳導率由 MATRIX_FORMULAS 讀，唔係寫死 0.55/0.45
  3. 剪裁（clip）嗰陣要標出嚟，唔可以靜靜印一個對唔返嘅拆解
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"))

from hkjc_racing_engine import renderer
from hkjc_racing_engine.matrix_mapper import MATRIX_FORMULAS, formula_share


def _detail(adj, j_share, t_share, j_final, t_final, clipped=False):
    net = (j_share * formula_share("trainer_signal", "jockey_score")
           + t_share * formula_share("trainer_signal", "trainer_score"))
    return {
        "jockey_final": j_final,
        "trainer_final": t_final,
        "adjustments": [{"factor": "騎練組合", "target": "騎師分/練馬師分",
                         "delta": adj, "evidence": "甲×乙 拍檔100仗：勝率15.0%、上名率38.0%"}],
        "combo_split": {
            "adj": adj, "jockey_share": j_share, "trainer_share": t_share,
            "net_dimension_points": round(net, 3),
            "jockey_ex_combo": round(j_final - j_share, 2),
            "trainer_ex_combo": round(t_final - t_share, 2),
            "clipped": clipped,
        },
    }


class ComboSectionIdentity(unittest.TestCase):
    def test_decomposition_is_an_identity(self):
        """扣返組合嘅分 + 淨貢獻 ≡ 原本嘅維度貢獻。差一個 float epsilon 都唔得。"""
        wj = formula_share("trainer_signal", "jockey_score")
        wt = formula_share("trainer_signal", "trainer_score")
        for adj in (-2.0, 2.0, 4.0):
            j_share = adj * 0.55
            t_share = adj * 0.45
            j_final, t_final = 68.0 + j_share, 62.0 + t_share
            split = _detail(adj, j_share, t_share, j_final, t_final)["combo_split"]
            direct = wj * j_final + wt * t_final
            decomposed = (wj * split["jockey_ex_combo"]
                          + wt * split["trainer_ex_combo"]
                          + split["net_dimension_points"])
            self.assertAlmostEqual(direct, decomposed, places=6,
                                   msg=f"adj={adj} 拆解對唔返維度貢獻")

    def test_transmission_is_read_from_the_formula_not_hardcoded(self):
        """公式一改，傳導率要跟住改 —— 寫死 0.55/0.45 嘅報告會靜靜印錯數。"""
        saved = MATRIX_FORMULAS["trainer_signal"]
        try:
            MATRIX_FORMULAS["trainer_signal"] = (("jockey_score", 0.70), ("trainer_score", 0.30))
            self.assertAlmostEqual(formula_share("trainer_signal", "jockey_score"), 0.70)
            split = _detail(4.0, 2.2, 1.8, 70.2, 61.8)["combo_split"]
            self.assertAlmostEqual(split["net_dimension_points"], 2.2 * 0.70 + 1.8 * 0.30, places=6)
        finally:
            MATRIX_FORMULAS["trainer_signal"] = saved
        # 現行公式下面淨傳導率係 0.505
        self.assertAlmostEqual(
            formula_share("trainer_signal", "jockey_score") ** 2
            + formula_share("trainer_signal", "trainer_score") ** 2,
            0.505, places=3)

    def test_absent_feature_has_zero_share(self):
        self.assertEqual(formula_share("trainer_signal", "speed_score"), 0.0)
        self.assertEqual(formula_share("no_such_dimension", "jockey_score"), 0.0)


class ComboSectionRendering(unittest.TestCase):
    def test_renders_the_net_contribution(self):
        lines = renderer._combo_section_lines({"trainer_signal_detail": _detail(4.0, 2.2, 1.8, 70.2, 61.8)})
        body = "\n".join(lines)
        self.assertIn("騎練組合（獨立一節）", body)
        self.assertIn("+2.02 分", body)          # 4.0 × 0.505
        self.assertIn("拍檔100仗", body)          # 證據要跟埋出嚟
        self.assertIn("68.0", body)              # 扣返組合之後嘅騎師分

    def test_zero_adjustment_still_explains_itself(self):
        lines = renderer._combo_section_lines({"trainer_signal_detail": _detail(0.0, 0.0, 0.0, 68.0, 62.0)})
        self.assertTrue(any("+0.00 分" in line for line in lines))

    def test_clipping_is_flagged_not_hidden(self):
        lines = renderer._combo_section_lines(
            {"trainer_signal_detail": _detail(4.0, 2.2, 1.8, 100.0, 61.8, clipped=True)})
        self.assertTrue(any("⚠️" in line for line in lines), "撞邊界要標出嚟")

    def test_no_detail_renders_nothing(self):
        self.assertEqual(renderer._combo_section_lines({}), [])
        self.assertEqual(renderer._combo_section_lines({"trainer_signal_detail": {}}), [])


if __name__ == "__main__":
    unittest.main()


class TrainerVenueRead(unittest.TestCase):
    """練馬師場地往績：印得出、唔入分、樣本唔夠就唔好亂噏。"""

    def test_renders_direction_and_says_it_is_not_scored(self):
        lines = renderer._trainer_venue_lines({"trainer_signal_detail": {"trainer_venue": {
            "venue": "跑馬地", "starts": 356, "place_rate": 26.4,
            "overall_place_rate": 31.8, "delta": -5.4}}})
        body = "\n".join(lines)
        self.assertIn("唔入分", body)
        self.assertIn("跑馬地356仗", body)
        self.assertIn("-5.4pp", body)
        self.assertIn("呢個場地表現偏弱", body)

    def test_small_gap_is_not_dressed_up_as_a_preference(self):
        body = "\n".join(renderer._trainer_venue_lines({"trainer_signal_detail": {"trainer_venue": {
            "venue": "沙田", "starts": 722, "place_rate": 29.8,
            "overall_place_rate": 29.8, "delta": 0.0}}}))
        self.assertIn("同自己平均差唔多", body)
        self.assertNotIn("偏好", body)

    def test_absent_read_renders_nothing(self):
        self.assertEqual(renderer._trainer_venue_lines({}), [])
        self.assertEqual(renderer._trainer_venue_lines({"trainer_signal_detail": {}}), [])
        self.assertEqual(
            renderer._trainer_venue_lines({"trainer_signal_detail": {"trainer_venue": None}}), [])


class TrainerVenuePriorLoading(unittest.TestCase):
    """個統計檔可能仲未生成 —— 缺檔只可以少一行報告，唔可以令評分死。"""

    def test_empty_priors_expose_trainer_venue(self):
        from hkjc_racing_engine.live_priors import EmptyTrainerSignalPriors
        self.assertEqual(EmptyTrainerSignalPriors().trainer_venue, {})

    def test_engine_returns_none_without_rows(self):
        from hkjc_racing_engine.engine_core import RacingEngine

        class _Stack:
            trainer_venue = {}

        engine = RacingEngine.__new__(RacingEngine)
        self.assertIsNone(engine._trainer_venue_read(_Stack(), "某練馬師"))
        self.assertIsNone(engine._trainer_venue_read(None, "某練馬師"))

    def test_thin_sample_is_withheld(self):
        """<50 仗唔好印 —— 一個 12 仗嘅『場地偏好』係噪音。"""
        from hkjc_racing_engine.engine_core import RacingEngine

        class _Stack:
            trainer_venue = {("練", "沙田"): {"starts": 12.0, "places": 6.0, "place_rate": 50.0}}

        engine = RacingEngine.__new__(RacingEngine)
        engine._is_sha_tin_context = lambda: True
        self.assertIsNone(engine._trainer_venue_read(_Stack(), "練"))

    def test_delta_is_against_the_trainers_own_overall_rate(self):
        from hkjc_racing_engine.engine_core import RacingEngine

        class _Stack:
            trainer_venue = {
                ("練", "沙田"): {"starts": 100.0, "places": 40.0, "place_rate": 40.0},
                ("練", "跑馬地"): {"starts": 100.0, "places": 20.0, "place_rate": 20.0},
            }

        engine = RacingEngine.__new__(RacingEngine)
        engine._is_sha_tin_context = lambda: True
        read = engine._trainer_venue_read(_Stack(), "練")
        self.assertEqual(read["venue"], "沙田")
        self.assertAlmostEqual(read["overall_place_rate"], 30.0)   # (40+20)/200
        self.assertAlmostEqual(read["delta"], 10.0)
