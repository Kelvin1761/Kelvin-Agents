"""校準模型機率（EXP-20261125-07）：防前視、同 AU 判決尺 bit-identical、機率加總。"""
from __future__ import annotations

import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "shared_racing" / "scripts"))

import model_probability as MP  # noqa: E402
import au_logloss_ruler as L  # noqa: E402


def fixture(days=35, races_per_day=4, seed=3, start="2026-08-10"):
    rng = np.random.default_rng(seed)
    d0 = date.fromisoformat(start)
    out = []
    for i in range(days):
        d = (d0 + timedelta(days=i)).isoformat()
        for r in range(races_per_day):
            n = int(rng.integers(5, 15))
            ab = rng.normal(60, 6, n)
            order = np.argsort(-(ab * 0.15 + rng.gumbel(size=n)))
            pos = np.empty(n, int)
            pos[order] = np.arange(1, n + 1)
            out.append({"date": d, "meeting": f"{d} Track", "race": r + 1,
                        "rows": [{"ability": float(a), "pos": int(p)} for a, p in zip(ab, pos)]})
    return out


class ModelProbabilityTests(unittest.TestCase):
    def test_future_days_never_change_past_params(self):
        races = fixture()
        for platform in ("au", "hkjc"):
            past = MP.params_before([r for r in races if r["date"] < "2026-09-05"], "2026-09-05", platform)
            full = MP.params_before(races, "2026-09-05", platform)
            self.assertEqual(past, full)
            wf_short = MP.walk_forward(races[:110], platform)
            wf_full = MP.walk_forward(races, platform)
            for d, p in wf_short.items():
                if d < max(wf_short):
                    self.assertEqual(p, wf_full[d])

    def test_target_day_itself_not_used(self):
        races = fixture()
        target = "2026-09-04"
        a = MP.params_before(races, target, "au")
        b = MP.params_before([r for r in races if r["date"] < target], target, "au")
        self.assertEqual(a, b)

    def test_warmup_insufficient(self):
        races = fixture(days=10)
        p = MP.params_before(races, "2099-01-01", "au")
        self.assertEqual(p["status"], "insufficient")
        self.assertIsNone(p["a"])

    def test_au_top3_bit_identical_to_ruler(self):
        races = L.eligible(fixture())
        cal = L.calibrations(races, "v2")
        days = sorted({r["date"] for r in races})
        refit_day = days[L.WARMUP_DAYS + L.REFIT_EVERY]       # 一個 ruler 會重 fit 嘅日子
        ours = MP.params_before(races, refit_day, "au")
        self.assertEqual((ours["a"], ours["alpha"], ours["gamma"]), cal[refit_day])
        for r in races[:20]:
            x1, y1 = MP.top3_xy(r, "au")
            x2, y2 = L._xy(r, version="v2")
            np.testing.assert_array_equal(x1, x2)
            np.testing.assert_array_equal(y1, y2)

    def test_field_logit_rules(self):
        self.assertEqual(MP.field_logit(8, "au"), MP.field_logit(8, "hkjc"))
        self.assertAlmostEqual(MP.field_logit(3, "hkjc"), np.log(3.0))
        self.assertGreater(MP.field_logit(3, "au"), 20)       # AU 尺：max(N−3, 1e-9)

    def test_probability_sums(self):
        races = fixture()
        for platform in ("au", "hkjc"):
            p = MP.params_before(races, "2099-01-01", platform)
            self.assertEqual(p["status"], "ok")
            self.assertGreater(p["beta_win"], 0)
            sums3 = []
            for r in MP.eligible(races, platform):
                ab = [x["ability"] for x in r["rows"]]
                self.assertAlmostEqual(float(MP.win_probs(ab, p["beta_win"]).sum()), 1.0, places=12)
                s3 = float(MP.top3_probs(ab, p, platform).sum())
                self.assertLess(abs(s3 - 3), 0.8)
                sums3.append(s3)
            # 有截距嘅 logistic MLE：訓練集 Σp = Σy，所以平均每場 ≈ 3
            self.assertAlmostEqual(float(np.mean(sums3)), 3.0, places=4)

    def test_current_model_filter(self):
        races = [{"date": "2026-11-10", "model_ids": {"A"}, "published_at": "2026-11-10T10:00:00+11:00"},
                 {"date": "2026-11-10", "model_ids": {"A", "B"}, "published_at": "2026-11-01T10:00:00+11:00"}]
        self.assertEqual(len(MP.current_model_races(races, "hkjc", "A", None)), 1)
        self.assertEqual(len(MP.current_model_races(races, "au", "x", "2026-11-05T00:00:00+11:00")), 1)
        self.assertEqual(MP.current_model_races(races, "au", "x", None), [])

    def test_model_ids(self):
        self.assertTrue(MP.model_id("au").startswith("au_golden:"))
        self.assertTrue(MP.model_id("hkjc").startswith("HKJC_"))

    def test_build_flags_model_change(self):
        races = fixture()
        out = MP.build("hkjc", races, "2099-01-01", mid="NEW", epoch=None, previous={"model_id": "OLD"})
        self.assertEqual(out["status"], "insufficient")          # fixture 冇 model_ids = 唔係現行模型
        self.assertEqual(out["model_changed_from"], "OLD")
        self.assertEqual(out["reference_all_models"]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
