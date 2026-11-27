#!/usr/bin/env python3
"""Read-only NBA B2 snapshot replay; stops if historical selection cannot be reproduced."""
import json
import itertools
import math
import random
from collections import Counter
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / '.agents/skills/nba'))
from nba_engine import banker, legs

ROOTS = [Path('/Users/imac/wongchoi-scheduler'), Path.home() / 'WongChoiData/Wong Choi NBA Analysis']

def read(path):
    return json.loads(path.read_text())

def identity(items):
    return sorted((x['player'], x['market'], float(x['line'])) for x in items)

def legkey(tag, leg):
    return (tag, leg.player, legs.MARKET[leg.stat], float(leg.line))


def alternative(pool, phase):
    for rule in (banker.STRICT, banker.FALLBACK):
        candidates = banker.pool(pool, rule, phase)[:25]
        best = None
        for n in range(banker.MIN_LEGS, banker.MAX_LEGS + 1):
            for combo in itertools.combinations(candidates, n):
                if not banker.allowed(combo) or max(Counter(x.team for x in combo).values()) > 3:
                    continue
                price = banker.product(combo)
                lo, hi = rule['target']
                if lo <= price <= hi * banker.TOLERANCE:
                    rank = (math.prod(x.p_final for x in combo), -n, price)
                    if best is None or rank > best[0]:
                        best = (rank, combo)
        if best:
            return list(best[1])
    return []


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def wilson(h, n):
    if not n:
        return None
    z = 1.959963984540054
    p = h / n
    center = (p + z*z/(2*n))/(1+z*z/n)
    half = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n))/(1+z*z/n)
    return [center-half, center+half]


def metrics(games):
    result = {}
    for variant in 'ABC':
        selected = [(g, g['variants'][variant]) for g in games if g['variants'][variant]]
        complete = [(g, c) for g, c in selected if all(legkey(g['tag'], l) in g['settlements'] for l in c)]
        leg_rows = [(l, g['settlements'][legkey(g['tag'], l)]) for g, c in selected for l in c if legkey(g['tag'], l) in g['settlements']]
        hits = sum(all(g['settlements'][legkey(g['tag'], l)] for l in c) for g,c in complete)
        all_legs = [l for _, c in selected for l in c]
        result[variant] = {'games_with_combo':len(selected), 'fully_settled':len(complete), 'all_hit':hits, 'all_hit_rate':hits/len(complete) if complete else None, 'wilson_95':wilson(hits,len(complete)), 'settled_legs':len(leg_rows), 'leg_hit_rate':mean([y for _,y in leg_rows]), 'mean_p_final':mean([x.p_final for x in all_legs]), 'mean_p_legacy':mean([x.p_legacy for x in all_legs]), 'mean_leg_price_product':mean([banker.product(c) for _,c in selected])}
    paired = {}
    for variant in 'BC':
        diff = [(g,g['variants']['A'],g['variants'][variant]) for g in games if {legkey(g['tag'],x) for x in g['variants']['A']} != {legkey(g['tag'],x) for x in g['variants'][variant]}]
        complete = [(g,a,b) for g,a,b in diff if a and b and all(legkey(g['tag'],x) in g['settlements'] for x in a+b)]
        outcomes = [(all(g['settlements'][legkey(g['tag'],x)] for x in a), all(g['settlements'][legkey(g['tag'],x)] for x in b)) for g,a,b in complete]
        paired[variant] = {'different_games':len(diff), 'both_fully_settled':len(complete), 'A_all_hit':sum(a for a,b in outcomes), 'other_all_hit':sum(b for a,b in outcomes), 'A_only_hit':sum(a and not b for a,b in outcomes), 'other_only_hit':sum(b and not a for a,b in outcomes)}
    return result, paired


def calibration(games):
    rows = []
    for g in games:
        seen = set()
        for l in g['pool']:
            key = legkey(g['tag'], l)
            if key not in seen and key in g['settlements']:
                rows.append((g['day'], l.p_final, l.p_legacy, g['settlements'][key]))
                seen.add(key)
    def loss(p,y):
        p = min(1-1e-15,max(1e-15,p))
        return -(y*math.log(p)+(1-y)*math.log(1-p))
    out = {'n':len(rows), 'actual_hit_rate':mean([y for _,_,_,y in rows])}
    for name, index in [('p_final',1),('p_legacy',2)]:
        out[name] = {'log_loss':mean([loss(r[index],r[3]) for r in rows]), 'brier':mean([(r[index]-r[3])**2 for r in rows]), 'bins':[]}
        for lo,hi in [(0.6,0.7),(0.7,0.8),(0.8,0.9),(0.9,1.0)]:
            group = [r for r in rows if lo <= r[index] < hi or (hi == 1.0 and r[index] == 1.0)]
            out[name]['bins'].append({'range':[lo,hi], 'n':len(group), 'mean_probability':mean([r[index] for r in group]), 'hit_rate':mean([r[3] for r in group])})
    days = sorted(set(r[0] for r in rows))
    clusters = {d:[loss(p,y)-loss(q,y) for day,p,q,y in rows if day == d] for d in days}
    rng = random.Random(20261127)
    samples = []
    for _ in range(2000):
        sample = [x for d in rng.choices(days,k=len(days)) for x in clusters[d]]
        samples.append(mean(sample))
    samples.sort()
    out['log_loss_difference_final_minus_legacy'] = out['p_final']['log_loss'] - out['p_legacy']['log_loss']
    out['cluster_bootstrap_95'] = [samples[49],samples[1949]]
    return out


def main():
    matched = total = 0
    missing, mismatches, snapshots, games = [], [], [], []
    for i in range(15):
        day = (date(2026, 11, 12) + timedelta(days=i)).isoformat()
        found = []
        for root in ROOTS:
            for path in root.glob(f'{day} NBA Analysis*/_prediction_snapshots/*/manifest.json'):
                m = read(path)
                if m.get('snapshot_role') == 'production' and m.get('target_date') == day:
                    found.append((m['created_at'], str(path), m))
        if not found:
            missing.append(day)
            continue
        _, name, manifest = min(found)
        folder = Path(name).parent
        snapshots.append({'date': day, 'manifest': name})
        ledger = Path.home() / f'WongChoiData/NBA_Market_Eval/ledger/{day}.jsonl'
        settlements = {}
        if ledger.exists():
            for line in ledger.read_text().splitlines():
                row = json.loads(line)
                if row.get('row_type') == 'settlement' and row.get('y') in (0,1):
                    key = (row['game_tag'], row['player'], row['market'], float(row['line']))
                    if key in settlements and settlements[key] != row['y']:
                        raise ValueError(f'Conflicting settlements: {day} {key}')
                    settlements[key] = row['y']
        else:
            missing.append(f'{day}: missing ledger')
        for tag in manifest.get('game_tags', []):
            odds = folder / f'Sportsbet_Odds_{tag}.json'
            data = folder / f'nba_game_data_{tag}.json'
            side = folder / f'Game_{tag}_Full_Analysis.md.market_legs.json'
            if not all(p.exists() for p in (odds, data, side)):
                missing.append(f'{day} {tag}: missing input or sidecar')
                continue
            package = read(data)
            pool, _ = legs.build_legs(read(odds), package)
            combo, rule = banker.select_b2(pool, (package.get('meta') or {}).get('season_phase'))
            phase = (package.get('meta') or {}).get('season_phase')
            original_edge = banker.edge
            try:
                banker.edge = lambda l: round(100 * (l.p_final or 0.0) - round(100 / l.price, 2), 2)
                combo_b, _ = banker.select_b2(pool, phase)
            finally:
                banker.edge = original_edge
            combo_c = alternative(pool, phase)
            union = banker.pool(pool, banker.STRICT, phase) + banker.pool(pool, banker.FALLBACK, phase)
            games.append({'day':day, 'tag':tag, 'variants':{'A':combo,'B':combo_b,'C':combo_c}, 'pool':union, 'settlements':settlements})
            s = read(side)
            candidates = [x for x in s.get('review_candidates', []) if x.get('candidate_id') == 'steady']
            stored = candidates[0]['legs'] if candidates else (s.get('combos') or [{}])[0].get('legs', [])
            # A nonempty proposal without a stored research record is not verifiable.
            if not candidates and not s.get('combos') and s.get('selection_diagnostics', {}).get('rule') not in ('none', None):
                missing.append(f'{day} {tag}: proposal not recorded')
                continue
            actual = identity([{'player': x.player, 'market': legs.MARKET[x.stat], 'line': x.line} for x in combo])
            expected = identity(stored)
            total += 1
            if actual == expected:
                matched += 1
            else:
                mismatches.append({'date': day, 'game': tag, 'current_rule': rule, 'stored_rule': s.get('selection_diagnostics', {}).get('rule'), 'current': actual, 'stored': expected})
    result = {'status': 'stopped_reproduction_failed' if not total or matched / total < .9 else 'reproduction_passed_replay_not_implemented', 'reproduced': matched, 'total': total, 'missing': missing, 'mismatches': mismatches, 'snapshots': snapshots}
    if total and matched / total >= .9:
        result['status'] = 'exploratory'
        result['variants'], result['paired'] = metrics(games)
        result['calibration'] = calibration(games)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print('\n| Reproduced | Comparable games |')
    print('|---:|---:|')
    print(f'| {matched} | {total} |')
    if result['status'] == 'exploratory':
        print('\n| Variant | Games | Settled | All hit | Leg hit rate |')
        print('|---|---:|---:|---:|---:|')
        for name, v in result['variants'].items():
            print(f"| {name} | {v['games_with_combo']} | {v['fully_settled']} | {v['all_hit']} | {v['leg_hit_rate']:.3f} |")

if __name__ == '__main__':
    main()
