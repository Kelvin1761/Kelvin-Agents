"""market_ruler.py：合成數據上嘅正／負對照、Harville、walk-forward 冇偷睇未來、配對判決。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import market_ruler as mr  # noqa: E402


def synth(days=60, per_day=15, n=10, market_w=1.0, model_w=0.0, seed=0):
    """真實力 = 市場知嘅 a + 市場唔知嘅 b。價由 a 定；ability = a·0.5 + model_w·b + 雜訊。"""
    rng = np.random.default_rng(seed)
    races = []
    for d in range(days):
        date = f"2026-{8 + d // 28:02d}-{1 + d % 28:02d}"
        for k in range(per_day):
            a = rng.normal(0, 1, n)
            b = rng.normal(0, 1, n)
            strength = market_w * a + 0.8 * b
            p_true = np.exp(strength) / np.exp(strength).sum()
            order = []
            left = list(range(n))
            pr = p_true.copy()
            for _ in range(n):                       # Plackett–Luce 抽名次
                w = pr[left] / pr[left].sum()
                i = left[rng.choice(len(left), p=w)]
                order.append(i)
                left.remove(i)
            pos = np.empty(n, int)
            pos[order] = np.arange(1, n + 1)
            pm = np.exp(market_w * a) / np.exp(market_w * a).sum()
            ab = 0.5 * a + model_w * b + rng.normal(0, 0.3, n)
            races.append({"date": date, "meeting": f"M{d}", "race": k + 1, "rows": [
                {"name": f"H{d}-{k}-{i}", "pos": int(pos[i]), "sp": float(1.15 / pm[i]), "ability": float(ab[i])}
                for i in range(n)]})
    return races


class HarvilleTest(unittest.TestCase):
    def test_sums_to_three_and_ordered(self):
        p = np.array([0.4, 0.25, 0.15, 0.1, 0.06, 0.04])
        q = mr.harville_top3(p)
        self.assertAlmostEqual(q.sum(), 3.0, places=6)
        self.assertTrue(np.all(np.diff(q) < 0))
        self.assertTrue(np.all(q >= p))

    def test_three_runners_all_place(self):
        q = mr.harville_top3(np.array([0.5, 0.3, 0.2]))
        np.testing.assert_allclose(q, 1.0, atol=1e-6)


class Top3SmallFieldTest(unittest.TestCase):
    def test_small_fields_not_scored_for_top3(self):
        big = [dict(r, meeting=r["meeting"] + "B") for r in synth(days=25, per_day=4, n=8, seed=5)]
        races = synth(days=25, per_day=4, n=3) + big
        R, _ = mr.prepare(races)
        vals, _ = mr.walk_forward(R, "top3")
        for r, v in zip(R, vals):
            if len(r["z"]) < mr.TOP3_MIN_FIELD:
                self.assertIsNone(v)
        self.assertTrue(any(v is not None for v in vals))


class PrepareTest(unittest.TestCase):
    def test_skips_missing_price_and_dead_heat(self):
        races = synth(days=1, per_day=3)
        races[0]["rows"][0]["sp"] = None
        for x in races[1]["rows"]:
            if x["pos"] == 2:
                x["pos"] = 1
        R, skipped = mr.prepare(races)
        self.assertEqual(len(R), 1)
        self.assertEqual(skipped, {"missing_price": 1, "no_single_winner": 1})


class WalkForwardTest(unittest.TestCase):
    def test_warmup_days_not_scored_and_no_future(self):
        races = synth(days=25, per_day=5)
        R, _ = mr.prepare(races)
        vals, _ = mr.walk_forward(R, "win")
        days = sorted({r["date"] for r in R})
        for r, v in zip(R, vals):
            self.assertEqual(v is None, days.index(r["date"]) < mr.WARMUP_DAYS)
        # 改未來賽日嘅結果唔可以影響之前已計分嘅賽日
        races2 = [dict(r, rows=[dict(x) for x in r["rows"]]) for r in races]
        last = days[-1]
        for r in races2:
            if r["date"] == last:
                for x in r["rows"]:
                    x["pos"] = {1: 2, 2: 1}.get(x["pos"], x["pos"])
        R2, _ = mr.prepare(races2)
        vals2, _ = mr.walk_forward(R2, "win")
        for r, a, b in zip(R, vals, vals2):
            if r["date"] != last:
                self.assertEqual(a, b)


class ControlsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.no_info = synth(model_w=0.0, seed=1)
        cls.info = synth(model_w=1.0, seed=1)

    def test_model_with_private_info_detected(self):
        res = mr.evaluate(self.info)
        self.assertTrue(res["arms"]["baseline"]["has_info_beyond_market"]["win"])
        self.assertGreater(res["arms"]["baseline"]["win"]["theta_last"][1], 0)

    def test_market_only_model_not_detected(self):
        res = mr.evaluate(self.no_info)
        self.assertFalse(res["arms"]["baseline"]["has_info_beyond_market"]["win"])

    def test_paired_pass_and_fail(self):
        self.assertEqual(mr.evaluate(self.no_info, self.info)["paired"]["verdict"], "PASS")
        self.assertEqual(mr.evaluate(self.info, self.no_info)["paired"]["verdict"], "FAIL")

    def test_paired_uses_common_races_only(self):
        cand = self.info[:-10]
        res = mr.evaluate(self.no_info, cand)
        self.assertEqual(res["common_races"], len(cand))

    def test_same_key_different_race_not_paired(self):
        cand = [dict(r, rows=[dict(x) for x in r["rows"]]) for r in self.info]
        cand[-1]["rows"][0]["sp"] += 1.0           # 同 key、唔同價 = 唔係同一場
        res = mr.evaluate(self.no_info, cand)
        self.assertEqual(res["mismatched_races"], 1)
        self.assertEqual(res["common_races"], len(cand) - 1)

    def test_too_few_days_cannot_pass(self):
        short_a = synth(days=40, model_w=0.0, seed=3)   # 20 日計分 < MIN_DAYS
        short_b = synth(days=40, model_w=1.5, seed=3)
        p = mr.evaluate(short_a, short_b)["paired"]
        self.assertTrue(p["checks"]["win_ci_lower_gt_0"])
        self.assertFalse(p["checks"]["enough_days"])
        self.assertEqual(p["verdict"], "FAIL")


class SinceTest(unittest.TestCase):
    def test_since_filters_both_arms(self):
        races = synth(days=60, per_day=2)
        res = mr.evaluate(races, races, since="2026-09-01")
        blocks = res["arms"]["baseline"]["win"]["blocks"]
        self.assertTrue(blocks)
        self.assertTrue(all(b["from"] >= "2026-09-01" for b in blocks))


if __name__ == "__main__":
    unittest.main()
