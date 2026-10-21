"""Sanity tests for nba_refit fitting code (run: python3 -m unittest)."""
import os, sys, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(__file__))
import nba_refit as nr


class Fit(unittest.TestCase):
    def test_recovers_logistic_coefficients(self):
        rng = np.random.default_rng(1)
        X = np.column_stack([np.ones(20000), rng.normal(size=20000)])
        y = (rng.random(20000) < nr.sigmoid(X @ [0.3, 1.2])).astype(float)
        b = nr.fit_l2(X, y, np.ones(20000), 0, np.array([0, 0]))
        self.assertTrue(np.allclose(b, [0.3, 1.2], atol=0.08))

    def test_l2_shrinks_and_ignores_unpenalised(self):
        rng = np.random.default_rng(2)
        X = np.column_stack([np.ones(5000), rng.normal(size=5000)])
        y = (rng.random(5000) < nr.sigmoid(X @ [0.5, 1.0])).astype(float)
        b0 = nr.fit_l2(X, y, np.ones(5000), 0, np.array([0, 1]))
        b1 = nr.fit_l2(X, y, np.ones(5000), 1e5, np.array([0, 1]))
        self.assertLess(abs(b1[1]), abs(b0[1]) * 0.2)
        self.assertGreater(b1[0], 0.3)   # intercept unpenalised

    def test_weights_equal_duplication(self):
        rng = np.random.default_rng(3)
        X = np.column_stack([np.ones(300), rng.normal(size=300)]); y = (rng.random(300) < 0.5).astype(float)
        w = rng.integers(0, 3, size=300).astype(float)
        b1 = nr.fit_l2(X, y, w, 0, np.array([0, 0]))
        Xd = np.repeat(X, w.astype(int), axis=0); yd = np.repeat(y, w.astype(int))
        b2 = nr.fit_l2(Xd, yd, np.ones(len(yd)), 0, np.array([0, 0]))
        self.assertTrue(np.allclose(b1, b2, atol=1e-6))


if __name__ == "__main__":
    unittest.main()
