from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import au_retest_watch as watch  # noqa: E402


def test_date_match_is_not_clean_pit(tmp_path):
    meeting = tmp_path / '2026-08-05 Moe Race Day'
    meeting.mkdir()
    (meeting / 'Race_1_Logic.json').write_text('{}')
    with (tmp_path / 'AU_Historical_Raw_Race_Results.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=['Date', 'Track', 'Race', 'Horse', 'Pos'])
        writer.writeheader()
        writer.writerow(dict(Date='2026-08-05', Track='Moe', Race='1', Horse='Only one label', Pos='1'))
    stats = watch.measure(tmp_path)
    assert stats['date_matched_races'] == 1
    assert stats['clean_races'] is None
    assert stats['readiness_status'] == 'NOT_ESTABLISHED'
    due, waiting = watch.partition_retests(stats, [{'id': 'x', 'metric': 'date_matched_races', 'threshold': 1}])
    assert due == []
    assert 'diagnostic_metric_not_readiness' in waiting[0]['readiness_blockers']


def test_contract_date_boundary_excludes_june(tmp_path):
    for date in ['2026-06-06', '2026-08-04', '2026-08-05']:
        meeting = tmp_path / f'{date} Moe Race Day'
        meeting.mkdir()
        (meeting / 'Race_1_Logic.json').write_text('{}')
    (tmp_path / 'AU_Historical_Raw_Race_Results.csv').write_text(
        'Date,Track,Race,Horse,Pos\n2026-06-06,Moe,1,A,1\n2026-08-04,Moe,1,A,1\n2026-08-05,Moe,1,A,1\n')
    assert watch.measure(tmp_path)['date_matched_races'] == 1


@pytest.mark.parametrize('now', [None, float('nan'), float('inf'), True, '600'])
def test_missing_invalid_or_unverified_readiness_never_due(now):
    due, waiting = watch.partition_retests(
        {'clean_races': now, 'readiness_status': 'NOT_ESTABLISHED'},
        [{'id': 'x', 'metric': 'clean_races', 'threshold': 1}])
    assert due == []
    assert waiting[0]['pct'] is None


@pytest.mark.parametrize('threshold', [0, -1, None, float('nan'), True])
def test_invalid_registered_threshold_is_observable(threshold):
    due, waiting = watch.partition_retests(
        {'races': 600, 'readiness_status': 'VERIFIED'},
        [{'id': 'x', 'metric': 'races', 'threshold': threshold}])
    assert due == []
    assert 'threshold_missing_or_invalid' in waiting[0]['readiness_blockers']


def test_pending_followups_cannot_trigger_experiment():
    assert watch.REGISTERED == []
    assert {x['id'] for x in watch.RESOLVED} == {'class_score', 'speed_figure'}
    assert {x['id'] for x in watch.PENDING_REGISTRATIONS} == {
        'class_label_oos', 'people_asof_oos', 'race_shape_start_position'}
    assert all(x['status'] == 'PENDING_REGISTRATION' for x in watch.PENDING_REGISTRATIONS)
    assert not any('threshold' in x or 'cmd' in x for x in watch.PENDING_REGISTRATIONS)
