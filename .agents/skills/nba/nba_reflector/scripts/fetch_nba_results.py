#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
fetch_nba_results.py — NBA Reflector 賽果擷取器

由 ESPN（scoreboard + summary）擷取指定美國日期嘅所有 NBA 賽果，生成結構化 JSON
供 Reflector 消費。ESPN 係唯一來源（EXP-20261101-60）；所有請求都經
``nba_espn_http``（限速、熔斷、完場日永久 cache）。

輸出:
  Results_Brief_{DATE}.json — 包含每場賽事嘅最終比分、球員 Box Score

Usage:
  python fetch_nba_results.py --date 2026-04-07 --dir "2026-04-08 NBA Analysis"

  (--date 係美國日期，即澳洲日期 -1)
"""

import argparse
import json
import io
from datetime import date, datetime, timezone

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ── Finality ─────────────────────────────────────────────────────────────────
# A game is final only when the ESPN scoreboard event says completed /
# STATUS_FINAL AND the box score's summed player points equal ESPN's score.
# ESPN unreachable => no games at all (exit 1); a game is never settled from
# nothing. ``box_score_is_complete`` and the >= 2-day rule stay for callers
# that hand in a box score with no ESPN event (tests, archived briefs).
SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
_NBA_SKILL = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _NBA_SKILL)
from nba_schedule import canonical_team_abbr  # noqa: E402
import nba_espn_http  # noqa: E402
import nba_espn_lineups  # noqa: E402


def _us_day(game_date_file):
    try:
        return date.fromisoformat(str(game_date_file))
    except ValueError:
        return None


def fetch_espn_events(game_date_file, timeout=15):
    """ESPN events for a US date (YYYY-MM-DD). Returns (events, reachable).

    A closed day (06:00 ET the next morning) is cached for good; today's
    board is always asked again.
    """
    day = _us_day(game_date_file)
    fresh = None
    if day is not None:
        closes = nba_espn_lineups.day_close(day)
        fresh = closes if datetime.now(nba_espn_lineups.US_EASTERN) >= closes else None
    try:
        url = f"{SITE}/scoreboard?dates={game_date_file.replace('-', '')}&limit=50"
        return nba_espn_http.get_json(url, timeout=timeout, fresh_after=fresh).get("events") or [], True
    except Exception as exc:
        print(f"  ❌ ESPN scoreboard 擷取失敗: {exc}")
        return [], False


def espn_index(events):
    """{(away, home): {completed, status, away_score, home_score, detail}} (canonical abbrs)."""
    index = {}
    for event in events:
        try:
            comp = event["competitions"][0]
            teams = {c["homeAway"]: c for c in comp["competitors"]}
            status = (event.get("status") or {}).get("type") or {}
            key = (canonical_team_abbr(teams["away"]["team"]["abbreviation"]),
                   canonical_team_abbr(teams["home"]["team"]["abbreviation"]))
            index[key] = {
                "event_id": str(event.get("id") or ""),
                "completed": bool(status.get("completed")) and status.get("name") == "STATUS_FINAL",
                "status": status.get("name"),
                "detail": status.get("detail"),
                "away_score": int(teams["away"]["score"]),
                "home_score": int(teams["home"]["score"]),
            }
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return index


ESPN_ID_PREFIX = "espn:"


def espn_scoreboard_games(events):
    """ESPN events -> ScoreboardV3-shaped games. Scores stay None, so finality
    is decided by ``decide_finality`` (ESPN completed + box-score match)."""
    games = []
    for event in events or []:
        try:
            comp = event["competitions"][0]
            teams = {c["homeAway"]: c["team"] for c in comp["competitors"]}
            status = ((event.get("status") or {}).get("type") or {})
            games.append({
                "gameId": ESPN_ID_PREFIX + str(event["id"]),
                "gameStatusText": status.get("detail") or status.get("name") or "",
                "homeTeam": {"teamTricode": canonical_team_abbr(teams["home"]["abbreviation"]),
                             "teamName": teams["home"].get("name") or "?", "score": None},
                "awayTeam": {"teamTricode": canonical_team_abbr(teams["away"]["abbreviation"]),
                             "teamName": teams["away"].get("name") or "?", "score": None},
            })
        except (KeyError, IndexError, TypeError):
            continue
    return games


def fetch_espn_summary(event_id, day=None):
    """The raw ESPN summary (cached for good once ``day`` has closed), or None."""
    try:
        return nba_espn_lineups.fetch_summary(str(event_id), day) if day else \
            nba_espn_http.get_json(f"{SITE}/summary?event={event_id}", timeout=20)
    except Exception as exc:
        print(f"    ⚠️ ESPN box score 擷取失敗 ({event_id}): {exc}")
        return None


def fetch_scoreboard(game_date_file, events=None):
    """ESPN games for a US date, in the ScoreboardV3 shape the rest of this file reads."""
    if events is None:
        events, _ = fetch_espn_events(game_date_file)
    games = espn_scoreboard_games(events)
    print(f"  ✅ 搵到 {len(games)} 場賽事（ESPN）")
    return games


def _made_attempted(text):
    made, _, attempted = str(text or "").partition("-")
    try:
        return int(made), int(attempted)
    except ValueError:
        return 0, 0


def _int_stat(text):
    try:
        return int(float(str(text).replace("+", "")))
    except (TypeError, ValueError):
        return 0


def espn_boxscore(summary):
    """ESPN summary -> BoxScoreTraditionalV3-shaped dict, or None.

    Team points are the SUM of player points, not ESPN's headline score, so
    ``decide_finality``'s box-vs-scoreboard comparison is still a real check.
    Only starters carry a position, as in V3 (``extract_player_stats`` reads
    the starter flag from it); DNP players get minutes '' plus a comment.
    """
    try:
        header = summary["header"]["competitions"][0]
        sides = {str(c["team"]["id"]): c["homeAway"] for c in header["competitors"]}
        out = {}
        for team_block in summary["boxscore"]["players"]:
            team = team_block["team"]
            side = sides.get(str(team.get("id")))
            if side not in ("home", "away"):
                continue
            stats = team_block["statistics"][0]
            keys = stats["keys"]
            players, points_total = [], 0
            for athlete in stats.get("athletes") or []:
                info = athlete.get("athlete") or {}
                row = dict(zip(keys, athlete.get("stats") or []))
                dnp = bool(athlete.get("didNotPlay")) or not row
                fgm, fga = _made_attempted(row.get("fieldGoalsMade-fieldGoalsAttempted"))
                tpm, tpa = _made_attempted(row.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
                ftm, fta = _made_attempted(row.get("freeThrowsMade-freeThrowsAttempted"))
                points = _int_stat(row.get("points"))
                points_total += points
                minutes = "" if dnp else f"{_int_stat(row.get('minutes'))}:00"
                players.append({
                    "name": info.get("displayName") or "?",
                    "position": ((info.get("position") or {}).get("abbreviation") or "")
                    if athlete.get("starter") else "",
                    "starter": "1" if athlete.get("starter") else "",
                    "comment": (athlete.get("reason") or "DNP") if dnp else "",
                    "statistics": {
                        "minutes": minutes, "points": points,
                        "reboundsTotal": _int_stat(row.get("rebounds")),
                        "assists": _int_stat(row.get("assists")),
                        "threePointersMade": tpm, "threePointersAttempted": tpa,
                        "fieldGoalsMade": fgm, "fieldGoalsAttempted": fga,
                        "freeThrowsMade": ftm, "freeThrowsAttempted": fta,
                        "steals": _int_stat(row.get("steals")),
                        "blocks": _int_stat(row.get("blocks")),
                        "turnovers": _int_stat(row.get("turnovers")),
                        "foulsPersonal": _int_stat(row.get("fouls")),
                        "plusMinusPoints": _int_stat(row.get("plusMinus")),
                    },
                })
            # nba.com listed inactive players with a comment (-> VOID_DNP); ESPN's
            # box leaves them out and names the Out ones under ``injuries``.
            listed = {p["name"] for p in players}
            for block in summary.get("injuries") or []:
                if str((block.get("team") or {}).get("id")) != str(team.get("id")):
                    continue
                for entry in block.get("injuries") or []:
                    name = (entry.get("athlete") or {}).get("displayName")
                    if name and name not in listed and str(entry.get("status") or "").lower() == "out":
                        listed.add(name)
                        players.append({"name": name, "position": "", "starter": "",
                                        "comment": "Inactive (ESPN injuries: Out)",
                                        "statistics": {"minutes": "", "points": 0}})
            out[f"{side}Team"] = {
                "teamTricode": canonical_team_abbr(team.get("abbreviation")),
                "teamName": team.get("name") or team.get("displayName") or "?",
                "statistics": {"points": points_total, "minutes": ""},
                "players": players,
            }
        if set(out) != {"homeTeam", "awayTeam"}:
            return None
        return {"boxScoreTraditional": out, "_source": "espn"}
    except (KeyError, IndexError, TypeError):
        return None


def _team_minutes(boxscore, team_key):
    team = ((boxscore or {}).get("boxScoreTraditional") or {}).get(team_key) or {}
    text = str((team.get("statistics") or {}).get("minutes") or "")
    try:
        minutes, _, seconds = text.partition(":")
        return int(minutes) + (int(seconds) / 60 if seconds else 0)
    except ValueError:
        return None


def box_score_is_complete(boxscore):
    """Objective completeness rule, used only when ESPN cannot answer.

    Final <=> both teams' total minutes are 240 + 25*k (k >= 0: regulation end
    or a finished overtime), the two totals agree, both team scores exist and
    DIFFER, and player stats are present. A tied score at 240 (or at 265...)
    means another period follows, so it is never final. A live game can only
    satisfy this at the exact instant a period ends with the score not tied,
    which is the end of the game. Edge cases: a box score caught mid-period
    (minutes not on a 25-minute boundary) is non-final; empty/partial stats
    are non-final.
    """
    home_pts, away_pts = _boxscore_points(boxscore, "homeTeam"), _boxscore_points(boxscore, "awayTeam")
    home_min, away_min = _team_minutes(boxscore, "homeTeam"), _team_minutes(boxscore, "awayTeam")
    if None in (home_pts, away_pts, home_min, away_min) or home_pts == away_pts:
        return False
    if abs(home_min - away_min) > 0.01 or home_min < 240 - 0.01:
        return False
    if abs((home_min - 240) % 25) > 0.01 and abs((home_min - 240) % 25 - 25) > 0.01:
        return False
    box = (boxscore or {}).get("boxScoreTraditional") or {}
    return bool((box.get("homeTeam") or {}).get("players")) and bool((box.get("awayTeam") or {}).get("players"))


def decide_finality(away_abbr, home_abbr, boxscore, espn, boxscore_may_settle):
    """Return (final: bool, scores: (away, home) | None, source: str)."""
    box_home, box_away = _boxscore_points(boxscore, "homeTeam"), _boxscore_points(boxscore, "awayTeam")
    has_stats = bool(((boxscore or {}).get("boxScoreTraditional") or {}).get("homeTeam", {}).get("players"))
    key = (canonical_team_abbr(away_abbr), canonical_team_abbr(home_abbr))
    event = (espn or {}).get(key)
    if event is not None:
        if not event["completed"]:
            return False, None, "espn_not_final"
        if not has_stats or box_home is None or box_away is None:
            return False, None, "espn_final_no_boxscore"
        if (box_away, box_home) != (event["away_score"], event["home_score"]):
            return False, None, "espn_boxscore_score_mismatch"
        return True, (box_away, box_home), "espn"
    if box_score_is_complete(boxscore):
        return True, (box_away, box_home), "boxscore_completeness"
    if boxscore_may_settle and box_home is not None and box_away is not None:   # legacy rule, unchanged
        return True, (box_away, box_home), "boxscore_age"
    return False, None, "unresolved"


def fetch_boxscore(game_id, day=None):
    """ESPN box score for an ``espn:<id>`` game, in the BoxScoreTraditionalV3 shape."""
    if not str(game_id).startswith(ESPN_ID_PREFIX):
        return None
    summary = fetch_espn_summary(str(game_id)[len(ESPN_ID_PREFIX):], day)
    return espn_boxscore(summary) if summary else None


def _player_display_name(player):
    """Full display name from either payload shape.

    BoxScoreTraditionalV3 has no ``name``; it carries ``firstName`` / ``familyName``
    / ``nameI`` ("A. Thompson").  Reading only ``name`` made every player '?', so on
    2026-10-21 every leg of the first finished games was PLAYER_NOT_FOUND.
    """
    name = str(player.get('name') or '').strip()
    if name:
        return name
    full = ' '.join(
        part for part in (str(player.get('firstName') or '').strip(),
                          str(player.get('familyName') or '').strip()) if part)
    return full or str(player.get('nameI') or '').strip() or '?'


def extract_player_stats(boxscore_data):
    """Extract player stats from BoxScoreTraditionalV3 response."""
    players = []
    
    box_data = boxscore_data.get('boxScoreTraditional', {})
    
    # Try to get player stats from both teams
    for team_key in ['homeTeam', 'awayTeam']:
        team_data = box_data.get(team_key, {})
        team_abbr = team_data.get('teamTricode', '?')
        team_name = team_data.get('teamName', '?')
        
        for player in team_data.get('players', []):
            stats = player.get('statistics', {})
            comment = str(player.get('comment') or '').strip()
            minutes = stats.get('minutes', '0')
            # BoxScoreTraditionalV3 lists DNP / inactive players with minutes '' and a
            # non-empty comment.  Empty minutes parse as "unknown", which verify_legs
            # then scores as a played game with 0 stats (MISS) instead of VOID.
            if comment and not str(minutes or '').strip():
                minutes = '0'
            players.append({
                'name': _player_display_name(player),
                'team': team_abbr,
                'position': player.get('position', '?'),
                # V3 has no 'starter' flag; only starters carry a position.
                'starter': player.get('starter', '') == '1' or bool(str(player.get('position') or '').strip()),
                'comment': comment,
                'minutes': minutes,
                'pts': stats.get('points', 0),
                'reb': stats.get('reboundsTotal', 0),
                'ast': stats.get('assists', 0),
                'fg3m': stats.get('threePointersMade', 0),
                'fgm': stats.get('fieldGoalsMade', 0),
                'fga': stats.get('fieldGoalsAttempted', 0),
                'ftm': stats.get('freeThrowsMade', 0),
                'fta': stats.get('freeThrowsAttempted', 0),
                'stl': stats.get('steals', 0),
                'blk': stats.get('blocks', 0),
                'tov': stats.get('turnovers', 0),
                'pf': stats.get('foulsPersonal', 0),
                'plus_minus': stats.get('plusMinusPoints', 0),
            })
    
    return players


def _boxscore_points(boxscore, team_key):
    team = ((boxscore or {}).get('boxScoreTraditional') or {}).get(team_key) or {}
    points = (team.get('statistics') or {}).get('points')
    return points if isinstance(points, (int, float)) else None


def process_game(game, *, boxscore_may_settle=False, espn=None, day=None):
    """Process a single game from the ESPN scoreboard.

    Scores always come from ``decide_finality``: ESPN completed + the box
    score's summed points equal to ESPN's score. Otherwise the status keeps
    the scoreboard text, which downstream treats as not final.
    """
    game_id = game.get('gameId', '')
    home = game.get('homeTeam', {})
    away = game.get('awayTeam', {})

    home_abbr = home.get('teamTricode', '?')
    away_abbr = away.get('teamTricode', '?')
    home_score = home.get('score', 0)
    away_score = away.get('score', 0)
    status = game.get('gameStatusText', '')

    # Fetch detailed box score
    print(f"  📊 擷取 {away_abbr} @ {home_abbr} Box Score...")
    boxscore = fetch_boxscore(game_id, day=day)
    if boxscore is None:
        event = (espn or {}).get((canonical_team_abbr(away_abbr), canonical_team_abbr(home_abbr)))
        if event and event.get("event_id"):
            summary = fetch_espn_summary(event["event_id"], day)
            boxscore = espn_boxscore(summary) if summary else None

    scoreboard_status = status
    status_source = "scoreboard"
    if home_score is None or away_score is None:
        final, scores, status_source = decide_finality(
            away_abbr, home_abbr, boxscore, espn, boxscore_may_settle)
        if final:
            away_score, home_score = scores
            status = {"espn": "Final", "boxscore_age": "Final (boxscore)"}.get(
                status_source, f"Final ({status_source})")
        else:
            print(f"    ⚠️ 冇比分（scoreboard: {status}；finality: {status_source}）— 當未完場處理")

    scored = home_score is not None and away_score is not None
    result = {
        'game_id': game_id,
        'status': status,
        'status_source': status_source,
        'scoreboard_status_text': scoreboard_status,
        'away': {
            'team': away_abbr,
            'name': away.get('teamName', '?'),
            'score': away_score,
        },
        'home': {
            'team': home_abbr,
            'name': home.get('teamName', '?'),
            'score': home_score,
        },
        'final_score': f"{away_abbr} {away_score} - {home_score} {home_abbr}",
        'margin': abs(home_score - away_score) if scored else None,
        'blowout': scored and abs(home_score - away_score) >= 20,
        'winner': (home_abbr if home_score > away_score else away_abbr) if scored else None,
    }

    if boxscore:
        players = extract_player_stats(boxscore)
        result['players'] = players

        # Flag players with low minutes (potential injury/foul trouble)
        low_min_players = [p for p in players if p['starter'] and
                          _parse_minutes(p['minutes']) < 20]
        if low_min_players:
            result['low_minutes_alert'] = [
                f"{p['name']} ({p['team']}) — {p['minutes']} MIN"
                for p in low_min_players
            ]
    else:
        result['players'] = []

    return result


def _parse_minutes(min_str):
    """Parse minutes string (e.g. 'PT32M15.00S' or '32') to float."""
    if isinstance(min_str, (int, float)):
        return float(min_str)
    if isinstance(min_str, str):
        # Handle ISO duration format PT32M15.00S
        if min_str.startswith('PT'):
            import re
            m = re.search(r'(\d+)M', min_str)
            return float(m.group(1)) if m else 0
        try:
            return float(min_str.split(':')[0]) if ':' in min_str else float(min_str)
        except (ValueError, IndexError):
            return 0
    return 0


def _matchup(row):
    """Canonical (away, home) of a Results Brief row, whichever source wrote it."""
    return (canonical_team_abbr((row.get('away') or {}).get('team')),
            canonical_team_abbr((row.get('home') or {}).get('team')))


def main():
    parser = argparse.ArgumentParser(description='NBA Reflector Results Fetcher')
    parser.add_argument('--date', required=True, 
                       help='US game date (YYYY-MM-DD or MM/DD/YYYY)')
    parser.add_argument('--games', default='', help='Only fetch these canonical AWAY_HOME tags (comma separated); merge other cached games')
    parser.add_argument('--dir', required=True, 
                       help='Output directory for Results Brief JSON')
    args = parser.parse_args()

    # Normalize date format
    game_date = args.date
    if '-' in game_date and len(game_date) == 10:
        # Convert YYYY-MM-DD to MM/DD/YYYY for ScoreboardV3
        parts = game_date.split('-')
        game_date_api = f"{parts[1]}/{parts[2]}/{parts[0]}"
        game_date_file = args.date
    else:
        game_date_api = game_date
        game_date_file = game_date.replace('/', '-')

    target_dir = args.dir
    if not os.path.isdir(target_dir):
        print(f"⚠️ 目錄不存在，建立中: {target_dir}")
        os.makedirs(target_dir, exist_ok=True)

    print("=" * 60)
    print("🏀 NBA Reflector — 賽果擷取器 V1")
    print(f"📅 擷取日期: {game_date_api}")
    print("=" * 60)

    espn_events, espn_ok = fetch_espn_events(game_date_file)
    espn = espn_index(espn_events) if espn_ok else None
    games = fetch_scoreboard(game_date_file, espn_events)

    if not games:
        print("❌ 該日期冇 NBA 賽事，或 ESPN 呼叫失敗")
        sys.exit(1)

    # Process each game
    # A box score may stand in for a stale scoreboard only once the US game
    # date is at least two days old (no game can still be in progress).
    try:
        us_day = datetime.strptime(game_date_file, '%Y-%m-%d').date()
        boxscore_may_settle = (datetime.now(timezone.utc).date() - us_day).days >= 2
    except ValueError:
        boxscore_may_settle = False

    results = []
    seen_ids = set()
    requested = {tag.strip() for tag in args.games.split(',') if tag.strip()}
    for game in games:
        tag = canonical_team_abbr(game.get('awayTeam',{}).get('teamTricode',''))+'_'+canonical_team_abbr(game.get('homeTeam',{}).get('teamTricode',''))
        if requested and tag not in requested:
            continue
        if game.get('gameId') in seen_ids:      # ScoreboardV3 lists every game twice
            continue
        seen_ids.add(game.get('gameId'))
        result = process_game(game, boxscore_may_settle=boxscore_may_settle, espn=espn, day=_us_day(game_date_file))
        results.append(result)
        
        score = result['final_score']
        blowout = " 🔴 BLOWOUT" if result['blowout'] else ""
        print(f"    ✅ {score}{blowout}")
        
        if result.get('low_minutes_alert'):
            for alert in result['low_minutes_alert']:
                print(f"    ⚠️ 低上場時間: {alert}")

    # Incremental polls preserve other games, including previously verified Finals.
    out_path = os.path.join(target_dir, f'Results_Brief_{game_date_file}.json')
    if requested and os.path.isfile(out_path):
        try:
            with open(out_path, encoding='utf-8') as existing:
                previous = json.load(existing)
            if previous.get('date') == game_date_file and previous.get('_version') == 'RESULTS_BRIEF_V1':
                fetched = {row.get('game_id') for row in results}
                matchups = {_matchup(row) for row in results}
                results = [row for row in previous.get('games', [])
                           if row.get('game_id') not in fetched
                           and _matchup(row) not in matchups] + results
        except (OSError, ValueError, TypeError, AttributeError):
            pass

    # Build final brief
    brief = {
        '_version': 'RESULTS_BRIEF_V1',
        '_note': '此 JSON 由 Python 自動生成，包含實際賽果同球員 Box Score。供 NBA Reflector 覆盤使用。',
        'date': game_date_file,
        'total_games': len(results),
        'games': results,
    }

    # Save
    out_path = os.path.join(target_dir, f'Results_Brief_{game_date_file}.json')
    with open(out_path+'.tmp', 'w', encoding='utf-8') as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)
    os.replace(out_path+'.tmp', out_path)

    print(f"\n{'=' * 60}")
    print(f"🏆 完成！{len(results)} 場賽果已擷取")
    print(f"📄 輸出: {out_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
