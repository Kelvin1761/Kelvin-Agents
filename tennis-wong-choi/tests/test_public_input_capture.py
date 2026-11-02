from contextlib import closing
import json
import sqlite3
from unittest.mock import patch

import pytest

from tennis_wc import research_public_capture as capture
from tennis_wc.research_indexed_generations import _native_schema, file_sha


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'source.sqlite'
    with closing(sqlite3.connect(path)) as conn:
        conn.row_factory = sqlite3.Row
        _native_schema(conn)
        conn.execute("INSERT INTO players (id,name,tour,source_provider,raw_response_id,created_at,updated_at) "
                     "VALUES (1,'Public Player','ATP','test',1,'2000-01-01','2000-01-01')")
        conn.execute("INSERT INTO raw_api_responses (id,provider_name,endpoint,request_url_hash,"
                     "request_params_json,response_json,status_code,fetched_at,created_at) "
                     "VALUES (1,'test','SECRET-ENDPOINT','secret','secret','SECRET-BODY',200,'2000','2000')")
        conn.execute("INSERT INTO provider_entities (provider_name,entity_type,provider_entity_id,"
                     "internal_entity_id,entity_name,confidence_score,created_at,updated_at) VALUES "
                     "('test','fixture','secret',9,'SECRET-FIXTURE',1,'2000','2000')")
        conn.execute("INSERT INTO player_aliases VALUES ('public player',1,'test','2000')")
        conn.execute("INSERT INTO rankings_history (player_id,ranking_date,tour,rank,source_provider,"
                     "raw_response_id,created_at) VALUES (1,'2026-01-01','ATP',50,'test',999,'2000')")
        conn.commit()
    return path


def read_capture(path):
    with closing(sqlite3.connect(path)) as conn:
        return json.loads(conn.execute('SELECT metadata FROM public_capture_manifest').fetchone()[0])


def test_public_capture_is_sealed_and_does_not_read_or_copy_private_fields(source, tmp_path):
    destination = tmp_path/'capture.sqlite'
    before = file_sha(source)
    real_connect = sqlite3.connect
    reads = []

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)

        def authorizer(action, table, column, database, trigger):
            if action == sqlite3.SQLITE_READ and database == 'live':
                reads.append((table, column))
                if table == 'raw_api_responses' and column not in capture.RAW_HEADER_COLUMNS:
                    return sqlite3.SQLITE_DENY
                if table not in {*capture.INPUT_TABLES, 'raw_api_responses', 'sqlite_master'}:
                    return sqlite3.SQLITE_DENY
            return sqlite3.SQLITE_OK

        conn.set_authorizer(authorizer)
        return conn

    with patch.object(capture.sqlite3, 'connect', side_effect=connect):
        result = capture.capture_public_inputs(destination, source=source)
    assert file_sha(source) == before
    assert result['qualification'] == 'UNQUALIFIED_RESEARCH_ONLY'
    assert result['started_at'] <= result['captured_at'] <= result['available_at']
    assert 0 < result['source_read_seconds'] < 5
    assert destination.stat().st_mode & 0o222 == 0
    assert result['sha256'] == file_sha(destination)
    assert result['missing_raw_headers'] == 1
    assert ('raw_api_responses', 'response_json') not in reads
    data = destination.read_bytes()
    for secret in (b'SECRET-ENDPOINT', b'SECRET-BODY', b'SECRET-FIXTURE'):
        assert secret not in data
    with closing(real_connect(destination)) as conn:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert names == {*capture.INPUT_TABLES, 'capture_raw_headers', 'public_capture_manifest'}
        assert conn.execute('SELECT COUNT(*) FROM provider_entities').fetchone()[0] == 0
        assert conn.execute('SELECT * FROM capture_raw_headers WHERE raw_response_id=999').fetchone() == (999,None,1)
        assert conn.execute('PRAGMA application_id').fetchone()[0] == capture.CAPTURE_ID
    # Appending to a mutable source cannot silently change the captured ranks.
    with closing(real_connect(source)) as conn:
        conn.execute('UPDATE rankings_history SET rank=1'); conn.commit()
    with closing(real_connect(destination)) as conn:
        assert conn.execute('SELECT rank FROM rankings_history').fetchone()[0] == 50
    assert read_capture(destination)['public_counts'] == result['public_counts']


def test_timeout_leaves_no_destination_and_releases_lock(source, tmp_path):
    destination = tmp_path/'timeout.sqlite'
    with pytest.raises(TimeoutError):
        capture.capture_public_inputs(destination, source=source, deadline_seconds=1e-9)
    assert not destination.exists()
    with closing(sqlite3.connect(source, timeout=0.1)) as conn:
        conn.execute('BEGIN EXCLUSIVE'); conn.rollback()


def test_locked_source_fails_promptly_without_empty_artifact(source, tmp_path):
    with closing(sqlite3.connect(source)) as blocker:
        blocker.execute('BEGIN EXCLUSIVE')
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            capture.capture_public_inputs(tmp_path/'locked.sqlite', source=source)
        blocker.rollback()
    assert not (tmp_path/'locked.sqlite').exists()


@pytest.mark.parametrize('seconds', [0,-1,5.1,float('nan')])
def test_invalid_deadline_refused(source, tmp_path, seconds):
    with pytest.raises(ValueError, match='deadline'):
        capture.capture_public_inputs(tmp_path/'bad.sqlite', source=source, deadline_seconds=seconds)


def test_unknown_public_column_is_not_exported(source, tmp_path):
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('ALTER TABLE players ADD COLUMN private_notes TEXT'); conn.commit()
    with pytest.raises(ValueError, match='unreviewed'):
        capture.capture_public_inputs(tmp_path/'bad.sqlite', source=source)
    assert not (tmp_path/'bad.sqlite').exists()


def test_missing_required_table_fails_closed(source, tmp_path):
    with closing(sqlite3.connect(source)) as conn:
        conn.execute('DROP TABLE rankings_history'); conn.commit()
    with pytest.raises(ValueError, match='required public'):
        capture.capture_public_inputs(tmp_path/'bad.sqlite', source=source)


def test_missing_optional_tables_are_explicit(source, tmp_path):
    with closing(sqlite3.connect(source)) as conn:
        for table in capture.OPTIONAL_TABLES: conn.execute(f'DROP TABLE {table}')
        conn.commit()
    result = capture.capture_public_inputs(tmp_path/'capture.sqlite', source=source)
    assert set(result['missing_optional_tables']) == capture.OPTIONAL_TABLES


def test_existing_destination_never_overwritten(source, tmp_path):
    destination = tmp_path/'existing'; destination.write_text('keep')
    with pytest.raises(ValueError, match='new separate'):
        capture.capture_public_inputs(destination, source=source)
    assert destination.read_text() == 'keep'


def test_source_replacement_during_capture_refused(source, tmp_path):
    original = capture._origin(source)
    with patch.object(capture, '_origin', side_effect=[original,[0,0]]):
        with pytest.raises(ValueError, match='replaced'):
            capture.capture_public_inputs(tmp_path/'bad.sqlite', source=source)
    assert not (tmp_path/'bad.sqlite').exists()


def test_wal_writer_cannot_mix_two_public_input_states(source, tmp_path):
    real_connect = sqlite3.connect
    keeper = real_connect(source)
    keeper.execute('PRAGMA journal_mode=WAL')
    keeper.execute('UPDATE players SET name=name'); keeper.commit()
    changed = []

    def connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)

        def trace(sql):
            if sql.startswith('CREATE TABLE main.rankings_history'):
                with closing(real_connect(source)) as writer:
                    writer.execute("UPDATE players SET name='New Public Player'")
                    writer.execute('UPDATE rankings_history SET rank=1')
                    writer.commit()
                changed.append(True)

        conn.set_trace_callback(trace)
        return conn

    try:
        with patch.object(capture.sqlite3, 'connect', side_effect=connect):
            result = capture.capture_public_inputs(tmp_path/'capture.sqlite', source=source)
    finally:
        keeper.close()
    assert changed == [True]
    with closing(real_connect(result['path'])) as conn:
        assert conn.execute('SELECT name FROM players').fetchone()[0] == 'Public Player'
        assert conn.execute('SELECT rank FROM rankings_history').fetchone()[0] == 50


def test_captured_revision_pins_history_and_ranks_while_source_appends(source, tmp_path, monkeypatch):
    from tennis_wc.research_indexed_generations import build_public_snapshot, ShadowGenerationRegistry
    from tennis_wc.database.db import get_history_connection, get_history_scope
    from tennis_wc.research_elo_generations import utc_now
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///'+str(source))
    saved = capture.capture_public_inputs(tmp_path/'capture.sqlite', source=source)
    revision = build_public_snapshot(tmp_path/'revision.sqlite', source=tmp_path/'capture.sqlite',
        source_receipts=[dict(sha256=saved['sha256'],captured_at=saved['available_at'])])
    reg = ShadowGenerationRegistry.create(tmp_path/'registry.sqlite')
    key = reg.register(tmp_path/'revision.sqlite'); reg.activate(key,reason='test only')
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("UPDATE players SET name='Changed Public Player'")
        conn.execute('UPDATE rankings_history SET rank=1')
        conn.commit()
    with reg.native_scope(knowledge_at=utc_now()):
        conn = get_history_connection()
        assert conn.execute('SELECT name FROM players').fetchone()[0] == 'Public Player'
        assert conn.execute('SELECT rank FROM rankings_history').fetchone()[0] == 50
        assert get_history_scope()['qualification'] == 'UNQUALIFIED_RESEARCH_ONLY'
        assert conn.execute('SELECT COUNT(*) FROM raw_api_responses').fetchone()[0] == 1
    assert revision['source_mode'] == 'public_capture'
    # Header pinning deliberately does not pretend to verify a raw body.
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("UPDATE raw_api_responses SET response_json='different body' WHERE id=1"); conn.commit()
    with reg.native_scope(knowledge_at=utc_now()):
        assert get_history_scope()['qualification'] == 'UNQUALIFIED_RESEARCH_ONLY'
    with closing(sqlite3.connect(source)) as conn:
        conn.execute("UPDATE raw_api_responses SET fetched_at='changed' WHERE id=1"); conn.commit()
    with pytest.raises(ValueError,match='raw header changed'):
        with reg.native_scope(knowledge_at=utc_now()): pass
    assert get_history_scope() is None


def test_prepared_shadow_has_actual_receipt_without_changing_source(source, tmp_path, monkeypatch):
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(source))
    before = file_sha(source)
    result = capture.prepare_public_shadow(tmp_path,source=source)
    assert result['production_model_changed'] is False
    assert file_sha(source) == before
    assert result['capture']['available_at'] <= result['revision']['available_at'] <= result['prepared_at']
    assert result['qualification'] == 'UNQUALIFIED_RESEARCH_ONLY'
    from pathlib import Path
    assert json.loads((Path(result['registry_path']).parent/'receipt.json').read_text()) == result


def test_builder_rejects_private_columns_in_a_forged_capture(source, tmp_path):
    import os
    from pathlib import Path
    from tennis_wc.research_indexed_generations import build_public_snapshot
    saved = capture.capture_public_inputs(tmp_path/'capture.sqlite',source=source)
    path = Path(saved['path'])
    os.chmod(path,0o600)
    with closing(sqlite3.connect(path)) as conn:
        conn.execute('ALTER TABLE capture_raw_headers ADD COLUMN response_body TEXT')
        conn.commit()
    os.chmod(path,0o400)
    with pytest.raises(ValueError,match='unreviewed capture columns'):
        build_public_snapshot(tmp_path/'bad.sqlite',source=path,
            source_receipts=[dict(sha256=saved['sha256'],captured_at=saved['available_at'])])


@pytest.mark.parametrize('mode',['enabled','disabled','capture_failure'])
def test_daily_capture_runs_before_features_and_failure_stops_card(source, tmp_path, monkeypatch, mode):
    from types import SimpleNamespace
    from tennis_wc import cli
    from tennis_wc.validation import current_slate
    from tennis_wc.ingestion import ingest_wta_stats
    monkeypatch.setenv('DATABASE_URL','sqlite:///'+str(source))
    events = []
    for name in ['provider_healthcheck','clear_pipeline_source_errors','_settle_backlog_with_research',
                 'backfill_confirmed_metadata_for_date','store_raw_response','_merge_player_identities']:
        monkeypatch.setattr(cli,name,lambda *args,**kwargs: {})
    monkeypatch.setattr(current_slate,'audit_current_slate',lambda *args,**kwargs: {'held':[]})
    monkeypatch.setattr(ingest_wta_stats,'wta_serve_stats_health',
                        lambda *args,**kwargs: {'model_serve_age_days':1})

    def producer(directory, *, source):
        events.append('capture')
        if mode == 'capture_failure': raise TimeoutError('capture failed')
        return {'qualification':'UNQUALIFIED_RESEARCH_ONLY'}

    class ReachedFeatures(Exception): pass

    def features(*args):
        events.append('features')
        raise ReachedFeatures()

    monkeypatch.setattr(capture,'prepare_public_shadow',producer)
    monkeypatch.setattr(cli,'build_sportsbet_feature_snapshots_for_date',features)
    args = SimpleNamespace(date='2026-11-02',mvp_snapshot=True)
    if mode != 'disabled': args.shadow_public_input_dir=tmp_path
    with pytest.raises(TimeoutError if mode == 'capture_failure' else ReachedFeatures):
        cli.run_daily(args)
    assert events == ({'enabled':['capture','features'],'disabled':['features'],
                       'capture_failure':['capture']}[mode])
