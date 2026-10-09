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
sys.path.insert(0, str(NBA_ROOT / 'nba_wong_choi' / 'scripts'))
import nba_extractor as extractor
import nba_orchestrator as orchestrator
import generate_nba_reports as reports
import generate_nba_sgm_reports as sgm
import claw_sportsbet_odds as claw
import validate_nba_output as firewall
from nba_identity import player_name_key


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
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=endpoint) as api, mock.patch.object(extractor.time, 'sleep'):
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
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', return_value=endpoint), mock.patch.object(extractor.time, 'sleep'):
            self.assertIsNone(extractor.fetch_player_gamelog(1, 'Rookie', season='2025-26', as_of='2026-10-09'))

    def test_regular_source_failure_cannot_silently_use_partial_playoffs(self):
        def endpoint(**kwargs):
            if kwargs.get('season_type_all_star') == 'Playoffs':
                return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame([box_score('2026-04-20', 27)])]))
            raise TimeoutError('regular-season source unavailable')
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=endpoint), mock.patch.object(extractor.time, 'sleep'):
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

    def test_statistics_endpoints_get_same_explicit_season_and_cutoff(self):
        pairs = [(extractor.fetch_all_player_advanced_stats, extractor.leaguedashplayerstats, 'LeagueDashPlayerStats'),
                 (extractor.fetch_team_advanced_stats, extractor.leaguedashteamstats, 'LeagueDashTeamStats'),
                 (extractor.fetch_defender_impact, extractor.leaguedashptdefend, 'LeagueDashPtDefend'),
                 (extractor.fetch_team_defense_vs_position, extractor.leaguedashptteamdefend, 'LeagueDashPtTeamDefend')]
        for fn, module, name in pairs:
            with self.subTest(endpoint=name), mock.patch.object(module, name, side_effect=TimeoutError('offline fixture')) as api:
                self.assertEqual(fn('2025-26', '2026-10-09'), {})
                self.assertEqual(api.call_args.kwargs['season'], '2025-26')
                self.assertEqual(api.call_args.kwargs['date_to_nullable'], '10/07/2026')

    def test_shadow_banner_in_game_and_both_master_reports(self):
        fixture = NBA_ROOT / 'nba_wong_choi/tests/fixtures/valid_game.json'
        meta = json.loads(fixture.read_text())['meta']
        meta.update(season_phase='PRESEASON', automation_mode='shadow', statistics_season='2025-26',
                    roster_season='2026-27', history_mode='previous_season_reference', history_date_to='10/08/2026')
        text = reports.gen_full_report(meta, {}, {}, {}, {}, [], '2026-10-09 12:00', season_phase='EARLY_SEASON')
        self.assertIn('NO BET — PRESEASON SHADOW ONLY', text)
        self.assertIn('statistics_season**: 2025-26', text)
        game = {'tag': 'HOU_DAL', 'shadow': True, 'combos': {}, 'summary': ''}
        self.assertIn('NO BET — PRESEASON SHADOW ONLY', sgm.generate_all_sgm_report([game], '2026-10-09'))
        self.assertIn('NO BET — PRESEASON SHADOW ONLY', sgm.generate_banker_report([game], '2026-10-09'))

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

    def test_nullable_history_does_not_crash_card_builder(self):
        card = reports.build_player_card('Rookie', 'LAL', {'lines': {}},
                                         {'gamelog': None}, 'points', engine_mode='legacy')
        self.assertEqual(card['l10'], [])


class PlayerIdentityAndShadowCoverageTests(unittest.TestCase):
    def test_full_name_normalizes_accents_without_surname_or_suffix_collision(self):
        self.assertEqual(player_name_key('Luka Dončić'), player_name_key('Luka Doncic'))
        self.assertEqual(player_name_key('Gary Payton Jr.'), player_name_key('Gary Payton Jr'))
        self.assertNotEqual(player_name_key('Gary Payton Jr.'), player_name_key('Gary Payton Sr.'))
        players = {'LAL': [{'name': 'Luka Dončić'}, {'name': 'Gary Payton Jr.'}]}
        self.assertEqual(reports.find_player_in_extractor(players, 'Luka Doncic', 'LAL')['name'], 'Luka Dončić')
        self.assertIsNone(reports.find_player_in_extractor(players, 'Dončić', 'LAL'))
        self.assertIsNone(reports.find_player_in_extractor(players, 'Gary Payton Sr.', 'LAL'))

    def test_ambiguous_full_names_are_rejected(self):
        players = {'LAL': [{'name': 'Luka Dončić'}, {'name': 'Luka Doncic'}]}
        self.assertIsNone(reports.find_player_in_extractor(players, 'Luka Doncic', 'LAL'))

    def source_files(self, tmp, phase='PRESEASON', with_history=True):
        odds = Path(tmp) / 'Sportsbet_Odds_SAC_LAL.json'
        odds.write_text(json.dumps({'player_props': {'points': {
            name: {'lines': {'10': '1.72'}} for name in ['Austin Reaves', 'Luka Doncic', 'Darius Acuff Jr.']}}}))
        data = {'meta': {'season_phase': phase, 'automation_mode': 'shadow' if phase == 'PRESEASON' else 'production'},
                'players': {'LAL': [{'name': 'Austin Reaves', 'gamelog': {'PTS': [22]} if with_history else None},
                                   {'name': 'Luka Dončić', 'gamelog': {'PTS': [31]} if with_history else None}]}}
        odds.with_name('nba_game_data_SAC_LAL.json').write_text(json.dumps(data))
        return str(odds)

    def test_shadow_requires_all_available_priced_players_not_news_mentions(self):
        with tempfile.TemporaryDirectory() as tmp:
            odds = self.source_files(tmp)
            text = 'NO BET — PRESEASON SHADOW ONLY\n#### Austin Reaves (#1, LAL) — PTS\n#### Luka Doncic (#77, LAL) — PTS'
            self.assertEqual(firewall.check_fw06_real_players(text, odds), [])
            news_only = text.replace('#### Luka Doncic (#77, LAL) — PTS', 'Injury news: Luka Doncic is day-to-day')
            self.assertIn('BLOCK', firewall.check_fw06_real_players(news_only, odds)[0])
            self.assertIn('BLOCK', firewall.check_fw06_real_players(text.replace('NO BET — PRESEASON SHADOW ONLY', ''), odds)[0])

    def test_shadow_without_real_history_is_blocked_even_with_all_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            odds = self.source_files(tmp, with_history=False)
            text = 'NO BET — PRESEASON SHADOW ONLY\n#### Austin Reaves (#1, LAL) — PTS\n#### Luka Doncic (#77, LAL) — PTS'
            self.assertIn('BLOCK', firewall.check_fw06_real_players(text, odds)[0])

    def test_production_minimum_coverage_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            odds = self.source_files(tmp, phase='EARLY_REGULAR')
            text = '#### Austin Reaves (#1, LAL) — PTS\n#### Luka Doncic (#77, LAL) — PTS\nNews: Darius Acuff Jr.'
            self.assertIn('要求 ≥3', firewall.check_fw06_real_players(text, odds)[0])

    def test_invalid_source_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            odds = Path(tmp) / 'Sportsbet_Odds_SAC_LAL.json'
            odds.write_text('{')
            self.assertIn('BLOCK', firewall.check_fw06_real_players('Luka Doncic', str(odds))[0])


class LocalModelConfigurationTests(unittest.TestCase):
    def test_explicit_local_model_is_loaded_without_cloud_dataset(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / 'local-model'
            local.mkdir()
            (local / 'model.pkl').write_bytes(pickle.dumps({'fixture_model': True}))
            (local / 'feature_names.json').write_text(json.dumps({'features': ['pts']}))
            code = "import sys; sys.path.insert(0, sys.argv[1]); from nba_ml_predictor import MLPropPredictor; p=MLPropPredictor(); assert p.model == {'fixture_model': True}; assert p.feature_names == ['pts']"
            repo = NBA_ROOT.parents[2]
            result = subprocess.run([sys.executable, '-c', code, str(repo / '.agents/scripts/nba_ml')],
                                    env={**os.environ, 'NBA_WC_MODEL_DIR': str(local),
                                         'WONGCHOI_DATA_ROOT': str(Path(tmp) / 'absent-cloud-dataset'),
                                         'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RegularOpenerHistoryTests(unittest.TestCase):
    def test_opener_empty_current_season_loads_actual_previous_history(self):
        def endpoint(**kwargs):
            rows = [] if kwargs['season'] == '2026-27' else [box_score('2026-04-10', 31)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=endpoint), mock.patch.object(extractor.time, 'sleep'):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-21', include_previous=True)
        self.assertEqual(log['PTS'], [31])
        self.assertEqual(log['history_seasons'], ['2025-26'])
        self.assertEqual(log['l10_seasons'], ['2025-26'])

    def test_early_current_games_precede_prior_season_games(self):
        def endpoint(**kwargs):
            rows = [box_score('2026-10-21', 24)] if kwargs['season'] == '2026-27' else [box_score('2026-04-10', 31)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=endpoint), mock.patch.object(extractor.time, 'sleep'):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-23', include_previous=True)
        self.assertEqual(log['PTS'], [24, 31])
        self.assertEqual(log['history_seasons'], ['2026-27', '2025-26'])

    def test_complete_current_l10_never_queries_older_season(self):
        def endpoint(**kwargs):
            rows = [box_score(f'2026-11-{i:02}', i + 20) for i in range(1, 11)]
            return mock.Mock(get_data_frames=mock.Mock(return_value=[pd.DataFrame(rows)]))
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=endpoint) as api, mock.patch.object(extractor.time, 'sleep'):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-11-15', include_previous=True)
        self.assertEqual(len(log['PTS']), 10)
        self.assertTrue(all(c.kwargs['season'] == '2026-27' for c in api.call_args_list))

    def test_failed_current_api_does_not_masquerade_as_empty_season(self):
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', side_effect=TimeoutError('current season unavailable')) as api, mock.patch.object(extractor.time, 'sleep'):
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
        with mock.patch.object(extractor.playergamelog, 'PlayerGameLog', return_value=endpoint), mock.patch.object(extractor.time, 'sleep'):
            log = extractor.fetch_player_gamelog(201142, 'Kevin Durant', season='2026-27', as_of='2026-10-09T02:30:00Z')
        self.assertEqual(log['PTS'], [27])
        self.assertEqual(log['history_date_to'], '10/07/2026')

    def test_unknown_official_game_never_uses_synthetic_fallback(self):
        argv = ['nba_extractor.py', '--date', '20261009', '--game', 'HOU_DAL']
        with mock.patch.object(sys, 'argv', argv), mock.patch.object(extractor, 'fetch_espn_scoreboard', return_value=[]), mock.patch.object(extractor, 'fetch_team_advanced_stats', return_value={}), mock.patch.object(extractor, 'fetch_all_player_advanced_stats', return_value={}), mock.patch.object(extractor, 'fetch_defender_impact', return_value={}), mock.patch.object(extractor, 'fetch_team_defense_vs_position', return_value={}), mock.patch.object(extractor, 'fetch_action_network_odds', return_value={'dummy': {}}), mock.patch.object(extractor, 'build_game_info_from_tag') as synthetic, self.assertRaises(SystemExit) as exc:
            extractor.main()
        self.assertEqual(exc.exception.code, 1)
        synthetic.assert_not_called()


if __name__ == '__main__':
    unittest.main()
