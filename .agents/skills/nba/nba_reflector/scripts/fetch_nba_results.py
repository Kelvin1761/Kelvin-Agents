#!/usr/bin/env python3
"""
fetch_nba_results.py — NBA Reflector 賽果擷取器

用 nba_api 自動擷取指定日期嘅所有 NBA 賽果，生成結構化 JSON 供 Reflector 消費。

輸出:
  Results_Brief_{DATE}.json — 包含每場賽事嘅最終比分、每節比分、球員 Box Score

Usage:
  python fetch_nba_results.py --date 2026-04-07 --dir "2026-04-08 NBA Analysis"

  (--date 係美國日期，即澳洲日期 -1)

Version: 1.0.0
"""

import argparse
import json
import os
import sys
import io
import time

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_SLEEP = 0.8  # Rate limit protection

try:
    from nba_api.stats.endpoints import (
        scoreboardv3,
        boxscoretraditionalv3,
        leaguegamefinder,
    )
    from nba_api.stats.static import teams as nba_teams
    NBA_API_OK = True
except ImportError:
    NBA_API_OK = False
    print("❌ nba_api 未安裝。請執行: pip install nba_api")
    sys.exit(1)


def fetch_scoreboard(game_date):
    """Fetch all games on a given date using ScoreboardV3."""
    print(f"📅 擷取 {game_date} 嘅 NBA 賽程...")
    try:
        sb = scoreboardv3.ScoreboardV3(game_date=game_date)
        time.sleep(API_SLEEP)
        data = sb.get_dict()
        games = data.get('scoreboard', {}).get('games', [])
        print(f"  ✅ 搵到 {len(games)} 場賽事")
        return games
    except Exception as e:
        print(f"  ❌ ScoreboardV3 失敗: {e}")
        return []


def fetch_boxscore(game_id):
    """Fetch box score for a specific game."""
    try:
        box = boxscoretraditionalv3.BoxScoreTraditionalV3(game_id=game_id)
        time.sleep(API_SLEEP)
        data = box.get_dict()
        return data
    except Exception as e:
        print(f"    ⚠️ BoxScore 擷取失敗 ({game_id}): {e}")
        return None


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
            players.append({
                'name': player.get('name', '?'),
                'team': team_abbr,
                'position': player.get('position', '?'),
                'starter': player.get('starter', '') == '1',
                'minutes': stats.get('minutes', '0'),
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


def process_game(game):
    """Process a single game from the scoreboard."""
    game_id = game.get('gameId', '')
    home = game.get('homeTeam', {})
    away = game.get('awayTeam', {})
    
    home_abbr = home.get('teamTricode', '?')
    away_abbr = away.get('teamTricode', '?')
    home_score = home.get('score', 0)
    away_score = away.get('score', 0)
    
    result = {
        'game_id': game_id,
        'status': game.get('gameStatusText', ''),
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
        'margin': abs(home_score - away_score),
        'blowout': abs(home_score - away_score) >= 20,
        'winner': home_abbr if home_score > away_score else away_abbr,
    }
    
    # Fetch detailed box score
    print(f"  📊 擷取 {away_abbr} @ {home_abbr} Box Score...")
    boxscore = fetch_boxscore(game_id)
    
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


def main():
    parser = argparse.ArgumentParser(description='NBA Reflector Results Fetcher')
    parser.add_argument('--date', required=True, 
                       help='US game date (YYYY-MM-DD or MM/DD/YYYY)')
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

    # Fetch scoreboard
    games = fetch_scoreboard(game_date_api)
    
    if not games:
        print("❌ 該日期冇 NBA 賽事，或 API 呼叫失敗")
        sys.exit(1)

    # Process each game
    results = []
    for game in games:
        result = process_game(game)
        results.append(result)
        
        score = result['final_score']
        blowout = " 🔴 BLOWOUT" if result['blowout'] else ""
        print(f"    ✅ {score}{blowout}")
        
        if result.get('low_minutes_alert'):
            for alert in result['low_minutes_alert']:
                print(f"    ⚠️ 低上場時間: {alert}")

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
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"🏆 完成！{len(results)} 場賽果已擷取")
    print(f"📄 輸出: {out_path}")
    print(f"{'=' * 60}")


if __name__ == '__main__':
    main()
