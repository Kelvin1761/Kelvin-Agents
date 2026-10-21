"""Tests for the E-recalibration maps (EXP-20261021-08)."""
import itertools, os, sys, unittest
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import nba_recal_e as rc


def brute_iso(x, y):
    """Reference isotonic fit by exhaustive search over merge partitions of the unique-x sequence (small n)."""
    ux = np.unique(x); w = np.array([np.sum(x == u) for u in ux], float); m = np.array([y[x == u].mean() for u in ux])
    best = None
    for cuts in itertools.product([0, 1], repeat=len(ux) - 1):
        blocks, start = [], 0
        for i, c in enumerate(cuts, 1):
            if c:
                blocks.append((start, i)); start = i
        blocks.append((start, len(ux)))
        vals = [np.average(m[s:e], weights=w[s:e]) for s, e in blocks]
        if any(vals[i] > vals[i + 1] + 1e-12 for i in range(len(vals) - 1)):
            continue
        fit = np.concatenate([[v] * (e - s) for v, (s, e) in zip(vals, blocks)])
        sse = float((w * (m - fit) ** 2).sum())
        if best is None or sse < best[0] - 1e-12:
            best = (sse, fit)
    return ux, best[1]


class Maps(unittest.TestCase):
    def test_pav_is_monotone_and_matches_bruteforce(self):
        rng = np.random.default_rng(3)
        for _ in range(20):
            x = rng.choice([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], size=40); y = (rng.random(40) < 0.5).astype(float)
            ux, f = rc.fit_iso(x, y); self.assertTrue(np.all(np.diff(f) >= -1e-12))
            _, fb = brute_iso(x, y); self.assertTrue(np.allclose(f, fb, atol=1e-9))

    def test_ties_are_merged_and_prediction_interpolates_and_clips(self):
        x = np.array([0.2, 0.2, 0.5, 0.5, 0.8, 0.8]); y = np.array([0, 1, 1, 1, 0, 1.0])
        m = rc.fit_iso(x, y); self.assertEqual(len(m[0]), 3)
        p = rc.pred_iso(m, np.array([0.0, 0.35, 0.99]))
        self.assertTrue(p[0] == m[1][0] or p[0] == 0.01 or abs(p[0] - max(0.01, m[1][0])) < 1e-12)
        self.assertTrue(0.01 <= p.min() and p.max() <= 0.99)
        self.assertGreaterEqual(p[1], min(m[1][:2]) - 1e-12)

    def test_platt_recovers_known_map(self):
        rng = np.random.default_rng(1); e = rng.uniform(0.1, 0.9, 40000)
        y = (rng.random(40000) < rc.nr.sigmoid(0.3 + 0.5 * rc.nc.logit(e))).astype(float)
        a, b = rc.fit_platt(e, y); self.assertAlmostEqual(b, 0.5, delta=0.05); self.assertAlmostEqual(a, 0.3, delta=0.05)

    def test_fit_uses_only_the_frame_passed(self):
        d = pd.DataFrame({"e": np.tile([0.2, 0.5, 0.8], 200), "y": np.tile([0, 1, 1, 0, 1, 0], 100), "stat": np.tile(["PTS", "REB", "AST", "FG3M"], 150)})
        M1 = rc.fit_all_maps(d); d2 = d.copy(); d2["y"] = 1 - d2["y"]
        M2 = rc.fit_all_maps(d2)
        self.assertFalse(np.allclose(M1["K1p"][1], M2["K1p"][1]))     # maps follow the frame -> caller must pass dev only

    def test_auc_basic_and_zone_cross(self):
        y = np.array([0, 0, 1, 1]); self.assertEqual(rc.auc(np.array([0.1, 0.2, 0.3, 0.4]), y), 1.0)
        self.assertAlmostEqual(rc.auc(np.array([0.5, 0.5, 0.5, 0.5]), y), 0.5)
        c = rc.zone_cross(np.array([0.75, 0.72, 0.6]), np.array([0.71, 0.65, 0.72]), np.array([1, 0, 1]))
        self.assertEqual(c["0.7"]["n_E"], 2); self.assertAlmostEqual(c["0.7"]["retained_of_E"], 0.5); self.assertEqual(c["0.7"]["new_from_below"], 1)


if __name__ == "__main__":
    unittest.main()
