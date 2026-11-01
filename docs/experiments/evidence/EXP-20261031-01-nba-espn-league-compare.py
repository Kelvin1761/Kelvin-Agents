import glob, json, os, statistics, sys
S = sys.argv[1]
ROOTS = {os.path.basename(d)[:10]: d for d in glob.glob('/Users/imac/WongChoiData/Wong Choi NBA Analysis/2026-10-2*')}
ROOTS['2026-10-29'] = '/Users/imac/wongchoi-scheduler/2026-10-29 NBA Analysis'
key = lambda l: (l['player'], l['market'], l['line'])
res = {}
for cfg in ('B', 'C'):
    diffs, flips, n_games, legs_total = [], {t: 0 for t in (.5, .6, .7, .8)}, 0, 0
    above = {t: 0 for t in flips}
    for f in sorted(glob.glob(f'{S}/replay/*_{cfg}.md.market_legs.json')):
        base = os.path.basename(f); day = base[:10]; tag = base[11:-len(f'_{cfg}.md.market_legs.json')]
        orig = f"{S}/replay/{day}_{tag}_A.md.market_legs.json"
        A = {key(l): l for l in json.load(open(orig))['legs']}
        Bl = {key(l): l for l in json.load(open(f))['legs']}
        n_games += 1
        for k in set(A) & set(Bl):
            a, b = A[k]['p_final'], Bl[k]['p_final']
            if a is None or b is None: continue
            legs_total += 1; diffs.append(b - a)
            for t in flips:
                above[t] += a >= t
                flips[t] += (a >= t) != (b >= t)
    ad = sorted(abs(d) for d in diffs)
    res[cfg] = dict(games=n_games, legs=legs_total, mean_shift=round(statistics.mean(diffs), 4),
                    median_abs=round(statistics.median(ad), 4), p90_abs=round(ad[int(.9 * (len(ad) - 1))], 4),
                    max_abs=round(ad[-1], 4), changed=sum(x > 1e-9 for x in ad),
                    flips={f'{t:.0%}': f'{flips[t]}/{above[t]}' for t in flips})
print(json.dumps(res, indent=1, ensure_ascii=False))
