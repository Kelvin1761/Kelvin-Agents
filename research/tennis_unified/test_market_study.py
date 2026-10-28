from copy import deepcopy

import numpy as np
import pytest

from .market_study import (fair, inner_choice, match_losses, raw_prediction, roi_vectors,
                           weighted_calibration, weighted_fit)
from .study import fit


def test_book_replication_does_not_change_ridge_fit_or_effective_sample():
    rng = np.random.default_rng(9)
    x = rng.normal(size=(700, 3))
    y = (rng.random(700) < 1 / (1 + np.exp(-x[:, 0]))).astype(int)
    control = fit(x, y)
    copies = np.repeat(x, 2, axis=0)
    candidate = weighted_fit(copies, np.repeat(y, 2), np.full(1400, .5), np.zeros(1400), np.array(control['scale']))
    assert np.max(np.abs(np.array(candidate['beta']) - control['beta'])) < 1e-12


def test_zero_correction_exactly_recovers_market_and_swap():
    x = np.zeros((20, 2))
    offsets = np.linspace(-3, 3, 20)
    model = weighted_fit(x, np.array([0, 1] * 10), np.ones(20), offsets, np.ones(2))
    expected = 1 / (1 + np.exp(-offsets))
    assert np.max(np.abs(raw_prediction(x, model, offsets) - expected)) < 1e-12
    assert np.max(np.abs(raw_prediction(x, model, offsets) + raw_prediction(-x, model, -offsets) - 1)) < 1e-12


def test_primary_is_mean_of_book_losses_not_loss_at_mean_probability():
    rows = [{'y': 1, 'quotes': [{'p': {'a': .1}}, {'p': {'a': .9}}]}]
    values = match_losses(rows, 'a')
    assert values[0, 0] == pytest.approx((-np.log(.1) - np.log(.9)) / 2)
    assert values[0, 0] != pytest.approx(-np.log(.5))


def test_shin_two_way_matches_analytic_additive_and_all_swaps():
    expected = (1 + 1 / 1.5 - 1 / 2.5) / 2
    assert fair(1.5, 2.5, 'shin') == pytest.approx(expected, abs=1e-12)
    for method in ('proportional', 'power', 'shin'):
        assert fair(1.5, 2.5, method) + fair(2.5, 1.5, method) == pytest.approx(1., abs=1e-10)
    with pytest.raises(ValueError):
        fair(3., 3., 'shin')


def test_inner_selection_excludes_outer_and_unreleased_labels():
    rows, probabilities = [], {}
    for i in range(600):
        y = i % 2
        row = {'key': str(i), 'date': '2022-02-01', 'available': '2022-02-22', 'y': y}
        rows.append(row)
        probabilities[row['key']] = [{'proportional': .6 if y else .4, 'power': .7 if y else .3, 'shin': .65 if y else .35}]
    future = {'key': 'future', 'date': '2023-02-01', 'available': '2023-02-22', 'y': 1}
    late = {'key': 'late', 'date': '2022-12-20', 'available': '2023-01-10', 'y': 1}
    rows.extend([future, late])
    probabilities['future'] = probabilities['late'] = [{'proportional': .999, 'power': .001, 'shin': .5}]
    result = inner_choice(rows, probabilities, '2023-01-01')
    assert result['selected'] == 'power' and result['matches'] == 600
    future['y'] = late['y'] = 0
    assert inner_choice(rows, probabilities, '2023-01-01') == result


def test_one_match_total_stake_is_not_inflated_by_multiple_books():
    q = {'book': 'B365', 'odds_a': 2., 'odds_b': 2., 'p': {'a': .6}, 'raw_p': {'a': .6}}
    second = deepcopy(q); second['book'] = 'PS'
    rows = [{'y': 1, 'quotes': [q, second]}]
    pnl, stake, clipping = roi_vectors(rows, 'a')
    assert pnl.tolist() == stake.tolist() == [1.] and clipping == 0
    assert roi_vectors(rows, 'a', 'B365')[1].tolist() == [1.]


def test_clipping_created_edge_is_reported_not_hidden_as_market_profit():
    q = {'book': 'B365', 'odds_a': 1.001, 'odds_b': 100., 'p': {'a': .98}, 'raw_p': {'a': .999}}
    assert roi_vectors([{'y': 0, 'quotes': [q]}], 'a')[2] == 1


def test_weighted_calibration_retains_one_match_mass():
    y, p, w = np.array([1, 1, 0]), np.array([.8, .8, .2]), np.array([.5, .5, 1.])
    report = weighted_calibration(y, p, w)
    assert sum(b['weight'] for b in report['bins']) == pytest.approx(2.)
    assert report['ece_10_equal_width'] == pytest.approx(.2)
