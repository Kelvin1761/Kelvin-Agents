#!/usr/bin/env python3
"""統一評估器嘅判決規則要釘死。

呢個檔存在嘅原因：到 2026-08-04 為止，同一個問題（「呢個改動好唔好？」）散落
喺七八個 harness、各有一套指標同閘門，而**冇一份文件講過邊把先算數**。
結果係同一個候選喺唔同 harness 之下可以得出相反結論。`au_eval.py` 定死一次，
呢度確保個規則唔會靜靜咁飄走。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))

import au_eval  # noqa: E402


def _races(n=200, sep=0.0, seed=1, field=8, dates=None):
    """砌 n 場，每場 `field` 匹。`sep` = 上名馬額外加幾多分（0 = 冇訊號）。

    `dates` 可以逐場指定賽日；用嚟砌「日期密度唔平均」嘅語料，
    因為 holdout 係按**日期**切、但報告要講**場次**佔比。
    """
    import random
    rng = random.Random(seed)
    out = []
    for index in range(n):
        rows = []
        for i in range(field):
            placed = i < 3
            rows.append({"features": {}, "wet": 0.0, "pos": i + 1,
                         "_s": rng.gauss(0, 1) + (sep if placed else 0.0)})
        rng.shuffle(rows)
        race = {"rows": rows, "field": field}
        if dates is not None:
            race["date"] = dates[index]
        out.append(race)
    return out


def score(row):
    return row["_s"]


class VerdictRuleTests(unittest.TestCase):
    def test_date_partition_never_splits_one_meeting_day(self):
        races = [
            {"date": date, "rows": []}
            for date in ("2026-01-01", "2026-01-01", "2026-01-02",
                         "2026-01-03", "2026-01-03")
        ]
        dev, holdout = au_eval.date_partitions(races, holdout=0.34)
        self.assertEqual(dev, [0, 1])
        self.assertEqual(holdout, [2, 3, 4])

    def test_a_real_improvement_ships(self):
        """候選比基準多一個真訊號 → 應該過。"""
        races = _races(sep=0.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"] + (1.2 if x["pos"] <= 3 else 0.0)
        v = au_eval.compare(
            races, score, lambda r: r["_c"], label="真訊號",
            leakage_audit_passed=True,
        )
        self.assertTrue(v.ship, f"應該 ship：{v.reason}")
        self.assertGreater(v.top_hold_ci[0], 0)

    def test_a_worse_candidate_is_rejected_with_the_right_reason(self):
        races = _races(sep=1.2)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"] - (1.2 if x["pos"] <= 3 else 0.0)
        v = au_eval.compare(
            races, score, lambda r: r["_c"], label="更差",
            leakage_audit_passed=True,
        )
        self.assertFalse(v.ship)
        self.assertEqual(v.stage4_verdict, "REJECT")

    def test_a_neutral_change_is_not_shipped(self):
        """⚠️ 呢個係最重要嘅一條。純噪音擾動一定唔可以過 ——
        場數指標嗰套閘校準過係 0/40 中性改動全過，而呢把尺要做得更準。"""
        import random
        rng = random.Random(9)
        races = _races(sep=1.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"] + rng.gauss(0, 0.05)
        v = au_eval.compare(
            races, score, lambda r: r["_c"], label="中性擾動",
            leakage_audit_passed=True,
        )
        self.assertFalse(v.ship, "中性改動唔可以過閘")

    def test_counts_are_reported_but_never_gate(self):
        """場數指標只做參考。一個場數靚但 AUC 跨 0 嘅候選唔可以過。"""
        races = _races(sep=1.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"]
        v = au_eval.compare(
            races, score, lambda r: r["_c"], label="完全一樣",
            leakage_audit_passed=True,
        )
        self.assertFalse(v.ship)
        self.assertEqual(v.reason, "ranking_evidence_too_weak")
        self.assertIsInstance(v.counts, dict)

    def test_counts_include_every_current_and_legacy_metric(self):
        counts = au_eval._counts(_races(10, sep=1.0), score)
        self.assertEqual(
            set(au_eval.CONTEXT_KEYS) | {"t3prec"},
            set(counts),
        )
        self.assertIn("gold", counts)
        self.assertIn("gold_strict", counts)
        self.assertIn("good_positional", counts)
        self.assertIn("pass", counts)
        self.assertNotIn("good_any2", counts)
        self.assertNotIn("pass_any1", counts)

    def test_top_k_region_is_what_decides(self):
        """判決欄位一定要係頭 K 位嗰個，唔係全場 —— 深位排序對 Gold/Good 冇影響。"""
        races = _races(sep=1.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"]
        v = au_eval.compare(
            races, score, lambda r: r["_c"], leakage_audit_passed=True
        )
        self.assertEqual(au_eval.TOP_K, 5)
        self.assertIn(f"頭 {au_eval.TOP_K} 位", str(v))

    def test_configured_scorer_normalises_candidate_weights(self):
        row = {
            "features": {"form_score": 80.0},
            "wet": 2.0,
        }
        once = au_eval.configured_scorer(
            weights={key: value for key, value in au_eval.MATRIX_WEIGHTS.items()},
            wet_scale=0.5,
        )(row)
        twice = au_eval.configured_scorer(
            weights={key: value * 2 for key, value in au_eval.MATRIX_WEIGHTS.items()},
            wet_scale=0.5,
        )(row)
        self.assertAlmostEqual(once, twice)

    def test_baseline_report_uses_whole_date_partition(self):
        races = _races(20, sep=1.0)
        for index, race in enumerate(races):
            race["date"] = f"2026-01-{index // 2 + 1:02d}"
            race["metadata"] = {"field_size": 8}
        report = au_eval.baseline_report(races, holdout=0.2, scorer=score)
        self.assertEqual(report["design"]["development_races"], 16)
        self.assertEqual(report["design"]["terminal_holdout_races"], 4)
        self.assertIn("top_k_terminal", report["auc"])


if __name__ == "__main__":
    unittest.main()


class FieldSizeReportingTests(unittest.TestCase):
    """場數指標**冇**按馬群大細正規化，所以報告一定要出分層。

    2026-08-21 實測（dev 901 場，時間因素已隔離）：Gold 由 ≤8 匹嘅 31.58% 一路
    跌到 13+ 匹嘅 8.91% —— 3.5 倍。後果係任何令馬群組成改變嘅嘢（換語料、換窗、
    加新場次）都會偽裝成模型變化：當日 pooled 數字係 dev 16.13% vs holdout
    20.70%，睇落「holdout 好過 dev」，但真相係 ≤8 匹嘅場次由 dev 佔 23% 變成
    holdout 佔 44%。

    呢個 class 鎖住「分層一定會出」，唔係鎖住具體分值。
    """

    def test_metrics_are_broken_down_by_field_size(self):
        report = au_eval.baseline_report(_races(120, sep=0.6), scorer=score)
        by_field = report["metrics_by_field"]
        self.assertIn("all", by_field)
        self.assertIn("9-10", au_eval.baseline_report(
            _races(60, sep=0.6, field=10), scorer=score)["metrics_by_field"]["all"])

    def test_every_race_lands_in_exactly_one_bucket(self):
        for field in (6, 8, 9, 10, 11, 12, 13, 20):
            buckets = [
                label for lo, hi, label in au_eval.FIELD_BUCKETS if lo <= field <= hi
            ]
            self.assertEqual(len(buckets), 1, f"馬群 {field} 落入 {buckets}")

    def test_bucket_race_counts_sum_to_the_whole_sample(self):
        races = _races(40, sep=0.6, field=8) + _races(30, sep=0.6, field=14, seed=2)
        buckets = au_eval.baseline_report(races, scorer=score)["metrics_by_field"]["all"]
        # `_counts` 會剔走前三不足 3 匹／冇頭馬嘅場次，所以只可以要求唔超過總數。
        self.assertLessEqual(sum(b["races"] for b in buckets.values()), len(races))
        self.assertEqual(sorted(buckets), sorted({"≤8", "13+"}))

    def test_field_size_means_are_reported_for_both_windows(self):
        races = _races(
            60, sep=0.6, field=8,
            dates=[f"2026-01-{day:02d}" for day in range(1, 7) for _ in range(10)],
        )
        field_size = au_eval.baseline_report(races, scorer=score)["field_size"]
        self.assertAlmostEqual(field_size["development_mean"], 8.0)
        self.assertAlmostEqual(field_size["terminal_mean"], 8.0)

    def test_holdout_share_of_races_is_not_the_date_fraction(self):
        """呢個就係 2026-08-21 實測到嘅缺陷：15% 日期 = 36.2% 場次。

        `date_partitions` 切嘅係**日期**。當唔同日期嘅場次密度差好遠（新語料
        每日場次密好多），「holdout 15%」呢句話就係錯嘅 —— 所有 docstring
        講「85/15」嘅地方都要對照 `holdout_share_of_races`。
        """
        # 9 個疏日（每日 1 場）+ 1 個密日（40 場）。尾 1 個日期入 holdout。
        dates = [f"2026-01-{day:02d}" for day in range(1, 10)] + ["2026-01-10"] * 40
        races = _races(len(dates), sep=0.6, dates=dates)
        design = au_eval.baseline_report(races, holdout=0.1, scorer=score)["design"]
        self.assertEqual(design["terminal_holdout_races"], 40)
        self.assertAlmostEqual(design["holdout_fraction_by_whole_date"], 0.1)
        # 10% 嘅日期 → 82% 嘅場次。呢個差距就係要報出嚟嘅嘢。
        self.assertGreater(design["holdout_share_of_races"], 0.8)


class CandidateDimensionWiringTests(unittest.TestCase):
    """候選權重表提到嘅維度**唔可以**被靜靜丟掉。

    2026-08-22 之前 `configured_scorer` 嘅 normalised dict 係 iterate live
    `MATRIX_WEIGHTS`，所以任何唔喺 live 權重表嘅維度會靜靜消失：候選返
    +0.0000，報告寫「呢把尺分唔開」，而真相係「你個維度我無視咗」。

    實測後果（mapper 出 7 個維度、live 權重表得 5 個）：
      * `form_line` 權重一直 0，所以**由來都冇得測** ——
        `au_weight_improvement_search.py` 個 docstring 明寫佢要測
        「the currently zero-weighted form_line dimension」，結構上做唔到
      * `race_shape` 2026-08-22 退出排名之後就再也 A/B 唔返轉頭

    呢個係 repo 嘅招牌 bug 形態：**靜靜返一個錯答案，唔係報錯。**
    """

    def test_a_dimension_outside_live_weights_actually_moves_the_score(self):
        from au_racing_engine.scoring import MATRIX_WEIGHTS
        extra = sorted(set(au_eval.matrix_mapper.MATRIX_FORMULAS) - set(MATRIX_WEIGHTS))
        if not extra:
            self.skipTest("live 權重表已覆蓋所有維度，冇得測")
        row = {"features": {"pace_map_score": 40.0, "formline_score": 40.0,
                            "form_score": 70.0}, "wet": 0.0}
        base = au_eval.configured_scorer()(row)
        # 俾其中一個「唔喺 live 權重表」嘅維度一個大權重
        candidate = dict(MATRIX_WEIGHTS, **{extra[0]: 5.0})
        moved = au_eval.configured_scorer(weights=candidate)(row)
        self.assertNotAlmostEqual(
            base, moved, places=4,
            msg=f"候選維度 {extra[0]!r} 冇影響到分數 —— 又係靜靜丟掉",
        )

    def test_an_unmappable_dimension_is_loud_not_silent(self):
        with self.assertRaises(ValueError) as caught:
            au_eval.configured_scorer(weights={"stability": 1.0, "not_a_dimension": 1.0})
        self.assertIn("not_a_dimension", str(caught.exception))

    def test_candidate_inside_live_weights_is_unchanged_behaviour(self):
        """舊用法（候選 key ⊆ live 權重表）行為必須完全一樣。"""
        from au_racing_engine.scoring import MATRIX_WEIGHTS
        row = {"features": {"form_score": 70.0, "pace_map_score": 50.0}, "wet": 0.0}
        doubled = {key: value * 2 for key, value in MATRIX_WEIGHTS.items()}
        self.assertAlmostEqual(
            au_eval.configured_scorer()(row),
            au_eval.configured_scorer(weights=doubled)(row),
            places=9,
        )
