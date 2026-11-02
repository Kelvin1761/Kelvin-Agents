"""EXP-20261101-60 R2 gate: ESPN player_base / team_base vs nba.com's LeagueDash Base tables.

usage: python3 EXP-20261101-60-nba-opportunity-parity.py <repo> <NBA_Opportunity_Sources.json> [...]

Each file is an nba.com capture (2026-27, cutoffs 10/24..10/27, before the block).
ESPN tables are rebuilt for the same season and cutoff; players matched by name.
Pre-registered: per-game box median |delta| <= 0.1.
"""
import json
import statistics
import sys
from pathlib import Path

repo = Path(sys.argv[1])
sys.path.insert(0, str(repo / ".agents/skills/nba"))
import nba_espn_league as L  # noqa: E402
from nba_identity import player_name_key  # noqa: E402
from nba_schedule import canonical_team_abbr  # noqa: E402


def _espn_rows(name, games):
    """ESPN box-score stand-ins for the two nba.com Base tables (EXP-20261101-60).

    ``player_base``: per-game box averages per ESPN athlete id (team = the
    player's latest team). ``team_base``: per-100-possession team totals, with
    possessions as in ``nba_espn_league``. TEAM_ID is the canonical team abbr.
    """
    if name == 'team_base':
        acc = {}
        for game in games:
            for abbr, team in game['teams'].items():
                row = acc.setdefault(abbr, {'GP': 0, 'MIN': 0.0, 'FGA': 0.0, 'FGM': 0.0, 'OREB': 0.0, 'poss': 0.0})
                row['GP'] += 1
                row['MIN'] += team['MIN'] / 5
                for key in ('FGA', 'FGM', 'OREB'):
                    row[key] += team[key]
                row['poss'] += L.possessions(team)
        return [{'TEAM_ID': abbr, 'TEAM_ABBREVIATION': abbr, 'GP': row['GP'],
                 'MIN': round(row['MIN'] / row['GP'], 1),
                 **{key: round(100 * row[key] / row['poss'], 1) for key in ('FGA', 'FGM', 'OREB')}}
                for abbr, row in sorted(acc.items()) if row['poss'] > 0]
    acc = {}
    for game in sorted(games, key=lambda g: g['date']):
        for line in game['players']:
            if not line.get('espn_id') or line['MIN'] <= 0:
                continue
            row = acc.setdefault(line['espn_id'], {'GP': 0, **dict.fromkeys(
                ('MIN', 'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM'), 0.0)})
            row['team'] = line['team']
            row['GP'] += 1
            for key in ('MIN', 'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM'):
                row[key] += line[key]
    return [{'PLAYER_ID': espn_id, 'TEAM_ID': row['team'], 'TEAM_ABBREVIATION': row['team'], 'GP': row['GP'],
             **{key: round(row[key] / row['GP'], 1) for key in ('MIN', 'FGA', 'FGM', 'FG3A', 'FG3M', 'FTA', 'FTM')}}
            for espn_id, row in sorted(acc.items())]


PLAYER_FIELDS = ("GP", "MIN", "FGA", "FGM", "FG3A", "FG3M", "FTA", "FTM")
TEAM_FIELDS = ("FGA", "FGM", "OREB")
NICK = {"76ers": "PHI", "Bucks": "MIL", "Bulls": "CHI", "Cavaliers": "CLE", "Celtics": "BOS", "Clippers": "LAC",
        "Grizzlies": "MEM", "Hawks": "ATL", "Heat": "MIA", "Hornets": "CHA", "Jazz": "UTA", "Kings": "SAC",
        "Knicks": "NYK", "Lakers": "LAL", "Magic": "ORL", "Mavericks": "DAL", "Nets": "BKN", "Nuggets": "DEN",
        "Pacers": "IND", "Pelicans": "NOP", "Pistons": "DET", "Raptors": "TOR", "Rockets": "HOU", "Spurs": "SAS",
        "Suns": "PHX", "Thunder": "OKC", "Timberwolves": "MIN", "Blazers": "POR", "Warriors": "GSW", "Wizards": "WAS"}
out = {}
for path in sys.argv[2:]:
    nba = json.loads(Path(path).read_text())
    season, cutoff = nba["season"], nba["history_date_to"]
    games = L.season_games(season, cutoff)
    names = {line["espn_id"]: line["name"] for g in games for line in g["players"]}
    espn_p = {player_name_key(names[r["PLAYER_ID"]]): r for r in _espn_rows("player_base", games)}
    espn_t = {r["TEAM_ID"]: r for r in _espn_rows("team_base", games)}
    deltas = {f: [] for f in PLAYER_FIELDS}
    matched = 0
    for row in nba["sources"]["player_base"]["rows"]:
        e = espn_p.get(player_name_key(row.get("PLAYER_NAME", "")))
        if not e:
            continue
        matched += 1
        for f in PLAYER_FIELDS:
            deltas[f].append(abs(float(row[f]) - float(e[f])))
    tdeltas = {f: [] for f in TEAM_FIELDS}
    for row in nba["sources"]["team_base"]["rows"]:
        e = espn_t.get(canonical_team_abbr(NICK.get(str(row.get("TEAM_NAME", "")).split()[-1], "")))
        if e:
            for f in TEAM_FIELDS:
                tdeltas[f].append(abs(float(row[f]) - float(e[f])))
    out[cutoff] = {
        "espn_games": len(games), "nba_players": len(nba["sources"]["player_base"]["rows"]),
        "espn_players": len(espn_p), "matched": matched,
        "player_median_abs": {f: round(statistics.median(v), 3) for f, v in deltas.items() if v},
        "player_p90_abs": {f: round(sorted(v)[int(0.9 * len(v))], 3) for f, v in deltas.items() if v},
        "team_rows": len(tdeltas["FGA"]),
        "team_median_abs_per100": {f: round(statistics.median(v), 3) for f, v in tdeltas.items() if v},
    }
print(json.dumps(out, indent=1))
