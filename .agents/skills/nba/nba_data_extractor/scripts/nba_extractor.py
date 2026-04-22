import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
nba_extractor.py — NBA Wong Choi Claw Code V3 (究極版)

全自動數據提取引擎，為 NBA Wong Choi Analyst 提供 100% 真實、零幻覺的數據包。

模塊清單：
  1. ESPN API — 賽程、傷病
  2. nba_api — 全員 L10 Box Score、進階數據、Home/Away Splits、Rest Day Splits
  3. nba_api — 球員級別防守影響力 (DvP)
  4. nba_api — 球隊進階防守/進攻/節奏
  5. The Odds API — Sportsbet 精確賠率 (需 API Key)
  6. Claw Code (curl_cffi) — Action Network 備用賠率

用法：
  # 提取今日所有賽事概覽
  python nba_extractor.py --date 20260402

  # 針對單場比賽深度提取 (推薦用法，配合 Game-by-Game 分析)
  python nba_extractor.py --date 20260402 --game PHX_CHA --output .agents.agents/tmp/nba_game_data_PHX_CHA.json

安裝依賴：
  pip install nba_api requests curl-cffi
"""

import json
import math
import argparse
import time
from datetime import datetime, timedelta

try:
    import requests
    from curl_cffi import requests as cffi_requests
except ImportError:
    print("❌ 缺少核心依賴庫。請執行：pip install curl-cffi requests")
    sys.exit(1)

try:
    from nba_api.stats.endpoints import (
        playergamelog,
        commonteamroster,
        leaguedashplayerstats,
        leaguedashteamstats,
        leaguedashptdefend,
        leaguedashptteamdefend,
        playerdashboardbygeneralsplits,
    )
    from nba_api.stats.static import teams, players
    NBA_API_AVAILABLE = True
except ImportError:
    print("⚠️ nba_api 未安裝。請執行：pip install nba_api")
    NBA_API_AVAILABLE = False

# ==========================================
# 配置
# ==========================================
CFFI_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

TEAM_ABBR_ESPN_MAP = {
    "GSW": "GS",
    "NOP": "NO",
    "NYK": "NY",
    "SAS": "SA",
    "UTA": "UTAH",
    "WAS": "WSH"
}

# The Odds API (免費 500 次/月)
# 註冊: https://the-odds-api.com → 免費帳號 → 複製 API Key
# 設定方式: export THE_ODDS_API_KEY="你的key"
THE_ODDS_API_KEY = os.environ.get("THE_ODDS_API_KEY", "")

API_SLEEP = 0.6  # nba_api rate limit 保護

# ==========================================
# 工具函數
# ==========================================
def calc_stats(arr):
    """計算 AVG, MED, SD, CoV"""
    if not arr or len(arr) == 0:
        return {"avg": 0, "med": 0, "sd": 0, "cov": 0}
    n = len(arr)
    avg = sum(arr) / n
    sorted_arr = sorted(arr)
    med = sorted_arr[n // 2] if n % 2 == 1 else (sorted_arr[n // 2 - 1] + sorted_arr[n // 2]) / 2
    variance = sum((x - avg) ** 2 for x in arr) / n
    sd = math.sqrt(variance)
    cov = sd / avg if avg != 0 else 0
    return {"avg": round(avg, 1), "med": round(med, 1), "sd": round(sd, 2), "cov": round(cov, 3)}


def cov_label(cov):
    if cov < 0.15:
        return "🛡️ 極度穩定"
    elif cov < 0.25:
        return "✅ 穩定"
    elif cov < 0.35:
        return "➖ 一般波動"
    else:
        return "🎲 神經刀"


# Sportsbet 標準盤口階梯 (Player Props)
SPORTSBET_LINES = {
    "PTS": [4.5, 9.5, 14.5, 19.5, 24.5, 29.5, 34.5, 39.5],
    "REB": [2.5, 4.5, 6.5, 8.5, 10.5, 12.5, 14.5],
    "AST": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5],
    "STL": [0.5, 1.5, 2.5, 3.5],
    "BLK": [0.5, 1.5, 2.5, 3.5],
    "FG3M": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5],
}

LEAGUE_AVG_PACE = 100.0  # 聯盟平均節奏 (每季微調)


def compute_prop_analytics(gamelog, opp_team_stats, player_splits, is_home):
    """
    🧠 Python Math Engine — 所有數學運算由 Python 執行，零 LLM 參與。
    
    計算項目：
    1. 命中率 (Hit Rate) — 針對每個 Sportsbet 盤口階梯
    2. 穩膽線 (Banker Line) = AVG - 0.5*SD
    3. 價值線 (Value Line) = MED + 正面加成
    4. Pace-Adjusted Projection
    5. +EV 預計算 (基於 1.90 基準賠率)
    6. AMC (Average Margin of Clearing)
    """
    if not gamelog:
        return None
    
    analytics = {}
    
    for stat_key in ["PTS", "REB", "AST", "STL", "BLK", "FG3M"]:
        arr = gamelog.get(stat_key, [])
        if not arr:
            continue
            
        stats = gamelog.get(f"{stat_key}_stats", calc_stats(arr))
        avg = stats["avg"]
        sd = stats["sd"]
        med = stats["med"]
        cov = stats["cov"]
        
        # L5 和 L3 均值
        l5 = arr[:5]
        l3 = arr[:3]
        l5_avg = round(sum(l5) / len(l5), 1) if l5 else 0
        l3_avg = round(sum(l3) / len(l3), 1) if l3 else 0
        
        # 穩膽線 & 價值線
        banker_line = round(avg - 0.5 * sd, 1)
        value_line = round(med + 0.5 * sd, 1)
        
        # Pace-Adjusted Projection
        opp_pace = opp_team_stats.get("PACE", LEAGUE_AVG_PACE)
        pace_adj = round((opp_pace - LEAGUE_AVG_PACE) / LEAGUE_AVG_PACE * avg, 1) if avg > 0 else 0
        pace_projected = round(avg + pace_adj, 1)
        
        # Home/Away 調整
        location_key = "Home" if is_home else "Road"
        location_ppg = 0
        if player_splits:
            split_key = f"{location_key}_PPG" if stat_key == "PTS" else (
                f"{location_key}_RPG" if stat_key == "REB" else (
                    f"{location_key}_APG" if stat_key == "AST" else None
                )
            )
            if split_key:
                location_ppg = player_splits.get(split_key, 0)
        
        # 針對每個 Sportsbet 盤口階梯計算命中率
        lines = SPORTSBET_LINES.get(stat_key, [])
        line_analytics = []
        for line in lines:
            # 過線場次
            hits_l10 = sum(1 for x in arr if x > line)
            hits_l5 = sum(1 for x in l5 if x > line)
            hits_l3 = sum(1 for x in l3 if x > line)
            
            hit_rate_l10 = round(hits_l10 / len(arr) * 100, 0) if arr else 0
            hit_rate_l5 = round(hits_l5 / len(l5) * 100, 0) if l5 else 0
            hit_rate_l3 = round(hits_l3 / len(l3) * 100, 0) if l3 else 0
            
            # AMC (Average Margin of Clearing) — 過線場次的平均超過幅度
            clearing_margins = [x - line for x in arr if x > line]
            amc = round(sum(clearing_margins) / len(clearing_margins), 1) if clearing_margins else 0
            
            # 未過線場次的平均差距
            miss_margins = [line - x for x in arr if x <= line]
            avg_miss = round(sum(miss_margins) / len(miss_margins), 1) if miss_margins else 0
            
            # +EV 計算 — 動態賠率估算模型
            # 根據盤口相對球員均值的位置估算市場賠率
            # ratio = line / avg: <0.5 = very easy (低賠), ~1.0 = coin flip (~1.85), >1.2 = hard (高賠)
            if avg > 0:
                ratio = line / avg
                if ratio <= 0.3:
                    est_odds = 1.08  # 極低線，幾乎必達
                elif ratio <= 0.5:
                    est_odds = round(1.10 + (ratio - 0.3) * 2.0, 2)  # 1.10-1.50
                elif ratio <= 0.75:
                    est_odds = round(1.50 + (ratio - 0.5) * 1.6, 2)  # 1.50-1.90
                elif ratio <= 1.0:
                    est_odds = round(1.90 + (ratio - 0.75) * 2.8, 2)  # 1.90-2.60
                elif ratio <= 1.3:
                    est_odds = round(2.60 + (ratio - 1.0) * 6.0, 2)  # 2.60-4.40
                else:
                    est_odds = round(4.40 + (ratio - 1.3) * 8.0, 2)  # 4.40+
            else:
                est_odds = 1.90
            
            implied_prob = round(1 / est_odds * 100, 1)
            estimated_prob = hit_rate_l10  # 用 L10 命中率作為預估勝率
            edge = round(estimated_prob - implied_prob, 1)
            
            # 判斷是否符合穩膽/價值線標準
            is_banker = hit_rate_l10 >= 80
            is_value = hit_rate_l10 >= 75 and not is_banker
            tier = "🛡️ 穩膽" if is_banker else ("💎 價值" if is_value else "")
            
            line_analytics.append({
                "line": line,
                "direction": "Over",
                "hit_rate_L10": hit_rate_l10,
                "hit_rate_L5": hit_rate_l5,
                "hit_rate_L3": hit_rate_l3,
                "hits": f"{hits_l10}/{len(arr)}",
                "AMC": amc,
                "avg_miss": avg_miss,
                "est_odds": est_odds,
                "implied_prob": implied_prob,
                "estimated_prob": estimated_prob,
                "edge": edge,
                "tier": tier,
            })
            
        analytics[stat_key] = {
            "raw": arr,
            "avg": avg,
            "med": med,
            "sd": sd,
            "cov": cov,
            "cov_label": cov_label(cov),
            "l5_avg": l5_avg,
            "l3_avg": l3_avg,
            "banker_line": banker_line,
            "value_line": value_line,
            "pace_adj": pace_adj,
            "pace_projected": pace_projected,
            "location": location_key,
            "location_avg": location_ppg,
            "sportsbet_lines": line_analytics,
        }
    
    return analytics


# ==========================================
# 模塊 1：ESPN API 賽程與傷病
# ==========================================
def fetch_espn_scoreboard(date_str=None):
    url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
    if date_str:
        url += f"?dates={date_str}"
    print(f"📡 [Module 1] ESPN 賽程: {url}")
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.json().get('events', [])
    except Exception as e:
        print(f"⚠️ ESPN API 失敗: {e}")
        return []


def parse_espn_events(events):
    """解析 ESPN 賽事為結構化列表"""
    games = []
    for evt in events:
        comps = evt.get('competitions', [{}])[0]
        competitors = comps.get('competitors', [])
        away = home = None
        for c in competitors:
            info = c['team']
            entry = {
                "id": info['id'],
                "name": info.get('displayName', info.get('name')),
                "abbreviation": info.get('abbreviation', ''),
                "home_away": c.get('homeAway', '')
            }
            if c.get('homeAway') == 'home':
                home = entry
            else:
                away = entry
        if away and home:
            games.append({
                "game_id": evt['id'],
                "name": evt['name'],
                "date": evt['date'],
                "short_name": evt.get('shortName', ''),
                "season": evt.get('season', {}),
                "competitions": evt.get('competitions', []),
                "away": away,
                "home": home,
                "tag": f"{away['abbreviation']}_{home['abbreviation']}"
            })
    return games


def detect_season_phase(date_str, game_info=None):
    """Classify NBA context for downstream model prompts and MC variance."""
    game_info = game_info or {}
    meta_text = " ".join(str(game_info.get(k, "")) for k in (
        "season_phase", "season_type", "game_type", "name", "short_name"))
    meta_text += " " + str(game_info.get("season", ""))
    meta_upper = meta_text.upper()
    if "PLAYOFF" in meta_upper or "POSTSEASON" in meta_upper:
        return "PLAYOFFS"
    if "PLAY-IN" in meta_upper or "PLAY IN" in meta_upper:
        return "PLAY_IN"
    if "PRESEASON" in meta_upper:
        return "EARLY_SEASON"

    try:
        d = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        try:
            d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        except Exception:
            return "MID_SEASON"

    month, day = d.month, d.day
    if d.year == 2025 and (month == 10 or (month == 11 and day <= 15)):
        return "EARLY_SEASON"
    if d.year == 2026 and ((month == 3 and day >= 25) or (month == 4 and day <= 13)):
        return "LATE_REGULAR"
    if d.year == 2026 and month == 4 and 14 <= day <= 18:
        return "PLAY_IN"
    if d.year == 2026 and ((month == 4 and day >= 19) or month in (5, 6)):
        return "PLAYOFFS"
    return "MID_SEASON"


def fetch_nba_news(team_abbr, limit=5):
    """從 ESPN API 獲取特定球隊的最新的 NBA 新聞"""
    espn_abbr = TEAM_ABBR_ESPN_MAP.get(team_abbr, team_abbr)
    print(f"📰 [Module 1c] 嘗試獲取 {team_abbr} (ESPN:{espn_abbr}) 即日新聞...")
    try:
        url = f"http://site.api.espn.com/apis/site/v2/sports/basketball/nba/news?team={espn_abbr}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            articles = r.json().get('articles', [])
            news_list = []
            for a in articles[:limit]:
                news_list.append({
                    "headline": a.get("headline", ""),
                    "description": a.get("description", "")
                })
            return news_list
        return []
    except Exception as e:
        print(f"  ⚠️ 獲取新聞失敗: {e}")
        return []


# ==========================================
# 模塊 2：nba_api — 全員 L10 完整 Box Score
# ==========================================
def fetch_team_roster(team_nickname):
    """從 nba_api 獲取球隊完整陣容"""
    if not NBA_API_AVAILABLE:
        return []
    all_teams = teams.get_teams()
    match = [t for t in all_teams if t['nickname'] == team_nickname or t['abbreviation'] == team_nickname or team_nickname.lower() in t['full_name'].lower()]
    if not match:
        print(f"⚠️ 找不到球隊: {team_nickname}")
        return []
    team_id = match[0]['id']
    try:
        roster = commonteamroster.CommonTeamRoster(team_id=team_id, season='2025-26')
        df = roster.get_data_frames()[0]
        time.sleep(API_SLEEP)
        result = []
        for _, row in df.iterrows():
            result.append({
                "player_id": row['PLAYER_ID'],
                "name": row['PLAYER'],
                "position": row.get('POSITION', ''),
                "age": row.get('AGE', ''),
                "num": row.get('NUM', ''),
            })
        return result
    except Exception as e:
        print(f"⚠️ Roster 提取失敗 ({team_nickname}): {e}")
        return []


def fetch_team_injuries(team_abbr):
    """從 ESPN API 獲取球隊傷病名單"""
    espn_abbr = TEAM_ABBR_ESPN_MAP.get(team_abbr, team_abbr)
    print(f"  🏥 [Module 1b] 嘗試獲取 {team_abbr} (ESPN:{espn_abbr}) 傷病名單 (ESPN)...")
    try:
        url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_abbr}/roster"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            athletes = r.json().get('athletes', [])
            injury_map = {}
            for a in athletes:
                name = a.get('fullName', '')
                injuries = a.get('injuries', [])
                if injuries and len(injuries) > 0:
                    status = injuries[0].get('status', 'Active')
                    injury_map[name] = status
            return injury_map
        return {}
    except Exception as e:
        print(f"  ⚠️ 獲取傷病名單失敗: {e}")
        return {}


def fetch_player_gamelog(player_id, player_name, n=10):
    """為單一球員提取 L10 完整 Box Score"""
    if not NBA_API_AVAILABLE:
        return None
    try:
        log = playergamelog.PlayerGameLog(player_id=player_id)
        df = log.get_data_frames()[0]
        time.sleep(API_SLEEP)

        if df.empty:
            return None

        df_l10 = df.head(n)
        record = {
            "name": player_name,
            "games_played": len(df),
            "l10_dates": df_l10['GAME_DATE'].tolist(),
            "l10_matchups": df_l10['MATCHUP'].tolist(),
            "l10_wl": df_l10['WL'].tolist(),
            "PTS": df_l10['PTS'].tolist(),
            "REB": df_l10['REB'].tolist(),
            "AST": df_l10['AST'].tolist(),
            "STL": df_l10['STL'].tolist(),
            "BLK": df_l10['BLK'].tolist(),
            "TOV": df_l10['TOV'].tolist(),
            "MIN": df_l10['MIN'].tolist(),
            "FGM": df_l10['FGM'].tolist(),
            "FGA": df_l10['FGA'].tolist(),
            "FG_PCT": df_l10['FG_PCT'].tolist(),
            "FG3M": df_l10['FG3M'].tolist(),
            "FG3A": df_l10['FG3A'].tolist(),
            "FTM": df_l10['FTM'].tolist(),
            "FTA": df_l10['FTA'].tolist(),
            "PLUS_MINUS": df_l10['PLUS_MINUS'].tolist(),
        }
        # 計算統計量
        for stat in ["PTS", "REB", "AST", "STL", "BLK", "MIN", "FG3M"]:
            s = calc_stats(record[stat])
            record[f"{stat}_stats"] = s
            record[f"{stat}_label"] = cov_label(s["cov"])

        return record
    except Exception as e:
        print(f"  ⚠️ {player_name} gamelog 失敗: {e}")
        return None


# ==========================================
# 模塊 2.5：nba_api — H2H 歷史對戰數據
# ==========================================
def fetch_player_h2h(player_id, player_name, opp_abbr):
    """提取球員對住特定球隊的歷史對戰數據 (當季 + 上季)"""
    # V3: Re-enabled (was previously disabled)
    if not NBA_API_AVAILABLE:
        return None
    try:
        h2h_games = []
        for season in ['2025-26', '2024-25']:
            try:
                log = playergamelog.PlayerGameLog(player_id=player_id, season=season)
                df = log.get_data_frames()[0]
                time.sleep(API_SLEEP)
                vs_opp = df[df['MATCHUP'].str.contains(opp_abbr)]
                for _, row in vs_opp.iterrows():
                    h2h_games.append({
                        "date": row['GAME_DATE'],
                        "matchup": row['MATCHUP'],
                        "WL": row['WL'],
                        "PTS": int(row['PTS']),
                        "REB": int(row['REB']),
                        "AST": int(row['AST']),
                        "STL": int(row['STL']),
                        "BLK": int(row['BLK']),
                        "MIN": int(row['MIN']),
                        "FGM": int(row['FGM']),
                        "FGA": int(row['FGA']),
                        "FG3M": int(row['FG3M']),
                        "PLUS_MINUS": int(row['PLUS_MINUS']),
                    })
            except Exception:
                pass
        
        if not h2h_games:
            return None
        
        # 計算 H2H 均值
        pts_arr = [g['PTS'] for g in h2h_games]
        reb_arr = [g['REB'] for g in h2h_games]
        ast_arr = [g['AST'] for g in h2h_games]
        
        return {
            "opponent": opp_abbr,
            "total_games": len(h2h_games),
            "games": h2h_games,
            "PTS_avg": round(sum(pts_arr) / len(pts_arr), 1),
            "REB_avg": round(sum(reb_arr) / len(reb_arr), 1),
            "AST_avg": round(sum(ast_arr) / len(ast_arr), 1),
            "PTS_high": max(pts_arr),
            "PTS_low": min(pts_arr),
            # H2H 對線命中率 (用 Banker Line 來檢測)
            "PTS_arr": pts_arr,
            "REB_arr": reb_arr,
            "AST_arr": ast_arr,
        }
    except Exception as e:
        return None


# ==========================================
# 模塊 3：nba_api — 進階球員數據
# ==========================================
def fetch_all_player_advanced_stats():
    """提取全聯盟球員進階數據 (USG%, TS%, DEF_RTG 等)"""
    if not NBA_API_AVAILABLE:
        return {}
    print("📊 [Module 3] 全聯盟球員進階數據 (USG%, TS%, DEF_RTG)...")
    try:
        stats = leaguedashplayerstats.LeagueDashPlayerStats(
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame'
        )
        df = stats.get_data_frames()[0]
        time.sleep(API_SLEEP)

        result = {}
        for _, row in df.iterrows():
            result[row['PLAYER_ID']] = {
                "USG_PCT": round(row.get('USG_PCT', 0) * 100, 1),
                "TS_PCT": round(row.get('TS_PCT', 0) * 100, 1),
                "OFF_RATING": round(row.get('OFF_RATING', 0), 1),
                "DEF_RATING": round(row.get('DEF_RATING', 0), 1),
                "NET_RATING": round(row.get('NET_RATING', 0), 1),
                "PACE": round(row.get('PACE', 0), 1),
                "PIE": round(row.get('PIE', 0) * 100, 1),
                "AST_PCT": round(row.get('AST_PCT', 0) * 100, 1),
                "EFG_PCT": round(row.get('EFG_PCT', 0) * 100, 1),
            }
        print(f"  ✅ 獲取 {len(result)} 位球員進階數據")
        return result
    except Exception as e:
        print(f"  ⚠️ 進階數據失敗: {e}")
        return {}


# ==========================================
# 模塊 4：nba_api — Home/Away & Rest Day Splits
# ==========================================
def fetch_player_splits(player_id, player_name):
    """提取球員 Home/Away 及 Rest Day Splits"""
    if not NBA_API_AVAILABLE:
        return None
    try:
        splits = playerdashboardbygeneralsplits.PlayerDashboardByGeneralSplits(player_id=player_id)
        dfs = splits.get_data_frames()
        time.sleep(API_SLEEP)

        result = {}

        # DF[1] = Home/Road splits
        if len(dfs) > 1 and not dfs[1].empty:
            for _, row in dfs[1].iterrows():
                gp = row.get('GP', 1) or 1
                group = row.get('GROUP_VALUE', '')
                result[f"{group}_PPG"] = round(row.get('PTS', 0) / gp, 1)
                result[f"{group}_RPG"] = round(row.get('REB', 0) / gp, 1)
                result[f"{group}_APG"] = round(row.get('AST', 0) / gp, 1)
                result[f"{group}_MPG"] = round(row.get('MIN', 0) / gp, 1)

        # DF[6] = Rest Day splits
        if len(dfs) > 6 and not dfs[6].empty:
            rest_data = {}
            for _, row in dfs[6].iterrows():
                gp = row.get('GP', 1) or 1
                group = row.get('GROUP_VALUE', '')
                rest_data[group] = {
                    "PPG": round(row.get('PTS', 0) / gp, 1),
                    "RPG": round(row.get('REB', 0) / gp, 1),
                    "GP": gp
                }
            result["rest_splits"] = rest_data

        return result
    except Exception as e:
        print(f"  ⚠️ {player_name} splits 失敗: {e}")
        return None


# ==========================================
# 模塊 5：nba_api — 防守影響力
# ==========================================
def fetch_defender_impact():
    """全聯盟球員級別防守壓制力 (D_FG%, PCT_PLUSMINUS)"""
    if not NBA_API_AVAILABLE:
        return {}
    print("🛡️ [Module 5] 球員防守影響力數據...")
    try:
        dvp = leaguedashptdefend.LeagueDashPtDefend(
            defense_category='Overall',
            per_mode_simple='PerGame'
        )
        df = dvp.get_data_frames()[0]
        time.sleep(API_SLEEP)

        result = {}
        for _, row in df.iterrows():
            pid = row['CLOSE_DEF_PERSON_ID']
            result[pid] = {
                "name": row['PLAYER_NAME'],
                "team": row.get('PLAYER_LAST_TEAM_ABBREVIATION', ''),
                "position": row.get('PLAYER_POSITION', ''),
                "D_FGA": row.get('D_FGA', 0),
                "D_FG_PCT": round(row.get('D_FG_PCT', 0), 3),
                "NORMAL_FG_PCT": round(row.get('NORMAL_FG_PCT', 0), 3),
                "PCT_PLUSMINUS": round(row.get('PCT_PLUSMINUS', 0), 3),
            }
        print(f"  ✅ 獲取 {len(result)} 位球員防守數據")
        return result
    except Exception as e:
        print(f"  ⚠️ 防守數據失敗: {e}")
        return {}


def fetch_team_defense_vs_position():
    """球隊級別 DvP"""
    if not NBA_API_AVAILABLE:
        return {}
    print("🛡️ [Module 5b] 球隊 DvP...")
    try:
        tdvp = leaguedashptteamdefend.LeagueDashPtTeamDefend(
            defense_category='Overall',
            per_mode_simple='PerGame'
        )
        df = tdvp.get_data_frames()[0]
        time.sleep(API_SLEEP)
        result = {}
        for _, row in df.iterrows():
            abbr = row.get('TEAM_ABBREVIATION', '')
            if not abbr:
                # Fallback: map team name to abbreviation
                all_t = teams.get_teams()
                name_map = {t['full_name']: t['abbreviation'] for t in all_t}
                abbr = name_map.get(row.get('TEAM_NAME', ''), '')
            result[abbr] = {
                "D_FG_PCT": round(row.get('D_FG_PCT', 0), 3),
                "PCT_PLUSMINUS": round(row.get('PCT_PLUSMINUS', 0), 3),
            }
        return result
    except Exception as e:
        print(f"  ⚠️ Team DvP 失敗: {e}")
        return {}


# ==========================================
# 模塊 6：球隊進階數據 (DEF_RTG, OFF_RTG, PACE)
# ==========================================
def fetch_team_advanced_stats():
    """全聯盟球隊進階數據"""
    if not NBA_API_AVAILABLE:
        return {}
    print("📊 [Module 6] 球隊進階數據 (Pace, Off RTG, Def RTG)...")
    try:
        stats = leaguedashteamstats.LeagueDashTeamStats(
            measure_type_detailed_defense='Advanced',
            per_mode_detailed='PerGame'
        )
        df = stats.get_data_frames()[0]
        time.sleep(API_SLEEP)

        # 建立 team_id -> abbreviation 映射
        all_teams = teams.get_teams()
        id_to_abbr = {t['id']: t['abbreviation'] for t in all_teams}

        df = df.sort_values(by='DEF_RATING', ascending=True)
        result = {}
        for rank, (_, row) in enumerate(df.iterrows(), 1):
            team_id = row['TEAM_ID']
            abbr = id_to_abbr.get(team_id, '')
            result[abbr] = {
                "name": row['TEAM_NAME'],
                "DEF_RATING": round(row['DEF_RATING'], 1),
                "DEF_RANK": rank,
                "OFF_RATING": round(row['OFF_RATING'], 1),
                "PACE": round(row['PACE'], 2),
                "NET_RATING": round(row['NET_RATING'], 1),
            }
        print(f"  ✅ 獲取 {len(result)} 支球隊數據")
        return result
    except Exception as e:
        print(f"  ⚠️ Team Stats 失敗: {e}")
        return {}


# ==========================================
# 模塊 7：The Odds API (Sportsbet 精確賠率)
# ==========================================
def fetch_odds_api(sport='basketball_nba'):
    """使用 The Odds API 獲取包含 Sportsbet 的精確賠率"""
    if not THE_ODDS_API_KEY:
        print("💰 [Module 7] The Odds API: 未設定 API Key，跳過。")
        print("   📝 設定方式: export THE_ODDS_API_KEY='你的key'")
        print("   📝 註冊免費帳號: https://the-odds-api.com")
        return {}

    print("💰 [Module 7] The Odds API: 正在抓取 Sportsbet 賠率...")
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds/"
    params = {
        "apiKey": THE_ODDS_API_KEY,
        "regions": "au",  # 澳洲區域 (包含 Sportsbet)
        "markets": "spreads,totals,h2h",
        "oddsFormat": "decimal",
        "bookmakers": "sportsbet",
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            data = r.json()
            remaining = r.headers.get('x-requests-remaining', '?')
            print(f"  ✅ 獲取 {len(data)} 場賽事賠率 | 剩餘配額: {remaining}")
            result = {}
            for game in data:
                away = game.get('away_team', '')
                home = game.get('home_team', '')
                bookmakers = game.get('bookmakers', [])
                if bookmakers:
                    bk = bookmakers[0]
                    markets = {}
                    for mkt in bk.get('markets', []):
                        key = mkt['key']
                        outcomes = {o['name']: o.get('price', 0) for o in mkt.get('outcomes', [])}
                        if key == 'spreads':
                            for o in mkt.get('outcomes', []):
                                outcomes[o['name'] + '_point'] = o.get('point', 0)
                        if key == 'totals':
                            for o in mkt.get('outcomes', []):
                                outcomes[o['name'] + '_point'] = o.get('point', 0)
                        markets[key] = outcomes
                    result[f"{away} vs {home}"] = {
                        "bookmaker": bk.get('title', 'Sportsbet'),
                        "markets": markets
                    }
            return result
        else:
            print(f"  ⚠️ API 回傳 {r.status_code}: {r.text[:200]}")
            return {}
    except Exception as e:
        print(f"  ⚠️ The Odds API 失敗: {e}")
        return {}


# ==========================================
# 模塊 8：Action Network 備用賠率 (Claw Code)
# ==========================================
def fetch_action_network_odds(date_str):
    """使用 curl_cffi 從 Action Network V2 API 提取真實賠率"""
    print("💰 [Module 8] Action Network 賠率 (curl_cffi Claw Code)...")
    try:
        clean_date = date_str.replace('-', '')
        url = f"https://api.actionnetwork.com/web/v2/scoreboard/nba?date={clean_date}&bookIds=15,30,76,68,69,75,123"
        r = cffi_requests.get(url, headers=CFFI_HEADERS, impersonate="chrome120")
        if r.status_code == 200:
            data = r.json()
            games = data.get('games', [])
            result = {}
            for g in games:
                teams_list = g.get('teams', [])
                if len(teams_list) < 2:
                    continue
                away_abbr = teams_list[0].get('abbr', '')
                home_abbr = teams_list[1].get('abbr', '')
                game_key = f"{away_abbr}_{home_abbr}"
                
                # 解析 markets 結構 (V2 格式: markets -> book_id -> event -> spread/total)
                markets = g.get('markets', {})
                spread_val = None
                total_val = None
                ml_away = None
                ml_home = None
                book_name = "Consensus"
                
                # 優先用 book_id=15 (Sportsbet)，fallback 到任何可用
                for bid in ['68', '15', '30', '76', '69', '75', '123']:
                    bk = markets.get(bid, {})
                    if not bk:
                        continue
                    evt = bk.get('event', {})
                    spreads = evt.get('spread', [])
                    totals = evt.get('total', [])
                    moneylines = evt.get('moneyline', [])
                    
                    if spreads:
                        for s in spreads:
                            if s.get('side') == 'away':
                                spread_val = s.get('value')
                        book_name = "Sportsbet" if bid == '68' else f"Book_{bid}"
                    if totals:
                        for t in totals:
                            if t.get('side') == 'over':
                                total_val = t.get('value')
                    if moneylines:
                        for m in moneylines:
                            if m.get('side') == 'away':
                                ml_away = m.get('odds')
                            elif m.get('side') == 'home':
                                ml_home = m.get('odds')
                    if spread_val is not None:
                        break  # 找到就停
                
                result[game_key] = {
                    "spread_away": spread_val,
                    "total": total_val,
                    "ml_away": ml_away,
                    "ml_home": ml_home,
                    "book": book_name,
                    "standings": {
                        away_abbr: f"{teams_list[0].get('standings',{}).get('win',0)}-{teams_list[0].get('standings',{}).get('loss',0)}",
                        home_abbr: f"{teams_list[1].get('standings',{}).get('win',0)}-{teams_list[1].get('standings',{}).get('loss',0)}",
                    }
                }
                print(f"  ✅ {game_key}: Spread={spread_val} | Total={total_val} | Book={book_name}")
            
            print(f"  ✅ 獲取 {len(result)} 場賠率")
            return result
        else:
            print(f"  ⚠️ API 回傳 {r.status_code}")
            return {}
    except Exception as e:
        print(f"  ⚠️ Action Network 失敗: {e}")
        return {}


# ==========================================
# 模塊 D1：Usage Redistribution (傷缺紅利自動計算)
# ==========================================
def compute_usage_redistribution(players, team_abbr):
    """
    當核心球員缺陣時，自動計算球權重新分配。
    原理：缺陣球員的 USG% 按比例分配給其他活躍球員。
    """
    active = []
    injured_usg = 0
    
    for p in players:
        adv = p.get('advanced', {})
        gl = p.get('gamelog')
        usg = adv.get('USG_PCT', 0)
        
        # 如果最近無 gamelog 或少於 3 場，視為缺陣
        if not gl or gl.get('games_played', 0) < 3:
            injured_usg += usg
        else:
            active.append(p)
    
    redistribution = {}
    if injured_usg > 0 and active:
        total_active_usg = sum(p.get('advanced', {}).get('USG_PCT', 0) for p in active)
        for p in active:
            p_usg = p.get('advanced', {}).get('USG_PCT', 0)
            share = p_usg / total_active_usg if total_active_usg > 0 else 0
            bonus_usg = round(injured_usg * share, 1)
            redistribution[p['name']] = {
                "original_USG": p_usg,
                "bonus_USG": bonus_usg,
                "projected_USG": round(p_usg + bonus_usg, 1),
            }
    
    return redistribution


# ==========================================
# 模塊 D2：Rest Day Fatigue Model
# ==========================================
def compute_fatigue_adjustment(player_splits, gamelog):
    """
    根據休息日數自動調整預期值。
    如果 0 Days Rest (B2B) 的 PPG 顯著低於 1+ Days Rest，生成警告。
    """
    if not player_splits:
        return None
    
    rest_splits = player_splits.get('rest_splits', {})
    if not rest_splits:
        return None
    
    b2b = rest_splits.get('0 Days Rest', {})
    normal = rest_splits.get('1 Days Rest', {})
    
    if not b2b or not normal:
        return None
    
    b2b_ppg = b2b.get('PPG', 0)
    normal_ppg = normal.get('PPG', 0)
    
    fatigue_drop = round(normal_ppg - b2b_ppg, 1) if normal_ppg > 0 else 0
    fatigue_pct = round(fatigue_drop / normal_ppg * 100, 1) if normal_ppg > 0 else 0
    
    return {
        "b2b_ppg": b2b_ppg,
        "normal_ppg": normal_ppg,
        "fatigue_drop": fatigue_drop,
        "fatigue_pct": fatigue_pct,
        "warning": f"⚠️ B2B 疲勞警告: PPG 下降 {fatigue_pct}%" if fatigue_pct > 10 else ""
    }


# ==========================================
# 模塊 D3：Correlation Warning System
# ==========================================
def compute_correlation_warnings(players, team_abbr):
    """
    自動偵測同場 SGM Legs 之間嘅正/負相關性。
    規則：
    - 🚨 同隊 3 人全買 PTS Over = 球權衝突 (Cannibal Risk)
    - ✅ 控衛 AST Over + 射手 PTS Over = 正相關
    - 🚨 Team market 不混入 player milestone SGM；總分盤只作背景參考
    """
    warnings = []
    high_usg_players = []
    
    for p in players:
        adv = p.get('advanced', {})
        if adv.get('USG_PCT', 0) > 20:
            high_usg_players.append(p['name'])
    
    if len(high_usg_players) >= 3:
        warnings.append({
            "type": "🚨 Cannibal Risk",
            "detail": f"{team_abbr} 有 {len(high_usg_players)} 位高球權球員 ({', '.join(high_usg_players[:4])})，同時買 PTS Over 會互相競爭球權",
        })
    
    return warnings


# ==========================================
# 主引擎：單場深度提取
# ==========================================
def extract_single_game(game_info, adv_stats, defender_data, team_dvp, team_stats, odds_data):
    """
    針對單場比賽提取雙方所有球員的深度數據。
    這是核心函數，輸出一個完整的 JSON 數據包。
    """
    away_abbr = game_info['away']['abbreviation']
    home_abbr = game_info['home']['abbreviation']
    away_name = game_info['away']['name']
    home_name = game_info['home']['name']

    print(f"\n🏀 ========== 深度提取: {away_name} @ {home_name} ==========")

    package = {
        "meta": {
            "game": game_info['name'],
            "date": game_info['date'],
            "season_phase": detect_season_phase(game_info['date'], game_info),
            "l10_order": "newest_first",
            "away": {"name": away_name, "abbr": away_abbr},
            "home": {"name": home_name, "abbr": home_abbr},
            "extracted_at": datetime.now().isoformat(),
        },
        "team_stats": {
            away_abbr: team_stats.get(away_abbr, {}),
            home_abbr: team_stats.get(home_abbr, {}),
        },
        "team_dvp": {
            away_abbr: team_dvp.get(away_abbr, {}),
            home_abbr: team_dvp.get(home_abbr, {}),
        },
        "odds": {},
        "news": {away_abbr: [], home_abbr: []},
        "players": {away_abbr: [], home_abbr: []},
        "key_defenders": {away_abbr: [], home_abbr: []},
        "injuries": {away_abbr: {}, home_abbr: {}},
    }

    # 賠率 — 嘗試多種 key 組合以匹配 Action Network 格式
    # Action Network 用 home_away 順序 + 標準縮寫 (WAS, UTA, GSW, NOP)
    # ESPN 用 away_home 順序 + ESPN 縮寫 (WSH, UTAH, GS, NO)
    ESPN_TO_STANDARD = {v: k for k, v in TEAM_ABBR_ESPN_MAP.items()}  # reverse map
    away_std = ESPN_TO_STANDARD.get(away_abbr, away_abbr)
    home_std = ESPN_TO_STANDARD.get(home_abbr, home_abbr)
    odds_candidates = [
        f"{away_abbr}_{home_abbr}",     # ESPN away_home
        f"{home_abbr}_{away_abbr}",     # ESPN home_away
        f"{away_std}_{home_std}",       # Standard away_home
        f"{home_std}_{away_std}",       # Standard home_away (AN format)
        f"{away_std}_{home_abbr}",      # Mixed
        f"{away_abbr}_{home_std}",      # Mixed
        f"{home_std}_{away_abbr}",      # Mixed
        f"{home_abbr}_{away_std}",      # Mixed
    ]
    matched_odds = {}
    for candidate in odds_candidates:
        if candidate in odds_data:
            matched_odds = odds_data[candidate]
            print(f"  💰 賠率匹配成功: {candidate}")
            break
    if not matched_odds:
        print(f"  ⚠️ 賠率匹配失敗 — 嘗試過: {odds_candidates[:4]}")
    package["odds"] = matched_odds

    # 提取雙方陣容與數據
    for side, abbr, full_name in [("away", away_abbr, away_name), ("home", home_abbr, home_name)]:
        print(f"\n📋 [{abbr}] 提取 {full_name} 陣容...")
        roster = fetch_team_roster(full_name)
        if not roster:
            # 嘗試用縮寫
            roster = fetch_team_roster(abbr)

        print(f"  👥 陣容人數: {len(roster)}")

        # 抓取真實傷病名單並存儲到 metadata
        injury_map = fetch_team_injuries(abbr)
        package["injuries"][abbr] = injury_map
        
        # 抓取球隊新聞
        team_news = fetch_nba_news(abbr, limit=5)
        package["news"][abbr] = team_news

        # 篩選核心球員 (有進階數據 = 有上場紀錄)
        core_players = []
        for p in roster:
            pid = p['player_id']
            adv = adv_stats.get(pid, {})
            if adv and adv.get('USG_PCT', 0) > 0:
                core_players.append(p)

        # 如果篩選太少，放寬條件
        if len(core_players) < 5:
            core_players = roster[:15]  # 最多取 15 人

        print(f"  🎯 核心球員: {len(core_players)}")

        for p in core_players:
            pid = p['player_id']
            pname = p['name']
            p_status = injury_map.get(pname, 'Active')
            p['status'] = p_status
            
            # 若為 Out 或明顯傷兵，標註並在某些場合可以略過，但這裡仍然提取以備不時之需（使用率重新分配）
            status_tag = f"[{p_status}]" if p_status != 'Active' else ""
            print(f"  📊 提取 {pname} {status_tag}...")

            # L10 Game Log
            gamelog = fetch_player_gamelog(pid, pname)

            # Home/Away & Rest Splits
            splits = fetch_player_splits(pid, pname)

            # 進階數據
            adv = adv_stats.get(pid, {})
            
            # H2H 歷史對戰 (只拉取核心球員 USG > 15%)
            h2h = None
            if adv.get('USG_PCT', 0) > 15:
                opp_abbr_for_h2h = home_abbr if side == "away" else away_abbr
                h2h = fetch_player_h2h(pid, pname, opp_abbr_for_h2h)
                if h2h:
                    print(f"    🎯 H2H vs {opp_abbr_for_h2h}: {h2h['total_games']} 場 | PTS AVG: {h2h['PTS_avg']}")

            player_entry = {
                "name": pname,
                "position": p.get('position', ''),
                "age": p.get('age', ''),
                "advanced": adv,
                "splits": splits,
                "gamelog": gamelog,
                "h2h": h2h,
            }
            
            # 🧠 Python Math Engine: 計算命中率、盤口線、Pace 調整、+EV
            opp_abbr = home_abbr if side == "away" else away_abbr
            opp_stats = team_stats.get(opp_abbr, {})
            is_home = (side == "home")
            prop_analytics = compute_prop_analytics(gamelog, opp_stats, splits, is_home)
            if prop_analytics:
                player_entry["prop_analytics"] = prop_analytics
            
            # 🧠 Fatigue Model
            fatigue = compute_fatigue_adjustment(splits, gamelog)
            if fatigue:
                player_entry["fatigue"] = fatigue
            
            package["players"][abbr].append(player_entry)

        # 防守者
        team_defenders = []
        for did, ddata in defender_data.items():
            dteam = ddata.get('team', '')
            if dteam == abbr or dteam in full_name:
                if ddata.get('D_FGA', 0) >= 20:
                    team_defenders.append(ddata)
        # 按壓制力排序
        team_defenders.sort(key=lambda x: x.get('PCT_PLUSMINUS', 0))
        package["key_defenders"][abbr] = team_defenders[:8]

        # 🧠 Usage Redistribution (Module D1)
        usg_redist = compute_usage_redistribution(package["players"][abbr], abbr)
        if usg_redist:
            package.setdefault("usage_redistribution", {})[abbr] = usg_redist
        
        # 🧠 Correlation Warnings (Module D3)
        corr_warnings = compute_correlation_warnings(package["players"][abbr], abbr)
        if corr_warnings:
            package.setdefault("correlation_warnings", {})[abbr] = corr_warnings

    return package


# ==========================================
# Markdown 報告生成 (概覽版)
# ==========================================
def generate_overview_md(games, team_stats, odds_data):
    """生成今日賽事概覽 Markdown"""
    lines = []
    lines.append("📋 NBA Meeting Intelligence Package (Claw Code V3)")
    lines.append(f"- 數據更新時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    lines.append("🏀 今日賽程：")
    for g in games:
        away = g['away']
        home = g['home']
        a_stats = team_stats.get(away['abbreviation'], {})
        h_stats = team_stats.get(home['abbreviation'], {})
        
        # Get team spread
        game_odds = odds_data.get(g['tag']) if odds_data else None
        spread = game_odds.get('spread') if game_odds else None
        blowout_warn = ""
        if spread is not None:
            if abs(spread) >= 8.5:
                blowout_warn = f"\n- ⚠️ **[BLOWOUT RISK 大炒高危]**: 讓分為 {spread}，主力球員上場時間可能縮減！謹慎操作 PTS Over，改買苦工/籃板/助攻。"
            else:
                blowout_warn = f"\n- ⚖️ [膠著分差]: 讓分為 {spread}，正常操作所有盤口。"

        lines.append(f"### {g['name']} ({g['tag']})")
        lines.append(f"- 開賽時間: {g['date']}")
        lines.append(f"- {away['abbreviation']} DEF: 第{a_stats.get('DEF_RANK','?')} | PACE: {a_stats.get('PACE','?')}")
        lines.append(f"- {home['abbreviation']} DEF: 第{h_stats.get('DEF_RANK','?')} | PACE: {h_stats.get('PACE','?')}{blowout_warn}")
        lines.append("")

    return "\n".join(lines)


# ==========================================
# 繞過 ESPN：直接從 game tag 建構 game_info
# ==========================================
def build_game_info_from_tag(game_tag):
    """當 ESPN 搵唔到賽事時，直接從 game tag 建構 game_info。
    用 nba_api.stats.static.teams 查兩隊嘅 full name 同 team_id。"""
    parts = game_tag.split("_")
    if len(parts) < 2:
        print(f"❌ 無效嘅 game tag: {game_tag}")
        return None
    away_abbr, home_abbr = parts[0], parts[1]

    if not NBA_API_AVAILABLE:
        print("❌ nba_api 未安裝，無法建構 game_info。")
        return None

    all_t = teams.get_teams()
    abbr_map = {t['abbreviation']: t for t in all_t}

    away_team = abbr_map.get(away_abbr)
    home_team = abbr_map.get(home_abbr)

    if not away_team:
        print(f"⚠️ nba_api 搵唔到球隊: {away_abbr}")
        return None
    if not home_team:
        print(f"⚠️ nba_api 搵唔到球隊: {home_abbr}")
        return None

    print(f"🔧 [build_game_info_from_tag] 繞過 ESPN，直接建構: {away_team['full_name']} @ {home_team['full_name']}")
    return {
        "game_id": f"synthetic_{game_tag}",
        "name": f"{away_team['full_name']} at {home_team['full_name']}",
        "date": datetime.now().isoformat(),
        "short_name": f"{away_abbr} @ {home_abbr}",
        "away": {
            "id": away_team["id"],
            "name": away_team["full_name"],
            "abbreviation": away_abbr,
            "home_away": "away",
        },
        "home": {
            "id": home_team["id"],
            "name": home_team["full_name"],
            "abbreviation": home_abbr,
            "home_away": "home",
        },
        "tag": game_tag,
    }


# ==========================================
# 主程式
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi Claw Code V3 Extractor")
    parser.add_argument("--date", type=str, help="YYYYMMDD (AEST)", default=None)
    parser.add_argument("--game", type=str, help="Game tag e.g. PHX_CHA", default=None)
    parser.add_argument("--output", type=str, help="Output path", default="NBA_Data_Package_Auto.md")
    args = parser.parse_args()

    target_date = args.date or datetime.now().strftime("%Y%m%d")
    formatted_date = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:]}"

    print(f"🚀 ========================================")
    print(f"🚀 NBA Wong Choi Claw Code V3")
    print(f"🚀 目標日期: {formatted_date} (AEST)")
    print(f"🚀 ========================================\n")

    # ── Step 1: AEST → US 時區轉換 + ESPN 賽程發現 ──
    # AEST 比 US Eastern 快 14 小時
    # Sportsbet 用 AEST 日期，ESPN 用 US 日期
    # 所以 AEST 4月16日嘅波 = US 4月15日晚嘅波
    aest_date = datetime.strptime(target_date, "%Y%m%d")
    prev_date = (aest_date - timedelta(days=1)).strftime("%Y%m%d")

    candidate_dates = [prev_date, target_date]  # 先試 date-1 (US date)，再試原始日期
    print(f"📅 AEST→US 時區轉換: 嘗試 ESPN 日期 {candidate_dates}")

    games = []
    seen_tags = set()
    for cd in candidate_dates:
        events = fetch_espn_scoreboard(cd)
        found = parse_espn_events(events)
        for g in found:
            if g['tag'] not in seen_tags:
                games.append(g)
                seen_tags.add(g['tag'])
        print(f"  ESPN {cd}: {len(found)} 場")

    print(f"\n✅ ESPN 總計發現 {len(games)} 場賽事")
    if games:
        for g in games:
            print(f"   - {g['tag']}: {g['name']}")
    print()

    # ── Step 2: 全聯盟預載 (nba_api — 只拉一次) ──
    team_stats = fetch_team_advanced_stats()
    adv_stats = fetch_all_player_advanced_stats()
    defender_data = fetch_defender_impact()
    team_dvp = fetch_team_defense_vs_position()

    # ── Step 3: 賠率 (Claw Code 主動提取) ──
    odds_data = fetch_action_network_odds(formatted_date)
    if not odds_data and THE_ODDS_API_KEY:
        odds_data = fetch_odds_api()

    # ── Step 4: 單場模式 (--game) ──
    if args.game:
        target_game = None
        game_tag_input = args.game.upper().replace(" ", "_").replace("@", "_")

        # 建立 ESPN abbreviation 映射版本
        mapped_tags = [game_tag_input]
        if '_' in game_tag_input:
            parts = game_tag_input.split('_')
            m_away = TEAM_ABBR_ESPN_MAP.get(parts[0], parts[0])
            m_home = TEAM_ABBR_ESPN_MAP.get(parts[1], parts[1])
            espn_tag = f"{m_away}_{m_home}"
            if espn_tag != game_tag_input:
                mapped_tags.append(espn_tag)
            # 亦嘗試反向映射
            ESPN_TO_STD = {v: k for k, v in TEAM_ABBR_ESPN_MAP.items()}
            std_away = ESPN_TO_STD.get(parts[0], parts[0])
            std_home = ESPN_TO_STD.get(parts[1], parts[1])
            std_tag = f"{std_away}_{std_home}"
            if std_tag != game_tag_input:
                mapped_tags.append(std_tag)

        # 喺 ESPN 搵到嘅 games 度匹配
        for g in games:
            for mt in mapped_tags:
                if g['tag'] == mt or mt in g['tag'] or mt in g['name']:
                    target_game = g
                    break
            if target_game:
                break

        # 如果 ESPN 搵唔到 → 用 nba_api 直接建構 game_info（繞過 ESPN schedule）
        if not target_game:
            print(f"\n⚠️ ESPN 賽程搵唔到: {game_tag_input}")
            print(f"   ESPN 可用: {[g['tag'] for g in games]}")
            print(f"   → 嘗試 nba_api 直接建構（繞過 ESPN schedule）...")
            target_game = build_game_info_from_tag(game_tag_input)
            if not target_game:
                print(f"❌ nba_api 亦無法建構 {game_tag_input}，放棄。")
                sys.exit(1)
            print(f"✅ 成功建構: {target_game['name']}")

        package = extract_single_game(target_game, adv_stats, defender_data, team_dvp, team_stats, odds_data)

        # 驗證數據品質 — 冇真實 gamelog 則 fail
        has_real_data = False
        for team_key in [target_game['away']['abbreviation'], target_game['home']['abbreviation']]:
            for p in package.get('players', {}).get(team_key, []):
                gl = p.get('gamelog')
                if gl and gl.get('PTS') and len(gl['PTS']) > 0:
                    has_real_data = True
                    break
            if has_real_data:
                break

        if not has_real_data:
            print(f"\n❌ [品質檢查] 所有球員都冇 L10 gamelog 數據！")
            print(f"   可能原因: nba_api 未安裝 / API 限流 / 球隊 abbreviation 唔啱")
            sys.exit(1)

        # 儲存為 JSON
        output_path = args.output
        if output_path.endswith('.md'):
            output_path = f"nba_game_data_{target_game['tag']}.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(package, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 單場深度數據已儲存至: {output_path}")

    else:
        # 概覽模式
        if not games:
            print("❌ ESPN 同 nba_api 都搵唔到賽事。")
            sys.exit(1)

        overview = generate_overview_md(games, team_stats, odds_data)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(overview)
        print(f"\n✅ 賽事概覽已儲存至: {args.output}")

        print("\n🏀 正在為每場比賽生成深度數據包...")
        for g in games:
            package = extract_single_game(g, adv_stats, defender_data, team_dvp, team_stats, odds_data)

            json_path = f"nba_game_data_{g['tag']}.json"
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(package, f, ensure_ascii=False, indent=2)
            print(f"  ✅ {g['tag']} → {json_path}")

    print("\n🏁 提取完成！")


if __name__ == "__main__":
    main()
