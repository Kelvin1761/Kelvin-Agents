#!/usr/bin/env python3
"""Price-free, stat-specific opportunity research. Never used for live betting.

Explicit feature allowlists keep prices, labels and bookmaker-derived estimates
out of prediction. Historical observed development dates are not a new holdout.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pickle
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.stats import nbinom, poisson
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / '.agents/skills/nba'))
from nba_identity import player_name_key
from nba_schedule import canonical_team_abbr
from nba_ml_pit import log_day, sha

CORE = ['count_logit', 'empirical_logit']
BLOCKS = {
    'minutes': ['minutes_mean', 'minutes_cv', 'minutes_l3_ratio', 'current_team_history_fraction'],
    'role': ['usage_pct', 'fga_per_min', 'fta_per_min', 'assist_pct', 'fg3a_per_min',
             'potential_assists', 'rebound_chances'],
    'opponent': ['opponent_pace', 'opponent_def_rating', 'opponent_stat_allowed_per100'],
    'schedule': ['is_home', 'days_since_game', 'b2b'],
}
ARMS = ['core', 'full', *['minus_' + block for block in BLOCKS]]
VERSION = 'nba-price-free-opportunity-logistic-v1'


def finite(value):
    if isinstance(value, bool) or value is None:
        return np.nan
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except (TypeError, ValueError):
        return np.nan


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def build_features(player, stat, line, *, event_day, team, opponent_stats, is_home):
    """Only the explicit dated player/context inputs can affect prediction."""
    line = finite(line)
    if not math.isfinite(line) or line < 1 or not line.is_integer():
        raise ValueError('integer milestone required')
    gl = player.get('gamelog') or {}
    values = np.asarray(gl.get(stat, [])[:10], dtype=float)
    dates = [log_day(day) for day in gl.get('l10_dates', [])[:10]]
    target = log_day(event_day)
    if (not len(values) or len(values) != len(dates) or not target
            or any(day is None or day >= target for day in dates)
            or dates != sorted(dates, reverse=True)
            or not np.isfinite(values).all() or (values < 0).any()):
        raise ValueError('invalid or non-prior aligned history')
    mean, variance = float(values.mean()), float(values.var())
    mu = max(mean, .05)
    alpha = max((variance - mean) / mu ** 2, 0)
    probability = (nbinom.sf(line - 1, 1 / alpha, 1 / (1 + alpha * mu))
                   if alpha > 0 else poisson.sf(line - 1, mu))
    features = {key: np.nan for key in [*CORE, *sum(BLOCKS.values(), [])]}
    features['count_logit'] = float(logit(probability))
    features['empirical_logit'] = float(logit(((values >= line).sum() + .5) / (len(values) + 1)))
    mins = np.asarray(gl.get('MIN', [])[:10], dtype=float)
    valid_minutes = (len(mins) == len(values) and np.isfinite(mins).all() and (mins >= 0).all()
                     and mins.sum() > 0)
    if valid_minutes:
        features['minutes_mean'] = float(mins.mean())
        features['minutes_cv'] = float(mins.std() / mins.mean())
        features['minutes_l3_ratio'] = float(mins[:3].mean() / mins.mean())
    matchups = gl.get('l10_matchups', [])[:10]
    if len(matchups) == len(values) and all(isinstance(m, str) and m.split() for m in matchups):
        features['current_team_history_fraction'] = sum(
            canonical_team_abbr(m.split()[0]) == canonical_team_abbr(team) for m in matchups) / len(matchups)
    advanced = player.get('advanced') or {}
    tracking = player.get('tracking') or {}
    if stat == 'PTS':
        features['usage_pct'] = finite(advanced.get('USG_PCT'))
    if stat == 'AST':
        features['assist_pct'] = finite(advanced.get('AST_PCT'))
        features['potential_assists'] = finite(tracking.get('POTENTIAL_AST'))
    if stat == 'REB':
        features['rebound_chances'] = finite(tracking.get('REB_CHANCES'))
    for field, key, applies in [('FGA', 'fga_per_min', stat == 'PTS'),
                               ('FTA', 'fta_per_min', stat == 'PTS'),
                               ('FG3A', 'fg3a_per_min', stat == 'FG3M')]:
        arr = np.asarray(gl.get(field, [])[:10], dtype=float)
        if applies and valid_minutes and len(arr) == len(mins) and np.isfinite(arr).all() and (arr >= 0).all():
            features[key] = float(arr.sum() / mins.sum())
    features['opponent_pace'] = finite(opponent_stats.get('PACE'))
    if stat in ('PTS', 'FG3M'):
        features['opponent_def_rating'] = finite(opponent_stats.get('DEF_RATING'))
    mode = ((opponent_stats.get('opponent_stats') or {}).get('modes') or {}).get('per_100_possessions') or {}
    if mode.get('status') == 'available' and finite(mode.get('games')) > 0:
        features['opponent_stat_allowed_per100'] = finite((mode.get('values') or {}).get('OPP_' + stat))
    days = (target - dates[0]).days
    features.update(is_home=int(is_home), days_since_game=min(days, 14), b2b=int(days == 1))
    return features


def team_value(mapping, team, default=None):
    matches = [value for key, value in mapping.items()
               if canonical_team_abbr(key) == canonical_team_abbr(team)]
    if len(matches) > 1:
        raise ValueError('ambiguous normalized team identity')
    return matches[0] if matches else default


def columns(arm):
    if arm not in ARMS:
        raise ValueError('unknown arm')
    return CORE + [name for block, names in BLOCKS.items()
                   if arm != 'core' and arm != 'minus_' + block for name in names]


def ladder_weights(rows):
    groups = rows.groupby(['game_group', 'player_key', 'stat_category'])['line_value'].transform('size')
    weights = 1 / groups.to_numpy(dtype=float)
    return weights / weights.mean()


def fit_stat_models(X, rows, arm):
    models, coverage = {}, {}
    for stat, indices in rows.groupby('stat_category').groups.items():
        subset, target = X.loc[indices, columns(arm)], rows.loc[indices, 'hit']
        if target.nunique() != 2:
            raise ValueError(f'{stat}: training fold needs both labels')
        model = Pipeline([('imputer', SimpleImputer(strategy='median', keep_empty_features=True)),
                          ('scale', StandardScaler()),
                          ('model', LogisticRegression(C=1, max_iter=2000, solver='lbfgs'))])
        model.fit(subset, target, model__sample_weight=ladder_weights(rows.loc[indices]))
        models[stat] = model
        coverage[stat] = {name: int(subset[name].notna().sum()) for name in subset}
    return models, coverage


def predict(models, X, rows, arm):
    probabilities = pd.Series(index=rows.index, dtype=float)
    for stat, indices in rows.groupby('stat_category').groups.items():
        probabilities.loc[indices] = models[stat].predict_proba(X.loc[indices, columns(arm)])[:, 1]
    if probabilities.isna().any():
        raise ValueError('incomplete probabilities')
    return probabilities


def metrics(rows, probability):
    y, p = np.asarray(rows.hit), np.asarray(probability)
    z = np.asarray(logit(p)).reshape(-1, 1)
    calibration = LogisticRegression(penalty=None, max_iter=2000).fit(z, y)
    reliability = []
    for lo, hi in [(0, .5), (.5, .7), (.7, .8), (.8, 1.00000001)]:
        mask = (p >= lo) & (p < hi)
        reliability.append({'range': [lo, min(hi, 1)], 'n': int(mask.sum()),
                            'p': float(p[mask].mean()) if mask.any() else None,
                            'hit': float(y[mask].mean()) if mask.any() else None})
    return {'brier': float(brier_score_loss(y, p)),
            'log_loss': float(log_loss(y, np.clip(p, 1e-12, 1 - 1e-12), labels=[0, 1])),
            'calibration_intercept': float(calibration.intercept_[0]),
            'calibration_slope': float(calibration.coef_[0, 0]), 'reliability': reliability}


def paired(rows, first, second, draws):
    delta = (np.asarray(first) - rows.hit.to_numpy()) ** 2 - (np.asarray(second) - rows.hit.to_numpy()) ** 2
    samples = np.asarray([delta[index].mean() for index in draws])
    return {'brier_delta_first_minus_second': float(delta.mean()),
            'date_bootstrap_95': np.percentile(samples, [2.5, 97.5]).tolist(),
            'bootstrap_sign_tail_descriptive': float((1 + (samples >= 0).sum()) / (len(samples) + 1))}


def selection_diagnostic(rows, probability):
    frame = rows.copy()
    frame['probability'] = np.asarray(probability)
    frame['ev'] = frame.probability * frame.market_price - 1
    frame = frame[(frame.ev > 0) & frame.market_price.between(1.15, 3.5)]
    selected = frame.sort_values(['ev', 'player_key', 'stat_category', 'line_value'],
                                ascending=[False, True, True, True], kind='stable').drop_duplicates('game_group')
    profit = (selected.hit * selected.market_price - 1).sum()
    return {'events': int(rows.game_group.nunique()), 'selected': len(selected),
            'hits': int(selected.hit.sum()), 'flat_single_leg_profit': float(profit),
            'flat_single_leg_roi': float(profit / len(selected)) if len(selected) else None,
            'average_predicted_probability': float(selected.probability.mean()) if len(selected) else None,
            'status': 'historical development single-leg diagnostic, not SGM/forward/production ROI'}, selected


def run(dataset, output, protocol_path, baseline_path):
    from train_nba_xgboost import load_and_prepare
    from sklearn.model_selection import TimeSeriesSplit
    sys.path.insert(0, str(ROOT / '.agents/skills/nba/nba_wong_choi/scripts'))
    import nba_prob_layer
    output = Path(output)
    output.mkdir(exist_ok=False)
    protocol = json.loads(Path(protocol_path).read_text())
    baseline = json.loads(Path(baseline_path).read_text())
    if sha(dataset) != protocol['dataset_sha256'] or sha(protocol_path) != baseline['protocol_sha256']:
        raise ValueError('protocol / baseline binding mismatch')
    _, _, _, _ = load_and_prepare(dataset)  # Independently verify artifacts and old feature values.
    frame = pd.read_csv(dataset)
    frame = frame[frame.hit.notna() & frame.game_date.isin(baseline['dev_dates'])].copy()
    cache, feature_rows = {}, {}
    for index, row in frame.iterrows():
        path = row.source_game_path
        if path not in cache:
            cache[path] = json.loads(Path(path).read_text())
        payload = cache[path]
        players = team_value(payload['players'], row.team)
        if players is None:
            raise ValueError('player team missing from source')
        matches = [p for p in players if player_name_key(p['name']) == row.player_key]
        if len(matches) != 1:
            raise ValueError('ambiguous player identity')
        home = canonical_team_abbr((payload['meta'].get('home') or {}).get('abbr')) == canonical_team_abbr(row.team)
        feature_rows[index] = build_features(matches[0], row.stat_category, row.line_value,
            event_day=row.game_date, team=row.team,
            opponent_stats=team_value(payload.get('team_stats', {}), row.opponent, {}), is_home=home)
    X = pd.DataFrame.from_dict(feature_rows, orient='index')
    predictions = pd.DataFrame(index=frame.index, columns=ARMS, dtype=float)
    fold_records, coverage_records = [], []
    for fold, (ti, vi) in enumerate(TimeSeriesSplit(n_splits=5).split(baseline['dev_dates']), 1):
        train_dates = [baseline['dev_dates'][i] for i in ti]
        valid_dates = [baseline['dev_dates'][i] for i in vi]
        train = frame[frame.game_date.isin(train_dates)]
        valid = frame[frame.game_date.isin(valid_dates)]
        if set(train.game_group) & set(valid.game_group) or max(train_dates) >= min(valid_dates):
            raise ValueError('time/event leakage')
        record = {'fold': fold, 'train_dates': train_dates, 'validation_dates': valid_dates, 'arms': {}}
        for arm in ARMS:
            models, coverage = fit_stat_models(X, train, arm)
            probability = predict(models, X, valid, arm)
            predictions.loc[valid.index, arm] = probability
            record['arms'][arm] = metrics(valid, probability)
            if arm == 'full':
                coverage_records.append({'fold': fold, 'features': coverage})
        fold_records.append(record)
    oof_indices = [i for fold in baseline['folds'] for i in fold['rows']]
    oof = frame.loc[oof_indices].copy().reset_index(drop=True)
    predictions = predictions.loc[oof_indices].reset_index(drop=True)
    if predictions.isna().any().any():
        raise ValueError('OOF rows do not match frozen baseline')
    oof['market'] = 1 / oof.market_price
    oof['C'] = [nba_prob_layer.calibrated_prob(s, p, h) / 100
                for s, p, h in zip(oof.stat_category, oof.market_price, oof.hit_rate_l10)]
    for arm in ARMS:
        oof[arm] = predictions[arm]
    days = oof.game_date.to_numpy()
    clusters = [np.flatnonzero(days == day) for day in sorted(set(days))]
    rng = np.random.default_rng(20261025)
    draws = [np.concatenate([clusters[i] for i in rng.integers(0, len(clusters), len(clusters))]) for _ in range(2000)]
    comparisons = {'full_vs_' + other: paired(oof, oof.full, oof[other], draws)
                   for other in ['core', 'market', 'C', *ARMS[2:]]}
    family = ['full_vs_core', *['full_vs_' + arm for arm in ARMS[2:]]]
    order = sorted(family, key=lambda name: comparisons[name]['bootstrap_sign_tail_descriptive'])
    previous = 0
    for rank, name in enumerate(order):
        previous = max(previous, min(1, (len(order) - rank) * comparisons[name]['bootstrap_sign_tail_descriptive']))
        comparisons[name]['holm_adjusted_sign_tail_descriptive'] = previous
    summary = {'version': VERSION, 'deployment_eligible': False, 'terminal_evaluated': False,
               'status': 'NEEDS_MORE_TESTING: observed development OOF only',
               'protocol_sha256': sha(protocol_path), 'dataset_sha256': sha(dataset), 'code_sha256': sha(__file__),
               'rows': len(oof), 'events': int(oof.game_group.nunique()), 'dates': len(clusters),
               'metrics': {name: metrics(oof, oof[name]) for name in [*ARMS, 'market', 'C']},
               'comparisons': comparisons, 'folds': fold_records, 'training_feature_coverage': coverage_records,
               'per_stat': {stat: {name: metrics(group, group[name]) for name in ['core', 'full', 'market', 'C']}
                            for stat, group in oof.groupby('stat_category')},
               'C_caveat': 'fitted/inspected historical dates overlap; not an independent comparator'}
    summary['selection_diagnostics'] = {}
    for arm in ['full', 'core', 'C']:
        info, selected = selection_diagnostic(oof, oof[arm])
        summary['selection_diagnostics'][arm] = info
        selected.to_csv(output / (arm + '_single_leg_selections.csv'), index=False)
    summary['monotonicity_violations'] = {}
    for arm in ARMS:
        violations = 0
        for _, group in oof.groupby(['game_group', 'player_key', 'stat_category']):
            ordered = group.sort_values('line_value')[arm].to_numpy()
            violations += int((np.diff(ordered) > 1e-10).sum())
        summary['monotonicity_violations'][arm] = violations
    models, coverage = fit_stat_models(X, frame, 'full')
    summary['standardized_coefficients_full_dev_associations_only'] = {
        stat: dict(zip(columns('full'), model.named_steps['model'].coef_[0].tolist()))
        for stat, model in models.items()}
    with (output / 'research_models.pkl').open('wb') as stream:
        pickle.dump(models, stream)
    artifact = {'version': VERSION, 'deployment_eligible': False, 'training_dates': baseline['dev_dates'],
                'train_last_date': max(baseline['dev_dates']), 'feature_names': columns('full'),
                'coverage': coverage, 'protocol_sha256': sha(protocol_path), 'model_sha256': sha(output / 'research_models.pkl'),
                'code_sha256': sha(__file__), 'dataset_sha256': sha(dataset)}
    (output / 'Artifact.json').write_text(json.dumps(artifact, indent=2, allow_nan=False))
    oof.to_csv(output / 'OOF.csv', index=False)
    (output / 'Summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False))
    print(json.dumps({'rows': len(oof), 'metrics': summary['metrics'], 'comparisons': comparisons,
                      'selection_diagnostics': summary['selection_diagnostics']}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ['dataset', 'output', 'protocol', 'baseline']:
        parser.add_argument('--' + option, required=True)
    args = parser.parse_args()
    run(args.dataset, args.output, args.protocol, args.baseline)
