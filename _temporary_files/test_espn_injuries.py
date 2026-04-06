import requests

TEAM_ABBR_ESPN_MAP = {
    "GSW": "GS",
    "NOP": "NO",
    "NYK": "NY",
    "SAS": "SA",
    "UTA": "UTAH",
    "WAS": "WSH"
}

all_nba_teams = [
    "ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GSW", 
    "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK", 
    "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SAS", "TOR", "UTA", "WAS"
]

success = 0
failed = []

for team in all_nba_teams:
    espn_abbr = TEAM_ABBR_ESPN_MAP.get(team, team)
    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_abbr}/roster"
    r = requests.get(url, timeout=5)
    if r.status_code == 200:
        data = r.json()
        athletes = data.get('athletes', [])
        injuries = []
        for a in athletes:
            if a.get('injuries') and len(a.get('injuries')) > 0:
                 injuries.append(a.get('fullName'))
        print(f"[{team}] (ESPN: {espn_abbr}) -> OK. Players injured: {len(injuries)}")
        success += 1
    else:
        print(f"[{team}] (ESPN: {espn_abbr}) -> FAILED: {r.status_code}")
        failed.append(team)

print(f"\nResults: {success}/30 teams successful.")
if failed:
    print(f"Failed teams: {failed}")
