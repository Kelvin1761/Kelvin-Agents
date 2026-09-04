"""負磅分嘅方向：重 = 好，輕 = 差。

香港負磅唔係外生嘅負擔，而係讓磅官對馬匹能力嘅意見 —— 贏得多就加評分加負磅。
所以頂磅馬係全場公認最好嘅馬。舊版當「輕磅係好事」，場內 AUC 0.4630（反方向）。

呢個唔係口味問題，係量出嚟嘅：
  * 讓磅官斜率 0.389 分/kg vs 慣例 0.5 —— 加磅加得唔夠狠
  * 控制住模型自己嘅排名後，頂磅馬喺模型排名 4+ 上名率 +8.7pp，
    95% CI [+3.1, +14.3]（n=254 vs 2246）
  * 排名 1-3 嗰批 −2.4pp、CI 跨零 —— 價值喺執返模型睇低嘅好馬

改動見 docs/experiments/EXP-20260904-09-weight-direction.md。
如果將來有人想調返轉，請先重跑 pit_backtest 而唔係靠直覺。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"))

from hkjc_racing_engine import scoring
from hkjc_racing_engine.engine_core import RacingEngine


def _score(weight, trend=""):
    engine = RacingEngine.__new__(RacingEngine)
    engine.horse_data = {"weight_carried": weight, "weight_trend": trend}
    engine.data = {}
    engine.provenance = {}
    engine.race_analysis = {}
    return engine._weight_score({})


class WeightDirection(unittest.TestCase):
    def test_top_weight_beats_light_weight(self):
        heavy, _, _ = _score(133)
        light, _, _ = _score(118)
        self.assertGreater(heavy, light,
                           "頂磅馬要高分過輕磅馬 —— 負磅係讓磅官嘅意見，唔係負擔")

    def test_the_two_ends_are_the_measured_values(self):
        self.assertEqual(scoring.WEIGHT_MICRO_WEIGHTS["heavy_weight_base"], 70.0)
        self.assertEqual(scoring.WEIGHT_MICRO_WEIGHTS["light_weight_base"], 54.0)

    def test_the_middle_band_is_untouched(self):
        """W 只調轉兩端；121-131 磅（56.6% 嘅馬）維持 base。"""
        for weight in (121, 126, 131):
            score, _, _ = _score(weight)
            self.assertEqual(score, scoring.WEIGHT_MICRO_WEIGHTS["base"], weight)

    def test_thresholds_did_not_move(self):
        self.assertEqual(_score(120)[0], scoring.WEIGHT_MICRO_WEIGHTS["light_weight_base"])
        self.assertEqual(_score(132)[0], scoring.WEIGHT_MICRO_WEIGHTS["heavy_weight_base"])

    def test_missing_weight_stays_neutral(self):
        score, note, source = _score(None)
        self.assertEqual(score, 60)
        self.assertEqual(source, "missing_neutral")

    def test_the_note_explains_the_mechanism_not_just_the_number(self):
        """一個調轉方向嘅 leaf 如果唔講原因，下一個讀報告嘅人會當佢係 bug。"""
        _, heavy_note, _ = _score(133)
        self.assertIn("讓磅官", heavy_note)
        _, light_note, _ = _score(118)
        self.assertIn("讓磅官", light_note)

    def test_the_note_number_tracks_the_constant(self):
        """敘述嘅數字唔准硬寫 —— 舊版寫死「70分」，一改常數就講大話。"""
        for weight in (118, 126, 133):
            score, note, _ = _score(weight)
            self.assertIn(f"{score:.0f}分", note)

    def test_bodyweight_trend_terms_are_untouched(self):
        """`weight_trend` 讀嘅係排位體重，唔係負磅 —— 呢個類別混淆未測過，
        W 冇動佢。改咗呢兩項就唔再係量過嗰個候選。"""
        self.assertEqual(scoring.WEIGHT_MICRO_WEIGHTS["trend_lighter_bonus"], 4.0)
        self.assertEqual(scoring.WEIGHT_MICRO_WEIGHTS["trend_heavier_pen"], -4.0)
        base = scoring.WEIGHT_MICRO_WEIGHTS["base"]
        self.assertEqual(_score(126, "轉輕")[0], base + 4.0)
        self.assertEqual(_score(126, "轉重")[0], base - 4.0)


if __name__ == "__main__":
    unittest.main()
