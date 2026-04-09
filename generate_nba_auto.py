#!/usr/bin/env python3
"""
generate_nba_auto.py — NBA Wong Choi 數據包生成器 (V5 — Data Brief)

V5 架構改革:
  Python = 數據供應商（純 JSON 輸出，零敘事，零決策）
  LLM    = 分析師（讀 JSON → 獨立分析 → 揀 Combo → 寫核心邏輯）
  Python = 品控（verify_nba_math.py 只驗數學）

V5 改動清單:
  1. 輸出格式: Skeleton.md → Data_Brief_{TAG}.json
  2. 刪除所有 Markdown 生成邏輯
  3. 刪除 Python narrative 生成
  4. 保留 python_suggestions 作為「Must-Respond」建議池
  5. 完整 8-Factor breakdown for ALL players/lines
  6. 唔再生成 Master SGM/Banker reports（由 LLM 跨場構建）

Usage:
  python3 generate_nba_auto.py
"""

import sys
import os
import json
import glob
import io
import time
import math
import re
import urllib.request
import urllib.error

# Fix encoding for Chinese output
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add the skill scripts to path so we can import the real generator
SKILL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
    ".agents/skills/nba/nba_wong_choi/scripts")
sys.path.insert(0, SKILL_DIR)

# Import only the MATH functions from generate_nba_reports — no Markdown generation
from generate_nba_reports import (
    compute_stats,
    grade_cov,
    weighted_avg,
    trend_label,
    hit_rate,
    implied_prob,
    edge_calc,
    edge_grade,
    calc_adjusted_winprob,
    build_leg_candidates,
    select_combo_1,
    select_combo_2,
    select_combo_3,
    select_combo_x_value_bomb,
    build_player_card,
)

# Import nba_api for real stats
try:
    from nba_api.stats.endpoints import playergamelog, leaguedashteamstats, commonteamroster
    from nba_api.stats.static import players as nba_players, teams as nba_teams
    NBA_API_OK = True
    print("✅ nba_api 已載入 — 將使用真實 API 數據")
except ImportError:
    NBA_API_OK = False
    print("❌ nba_api 未安裝，無法抓取真實數據。請執行: pip install nba_api")
    sys.exit(1)

API_SLEEP = 0.7  # Rate limit protection

# ─── Config ──────────────────────────────────────────────────────────────
BASE_DIR = "2026-04-08 NBA Analysis"

TEAM_LOOKUP = {
    "ATL": "Atlanta Hawks", "BOS": "Boston Celtics",
    "BKN": "Brooklyn Nets", "CHA": "Charlotte Hornets",
    "CHI": "Chicago Bulls", "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks", "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons", "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets", "IND": "Indiana Pacers",
    "LAC": "LA Clippers", "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies", "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks", "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans", "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder", "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers", "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers", "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs", "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz", "WSH": "Washington Wizards",
}
# Reverse lookup: full name → abbreviation
TEAM_NAME_TO_ABBR = {v: k for k, v in TEAM_LOOKUP.items()}


# ─── Team Roster Cache (V4 新增) ────────────────────────────────────────
_roster_cache = {}

# ESPN team ID mapping for injuries
ESPN_TEAM_IDS = {
    'ATL': 1, 'BOS': 2, 'BKN': 17, 'CHA': 30, 'CHI': 4, 'CLE': 5,
    'DAL': 6, 'DEN': 7, 'DET': 8, 'GSW': 9, 'HOU': 10, 'IND': 11,
    'LAC': 12, 'LAL': 13, 'MEM': 29, 'MIA': 14, 'MIL': 15, 'MIN': 16,
    'NOP': 3, 'NYK': 18, 'OKC': 25, 'ORL': 19, 'PHI': 20, 'PHX': 21,
    'POR': 22, 'SAC': 23, 'SAS': 24, 'TOR': 28, 'UTA': 26, 'WSH': 27,
}


def fetch_espn_game_lines(game_date):
    """
    Fetch spread + total from ESPN Scoreboard API.
    Checks both game_date and the day before (AU timezone is 14h ahead of US ET).
    Returns dict: { (away_abbr, home_abbr): {spread_away, total, ml_away, ml_home} }
    """
    print(f"📊 抓取 ESPN 賽事盤口 (spread/total)...")
    
    # ESPN abbreviation fixes
    espn_fix = {
        'GS': 'GSW', 'SA': 'SAS', 'NY': 'NYK', 'NO': 'NOP',
        'UTAH': 'UTA', 'PHO': 'PHX', 'PHOE': 'PHX',
    }
    
    result = {}
    
    # Check two dates: today and yesterday (AU vs US timezone issue)
    from datetime import datetime, timedelta
    try:
        base_date = datetime.strptime(game_date, '%Y-%m-%d')
    except ValueError:
        base_date = datetime.now()
    dates_to_check = [
        (base_date - timedelta(days=1)).strftime('%Y%m%d'),
        base_date.strftime('%Y%m%d'),
    ]
    
    for date_str in dates_to_check:
        try:
            url = f'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates={date_str}'
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read())
            events = data.get('events', [])
            for event in events:
                comp = event.get('competitions', [{}])[0]
                teams_info = comp.get('competitors', [])
                away = next((t for t in teams_info if t.get('homeAway') == 'away'), {})
                home = next((t for t in teams_info if t.get('homeAway') == 'home'), {})
                away_abbr = away.get('team', {}).get('abbreviation', '').upper()
                home_abbr = home.get('team', {}).get('abbreviation', '').upper()
                away_abbr = espn_fix.get(away_abbr, away_abbr)
                home_abbr = espn_fix.get(home_abbr, home_abbr)
                if not away_abbr or not home_abbr:
                    continue
                # Skip if already found (prefer more recent date)
                key = (away_abbr, home_abbr)
                if key in result and result[key].get('total') != '?':
                    continue
                odds_list = comp.get('odds', [])
                if odds_list:
                    o = odds_list[0]
                    spread_val = o.get('spread', None)
                    total_val = o.get('overUnder', None)
                    details = o.get('details', '')
                    home_ml = o.get('homeTeamOdds', {}).get('moneyLine')
                    away_ml = o.get('awayTeamOdds', {}).get('moneyLine')
                    spread_away = None
                    if spread_val is not None and details:
                        # Check if the favourite abbreviation is in the details text
                        # Need to check both the raw ESPN abbr and our fixed abbr
                        det_upper = details.upper()
                        home_is_fav = home_abbr in det_upper
                        # Also check raw ESPN abbr
                        raw_home = home.get('team', {}).get('abbreviation', '').upper()
                        if raw_home in det_upper:
                            home_is_fav = True
                        if home_is_fav:
                            spread_away = abs(float(spread_val))
                        else:
                            spread_away = -abs(float(spread_val))
                    result[key] = {
                        'spread_away': spread_away if spread_away is not None else '?',
                        'total': total_val if total_val is not None else '?',
                        'ml_away': away_ml if away_ml is not None else '?',
                        'ml_home': home_ml if home_ml is not None else '?',
                        'provider': o.get('provider', {}).get('name', 'ESPN'),
                    }
                elif key not in result:
                    result[key] = {
                        'spread_away': '?', 'total': '?', 'ml_away': '?', 'ml_home': '?',
                    }
        except Exception as e:
            print(f"  ⚠️ ESPN {date_str} 抓取失敗: {e}")
    
    with_odds = sum(1 for v in result.values() if v.get('total') != '?')
    print(f"  ✅ 獲取 {len(result)} 場賽事盤口 ({with_odds} 有 odds)")
    for k, v in result.items():
        if v.get('total') != '?':
            print(f"    {k[0]}@{k[1]}: spread={v['spread_away']} total={v['total']}")
    return result


def fetch_injuries_for_teams(team_abbrs, game_date):
    """
    Fetch injury reports for specified teams from Basketball Reference.
    Returns dict: { team_abbr: { player_name: "status (detail)" } }
    """
    print(f"🏥 抓取傷缺報告 ({', '.join(team_abbrs)})...")
    result = {abbr: {} for abbr in team_abbrs}
    
    # BBRef team name → our abbreviation mapping
    bbref_team_map = {v: k for k, v in TEAM_LOOKUP.items()}
    
    # Method 1: Basketball Reference injury page (reliable, server-rendered HTML)
    try:
        url = 'https://www.basketball-reference.com/friv/injuries.fcgi'
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='replace')
        
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', html, re.DOTALL)
        parsed_count = 0
        
        for row in rows[1:]:  # skip header
            # Player name is in <th> tag with data-stat="player"
            player_match = re.search(
                r'<th[^>]*data-stat="player"[^>]*>.*?<a[^>]*>([^<]+)</a>',
                row, re.DOTALL
            )
            if not player_match:
                continue
            player_name = player_match.group(1).strip()
            
            # Parse data cells
            cells = re.findall(
                r'<td[^>]*data-stat="([^"]+)"[^>]*>(.*?)</td>',
                row, re.DOTALL
            )
            cell_dict = {k: re.sub(r'<[^>]+>', '', v).strip() for k, v in cells}
            
            team_full = cell_dict.get('team_name', '')
            description = cell_dict.get('note', '')
            
            # Map team name to abbreviation
            team_abbr_found = bbref_team_map.get(team_full)
            if not team_abbr_found:
                # Try fuzzy match
                for full_name, abbr in bbref_team_map.items():
                    if full_name in team_full or team_full in full_name:
                        team_abbr_found = abbr
                        break
            
            if team_abbr_found and team_abbr_found in team_abbrs:
                # Extract status from description (e.g., "Out (Ankle) - ...")
                status_match = re.match(r'(Out|Out For Season|Day-To-Day|Questionable|Doubtful|Probable)', description)
                status = status_match.group(1) if status_match else 'Out'
                
                # Extract injury type
                injury_match = re.search(r'\(([^)]+)\)', description)
                injury = injury_match.group(1) if injury_match else ''
                
                result[team_abbr_found][player_name] = f"{status} ({injury})" if injury else status
                parsed_count += 1
        
        if parsed_count > 0:
            total = sum(len(v) for v in result.values())
            print(f"  ✅ Basketball Reference: 獲取 {total} 位傷缺球員 (全聯盟 {parsed_count} 筆)")
            for abbr in team_abbrs:
                inj = result[abbr]
                if inj:
                    out_count = sum(1 for s in inj.values() if 'Out' in s)
                    dtd_count = sum(1 for s in inj.values() if any(x in s for x in ['Day-To-Day', 'Questionable', 'Doubtful']))
                    names = list(inj.keys())[:5]
                    print(f"    {abbr}: {out_count} Out, {dtd_count} DTD/Q/D — {names}")
                else:
                    print(f"    {abbr}: 無傷兵報告 ✅")
            return result
        else:
            print(f"  ⚠️ Basketball Reference: 解析到 0 筆傷兵數據")
    except Exception as e:
        print(f"  ⚠️ Basketball Reference 抓取失敗: {e}")
    
    print(f"  ⚠️ 傷缺數據無法自動取得，建議 LLM 用 web search 補充")
    return result


def fetch_team_roster(team_abbr):
    """Fetch team roster via commonteamroster. Returns dict of player_name → {position, number}."""
    if team_abbr in _roster_cache:
        return _roster_cache[team_abbr]

    team_dict = nba_teams.find_team_by_abbreviation(team_abbr)
    teams_list = [team_dict] if team_dict else []
    if not teams_list:
        full_name = TEAM_LOOKUP.get(team_abbr, "")
        teams_list = nba_teams.find_teams_by_full_name(full_name)
    if not teams_list:
        print(f"    ⚠️ 搵唔到球隊 ID: {team_abbr}")
        _roster_cache[team_abbr] = {}
        return {}

    team_id = teams_list[0]['id']
    try:
        roster = commonteamroster.CommonTeamRoster(team_id=team_id)
        time.sleep(API_SLEEP)
        data = roster.get_normalized_dict()
        players = {}
        for row in data.get("CommonTeamRoster", []):
            name = row.get("PLAYER", "")
            if name:
                players[name] = {
                    "position": row.get("POSITION", "?"),
                    "number": row.get("NUM", "?"),
                }
        _roster_cache[team_abbr] = players
        return players
    except Exception as e:
        print(f"    ⚠️ Roster 抓取失敗 ({team_abbr}): {e}")
        _roster_cache[team_abbr] = {}
        return {}


def build_player_team_map(away_abbr, home_abbr):
    """Build a global player→team map from both rosters."""
    pmap = {}
    for abbr in [away_abbr, home_abbr]:
        roster = fetch_team_roster(abbr)
        for name, info in roster.items():
            pmap[name.lower()] = {
                "team": abbr,
                "position": info.get("position", "?"),
                "number": info.get("number", "?"),
            }
    return pmap


def resolve_player_team(player_name, player_team_map, away_abbr, home_abbr):
    """Resolve which team a player belongs to, with fuzzy matching."""
    pname_lower = player_name.lower()
    if pname_lower in player_team_map:
        return player_team_map[pname_lower]
    last_name = player_name.split()[-1].lower() if player_name else ""
    for key, val in player_team_map.items():
        if key.endswith(last_name) or last_name in key:
            return val
    return {"team": "?", "position": "?", "number": "?"}


# ─── nba_api Data Fetching ───────────────────────────────────────────────

_player_id_cache = {}

def find_player_id(player_name):
    if player_name in _player_id_cache:
        return _player_id_cache[player_name]
    results = nba_players.find_players_by_full_name(player_name)
    if results:
        pid = results[0]['id']
        _player_id_cache[player_name] = pid
        return pid
    last_name = player_name.split()[-1] if player_name else ""
    results = nba_players.find_players_by_last_name(last_name)
    if results:
        for r in results:
            if r.get('full_name', '').lower() == player_name.lower():
                _player_id_cache[player_name] = r['id']
                return r['id']
        pid = results[0]['id']
        _player_id_cache[player_name] = pid
        return pid
    return None


def fetch_player_l10(player_name, player_id):
    try:
        gl = playergamelog.PlayerGameLog(
            player_id=player_id,
            season='2025-26',
            season_type_all_star='Regular Season'
        )
        time.sleep(API_SLEEP)
        data = gl.get_normalized_dict()
        games = data.get("PlayerGameLog", [])
        if not games:
            return None
        last10 = games[:10]
        result = {
            "PTS": [g.get("PTS", 0) for g in last10],
            "FG3M": [g.get("FG3M", 0) for g in last10],
            "REB": [g.get("REB", 0) for g in last10],
            "AST": [g.get("AST", 0) for g in last10],
            "MIN": [g.get("MIN", 0) for g in last10],
            "dates": [g.get("GAME_DATE", "") for g in last10],
            "matchups": [g.get("MATCHUP", "") for g in last10],
        }
        return result
    except Exception as e:
        print(f"    ⚠️ {player_name} gamelog 錯誤: {e}")
        return None


def fetch_all_team_stats():
    """Fetch all team advanced stats (PACE, DEF_RATING, OFF_RATING) from nba_api."""
    print("📊 抓取全聯盟球隊進階數據 (PACE, DEF, OFF)...")
    MAX_RETRIES = 3
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            # MUST use 'Advanced' to get PACE/DEF_RATING/OFF_RATING
            stats = leaguedashteamstats.LeagueDashTeamStats(
                measure_type_detailed_defense='Advanced',
                per_mode_detailed='PerGame',
                season='2025-26',
                season_type_all_star='Regular Season'
            )
            time.sleep(API_SLEEP)
            # Use get_dict() instead of get_normalized_dict() which returns None values
            data = stats.get_dict()
            rs = data.get('resultSets', [])
            if not rs:
                print(f"  ⚠️ 嘗試 {attempt}/{MAX_RETRIES}: resultSets 為空")
                time.sleep(2)
                continue
            headers = rs[0].get('headers', [])
            rows = rs[0].get('rowSet', [])
            if not rows:
                print(f"  ⚠️ 嘗試 {attempt}/{MAX_RETRIES}: rowSet 為空")
                time.sleep(2)
                continue

            # Build header index map
            h_idx = {h: i for i, h in enumerate(headers)}

            # First pass: extract raw data
            teams_raw = []
            for row in rows:
                abbr = row[h_idx['TEAM_ABBREVIATION']] if 'TEAM_ABBREVIATION' in h_idx else None
                if not abbr:
                    # Fallback: map from TEAM_NAME using reverse lookup
                    tname = row[h_idx.get('TEAM_NAME', 1)] if len(row) > 1 else None
                    abbr = TEAM_NAME_TO_ABBR.get(tname)
                if not abbr:
                    continue
                def safe_get(field, default=None):
                    idx = h_idx.get(field)
                    if idx is not None and idx < len(row) and row[idx] is not None:
                        return row[idx]
                    return default

                teams_raw.append({
                    'abbr': abbr,
                    'PACE': safe_get('PACE'),
                    'OFF_RATING': safe_get('OFF_RATING'),
                    'DEF_RATING': safe_get('DEF_RATING'),
                    'NET_RATING': safe_get('NET_RATING'),
                    'W_PCT': safe_get('W_PCT'),
                })

            # Second pass: compute DEF_RANK
            sorted_by_def = sorted(teams_raw, key=lambda x: x.get('DEF_RATING') or 999)
            for rank, team in enumerate(sorted_by_def, 1):
                team['DEF_RANK'] = rank

            # Build result dict
            result = {}
            for team in teams_raw:
                result[team['abbr']] = {
                    'PACE': round(team['PACE'], 2) if team.get('PACE') else '?',
                    'OFF_RATING': round(team['OFF_RATING'], 1) if team.get('OFF_RATING') else '?',
                    'DEF_RATING': round(team['DEF_RATING'], 1) if team.get('DEF_RATING') else '?',
                    'DEF_RANK': team.get('DEF_RANK', '?'),
                    'NET_RATING': round(team['NET_RATING'], 1) if team.get('NET_RATING') else '?',
                    'W_PCT': round(team['W_PCT'], 3) if team.get('W_PCT') else '?',
                }

            # Validate: check at least one team has non-? PACE
            valid_count = sum(1 for v in result.values() if v.get('PACE') != '?')
            if valid_count == 0:
                print(f"  ⚠️ 嘗試 {attempt}/{MAX_RETRIES}: 所有 PACE 都為空，數據可能有問題")
                time.sleep(2)
                continue

            print(f"  ✅ 獲取 {len(result)} 支球隊數據 ({valid_count} 有 PACE)")
            # Debug: show sample
            sample_abbr = list(result.keys())[0] if result else None
            if sample_abbr:
                s = result[sample_abbr]
                print(f"    📋 範例 {sample_abbr}: PACE={s['PACE']} DEF={s['DEF_RATING']} OFF={s['OFF_RATING']} DEF_RANK=#{s['DEF_RANK']}")
            return result

        except Exception as e:
            print(f"  ❌ 嘗試 {attempt}/{MAX_RETRIES} 球隊數據抓取失敗: {e}")
            time.sleep(2)

    print("  🚨 全部 {MAX_RETRIES} 次嘗試失敗，team_stats 將為空")
    return {}


# ─── Bet365 Sanitization ─────────────────────────────────────────────────

def sanitize_bet365_lines(player_props):
    if not isinstance(player_props, dict):
        return {}
    MAX_LINE_MAP = {"points": 50, "threes_made": 12, "rebounds": 20, "assists": 15}
    cleaned = {}
    for category, players in player_props.items():
        if not isinstance(players, dict):
            continue
        max_line = MAX_LINE_MAP.get(category, 50)
        cleaned_players = {}
        for pname, pdata in players.items():
            if not isinstance(pdata, dict):
                continue
            lines = pdata.get("lines", {})
            if not isinstance(lines, dict) or not lines:
                continue
            filtered_lines = {}
            prev_odds = 0
            safe_keys = []
            for x in lines.keys():
                try:
                    float(x)
                    safe_keys.append(x)
                except (ValueError, TypeError):
                    pass
            for line_key in sorted(safe_keys, key=lambda x: float(x)):
                val = float(line_key)
                if val > max_line:
                    continue
                try:
                    odds = float(lines[line_key])
                except (ValueError, TypeError):
                    continue
                if odds < 1.01:
                    continue
                if prev_odds > 0 and odds < prev_odds * 0.95:
                    continue
                filtered_lines[line_key] = lines[line_key]
                prev_odds = odds
            if filtered_lines:
                cleaned_pdata = dict(pdata)
                cleaned_pdata["lines"] = filtered_lines
                cleaned_players[pname] = cleaned_pdata
        if cleaned_players:
            cleaned[category] = cleaned_players
    return cleaned


# ─── B2B Detection ───────────────────────────────────────────────────────

def detect_b2b_from_gamelog(gl):
    dates = gl.get("dates", [])
    if len(dates) >= 2:
        try:
            from datetime import datetime
            d1 = datetime.strptime(dates[0].replace("T00:00:00", ""), "%Y-%m-%d")
            d2 = datetime.strptime(dates[1].replace("T00:00:00", ""), "%Y-%m-%d")
            return abs((d1 - d2).days) <= 1
        except (ValueError, TypeError):
            pass
    return False


# ─── V5: Build ext_player from gamelog ───────────────────────────────────

def build_ext_player_from_gamelog(player_name, gl, position="?"):
    ext = {
        "name": player_name,
        "position": position,
        "gamelog": {
            "PTS": gl.get("PTS", []),
            "FG3M": gl.get("FG3M", []),
            "REB": gl.get("REB", []),
            "AST": gl.get("AST", []),
            "MIN": gl.get("MIN", []),
        },
        "advanced": {},
        "splits": {},
        "fatigue": {},
    }
    return ext


# ─── V5: Build Data Brief JSON ──────────────────────────────────────────

def build_data_brief(meta, odds, injuries, team_stats, all_cards, b2b_info, bet365_time):
    """Build a pure JSON data brief for LLM consumption. Zero narrative."""
    away_abbr = meta["away"]["abbr"]
    home_abbr = meta["home"]["abbr"]

    # Organize player data
    players_data = {}
    cat_label = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}

    for card in all_cards:
        pname = card["name"]
        cl = cat_label.get(card["category"], card["category"])

        if pname not in players_data:
            players_data[pname] = {
                "team": card["team"],
                "position": card.get("position", "?"),
                "jersey": card.get("jersey", "?"),
                "props": {},
            }

        # Build prop data with full 8-factor breakdown
        lines_data = {}
        for line_key, la in card.get("line_analysis", {}).items():
            bd = la.get("adj_breakdown", {})
            lines_data[la["line_display"]] = {
                "odds": float(la["odds"]),
                "implied_prob": la["implied_prob"],
                "base_rate": la.get("base_rate", la["hit_l10"]),
                "adjusted_prob": la["estimated_prob"],
                "edge": la["edge"],
                "edge_grade": la["edge_grade"],
                "l10_hit": la["hit_l10_count"],
                "l5_hit": la["hit_l5_count"],
                "l10_pct": la["hit_l10"],
                "l5_pct": la["hit_l5"],
                "verdict": la["verdict"],
                "eight_factor": {
                    "trend": bd.get("trend", 0),
                    "cov_adj": bd.get("cov", 0),
                    "buffer": bd.get("buffer", 0),
                    "matchup": bd.get("matchup", 0),
                    "context": bd.get("context", 0),
                    "pace": bd.get("pace", 0),
                    "usg": bd.get("usg", 0),
                    "defender": bd.get("defender", 0),
                },
            }

        players_data[pname]["props"][cl] = {
            "l10": card.get("l10", []),
            "stats": {
                "avg": card["avg"],
                "med": card["med"],
                "sd": card["sd"],
                "cov": card["cov"],
                "cov_grade": card["cov_grade"],
            },
            "trend": card["trend"],
            "weighted_avg": card.get("weighted_avg", 0),
            "min_avg": card.get("min_avg", 0),
            "lines": lines_data,
        }

    # Build python_suggestions (Must-Respond)
    candidates = build_leg_candidates(all_cards, team_odds=odds, meta=meta, injuries=injuries)

    combo_1 = select_combo_1(candidates)
    used = set(c["desc"] for c in combo_1)
    remaining = [c for c in candidates if c["desc"] not in used]

    combo_2 = select_combo_2(remaining, exclude_descs=used)
    used2 = used | set(c["desc"] for c in combo_2)
    remaining2 = [c for c in candidates if c["desc"] not in used2]

    combo_3 = select_combo_3(remaining2, exclude_descs=used2)
    combo_x = select_combo_x_value_bomb(candidates)

    def leg_to_suggestion(leg):
        return {
            "desc": leg["desc"],
            "player": leg["player"],
            "team": leg["team"],
            "category": leg["category"],
            "line": leg["line_display"],
            "odds": leg["odds"],
            "edge": leg["edge"],
            "adjusted_prob": leg.get("estimated_prob", leg["hit_l10"]),
            "l10_hit_pct": leg["hit_l10"],
            "cov": leg["cov"],
            "cov_grade": leg["cov_grade"],
        }

    # Top legs by edge (for Must-Respond)
    top_by_edge = sorted(
        [c for c in candidates if c["edge"] > 0 and c.get("hit_l10", 0) >= 40],
        key=lambda x: -x["edge"]
    )[:10]

    brief = {
        "_version": "V7_DATA_BRIEF",
        "_note": "此 JSON 由 Python 生成，包含純數據 + 數學計算。LLM Analyst 讀取後應獨立分析並自主構建 3+1 SGM 組合。",
        "_llm_context": {
            "_instruction": (
                "V7 8-Factor 分工：Python 已計算 trend/cov/buffer/pace 4 個客觀因子。"
                "LLM 必須基於下方提供嘅球隊數據和球員數據，為每個 Leg 賦予以下 4 個客觀因子的 +/- 值並提供推理："
                "(1) matchup: 對位防守影響 [-3 至 +2]"
                "(2) context: B2B/主客/過去賽程密度/大比分差風險 [-3 至 +1]"
                "(3) usg: 隨隊友傷缺而引發嘅球權重分配 [0 至 +3]"
                "(4) defender: 對位防守者的具體壓制力 [-3 至 0]"
                "L10 數據排列方向：左→右 = 最舊→最新。"
            ),
            "combo_targets": {
                "combo_1_safe": "≥ 2.0",
                "combo_2_value": "≥ 4.0",
                "combo_3_aggressive": "≥ 8.0",
                "combo_x_value_bomb": "Edge ≥15%, 可選",
            },
        },
        "meta": {
            "away": meta["away"],
            "home": meta["home"],
            "date": meta.get("date", "2026-04-08"),
            "bet365_time": bet365_time,
        },
        "team_stats": {
            away_abbr: team_stats.get(away_abbr, {}),
            home_abbr: team_stats.get(home_abbr, {}),
        },
        "game_lines": {
            "spread_away": odds.get("spread_away", "?"),
            "total": odds.get("total", "?"),
            "ml_away": odds.get("ml_away", "?"),
            "ml_home": odds.get("ml_home", "?"),
        },
        "injuries": injuries,
        "b2b": b2b_info,
        "players": players_data,
        "python_suggestions": {
            "_must_respond_protocol": (
                "以下係 Python 基於 8-Factor 數學模型嘅建議。"
                "LLM Analyst 必須逐一回應 top_legs_by_edge 前 5 名（同意/修改/拒絕+原因）。"
                "LLM 有權覆蓋任何建議，但必須提供籃球邏輯嘅理由。"
            ),
            "top_legs_by_edge": [leg_to_suggestion(l) for l in top_by_edge],
            "suggested_combo_1_safe": [leg_to_suggestion(l) for l in combo_1] if combo_1 else [],
            "suggested_combo_2_value": [leg_to_suggestion(l) for l in combo_2] if combo_2 else [],
            "suggested_combo_3_aggressive": [leg_to_suggestion(l) for l in combo_3] if combo_3 else [],
            "suggested_combo_x_bomb": [leg_to_suggestion(l) for l in combo_x] if combo_x else [],
        },
    }

    return brief


# ─── V5: Run Single Game (returns Data Brief dict) ──────────────────────

def run_single_game(bet365_path, team_stats_global, espn_lines=None, injuries_global=None):
    """Process one Bet365 JSON → return Data Brief dict."""
    espn_lines = espn_lines or {}
    injuries_global = injuries_global or {}

    with open(bet365_path, 'r', encoding='utf-8') as f:
        bet365 = json.load(f)

    bet365_time = bet365.get("extraction_time", "2026-04-08")
    matchup_raw = bet365.get("matchup", "")
    away_abbr = bet365.get("away_team", "")
    home_abbr = bet365.get("home_team", "")

    if not away_abbr or not home_abbr:
        fname = os.path.basename(bet365_path)
        parts = fname.replace("Bet365_Odds_", "").replace(".json", "").split("_")
        if len(parts) >= 2:
            away_abbr, home_abbr = parts[0], parts[1]

    away_name = TEAM_LOOKUP.get(away_abbr, away_abbr)
    home_name = TEAM_LOOKUP.get(home_abbr, home_abbr)

    meta = {
        "date": "2026-04-08",
        "away": {"name": away_name, "abbr": away_abbr},
        "home": {"name": home_name, "abbr": home_abbr},
    }

    # Team stats from API
    away_ts = team_stats_global.get(away_abbr, {})
    home_ts = team_stats_global.get(home_abbr, {})
    team_stats = {away_abbr: away_ts, home_abbr: home_ts}

    # Game-level odds: Bet365 first, ESPN fallback
    game_lines = bet365.get("game_lines", {})
    espn_match = espn_lines.get((away_abbr, home_abbr), {})
    odds = {
        "spread_away": game_lines.get("spread_away") or espn_match.get("spread_away", "?"),
        "total": game_lines.get("total") or espn_match.get("total", "?"),
        "ml_away": game_lines.get("ml_away") or espn_match.get("ml_away", "?"),
        "ml_home": game_lines.get("ml_home") or espn_match.get("ml_home", "?"),
    }
    if espn_match.get('provider'):
        odds['_source'] = espn_match['provider']

    # Injuries: Bet365 first, then ESPN/CBS global, merge
    injuries = {away_abbr: {}, home_abbr: {}}
    # Layer 1: Bet365 JSON injuries
    bet365_injuries = bet365.get("injuries", {})
    if bet365_injuries:
        for team_key in [away_abbr, home_abbr]:
            team_inj = bet365_injuries.get(team_key, {})
            if isinstance(team_inj, dict):
                injuries[team_key].update(team_inj)
            elif isinstance(team_inj, list):
                for p in team_inj:
                    if isinstance(p, dict) and p.get('name'):
                        injuries[team_key][p['name']] = p.get('status', 'Out')
                    elif isinstance(p, str):
                        injuries[team_key][p] = 'Out'
    # Layer 2: ESPN/CBS global injuries (merge, don't overwrite)
    for team_key in [away_abbr, home_abbr]:
        global_inj = injuries_global.get(team_key, {})
        for pname, status in global_inj.items():
            if pname not in injuries[team_key]:
                injuries[team_key][pname] = status

    # Build player→team roster map
    print(f"  📋 抓取兩隊 Roster ({away_abbr}, {home_abbr})...")
    player_team_map = build_player_team_map(away_abbr, home_abbr)
    print(f"    ✅ Roster 映射: {len(player_team_map)} 位球員")

    # Sanitize Bet365 lines
    player_props = sanitize_bet365_lines(bet365.get("player_props", {}))

    # Collect unique player names
    unique_players = set()
    for category, players_data in player_props.items():
        for player_name in players_data:
            unique_players.add(player_name)

    # Fetch L10 gamelog for each unique player
    cat_map_rev = {"points": "PTS", "threes_made": "FG3M", "rebounds": "REB", "assists": "AST"}
    player_gamelogs = {}
    api_errors = []

    print(f"  📡 抓取 {len(unique_players)} 位球員 L10 gamelog...")
    for pname in sorted(unique_players):
        pid = find_player_id(pname)
        if pid is None:
            api_errors.append(f"❌ {pname}: 搵唔到球員 ID")
            continue
        gl = fetch_player_l10(pname, pid)
        if gl is None:
            api_errors.append(f"⚠️ {pname}: L10 gamelog 為空")
            continue
        player_gamelogs[pname] = gl
        print(f"    ✅ {pname} — L10 抓取成功")

    if api_errors:
        print(f"  ⚠️ API 錯誤共 {len(api_errors)} 個:")
        for err in api_errors[:5]:
            print(f"    {err}")

    # Detect B2B per team
    team_b2b = {away_abbr: False, home_abbr: False}
    for pname, gl in player_gamelogs.items():
        info = resolve_player_team(pname, player_team_map, away_abbr, home_abbr)
        team = info['team']
        if team != "?" and detect_b2b_from_gamelog(gl):
            team_b2b[team] = True

    # Parse spread
    spread_val = odds.get("spread_away")
    spread_for_context = None
    if spread_val and spread_val != "?":
        try:
            spread_for_context = float(spread_val)
        except (ValueError, TypeError):
            pass

    # Build ALL player cards with correct team + ext_player
    all_cards = []
    skipped_players = []

    for category, players_data in player_props.items():
        stat_key = cat_map_rev.get(category, "PTS")
        for player_name, bet_data in players_data.items():
            gl = player_gamelogs.get(player_name)
            if gl is None:
                skipped_players.append(f"{player_name} ({category})")
                continue

            player_info = resolve_player_team(player_name, player_team_map, away_abbr, home_abbr)
            team = player_info['team']
            position = player_info['position']
            jersey = player_info['number']

            if team == away_abbr:
                opponent = home_abbr
                is_home = False
            elif team == home_abbr:
                opponent = away_abbr
                is_home = True
            else:
                opponent = home_abbr
                is_home = None

            opp_stats = team_stats_global.get(opponent, {})
            opp_def_rank = opp_stats.get("DEF_RANK")
            opp_pace = opp_stats.get("PACE")
            is_b2b = team_b2b.get(team, False)

            ext_player = build_ext_player_from_gamelog(player_name, gl, position=position)

            enriched_bet_data = dict(bet_data)
            if jersey and not enriched_bet_data.get("jersey"):
                enriched_bet_data["jersey"] = jersey

            card = build_player_card(
                player_name=player_name,
                team_abbr=team,
                bet365_data=enriched_bet_data,
                ext_player=ext_player,
                category=category,
                opponent_def_rank=opp_def_rank,
                opponent_pace=opp_pace,
                is_b2b=is_b2b,
                is_home=is_home,
                spread=spread_for_context,
                usg_bonus=0,
                defender_impact=None,
                top_defender_name="",
                opponent_abbr=opponent,
            )
            all_cards.append(card)

    print(f"  📊 球員: {len(all_cards)} OK, {len(skipped_players)} 跳過")

    # V5: Build Data Brief JSON (no Markdown!)
    brief = build_data_brief(
        meta=meta,
        odds=odds,
        injuries=injuries,
        team_stats=team_stats,
        all_cards=all_cards,
        b2b_info=team_b2b,
        bet365_time=bet365_time,
    )

    return {
        "away_abbr": away_abbr,
        "home_abbr": home_abbr,
        "matchup": f"{away_name} @ {home_name}",
        "brief": brief,
        "players_ok": len(all_cards),
        "players_skipped": len(skipped_players),
        "api_errors": api_errors,
    }


# ─── Main ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("🏀 NBA Wong Choi — 數據包生成器 V7 (Data Brief)")
    print(f"📂 掃描目錄: {BASE_DIR}")
    print("=" * 60)

    # Step 1: Fetch global team stats (PACE/DEF/OFF)
    team_stats_global = fetch_all_team_stats()

    # Step 2: Find all Bet365 JSON files
    files = sorted(glob.glob(f"{BASE_DIR}/Bet365_Odds_*.json"))
    skip_patterns = ["TEST", "GEMINI", "MIN.json"]

    # Step 2.5: Extract all team abbreviations from file names for injury fetch
    all_team_abbrs = set()
    for fpath in files:
        basename = os.path.basename(fpath)
        if any(p in basename for p in skip_patterns):
            continue
        parts = basename.replace("Bet365_Odds_", "").replace(".json", "").split("_")
        if len(parts) >= 2:
            all_team_abbrs.add(parts[0])
            all_team_abbrs.add(parts[1])

    # Step 3: Fetch ESPN game lines (spread/total) - one API call for all games
    espn_lines = fetch_espn_game_lines("2026-04-08")

    # Step 4: Fetch injury reports for all teams - one request to CBS Sports
    injuries_global = {}
    if all_team_abbrs:
        injuries_global = fetch_injuries_for_teams(list(all_team_abbrs), "2026-04-08")

    generated = 0
    skipped = 0
    total_api_errors = []

    for fpath in files:
        basename = os.path.basename(fpath)

        if any(p in basename for p in skip_patterns):
            print(f"⏭️ 跳過: {basename}")
            skipped += 1
            continue

        print(f"\n{'─' * 50}")
        print(f"📊 處理中: {basename}")

        try:
            result = run_single_game(fpath, team_stats_global, espn_lines=espn_lines, injuries_global=injuries_global)
        except Exception as e:
            print(f"  ❌ 處理失敗: {e}")
            import traceback
            traceback.print_exc()
            skipped += 1
            continue

        if result is None:
            print(f"  ❌ 生成失敗")
            skipped += 1
            continue

        # V5: Write as Data_Brief JSON
        out_path = f"{BASE_DIR}/Data_Brief_{result['away_abbr']}_{result['home_abbr']}.json"
        with open(out_path, 'w', encoding='utf-8') as f:
            json.dump(result["brief"], f, ensure_ascii=False, indent=2)
        print(f"  ✅ 已生成: {out_path}")

        total_api_errors.extend(result.get("api_errors", []))
        generated += 1

    print(f"\n{'=' * 60}")
    print(f"📊 Data Brief 生成完成: {generated} 場 | 跳過: {skipped} 場")
    if total_api_errors:
        print(f"⚠️ 總共 {len(total_api_errors)} 個 API 錯誤")
    print(f"{'=' * 60}")

    print(f"\n🏆 全部完成！")
    print(f"📎 下一步:")
    print(f"  1. 用 Gemini 開啟新 Session")
    print(f"  2. 觸發 @nba wong choi 逐場分析")
    print(f"  3. LLM 會讀取每場 Data_Brief JSON → 獨立分析 → 輸出 Full_Analysis.md")
    print(f"  4. 每場完成後自動驗證，通過先做下一場")


if __name__ == "__main__":
    main()
