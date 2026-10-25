"""Declared broad NBA intake preserves raw tables, provenance and missing sources."""
from pathlib import Path
import sys
from unittest import mock
import json
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'scripts/nba_ml'))
import nba_feature_intake as intake


def test_catalogue_has_separate_player_team_and_opponent_units():
    specs = intake.catalogue()
    assert len({row['name'] for row in specs}) == len(specs)
    assert {'player_advanced', 'player_usage', 'player_tracking_passing', 'player_tracking_rebounding',
            'player_tracking_possessions', 'team_opponent', 'team_opponent_per100'} <= {row['name'] for row in specs}
    assert next(row for row in specs if row['name'] == 'team_opponent_per100')['unit'] == 'Per100Possessions'


def test_capture_keeps_all_raw_columns_gp_and_explicit_cutoff(tmp_path):
    payload = {'resultSets': [{'name': 'stats', 'headers': ['PLAYER_ID', 'GP', 'POTENTIAL_AST', 'NEW_COLUMN'],
                               'rowSet': [[1, 2, 12, 999]]}]}
    fetch = mock.Mock(return_value=mock.Mock(get_dict=lambda: payload))
    spec = next(row for row in intake.catalogue() if row['name'] == 'player_tracking_passing')
    result = intake.capture(spec, season='2026-27', cutoff='10/23/2026', output=tmp_path, fetch=fetch)
    assert result['status'] == 'available'
    assert result['tables'][0]['gp_max'] == 2
    assert result['verification'] == 'single_NBA_source_research_only'
    assert fetch.call_args.kwargs['date_to_nullable'] == '10/23/2026'
    assert json.loads((tmp_path / result['path']).read_text()) == payload


def test_network_failure_is_unavailable_not_empty_or_zero(tmp_path):
    fetch = mock.Mock(side_effect=TimeoutError())
    result = intake.capture(intake.catalogue()[0], season='2026-27', cutoff='10/23/2026', output=tmp_path, fetch=fetch)
    assert result['status'] == 'unavailable' and result['error_type'] == 'TimeoutError'
    assert not list(tmp_path.glob('*.json'))


def test_malformed_table_is_rejected():
    with pytest.raises(ValueError):
        intake.table_inventory({'resultSets': [{'headers': ['A'], 'rowSet': [[1, 2]]}]})
