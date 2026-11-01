"""Replay stored NBA game reports with the nba.com-only tables replaced.
B: key_defenders/team_dvp empty.  C: B + ESPN team_stats and player advanced."""
import glob, json, os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
NBA = sys.argv[1]; OUT = sys.argv[2]
sys.path.insert(0, NBA); import nba_espn_league as L
names = L.nba_name_index(); tables = {}
jobs = []
for d in sorted(glob.glob('/Users/imac/WongChoiData/Wong Choi NBA Analysis/2026-10-2*')) + ['/Users/imac/wongchoi-scheduler/2026-10-29 NBA Analysis']:
    for f in sorted(glob.glob(d + '/nba_game_data_*.json')):
        tag = f.split('nba_game_data_')[1][:-5]
        sb = f'{d}/Sportsbet_Odds_{tag}.json'; legs = f'{d}/Game_{tag}_Full_Analysis.md.market_legs.json'
        if not (os.path.exists(sb) and os.path.exists(legs)): continue
        x = json.load(open(f)); m = x['meta']
        if (m.get('data_sources', {}).get('team_stats') or {}).get('data_season') != '2026-27': continue
        dt = m['history_date_to']
        if dt not in tables:
            g = L.season_games('2026-27', dt); tables[dt] = (L.team_advanced(g), L.player_advanced(g, names))
        ts, adv = tables[dt]
        day = os.path.basename(d)[:10]
        for cfg in ('A', 'B', 'C'):
            y = json.loads(json.dumps(x))
            if cfg != 'A': y['key_defenders'] = {}; y['team_dvp'] = {}
            if cfg == 'C':
                y['team_stats'] = {a: {**ts[a], 'opponent_stats': (x['team_stats'].get(a) or {}).get('opponent_stats', {})} for a in x['team_stats'] if a in ts}
                for side in y['players'].values():
                    for p in side:
                        p['advanced'] = adv.get(p.get('player_id'), {})
            src = f'{OUT}/{day}_{tag}_{cfg}.json'
            json.dump(y, open(src, 'w'))
            jobs.append((sb, src, f'{OUT}/{day}_{tag}_{cfg}.md'))
print('jobs', len(jobs), flush=True)
env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'}
def run(j):
    sb, src, out = j
    if os.path.exists(out + '.market_legs.json'): return 0
    return subprocess.run([sys.executable, f'{NBA}/nba_wong_choi/scripts/generate_nba_reports.py', '--sportsbet', sb, '--extractor', src, '--output', out], env=env, capture_output=True).returncode
with ThreadPoolExecutor(4) as ex:
    codes = list(ex.map(run, jobs))
print('failed', sum(1 for c in codes if c), 'of', len(codes))
