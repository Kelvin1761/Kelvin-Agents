#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
fetch_nba_pbp.py — NBA Play-by-Play 擷取器

用 nba_api 擷取指定賽事嘅 Play-by-Play 數據,生成結構化 JSON 供 Reflector 深度覆盤。
重點提取:球員上場時間分段、得分分布、Blowout 時間點、關鍵 lineup 變化。

Usage:
  python fetch_nba_pbp.py --date 2026-04-07 --dir "2026-04-08 NBA Analysis"
  python fetch_nba_pbp.py --date 2026-04-07 --dir "..." --games "0022501050,0022501051"

Version: 1.0.0
"""

import argparse
import json
import io
import time
import re
from collections import defaultdict

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_SLEEP = 0.8

try:
    from nba_api.stats.endpoints import (
        playbyplayv3,
        scoreboardv3,
    )
    NBA_API_OK = True
except ImportError:
    NBA_API_OK = False
    print("❌ nba_api 未安裝。請執行: pip install nba_api")
    sys.exit(1)


def fetch_scoreboard(game_date):
    """Fetch all games on a given date."""
    try:
        sb = scoreboardv3.ScoreboardV3(game_date=game_date)
        time.sleep(API_SLEEP)
        data = sb.get_dict()
        return data.get('scoreboard', {}).get('games', [])
    except Exception as e:
        print(f"  ❌ ScoreboardV3 失敗: {e}")
        return []


def parse_clock(clock_str):
    """Parse game clock string like 'PT05M30.00S' to seconds remaining."""
    if not clock_str:
        return 0
    m = re.search(r'PT(\d+)M([\d.]+)S', str(clock_str))
    if m:
        return int(m.group(1)) * 60 + float(m.group(2))
    return 0


def parse_period(period):
    """Convert period number to readable label."""
    if period <= 4:
        return f"Q{period}"
    return f"OT{period - 4}"


def fetch_pbp(game_id):
    """Fetch play-by-play for a specific game."""
    print(f"  📋 擷取 Play-by-Play (game_id: {game_id})...")
    try:
        pbp = playbyplayv3.PlayByPlayV3(game_id=game_id)
        time.sleep(API_SLEEP)
        data = pbp.get_dict()
        actions = data.get('game', {}).get('actions', [])
        print(f"    ✅ 擷取到 {len(actions)} 個 actions")
        return actions
    except Exception as e:
        print(f"    ❌ PlayByPlayV3 失敗: {e}")
        return []


def analyze_pbp(actions, home_team, away_team):
    """Analyze play-by-play data to extract key insights."""

    # Tracking structures
    player_minutes = defaultdict(lambda: {
        'periods': defaultdict(float),
        'total_minutes': 0,
        'team': '?',
    })
    player_scoring = defaultdict(lambda: {
        'periods': defaultdict(int),
        'total': 0,
        'team': '?',
    })
    score_margin_timeline = []
    blowout_events = []
    substitution_log = []

    home_score = 0
    away_score = 0

    # Track who is on court (simplified via substitution events)
    for action in actions:
        period = action.get('period', 0)
        clock = action.get('clock', '')
        action_type = action.get('actionType', '')
        sub_type = action.get('subType', '')
        player_name = action.get('playerNameI', '')
        team_tricode = action.get('teamTricode', '')
        description = action.get('description', '')
        score_home = action.get('scoreHome', '')
        score_away = action.get('scoreAway', '')

        # Track score
        if score_home and score_away:
            try:
                home_score = int(score_home)
                away_score = int(score_away)
                margin = home_score - away_score

                score_margin_timeline.append({
                    'period': parse_period(period),
                    'clock': clock,
                    'home_score': home_score,
                    'away_score': away_score,
                    'margin': margin,
                })

                # Detect blowout moments (margin >= 20)
                if abs(margin) >= 20:
                    blowout_events.append({
                        'period': parse_period(period),
                        'clock': clock,
                        'margin': margin,
                        'leading_team': home_team if margin > 0 else away_team,
                        'description': description,
                    })
            except (ValueError, TypeError):
                pass

        # Track scoring by player
        if action_type in ('2pt', '3pt') and sub_type == 'Made':
            pts = 3 if action_type == '3pt' else 2
            if player_name:
                player_scoring[player_name]['periods'][parse_period(period)] += pts
                player_scoring[player_name]['total'] += pts
                player_scoring[player_name]['team'] = team_tricode

        elif action_type == 'freethrow' and 'MISS' not in (description or '').upper():
            if player_name and score_home:  # Made FT
                player_scoring[player_name]['periods'][parse_period(period)] += 1
                player_scoring[player_name]['total'] += 1
                player_scoring[player_name]['team'] = team_tricode

        # Track substitutions
        if action_type == 'substitution':
            sub_in = action.get('playerNameI', '')
            sub_out = description  # Sometimes description has the sub-out player
            substitution_log.append({
                'period': parse_period(period),
                'clock': clock,
                'team': team_tricode,
                'player': sub_in,
                'type': sub_type,
            })

    # Derive blowout bench time
    blowout_bench_time = None
    if blowout_events:
        first_blowout = blowout_events[0]
        blowout_bench_time = {
            'first_20pt_margin': f"{first_blowout['period']} {first_blowout['clock']}",
            'leading_team': first_blowout['leading_team'],
            'total_blowout_actions': len(blowout_events),
        }

    # Build per-quarter score summary
    quarter_scores = {'home': defaultdict(int), 'away': defaultdict(int)}
    prev_home, prev_away = 0, 0
    for entry in score_margin_timeline:
        period = entry['period']
        if entry['home_score'] > prev_home:
            quarter_scores['home'][period] = entry['home_score']
        if entry['away_score'] > prev_away:
            quarter_scores['away'][period] = entry['away_score']
        prev_home = max(prev_home, entry['home_score'])
        prev_away = max(prev_away, entry['away_score'])

    # Compute quarter-by-quarter differentials
    periods_seen = sorted(set(e['period'] for e in score_margin_timeline))
    quarter_breakdown = {}
    prev_h, prev_a = 0, 0
    for p in periods_seen:
        p_entries = [e for e in score_margin_timeline if e['period'] == p]
        if p_entries:
            last = p_entries[-1]
            q_home = last['home_score'] - prev_h
            q_away = last['away_score'] - prev_a
            quarter_breakdown[p] = {
                'home': q_home,
                'away': q_away,
                'diff': q_home - q_away,
            }
            prev_h = last['home_score']
            prev_a = last['away_score']

    # Build player scoring distributions
    scoring_dist = {}
    for player, data in sorted(player_scoring.items(), key=lambda x: -x[1]['total']):
        if data['total'] >= 5:  # Only include players with meaningful scoring
            scoring_dist[player] = {
                'team': data['team'],
                'total': data['total'],
                'by_quarter': dict(data['periods']),
            }

    return {
        'quarter_breakdown': quarter_breakdown,
        'player_scoring_distribution': scoring_dist,
        'blowout_analysis': blowout_bench_time,
        'blowout_events_count': len(blowout_events),
        'total_actions': len(actions),
        'substitution_count': len(substitution_log),
    }


def main():
    parser = argparse.ArgumentParser(description='NBA Play-by-Play Fetcher')
    parser.add_argument('--date', required=True,
                        help='US game date (YYYY-MM-DD)')
    parser.add_argument('--dir', required=True,
                        help='Output directory')
    parser.add_argument('--games', default=None,
                        help='Comma-separated game IDs (optional — if omitted, fetches all)')
    args = parser.parse_args()

    # Normalize date
    game_date = args.date
    if '-' in game_date and len(game_date) == 10:
        parts = game_date.split('-')
        game_date_api = f"{parts[1]}/{parts[2]}/{parts[0]}"
    else:
        game_date_api = game_date

    target_dir = args.dir
    os.makedirs(target_dir, exist_ok=True)

    print("=" * 60)
    print("🏀 NBA Reflector — Play-by-Play 擷取器 V1")
    print(f"📅 日期: {game_date_api}")
    print("=" * 60)

    # Determine which games to fetch
    if args.games:
        game_ids = [g.strip() for g in args.games.split(',')]
        print(f"🎯 指定 {len(game_ids)} 場賽事")
        # Still need scoreboard for team info
        scoreboard_games = fetch_scoreboard(game_date_api)
        games_to_process = []
        for game in scoreboard_games:
            if game.get('gameId') in game_ids:
                games_to_process.append(game)
        if not games_to_process:
            # If scoreboard fails, create minimal game entries
            games_to_process = [{'gameId': gid} for gid in game_ids]
    else:
        scoreboard_games = fetch_scoreboard(game_date_api)
        if not scoreboard_games:
            print("❌ 該日期冇 NBA 賽事")
            sys.exit(1)
        games_to_process = scoreboard_games

    print(f"📊 處理 {len(games_to_process)} 場賽事")

    all_pbp_briefs = []

    for game in games_to_process:
        game_id = game.get('gameId', '?')
        home_team = game.get('homeTeam', {}).get('teamTricode', '?')
        away_team = game.get('awayTeam', {}).get('teamTricode', '?')
        tag = f"{away_team}_{home_team}" if home_team != '?' else game_id

        print(f"\n🏀 {away_team} @ {home_team} (ID: {game_id})")

        actions = fetch_pbp(game_id)
        if not actions:
            print(f"  ⚠️ 無法擷取 PBP，跳過")
            continue

        analysis = analyze_pbp(actions, home_team, away_team)

        pbp_brief = {
            'game_id': game_id,
            'matchup': f"{away_team} @ {home_team}",
            'home_team': home_team,
            'away_team': away_team,
            **analysis,
        }

        all_pbp_briefs.append(pbp_brief)

        # Print key findings
        if analysis.get('blowout_analysis'):
            ba = analysis['blowout_analysis']
            print(f"  🔴 BLOWOUT 偵測: {ba['leading_team']} 領先 20+ @ {ba['first_20pt_margin']}")

        qb = analysis.get('quarter_breakdown', {})
        for q, data in sorted(qb.items()):
            print(f"  📊 {q}: Home {data['home']} - Away {data['away']} (diff: {data['diff']:+d})")

    # Build final output
    output = {
        '_version': 'PBP_BRIEF_V1',
        '_generated_by': 'fetch_nba_pbp.py',
        'date': args.date,
        'total_games': len(all_pbp_briefs),
        'games': all_pbp_briefs,
    }

    out_path = os.path.join(target_dir, f'PBP_Brief_{args.date}.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"🏆 完成！{len(all_pbp_briefs)} 場 Play-by-Play 已擷取")
    print(f"📄 輸出: {out_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
