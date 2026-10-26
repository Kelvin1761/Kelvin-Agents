from __future__ import annotations

import json
import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.database.history_audit import audit_legacy_history,quarantine_history_plan


def seed(c):
    for pid,name in ((1,'Alpha Player'),(2,'Beta Player'),(3,'Gamma Player')):
        c.execute("INSERT INTO players(id,name,tour,source_provider,created_at,updated_at) VALUES (?,?,'ATP','test','now','now')",(pid,name))
        c.execute("INSERT INTO provider_entities(provider_name,entity_type,provider_entity_id,internal_entity_id,entity_name,confidence_score,created_at,updated_at) VALUES ('tennismylife_history','player',?,?,?,1,'now','now')",(str(pid),pid,name))
    raw=[{'tourney_id':'2026-319','match_num':'26','winner_id':'1','loser_id':'3',
          'winner_name':'Alpha Player','loser_name':'Gamma Player','round':'SF','tourney_date':'20260720'}]
    c.execute("INSERT INTO raw_api_responses(id,provider_name,endpoint,request_url_hash,request_params_json,response_json,status_code,fetched_at,entity_type,created_at) VALUES (11,'tennismylife_history','/history','hash','{}',?,200,'2026-10-25T00:00:00Z','match_history','now')",(json.dumps(raw),))
    c.execute("""INSERT INTO player_match_history
        (provider_match_id,player_id,opponent_id,tour,match_date,tournament_external_id,tournament_level,
         round,format,won,ace_count,source_provider,raw_response_id,created_at)
        VALUES ('ATP-2026-319-26-winner',1,2,'ATP','2026-07-20','2026-319','ATP_250','QF','BO3',1,13,
                'tennismylife_history',11,'2026-07-22T00:00:00Z')""")


def test_audit_proves_mixed_source_context_without_reconstructing_old_stats(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c)
        report=audit_legacy_history(c)
        assert report['counts']['proven_mismatches']==1
        assert report['cases'][0]['source_opponent_id']==3
        assert 'source_opponent_differs_from_stored_header' in report['cases'][0]['issues']
        assert quarantine_history_plan(c,report,'2026-10-27T00:00:00Z')==1
        row=c.execute('SELECT * FROM player_match_history').fetchone()
        assert row['opponent_id']==2 and row['ace_count']==13 and row['history_status']=='DISPUTED'
        assert c.execute('SELECT COUNT(*) FROM history_observations').fetchone()[0]==1
        assert audit_legacy_history(c)['counts'].get('proven_mismatches',0)==0


def test_missing_raw_evidence_is_unknown_and_stale_plans_cannot_apply(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c);plan=audit_legacy_history(c)
        c.execute('UPDATE player_match_history SET raw_response_id=999')
        assert audit_legacy_history(c)['counts'].get('proven_mismatches',0)==0
        with pytest.raises(ValueError,match='stale'):
            quarantine_history_plan(c,plan,'2026-10-27T00:00:00Z')
        assert c.execute('SELECT history_status FROM player_match_history').fetchone()[0]=='ACTIVE'


def test_any_changed_history_fact_invalidates_quarantine_plan(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c);plan=audit_legacy_history(c)
        c.execute('UPDATE player_match_history SET ace_count=99')
        with pytest.raises(ValueError,match='stale'):
            quarantine_history_plan(c,plan,'2026-10-27T00:00:00Z')


def test_history_observations_cannot_be_rewritten_or_deleted(tmp_path,monkeypatch):
    import sqlite3
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c);quarantine_history_plan(c,audit_legacy_history(c),'2026-10-27T00:00:00Z')
        for sql in ('DELETE FROM history_observations',"UPDATE history_observations SET observation_kind='safe'"):
            with pytest.raises(sqlite3.IntegrityError,match='append-only'):
                c.execute(sql)
