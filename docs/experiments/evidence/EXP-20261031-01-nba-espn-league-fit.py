import glob, json, statistics, sys
sys.path.insert(0, sys.argv[1]); import nba_espn_league as L
refs = {}
for f in sorted(glob.glob('/Users/imac/WongChoiData/Wong Choi NBA Analysis/2026-10-2*/nba_game_data_*.json')) + sorted(glob.glob('/Users/imac/wongchoi-scheduler/2026-10-29 NBA Analysis/nba_game_data_*.json')):
    x = json.load(open(f)); m = x['meta']; ds = m.get('data_sources') or {}
    if (ds.get('team_stats') or {}).get('data_season') != '2026-27': continue
    for a, r in x['team_stats'].items():
        if r.get('PACE') is not None: refs[(m['history_date_to'], a)] = r
G = {dt: L.season_games('2026-27', dt) for dt in {k[0] for k in refs}}
def err(k, base, windows):
    L.possessions = lambda t: k * base(t)
    out = {'PACE': [], 'OFF_RATING': [], 'DEF_RATING': [], 'rank': []}
    for dt in windows:
        t = L.team_advanced(G[dt])
        for (w, a), r in refs.items():
            if w == dt and a in t:
                for f in ('PACE', 'OFF_RATING', 'DEF_RATING'): out[f].append(t[a][f] - r[f])
                out['rank'].append(abs(t[a]['DEF_RANK'] - r['DEF_RANK']))
    return {f: (round(statistics.mean(v), 2), round(statistics.median([abs(x) for x in v]), 2)) for f, v in out.items()}, len(out['rank'])
wins = sorted(G, key=lambda d: d[6:]+d[:5]); dev = [w for w in wins if w <= '10/24/2026']; test = [w for w in wins if w > '10/24/2026']
print('dev', dev, 'test', test)
for name, base in (('totalTOV', lambda t: t['FGA'] + .44*t['FTA'] - t['OREB'] + t['TOV']),
                   ('playerTOV', lambda t: t['FGA'] + .44*t['FTA'] - t['OREB'] + t.get('PLAYER_TOV', t['TOV']))):
    best = min((abs(err(k/1000, base, dev)[0]['PACE'][0]), k/1000) for k in range(960, 1001, 2))[1]
    print(name, 'k', best, 'dev', err(best, base, dev), 'TEST', err(best, base, test), 'TEST k=1', err(1.0, base, test))
