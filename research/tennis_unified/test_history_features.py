from copy import deepcopy
from datetime import date, timedelta
import json

import numpy as np
import pytest

from .features import make_features, profiles, sigmoid
from .history import canonicalise, parse_row, points, score_sets
from .study import PROTOCOL, fit, holm, losses, paired_bootstrap, predict, validate_inputs
from .warehouse import digest


def raw(**changes):
    item = {'tourney_date': '20210101', 'tourney_id': '2021-001', 'match_num': '2', 'round': 'F',
            'best_of': '3', 'winner_id': '1', 'loser_id': '2', 'score': '6-4 6-3',
            'surface': 'Hard', 'tourney_level': 'A', 'winner_rank': '20', 'loser_rank': '30'}
    for prefix in ('w', 'l'):
        item.update({prefix + '_svpt': '80', prefix + '_1stIn': '50',
                     prefix + '_1stWon': '35', prefix + '_2ndWon': '15'})
    return dict(item, **changes)


def row(day='2021-01-01', a=1, b=2, y=1, key='x', **changes):
    return dict({'key': key, 'date': day, 'available': (date.fromisoformat(day) + timedelta(days=21)).isoformat(),
                 'tour': 'ATP', 'a': a, 'b': b, 'y': y, 'surface': 'Hard', 'level': 'A', 'best_of': 3,
                 'a_points': [50, 80], 'b_points': [45, 80], 'a_rank': 20, 'b_rank': 30}, **changes)


PRIORS = {'by_tour': {'ATP': {'serve': .6, 'reference_exposure': 80.}}}


def features(rows):
    return make_features(sorted(rows, key=lambda r: (r['date'], r['key'])), PRIORS)[0]


@pytest.mark.parametrize('score,best_of', [('6-4 RET', 3), ('W/O', 3), ('6-3', 3), ('6-4 6-4 6-0', 3),
                                         ('6-5 6-2', 3), ('6-4 4-6 [10-8]', 3), ('4-6 3-6', 3)])
def test_uncompleted_or_unsupported_labels_held(score, best_of):
    assert score_sets(score, best_of) is None


def test_point_count_validation_does_not_drop_target_label():
    item = raw(w_2ndWon='31')
    assert points(item, 'w') is None
    parsed, reason = parse_row(item, 'ATP', 1, 0)
    assert reason is None and parsed['a_points'] is None
    assert parsed['y'] == 1


def test_canonical_ordinal_revisions_collapse_but_conflicts_hold():
    first, _ = parse_row(raw(), 'ATP', 1, 0)
    second, _ = parse_row(raw(match_num='999'), 'ATP', 2, 0)
    selected, held, collapsed = canonicalise([first, second])
    assert len(selected) == len(collapsed) == 1 and held == []
    second['a_points'] = [51, 80]
    selected, held, collapsed = canonicalise([first, second])
    assert selected == [] and len(held) == 2 and collapsed == []


def test_repeat_round_robin_is_not_merged_by_pair_and_date():
    one, _ = parse_row(raw(round='RR'), 'ATP', 1, 0)
    two, _ = parse_row(raw(round='RR', match_num='3'), 'ATP', 1, 1)
    assert canonicalise([one, two])[0] == []


def test_different_identified_events_are_not_merged():
    one, _ = parse_row(raw(), 'ATP', 1, 0)
    two, _ = parse_row(raw(tourney_id='2021-002'), 'ATP', 1, 1)
    assert len(canonicalise([one, two])[0]) == 2


def test_equal_match_and_true_point_exposure_and_pseudo_prior():
    h = [{'date': '2020-12-01', 'available': '2020-12-22', 'serve': [1, 10], 'return': [2, 10]},
         {'date': '2020-12-02', 'available': '2020-12-23', 'serve': [80, 100], 'return': [50, 100]}]
    p = profiles(h, '2021-01-01', PRIORS['by_tour']['ATP'])
    assert p['000'][0] == pytest.approx(.45)
    assert p['E'][0] == pytest.approx(81 / 110)
    assert p['S'][0] == pytest.approx((.45 * 160 + .6 * 100) / 260)
    assert p['ES'][0] == pytest.approx((81 + .6 * 100) / 210)
    assert p['R'][0] > p['000'][0]


def test_window_counts_missing_rows_before_filtering_points():
    h = [{'date': '2020-12-01', 'available': '2020-12-22', 'serve': [0, 10], 'return': [0, 10]}]
    h += [{'date': '2020-12-01', 'available': '2020-12-22', 'serve': None, 'return': None}] * 25
    assert profiles(h, '2021-01-01', PRIORS['by_tour']['ATP'])['E'] == [.6, .4]


def test_future_profile_row_rejected():
    h = [{'date': '2021-01-01', 'available': '2021-01-22', 'serve': [5, 10], 'return': None}]
    with pytest.raises(ValueError, match='future'):
        profiles(h, '2021-01-22', PRIORS['by_tour']['ATP'])


def test_strict_21d_cutoff_same_day_freeze_and_cold_start_retained():
    rows = [row(key='first'), row('2021-01-22', key='exact'), row('2021-01-23', key='later')]
    out = {r['key']: r for r in features(rows)}
    assert out['first']['n_a'] == out['exact']['n_a'] == 0
    assert out['later']['n_a'] == 1
    assert out['first']['x']['elo'] == 0


def test_target_stats_rank_and_outcome_do_not_enter_own_features():
    rows = [row('2020-12-01', key='past'), row('2021-01-01', key='target')]
    before = features(rows)[0]
    rows[-1].update(y=0, a_points=[1, 100], b_points=None, a_rank=9999, b_rank=1)
    after = features(rows)[0]
    assert before['x'] == after['x'] and before['state_sha256'] == after['state_sha256']


def test_future_result_injection_does_not_rewrite_earlier_features():
    rows = [row('2020-12-01', key='past'), row('2021-01-01', key='earlier'), row('2021-04-01', key='future')]
    before = features(rows)[0]
    rows[-1].update(y=0, a_points=[1, 100], a_rank=1)
    assert features(rows)[0] == before


def test_h2h_expectation_is_from_historical_forecast_not_current_rating():
    rows = [row('2020-12-01', 1, 3, 1, 'warm-a'), row('2020-12-01', 2, 4, 0, 'warm-b'),
            row('2021-01-10', key='meeting'), row('2021-02-01', 1, 3, 0, 'other'),
            row('2021-03-01', key='target')]
    out = {r['key']: r for r in features(rows)}
    historical_p = sigmoid(out['meeting']['x']['elo'])
    assert out['target']['x']['h2h_residual'] == pytest.approx((1 - historical_p) / 6)
    assert out['target']['h2h_keys'] == ['meeting']


def test_training_scale_and_probability_preserve_exact_swap_symmetry():
    rng = np.random.default_rng(7)
    x = rng.normal(size=(1000, 3)) + [3., 0., 0.]
    x[:, 2] = 0
    y = (rng.random(1000) < 1 / (1 + np.exp(-x[:, 0]))).astype(int)
    fitted = fit(x, y)
    assert fitted['scale'][2] == 1
    assert np.max(np.abs(predict(x, fitted) + predict(-x, fitted) - 1)) < 1e-10
    assert np.array_equal(predict(x, fitted), predict(x, deepcopy(fitted)))


def test_aa_has_zero_gain_and_cannot_pass_multiplicity():
    y, p = np.array([0, 1] * 20), np.array([.3, .7] * 20)
    vector = losses(y, p)
    _, mean, ci, pv = paired_bootstrap(vector - vector, trials=100)
    assert np.array_equal(mean, [0, 0]) and np.array_equal(ci, np.zeros((2, 2)))
    assert np.array_equal(pv, [1, 1])
    assert holm({'a': 1 / 4001, **{str(i): 1. for i in range(75)}})['a'] == pytest.approx(76 / 4001)


def test_separate_tour_results_never_change_tennis_features():
    atp = [row('2020-12-01', key='past'), row('2021-01-01', key='target')]
    wta = row('2020-12-01', key='wta', tour='WTA', y=0)
    assert features(atp)[0]['x'] == features(atp + [wta])[0]['x']


def test_complete_comparison_roster_is_fixed_before_candidate_fitting():
    p = json.loads(PROTOCOL.read_text())
    assert len(p['comparisons']) == len({r[0] for r in p['comparisons']}) == 38
    assert p['statistics']['holm_tests'] == 2 * len(p['comparisons']) == 76
    for arm in ('R', 'E', 'S', 'RE', 'RS', 'ES', 'RES'):
        assert ['serve_' + arm + '_vs_simple', 'serve_' + arm, 'simple'] in p['comparisons']
    for arm in ('RE', 'RS', 'ES'):
        assert ['serve_RES_vs_' + arm, 'serve_RES', 'serve_' + arm] in p['comparisons']


def test_lock_rejects_stale_cohort_or_changed_label(tmp_path):
    source = row(key='event')
    cohort = tmp_path / 'cohort.json'
    cohort.write_text(json.dumps({'rows': [source], 'sources': [{'raw_id': 1}]}))
    generated = features([source])
    data = {'cohort_sha256': digest(cohort), 'rows': generated}
    protocol = {'train_start': '2021-01-01', 'source_raw_ids': [1]}
    validate_inputs(cohort, data, protocol)
    data['rows'][0]['y'] = 0
    with pytest.raises(ValueError, match='label mismatch'):
        validate_inputs(cohort, data, protocol)
    data['cohort_sha256'] = 'stale'
    with pytest.raises(ValueError, match='different cohort'):
        validate_inputs(cohort, data, protocol)
