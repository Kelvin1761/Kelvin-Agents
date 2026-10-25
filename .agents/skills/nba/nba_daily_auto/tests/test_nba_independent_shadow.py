"""The price-free research model must not import labels, prices or future history."""
import copy
from pathlib import Path
import sys
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / 'scripts/nba_ml'))
import nba_independent_shadow as study


def player():
    return {'advanced': {'USG_PCT': 25, 'AST_PCT': 30, 'DEF_RATING': 999},
            'gamelog': {'PTS': [20, 22, 18], 'AST': [5, 7, 4], 'REB': [6, 9, 5],
                        'FG3M': [2, 3, 1], 'MIN': [30, 32, 28], 'FGA': [15, 16, 14],
                        'FTA': [4, 5, 3], 'FG3A': [6, 7, 5],
                        'l10_dates': ['2026-04-10', '2026-04-08', '2026-04-06'],
                        'l10_matchups': ['BOS @ LAL', 'BOS vs. MIL', 'NYK @ ATL']}}


def features(p=None, stat='PTS', line=15, **kwargs):
    options = dict(event_day='2026-04-11', team='BOS', opponent_stats={'PACE': 100, 'DEF_RATING': 110}, is_home=True)
    options.update(kwargs)
    return study.build_features(p or player(), stat, line, **options)


def test_price_label_and_h2h_changes_cannot_change_features():
    p = player()
    p.update(market_price=1.1, actual_value=999, hit=1, h2h={'PTS': [999]})
    p['advanced']['BOOKIE_PROBABILITY'] = 1
    pd.testing.assert_series_equal(pd.Series(features()), pd.Series(features(p)))
    assert not any('price' in key or 'market' in key for key in features())


@pytest.mark.parametrize('stat,line', [('PTS', 15), ('AST', 4), ('REB', 4), ('FG3M', 1)])
def test_core_probabilities_are_monotone_in_milestone(stat, line):
    low, high = features(stat=stat, line=line), features(stat=stat, line=line + 1)
    assert low['count_logit'] >= high['count_logit']
    assert low['empirical_logit'] >= high['empirical_logit']


def test_stat_specific_roles_and_opponent_metrics_are_not_interchangeable():
    points, assists, rebounds = features(), features(stat='AST', line=4), features(stat='REB', line=4)
    assert points['usage_pct'] == 25 and points['fga_per_min'] == .5
    assert np.isnan(assists['usage_pct']) and assists['assist_pct'] == 30
    assert np.isnan(assists['opponent_def_rating']) and np.isnan(rebounds['opponent_def_rating'])
    assert np.isnan(assists['potential_assists']) and np.isnan(rebounds['rebound_chances'])
    assert points['current_team_history_fraction'] == 2 / 3
    assert assists['b2b'] == 1 and assists['days_since_game'] == 1


def test_missing_opponent_stats_are_unknown_and_preserve_units():
    missing = features(opponent_stats={})
    assert np.isnan(missing['opponent_pace'])
    raw = {'opponent_stats': {'modes': {'per_game': {'status': 'available', 'games': 10, 'values': {'OPP_PTS': 999}},
                                       'per_100_possessions': {'status': 'available', 'games': 10, 'values': {'OPP_PTS': 109}}}}}
    assert features(opponent_stats=raw)['opponent_stat_allowed_per100'] == 109
    raw['opponent_stats']['modes']['per_100_possessions']['games'] = 0
    assert np.isnan(features(opponent_stats=raw)['opponent_stat_allowed_per100'])


@pytest.mark.parametrize('mutation', ['future', 'order', 'unaligned', 'invalid'])
def test_bad_history_fails_instead_of_becoming_a_neutral_signal(mutation):
    p = player()
    if mutation == 'future': p['gamelog']['l10_dates'][0] = '2026-04-11'
    if mutation == 'order': p['gamelog']['l10_dates'].reverse()
    if mutation == 'unaligned': p['gamelog']['l10_dates'].pop()
    if mutation == 'invalid': p['gamelog']['PTS'][0] = float('nan')
    with pytest.raises(ValueError): features(p)


def test_ladder_weights_do_not_let_many_lines_multiply_one_players_training_weight():
    rows = pd.DataFrame({'game_group': ['g'] * 4, 'player_key': ['a', 'a', 'a', 'b'],
                         'stat_category': ['PTS'] * 4, 'line_value': [10, 15, 20, 10]})
    weights = study.ladder_weights(rows)
    assert weights[:3].sum() == pytest.approx(weights[3])
    assert weights.mean() == pytest.approx(1)


def test_validation_values_do_not_refit_training_imputer_or_scaler():
    rows = pd.DataFrame({'stat_category': ['PTS'] * 4, 'hit': [0, 0, 1, 1],
                         'game_group': ['a', 'b', 'c', 'd'], 'player_key': ['x'] * 4, 'line_value': [10] * 4})
    X = pd.DataFrame({'count_logit': [-2, -1, 1, 2], 'empirical_logit': [-2, np.nan, 1, 2]})
    models, _ = study.fit_stat_models(X, rows, 'core')
    before = copy.deepcopy(models['PTS'].named_steps['imputer'].statistics_)
    altered = X.copy(); altered.loc[0, 'empirical_logit'] = 100000
    study.predict(models, altered, rows, 'core')
    np.testing.assert_equal(before, models['PTS'].named_steps['imputer'].statistics_)


def test_team_aliases_are_normalized_without_combining_ambiguous_sources():
    assert study.team_value({'GS': ['player']}, 'GSW') == ['player']
    assert study.team_value({'NY': {'PACE': 99}}, 'NYK') == {'PACE': 99}
    assert study.team_value({}, 'GSW', {}) == {}
    with pytest.raises(ValueError, match='ambiguous'):
        study.team_value({'GS': [], 'GSW': []}, 'GSW')
