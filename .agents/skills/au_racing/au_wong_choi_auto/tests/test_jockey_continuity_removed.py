"""騎師連續性三項退出計分（2026-09-01）—— 守住佢哋唔會靜靜復活。

點解要專門測試：AU golden 嘅 case 係 `{id, features, expected}`（凍結 feature
向量，**冇 `_data`**），所以 `_jockey_horse_fit_score` 由 golden fixture 根本跑唔起。
「golden 120/120 一致」對呢個改動係**預期且無資訊** —— 同 `barrier`（fixture 冇
barrier）、`trajectory`（fixture 冇 trajectory）同一個範圍限制。

三項嘅符號實測同方向相反（條件化量度，1,820 場，控制「曾策騎此駒」次數）：
    離開上仗已證明配搭  0 次層  觸發 +4.09pp vs 冇觸發 −2.96pp  差 +7.05pp
    未及上仗騎師       0 次層  觸發 +4.08pp vs 冇觸發 −0.59pp  差 +4.67pp
    回配熟手騎師       每層都錯（−3.55 / −1.19 / −7.49pp）
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from au_racing_engine.scoring import FIT_MICRO_WEIGHTS  # noqa: E402

ENGINE_SRC = (ROOT / "au_racing_engine" / "engine_core.py").read_text(encoding="utf-8")
REMOVED = ("leave_proven_jockey_pen", "latest_downgrade_pen", "signal_reunite_bonus")
# `add()` 呼叫用過嘅 factor 名。⚠️ 「回配」嗰支而家用 `jockey_change_signal`
# 原文出敘述（因為原文本身已經寫住「回配…」），所以字面 factor 名唔再喺 source。
FACTORS = ("今場離開上仗已證明配搭", "今場騎師對此駒往績未及上仗騎師", "回配熟手騎師")
# 敘述仍然應該存在嘅字眼（唔係 factor 名，係佢哋喺 source 剩返嘅痕跡）。
NARRATIVE = ("今場離開上仗已證明配搭", "今場騎師對此駒往績未及上仗騎師", '"回配" in jockey_change_signal')


class TestJockeyContinuityRemoved(unittest.TestCase):
    def test_constants_are_zero_not_deleted(self):
        """要留 key 做文獻。`engine_core` 原本用 `.get(key, <default>)` ——
        key 唔喺度嘅話，將來有人駁返個 `.get()` 就會令 hard-coded default
        （−4.0 / −3.0 / 2.0）靜靜復活。"""
        for key in REMOVED:
            self.assertIn(key, FIT_MICRO_WEIGHTS, f"{key} 唔可以刪 key，要留 0.0 做文獻")
            self.assertEqual(FIT_MICRO_WEIGHTS[key], 0.0, f"{key} 應該係 0.0")

    def test_no_scoring_call_remains(self):
        """真正嘅守衛：source 入面唔可以再有 `add(...)` 把呢三項入分。"""
        for key in REMOVED:
            self.assertNotRegex(
                ENGINE_SRC,
                rf"add\(\s*FIT_MICRO_WEIGHTS\.get\(\s*[\"']{key}[\"']",
                f"{key} 又被駁返入分 —— 佢符號實測係反嘅",
            )

    def test_factors_are_not_added_by_any_route(self):
        """連 `add(<literal>, \"今場離開上仗…\")` 咁樣繞路都唔准。"""
        for factor in FACTORS:
            for m in re.finditer(rf"add\(([^\n]*?){re.escape(factor)}", ENGINE_SRC):
                self.fail(f"「{factor}」又出現喺 add() 呼叫：{m.group(0)[:80]}")

    def test_narrative_is_kept(self):
        """三個情境對讀者有意義，敘述要保留（標明不入分）。"""
        for token in NARRATIVE:
            self.assertIn(token, ENGINE_SRC, f"「{token}」嘅敘述／分支唔應該一併刪走")
        self.assertGreaterEqual(
            ENGINE_SRC.count("不入分"), 3,
            "三項都應該喺 notes 標明「不入分」",
        )

    def test_display_gain_not_reinflated(self):
        """⚠️ 剷走噪音項令 jockey_trainer raw SD 6.87 → 5.20。實測把 gain 拉返
        「目標 SD 11」會令結果變差（terminal −0.0095 vs 保持原 gain +0.0000）。
        清噪音之後應該讓維度影響力自然下降。"""
        from au_racing_engine.matrix_mapper import MATRIX_DISPLAY_GAINS
        self.assertAlmostEqual(
            MATRIX_DISPLAY_GAINS["jockey_trainer"], 2.4973, places=3,
            msg="jockey_trainer 個 gain 唔應該因為剷走噪音而重算",
        )


if __name__ == "__main__":
    unittest.main()
