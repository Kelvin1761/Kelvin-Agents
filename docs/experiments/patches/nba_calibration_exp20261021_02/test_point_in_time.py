"""Unit tests for the point-in-time rule of EXP-20261021-02 (run: python3 -m unittest)."""
import os, sys, unittest
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc


def toy_log(n_games=14, future_stat=None):
    rows = []
    for i in range(n_games):
        rows.append(dict(PLAYER_ID=1, PLAYER_NAME="X", TEAM_ABBREVIATION="AAA", GAME_ID=f"{i:03d}",
                         GAME_DATE=f"2025-11-{i+1:02d}", MATCHUP="AAA vs. BBB", MIN=30, PTS=10 + i % 3,
                         REB=5, AST=3, FG3M=2, is_home=True))
    df = pd.DataFrame(rows)
    if future_stat is not None:
        df.loc[df.index[-1], "PTS"] = future_stat
    return df


class PointInTime(unittest.TestCase):
    def test_prior_count_is_strict(self):
        d = ["2025-11-01", "2025-11-02", "2025-11-03"]
        self.assertEqual(nc.prior_count(d, "2025-11-03"), 2)   # same day excluded
        self.assertEqual(nc.prior_count(d, "2025-11-04"), 3)
        self.assertEqual(nc.prior_count(d, "2025-11-01"), 0)

    def test_first_unit_needs_ten_prior_games(self):
        gen = nc.load_live()
        rows = nc.build_rows(toy_log(14), "T", gen)
        self.assertEqual(min(r["k"] for r in rows), 10)
        self.assertTrue(all(r["date"] >= "2025-11-11" for r in rows))

    def test_features_ignore_current_and_future_games(self):
        """Changing the stat of the LAST game must not change that game's own features,
        and must not change any earlier game's features."""
        gen = nc.load_live()
        a = nc.build_rows(toy_log(14, future_stat=None), "T", gen)
        b = nc.build_rows(toy_log(14, future_stat=60), "T", gen)
        feat = ["a", "hit_sea", "mu", "e", "f", "m", "line"]
        self.assertEqual(len(a), len(b))
        for ra, rb in zip(a, b):
            for k in feat:
                self.assertEqual(ra[k], rb[k], f"feature {k} moved when only the outcome changed")
        # ...while the outcome itself does change (sanity: test has power)
        self.assertNotEqual([r["y"] for r in a], [r["y"] for r in b])

    def test_same_day_game_not_used(self):
        gen = nc.load_live()
        df = toy_log(12)
        extra = df.iloc[[-1]].copy()
        extra["GAME_ID"] = "999"; extra["PTS"] = 80    # same date as last game (double-count attempt)
        rows = nc.build_rows(pd.concat([df, extra], ignore_index=True).sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"]), "T", gen)
        last_day = df.GAME_DATE.iloc[-1]
        for r in rows:
            if r["date"] == last_day:
                self.assertEqual(r["k"], 11)   # exactly the 11 strictly-earlier games

    def test_line_choice_depends_on_mean_only(self):
        self.assertEqual(nc.choose_lines(7.3), [6, 7, 8])
        self.assertEqual(nc.choose_lines(1.0), [1, 2, 3])
        self.assertEqual(nc.choose_lines(25.5), [24, 25, 26])   # tie 25/26 -> smaller; then 24 vs 27 -> 24
        self.assertTrue(all(n >= 1 for n in nc.choose_lines(1.1)))


if __name__ == "__main__":
    unittest.main()
