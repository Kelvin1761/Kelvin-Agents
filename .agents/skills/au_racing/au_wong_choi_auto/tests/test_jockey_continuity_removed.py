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

from au_racing_engine.jockey_trainer import FIT_WEIGHTS  # noqa: E402

ENGINE_SRC = ((ROOT / "au_racing_engine" / "engine_core.py").read_text(encoding="utf-8")
              + (ROOT / "au_racing_engine" / "jockey_trainer.py").read_text(encoding="utf-8"))
REMOVED = ("leave_proven_jockey_pen", "latest_downgrade_pen", "signal_reunite_bonus")
# `add()` 呼叫用過嘅 factor 名。⚠️ 「回配」嗰支而家用 `jockey_change_signal`
# 原文出敘述（因為原文本身已經寫住「回配…」），所以字面 factor 名唔再喺 source。
FACTORS = ("今場離開上仗已證明配搭", "今場騎師對此駒往績未及上仗騎師", "回配熟手騎師")
# 敘述仍然應該存在嘅字眼（唔係 factor 名，係佢哋喺 source 剩返嘅痕跡）。
NARRATIVE = ("今場離開上仗已證明配搭", "今場騎師對此駒往績未及上仗騎師", '"回配" in signal')


class TestJockeyContinuityRemoved(unittest.TestCase):
    def test_removed_terms_have_no_weight(self):
        """EXP-20261103-05：入分只喺 `jockey_trainer.fit_parts`，用 `w[key]` 直接讀（冇 `.get` default），
        所以退出計分嘅 key 連同分支一齊剷，唔會靜靜復活。"""
        for key in REMOVED + ("signal_same_jockey_bonus", "latest_jockey_record_mult"):
            self.assertNotIn(key, FIT_WEIGHTS)
        self.assertNotIn(".get(", (ROOT / "au_racing_engine" / "jockey_trainer.py").read_text(encoding="utf-8")
                         .split("def fit_parts", 1)[1])

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

    def test_effective_jockey_weight_not_reinflated(self):
        from au_racing_engine.scoring import MATRIX_WEIGHTS
        self.assertAlmostEqual(MATRIX_WEIGHTS["jockey_trainer"],
                               .245341972 * 2.4973 / .9245975952, places=10)


if __name__ == "__main__":
    unittest.main()
