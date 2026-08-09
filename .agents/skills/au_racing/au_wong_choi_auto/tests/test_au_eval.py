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
sys.path.insert(0, str(SCRIPTS / "racing_engine"))
sys.path.insert(0, str(SCRIPTS.parents[2] / "shared_racing"))

import au_eval  # noqa: E402


def _races(n=200, sep=0.0, seed=1):
    """砌 n 場，每場 8 匹。`sep` = 上名馬額外加幾多分（0 = 冇訊號）。"""
    import random
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        rows = []
        for i in range(8):
            placed = i < 3
            rows.append({"features": {}, "wet": 0.0, "pos": i + 1,
                         "_s": rng.gauss(0, 1) + (sep if placed else 0.0)})
        rng.shuffle(rows)
        out.append({"rows": rows})
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
        v = au_eval.compare(races, score, lambda r: r["_c"], label="真訊號")
        self.assertTrue(v.ship, f"應該 ship：{v.reason}")
        self.assertGreater(v.top_hold_ci[0], 0)

    def test_a_worse_candidate_is_rejected_with_the_right_reason(self):
        races = _races(sep=1.2)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"] - (1.2 if x["pos"] <= 3 else 0.0)
        v = au_eval.compare(races, score, lambda r: r["_c"], label="更差")
        self.assertFalse(v.ship)
        self.assertIn("全負", v.reason)

    def test_a_neutral_change_is_not_shipped(self):
        """⚠️ 呢個係最重要嘅一條。純噪音擾動一定唔可以過 ——
        場數指標嗰套閘校準過係 0/40 中性改動全過，而呢把尺要做得更準。"""
        import random
        rng = random.Random(9)
        races = _races(sep=1.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"] + rng.gauss(0, 0.05)
        v = au_eval.compare(races, score, lambda r: r["_c"], label="中性擾動")
        self.assertFalse(v.ship, "中性改動唔可以過閘")

    def test_counts_are_reported_but_never_gate(self):
        """場數指標只做參考。一個場數靚但 AUC 跨 0 嘅候選唔可以過。"""
        races = _races(sep=1.0)
        for r in races:
            for x in r["rows"]:
                x["_c"] = x["_s"]
        v = au_eval.compare(races, score, lambda r: r["_c"], label="完全一樣")
        self.assertFalse(v.ship)
        self.assertIn("跨 0", v.reason)
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
        v = au_eval.compare(races, score, lambda r: r["_c"])
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
