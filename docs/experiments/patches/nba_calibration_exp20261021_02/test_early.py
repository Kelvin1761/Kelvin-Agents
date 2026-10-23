"""Tests for the early-season builder (EXP-20261021-06)."""
import os, sys, unittest
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_early as ne


def season_log(season_dates, pid=1, mins=30, pts=lambda i: 12 + i % 4, team="AAA", n_extra_player=True):
    rows = []
    for i, d in enumerate(season_dates):
        rows.append(dict(PLAYER_ID=pid, TEAM_ABBREVIATION=team, GAME_ID=f"{d}", GAME_DATE=d, MATCHUP=f"{team} vs. BBB", MIN=mins,
                         PTS=pts(i), REB=5, AST=3, FG3M=2, is_home=True))
    return rows


def dates(start, n):
    import datetime as dt
    s = dt.date.fromisoformat(start)
    return [(s + dt.timedelta(days=i)).isoformat() for i in range(n)]


def build(prior_n=45, prior_min=30, cur_n=14, future_pts=None):
    P = pd.DataFrame(season_log(dates("2023-11-01", prior_n), mins=prior_min))
    cur_rows = season_log(dates("2024-11-01", cur_n))
    if future_pts is not None:
        cur_rows[-1]["PTS"] = future_pts
    S = pd.DataFrame(cur_rows)
    for df in (P, S):
        df["GAME_DATE"] = df["GAME_DATE"].astype(str)
    return ne.build_rows(S.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True),
                         P.sort_values(["PLAYER_ID", "GAME_DATE"]).reset_index(drop=True), "S", nc.load_live())


class Early(unittest.TestCase):
    def test_only_first_ten_games_and_prior_season_in_l10(self):
        rows = build()
        self.assertEqual(sorted({r["n_cur"] for r in rows}), list(range(10)))
        r0 = [r for r in rows if r["n_cur"] == 0 and r["stat"] == "PTS"]
        self.assertTrue(r0 and all(r["M_cur"] == 0 and r["S_cur"] == 0 for r in r0))     # game 1: nothing from the same season
        self.assertTrue(all(np.isclose(r["prior_total"], sum(12 + i % 4 for i in range(45))) for r in r0))

    def test_eligibility_rules(self):
        self.assertEqual(build(prior_n=39), [])          # <40 prior-season games
        self.assertEqual(build(prior_min=19), [])        # prior-season mean MIN <20

    def test_features_ignore_current_and_future_outcomes(self):
        a = build(); b = build(future_pts=70)
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            for k in ("a", "e", "n_cur", "S_cur", "M_cur", "min10", "line"):
                self.assertEqual(x[k], y[k])

    def test_blend_limits(self):
        rows = pd.DataFrame(build()); kmap = {s: 0 for s in nc.STATS}
        mu0 = ne.mu_prior(rows); mu_k = ne.mu_blend(rows, {s: 10 ** 9 for s in nc.STATS})
        self.assertTrue(np.allclose(mu0, mu_k, rtol=1e-6))        # k -> inf == prior-only
        g1 = rows[rows.n_cur == 0]
        self.assertTrue(np.allclose(ne.mu_blend(g1, kmap), ne.mu_prior(g1)))   # no current games -> prior rate


if __name__ == "__main__":
    unittest.main()
