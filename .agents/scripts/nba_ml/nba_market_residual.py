"""Research-only market residual trends; no live model or wager integration."""
from __future__ import annotations
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit
from sklearn.model_selection import TimeSeriesSplit

from nba_ml_pit import log_day, sha

VERSION = 'market-residual-trends-v1'
ARMS = {'B': (), 'BM': ('minutes_trend',), 'BR': ('rate_trend',),
        'BMR': ('minutes_trend', 'rate_trend')}
STATS = ('PTS', 'REB', 'AST', 'FG3M')
RIDGE = .01
SEED = 20261025


def trend_features(player, stat, game_date):
    """Use aligned historical arrays only; ignore target-game/label fields."""
    gl = player.get('gamelog') or {}
    dates, mins, values = gl.get('l10_dates') or [], gl.get('MIN') or [], gl.get(stat) or []
    empty = {'minutes_trend': None, 'rate_trend': None}
    if not len(dates) == len(mins) == len(values):return dict(empty, status='unaligned_history')
    if len(dates) < 5:return dict(empty, status='short_history')
    parsed = [log_day(value) for value in dates]
    cutoff = log_day(game_date)
    if (not cutoff or any(d is None or d >= cutoff for d in parsed)
            or any(a <= b for a, b in zip(parsed, parsed[1:]))):
        return dict(empty, status='unsafe_history_dates')
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
           for v in [*mins, *values]):return dict(empty, status='invalid_history_numbers')
    if any(m == 0 and v > 0 for m, v in zip(mins, values)):
        return dict(empty, status='inconsistent_zero_minutes')
    mins, values = mins[:10], values[:10]
    min3, min10, stat3, stat10 = sum(mins[:3]), sum(mins), sum(values[:3]), sum(values)
    if min3 <= 0 or min10 <= 0 or stat10 <= 0:return dict(empty, status='zero_denominator')
    return {'minutes_trend': float(np.clip((min3/3)/(min10/len(mins))-1, -1, 1)),
            'rate_trend': float(np.clip((stat3/min3)/(stat10/min10)-1, -1, 1)), 'status': 'ok'}


def game_unit_weights(frame):
    keys = ['game_group', 'player_key', 'stat_category']
    lines = frame.groupby(keys)['line_value'].transform('size').to_numpy(dtype=float)
    units = frame[keys].drop_duplicates()['game_group'].value_counts()
    return 1/(lines * frame['game_group'].map(units).to_numpy(dtype=float))


class ResidualLogit:
    def __init__(self, extra=()):
        self.extra = tuple(extra)

    def design(self, frame, fit=False):
        market = np.clip(1/frame['market_price'].to_numpy(dtype=float), .02, .98)
        hit = np.clip(frame['hit_rate_l10'].to_numpy(dtype=float)/100, .05, .95)
        columns = [(frame['stat_category'] == stat).to_numpy(dtype=float) for stat in STATS]
        columns += [np.log(market/(1-market)), np.log(hit/(1-hit))]
        if not frame['stat_category'].isin(STATS).all():raise ValueError('unknown stat')
        if fit:self.scaler = {}
        for name in self.extra:
            values = frame[name].to_numpy(dtype=float)
            if fit:self.scaler[name] = {'mean': float(values.mean()), 'sd': float(values.std())}
            summary = self.scaler[name]
            columns.append((values-summary['mean'])/(summary['sd'] or 1))
        result = np.column_stack(columns)
        if not np.isfinite(result).all():raise ValueError('nonfinite model inputs')
        return result

    def fit(self, frame, y):
        design = self.design(frame, fit=True)
        y = np.asarray(y, dtype=float)
        if len(set(y)) != 2 or not set(y) <= {0, 1}:raise ValueError('need both binary labels')
        weights = game_unit_weights(frame);weights /= weights.sum()
        prior = np.zeros(design.shape[1]);prior[4] = 1
        mask = np.ones(len(prior));mask[:4] = 0
        def objective(beta):
            z = design @ beta;difference = mask*(beta-prior)
            loss = np.dot(weights, np.logaddexp(0, z)-y*z) + RIDGE/2*np.dot(difference, difference)
            gradient = design.T @ (weights*(expit(z)-y)) + RIDGE*difference
            return loss, gradient
        result = minimize(objective, prior, jac=True, method='L-BFGS-B',
                          options={'maxiter': 2000, 'ftol': 1e-12})
        if not result.success or not np.isfinite(result.x).all():raise ValueError('optimizer failed: '+str(result.message))
        self.coef = result.x
        self.training_end_date = str(frame['game_date'].max())
        return self

    def predict(self, frame):
        return expit(self.design(frame) @ self.coef)

    def metadata(self):
        return {'extra': self.extra, 'coefficients': self.coef.tolist(), 'scaler': self.scaler,
                'training_end_date': self.training_end_date, 'deployment_eligible': False}


def paired_diagnostic(y, probability, baseline, days):
    difference = (np.asarray(probability)-y)**2-(np.asarray(baseline)-y)**2
    days = np.asarray(days);unique = sorted(set(days));rng = np.random.default_rng(SEED)
    indices = [np.flatnonzero(days == day) for day in unique]
    samples = [difference[np.concatenate([indices[i] for i in rng.integers(0, len(indices), len(indices))])].mean()
               for _ in range(2000)]
    return {'brier_delta': float(difference.mean()), 'ci95': np.percentile(samples, [2.5, 97.5]).tolist(),
            'date_clusters': len(unique), 'seed': SEED, 'replicates': 2000}


def band_summary(y, probability):
    return {str(low): {'n': int((probability >= low).sum()),
                      'mean_probability': float(probability[probability >= low].mean()) if (probability >= low).any() else None,
                      'hit_rate': float(y[probability >= low].mean()) if (probability >= low).any() else None}
            for low in (.7, .8)}


def run_study(dataset, output_dir):
    # Existing verifier reconstructs hash-matched pre-tip features and real prices.
    from train_nba_xgboost import load_and_prepare, _metrics
    import sys
    repo = Path(__file__).resolve().parents[3]
    sys.path.insert(0, str(repo/'.agents/skills/nba'))
    sys.path.insert(0, str(repo/'.agents/skills/nba/nba_wong_choi/scripts'))
    from nba_identity import player_name_key
    from nba_schedule import canonical_team_abbr
    from nba_prob_layer import calibrated_prob, probability_model_id
    X, y, _, context = load_and_prepare(dataset)
    frame = pd.read_csv(dataset).loc[X.index].copy()
    dates = sorted(context['game_date'].unique());terminal_n = math.ceil(len(dates)*.2)
    dev_dates, terminal_dates = dates[:-terminal_n], dates[-terminal_n:]
    sources = {};features = []
    for _, row in frame.iterrows():
        path = row['source_game_path']
        if path not in sources:
            payload = json.loads(Path(path).read_text())
            sources[path] = {(canonical_team_abbr(team), player_name_key(p['name'])): p for team, players in payload['players'].items() for p in players}
        player = sources[path].get((row['team'], row['player_key']))
        if player is None:raise ValueError('feature player missing')
        features.append(trend_features(player, row['stat_category'], row['game_date']))
    trends = pd.DataFrame(features, index=frame.index)
    frame[['minutes_trend', 'rate_trend', 'trend_status']] = trends.rename(columns={'status': 'trend_status'})
    coverage = {'status_rows': frame['trend_status'].value_counts().to_dict(),
                'priced_labeled_rows': len(frame), 'complete_rows': int((frame.trend_status == 'ok').sum()),
                'excluded_unlabeled_rows': len(pd.read_csv(dataset))-len(frame)}
    frame = frame.loc[(frame.trend_status == 'ok') & frame.game_date.isin(dev_dates)].copy()
    if len(dev_dates) < 10:raise ValueError('insufficient dates for fixed five-fold diagnostic')
    predictions = [];folds = [];models = {}
    for fold, (train_days, valid_days) in enumerate(TimeSeriesSplit(n_splits=5).split(dev_dates), 1):
        train = frame.loc[frame.game_date.isin([dev_dates[i] for i in train_days])]
        valid = frame.loc[frame.game_date.isin([dev_dates[i] for i in valid_days])]
        if train.empty or valid.empty or train.game_date.max() >= valid.game_date.min():raise ValueError('unsafe or empty temporal fold')
        if set(train.game_group) & set(valid.game_group):raise ValueError('event crosses fold')
        out = valid[['game_date', 'game_group', 'player_key', 'stat_category', 'line_value', 'market_price', 'hit']].copy()
        out['fold'] = fold
        out['market'] = 1/valid.market_price.to_numpy(dtype=float)
        out['raw_l10'] = valid.hit_rate_l10.to_numpy(dtype=float)/100
        out['C_historical_context_only'] = [calibrated_prob(stat, price, hit)/100 for stat, price, hit
            in zip(valid.stat_category, valid.market_price, valid.hit_rate_l10)]
        fold_metrics = {}
        for name, extra in ARMS.items():
            model = ResidualLogit(extra).fit(train, train.hit)
            prob = model.predict(valid);out[name] = prob
            fold_metrics[name] = _metrics(valid.hit, prob)
            models[f'{fold}:{name}'] = model.metadata()
        predictions.append(out)
        folds.append({'fold': fold, 'train_dates': sorted(train.game_date.unique()),
                      'validation_dates': sorted(valid.game_date.unique()), 'train_rows': len(train),
                      'valid_rows': len(valid), 'metrics': fold_metrics})
    predicted = pd.concat(predictions, ignore_index=True)
    if set(predicted.game_date) & set(terminal_dates):raise ValueError('spent terminal entered evaluation')
    target = predicted.hit.to_numpy(dtype=float)
    metrics = {name: _metrics(target, predicted[name].to_numpy()) for name in [*ARMS, 'market', 'raw_l10', 'C_historical_context_only']}
    weights = game_unit_weights(predicted)
    comparisons = {}
    for name in metrics:
        prob = predicted[name].to_numpy()
        metrics[name]['weighted_brier'] = float(np.average((prob-target)**2, weights=weights))
        metrics[name]['high_bands'] = band_summary(target, prob)
        metrics[name]['estimated_positive_leg_ev_fraction'] = float((prob*predicted.market_price.to_numpy() > 1).mean())
        metrics[name]['by_stat'] = {stat: _metrics(predicted.loc[predicted.stat_category == stat, 'hit'],
                                        predicted.loc[predicted.stat_category == stat, name]) for stat in STATS
                                  if (predicted.stat_category == stat).any()}
        metrics[name]['overall_calibration'] = {'mean_probability': float(prob.mean()), 'hit_rate': float(target.mean()),
                                               'gap': float(prob.mean()-target.mean())}
        inversions = 0
        for _, group in predicted.groupby(['game_group', 'player_key', 'stat_category']):
            inversions += int(np.sum(np.diff(group.sort_values('line_value')[name].to_numpy()) > 1e-10))
        metrics[name]['milestone_probability_inversions'] = inversions
        if name in ARMS:
            comparisons[name] = {base: paired_diagnostic(target, prob, predicted[base].to_numpy(), predicted.game_date)
                                 for base in ['B', 'market'] if name != base}
    marginal = {f'BMR_minus_{base}': paired_diagnostic(target, predicted.BMR.to_numpy(), predicted[base].to_numpy(), predicted.game_date)
                for base in ['BM', 'BR']}
    signals = {}
    for name in ['BM', 'BR', 'BMR']:
        wins = sum(f['metrics'][name]['brier_score'] <= f['metrics']['B']['brier_score'] for f in folds)
        signals[name] = {'folds_not_worse_than_B': wins,
                         'worth_forward_diagnostic': comparisons[name]['B']['ci95'][1] < 0
                         and comparisons[name]['market']['ci95'][1] <= 0 and wins >= 4
                         and metrics[name]['log_loss'] <= metrics['B']['log_loss']}
    result = {'version': VERSION, 'dataset_sha256': sha(dataset), 'dev_dates': dev_dates,
              'excluded_spent_terminal_dates': terminal_dates, 'coverage': coverage,
              'oos_rows': len(predicted), 'oos_games': int(predicted.game_group.nunique()),
              'oos_dates': int(predicted.game_date.nunique()), 'folds': folds, 'metrics': metrics,
              'comparisons': comparisons, 'marginal': marginal, 'signals': signals,
              'C_probability_model_id': probability_model_id(),
              'status': 'NEEDS_MORE_TESTING', 'promotion_allowed': False, 'deployment_eligible': False,
              'multiple_comparisons': 'Unadjusted exploratory intervals; no confirmatory WIN or adoption decision',
              'note': 'Historical previously seen corpus; OOS diagnostic, not confirmation. C overlaps historical training; context only. '
                      'Common complete-case cohort conditional on observed labels; no SGM prices/ROI or profitability claims.'}
    output = Path(output_dir);output.mkdir(parents=True, exist_ok=False)
    predicted.to_csv(output/'oos_predictions.csv', index=False)
    (output/'metrics.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (output/'research_models.json').write_text(json.dumps(models, indent=2, allow_nan=False)+'\n')
    print(json.dumps({key: result[key] for key in ['version', 'coverage', 'oos_rows', 'oos_games', 'oos_dates', 'signals']}, indent=2))
    return result
