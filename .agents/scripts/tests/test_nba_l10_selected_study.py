import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('l10_study', Path(__file__).parents[1] / 'nba_ml/nba_l10_selected_study.py')
study = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(study)


def row(day='2026-01-01', event='a', player='x', p=.8, hit=0, price=1.5):
    return dict(game_date=day, game_group=event, player_key=player, stat_category='PTS',
                line_value=15., n_history=10., hit_rate_l10=80., hit_rate_l5=80.,
                full=p, market_price=price, hit=hit)


def test_filter_reranks_whole_pool_and_retains_ev():
    bad = dict(row(player='bad', p=.99), hit_rate_l10=70)
    good = row(player='good')
    negative = row(event='b', p=.5)
    assert study.select([bad, good, negative], 'full') == [good]
    assert not study.eligible(dict(good, n_history=5))


def test_offset_handles_single_class_and_shrinks_to_zero():
    assert study.fit_offset([], 4) == pytest.approx(0, abs=1e-10)
    offset = study.fit_offset([row() for _ in range(10)], 4)
    assert offset < 0
    assert .1 < study.adjusted(.8, offset) < .8
    positive = study.fit_offset([row(hit=1) for _ in range(10)], 4)
    assert positive > 0
    with pytest.raises(ValueError):
        study.fit_offset([], 0)


def test_shared_offset_preserves_milestone_order():
    values = [study.adjusted(p, -1.2) for p in [.95, .8, .6, .2]]
    assert values == sorted(values, reverse=True)


def test_future_outcomes_cannot_change_earlier_predictions_and_embargo():
    rows = [row(day=f'2026-01-{i:02}', event=str(i), hit=i % 2) for i in range(1, 11)]
    config = dict(min_train_dates=3, min_train_events=3, label_embargo_calendar_days=2, ridge=4)
    predictions, records = study.forward(rows, config)
    changed = [dict(r, hit=1-r['hit']) if r['game_date'] >= '2026-01-08' else r for r in rows]
    other, _ = study.forward(changed, config)
    before = [(r['game_date'], r['calibrated']) for r in predictions if r['game_date'] <= '2026-01-08']
    assert before == [(r['game_date'], r['calibrated']) for r in other if r['game_date'] <= '2026-01-08']
    for record in records:
        if record['status'] == 'evaluated':
            assert max(record['train_dates']) <= record['latest_allowed_train_date'] < record['test_date']
    assert predictions[0]['game_date'] == '2026-01-05'


def test_fixed_cohort_metrics_keep_same_outcomes():
    rows = [dict(row(), calibrated=.65)]
    assert study.metrics(rows, 'full')['hits'] == study.metrics(rows, 'calibrated')['hits']
    assert study.paired_brier(rows, 'calibrated', 'full')['delta_first_minus_second'] < 0
