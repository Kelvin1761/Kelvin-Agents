from __future__ import annotations

from conftest import configure_test_db
from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.props import settlement
from tennis_wc.props.pricing_evidence import capture_context, read_evidence, source_quality


def _seed(c):
    c.execute("INSERT INTO matches(id,provider_match_id,tour,match_date,tournament_id,player_a_id,player_b_id,round,source_provider,created_at,updated_at,start_time_utc) VALUES (1,'event','ATP','2026-06-01',1,1,2,'R1','test','now','now','2026-06-01T12:00:00Z')")
    _feature(c, 65, '2026-06-01T08:00:00Z')


def _feature(c, quality, when):
    c.execute("INSERT INTO feature_snapshots(match_id,player_id,feature_set_version,features_json,provenance_json,data_quality_score,created_at) VALUES (1,1,'test','{}','{}',?,?)", (quality, when))


def _record(c, **kwargs):
    settlement.record_prop(c, match_id=1, match_date='2026-06-01', match_label='One vs Two',
        market_key='match_total_games', line=22.5, selection='Over', side='over',
        prop_scope='match_games', subject_player_id=None, decimal_odds=1.9,
        model_prob=.6, model_prob_raw=.6, temper_strength=0, market_prob_fair=.5,
        blended_prob=.55, edge=.05, ev=.045, predicted_mean=23, stake_units=1,
        is_value=True, **kwargs)


def test_repricing_freezes_each_actual_quality_and_preserves_first_write(tmp_path, monkeypatch):
    configure_test_db(tmp_path, monkeypatch); init_db()
    monkeypatch.setattr(settlement, 'utc_now', lambda: '2026-06-01T09:00:00Z')
    with get_connection() as c:
        _seed(c); _record(c)
        first = dict(c.execute('SELECT * FROM prop_tracker').fetchone())
        assert read_evidence(first['pricing_evidence_json'])['source_quality'] == .65
        _feature(c, 90, '2026-06-01T10:00:00Z')
        assert read_evidence(c.execute('SELECT pricing_evidence_json FROM prop_tracker').fetchone()[0])['source_quality'] == .65
        monkeypatch.setattr(settlement, 'utc_now', lambda: '2026-06-01T11:00:00Z')
        _record(c)
        updated = dict(c.execute('SELECT * FROM prop_tracker').fetchone())
        evidence = read_evidence(updated['pricing_evidence_json'])
        assert evidence['source_quality'] == .9
        assert evidence['features'][0]['id'] != read_evidence(first['pricing_evidence_json'])['features'][0]['id']
        assert updated['recorded_at'] == first['recorded_at']
        assert updated['priced_at'] == evidence['priced_at'] == '2026-06-01T11:00:00Z'
        monkeypatch.setattr(settlement, 'utc_now', lambda: '2026-06-01T13:00:00Z')
        _feature(c, 0, '2026-06-01T13:00:00Z'); _record(c)
        assert c.execute('SELECT pricing_evidence_json FROM prop_tracker').fetchone()[0] == updated['pricing_evidence_json']
        c.execute("UPDATE prop_tracker SET result_status='WON'")
        monkeypatch.setattr(settlement, 'utc_now', lambda: '2026-06-01T11:30:00Z')
        _record(c)
        assert c.execute('SELECT pricing_evidence_json FROM prop_tracker').fetchone()[0] == updated['pricing_evidence_json']


def test_profiles_are_captured_values_not_later_history_counts():
    context = {'fixture': {'player_a_id': 1, 'player_b_id': 2},
               'profiles': {'aces': {'1': {'n': 12, 'history_ids': [1, 2]},
                                      '2': {'n': 9, 'history_ids': [3, 4]}}}}
    assert source_quality(context, 'player_aces', 1) == .6
    assert source_quality(context, 'player_double_faults', 1) is None
    assert read_evidence(None) is None
    assert read_evidence('{invalid') is None


def test_evidence_readers_do_not_borrow_rebuilt_quality_or_late_labels(tmp_path, monkeypatch):
    from tennis_wc.props.calibration import family_reliability
    configure_test_db(tmp_path, monkeypatch); init_db()
    monkeypatch.setattr(settlement, 'utc_now', lambda: '2026-06-01T09:00:00Z')
    with get_connection() as c:
        _seed(c); _record(c)
        c.execute("UPDATE prop_tracker SET result_status='WON',profit_loss_units=.9,settled_at='2026-06-02T18:00:00Z'")
        _feature(c, 0, '2026-07-01T08:00:00Z')
        assert settlement.model_vs_market_scorecard(c, as_of_date='2026-06-02')['settled'] == 0
        assert settlement.model_vs_market_scorecard(c, as_of_date='2026-06-03')['settled'] == 1
        assert family_reliability(c, 'match_total_games', '2026-06-02').settled == 0
        assert family_reliability(c, 'match_total_games', '2026-06-03').settled == 1
        assert settlement.prop_roi_report(c, as_of_date='2026-06-02')['overall']['settled'] == 0
        assert settlement.prop_roi_report(c, as_of_date='2026-06-03')['by_data_quality']['65%+']['settled'] == 1
        # A legacy row remains in the raw return report without invented quality.
        c.execute('UPDATE prop_tracker SET pricing_evidence_json=NULL,priced_at=NULL')
        assert family_reliability(c, 'match_total_games', '2026-06-03').settled == 0
        report = settlement.prop_roi_report(c)
        assert report['overall']['settled'] == 1
        assert report['by_data_quality']['UNKNOWN']['settled'] == 1
        assert report['formal_profile']['settled'] == 0


def test_reliability_database_errors_are_visible(tmp_path, monkeypatch):
    from tennis_wc.props.calibration import family_reliability
    import sqlite3
    configure_test_db(tmp_path, monkeypatch); init_db()
    with get_connection() as c:
        c.execute('DROP TABLE prop_tracker')
        import pytest
        with pytest.raises(sqlite3.OperationalError):
            family_reliability(c, 'match_total_games', '2026-06-03')
