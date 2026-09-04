"""PIT adapters must patch the production package, never a duplicate module."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import pit_backtest as pit
import rescore_backtest as bt
import pandas as pd
from hkjc_racing_engine import engine_core, live_priors


class PointInTimeTests(unittest.TestCase):
    def setUp(self):
        self.old_ratings = live_priors._JT_RATINGS
        self.old_priors = engine_core._TRAINER_SIGNAL_PRIORS
        self.rows = pd.DataFrame([
            dict(Date="2026-04-10", SeasonTag="25_26", Jockey="A", Trainer="T",
                 Horse="H", Distance=1200, Win=0, Place=0),
            dict(Date="2026-04-12", SeasonTag="25_26", Jockey="A", Trainer="T",
                 Horse="H", Distance=1200, Win=1, Place=1),
            dict(Date="2026-04-13", SeasonTag="25_26", Jockey="B", Trainer="T",
                 Horse="H", Distance=1200, Win=1, Place=1),
        ])

    def tearDown(self):
        live_priors._JT_RATINGS = self.old_ratings
        engine_core._TRAINER_SIGNAL_PRIORS = self.old_priors

    def test_strict_cutoff_and_package_identity(self):
        self.assertIs(pit.engine_core, engine_core)
        self.assertIs(pit.live_priors, live_priors)
        self.assertEqual(pit.inject_as_of(self.rows, "2026-04-12"), 1)
        rating = live_priors.get_jt_ratings("2026-04-12").lookup("jockey", "A")
        self.assertEqual(rating["starts"], 1)
        self.assertEqual(rating["win_rate"], 0)
        prior = engine_core._TRAINER_SIGNAL_PRIORS
        self.assertTrue(live_priors.temporal_source_is_safe(prior, "2026-04-12"))
        self.assertFalse(live_priors.temporal_source_is_safe(prior, "2026-04-11"))
        self.assertEqual(prior.combo[("A", "T")]["wins"], 0)

    def test_future_results_do_not_change_snapshot(self):
        pit.inject_as_of(self.rows, "2026-04-12")
        before = dict(live_priors._JT_RATINGS.jockey)
        changed = self.rows.copy()
        changed.loc[changed.Date >= "2026-04-12", "Jockey"] = "FUTURE"
        pit.inject_as_of(changed, "2026-04-12")
        self.assertEqual(before, live_priors._JT_RATINGS.jockey)

    def test_pit_rating_maths_matches_production(self):
        rows = pd.concat([self.rows, pd.DataFrame([
            dict(Date="2025-04-10", SeasonTag="24_25", Jockey="B", Trainer="U",
                 Horse="X", Distance=1200, Win=1, Place=1),
            dict(Date="2025-04-11", SeasonTag="24_25", Jockey="A", Trainer="T",
                 Horse="Y", Distance=1200, Win=0, Place=1),
        ])], ignore_index=True)
        rows = rows[rows.Date < "2026-04-12"]
        frames = {}
        for group, files in live_priors.MASTER_STATS_FILES.items():
            col = "Jockey" if group == "jockey" else "Trainer"
            for source, _ in files:
                sub = rows[rows.SeasonTag == source.parent.name]
                frames[source] = sub.groupby(col).agg(
                    Wins=("Win", "sum"), Starts=("Win", "count"),
                    Places=("Place", "sum")).reset_index()
        with patch.object(live_priors, "_read_prior_csv",
                          side_effect=lambda path, required: frames[path].copy()):
            production = live_priors.JockeyTrainerRatings()
        for group in ("jockey", "trainer"):
            actual = pit.build_ratings(rows, group)
            self.assertEqual(set(actual), set(getattr(production, group)))
            for name, values in actual.items():
                for key, number in values.items():
                    self.assertAlmostEqual(number, getattr(production, group)[name][key], places=12)

    def test_missing_cutoff_rejected(self):
        with self.assertRaises(ValueError):
            pit.inject_as_of(self.rows, "")

    def test_source_missing_date_rejected(self):
        self.rows.loc[0, "Date"] = None
        with self.assertRaises(ValueError):
            pit.inject_as_of(self.rows, "2026-04-12")

    def test_unknown_venue_resolved_but_surface_preserved(self):
        md = Path("2026-05-09_ShaTin")
        for missing in (None, "", "Unknown", "N/A"):
            context = bt.resolve_meeting_context({"race_analysis": {"venue": missing}}, md)
            self.assertEqual(context["venue"], "沙田")
        context = bt.resolve_meeting_context({"race_analysis": {"venue": "沙田AWT"}}, md)
        self.assertEqual(context["venue"], "沙田AWT")
        with self.assertRaisesRegex(ValueError, "venue conflicts"):
            bt.resolve_meeting_context({"race_analysis": {"venue": "跑馬地"}}, md)

    def test_meeting_date_passed_and_conflicts_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            md = Path(directory) / "2026-04-12_ShaTin"
            md.mkdir()
            lp = md / "Race_1_Logic.json"
            logic = {"race_analysis": {}, "horses": {}}
            lp.write_text(json.dumps(logic))
            (md / "全日賽果.json").write_text(json.dumps({"1": {"results": [
                {"horse_no": "1", "pos": "1"}]}}))
            seen = []
            def capture(data, **kwargs):
                seen.append(data["race_analysis"])
                return data
            with patch.object(bt, "rescore_logic", side_effect=capture):
                _, errors = bt.rescore_meeting(md, include_legacy=True)
            self.assertFalse(errors)
            self.assertEqual(seen[0]["race_date"], "2026-04-12")
            self.assertEqual(json.loads(lp.read_text()), logic)
            logic["race_analysis"]["race_date"] = "2026-04-11"
            lp.write_text(json.dumps(logic))
            _, errors = bt.rescore_meeting(md, include_legacy=True)
            self.assertIn("conflicts", errors[0])


if __name__ == "__main__":
    unittest.main()
