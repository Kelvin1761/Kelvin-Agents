from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db


def seed(c):
    c.execute("""INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,
        player_b_id,round,source_provider,created_at,updated_at,start_time_utc)
        VALUES (1,'m','ATP','2026-07-20',1,1,2,'Q1','test','now','now','2026-07-20T12:00:00Z')""")
    c.execute("INSERT INTO tournament_levels(tournament_id,tour,level,source_provider,raw_response_id,created_at,updated_at) VALUES (1,'ATP','GRAND_SLAM','test',0,'now','now')")
    for pid in (1,2):
        for n,(day,created,ace,hold,status) in enumerate([
            ('2026-06-01','2026-06-02T00:00:00Z',3,.7,'ACTIVE'),
            ('2026-07-18','2026-07-21T00:00:00Z',50,.95,'ACTIVE'),
            ('2026-08-01','2026-08-02T00:00:00Z',60,.99,'ACTIVE'),
            ('2026-05-01','2026-05-02T00:00:00Z',70,.99,'SUPERSEDED'),
        ]):
            c.execute("""INSERT INTO player_match_history(provider_match_id,player_id,opponent_id,tour,
                match_date,tournament_external_id,tournament_level,round,format,won,ace_count,hold_rate,
                source_provider,raw_response_id,created_at,history_status)
                VALUES (?,?,?,'ATP',?,'T','ATP_250','QF','BO3',1,?,?,'test',0,?,?)""",
                (f'{pid}-{n}',pid,3,day,ace,hold,created,status))


def test_historical_report_context_excludes_future_late_and_retired_history(tmp_path,monkeypatch):
    from tennis_wc.reports.daily_report import _match_games_context
    from tennis_wc.reports.market_validation_report import _historical_ace_values
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:seed(c)
    assert _historical_ace_values(1,1)==[3.0]
    assert _historical_ace_values(1,None)==[6.0]
    context=_match_games_context(1)
    assert context['hold_a']==context['hold_b']==.7
    assert context['best_of']==3


def test_ambiguous_history_count_cannot_silently_settle_a_forecast(tmp_path,monkeypatch):
    from tennis_wc.props.settlement import _history_count
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c)
        c.execute('UPDATE player_match_history SET opponent_id=2 WHERE player_id=1')
        c.execute("UPDATE player_match_history SET match_date='2026-07-18',created_at='2026-07-19' WHERE player_id=1 AND ace_count=3")
        assert _history_count(c,1,1,'ace_count') is None
        c.execute("UPDATE player_match_history SET history_status='DISPUTED' WHERE ace_count=50")
        assert _history_count(c,1,1,'ace_count')==3
        c.execute("UPDATE player_match_history SET ace_count='bad' WHERE ace_count=3")
        assert _history_count(c,1,1,'ace_count') is None


def test_conceded_ace_profile_requires_both_source_perspectives_before_cutoff(tmp_path,monkeypatch):
    from tennis_wc.props.ace_model import player_ace_profile
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        seed(c)
        c.execute("DELETE FROM player_match_history")
        for role,pid,opp,created in [('winner',1,2,'2026-07-19T00:00:00Z'),('loser',2,1,'2026-07-21T00:00:00Z')]:
            c.execute("""INSERT INTO player_match_history(provider_match_id,player_id,opponent_id,tour,
                match_date,tournament_external_id,tournament_level,round,format,won,ace_count,
                source_provider,raw_response_id,created_at,surface)
                VALUES (?,?,?,'ATP','2026-07-18','T','ATP_250','QF','BO3',?,3,'test',0,?,'hard')""",
                ('event-'+role,pid,opp,int(role=='winner'),created))
        profile=player_ace_profile(c,1,'2026-07-20','hard',start_time='2026-07-20T12:00:00Z')
        assert profile.n==1
        assert profile.conceded_history_ids==()
        assert profile.conceded_mean is None
