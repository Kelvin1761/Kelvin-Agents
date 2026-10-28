from __future__ import annotations

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.validation.current_slate import audit_current_slate


def _match(c,mid,date,a=1,b=2,quoted=True):
    c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at) VALUES (?,?,'ATP',?,1,?,?,'R1','test','now','now')",(mid,str(mid),date,a,b))
    if quoted:
        c.execute("INSERT INTO odds_snapshots(event_id,match_id,bookmaker,market,player_a_odds,player_b_odds,source_provider,raw_response_id,fetched_at,created_at) VALUES (?,?, 'Test','match_winner',1.9,1.9,'test',1,'now','now')",(str(mid),mid))


def test_only_current_priced_integrity_errors_hold_today_and_are_audited(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _match(c,1,'2025-01-01',a=1,b=1)
        _match(c,2,'2026-06-01')
        _match(c,3,'2026-06-01')
        _match(c,4,'2026-06-01',a=1,b=1,quoted=False)
        c.execute("INSERT INTO match_results(match_id,winner_player_id,source_provider,created_at) VALUES (2,99,'test','now')")
        report=audit_current_slate(c,'2026-06-01')
        assert report['checked']==2
        assert report['held']==[{'match_id':2,'issues':['winner_not_in_fixture']}]
        assert c.execute('SELECT fixture_status FROM matches WHERE id=2').fetchone()[0]=='ACTIVE'
        audit_current_slate(c,'2026-06-01',apply=True)
        assert c.execute('SELECT fixture_status FROM matches WHERE id=2').fetchone()[0]=='DISPUTED'
        assert c.execute('SELECT fixture_status FROM matches WHERE id=3').fetchone()[0]=='ACTIVE'
        assert c.execute('SELECT COUNT(*) FROM match_results WHERE match_id=2').fetchone()[0]==1
        audit_current_slate(c,'2026-06-01',apply=True)
        assert c.execute("SELECT COUNT(*) FROM fixture_observations WHERE observation_kind='CURRENT_SLATE_INTEGRITY_HOLD'").fetchone()[0]==1


def test_current_slate_hold_is_a_critical_readiness_failure():
    from tennis_wc.pipeline_readiness import _pipeline_reasons
    reasons=_pipeline_reasons({'matches_analysed':1,'valid_feature_snapshots':1,
        'source_errors':[{'source':'slate_integrity','error':'fixture held'}]})
    assert any('slate_integrity' in reason for reason in reasons)
