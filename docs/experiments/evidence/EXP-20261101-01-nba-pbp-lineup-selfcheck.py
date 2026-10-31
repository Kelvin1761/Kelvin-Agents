"""EXP-20261101-01 self-check: rebuilt lineups vs the same game's box score.

Per player: on-court minutes vs box MIN. Per team: counted possessions vs the
box estimate FGA + 0.44 FTA - OREB + TOV. Reads only cached summaries.
usage: python3 ...-selfcheck.py <.agents/skills/nba>
"""
import glob, json, os, statistics, sys
sys.path.insert(0, sys.argv[1])
import nba_espn_lineups as P, nba_espn_league as L, nba_espn_http as H
from datetime import date
mins, poss, bad, n = [], [], 0, 0
for path in sorted(glob.glob(str(H.responses_root() / '*.json'))):
    entry = json.load(open(path))
    if '/summary?event=' not in entry.get('url', ''): continue
    payload = entry['payload']
    if not payload.get('plays'): continue
    game = P.parse_game(payload); box = L.parse_summary(payload, date(2026, 10, 1))
    if not game or not box: continue
    n += 1; bad += len(game['quality']['bad_periods'])
    boxmin = {p['espn_id']: p['MIN'] for p in box['players']}
    for pid, row in game['players'].items():
        if pid in boxmin: mins.append(row['minutes'] - boxmin[pid])
    counted = {}
    for pid, row in game['players'].items():
        counted.setdefault(row['team'], 0); counted[row['team']] += row['off_poss']
    for team, t in box['teams'].items():
        est = t['FGA'] + 0.44 * t['FTA'] - t['OREB'] + t['TOV']
        poss.append((counted.get(team, 0) / 5) / est)
a = [abs(x) for x in mins]
print('games', n, 'bad periods', bad)
print('minutes |Δ| median', round(statistics.median(a), 2), 'p90', round(sorted(a)[int(.9 * len(a))], 2), 'max', round(max(a), 1))
print('counted/box-estimate possessions median', round(statistics.median(poss), 4), 'p10', round(sorted(poss)[len(poss)//10], 4), 'p90', round(sorted(poss)[9*len(poss)//10], 4))
