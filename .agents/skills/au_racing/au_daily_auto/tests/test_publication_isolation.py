"""Exercise the real snapshot admission path, without Cloudflare or extraction."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import au_daily_schedule as S


@pytest.fixture
def snapshot_fixture(tmp_path, monkeypatch):
    work = tmp_path / 'work'
    work.mkdir()
    monkeypatch.setenv('WC_AU_SCHED_LOG_DIR', str(tmp_path / 'logs'))
    monkeypatch.setattr(S, 'WORK_DIR', work)
    log = S.RunLog('evening', S.date(2026, 10, 23), tmp_path / 'run.json', notify=False)
    base = {'meetings':[{'date':'2026-10-25','venue':'ShaTin','region':'HKJC'}],
            'races':{'2026-10-25|ShaTin':{'races_by_analyst':{'Kelvin':[{'race_number':1}]}}}}

    def download(_log, target):
        target.write_text(json.dumps(base))
        return target

    def merge(command, **kwargs):
        folder = Path(command[command.index('--au-meeting-dir') + 1])
        if 'Broken' in folder.name:
            return 2, 'parser rejected bad meeting'
        payload = json.loads(Path(command[command.index('--base-snapshot')+1]).read_text())
        venue = S.venue_from_folder(folder.name)
        key = f'2026-10-24|{venue}'
        payload['meetings'] = [m for m in payload['meetings'] if m['venue'] != venue]
        payload['meetings'].append({'date':'2026-10-24','venue':venue,'region':'AU'})
        payload['races'][key] = {'races_by_analyst':{'Kelvin':[{'race_number':1}]}}
        Path(command[command.index('--output-json')+1]).write_text(json.dumps(payload))
        Path(command[command.index('--output-html')+1]).write_text('html')
        return 0, 'ok'

    monkeypatch.setattr(S, 'download_live_snapshot', download)
    monkeypatch.setattr(S, 'find_meeting_dir', lambda *a: None)
    monkeypatch.setattr(S, 'run_cmd', merge)
    monkeypatch.setattr(S, 'check_data_contract', lambda _l, fs: ['dead'] if any('Dead' in f.name for f in fs) else [])
    monkeypatch.setattr(S, 'deploy_dashboard', lambda *a: {'ok':True})
    monkeypatch.setattr(S, 'verify_live', lambda *a, **k: {'ok':True})
    return log, work


def folders(tmp_path, *names):
    out = []
    for name in names:
        f = tmp_path / f'2026-10-24 {name} Race 1-1'
        f.mkdir()
        out.append(f)
    return out


def test_dead_and_broken_meetings_do_not_block_healthy_or_hkjc(snapshot_fixture, tmp_path):
    log, work = snapshot_fixture
    candidates = folders(tmp_path, 'Alpha', 'Dead', 'Broken', 'Gamma')
    assert S.step_dashboard(log, candidates, [], isolate_failures=True,
                            recover_unpublished=False, retain_intermediates=False)
    validation = log.data['dashboard_validation']
    assert set(validation['meetings']) == {'2026-10-25|ShaTin', '2026-10-24|Alpha', '2026-10-24|Gamma'}
    assert set(log.data['publication_rejected']) == {candidates[1].name, candidates[2].name}
    assert len(list(work.glob('merge-*.json'))) == 1
    assert len(list(work.glob('merge-*.html'))) == 1


def test_closed_queue_never_auto_sweeps_unsubmitted_local_meetings(snapshot_fixture, tmp_path, monkeypatch):
    log, _ = snapshot_fixture
    recovered = Mock(side_effect=AssertionError('must not inspect mutable local inputs'))
    monkeypatch.setattr(S, 'unpublished_local_meetings', recovered)
    assert S.step_dashboard(log, folders(tmp_path, 'Alpha'), [],
                            recover_unpublished=False, isolate_failures=True)
    recovered.assert_not_called()


def test_pending_analysis_is_excluded_only_in_isolation_mode(snapshot_fixture, tmp_path):
    log, _ = snapshot_fixture
    candidates = folders(tmp_path, 'Pending', 'Alpha')
    (candidates[0] / S.ANALYSIS_PENDING).touch()
    assert S.step_dashboard(log, candidates, [], recover_unpublished=False, isolate_failures=True)
    assert candidates[0].name in log.data['publication_rejected']
    assert '2026-10-24|Alpha' in log.data['dashboard_validation']['meetings']


def test_morning_keeps_one_batch_and_never_starts_background_publisher(tmp_path, monkeypatch):
    monkeypatch.setenv('WC_AU_SCHED_LOG_DIR', str(tmp_path / 'logs'))
    log = S.RunLog('morning', S.date(2026,10,24), tmp_path / 'run.json', notify=False)
    monkeypatch.setattr(S, 'dashboard_au_meetings', lambda *a: [])
    monkeypatch.setattr(S, 'step_prediction_evidence', lambda *a: True)
    publish = Mock(return_value=True)
    monkeypatch.setattr(S, 'step_dashboard', publish)
    monkeypatch.setattr(S, 'step_mirror_reports', lambda *a: None)
    monkeypatch.setattr(S, 'push_run_summary', lambda *a: None)
    args = SimpleNamespace(skip_review=True, skip_refresh=True, skip_analysis=True,
                           skip_deploy=True, max_meetings=0, rounds=1, round_gap=0)
    assert S.run_morning(log, args, S.date(2026,10,24)) == 0
    publish.assert_called_once()
    assert publish.call_args.kwargs['isolate_failures'] is True


def test_only_complete_meetings_trigger_evening_publication_callback(tmp_path, monkeypatch):
    monkeypatch.setenv('WC_AU_SCHED_LOG_DIR', str(tmp_path / 'logs'))
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path / 'run.json', notify=False)
    candidates = folders(tmp_path, 'Alpha', 'Beta')
    monkeypatch.setattr(S, 'api_next_events', lambda *a: [])
    monkeypatch.setattr(S, 'events_by_day', lambda *a: {'2026-10-24':{'Alpha':{},'Beta':{}}})
    monkeypatch.setattr(S, 'api_day_meetings', lambda *a, **k: [])
    monkeypatch.setattr(S, 'fetch_date_index', lambda *a: {
        'alpha':{'meetingId':'1','races':['1']}, 'beta':{'meetingId':'2','races':['2']}})
    monkeypatch.setattr(S, 'analyse_one_meeting', Mock(side_effect=[(candidates[0],True,True),
                                                                  (candidates[1],False,True)]))
    callback = Mock()
    S.step_analyse_next_day(log, S.date(2026,10,23), rounds=1, on_complete=callback)
    callback.assert_called_once_with(candidates[0])


def test_callback_failure_does_not_stop_next_meeting(tmp_path, monkeypatch):
    monkeypatch.setenv('WC_AU_SCHED_LOG_DIR', str(tmp_path / 'logs'))
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path / 'run.json', notify=False)
    candidates = folders(tmp_path, 'Alpha', 'Beta')
    monkeypatch.setattr(S, 'api_next_events', lambda *a: [])
    monkeypatch.setattr(S, 'events_by_day', lambda *a: {'2026-10-24':{'Alpha':{},'Beta':{}}})
    monkeypatch.setattr(S, 'api_day_meetings', lambda *a, **k: [])
    monkeypatch.setattr(S, 'fetch_date_index', lambda *a: {
        'alpha':{'meetingId':'1','races':['1']}, 'beta':{'meetingId':'2','races':['2']}})
    monkeypatch.setattr(S, 'analyse_one_meeting', Mock(side_effect=[(f,True,True) for f in candidates]))
    callback = Mock(side_effect=[RuntimeError('worker crashed'),None])
    assert S.step_analyse_next_day(log, S.date(2026,10,23), rounds=1,
                                   on_complete=callback) == candidates
    assert callback.call_count == 2
    assert candidates[0].name in log.data['publication_rejected']


@pytest.mark.parametrize('enabled', [True, False])
def test_evening_uses_background_callbacks_or_explicit_batch_rollback(tmp_path, monkeypatch, enabled):
    import au_progressive_publish as P
    monkeypatch.setenv('WC_AU_PROGRESSIVE_PUBLISH', '1' if enabled else '0')
    monkeypatch.setenv('WC_AU_SCHED_LOG_DIR', str(tmp_path/'logs'))
    log = S.RunLog('evening', S.date(2026,10,23), tmp_path/'run.json', notify=False)
    candidates = folders(tmp_path, 'Alpha', 'Beta')
    publisher = Mock()
    publisher.finish.return_value = {'published':{'Alpha':'1'},'complete':True}
    factory = Mock(return_value=publisher)
    monkeypatch.setattr(P, 'ProgressivePublisher', factory)
    analyse = Mock(return_value=candidates)
    dashboard = Mock(return_value=True)
    monkeypatch.setattr(S, 'step_analyse_next_day', analyse)
    monkeypatch.setattr(S, 'step_dashboard', dashboard)
    monkeypatch.setattr(S, 'step_prediction_evidence', lambda *a: True)
    monkeypatch.setattr(S, 'step_mirror_reports', lambda *a: None)
    monkeypatch.setattr(S, 'push_run_summary', lambda *a: None)
    monkeypatch.setattr(S, 'close_browser', lambda *a: None)
    args = SimpleNamespace(skip_review=True, skip_results_ingest=True, skip_speed_shadow=True,
                           skip_deploy=False, skip_analysis=False, max_meetings=0,
                           rounds=1, round_gap=0)
    assert S.run_evening(log,args,S.date(2026,10,23)) == 0
    if enabled:
        factory.assert_called_once()
        assert analyse.call_args.kwargs['on_complete'] == publisher.submit
        publisher.finish.assert_called_once()
        publisher.abort.assert_called_once()
        dashboard.assert_not_called()
    else:
        factory.assert_not_called()
        dashboard.assert_called_once()
        assert dashboard.call_args.kwargs['isolate_failures']
