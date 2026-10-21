"""Tests for the pre-game population builder (EXP-20261021-05)."""
import os, sys, unittest
import pandas as pd
sys.path.insert(0, os.path.dirname(__file__))
import nba_calib as nc
import nba_pregame as npg


def log(n=16, zero_at=None, skip=None, future=None):
    rows = []
    for i in range(n):
        if skip is not None and i == skip:
            continue
        rows.append(dict(PLAYER_ID=1, TEAM_ABBREVIATION="AAA", GAME_ID=f"{i:03d}", GAME_DATE=f"2025-11-{i+1:02d}",
                         MATCHUP="AAA vs. BBB", MIN=(0 if i == zero_at else 30), PTS=(0 if i == zero_at else 12 + i % 3),
                         REB=(0 if i == zero_at else 5), AST=(0 if i == zero_at else 3), FG3M=(0 if i == zero_at else 2), is_home=True))
    df = pd.DataFrame(rows)
    # teammate with full attendance so the team has all dates
    return df


def with_team(df, n=16):
    others = [dict(PLAYER_ID=2, TEAM_ABBREVIATION="AAA", GAME_ID=f"{i:03d}", GAME_DATE=f"2025-11-{i+1:02d}", MATCHUP="AAA vs. BBB",
                   MIN=30, PTS=10, REB=4, AST=2, FG3M=1, is_home=True) for i in range(n)]
    return pd.concat([df, pd.DataFrame(others)], ignore_index=True).sort_values(["PLAYER_ID", "GAME_DATE", "GAME_ID"]).reset_index(drop=True)


class Pregame(unittest.TestCase):
    def test_min0_row_is_unit_with_y0_and_not_in_prior(self):
        gen = nc.load_live()
        rows = npg.build_rows(with_team(log(16, zero_at=12)), "T", gen)
        r12 = [r for r in rows if r["player_id"] == 1 and r["date"] == "2025-11-13"]
        self.assertTrue(r12 and all(r["y"] == 0 and r["min_g"] == 0 for r in r12))
        r13 = [r for r in rows if r["player_id"] == 1 and r["date"] == "2025-11-14"]
        self.assertTrue(all(r["k"] == 12 for r in r13))      # 13 prior rows minus the MIN==0 row

    def test_virtual_absence_uses_only_earlier_games_and_is_y0(self):
        gen = nc.load_live()
        rows = npg.build_rows(with_team(log(16, skip=13)), "T", gen)
        v = [r for r in rows if r["virtual"] == 1 and r["player_id"] == 1]
        self.assertTrue(v and all(r["date"] == "2025-11-14" and r["y"] == 0 and r["k"] == 13 for r in v))

    def test_features_ignore_outcome(self):
        gen = nc.load_live()
        d1 = with_team(log(16)); d2 = d1.copy(); d2.loc[(d2.PLAYER_ID == 1) & (d2.GAME_ID == "015"), "PTS"] = 70
        a = npg.build_rows(d1, "T", gen); b = npg.build_rows(d2, "T", gen)
        self.assertEqual(len(a), len(b))
        for x, y in zip(a, b):
            for k in ("a", "mu", "e", "f", "hit_sea", "line"):
                self.assertEqual(x[k], y[k])


if __name__ == "__main__":
    unittest.main()
