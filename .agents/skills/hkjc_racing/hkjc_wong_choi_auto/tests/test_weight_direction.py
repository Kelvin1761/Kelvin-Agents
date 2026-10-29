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

    def test_body_weight_trend_no_longer_moves_the_handicap_score(self):
        """EXP-20261010-04：馬匹體重係健康訊號（risk_score 已計），負磅分只計讓磅。"""
        self.assertNotIn("trend_lighter_bonus", scoring.WEIGHT_MICRO_WEIGHTS)
        self.assertNotIn("trend_heavier_pen", scoring.WEIGHT_MICRO_WEIGHTS)
        base = scoring.WEIGHT_MICRO_WEIGHTS["base"]
        self.assertEqual(_score(126, "轉輕")[0], base)
        self.assertEqual(_score(126, "轉重")[0], base)


if __name__ == "__main__":
    unittest.main()


class ApprenticeAllowance(unittest.TestCase):
    """負磅分用**宣佈負磅**：見習減磅係騎師嘅減磅，唔係讓磅官嘅意見（EXP-20261029-30）。

    Logic `weight_carried` 係實際負磅（已扣減磅，EXP-20261018-06：327/335 同賽果 actual_wt
    一樣），所以宣佈負磅 = 實際 + 減磅；orchestrator 由排位表直接寫 `declared_weight`。
    """

    def _engine(self, carried, allowance, declared=None):
        engine = RacingEngine.__new__(RacingEngine)
        engine.horse_data = {"weight_carried": carried}
        engine.data = {"jockey_allowance": allowance}
        if declared is not None:
            engine.data["declared_weight"] = declared
        engine.provenance = {}
        engine.race_analysis = {}
        return engine

    def test_claim_is_added_back_not_subtracted(self):
        score, note, _ = self._engine(123, 3)._weight_score({})
        self.assertEqual(score, scoring.WEIGHT_MICRO_WEIGHTS["base"])
        self.assertIn("宣佈負磅126磅", note)
        self.assertIn("實際負磅 123", note)

    def test_apprentice_does_not_turn_a_mid_weight_into_a_light_weight(self):
        """120 實際 + 3 減磅 = 宣佈 123：讓磅官放佢喺中游，唔係輕磅。"""
        score, _note, _ = self._engine(120, 3)._weight_score({})
        self.assertEqual(score, scoring.WEIGHT_MICRO_WEIGHTS["base"])

    def test_apprentice_on_the_top_weight_keeps_the_top_weight_score(self):
        score, _note, _ = self._engine(128, 5)._weight_score({})
        self.assertEqual(score, scoring.WEIGHT_MICRO_WEIGHTS["heavy_weight_base"])

    def test_racecard_declared_weight_wins(self):
        score, note, _ = self._engine(113, 7, declared=120)._weight_score({})
        self.assertEqual(score, scoring.WEIGHT_MICRO_WEIGHTS["light_weight_base"])
        self.assertIn("宣佈負磅120磅", note)


class NarrativeFollowsScoreDirection(unittest.TestCase):
    """文字方向要跟分數方向（2026-10-29）。

    09-04 調轉咗分數，但 renderer 仲將低負磅分寫成「負磅條件略為吃力」——
    低分而家係輕磅，即係將輕磅講成負擔。一個 leaf 嘅意思抄咗喺引擎 note、
    矩陣描述、風險短語、事實行四處，兩次修正都只改咗一半。
    """

    def test_low_weight_score_is_not_described_as_a_burden(self):
        from hkjc_racing_engine import renderer
        light, _, _ = _score(113)
        phrase = renderer._risk_phrase("weight_score", light)
        for burden in ("吃力", "負擔", "重壓"):
            self.assertNotIn(burden, phrase)
        self.assertIn("輕磅", phrase)

    def test_fact_line_does_not_subtract_the_claim_again(self):
        from hkjc_racing_engine import renderer
        horse = {"python_auto": {}, "_data": {"weight_carried": "113", "jockey_allowance": 7}}
        lines = "\n".join(renderer._matrix_fact_lines("class_advantage", horse))
        self.assertIn("實際負磅=113", lines)
        self.assertIn("宣佈負磅120", lines)
        self.assertNotIn("106", lines)
