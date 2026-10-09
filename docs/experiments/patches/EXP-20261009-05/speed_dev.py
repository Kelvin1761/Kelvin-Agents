"""Speed-figure redevelopment — DEV ONLY (targets < 2026-09-27; the post-09-27 window is the
blind terminal of EXP-20260927-02 and must not be read)."""
import sys, json, random, statistics, csv, re
from collections import defaultdict
from pathlib import Path
SCRIPTS = Path(sys.argv[1]); sys.path.insert(0, str(SCRIPTS))
import au_speed_venue_audit as A
ROOT = Path(sys.argv[2]); CUT = '2026-09-27'; CLEAN_FROM = '2026-06-06'

def figures(block, standards, target_date):
    base, going, _ = standards
    out = []
    for line in block.splitlines():
        run = A.parse_run(line)
        if run is None or run['date'] >= target_date:
            continue
        std = base.get((run['track'], run['distance']))
        if std is None:
            continue
        spl = 2.4 / (run['distance'] / run['winning_time'])
        own = run['winning_time'] + run['margin'] * spl
        adj = own - std - going.get(run['condition'], 0.0)
        out.append((run['date'], run['distance'], -adj / (run['distance'] / 1000.0)))
    return sorted(out, reverse=True)  # newest first

def variants(figs, today_dist):
    v = {}
    vals = [f for _, _, f in figs]
    v['best3'] = sum(sorted(vals)[-3:]) / 3 if len(vals) >= 3 else None
    v['best3_min2'] = (sum(sorted(vals)[-3:]) / min(3, len(vals))) if len(vals) >= 2 else None
    v['last3'] = statistics.mean(vals[:3]) if len(vals) >= 3 else None
    w = [1.0, 0.8, 0.64, 0.51, 0.41, 0.33]
    if len(vals) >= 2:
        ws = w[:min(6, len(vals))]
        v['recency'] = sum(a * b for a, b in zip(vals, ws)) / sum(ws)
    else:
        v['recency'] = None
    near = [f for d, dist, f in figs if today_dist and abs(dist - today_dist) <= 200]
    v['dist_band'] = sum(sorted(near)[-2:]) / min(2, len(near)) if len(near) >= 2 else None
    if vals:
        n = len(vals); top = sorted(vals)[-3:]
        v['shrunk'] = (sum(top) / len(top)) * (n / (n + 2.0))
    else:
        v['shrunk'] = None
    return v

def load():
    obs, _ = A.collect_reference_races(ROOT)
    results = A._historical_results(ROOT)
    races = []
    from sb_backfill_archive import scored_meeting_index
    idx = scored_meeting_index(ROOT)
    target_dates = sorted({A.MEETING_RE.match(n).group(1) for n in idx if A.MEETING_RE.match(n)
                           and CLEAN_FROM <= A.MEETING_RE.match(n).group(1) < CUT})
    stds = A.build_asof_standards(obs, target_dates)
    for name, mdir in sorted(idx.items()):
        m = A.MEETING_RE.match(name)
        if not m: continue
        date, venue = m.group(1), m.group(2).strip()
        if not (CLEAN_FROM <= date < CUT): continue
        actual_by_race = results.get((date, A.norm(venue))); st = stds.get(date)
        if not actual_by_race or st is None: continue
        scoring = defaultdict(dict)
        with open(mdir / 'Meeting_Auto_Scoring.csv', encoding='utf-8-sig') as fh:
            for row in csv.DictReader(fh):
                scoring[int(row['race_number'])][A.norm(row['horse_name'])] = row
        for fg in sorted(mdir.glob('*Formguide.md')):
            text = fg.read_text(encoding='utf-8', errors='replace')
            hdr = A.RE_HDR_DIST.search(text)
            if not hdr: continue
            race_no = int(hdr.group(1))
            dist_m = re.search(r'(\d{3,4})m', text[:300]); today_dist = int(dist_m.group(1)) if dist_m else 0
            actual = actual_by_race.get(race_no); rows = scoring.get(race_no)
            if not actual or not rows: continue
            starts = [x.start() for x in A.RE_RUNNER.finditer(text)]; runners = []
            for i, mt in enumerate(A.RE_RUNNER.finditer(text)):
                end = starts[i + 1] if i + 1 < len(starts) else len(text)
                key = A.norm(mt.group(2)); sr, pos = rows.get(key), actual.get(key)
                if sr is None or pos is None: continue
                figs = figures(text[mt.start():end], st, date)
                runners.append({'n': int(sr['horse_number']), 'score': float(sr['final_rank_score']),
                                'pf': float(sr['pace_figure_score']), 'pos': int(pos), **variants(figs, today_dist)})
            if len(runners) >= 5:
                races.append({'date': date, 'venue': venue, 'race': race_no, 'rows': runners})
    return races

def z(vals):
    av = [v for v in vals if v is not None]
    if len(av) < 2: return [0.0] * len(vals)
    mu = statistics.mean(av); sd = statistics.pstdev(av)
    return [0.0 if (v is None or sd <= 0) else (v - mu) / sd for v in vals]

def resid(sz, pz):
    # within-race residual of speed z on pace_figure z (only where speed present)
    pairs = [(a, b) for a, b in zip(sz, pz) if a != 0.0]
    if len(pairs) < 3: return sz
    mb = statistics.mean(b for _, b in pairs); ma = statistics.mean(a for a, _ in pairs)
    vb = sum((b - mb) ** 2 for _, b in pairs)
    beta = sum((a - ma) * (b - mb) for a, b in pairs) / vb if vb > 0 else 0.0
    return [a - beta * b if a != 0.0 else 0.0 for a, b in zip(sz, pz)]

def metrics(race, key, k, orth=False):
    rows = race['rows']
    if key is None:
        order = sorted(rows, key=lambda r: (-r['score'], r['n']))
    else:
        sz = z([r[key] for r in rows])
        if orth: sz = resid(sz, z([r['pf'] for r in rows]))
        adj = {id(r): r['score'] + k * s for r, s in zip(rows, sz)}
        order = sorted(rows, key=lambda r: (-adj[id(r)], r['n']))
    pos = {r['n']: r['pos'] for r in rows}; top3 = [n for n, p in pos.items() if p <= 3]
    if len(top3) < 3: return None
    m = A.race_metrics([r['n'] for r in order], top3, None, pos, len(rows))
    return (int(m['gold']), int(m['good_positional']), int(m['champion']), int(m['winner_in_top3']))

def boot(d, B=2000, seed=7):
    rng = random.Random(seed); m = len(d)
    s = sorted(sum(d[rng.randrange(m)] for _ in range(m)) / m for _ in range(B))
    return s[int(.025 * B)], s[int(.975 * B) - 1]

races = load()
print('dev races', len(races), races[0]['date'], '..', races[-1]['date'])
cov = {k: sum(1 for r in races for x in r['rows'] if x[k] is not None) / sum(len(r['rows']) for r in races)
       for k in ('best3', 'best3_min2', 'last3', 'recency', 'dist_band', 'shrunk')}
print('coverage', {k: f'{v:.1%}' for k, v in cov.items()})
base = [metrics(r, None, 0) for r in races]
dates = sorted({r['date'] for r in races}); folds = [set(dates[i * len(dates) // 5:(i + 1) * len(dates) // 5]) for i in range(5)]
hi_cov = [i for i, r in enumerate(races) if r['date'] >= '2026-08-17']
out = []
for key in ('best3', 'best3_min2', 'last3', 'recency', 'dist_band', 'shrunk'):
    for k in (0.25, 0.5, 1.0):
        for orth in (False, True):
            cand = [metrics(r, key, k, orth) for r in races]
            idx = [i for i in range(len(races)) if base[i] and cand[i]]
            dg = [cand[i][0] - base[i][0] for i in idx]; dd = [cand[i][1] - base[i][1] for i in idx]
            dc = [cand[i][2] - base[i][2] for i in idx]; dw = [cand[i][3] - base[i][3] for i in idx]
            fpos = sum(1 for f in folds if sum(dg[j] + dd[j] for j, i in enumerate(idx) if races[i]['date'] in f) >= 0)
            hi = [j for j, i in enumerate(idx) if i in set(hi_cov)]
            out.append((key, k, orth, sum(dg), sum(dd), sum(dc), sum(dw), fpos, boot(dg), boot(dd),
                        sum(dg[j] for j in hi), sum(dd[j] for j in hi), len(idx)))
print(f"{'variant':12s} {'k':>4s} orth {'ΔGold':>6s} {'ΔGood':>6s} {'ΔChamp':>6s} {'ΔW@3':>6s} folds  Gold CI           Good CI          | 08-17+ Gold Good")
for r in sorted(out, key=lambda x: -(x[3] + x[4])):
    key, k, orth, g, d, c, w, f, gci, dci, hg, hd, n = r
    print(f"{key:12s} {k:4.2f} {str(orth)[0]:>4s} {g:+6d} {d:+6d} {c:+6d} {w:+6d} {f}/5  [{100*gci[0]:+.2f},{100*gci[1]:+.2f}] [{100*dci[0]:+.2f},{100*dci[1]:+.2f}] | {hg:+d} {hd:+d}   n={n}")
