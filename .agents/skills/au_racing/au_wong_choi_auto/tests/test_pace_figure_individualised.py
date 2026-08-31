"""個體化 L600：`own_l600_delta = l600_delta + margin × 0.17`。

`l600_delta` 係 **race-level** —— 同一場歷史賽事嘅每匹馬拎同一個數，描述
「面對過幾快嘅速度考驗」，唔係本駒自己跑幾快（`_pace_figure_score` docstring
自己寫明）。加返本駒喺嗰場輸咗幾多秒就個體化咗佢。

呢度釘住三件今次實測踩到嘅嘢：
  1. `margin:` 有兩種格式，個 `L` 唔可以當必需
  2. 只可以對 Sportsbet 嘅 L600 做（Racenet `Last600` 係另一個量）
  3. 冇 margin 一定要原封不動退返 race-level，唔可以變中性 60
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing"
                      / "au_wong_choi_auto" / "scripts"))

from au_racing_engine.engine_core import (  # noqa: E402
    _SEC_PER_LENGTH, _pf_aggregates, _parse_formguide_pf_metrics)


def _runs(*specs, source="sportsbet_race_context"):
    return [{"l600_delta": l6, "margin": mg, "source": source}
            for l6, mg in specs]


class MarginFormatTests(unittest.TestCase):
    """Sportsbet 寫 `margin:1.14L`，Racenet 寫 `margin:10.4`（冇 L）。

    硬要個 `L` 會靜靜漏走成個 Racenet 年代 —— 實測 2026-05..07 共 326 場
    A/B 全部 +0.0000，就係咁嚟。同一類「嚴格 regex 靜靜丟數據」嘅缺陷。
    """

    def _formguide(self, tmp: Path, line: str) -> Path:
        (tmp / "2026-08-30 Test").mkdir(parents=True, exist_ok=True)
        d = tmp / "2026-08-30 Test"
        (d / "08-30 Race 1 Formguide.md").write_text(
            "RACE 1\n[1] Alpha (3)\n" + line + "\n", encoding="utf-8")
        return d / "08-30 Race 1 Facts.md"

    def test_both_margin_formats_parse(self) -> None:
        from tempfile import TemporaryDirectory
        for line, expected in (
            ("Track R1 2026-07-01 1200m cond:Good margin:1.14L starters:9 "
             "PF[Source: sportsbet_race_context L600 Delta: 0.11]", 1.14),
            ("Track R1 2026-07-01 1200m cond:4 margin:10.4 HC:65 "
             "PF[Source: sportsbet_race_context L600 Delta: 0.38]", 10.4),
        ):
            with self.subTest(line=line[:40]), TemporaryDirectory() as tmp:
                facts = self._formguide(Path(tmp), line)
                out = _parse_formguide_pf_metrics(facts)
                runs = out["1"]["pf_runs"]
                self.assertEqual(len(runs), 1)
                self.assertAlmostEqual(runs[0]["margin"], expected)


class IndividualisationTests(unittest.TestCase):
    def test_own_delta_adds_beaten_seconds(self) -> None:
        agg = _pf_aggregates(_runs((0.5, 2.0), (0.5, 0.0)), "sportsbet_race_context")
        # (0.5 + 2×0.17) + (0.5 + 0) = 0.84 + 0.5 → 平均 0.67
        self.assertAlmostEqual(agg["own_l600_delta_avg"], 0.67, places=3)
        self.assertAlmostEqual(agg["l600_delta_avg"], 0.5, places=3)

    def test_winner_run_is_unchanged(self) -> None:
        """輸 0 馬位 → 本駒 L600 就係嗰場 L600。"""
        agg = _pf_aggregates(_runs((1.2, 0.0)), "sportsbet_race_context")
        self.assertAlmostEqual(agg["own_l600_delta_avg"], 1.2, places=4)

    def test_sec_per_length_is_the_textbook_constant(self) -> None:
        """0.17 係先驗常數，唔准喺語料上調 —— 調咗就變成用 holdout 擬合。"""
        self.assertEqual(_SEC_PER_LENGTH, 0.17)


class SourceGateTests(unittest.TestCase):
    """Racenet `Last600` 係「到 600m 標記為止嘅累計時間」，唔係最後 600m 分段。

    全程輸嘅馬位大部分喺嗰個標記之後先產生，所以加落去係語意錯。
    實測 784 場 Racenet 年代照加 = −0.0019 [−0.0050, +0.0011]，
    同一改動喺 998 場 Sportsbet 年代 = +0.0040 [−0.0005, +0.0088]。
    """

    def test_racenet_source_is_not_individualised(self) -> None:
        agg = _pf_aggregates(_runs((0.5, 2.0), source="racenet_formguide_cfb"),
                             "racenet_formguide_cfb")
        self.assertIsNone(agg.get("own_l600_delta_avg"))
        self.assertAlmostEqual(agg["l600_delta_avg"], 0.5, places=4)

    def test_sportsbet_source_is_individualised(self) -> None:
        agg = _pf_aggregates(_runs((0.5, 2.0)), "sportsbet_race_context")
        self.assertIsNotNone(agg.get("own_l600_delta_avg"))


class FallbackTests(unittest.TestCase):
    def test_runs_without_margin_leave_race_level_intact(self) -> None:
        """冇 margin 唔可以變中性 60 —— 一定要照用 race-level 個值。"""
        agg = _pf_aggregates(_runs((0.5, None), (0.9, None)), "sportsbet_race_context")
        self.assertIsNone(agg.get("own_l600_delta_avg"))
        self.assertAlmostEqual(agg["l600_delta_avg"], 0.7, places=4)

    def test_partial_margin_coverage_only_averages_what_exists(self) -> None:
        agg = _pf_aggregates(_runs((0.5, 2.0), (0.9, None)), "sportsbet_race_context")
        self.assertAlmostEqual(agg["own_l600_delta_avg"], 0.84, places=3)
        self.assertAlmostEqual(agg["l600_delta_avg"], 0.7, places=4)


if __name__ == "__main__":
    unittest.main()
