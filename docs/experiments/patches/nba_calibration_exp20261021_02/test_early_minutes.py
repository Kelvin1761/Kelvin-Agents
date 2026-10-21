"""Tests for the minutes-calibration code (EXP-20261021-07)."""
import os, sys, unittest
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import nba_early_minutes as em
import nba_early as ne


def toy():
    rng = np.random.default_rng(0); rows = []
    gid = 0
    for n_cur in (0, 2, 7):
        for pm in (22.0, 27.0, 33.0):
            for _ in range(40):
                gid += 1
                for stat in ("PTS", "REB", "AST", "FG3M"):
                    rows.append(dict(season="2025-26", date="2025-11-01", game_id=str(gid), player_id=gid, stat=stat, line=5, y=0, a=0.5, e=0.5,
                                     n_cur=n_cur, S_cur=5.0 * n_cur, M_cur=30.0 * n_cur, prior_total=400.0, prior_min_total=2000.0,
                                     min10=30.0, prior_min_mean=pm, min_g=float(rng.integers(20, 36))))
    return pd.DataFrame(rows)


class Minutes(unittest.TestCase):
    def test_f_is_ratio_of_sums_per_stratum(self):
        d = toy(); m1, m2 = em.fit_f(d)
        u = d.drop_duplicates(["player_id", "game_id"]); u = u[u.n_cur == 2]
        self.assertAlmostEqual(m1["S1"], u.min_g.sum() / u.min10.sum(), places=12)

    def test_m2_shrinks_to_m1_when_cell_sparse_and_to_raw_when_large(self):
        d = toy(); m1, m2 = em.fit_f(d)
        for (b, s), v in m2.items():
            self.assertLessEqual(abs(v - m1[s]), 0.2)                # 40 units/cell, shrink 100 -> close to M1
        em.SHRINK_UNITS, old = 0, em.SHRINK_UNITS
        try:
            _, m2raw = em.fit_f(d)
            u = d.drop_duplicates(["player_id", "game_id"]); g = u[(u.n_cur == 0) & (u.prior_min_mean == 22.0)]
            self.assertAlmostEqual(m2raw[("B1", "S0")], g.min_g.sum() / g.min10.sum(), places=12)
        finally:
            em.SHRINK_UNITS = old

    def test_mu_with_unit_factor_equals_exp06_blend(self):
        d = toy()
        self.assertTrue(np.allclose(em.mu_blend_f(d, np.ones(len(d))), ne.mu_blend(d, em.KMAP)))

    def test_f_depends_only_on_the_dev_frame_passed_in(self):
        d = toy(); other = d.copy(); other["min_g"] = 1.0              # H2/H3-like frame with different minutes
        m1a, _ = em.fit_f(d); m1b, _ = em.fit_f(d)                     # deterministic
        self.assertEqual(m1a, m1b)
        m1c, _ = em.fit_f(other)
        self.assertNotEqual(m1a["S0"], m1c["S0"])                      # f follows whatever frame is passed -> caller must pass dev only

    def test_veto_and_level_rules(self):
        t = {"S": {"S0": {"n": 10, "mean_resid": -0.05, "ci": [-0.08, -0.02]}}, "B": {}}
        self.assertTrue(em.veto(t)); self.assertFalse(em.level_ok(t, ["S0"]))
        t2 = {"S": {"S0": {"n": 10, "mean_resid": -0.02, "ci": [-0.04, 0.01]}}, "B": {}}
        self.assertFalse(em.veto(t2)); self.assertTrue(em.level_ok(t2, ["S0"]))


if __name__ == "__main__":
    unittest.main()
