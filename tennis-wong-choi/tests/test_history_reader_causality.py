from __future__ import annotations

from datetime import date
import pytest

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db


def _history(c, *, key, opponent=2, ingested='2026-06-02T08:00:00Z', day='2026-06-01'):
    c.execute('''INSERT INTO player_match_history
        (provider_match_id,player_id,opponent_id,tour,match_date,tournament_external_id,
         tournament_level,round,format,won,source_provider,created_at,surface,ace_count,
         double_fault_count,hold_rate,break_rate,raw_response_id)
        VALUES (?,1,?,'ATP',?,'event','ATP_250','Final','BO3',1,'test',?,'hard',8,3,.8,.2,0)''',
        (key,opponent,day,ingested))


def _calculate(kind):
    stamp=date(2026,6,5)
    if kind=='big':
        from tennis_wc.features.big_match import calculate_big_match_stats
        return calculate_big_match_stats(1,'hard',stamp,'LAST_52_WEEKS',persist=False)
    if kind=='format':
        from tennis_wc.features.bo_format import calculate_bo_format_stats
        return calculate_bo_format_stats(1,'BO3','hard',stamp,'LAST_52_WEEKS',persist=False)
    if kind=='round':
        from tennis_wc.features.round_performance import calculate_round_stats
        return calculate_round_stats(1,'Final','ATP_250','hard',stamp,'LAST_52_WEEKS',persist=False)
    if kind=='level':
        from tennis_wc.features.tournament_level import calculate_tournament_level_stats
        return calculate_tournament_level_stats(1,'ATP_250','hard',stamp,'LAST_52_WEEKS',persist=False)
    if kind=='pressure':
        from tennis_wc.features.pressure import calculate_pressure_stats
        return calculate_pressure_stats(1,'hard',stamp,'LAST_52_WEEKS')
    if kind=='h2h':
        from tennis_wc.features.head_to_head import calculate_head_to_head_stats
        return calculate_head_to_head_stats(1,2,'hard',stamp)
    if kind=='rank':
        from tennis_wc.features.opponent_rank_buckets import calculate_player_rank_bucket_stats
        return calculate_player_rank_bucket_stats(1,'hard',stamp,'LAST_52_WEEKS',persist=False)['UNKNOWN']
    from tennis_wc.features.opponent_elo_buckets import calculate_player_elo_bucket_stats
    return calculate_player_elo_bucket_stats(1,'hard',stamp,'LAST_52_WEEKS')['UNKNOWN']


@pytest.mark.parametrize('kind',['big','format','round','level','pressure','h2h','rank','elo'])
def test_same_event_late_ingestion_cannot_enter_form_features(tmp_path,monkeypatch,kind):
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _history(c,key='known')
        _history(c,key='future',ingested='2026-06-10T08:00:00Z')
    assert _calculate(kind)['matches']==1


def test_double_fault_profile_uses_the_same_event_guard(tmp_path,monkeypatch):
    from tennis_wc.props.player_model import count_profile
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _history(c,key='known')
        _history(c,key='future',ingested='2026-06-10T08:00:00Z')
        profile=count_profile(c,1,'2026-06-05','double_fault_count')
        assert profile.n==1


def test_self_history_is_excluded_without_erasing_valid_result_rows(tmp_path,monkeypatch):
    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.ace_model import player_ace_profile
    from tennis_wc.props.player_model import count_profile
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _history(c,key='valid')
        _history(c,key='self',opponent=1)
        assert serve_return_profile(c,1,'2026-06-05').matches==1
        assert player_ace_profile(c,1,'2026-06-05',None).n==1
        assert count_profile(c,1,'2026-06-05','double_fault_count').n==1
        assert c.execute('SELECT COUNT(*) FROM player_match_history').fetchone()[0]==2


def test_invalid_measurements_are_missing_not_clamped_or_counted(tmp_path,monkeypatch):
    from tennis_wc.features.serve_return import serve_return_profile
    from tennis_wc.props.ace_model import player_ace_profile
    from tennis_wc.props.player_model import count_profile
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _history(c,key='valid')
        _history(c,key='bad',opponent=3)
        c.execute("UPDATE player_match_history SET hold_rate=1.4,break_rate=-.2,ace_count=-1,double_fault_count=-3 WHERE provider_match_id='bad'")
        profile=serve_return_profile(c,1,'2026-06-05')
        assert profile.matches==1 and profile.serve['hold_rate']==.8
        assert player_ace_profile(c,1,'2026-06-05',None).n==1
        assert count_profile(c,1,'2026-06-05','double_fault_count').n==1
        # The source outcome is retained. Only unusable measurements are ignored.
        c.commit()
        assert _calculate('round')['matches']==2
        assert c.execute("SELECT won FROM player_match_history WHERE provider_match_id='bad'").fetchone()[0]==1


def test_rate_validation_keeps_unknown_fields_distinct_from_zero():
    from tennis_wc.features.history_values import clean_history_row
    row=clean_history_row({'hold_rate':1.4,'break_rate':0,'first_serve_points_won_pct':float('inf'),
        'double_fault_count':-1,'break_points_saved':4,'break_points_faced':3,'won':1})
    assert row['hold_rate'] is None and row['first_serve_points_won_pct'] is None
    assert row['break_rate']==0 and row['double_fault_count'] is None
    assert row['break_points_saved'] is None and row['break_points_faced'] is None
    assert row['won']==1


def test_ingestion_cutoff_compares_instants_across_offsets(tmp_path,monkeypatch):
    from tennis_wc.props.player_model import count_profile
    configure_test_db(tmp_path,monkeypatch);init_db()
    with get_connection() as c:
        _history(c,key='before',ingested='2026-06-05T00:30:00+02:00')
        _history(c,key='after',ingested='2026-06-04T23:30:00-02:00')
        profile=count_profile(c,1,'2026-06-05','double_fault_count')
        assert profile.n==1
        assert c.execute('SELECT provider_match_id FROM player_match_history WHERE id=?',profile.history_ids).fetchone()[0]=='before'
