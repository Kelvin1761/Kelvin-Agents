from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

DAILY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DAILY))
import au_daily_schedule as S  # noqa: E402


class RunLog:
    def __init__(self):
        self.data = {key: [] for key in ['scratchings_detected', 'track_changes_detected', 'races_updated', 'analysis_changes']}
        self.warnings = []
        self.events = []

    def warn(self, text):
        self.warnings.append(text)

    def step(self, *args, **kwargs):
        self.events.append(('step', args, kwargs))

    def meeting(self, *args, **kwargs):
        self.events.append(('meeting', args, kwargs))


def _state(numbers):
    return {1: {'going': 'Good 4', 'field': list(numbers),
                'jockeys': {n: 'Fixture Rider' for n in numbers},
                'barriers': {n: n for n in numbers}}}


@pytest.mark.parametrize("returncode", [1, 2, 124])
def test_rebuild_returns_failure_after_successful_extract_failed_scoring(tmp_path, returncode):
    folder = tmp_path / '2026-08-05 Fixture Race 1-2'
    folder.mkdir()
    log = RunLog()
    metadata = {'meetingId': '123', 'races': ['456', '457'], 'date': '2026-08-05'}
    with patch.object(S, 'load_mapping', return_value={'fixture': metadata}), \
         patch.object(S, 'warm_people_pages'), \
         patch.object(S, 'apply_ra_ratings'), \
         patch.object(S, 'run_cmd', side_effect=[(0, 'extract completed'), (returncode, 'scoring failed')]):
        assert S.rebuild_meeting_from_cache(log, folder, 'fixture', 'Good 4') is False
    assert any(f'rc={returncode}' in message for message in log.warnings)


def test_failed_field_refresh_does_not_record_rescored_or_successful_update(tmp_path):
    folder = tmp_path / '2026-08-05 Fixture Race 1-2'
    folder.mkdir()
    old = folder / 'Race_1_Logic.json'
    old.write_text(json.dumps({'horses': {'1': {'horse_name': 'First'}, '2': {'horse_name': 'Second'}}}))
    original = old.read_bytes()
    log = RunLog()
    stored, live = _state(['1', '2']), _state(['1'])
    with patch.object(S, 'stored_race_state', return_value=stored), \
         patch.object(S, 'live_race_state', return_value=(live, 'Good 4')), \
         patch.object(S, 'mapping_key_for', return_value='fixture'), \
         patch.object(S, 'market_drift'), \
         patch.object(S, 'record_odds_from_cache', return_value=2), \
         patch.object(S, 'record_odds_snapshot') as after_snapshot, \
         patch.object(S, 'top_picks_snapshot', return_value={}), \
         patch.object(S, 'rebuild_meeting_from_cache', return_value=False):
        with pytest.raises(S.TemporaryFailure, match='重建出賽名單失敗'):
            S.refresh_one_meeting(log, folder, {})
    assert not log.data['races_updated'] and not log.data['analysis_changes']
    assert not any(e[0] == 'meeting' and e[1][1] == 'rescored' for e in log.events)
    after_snapshot.assert_not_called()
    assert old.read_bytes() == original


def test_successful_rebuild_still_returns_success(tmp_path):
    folder = tmp_path / '2026-08-05 Fixture Race 1-2'
    folder.mkdir()
    log = RunLog()
    metadata = {'meetingId': '123', 'races': ['456', '457'], 'date': '2026-08-05'}
    with patch.object(S, 'load_mapping', return_value={'fixture': metadata}), \
         patch.object(S, 'warm_people_pages'), \
         patch.object(S, 'apply_ra_ratings'), \
         patch.object(S, 'run_cmd', side_effect=[(0, 'extract completed'), (0, 'scoring completed')]):
        assert S.rebuild_meeting_from_cache(log, folder, 'fixture', 'Good 4') is True
    assert not log.warnings


def test_actual_refresh_and_rebuild_chain_propagates_failure(tmp_path):
    folder = tmp_path / '2026-08-05 Fixture Race 1-2'
    folder.mkdir()
    old = folder / 'Race_1_Logic.json'
    old.write_text(json.dumps({'race_analysis': {'going': 'Good 4'},
                              'horses': {n: {'horse_name': n, 'jockey': 'Fixture Rider', 'barrier': n}
                                         for n in ['1', '2']}}))
    original = old.read_bytes()
    log = RunLog()
    metadata = {'meetingId': '123', 'races': ['456', '457'], 'date': '2026-08-05'}
    with patch.object(S, 'live_race_state', return_value=(_state(['1']), 'Good 4')), \
         patch.object(S, 'mapping_key_for', return_value='fixture'), \
         patch.object(S, 'load_mapping', return_value={'fixture': metadata}), \
         patch.object(S, 'market_drift'), \
         patch.object(S, 'record_odds_from_cache', return_value=2), \
         patch.object(S, 'record_odds_snapshot') as after_snapshot, \
         patch.object(S, 'warm_people_pages'), \
         patch.object(S, 'apply_ra_ratings'), \
         patch.object(S, 'run_cmd', side_effect=[(0, 'extract completed'), (1, 'scoring failed')]) as commands:
        with pytest.raises(S.TemporaryFailure, match='重建出賽名單失敗'):
            S.refresh_one_meeting(log, folder, {})
    assert commands.call_count == 2
    assert not log.data['races_updated'] and not log.data['analysis_changes']
    assert not any(e[0] == 'meeting' and e[1][1] == 'rescored' for e in log.events)
    after_snapshot.assert_not_called()
    assert old.read_bytes() == original
