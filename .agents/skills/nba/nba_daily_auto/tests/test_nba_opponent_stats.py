"""Opponent totals remain descriptive and preserve units, cutoff and missingness."""
import sys
from pathlib import Path
from unittest import mock
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'nba_data_extractor/scripts'))
import nba_extractor as extractor


def test_opponent_modes_preserve_source_and_do_not_read_own_totals():
    calls = []
    def endpoint(**kwargs):
        calls.append(kwargs)
        value = 115 if kwargs['per_mode_detailed'] == 'PerGame' else 109
        return mock.Mock(get_data_frames=lambda: [pd.DataFrame([{
            'TEAM_ID': 1, 'GP': 2, 'PTS': 999, 'REB': 999,
            'OPP_PTS': value, 'OPP_REB': 41, 'OPP_AST': 24,
            'OPP_OREB': 9, 'OPP_DREB': 32, 'OPP_FGA': 90, 'OPP_FGM': 42, 'OPP_FG3A': 35, 'OPP_FG3M': 12,
        }])])
    with mock.patch.object(extractor, 'NBA_API_AVAILABLE', True), mock.patch.object(extractor.teams, 'get_teams', return_value=[{'id': 1, 'abbreviation': 'MIL'}]), mock.patch.object(extractor.leaguedashteamstats, 'LeagueDashTeamStats', side_effect=endpoint), mock.patch.object(extractor.time, 'sleep'):
        record = extractor.fetch_team_opponent_stats('2026-27', '2026-10-25')['MIL']
    assert record['modes']['per_game']['values']['OPP_PTS'] == 115
    assert record['modes']['per_100_possessions']['values']['OPP_PTS'] == 109
    assert record['modes']['per_game']['games'] == 2
    assert record['modes']['per_100_possessions']['values']['OPP_FG3A'] == 35
    assert record['model_input_enabled'] is False
    for call in calls:
        assert call['season'] == '2026-27'
        assert call['date_to_nullable'] == extractor.history_date_to('2026-10-25')
        assert call['measure_type_detailed_defense'] == 'Opponent'
        assert call['season_type_all_star'] == 'Regular Season'


def test_partial_source_failure_and_missing_values_are_not_zero():
    def endpoint(**kwargs):
        if kwargs['per_mode_detailed'] == 'Per100Possessions':
            raise TimeoutError()
        return mock.Mock(get_data_frames=lambda: [pd.DataFrame([{'TEAM_ID': 1, 'GP': 1, 'OPP_PTS': float('nan')}])])
    with mock.patch.object(extractor, 'NBA_API_AVAILABLE', True), mock.patch.object(extractor.teams, 'get_teams', return_value=[{'id': 1, 'abbreviation': 'MIL'}]), mock.patch.object(extractor.leaguedashteamstats, 'LeagueDashTeamStats', side_effect=endpoint), mock.patch.object(extractor.time, 'sleep'):
        record = extractor.fetch_team_opponent_stats('2026-27', '2026-10-25')['MIL']
    assert record['modes']['per_game']['status'] == 'insufficient'
    assert record['modes']['per_game']['values']['OPP_REB'] is None
    assert record['modes']['per_game']['values']['OPP_PTS'] is None
    assert record['modes']['per_100_possessions']['status'] == 'unavailable'


def test_advanced_stats_attach_opponent_data_without_changing_ratings():
    frame = pd.DataFrame([{'TEAM_ID': 1, 'TEAM_NAME': 'Milwaukee', 'DEF_RATING': 110,
                           'OFF_RATING': 112, 'NET_RATING': 2, 'PACE': 99}])
    with mock.patch.object(extractor, 'NBA_API_AVAILABLE', True), mock.patch.object(extractor.teams, 'get_teams', return_value=[{'id': 1, 'abbreviation': 'MIL'}]), mock.patch.object(extractor.leaguedashteamstats, 'LeagueDashTeamStats', return_value=mock.Mock(get_data_frames=lambda: [frame])), mock.patch.object(extractor.time, 'sleep'), mock.patch.object(extractor, 'fetch_team_opponent_stats', return_value={'MIL': {'model_input_enabled': False}}) as source:
        record = extractor.fetch_team_advanced_stats('2026-27', '2026-10-25')['MIL']
    assert record['DEF_RATING'] == 110
    assert record['opponent_stats'] == {'model_input_enabled': False}
    source.assert_called_once_with('2026-27', '2026-10-25')
