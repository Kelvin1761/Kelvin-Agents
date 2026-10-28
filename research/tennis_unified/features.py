"""Causal delayed-source features for the unified SEEN_DEV experiment."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import hashlib
import heapq
import json
import math
import statistics

SERVE_ARMS = ('000', 'R', 'E', 'S', 'RE', 'RS', 'ES', 'RES')
BASE_FEATURES = ('elo', 'rank', 'rank_missing', 'count', 'opponent_low', 'opponent_high', 'history_missing')


def sigmoid(x):
    return 1 / (1 + math.exp(-max(-40., min(40., x))))


def logit(p):
    p = max(1e-6, min(1 - 1e-6, p))
    return math.log(p / (1 - p))


class Rating:
    """Same frozen history control update as EXP-20261027-07, not B_live."""
    def __init__(self):
        self.values = {}
        self.counts = Counter()

    def get(self, player, surface=''):
        return self.values.get((player, surface), self.values.get((player, ''), 1500.))

    def effective(self, player, surface, dynamic=False):
        n = self.counts[(player, surface)]
        w = n / (n + 20.) if dynamic else .65
        return (1 - w) * self.get(player) + w * self.get(player, surface)

    def feature(self, a, b, surface, dynamic=False):
        return math.log(10) / 400 * (self.effective(a, surface, dynamic) - self.effective(b, surface, dynamic))

    def update(self, a, b, surface, target):
        before = [(s, self.get(a, s), self.get(b, s)) for s in ('', surface)]
        for s, ra, rb in before:
            expected = sigmoid((ra - rb) * math.log(10) / 400)
            for player, value, residual in ((a, ra, target - expected), (b, rb, expected - target)):
                key = (player, s)
                self.values[key] = value + 120 / (self.counts[key] + 5) ** .4 * residual
                self.counts[key] += 1


def warmup_priors(rows):
    totals, exposures, keys = defaultdict(lambda: [0, 0]), defaultdict(list), []
    for r in rows:
        if r['date'] >= '2021-01-01' or r['available'] >= '2021-01-01':
            continue
        keys.append(r['key'])
        for label in ('a_points', 'b_points'):
            value = r[label]
            if value:
                totals[r['tour']][0] += value[0]
                totals[r['tour']][1] += value[1]
                exposures[r['tour']].append(value[1])
    if set(totals) != {'ATP', 'WTA'} or any(n <= 0 for _, n in totals.values()):
        raise ValueError('missing fixed pre-2021 tour prior exposure')
    return {'by_tour': {t: {'serve': v[0] / v[1], 'won': v[0], 'points': v[1],
                            'reference_exposure': statistics.median(exposures[t])} for t, v in totals.items()},
            'source_keys_sha256': hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest(),
            'availability_cutoff': '2021-01-01', 'publication_clock_verified': False}


def profiles(history, forecast_date, prior):
    """Eight factorial profiles. E-off weights make equal-match averages.

    The fixed warmup reference exposure gives E-off denominators point-equivalent
    units, so S=100 has a declared meaning without changing the unshrunk mean.
    """
    day = date.fromisoformat(forecast_date)
    sums = {arm: [[0., 0.], [0., 0.]] for arm in SERVE_ARMS}
    for h in history[-25:]:
        if h['available'] >= forecast_date:
            raise ValueError('future history reached profile')
        decay = 2 ** (-(day - date.fromisoformat(h['date'])).days / 180.)
        for role, name in enumerate(('serve', 'return')):
            pair = h[name]
            if pair is None:
                continue
            won, total = pair
            for arm in SERVE_ARMS:
                weight = decay if 'R' in arm else 1.
                if 'E' not in arm:
                    weight *= prior['reference_exposure'] / total
                sums[arm][role][0] += weight * won
                sums[arm][role][1] += weight * total
    result = {}
    for arm in SERVE_ARMS:
        values = []
        for role, (won, total) in enumerate(sums[arm]):
            mu = prior['serve'] if role == 0 else 1 - prior['serve']
            if 'S' in arm:
                won, total = won + 100 * mu, total + 100
            values.append(won / total if total else mu)
        result[arm] = values
    return result


def make_features(rows, priors=None):
    if rows != sorted(rows, key=lambda r: (r['date'], r['key'])):
        raise ValueError('cohort order must be frozen')
    priors = priors or warmup_priors(rows)
    rating, queue, history, meetings = Rating(), [], defaultdict(list), defaultdict(list)
    ranks, result, state_hash, maximum_available = {}, [], hashlib.sha256(), None
    for seq, r in enumerate(rows):
        while queue and queue[0][0] < r['date']:
            _, _, past, context = heapq.heappop(queue)
            a, b = (past['tour'], past['a']), (past['tour'], past['b'])
            rating.update(a, b, past['surface'], past['y'])
            state_hash.update(json.dumps([past, context], sort_keys=True).encode())
            maximum_available = past['available']
            meetings[(a, b)].append({'key': past['key'], 'y': past['y'], 'p': context['p']})
            for player, side, other, own_elo, opp_elo in (
                    (a, 'a', 'b', context['elo_a'], context['elo_b']),
                    (b, 'b', 'a', context['elo_b'], context['elo_a'])):
                own_points, opp_points = past[side + '_points'], past[other + '_points']
                history[player].append({'key': past['key'], 'date': past['date'], 'available': past['available'],
                                        'serve': own_points,
                                        'return': None if opp_points is None else [opp_points[1] - opp_points[0], opp_points[1]],
                                        'opponent_elo': opp_elo, 'relative_strength': (opp_elo - own_elo) / 400})
                if past[side + '_rank'] is not None:
                    ranks[player] = past[side + '_rank']
        a, b = (r['tour'], r['a']), (r['tour'], r['b'])
        fixed = rating.feature(a, b, r['surface'])
        context = {'p': sigmoid(fixed), 'elo_a': rating.get(a), 'elo_b': rating.get(b)}
        if r['date'] >= '2021-01-01':
            n_a, n_b = rating.counts[(a, '')], rating.counts[(b, '')]
            def summary(player):
                recent = history[player][-10:]
                n = len(recent)
                return (sum(h['opponent_elo'] < 1400 for h in recent) / n if n else 0.,
                        sum(h['opponent_elo'] > 1600 for h in recent) / n if n else 0.,
                        sum(h['relative_strength'] for h in recent) / n if n else 0.)
            sa, sb = summary(a), summary(b)
            ra, rb = ranks.get(a), ranks.get(b)
            x = {'elo': fixed, 'surface_dynamic': rating.feature(a, b, r['surface'], True),
                 'rank': math.log(rb or 1) - math.log(ra or 1) if ra and rb else 0.,
                 'rank_missing': float(ra is None) - float(rb is None),
                 'count': math.log1p(n_a) - math.log1p(n_b),
                 'opponent_low': sa[0] - sb[0], 'opponent_high': sa[1] - sb[1],
                 'history_missing': float(not n_a) - float(not n_b), 'strength': sa[2] - sb[2]}
            pair = meetings[(a, b)]
            x['h2h_raw'] = sum(2 * h['y'] - 1 for h in pair) / len(pair) if pair else 0.
            x['h2h_residual'] = sum(h['y'] - h['p'] for h in pair) / (len(pair) + 5)
            pa = profiles(history[a], r['date'], priors['by_tour'][r['tour']])
            pb = profiles(history[b], r['date'], priors['by_tour'][r['tour']])
            for arm in SERVE_ARMS:
                for role, name in enumerate(('serve', 'return')):
                    x[name + '_' + arm] = logit(pa[arm][role]) - logit(pb[arm][role])
            result.append({'key': r['key'], 'date': r['date'], 'available': r['available'], 'tour': r['tour'],
                           'surface': r['surface'], 'level': r['level'], 'best_of': r['best_of'], 'y': r['y'],
                           'n_a': n_a, 'n_b': n_b, 'h2h_n': len(pair),
                           'a_profile_n': sum(h['serve'] is not None for h in history[a][-25:]),
                           'b_profile_n': sum(h['serve'] is not None for h in history[b][-25:]),
                           'state_sha256': state_hash.hexdigest(), 'max_history_available': maximum_available,
                           'a_history_keys': [h['key'] for h in history[a][-25:]],
                           'b_history_keys': [h['key'] for h in history[b][-25:]],
                           'h2h_keys': [h['key'] for h in pair], 'x': x})
        heapq.heappush(queue, (r['available'], seq, r, context))
    return result, priors
