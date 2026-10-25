from datetime import datetime
import importlib.util
import json
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("health_log_scan", Path(__file__).parents[1] / "health_log_scan.py")
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)
CUTOFF = datetime(2026, 10, 23)


def test_replayed_old_json_uses_attempt_completion_time(tmp_path):
    attempt = tmp_path / 'tennis/2026-09-01/daily/attempt-1.json'
    attempt.parent.mkdir(parents=True)
    attempt.write_text(json.dumps({'completed_at': '2026-09-01T09:00:00+11:00'}))
    line = json.dumps({'artifacts': [str(attempt)], 'detail': {'reason': 'Operation not permitted'}})
    assert scan.recent_errors([line], CUTOFF, tmp_path) == ([], 0)


def test_current_recovery_of_old_target_is_reported(tmp_path):
    line = json.dumps({'at': '2026-10-25T21:00:00+11:00', 'target_date': '2026-09-01',
                       'detail': {'reason': 'Operation not permitted'}})
    assert scan.recent_errors([line], CUTOFF, tmp_path) == ([line], 0)


def test_undated_json_does_not_inherit_previous_lines_time(tmp_path):
    lines = ['[2026-10-25T10:00:00+11:00] start', '{"error": "Operation not permitted"}']
    assert scan.recent_errors(lines, CUTOFF, tmp_path) == ([], 1)


def test_text_traceback_inherits_text_event_time(tmp_path):
    lines = ['[2026-10-25T10:00:00+11:00] start', 'Traceback (most recent call last):']
    assert scan.recent_errors(lines, CUTOFF, tmp_path) == ([lines[1]], 0)


def test_does_not_open_arbitrary_artifact_paths(tmp_path):
    elsewhere = tmp_path / 'other.json'
    elsewhere.write_text('{"completed_at":"2026-10-25T10:00:00+11:00"}')
    line = json.dumps({'artifacts': [str(elsewhere)], 'error': 'fatal'})
    assert scan.recent_errors([line], CUTOFF, tmp_path / 'runs') == ([], 1)
