"""EXP-20261101-01: ESPN play-by-play lineups vs stored nba.com player advanced.

usage: python3 EXP-20261101-01-nba-pbp-lineup-parity.py <.agents/skills/nba> [scale] [dev|test|all]
dev = history_date_to 10/21..10/24 (fit), test = 10/25..10/27 (check).
Reference: scheduler nba_game_data_*.json, 2026-27 player_advanced straight from
nba_api (not espn_box, not a 2025-26 fill), one row per (history_date_to, player).
"""
import glob, json, statistics, sys
sys.path.insert(0, sys.argv[1])
import nba_espn_league as L, nba_espn_lineups as P
scale = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0
part = sys.argv[3] if len(sys.argv) > 3 else 'all'
files = sorted(glob.glob('/Users/imac/WongChoiData/Wong Choi NBA Analysis/2026-10-*/nba_game_data_*.json')) \
    + sorted(glob.glob('/Users/imac/wongchoi-scheduler/2026-10-* NBA Analysis/nba_game_data_*.json'))
refs = {}
for f in files:
    x = json.load(open(f)); m = x['meta']; src = (m.get('data_sources') or {}).get('player_advanced') or {}
    if src.get('data_season') != '2026-27' or src.get('source') == 'espn_box':
        continue
    filled = set(map(str, src.get('filled_keys') or []))
    for team, rows in (x.get('players') or {}).items():
        for p in rows:
            adv = p.get('advanced') or {}
            if str(p.get('player_id')) in filled or adv.get('DEF_RATING') is None:
                continue
            refs[(m['history_date_to'], str(p['player_id']))] = (adv, p.get('name'))
index = {k: str(v) for k, v in L.nba_name_index().items()}
windows = sorted({k[0] for k in refs}, key=lambda d: d[6:] + d[:5])
windows = [w for w in windows if part == 'all' or (part == 'dev') == (w <= '10/24/2026')]
quality = {}
diffs = {f: [] for f in ('OFF_RATING', 'DEF_RATING', 'PACE', 'NET_RATING')}
pairs = {f: [] for f in diffs}
unmatched = []
by_min = []
missing = 0
for w in windows:
    games = P.season_lineups('2026-27', w)
    for g in games:
        quality[id(g)] = g['quality']
    table = P.player_ratings(games, index, possession_scale=scale)
    for (ww, pid), (adv, name) in refs.items():
        if ww != w:
            continue
        mine = table.get(pid)
        if mine is None:
            missing += 1; unmatched.append(name); continue
        for f in diffs:
            if adv.get(f) is not None:
                diffs[f].append(mine[f] - adv[f]); pairs[f].append((mine[f], adv[f]))
        by_min.append((mine['ON_COURT_MIN'], abs(mine['DEF_RATING'] - adv['DEF_RATING'])))
def corr(x, y):
    mx, my = statistics.mean(x), statistics.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (len(x) * statistics.pstdev(x) * statistics.pstdev(y))
def q(v, p):
    v = sorted(abs(x) for x in v); return round(v[min(len(v) - 1, int(p * len(v)))], 2)
print('windows', windows, 'rows', len(refs), 'unmatched', missing, 'scale', scale)
for f, v in diffs.items():
    print(f, 'n', len(v), 'median|Δ|', round(statistics.median([abs(x) for x in v]), 2), 'p90', q(v, .9), 'bias', round(statistics.mean(v), 2))
for f, v in pairs.items():
    print(f, 'pearson r', round(corr([a for a, _ in v], [b for _, b in v]), 3),
          'nba.com SD', round(statistics.pstdev([b for _, b in v]), 2))
for lo, hi in ((0, 30), (30, 100), (100, 10**6)):
    v = [d for m, d in by_min if lo <= m < hi]
    if v: print(f'DEF_RATING on-court min [{lo},{hi}) n={len(v)} median {statistics.median(v):.2f} p90 {q(v,.9)}')
import collections
print('unmatched names (top)', collections.Counter(unmatched).most_common(8))
qs = list(quality.values())
print('games', len(qs), 'bad periods', sum(len(x['bad_periods']) for x in qs), 'of', sum(x['periods'] for x in qs),
      'poss skipped', sum(x['possessions_skipped'] for x in qs), 'of', sum(x['possessions'] for x in qs),
      'subs unmatched', sum(x['subs_unmatched'] for x in qs), 'of', sum(x['subs'] for x in qs))
