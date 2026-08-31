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

    def test_the_ability_scale_is_actually_used_by_the_validator(self) -> None:
        """釘住 validator 真係讀 MATRIX_ABILITY_SCALE。

        缺咗個除法一樣可以「冇 mismatch」——如果 scale 剛好係 1.0。
        所以直接查來源。
        """
        src = (SCRIPTS / "au_racing_engine" / "validation.py").read_text(
            encoding="utf-8")
        self.assertIn("MATRIX_ABILITY_SCALE", src)

    def test_every_known_copy_imports_the_scale(self) -> None:
        """七份複本清單 —— 加新複本就要加落呢度。"""
        copies = [
            SCRIPTS / "au_racing_engine" / "scoring.py",
            SCRIPTS / "au_racing_engine" / "engine_core.py",
            SCRIPTS / "au_racing_engine" / "matrix_mapper.py",
            SCRIPTS / "au_racing_engine" / "validation.py",
            SCRIPTS / "au_eval.py",
            SCRIPTS / "au_matrix_refit.py",
            ROOT / ".agents" / "skills" / "shared_racing" / "scripts"
                 / "golden_scoring.py",
        ]
        missing = [p.name for p in copies
                   if p.exists()
                   and "MATRIX_ABILITY_SCALE" not in p.read_text(encoding="utf-8")]
        self.assertEqual(missing, [],
                         f"呢幾份 ability 式複本冇 MATRIX_ABILITY_SCALE：{missing}")


if __name__ == "__main__":
    unittest.main()
