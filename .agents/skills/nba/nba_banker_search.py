"""Opt-in, bounded actual-price research. Never feeds formal selection or ROI."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from itertools import combinations
import math

from nba_sgm_quote import legs_identity, quote_legs

VERSION = 'banker-search-v1'
SHORTLIST = 18
QUOTE_BUDGET = 12


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def accuracy_review(attempts, baseline_key, *, is_current):
    """Rerank the same verified quotes, never refit probabilities or recommend bets."""
    eligible = []
    for row in attempts:
        legs = row.get('legs') or []
        probabilities = [leg.get('model_probability') for leg in legs]
        if (not row.get('quote_verified_at_capture') or not row.get('legs_sha256')
                or not _finite(row.get('actual_price')) or row['actual_price'] < 2
                or not _finite(row.get('adjusted_joint_probability'))
                or not 0 < row['adjusted_joint_probability'] < 1
                or not 2 <= len(legs) <= 4
                or any(not _finite(p) or not 0 < p < 1 for p in probabilities)):
            continue
        eligible.append(row)
    eligible.sort(key=lambda r: (-r['adjusted_joint_probability'],
                                -min(c['model_probability'] for c in r['legs']),
                                len(r['legs']), r['legs_sha256']))

    def describe(row):
        if row is None:
            return None
        result = deepcopy(row)
        result['weakest_leg_probability'] = min(c['model_probability'] for c in row['legs'])
        result['weakest_legs'] = [deepcopy(c) for c in row['legs']
                                 if c['model_probability'] == result['weakest_leg_probability']]
        result['formal_eligible'] = False
        return result

    current = [row for row in eligible if is_current(row)]
    baseline = next((r for r in eligible if r['legs_sha256'] == baseline_key), None)
    return {'version': 'banker-accuracy-review-v1', 'analysis_only': True,
            'status': 'NEEDS_MORE_TESTING',
            'decision': 'OBSERVE', 'promotion_allowed': False,
            'probabilities_refitted': False, 'eligible_quoted_combinations': len(eligible),
            'baseline_at_capture': describe(baseline),
            'candidate_at_capture': describe(eligible[0] if eligible else None),
            'current_candidate': describe(current[0] if current else None),
            'role_filter_applied': False,
            'note': 'Highest supplied joint probability among existing verified quotes >=2.0 only. '
                    'Capture records are historical evidence, not actionable prices. Negative EV remains visible; '
                    'no formal recommendation, accuracy or profitability claim. No outcomes enter ranking.'}


def audit_search(candidates, odds, *, pool, select, allowed, evaluate, quote, valid_quote):
    """Q0/Q1 isolate prequote EV; Q2 explores more combinations at frozen budget."""
    inputs = deepcopy(candidates)
    cached = {}
    proposals = {}
    attempts = []
    stages = {}
    counts = {}

    def price(legs, rule, stage):
        key = legs_identity(legs)
        if key in cached:
            return cached[key]
        proposed = deepcopy(legs)
        proposals[key] = proposed
        quoted = quote(odds, proposed)
        verified = valid_quote(quoted.quote, odds, proposed)
        metrics = evaluate(quoted if verified else proposed)
        actual = quoted.quote.get('decimal_odds') if verified else None
        ev = metrics.get('combo_ev_pct') if verified else None
        joint = metrics.get('adjusted_joint_prob')
        positive = (verified and _finite(actual) and actual >= 2 and _finite(ev) and ev > 0
                    and _finite(joint) and 0 < joint < 1)
        row = {'legs_sha256': key, 'selection_rule': rule, 'first_stage': stage,
               'decision': 'OBSERVE', 'analysis_only': True, 'positive_ev_candidate': positive,
               'quote_verified_at_capture': verified, 'sgm_quote': dict(quoted.quote),
               'actual_price': actual, 'expected_value': ev/100 if _finite(ev) else None,
               'adjusted_joint_probability': joint,
               'legs': [dict(quote_legs([c])[0], team=c['team'], category=c['category'],
                             model_probability=c['estimated_prob']/100, selection=c['desc'],
                             probability_model_id=c.get('probability_model_id'),
                             l10_hit_rate=c.get('hit_l10'), l5_hit_rate=c.get('hit_l5'),
                             cov=c.get('cov'), average_minutes=c.get('min_avg')) for c in proposed]}
        cached[key] = row
        attempts.append(row)
        return row

    for name, require_ev in (('Q0', True), ('Q1', False)):
        proposal = select(deepcopy(inputs), require_leg_ev=False, require_combo_ev=require_ev)
        row = price(proposal, getattr(proposal, 'selection_rule', None), name) if proposal else None
        stages[name] = {'proposal_found': bool(proposal), 'positive_ev_candidate': bool(row and row['positive_ev_candidate']),
                        'candidate': row}

    # Each tier gets the same fixed shortlist; never filter on product price/EV.
    queues = []
    all_seen = set()
    for rule in ('banker', 'banker_fallback'):
        eligible = pool(deepcopy(inputs), rule, require_leg_ev=False)
        eligible = [c for c in eligible if _finite(c.get('estimated_prob')) and 0 < c['estimated_prob'] < 100
                    and _finite(c.get('edge')) and _finite(c.get('odds')) and c['odds'] > 1]
        eligible.sort(key=lambda c: (-c['estimated_prob'], -c['edge'], c['odds'], c['desc']))
        shortlist = eligible[:SHORTLIST]
        buckets = {n: [] for n in (2, 3, 4)}
        for n in buckets:
            for combo in combinations(shortlist, n):
                if not allowed(combo) or max(Counter(c['team'] for c in combo).values()) > 3:
                    continue
                key = legs_identity(combo)
                if key in all_seen:
                    continue
                all_seen.add(key)
                metrics = evaluate(combo)
                proxy = metrics['adjusted_joint_prob'] * math.prod(c['odds'] for c in combo)-1
                if not _finite(proxy):
                    continue
                rank = (-proxy, tuple(sorted(c['desc'] for c in combo)))
                buckets[n].append((rank, key, list(combo)))
        for bucket in buckets.values():
            bucket.sort(key=lambda item: item[0])
        counts[rule] = {'eligible_legs': len(eligible), 'shortlisted_legs': len(shortlist),
                        'shortlist_truncated': len(eligible) > SHORTLIST,
                        'legal_unique_combinations': sum(map(len, buckets.values())),
                        'by_leg_count': {str(n): len(b) for n, b in buckets.items()}}
        # Fixed round-robin leg-count coverage, strict tier before fallback.
        for index in range(max(map(len, buckets.values()), default=0)):
            for n in (2, 3, 4):
                if index < len(buckets[n]):
                    queues.append((rule, buckets[n][index]))
    extra = 0
    for rule, (_, key, combo) in queues:
        if key in cached:
            continue
        if extra == QUOTE_BUDGET:
            break
        price(combo, rule, 'Q2')
        extra += 1
    # Include Q0/Q1 as incumbent candidates, so broader search retains them.
    positive = [r for r in attempts if r['positive_ev_candidate']]
    positive.sort(key=lambda r: (-r['expected_value'], -r['adjusted_joint_probability'], r['legs_sha256']))
    # Validate freshness again: a long quote round must not retain expired winners.
    current_positive = []
    for row in positive:
        source_legs = next((legs for _, (_, key, legs) in queues if key == row['legs_sha256']), None)
        if source_legs is None:
            # Incumbents may sit outside the bounded shortlist.
            source_legs = [{'player': c['player'], 'category': c['category'], 'line_val': c['line'],
                            'side': c['side']} for c in row['legs']]
        if valid_quote(row['sgm_quote'], odds, source_legs):
            current_positive.append(row)
    stages['Q2'] = {'positive_ev_candidate': bool(current_positive),
                    'candidate': current_positive[0] if current_positive else None,
                    'positive_candidates_at_capture': len(positive),
                    'positive_candidates_still_current': len(current_positive)}
    remaining = sum(key not in cached for _, (_, key, _) in queues)
    incumbent = stages['Q1']['candidate']
    accuracy = accuracy_review(attempts, incumbent['legs_sha256'] if incumbent else None,
                               is_current=lambda row: valid_quote(row['sgm_quote'], odds,
                                                                 proposals[row['legs_sha256']]))
    return {'version': VERSION, 'analysis_only': True, 'decision': 'OBSERVE',
            'status': 'NEEDS_MORE_TESTING', 'promotion_allowed': False,
            'evidence_scope': 'engineering_preview_not_forward_profit',
            'captured_at': datetime.now(timezone.utc).isoformat(),
            'event_id': odds.get('sportsbet_event_id'), 'event_start_time': odds.get('event_start_time'),
            'limits': {'shortlist_per_tier': SHORTLIST, 'new_quote_budget': QUOTE_BUDGET},
            'search_counts': counts, 'new_search_quotes': extra, 'unique_quotes': len(attempts),
            'unpriced_combinations': remaining, 'quote_budget_exhausted': extra == QUOTE_BUDGET and remaining > 0,
            'stages': stages, 'quote_attempts': attempts, 'accuracy_review': accuracy,
            'note': 'Bounded search; unpriced combinations remain unknown. Positive means model-estimated EV only. '
                    'No profitability claim or formal recommendation; expired winners are excluded.'}
