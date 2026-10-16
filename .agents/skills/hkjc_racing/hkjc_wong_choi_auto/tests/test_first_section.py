"""最快第一段（EXP-20261016-52/53）：Facts 解析 + 段速分段。"""
import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_auto_orchestrator import _first_section_min_delta  # noqa: E402
from hkjc_racing_engine import engine_core  # noqa: E402

SpeedScorer = engine_core.SpeedScorer  # engine_core 用 top-level `speed`，要用同一個 class

TWELVE = """### 馬號 1 — 甲
📊 **全段速剖面 (Full Sectional Profile — 近 6 仗):**
| # | 日期 | 距離 | S1 | S2 | S3 | S4 | Δ1 | Δ2 | Δ3 | Δ4 | 形態 |
|---|------|------|--- | --- | --- | ---|--- | --- | --- | ---|------|
| 1 | 12/07/2026 | 1400 | 13.79 | 21.61 | 23.33 | 23.46 | +0.34 | -0.09 | -0.02 | +0.11 | 快開慢收 ⚠️ |
| 2 | 21/06/2026 | 1200 | 24.39 | 22.40 | 22.56 | - | -0.64 | -0.05 | -0.49 | - | 漸進加速 ✅ |
🔧 **引擎 (速度分佈):**
"""

FOURTEEN = """### 馬號 2 — 乙
📊 **全段速剖面 (Full Sectional Profile — 近 6 仗):**
| # | 日期 | 距離 | S1 | S2 | S3 | S4 | S5 | Δ1 | Δ2 | Δ3 | Δ4 | Δ5 | 形態 |
|---|------|------|--- | --- | --- | --- | ---|--- | --- | --- | --- | ---|------|
| 1 | 16/09/2026 | 1650 | 29.49 | 23.64 | 23.97 | 23.11 | - | +1.69 | -0.16 | +0.07 | -0.49 | - | 均速型 ✅ |
| 2 | 09/11/2025 | 1800 | 14.36 | 22.79 | 23.56 | 23.24 | 23.86 | +0.41 | +0.19 | -0.34 | -0.61 | +1.06 | 波動型 ➖ |
🔧 **引擎 (速度分佈):**
"""


def horse(delta):
    data = {"raw_l400": "23.40", "l400_trend": "穩定"}
    if delta is not None:
        data["first_section_min_delta"] = delta
    return {"_data": data}


class FirstSectionTests(unittest.TestCase):
    def test_twelve_column_table(self):
        self.assertEqual(_first_section_min_delta(TWELVE), -0.64)

    def test_fourteen_column_table_reads_delta1_not_s5(self):
        # 寫死欄位會讀到 S5 / Δ1 錯位；按表頭應該係 min(+1.69, +0.41)
        self.assertEqual(_first_section_min_delta(FOURTEEN), 0.41)

    def test_single_run_is_no_evidence(self):
        one = TWELVE.replace("| 2 | 21/06/2026 | 1200 | 24.39 | 22.40 | 22.56 | - | -0.64 | -0.05 | -0.49 | - | 漸進加速 ✅ |\n", "")
        self.assertIsNone(_first_section_min_delta(one))
        self.assertIsNone(_first_section_min_delta("### 馬號 3 — 丙\n冇剖面\n"))

    def test_bands(self):
        base, _ = SpeedScorer(horse(None), {}).compute()
        for delta, expected in ((-0.5, 4.0), (-0.1, 2.0), (0.1, 0.0), (0.4, -1.0), (0.9, -2.0)):
            scorer = SpeedScorer(horse(delta), {})
            score, _ = scorer.compute()
            self.assertAlmostEqual(score - base, expected, places=2, msg=delta)
            self.assertIn("頭段速度", {d["factor"] for d in scorer.detail})

    def test_missing_field_leaves_score_untouched(self):
        scorer = SpeedScorer(horse(None), {})
        scorer.compute()
        self.assertNotIn("頭段速度", {d["factor"] for d in scorer.detail})


if __name__ == "__main__":
    unittest.main()
