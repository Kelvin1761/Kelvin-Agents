from __future__ import annotations

import json

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.reports import daily_report


def test_start_marker_preserves_previous_source_failures(tmp_path, monkeypatch):
    from tennis_wc.ingestion.raw_response_store import store_raw_response
    configure_test_db(tmp_path, monkeypatch); init_db()
    old_id = store_raw_response('tennis_wc_pipeline', '/run-daily', {'date': '2026-06-01'},
                               {'errors': [{'source': 'odds', 'error': 'failed'}]},
                               500, 'run_daily_source_errors', '2026-06-01')
    daily_report.clear_pipeline_source_errors('2026-06-01')
    with get_connection() as c:
        rows = c.execute("SELECT id,response_json FROM raw_api_responses WHERE entity_type='run_daily_source_errors' ORDER BY id").fetchall()
    assert len(rows) == 2 and rows[0]['id'] == old_id
    assert json.loads(rows[0]['response_json'])['errors'][0]['error'] == 'failed'
    assert json.loads(rows[1]['response_json'])['errors'] == []


def test_prop_failure_is_renderable_but_blocks_readiness_and_closes_connection(tmp_path, monkeypatch):
    from tennis_wc.pipeline_readiness import _pipeline_reasons
    configure_test_db(tmp_path, monkeypatch); init_db()
    seen = []
    def fail(match_date, conn):
        seen.append(conn)
        raise RuntimeError('pricing test failure')
    monkeypatch.setattr(daily_report, '_build_ace_prop_data', fail)
    data = daily_report._ace_prop_data('2026-06-01')
    assert data['error'] == 'pricing test failure'
    assert daily_report.latest_prop_pricing_error('2026-06-01') == 'pricing test failure'
    reasons = _pipeline_reasons({'source_errors': [{'source': 'prop_pricing', 'error': data['error']}]})
    assert any('prop_pricing' in reason for reason in reasons)
    import sqlite3
    import pytest
    with pytest.raises(sqlite3.ProgrammingError, match='closed'):
        seen[0].execute('SELECT 1')
    # A successful empty board is recorded as a healthy observation, not an error.
    monkeypatch.setattr(daily_report, '_build_ace_prop_data', lambda date, c: {'error': None, 'boards': []})
    assert daily_report._ace_prop_data('2026-06-01')['error'] is None
    assert daily_report.latest_prop_pricing_error('2026-06-01') is None
    with get_connection() as c:
        assert c.execute("SELECT COUNT(*) FROM raw_api_responses WHERE entity_type='prop_pricing_status'").fetchone()[0] == 2
