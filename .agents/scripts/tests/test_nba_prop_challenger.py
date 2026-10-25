from copy import deepcopy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]/'nba_ml'))
import nba_prop_challenger as challenger


def record(i=0, stat='PTS'):
    high = bool(i % 2)
    line = 10
    values = [11]*8+[6]*2 if high else [12]*9+[5]
    return {'contract': challenger.evidence.CONTRACT,
            'key': [f'2026-01-{1+i%10:02}', f'G{i%25}', f'Player{i}', stat.lower(), line, 'over'],
            'prop': stat, 'available_at': '2026-01-01T00:00:00+00:00', 'eligible_80_80': True,
            'inputs': {'l10_values': values, 'l10_dates': [f'2025-12-{d}' for d in range(29, 19, -1)],
                       'l10_minutes': [30]*10, 'opportunity': {k: .3+.1*high for k in
                           challenger.OPPORTUNITY[stat]+challenger.OPPONENT[stat]}},
            'feature_evidence': {'source': {'tip_off': '2026-01-02T00:00:00+00:00'}},
            'baseline': {'model_id': 'calibrated:test', 'probability': .7, 'price': 1.6},
            'target': {'y': int(high), 'available_at': '2026-01-11T04:00:00+00:00'}}


def future(i=999, stat='PTS'):
    row = record(i, stat)
    row.update(available_at='2026-02-01T00:00:00+00:00')
    row['key'][0] = '2026-02-02'
    row['feature_evidence']['source']['tip_off'] = '2026-02-02T00:00:00+00:00'
    return row


def test_source_fields_price_c_outcome_and_names_cannot_enter_features():
    row = record()
    original = challenger.features(row)
    changed = deepcopy(row)
    changed['baseline'] = {'probability': .01, 'price': 100, 'model_id': 'changed'}
    changed['target']['y'] = 1-row['target']['y']
    changed['key'][2] = 'Other name'
    assert challenger.features(changed) == original
    assert 'potential_ast_conversion' not in challenger.columns('AST', 'full')
    assert 'usage_pct' not in challenger.columns('PTS', 'full')


@pytest.mark.parametrize('stat', ['PTS', 'REB', 'AST', 'FG3M'])
def test_fit_json_predict_and_milestone_monotonicity(stat):
    rows = [record(i, stat) for i in range(120)]
    model = challenger.fit(rows, stat, 'full')
    model = json.loads(json.dumps(model))
    row = future(stat=stat)
    probabilities = []
    for line in [1, 5, 10, 15, 25, 50]:
        row['key'][4] = line
        probabilities.append(challenger.predict(model, row))
    assert probabilities == sorted(probabilities, reverse=True)
    assert all(0 < p < 1 for p in probabilities)


def test_training_medians_do_not_consume_future_data_and_missing_is_not_zero():
    rows = [record(i) for i in range(120)]
    field = challenger.OPPORTUNITY['PTS'][0]
    for i, row in enumerate(rows):
        row['inputs']['opportunity'][field] = None if i % 3 == 0 else .4
    model = challenger.fit(rows, 'PTS', 'full')
    pos = model['columns'].index(field)
    assert model['median'][pos] == .4
    before = deepcopy(model)
    row = future()
    row['inputs']['opportunity'][field] = 1000
    challenger.predict(model, row)
    assert model == before


def test_fit_blocks_sparse_independent_data_and_missing_opportunities():
    with pytest.raises(challenger.InsufficientData):
        challenger.fit([record(i) for i in range(5)], 'PTS', 'full')
    rows = [record(i) for i in range(120)]
    for row in rows:
        row['inputs']['opportunity'] = {}
    with pytest.raises(challenger.InsufficientData):
        challenger.fit(rows, 'PTS', 'full')
    assert challenger.fit(rows, 'PTS', 'core')['training_ladders'] == 120


def test_model_rejects_unavailable_training_labels_and_wrong_constructor_order():
    model = challenger.fit([record(i) for i in range(120)], 'PTS', 'core')
    with pytest.raises(ValueError, match='unavailable'):
        challenger.predict(model, record())
    model['columns'].reverse()
    with pytest.raises(ValueError, match='order'):
        challenger.predict(model, future())


def test_study_uses_only_labels_available_before_first_snapshot(monkeypatch):
    rows = [record(i) for i in range(12)]
    for i, row in enumerate(rows):
        row['available_at'] = f'2026-01-{2+i:02}T00:00:00+00:00'
        row['key'][0] = f'2026-01-{2+i:02}'
        row['feature_evidence']['source']['tip_off'] = f'2026-01-{2+i:02}T12:00:00+00:00'
        row['target']['available_at'] = f'2026-01-{3+i:02}T00:00:00+00:00'
    seen = []
    def inspect(train, stat, arm):
        seen.append(deepcopy(train))
        raise challenger.InsufficientData('fixture')
    monkeypatch.setattr(challenger, 'fit', inspect)
    result, oof = challenger.study(rows)
    for test, train in zip(rows, seen):
        assert all(r['key'][0] < test['key'][0] and r['target']['available_at'] < test['available_at'] for r in train)
    assert not oof and result['status'] == 'awaiting_new_data'


def test_mixed_baseline_versions_are_not_pooled():
    rows = [record(), record(1)]
    rows[1]['baseline']['model_id'] = 'other_C'
    with pytest.raises(ValueError, match='mixed C'):
        challenger.study(rows)


def test_zero_native_export_is_readiness_not_a_fitted_candidate(tmp_path):
    (tmp_path/'dataset.jsonl').write_text('')
    (tmp_path/'Readiness.json').write_text(json.dumps({'contract': challenger.evidence.CONTRACT,
                                                      'source_ledger_sha256': {}}))
    rows = challenger.load_export(tmp_path)
    report, oof = challenger.study(rows)
    assert rows == oof == [] and report['deployment_eligible'] is False


def test_export_tampering_cannot_create_training_examples(tmp_path):
    (tmp_path/'dataset.jsonl').write_text(json.dumps(record())+'\n')
    (tmp_path/'Readiness.json').write_text(json.dumps({'contract': challenger.evidence.CONTRACT,
                                                      'source_ledger_sha256': {}}))
    with pytest.raises(ValueError, match='does not match'):
        challenger.load_export(tmp_path)


def test_identical_probabilities_have_zero_paired_delta():
    rows = [{'key': ['2026-01-01', 'G'], 'y': 1, 'C': .7, 'full': .7},
            {'key': ['2026-01-02', 'H'], 'y': 0, 'C': .6, 'full': .6}]
    out = challenger.paired(rows, 'full', 'C')
    assert out['brier_delta_first_minus_second'] == 0
    assert out['descriptive_date_cluster95'] == [0, 0]
