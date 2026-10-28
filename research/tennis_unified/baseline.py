"""Replay saved winner forecasts, with explicit legacy and timing exclusions.

No candidate, parameter selection, history rebuild, or production writes.
The output is SEEN_DEV and never qualifies a model for promotion by itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tennis-wong-choi/src'))
from tennis_wc.evaluation.match_corpus import prematch_outcomes

from research.tennis_unified.warehouse import digest, readonly, write_new


NUDGES = ('serve_return_edge', 'recent_form_edge', 'opponent_rank_bucket_edge',
          'tournament_level_edge', 'round_performance_edge', 'big_match_edge',
          'pressure_edge', 'head_to_head_edge', 'fatigue_edge')
SEED, TRIALS = 20260826, 4000


def instant(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def price_exclusion(quote, start, forecast):
    if quote is None:
        return 'no_first_quote'
    fetched, created = instant(quote['fetched_at']), instant(quote['created_at'])
    if any(clock is None for clock in (start, forecast, fetched, created)):
        return 'unverifiable_clock'
    if not fetched <= created <= forecast < start:
        return 'quote_not_observed_and_ingested_by_forecast'
    if quote['source_provider'] == 'mock':
        return 'mock_quote'
    try:
        odds = [float(quote[k]) for k in ('player_a_odds', 'player_b_odds')]
    except (ValueError, TypeError):
        return 'invalid_price'
    if not all(math.isfinite(x) and x > 1 for x in odds):
        return 'invalid_price'
    return None


def replay(pricing):
    """Reconstruct original raw logit, original side and original risk shrink."""
    model = pricing['model']
    parts = {part['name']: part for part in model['components']}
    if len(parts) != len(model['components']):
        raise ValueError('duplicate_components')
    if not any(parts.get(k, {}).get('active') is True
               for k in ('surface_elo_edge', 'overall_elo_edge')):
        raise ValueError('no_active_elo')
    terms = []
    for name in NUDGES:
        part = parts[name]
        if not isinstance(part.get('active'), bool):
            raise ValueError('unrecorded_activity')
        weight, probability = float(part['weight']), float(part['probability'])
        if not math.isfinite(weight) or weight < 0 or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError('invalid_component')
        terms.append(weight * (probability - .5) if part['active'] else 0.)
    nudge = min(1.2, max(-1.2, sum(terms)))
    base, stored = float(model['elo_base_logit']), float(model['total_nudge_logit'])
    if not math.isfinite(base) or not math.isfinite(stored) or abs(nudge - stored) > 1e-6:
        raise ValueError('nudge_reconstruction_mismatch')
    raw = min(.98, max(.02, 1 / (1 + math.exp(-max(-700, min(700, base + nudge))))))
    side = pricing['selection_side']
    if side not in ('player_a', 'player_b'):
        raise ValueError('unrecorded_side')
    selected = raw if side == 'player_a' else 1 - raw
    discount, market = float(pricing['segment_risk_discount']), float(pricing['no_vig_market_probability'])
    if not math.isfinite(discount) or not 0 <= discount <= 1 or not math.isfinite(market) or not 0 < market < 1:
        raise ValueError('invalid_risk_metadata')
    return {'raw_a': raw, 'selected_final': market + (selected - market) * (1 - discount)}


def collect(conn):
    forecasts = prematch_outcomes(conn)
    predictions = {r['id']: dict(r) for r in conn.execute('SELECT * FROM predictions')}
    matches = {r['id']: dict(r) for r in conn.execute('SELECT * FROM matches')}
    first = {r['match_id']: dict(r) for r in conn.execute(
        "SELECT * FROM odds_snapshots WHERE id IN (SELECT MIN(id) FROM odds_snapshots "
        "WHERE market='match_winner' GROUP BY match_id)")}
    counts, excluded, rows = Counter(), [], []
    counts['all_saved_predictions'] = len(predictions)
    counts['agreed_completed_first_forecasts'] = len(forecasts)
    for forecast in forecasts:
        match_id = forecast['match_id']
        p, m = predictions[forecast['prediction_id']], matches[match_id]
        reason = None
        start, written = instant(forecast['start_time_utc']), instant(p['created_at'])
        quote = first.get(match_id)
        if m['source_provider'] == 'mock':
            reason = 'mock_fixture'
        elif m.get('fixture_status', 'ACTIVE') != 'ACTIVE':
            reason = 'inactive_fixture'
        elif start is None or written is None or not written < start:
            reason = 'unverifiable_forecast_clock'
        else:
            reason = price_exclusion(quote, start, written)
        if reason:
            counts['excluded_' + reason] += 1
            excluded.append({'match_id': match_id, 'prediction_id': p['id'], 'reason': reason})
            continue
        payload = None
        try:
            payload = json.loads(p['pricing_json'])
            pricing = payload['pricing']
            reconstructed = replay(pricing)
            error = abs(reconstructed['selected_final'] - float(p['model_probability']))
            if error > 1e-6:
                raise ValueError('final_probability_mismatch')
            expected_side = 'player_a' if p['selection_player_id'] == m['player_a_id'] else 'player_b'
            if pricing['selection_side'] != expected_side:
                raise ValueError('selection_identity_mismatch')
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            parity_reason = str(exc) if isinstance(exc, ValueError) else 'missing_or_invalid_metadata'
            counts['parity_excluded_' + parity_reason] += 1
            reconstructed, error = None, None
        else:
            parity_reason = None
            counts['faithful_parity'] += 1
        # Fixture evidence is a separate criterion, never inferred by parity.
        try:
            frozen = payload.get('fixture_at_prediction')
        except (UnboundLocalError, AttributeError):
            frozen = None
        frozen_ok = isinstance(frozen, dict) and all(
            frozen.get(k) == m[k] for k in ('id', 'player_a_id', 'player_b_id', 'match_date', 'start_time_utc')
        ) and frozen.get('fixture_status') == 'ACTIVE'
        a_odds, b_odds = float(quote['player_a_odds']), float(quote['player_b_odds'])
        implied_a, implied_b = 1 / a_odds, 1 / b_odds
        rows.append({'match_id': match_id, 'prediction_id': p['id'], 'quote_id': quote['id'],
                     'bookmaker': quote['bookmaker'], 'tour': m['tour'], 'date': m['match_date'],
                     'start_time_utc': forecast['start_time_utc'], 'prediction_created_at': p['created_at'],
                     'player_a_id': m['player_a_id'], 'player_b_id': m['player_b_id'],
                     'outcome_a': int(forecast['winner_player_id'] == m['player_a_id']),
                     'stored_a': forecast['model_p'], 'market_a': implied_a / (implied_a + implied_b),
                     'a_odds': a_odds, 'b_odds': b_odds, 'overround': implied_a + implied_b,
                     'parity_error': error, 'parity_exclusion': parity_reason,
                     'reconstructed': reconstructed, 'frozen_fixture_verified': frozen_ok,
                     'source_provenance_verified': False, 'split': 'SEEN_DEV'})
    counts['timed_market_rows'] = len(rows)
    counts['frozen_fixture_verified'] = sum(r['frozen_fixture_verified'] for r in rows)
    if len({r['match_id'] for r in rows}) != len(rows):
        raise ValueError('multiple independent rows for one match')
    return rows, excluded, dict(counts)


def score(rows):
    if not rows:
        return {'n': 0, 'status': 'NO_ELIGIBLE_ROWS'}
    y = np.array([r['outcome_a'] for r in rows], dtype=float)
    model = np.clip([r['stored_a'] for r in rows], 1e-9, 1-1e-9)
    market = np.clip([r['market_a'] for r in rows], 1e-9, 1-1e-9)
    def ll(p):
        return -y*np.log(p)-(1-y)*np.log1p(-p)
    gains = np.column_stack((ll(market)-ll(model), (market-y)**2-(model-y)**2))
    rng, samples = np.random.default_rng(SEED), []
    for offset in range(0, TRIALS, 50):
        indices = rng.integers(len(rows), size=(min(50, TRIALS-offset), len(rows)))
        samples.extend(gains[indices].mean(axis=1))
    ci = np.quantile(np.array(samples), [.025, .975], axis=0)
    return {'n': len(rows), 'model_ll': float(ll(model).mean()), 'market_ll': float(ll(market).mean()),
            'model_brier': float(np.mean((model-y)**2)), 'market_brier': float(np.mean((market-y)**2)),
            'gain_ll': float(gains[:, 0].mean()), 'gain_brier': float(gains[:, 1].mean()),
            'gain_ll_ci95': ci[:, 0].tolist(), 'gain_brier_ci95': ci[:, 1].tolist()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    conn = readonly(args.db)
    try:
        rows, excluded, counts = collect(conn)
    finally:
        conn.close()
    summaries = {'timed_market': score(rows),
                 'faithful_parity': score([r for r in rows if r['parity_exclusion'] is None]),
                 'frozen_parity': score([r for r in rows if r['parity_exclusion'] is None and r['frozen_fixture_verified']])}
    summary = {'counts': counts, 'metrics': summaries, 'dataset_sha256': digest(args.db),
               'implementation_sha256': digest(Path(__file__)), 'seed': SEED, 'trials': TRIALS,
               'bootstrap_unit': 'match', 'promotion_eligible': False,
               'qualification': 'SEEN_DEV. Saved forecasts of multiple historical versions; not current-model performance. '
                                'Frozen fixture does not prove full raw feature provenance or execution.'}
    write_new(args.output / 'baseline_summary.json', summary)
    write_new(args.output / 'baseline_rows.json', {'rows': rows})
    write_new(args.output / 'excluded_rows.json', {'rows': excluded})
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
