from __future__ import annotations

import contextlib
import io
import json
import os
import pickle
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

NBA_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_ROOT))
sys.path.insert(0, str(NBA_ROOT / 'nba_data_extractor' / 'scripts'))
import nba_extractor as extractor
import nba_orchestrator as orchestrator
import claw_sportsbet_odds as claw


@contextlib.contextmanager
def espn_log(**kwargs):
    """The old PlayerGameLog fixtures, served through the ESPN game-log path."""
    api = mock.Mock(**kwargs)

    def frame(player_id, season, date_to, season_type):
        return api(player_id=player_id, season=season, date_to_nullable=date_to,
                   season_type_all_star=season_type).get_data_frames()[0], 'espn'
    with mock.patch.object(extractor, 'player_log_frame', side_effect=frame):
        yield api


def box_score(day, points, matchup='HOU @ DAL'):
    row = dict.fromkeys(['REB', 'AST', 'STL', 'BLK', 'TOV', 'MIN', 'FGM', 'FGA',
                         'FG_PCT', 'FG3M', 'FG3A', 'FTM', 'FTA', 'PLUS_MINUS'], 0)
    row.update(GAME_DATE=day, MATCHUP=matchup, WL='W', PTS=points)
    return row


class PreseasonHistoryTests(unittest.TestCase):
    def test_prior_season_only_for_preseason_and_follows_target_year(self):
        self.assertEqual(extractor.statistics_season_for_game('2026-10-09'), '2025-26')
        self.assertEqual(extractor.statistics_season_for_game('2027-10-09'), '2026-27')
        self.assertEqual(extractor.statistics_season_for_game('2026-11-09'), '2026-27')
        self.assertEqual(extractor.statistics_season_for_game('2026-04-05'), '2025-26')

    def test_history_sorted_and_event_day_future_games_removed(self):
        playoff = pd.DataFrame([box_score('2026-04-20', 27), box_score('2026-10-09', 50)])
        regular = pd.DataFrame([box_score('2026-04-10', 19), box_score('2026-04-12', 31),
                                box_score('2026-10-10', 70)])
        def endpoint(**kwargs):
            frame = playoff if kwargs.get('season_type_all_star') == 'Playoffs' else regular
            return mock.Mock(get_data_frames=mock.Mock(return_value=[frame]))
        with espn_log(side_effect=endpoint) as api:
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', n=3,
                                                season='2025-26', as_of='2026-10-09T12:10:00Z')
        self.assertEqual(log['PTS'], [27, 31, 19])
        self.assertEqual(log['history_season'], '2025-26')
        self.assertEqual(log['history_date_to'], '10/08/2026')
        self.assertEqual(log['playoff_games_in_l10'], 1)
        self.assertEqual(log['l10_season_types'], ['Playoffs', 'Regular Season', 'Regular Season'])
        for call in api.call_args_list:
            self.assertEqual(call.kwargs['season'], '2025-26')
            self.assertEqual(call.kwargs['date_to_nullable'], '10/08/2026')

    def test_no_history_for_rookie_does_not_invent_data(self):
        endpoint = mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame()]))
        with espn_log(return_value=endpoint):
            self.assertIsNone(extractor.fetch_player_gamelog(1, 'Rookie', season='2025-26', as_of='2026-10-09'))

    def test_regular_source_failure_cannot_silently_use_partial_playoffs(self):
        def endpoint(**kwargs):
            if kwargs.get('season_type_all_star') == 'Playoffs':
                return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame([box_score('2026-04-20', 27)])]))
            raise TimeoutError('regular-season source unavailable')
        with espn_log(side_effect=endpoint):
            self.assertIsNone(extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2025-26', as_of='2026-10-09'))

    def test_current_roster_with_explicit_prior_history_provenance(self):
        game = {'name': 'Houston Rockets at Dallas Mavericks', 'date': '2026-10-09T12:10:00Z',
                'away': {'name': 'Houston Rockets', 'abbreviation': 'HOU'},
                'home': {'name': 'Dallas Mavericks', 'abbreviation': 'DAL'}}
        with mock.patch.object(extractor, 'fetch_team_roster', return_value=[]) as roster, mock.patch.object(extractor, 'fetch_team_injuries', return_value={}), mock.patch.object(extractor, 'fetch_nba_news', return_value=[]):
            package = extractor.extract_single_game(game, {}, {}, {}, {}, {})
        self.assertTrue(all(c.args[1] == '2026-27' for c in roster.call_args_list))
        self.assertEqual(package['meta']['statistics_season'], '2025-26')
        self.assertEqual(package['meta']['history_mode'], 'previous_season_reference')
        self.assertEqual(package['meta']['automation_mode'], 'shadow')

    def test_league_tables_get_same_explicit_season_and_cutoff(self):
        with mock.patch.object(extractor.nba_espn_league, 'season_games', return_value=[]) as games:
            self.assertEqual(extractor.espn_league_tables('2025-26', '2026-10-09', {}), ({}, {}))
        self.assertEqual(games.call_args.args[:2], ('2025-26', '10/07/2026'))


    def test_failed_child_stdout_retained_in_orchestrator(self):
        error = subprocess.CalledProcessError(1, ['extractor'], output='All players have no L10; season=2026-27', stderr='warning')
        output = io.StringIO()
        with mock.patch.object(orchestrator.subprocess, 'run', side_effect=error), contextlib.redirect_stdout(output):
            self.assertFalse(orchestrator.run_script(str(NBA_ROOT / 'nba_data_extractor/scripts/nba_extractor.py'), []))
        self.assertIn('All players have no L10; season=2026-27', output.getvalue())


class LiveMarketContractTests(unittest.TestCase):
    def test_full_game_markets_cannot_be_overwritten_by_quarters_or_alternates(self):
        x = claw.SportsbetNBAExtractor(target_date='2026-10-09')
        raw = {'Match Betting': {'Sacramento Kings': '2.35', 'Los Angeles Lakers': '1.63'},
               '1st Half Match Betting (3-Way)': {'Sacramento Kings': '4.10'},
               '4th Quarter Match Betting (3-Way)': {'Sacramento Kings': '2.15'},
               'Line': {'Los Angeles Lakers -3.5': '1.9', 'Sacramento Kings +3.5': '1.9'},
               'Pick Your Own Line': {'Sacramento Kings +36.5': '1.02'}}
        data = x._format_as_sportsbet('SAC at LAL', 'SAC', 'LAL', x._clean_markets(raw))
        self.assertEqual(data['game_lines'], {'spread_away': '+3.5', 'ml_away': '2.35', 'ml_home': '1.63'})

    def test_alternate_only_has_no_invented_main_spread(self):
        x = claw.SportsbetNBAExtractor(target_date='2026-10-09')
        raw = {'Pick Your Own Line': {'Sacramento Kings +36.5': '1.02'},
               'Match Betting': {'Sacramento Kings': '2.35'}}
        data = x._format_as_sportsbet('SAC at LAL', 'SAC', 'LAL', x._clean_markets(raw))
        self.assertNotIn('spread_away', data['game_lines'])

    def test_no_props_skips_expensive_extraction_and_produces_no_report(self):
        output = io.StringIO()
        with mock.patch.object(orchestrator, '_load_sportsbet_json', return_value={'game_lines': {'ml_away': '1.72'}, 'player_props': {'points': {}}}), mock.patch.object(orchestrator, 'run_script') as run, contextlib.redirect_stdout(output):
            self.assertFalse(orchestrator.process_single_game('HOU_DAL', 'odds.json', '/unused', '2026-10-09'))
        run.assert_not_called()
        self.assertIn('player_markets_not_open', output.getvalue())

    def test_only_valid_supported_milestone_counts_as_open(self):
        for lines, expected in [({'10': '1.72'}, True), ({'10.5': '1.72'}, False),
                                ({'10': 'NaN'}, False), ({'10': 'Infinity'}, False),
                                ({'10': '1'}, False), ({'0': '1.72'}, False)]:
            with self.subTest(lines=lines):
                payload = {'player_props': {'points': {'Kevin Durant': {'lines': lines}}}}
                self.assertEqual(orchestrator.player_milestone_markets_available(payload), expected)



class RegularOpenerHistoryTests(unittest.TestCase):
    def test_opener_empty_current_season_loads_actual_previous_history(self):
        def endpoint(**kwargs):
            rows = [] if kwargs['season'] == '2026-27' else [box_score('2026-04-10', 31)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with espn_log(side_effect=endpoint):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-21', include_previous=True)
        self.assertEqual(log['PTS'], [31])
        self.assertEqual(log['history_seasons'], ['2025-26'])
        self.assertEqual(log['l10_seasons'], ['2025-26'])

    def test_early_current_games_precede_prior_season_games(self):
        def endpoint(**kwargs):
            rows = [box_score('2026-10-21', 24)] if kwargs['season'] == '2026-27' else [box_score('2026-04-10', 31)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with espn_log(side_effect=endpoint):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-23', include_previous=True)
        self.assertEqual(log['PTS'], [24, 31])
        self.assertEqual(log['history_seasons'], ['2026-27', '2025-26'])

    def test_complete_current_l10_never_queries_older_season(self):
        def endpoint(**kwargs):
            rows = [box_score(f'2026-11-{i:02}', i + 20) for i in range(1, 11)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with espn_log(side_effect=endpoint) as api:
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-11-15', include_previous=True)
        self.assertEqual(len(log['PTS']), 10)
        self.assertTrue(all(c.kwargs['season'] == '2026-27' for c in api.call_args_list))

    def test_failed_current_api_does_not_masquerade_as_empty_season(self):
        with espn_log(side_effect=TimeoutError('current season unavailable')) as api:
            self.assertIsNone(extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-21', include_previous=True))
        self.assertTrue(all(c.kwargs['season'] == '2026-27' for c in api.call_args_list))


class WaitingMarketCLITests(unittest.TestCase):
    def test_moneyline_only_cli_exits_retryable_75_and_never_claims_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / 'Sportsbet_Odds_HOU_DAL.json').write_text(json.dumps({
                'target_analysis_date': '2026-10-09', 'event_local_date': '2026-10-09',
                'matchup': 'HOU @ DAL', 'game_lines': {'ml_away': '1.72'},
                'player_props': {'points': {}}}))
            output = io.StringIO()
            argv = ['nba_orchestrator.py', '--date', '2026-10-09', '--game', 'HOU_DAL', '--auto', '--skip-cloudflare-deploy']
            with mock.patch.object(sys, 'argv', argv), mock.patch.object(orchestrator, 'get_target_dir', return_value=str(folder)), mock.patch.object(orchestrator, 'load_espn_schedule', return_value=({'HOU_DAL'}, True)), mock.patch.object(orchestrator, 'run_script') as run, contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as exc:
                orchestrator.main()
            self.assertEqual(exc.exception.code, 75)
            run.assert_not_called()
            self.assertIn('Pipeline 未完成', output.getvalue())
            self.assertFalse((folder / 'Game_HOU_DAL_Full_Analysis.md').exists())
            self.assertFalse((folder / '_prediction_snapshots').exists())


class USGameDateCutoffTests(unittest.TestCase):
    def test_utc_next_day_does_not_include_target_us_game_day(self):
        self.assertEqual(extractor.history_date_to('2026-10-09T02:30:00Z'), '10/07/2026')
        self.assertEqual(extractor.history_date_to('2026-10-09T12:10:00Z'), '10/08/2026')
        self.assertEqual(extractor.history_date_to('2026-10-09'), '10/07/2026')

    def test_api_rows_on_target_us_day_are_removed_even_if_provider_ignores_cutoff(self):
        rows = pd.DataFrame([box_score('2026-10-08', 50), box_score('2026-10-07', 27)])
        endpoint = mock.Mock(get_data_frames=mock.Mock(return_value=[rows]))
        with espn_log(return_value=endpoint):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-09T02:30:00Z')
        self.assertEqual(log['PTS'], [27])
        self.assertEqual(log['history_date_to'], '10/07/2026')

    def test_unknown_official_game_never_uses_synthetic_fallback(self):
        argv = ['nba_extractor.py', '--date', '20261009', '--game', 'HOU_DAL']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(extractor, 'fetch_espn_scoreboard', return_value=[]), mock.patch.object(extractor, 'espn_league_tables', return_value=({}, {})), mock.patch.object(extractor, 'fetch_action_network_odds', return_value={'dummy': {}}), self.assertRaises(SystemExit) as exc:
            extractor.main()
        self.assertEqual(exc.exception.code, 1)
        self.assertFalse(hasattr(extractor, 'build_game_info_from_tag'), 'no synthetic game path exists')


if __name__ == '__main__':
    unittest.main()
