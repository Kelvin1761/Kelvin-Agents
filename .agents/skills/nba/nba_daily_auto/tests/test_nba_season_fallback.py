"""New-season fallback: empty 2026-27 league feeds must fall back to 2025-26,
say so in the payload, and the report must not claim adjustments it lacks."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_data_extractor' / 'scripts'))
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import nba_extractor as extractor
import monte_carlo_nba as mc

AS_OF = '2026-10-20T19:00Z'


def teams(n):
    return {f"T{i}": {"PACE": 99.0, "DEF_RANK": i + 1} for i in range(n)}


class FallbackTests(unittest.TestCase):
    def test_empty_current_season_uses_previous_and_keeps_cutoff(self):
        calls = []

        def fetch(season, as_of):
            calls.append((season, as_of))
            return {} if season == '2026-27' else teams(30)

        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25, 'team_stats')
        self.assertEqual(len(data), 30)
        self.assertEqual(info['data_season'], '2025-26')
        self.assertEqual(info['requested_season'], '2026-27')
        self.assertTrue(info['fallback_used'])
        # leakage guard: same as_of passed through to the fallback season
        self.assertEqual({a for _, a in calls}, {AS_OF})
        self.assertEqual([s for s, _ in calls], ['2026-27', '2025-26'])

    def test_thin_current_season_counts_as_insufficient(self):
        fetch = lambda season, as_of: teams(2) if season == '2026-27' else teams(30)
        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25)
        self.assertEqual(len(data), 30)
        self.assertTrue(info['fallback_used'])
        self.assertEqual(info['current_rows'], 2)

    def test_sufficient_current_season_no_fallback(self):
        calls = []
        def fetch(season, as_of):
            calls.append(season)
            return teams(30)
        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25)
        self.assertFalse(info['fallback_used'])
        self.assertEqual(info['data_season'], '2026-27')
        self.assertEqual(calls, ['2026-27'])

    def test_both_empty_reports_failure_not_fallback(self):
        data, info = extractor.fetch_with_season_fallback(lambda s, a: {}, '2026-27', AS_OF, 25)
        self.assertFalse(data)
        self.assertFalse(info['fallback_used'])
        self.assertTrue(info['fallback_failed'])

    def test_payload_records_data_sources(self):
        sources = {"team_stats": {"data_season": "2025-26", "fallback_used": True}}
        game = {"name": "BOS@DET", "date": AS_OF, "tag": "BOS_DET",
                "away": {"abbreviation": "BOS", "name": "Boston Celtics"},
                "home": {"abbreviation": "DET", "name": "Detroit Pistons"}}
        from unittest import mock
        with mock.patch.object(extractor, 'fetch_team_roster', return_value=[]), \
             mock.patch.object(extractor, 'fetch_team_injuries', return_value={}), \
             mock.patch.object(extractor, 'fetch_nba_news', return_value=[]):
            pkg = extractor.extract_single_game(game, {}, {}, {}, teams(0), {}, data_sources=sources)
        self.assertTrue(pkg['meta']['fallback_used'])
        self.assertEqual(pkg['meta']['data_sources']['team_stats']['data_season'], '2025-26')


class ReportGateTests(unittest.TestCase):
    META = {"away": {"abbr": "BOS"}, "home": {"abbr": "DET"}}

    def test_empty_team_stats_do_not_claim_pace_or_defence(self):
        status = mc.context_inputs_status({"BOS": {}, "DET": {}}, self.META)
        self.assertFalse(status['pace'])
        self.assertFalse(status['defence'])
        text = mc.format_mc_section([], context_status=status)
        self.assertNotIn("分鐘、Pace", text)
        self.assertIn("數據缺失", text)
        self.assertIn("冇", text)
        self.assertIn("Pace、防守", text)

    def test_populated_fallback_discloses_season(self):
        meta = dict(self.META, data_sources={"team_stats": {"data_season": "2025-26", "fallback_used": True}})
        ts = {"BOS": {"PACE": 99.1, "DEF_RANK": 3}, "DET": {"PACE": 98.0, "DEF_RANK": 20}}
        status = mc.context_inputs_status(ts, meta)
        self.assertTrue(status['pace'] and status['defence'])
        text = mc.format_mc_section([], context_status=status)
        self.assertIn("2025-26", text)
        self.assertIn("分鐘、Pace、防守", text)


if __name__ == '__main__':
    unittest.main()


class PartialFillTests(unittest.TestCase):
    """2026-10-23: 28 of 30 teams had played, the feed passed the >=25 test, and the
    two teams that had not yet played got no team or advanced data."""

    def test_missing_teams_filled_from_previous_season_current_rows_kept(self):
        current = {k: {"PACE": 101.0} for k in (f"T{i}" for i in range(28))}
        prior = {k: {"PACE": 99.0} for k in (f"T{i}" for i in range(30))}
        calls = []

        def fetch(season, as_of):
            calls.append((season, as_of))
            return current if season == '2026-27' else prior

        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25, 'team_stats', fill_below=30)
        self.assertEqual(len(data), 30)
        self.assertEqual(data["T0"]["PACE"], 101.0)       # current season wins where it exists
        self.assertEqual(data["T29"]["PACE"], 99.0)       # missing team filled from last season
        self.assertTrue(info["fallback_used"] and info["fallback_partial"])
        self.assertEqual(info["filled_count"], 2)
        self.assertEqual(info["filled_from"], '2025-26')
        self.assertEqual({a for _, a in calls}, {AS_OF})   # leakage cutoff unchanged

    def test_complete_current_feed_makes_no_extra_request(self):
        calls = []

        def fetch(season, as_of):
            calls.append(season)
            return teams(30)

        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25, 'team_stats', fill_below=30)
        self.assertEqual(calls, ['2026-27'])
        self.assertFalse(info["fallback_used"])

    def test_player_feed_always_fills_missing_players(self):
        fetch = lambda season, as_of: ({1: {"USG_PCT": 25}} if season == '2026-27'
                                       else {1: {"USG_PCT": 20}, 2: {"USG_PCT": 18}})
        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 1, 'player_advanced',
                                                         fill_below=extractor.ALWAYS_FILL)
        self.assertEqual(data[1]["USG_PCT"], 25)
        self.assertEqual(data[2]["USG_PCT"], 18)
        self.assertEqual(info["filled_count"], 1)

    def test_prior_empty_leaves_current_untouched(self):
        fetch = lambda season, as_of: teams(28) if season == '2026-27' else {}
        data, info = extractor.fetch_with_season_fallback(fetch, '2026-27', AS_OF, 25, 'team_stats', fill_below=30)
        self.assertEqual(len(data), 28)
        self.assertFalse(info["fallback_used"])
