import unittest

from hkjc_dated_shape_20260902 import component_deltas, historical_rows, parse_date, transformed


HEADER = "| # | 日期 | 場地 | 距離 | 班次 | 檔位 | 名次 | 頭馬距離 | 走位(XW) |\n"


class DatedShapeTests(unittest.TestCase):
    def test_dates_and_future_exclusion(self):
        for text in ("2026-06-01", "2026/06/01", "01/06/2026", "01/06/26"):
            self.assertEqual(parse_date(text).isoformat(), "2026-06-01")
        rows, audit = historical_rows(HEADER +
            "| 1 | 01/06/2026 | 沙田 | 1200 | C4 | 1 | 2 | 1/2 | (1W1W) |\n"+
            "| 2 | 02/06/2026 | 沙田 | 1200 | C4 | 1 | 1 | 頭位 | (1W1W) |\n",
            "2026-06-02")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["margin"], .5)
        self.assertEqual(audit["invalid_or_nonpast_date"], 1)

    def test_different_dates_not_deduped_by_same_finish_xw(self):
        rows, _ = historical_rows(HEADER +
            "| 1 | 01/05/2026 | 沙田 | 1200 | C4 | 1 | 2 | 1/2 | (1W1W) |\n"+
            "| 2 | 01/04/2026 | 沙田 | 1200 | C4 | 1 | 2 | 1/2 | (1W1W) |\n",
            "2026-06-02")
        self.assertEqual(len(rows), 2)

    def test_conflicting_date_identity_rejected(self):
        with self.assertRaisesRegex(ValueError, "Conflicting historical"):
            historical_rows(HEADER +
                "| 1 | 01/05/2026 | 沙田 | 1200 | C4 | 1 | 2 | 1/2 | (1W1W) |\n"+
                "| 2 | 01/05/2026 | 沙田 | 1200 | C4 | 1 | 3 | 1/2 | (1W1W) |\n",
                "2026-06-02")

    def test_missing_inputs_neutral(self):
        d = component_deltas([], 1)
        self.assertEqual((d["fit_st"],d["fit_hv"],d["trip"]), (0,0,0))

    def test_sparse_fit_shrunk_and_bad_wide_run_not_rewarded(self):
        inner = dict(wide=1, margin=0, weight=1)
        outer = dict(wide=4, margin=6, weight=1)
        d = component_deltas([inner, outer], 1)
        self.assertEqual(d["fit_st"], 3)
        self.assertEqual(d["trip"], 0)
        self.assertEqual(component_deltas([inner, outer], 0)["fit_st"], 0)

    def test_wide_close_reward_and_easy_bad_penalty(self):
        self.assertGreater(component_deltas([dict(wide=4,margin=.5,weight=1)],9)["trip"],0)
        self.assertLess(component_deltas([dict(wide=1,margin=9,weight=1)],1)["trip"],0)

    def test_winner_margin_is_zero_not_margin_of_victory(self):
        rows,_ = historical_rows(HEADER+
            "| 1 | 01/05/2026 | 沙田 | 1200 | C4 | 1 | 1 | 5 | (3W3W) |\n", "2026-06-02")
        self.assertEqual(rows[0]["margin"],0)

    def test_component_composition_matches_matrix_rounding(self):
        race = dict(venue="沙田", runners=[dict(draw=75, fit=60, trip=62/3,
            matrix=dict(race_shape=60), dated_shape={})])
        result = transformed(race, "baseline")
        self.assertEqual(result["runners"][0]["matrix"]["race_shape"], round(.55*75+.25*60+.2*62/3,2))


if __name__ == "__main__":
    unittest.main()
