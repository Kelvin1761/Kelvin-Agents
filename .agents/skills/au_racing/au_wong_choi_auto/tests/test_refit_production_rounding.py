"""Refit must preserve production's decimal half-case matrix rounding."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts'))
import au_matrix_refit as refit
from au_racing_engine.scoring import MATRIX_WEIGHTS, compose_matrix_score
from au_racing_engine.matrix_mapper import map_features_to_matrix_scores


def test_decimal_half_case_uses_production_value_not_numpy_bankers_rounding(tmp_path):
    features = {'class_score': 57.7, 'rating_score': 57.7}
    expected = map_features_to_matrix_scores(features)
    assert expected['class_weight'] == 58.05
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps({'races': [{'rows': [{'n': 1, 'features': features,
        'wet': 0, 'ability': round(compose_matrix_score(expected), 4)}]}]}))
    ds = refit.Dataset(path)
    assert ds.raw['class_weight'][0] == 58.05
    assert ds.ability(ds.dim_matrix(), MATRIX_WEIGHTS)[0] == ds.engine_ability[0]


def test_clipping_missing_values_and_all_formula_keys_follow_canonical_mapper(tmp_path):
    features = {'form_score': -10, 'performance_quality_score': 120, 'class_score': 57.7,
                'rating_score': 57.7, 'pace_map_score': 0}
    expected = map_features_to_matrix_scores(features)
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps({'races': [{'rows': [{'n': 1, 'features': features,
        'wet': 0, 'ability': round(compose_matrix_score(expected), 4)}]}]}))
    ds = refit.Dataset(path)
    assert {key: float(values[0]) for key, values in ds.raw.items()} == expected


def test_publication_rounding_preserves_python_half_cases_and_overlay_sum(tmp_path):
    features = {'class_score': 57.7, 'rating_score': 57.7}
    matrices = map_features_to_matrix_scores(features)
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps({'races': [{'rows': [{'n': 1, 'features': features,
        'wet': 0.00005, 'proven_class': 0.12345, 'ability': 60}]}]}))
    ds = refit.Dataset(path)
    for weights in [MATRIX_WEIGHTS, {'class_weight': 0.0001}, {'class_weight': 1.0}]:
        ordered = {key: weights.get(key, 0.0) for key in refit.DIMS}
        pure = round(compose_matrix_score(matrices, ordered), 4)
        expected = round(pure + 0.00005 + 0.12345, 4)
        assert ds.ability(ds.dim_matrix(), weights)[0] == expected
