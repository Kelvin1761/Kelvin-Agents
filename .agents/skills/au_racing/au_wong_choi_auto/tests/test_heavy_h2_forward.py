"""EXP-20261105-06 H2 forward：反事實「今場大爛地用舊公式」一定要同引擎開 H2 時一樣。

2026-11-05 已用 2026-10-24 Eagle Farm（Heavy 9，10 場、88 匹）實測：一邊 main（C2）評分後用
`h2_scores` 重砌，一邊研究分支 `WC_AU_FQ_HEAVY=H2` 真引擎評分，最大差 0.0024 分。呢度鎖住條式。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))

from au_heavy_h2_forward import h2_scores, today_going  # noqa: E402
from au_racing_engine.stability import is_heavy_going, legacy_raw  # noqa: E402


def run(zp, zr, w, pct):
    zq = zr * (1 - pct) if zr > 0 else zr
    return {"z_place": zp, "z_prize": zq, "z_prize_raw": zr, "weight": w, "value": (zp + zq) / 2}


def horse(runs, field_mean, field_stdev, field_count, score):
    raw = sum(r["value"] * r["weight"] for r in runs) / sum(r["weight"] for r in runs)
    detail = {"raw": raw, "run_count": len(runs), "field_count": field_count, "field_mean": field_mean,
              "field_stdev": field_stdev, "runs": runs}
    return {"python_auto": {"feature_scores": {"form_quality_score": score},
                            "stability_detail": {"form_quality": detail}}}


class H2Tests(unittest.TestCase):
    def test_legacy_raw_ignores_discount(self) -> None:
        runs = [run(-1.0, 2.0, 1.0, 0.9), run(0.5, -0.4, 0.8, 0.2)]
        self.assertAlmostEqual(legacy_raw(runs), ((-1.0 + 2.0) / 2 * 1.0 + (0.5 - 0.4) / 2 * 0.8) / 1.8)

    def test_pre_c2_rows_use_z_prize(self) -> None:
        self.assertAlmostEqual(legacy_raw([{"z_place": 1.0, "z_prize": 1.0, "weight": 1.0},
                                           {"z_place": 0.0, "z_prize": 0.0, "weight": 1.0}]), 0.5)

    def test_field_recomputed_from_legacy_raw(self) -> None:
        a = [run(-1.5, 4.0, 1.0, 1.0), run(-1.5, 4.0, 0.8, 1.0)]     # 大賽包尾：C2 −0.75，舊 +1.25
        b = [run(1.5, 0.2, 1.0, 0.0), run(1.5, 0.2, 0.8, 0.0)]       # 細賽贏
        c = [run(0.0, 0.0, 1.0, 0.5), run(0.0, 0.0, 0.8, 0.5)]
        raws = [(-1.5 + 0.0) / 2, (1.5 + 0.2) / 2, 0.0]
        mean = sum(raws) / 3
        sd = (sum((r - mean) ** 2 for r in raws) / 3) ** 0.5
        horses = {str(i + 1): horse(r, mean, sd, 3, 60 + 20 * (raw - mean) / sd)
                  for i, (r, raw) in enumerate(zip((a, b, c), raws))}
        out, problem = h2_scores(horses)
        self.assertEqual(problem, "")
        self.assertGreater(out["1"], out["2"])         # 舊公式：大賽包尾高過細賽贏（正正係 C2 想修嘅嘢）
        self.assertLess(horses["1"]["python_auto"]["feature_scores"]["form_quality_score"],
                        horses["2"]["python_auto"]["feature_scores"]["form_quality_score"])

    def test_rebuild_mismatch_is_skipped(self) -> None:
        a = [run(0.5, 0.5, 1.0, 0.2), run(0.5, 0.5, 0.8, 0.2)]
        h = horse(a, 0.0, 1.0, 3, 10.0)                  # 儲存分數同重砌對唔上
        h["python_auto"]["stability_detail"]["form_quality"]["field_mean"] = None
        self.assertEqual(h2_scores({"1": h})[1], "live_rebuild_mismatch")

    def test_missing_stored_detail_is_not_unchanged(self) -> None:
        self.assertEqual(h2_scores({"1": {"python_auto": {"feature_scores": {"form_quality_score": 60}}}})[1],
                         "no_stored_detail")

    def test_heavy_detection(self) -> None:
        self.assertTrue(is_heavy_going("Heavy 8"))
        self.assertTrue(is_heavy_going("Heavy"))
        self.assertFalse(is_heavy_going("Soft 7"))
        logic = {"race_analysis": {"going": "Good 4", "meeting_intelligence": {"going": "Heavy 9"}}}
        self.assertEqual(today_going(logic), "Heavy 9")


if __name__ == "__main__":
    unittest.main()
