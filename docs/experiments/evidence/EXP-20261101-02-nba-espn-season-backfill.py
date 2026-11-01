"""EXP-20261101-02: one season of ESPN summaries + game logs for the training corpus.

usage: WC_NBA_ESPN_HTTP_RESPONSES_DIR=<external disk dir> \
  python3 EXP-20261101-02-nba-espn-season-backfill.py <.agents/skills/nba> 2025-10-01 2026-06-10
Every request goes through nba_espn_http (shared spacing + circuit) and is
cached for good; this script adds 1 s after each network call on top. It stops
at the first EspnBlocked.
"""
import sys, time
import requests
from datetime import date, timedelta
sys.path.insert(0, sys.argv[1])
import nba_espn_league as L, nba_espn_lineups as P, nba_espn_http as H
first, last = date.fromisoformat(sys.argv[2]), date.fromisoformat(sys.argv[3])
day, n, missing = first, 0, []
def pause(before):
    if H._state['network_calls'] > before:
        time.sleep(1.0)
try:
    while day <= last:
        before = H._state['network_calls']
        events = L._scoreboard_events(day)
        pause(before)
        for e in events:
            if e['season_type'] in (2, 3, 5) and e['final']:
                before = H._state['network_calls']
                try:
                    L._game(e['id'], day)
                    P.game_lineups(e['id'], day)
                except requests.HTTPError as exc:   # ESPN has no summary for a few playoff games
                    if exc.response is None or exc.response.status_code != 404:
                        raise
                    missing.append(e['id'])
                    print('404', day, e['id'], flush=True)
                pause(before)
                n += 1
        if day.day == 1:
            print(day, n, H.summary(), flush=True)
        day += timedelta(days=1)
except H.EspnBlocked as exc:
    print('STOPPED', exc)
print('done', n, 'summary 404:', missing, H.summary())
