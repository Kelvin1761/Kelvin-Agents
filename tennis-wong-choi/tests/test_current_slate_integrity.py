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


def test_current_slate_hold_does_not_withhold_the_whole_card():
    # The held fixture is quarantined and every card path reads ACTIVE only,
    # so a hold must not turn a board of 51 valid snapshots into "BROKEN".
    from tennis_wc.pipeline_readiness import _pipeline_reasons, analysis_readiness
    payload={'matches_analysed':51,'valid_feature_snapshots':51,
        'odds_coverage':{'fixtures':60,'book_fixtures':60,'priced_matches':52},
        'source_errors':[],
        'source_warnings':[{'source':'slate_integrity','warning':'held fixtures (excluded from card)'}]}
    assert _pipeline_reasons(payload)==[]
    assert analysis_readiness(payload)['publishable']
    # Even if an old caller still files it as an error, it is not critical.
    payload['source_errors']=[{'source':'slate_integrity','error':'fixture held'}]
    assert not any('slate_integrity' in r for r in _pipeline_reasons(payload))


def test_pending_tracker_rows_of_a_disputed_fixture_are_pruned(tmp_path,monkeypatch):
    configure_test_db(tmp_path,monkeypatch);init_db()
    from tennis_wc.betting.ledger import _ensure_tracking_schema,_prune_pending_disputed_fixtures
    from tennis_wc.ingestion.fixture_versions import ensure_fixture_schema
    _ensure_tracking_schema()
    with get_connection() as c:
        ensure_fixture_schema(c)
        _match(c,1,'2026-06-01');_match(c,2,'2026-06-01')
        cols={r['name'] for r in c.execute('PRAGMA table_info(clv_tracker)')}
        for sid,(mid,status) in enumerate(((1,'PENDING'),(2,'PENDING'),(2,'WIN'))):
            row={'recommendation_type':'MATCH_PREDICTION','source_id':sid,'match_id':mid,'match_date':'2026-06-01',
                 'selection_name':'x','selection_side':'player_a','market_key':'match_winner','market_name':'Match Betting',
                 'tier':'T','odds_taken':1.9,'result_status':status,
                 'recorded_at':'now','updated_at':'now'}
            row={k:v for k,v in row.items() if k in cols}
            c.execute(f"INSERT INTO clv_tracker({','.join(row)}) VALUES ({','.join('?'*len(row))})",tuple(row.values()))
        c.execute("UPDATE matches SET fixture_status='DISPUTED' WHERE id=2")
        assert _prune_pending_disputed_fixtures(c,'2026-06-01')==1
        left=c.execute('SELECT match_id,result_status FROM clv_tracker ORDER BY match_id,result_status').fetchall()
        assert [tuple(r) for r in left]==[(1,'PENDING'),(2,'WIN')]
