import requests

url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260415"
try:
    r = requests.get(url, timeout=10)
    events = r.json().get('events', [])
    print(f"Games on 2026-04-15: {len(events)}")
    for e in events:
        print(e['name'])
except Exception as ex:
    print(ex)

url2 = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=20260414"
try:
    r = requests.get(url2, timeout=10)
    events = r.json().get('events', [])
    print(f"Games on 2026-04-14: {len(events)}")
    for e in events:
        print(e['name'])
except Exception as ex:
    print(ex)
