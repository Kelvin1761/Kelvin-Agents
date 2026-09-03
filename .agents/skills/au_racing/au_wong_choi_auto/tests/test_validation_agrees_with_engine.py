"""`validation.py` 條 ability 式一定要同 `engine_core` 出嘅分一致。

ability 條式喺 repo 有**七份複本**（scoring / engine_core / matrix_mapper /
validation / au_eval / au_matrix_refit / golden_scoring）。2026-08-26 加
`MATRIX_ABILITY_SCALE` 嗰陣漏咗 `validation.py`，後果係**每次跑 orchestrator
都會逐匹馬報 `SCORE-002` / `SCORE-004`**。

⚠️ 呢個 bug 兩個閘門都捉唔到：
  * `檢查.sh` **唔會跑 orchestrator**（只跑 ruff / golden / 合約 / 單元測試）
  * `golden_scoring` 用自己嗰份 ability 式，唔會 call validator
  * 已有嘅 `test_signal_map.test_ability_equation_is_matrix_plus_declared_overlays`
    只驗 `engine_core` 嗰份

2026-08-31 復發：cherry-pick 顯示尺修正落 au-production 嗰陣冇帶埋 validation
修正，一場七匹馬即刻報 12 個 SCORE-002/004，而 run_tests.sh 十個 suite 同
檢查.sh 全部綠。所以要有一條測試**直接**對住 validator。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
SCRIPTS = (ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto"
           / "scripts")
sys.path.insert(0, str(SCRIPTS))

from au_racing_engine.engine_core import RacingEngine  # noqa: E402
from au_racing_engine.validation import validate_logic_data  # noqa: E402
from au_auto_orchestrator import _build_field_summary  # noqa: E402

FACTS = """- **going:** Soft 6
"""


def _scored_logic(n_horses: int = 5) -> dict:
    """由引擎真正評分，砌一份 orchestrator 會交俾 validator 嘅 Logic。"""
    horses = {}
    for i in range(1, n_horses + 1):
        horses[str(i)] = {
            "horse_number": str(i),
            "horse_name": f"Horse {i}",
            "weight": 55.0 + i,
            "rating": 60.0 + i,
            "jockey": f"J{i}",
            "trainer": f"T{i}",
            "_data": {
                "facts_section": FACTS,
                "going_stats_line": f"3:0-1-0 | 軟地: {i}:0-1-0 | 重地: 0:0-0-0",
            },
        }
    ctx = {"race_number": 1, "going": "Soft 6"}
    ctx["field_summary"] = _build_field_summary(horses)
    for num, horse in horses.items():
        hd = dict(horse)
        eng = RacingEngine(hd, ctx, facts_section=FACTS,
                           facts_path=str(Path("/tmp/2026-08-30_x/x.md")))
        horse["python_auto"] = eng.analyze_horse()
    return {"race_analysis": {"race_number": 1}, "horses": horses}


class ValidationAgreesWithEngineTests(unittest.TestCase):
    def test_no_score_mismatch_on_engine_output(self) -> None:
        """引擎自己評出嘅分，validator 唔可以話唔對。"""
        errors = validate_logic_data(_scored_logic())
        mismatches = [e for e in errors
                      if "SCORE-002" in e or "SCORE-004" in e]
        self.assertEqual(
            mismatches, [],
            "validation.py 條 ability 式同 engine_core 走位咗 —— "
            "檢查所有 MATRIX_ABILITY_SCALE 複本",
        )

    def test_validator_detects_a_corrupted_score(self):
        logic = _scored_logic()
        first = next(iter(logic["horses"].values()))["python_auto"]
        first["ability_score"] += 3.0
        self.assertTrue(any("SCORE-004" in error for error in validate_logic_data(logic)))

    def test_refit_and_engine_use_the_same_equation(self):
        from au_racing_engine.scoring import compose_matrix_score, MATRIX_WEIGHTS
        from au_matrix_refit import Dataset
        from au_racing_engine.matrix_mapper import map_features_to_matrix_scores
        import numpy as np
        auto = next(iter(_scored_logic()["horses"].values()))["python_auto"]
        rows = [{"n": i, "name": str(i), "pos": i, "sp": "3", "features": auto["feature_scores"],
                 "wet": 0, "proven_class": 0, "ability": 60} for i in range(1,5)]
        import json
        from types import SimpleNamespace
        payload = {"races": [{"date":"2026-08-30", "race":1, "field":4, "rows":rows}]}
        ds = Dataset(SimpleNamespace(read_text=lambda **kw: json.dumps(payload)))
        expected = compose_matrix_score(map_features_to_matrix_scores(auto["feature_scores"]))
        self.assertTrue(np.allclose(ds.ability(ds.dim_matrix(), MATRIX_WEIGHTS), expected, atol=.0001))


if __name__ == "__main__":
    unittest.main()
