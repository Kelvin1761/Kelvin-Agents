import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
nba_extractor.py — NBA Wong Choi Claw Code V3 (究極版)

全自動數據提取引擎，為 NBA Wong Choi Analyst 提供 100% 真實、零幻覺的數據包。

模塊清單（ESPN 係唯一數據來源，EXP-20261101-60；賠率只嚟自 Sportsbet JSON，唔喺呢度）：
  1. ESPN API — 賽程、傷病、陣容
  2. ESPN — 全員 L10 Box Score 同季度 game log
  3. ESPN box score／play-by-play — 球隊同球員進階數據

  球員一律用 ESPN athlete id（package 寫 ``player_id_source: espn``）。

用法（orchestrator 就係咁叫）：
  python nba_extractor.py --date 20260402 --game PHX_CHA --output <dir>/nba_game_data_PHX_CHA.json
  python nba_extractor.py --refresh-availability <dir>/nba_game_data_PHX_CHA.json
"""

import json
import math
import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

NBA_SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_SKILL_DIR))
from nba_schedule import canonical_team_abbr, canonical_game_tag, event_sydney_date
from nba_data_contract import NBA_STATISTICS_CONTRACT, TRACKING_UNAVAILABLE, stat_source
import nba_opportunities
import nba_team_context
from nba_availability import compute_usage_redistribution
from nba_season import classify_nba_season
from nba_identity import player_name_key
import nba_espn_stats
import nba_espn_league
import nba_espn_lineups
from nba_availability import (AvailabilityUnavailable, RosterChanged, apply_availability,
                              availability_current, aware_time, fetch_team_availability, refresh_availability)

try:
    import requests
except ImportError:
    print("❌ 缺少核心依賴庫。請執行：pip install requests")
    sys.exit(1)

import atexit
import nba_espn_http
atexit.register(lambda: print(nba_espn_http.summary()))

# ==========================================
# 配置
# ==========================================
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
                "abbreviation": canonical_team_abbr(info.get('abbreviation', '')),
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


def nba_season_for_date(date_value):
    """Return the NBA season label (e.g. 2026-27) for an event/analysis date."""
    text = str(date_value or "")[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        parsed = datetime.now()
    start_year = parsed.year if parsed.month >= 7 else parsed.year - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def previous_nba_season(season):
    start_year = int(str(season).split("-", 1)[0]) - 1
    return f"{start_year}-{str(start_year + 1)[-2:]}"


def statistics_season_for_game(date_value, game_info=None):
    """Use completed prior-season history for preseason shadow analysis only."""
    season = nba_season_for_date(date_value)
    context = classify_nba_season(date_value, game_info)
    return previous_nba_season(season) if context["season_phase"] == "PRESEASON" else season


def history_cutoff_day(date_value):
    """NBA game logs use US game dates. Exclude the entire event's US day."""
    text = str(date_value)
    parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo('Australia/Sydney'))
    return parsed.astimezone(ZoneInfo('America/New_York')).date()


def history_date_to(date_value):
    """Last completed US game day; date-only Sydney inputs are conservative."""
    if not date_value:
        return ""
    return (history_cutoff_day(date_value) - timedelta(days=1)).strftime("%m/%d/%Y")


# League-level feeds need roughly a full league to be usable. After game 1 of a
# new season only the teams that have played return rows, so "non-empty" is not
# enough to trust the current season.
MIN_TEAM_ROWS = 25
MIN_PLAYER_ROWS = 100
ALWAYS_FILL = 10 ** 9   # player-level feeds have no fixed 'complete' size


def fetch_with_season_fallback(fetch_fn, season, as_of, min_rows=1, label="", fill_below=None):
    """Call ``fetch_fn(season, as_of)``; use last season when empty/thin, and fill gaps.

    Two cases, both bounded by ``as_of`` (no game on or after the event's US day is read):

    * whole feed empty/thin (< ``min_rows``): use last season entirely;
    * feed usable but incomplete: keep the current-season rows and fill each MISSING
      key (team / player) from last season.  2026-10-23: after opening night the
      league feed returned 28 teams (>= MIN_TEAM_ROWS) so it was trusted as-is, and
      DEN / CLE - who had not yet played - got no team or advanced data, so their game
      had no combos.  ``fill_below`` (e.g. 30 teams) is the row count at which the
      current feed counts as complete; at or above it no extra request is made.
      ``None`` (default) never fills.

    Returns ``(data, info)``; ``info`` records which season the numbers really come from.
    """
    data = fetch_fn(season, as_of)
    rows = len(data) if data else 0
    info = {
        "label": label,
        "requested_season": season,
        "data_season": season,
        "fallback_used": False,
        "rows": rows,
    }
    prior = previous_nba_season(season)
    if rows < min_rows:
        print(f"  ↩️ {label or 'data'}: {season} 得 {rows} 行 (<{min_rows})，改用 {prior}")
        prior_data = fetch_fn(prior, as_of)
        prior_rows = len(prior_data) if prior_data else 0
        if prior_rows > rows:
            info.update({"data_season": prior, "fallback_used": True,
                         "rows": prior_rows, "current_rows": rows})
            return prior_data, info
        info["fallback_failed"] = True
        return data, info
    if isinstance(data, dict) and fill_below is not None and rows < fill_below:
        prior_data = fetch_fn(prior, as_of)
        if isinstance(prior_data, dict):
            missing = [key for key in prior_data if key not in data]
            if missing:
                merged = dict(data)
                merged.update({key: prior_data[key] for key in missing})
                print(f"  ↩️ {label or 'data'}: {season} 缺 {len(missing)} 項，由 {prior} 補上")
                info.update({
                    "fallback_used": True, "fallback_partial": True, "current_rows": rows,
                    "rows": len(merged), "filled_from": prior, "filled_count": len(missing),
                    "filled_keys": [str(key) for key in missing[:40]],
                })
                return merged, info
    return data, info


# Key defenders and team defence-vs-position were Second Spectrum tracking
# tables, on stats.nba.com only. They are retired (EXP-20261101-60): the keys
# stay in the package, empty and marked, so old readers see "unavailable".
TRACKING_ONLY_TABLES = ("key_defenders", "team_dvp")


def espn_league_tables(season, as_of, data_sources, *, get=None):
    """Team and player advanced tables from ESPN box scores and play-by-play.

    Point-in-time: games up to ``history_date_to(as_of)``. Returns
    ``(team_stats, adv_stats)``; empty tables when ESPN cannot answer, and the
    caller fails closed. ``data_sources`` records where each table came from.
    """
    date_to = history_date_to(as_of)
    team_stats, adv_stats = {}, {}
    try:
        games = nba_espn_league.season_games(season, date_to, get=get)
    except Exception as exc:
        print(f"  ⛔ ESPN 賽果攞唔到：{exc}")
        games = []
    if games:
        team_stats = nba_espn_league.team_advanced(games)
        for record in team_stats.values():
            record["opponent_stats"] = {"status": "unavailable", "season": season,
                                        "history_date_to": date_to, "model_input_enabled": False}
        adv_stats = nba_espn_league.player_advanced(games)
    for label, table in (("team_stats", team_stats), ("player_advanced", adv_stats)):
        data_sources[label] = {"label": label, "requested_season": season, "data_season": season,
                               "fallback_used": False, "rows": len(table),
                               "source": nba_espn_league.SOURCE, "espn_games": len(games)}
    if adv_stats:
        # On-court OFF/DEF/NET rating and PACE from play-by-play lineups
        # (EXP-20261101-01); a failure leaves them None, never guessed.
        try:
            lineup_games = nba_espn_lineups.season_lineups(season, date_to, get=get)
            filled = nba_espn_league.fill_on_court_ratings(
                adv_stats, nba_espn_lineups.player_ratings(lineup_games))
            data_sources["player_advanced"]["espn_pbp_games"] = len(lineup_games)
            data_sources["player_advanced"]["on_court_filled"] = filled
        except Exception as exc:
            print(f"  ⚠️ ESPN 陣容（OFF/DEF rating）計唔到：{exc}")
    for label in TRACKING_ONLY_TABLES:
        data_sources[label] = {"label": label, "requested_season": season, "data_season": season,
                               "fallback_used": False, "rows": 0, "unavailable": TRACKING_UNAVAILABLE}
    print(f"  📊 ESPN 聯盟數據：{len(games)} 場 → 球隊 {len(team_stats)}、球員 {len(adv_stats)}")
    return team_stats, adv_stats


# ==========================================
# 模塊 2：ESPN — 全員 L10 完整 Box Score
# ==========================================
def fetch_team_roster(team_abbr, season=None):
    """ESPN team roster; ``player_id`` is the ESPN athlete id."""
    try:
        return nba_espn_stats.espn_roster(team_abbr)
    except Exception as exc:
        print(f"⚠️ ESPN roster 失敗 ({team_abbr}): {exc}")
        return []


def fetch_team_injuries(team_abbr):
    """An empty verified list means healthy; a source failure must never mean healthy."""
    print(f"  🏥 [Module 1b] 獲取 {team_abbr} 即時傷停及完整陣容 (ESPN)...")
    return fetch_team_availability(team_abbr, get=requests.get)


FIT_STATS = ("PTS", "REB", "AST", "FG3M")


def compute_fit_inputs(df, game_season):
    """Point-in-time inputs for the shadow fit layer (EXP-20261021-05).

    ``df`` is the player's full fetched log, already cut at the event's US day
    and sorted newest-first. Only SAME-season regular-season games with MIN > 0
    count: prior-season carryover, preseason and playoff rows are excluded, so
    an early-season fallback can never masquerade as season-to-date totals.
    Never raises: failure is recorded as ``{"error": ...}``.
    """
    try:
        import pandas as pd
        same = df[(df["_season"] == game_season) & (df["_season_type"] == "Regular Season")]
        mins = pd.to_numeric(same["MIN"], errors="coerce").fillna(0)
        same = same[mins > 0]
        mins = mins[mins > 0]
        last10 = same.head(10)
        out = {
            "season": game_season,
            "same_season_rs_games": int(len(same)),
            "totals": {stat: float(pd.to_numeric(same[stat], errors="coerce").fillna(0).sum()) for stat in FIT_STATS},
            "minutes_total": float(mins.sum()),
            "prior10_games": int(len(last10)),
            "prior10_mean_min": round(float(pd.to_numeric(last10["MIN"], errors="coerce").mean()), 3) if len(last10) else None,
            "prior10_mean": {stat: round(float(pd.to_numeric(last10[stat], errors="coerce").mean()), 3) if len(last10) else None
                             for stat in FIT_STATS},
        }
        return out
    except Exception as exc:  # shadow data must never break extraction
        return {"error": f"{type(exc).__name__}: {exc}"}


SEASON_LOG_STATS = ("MIN", "PTS", "REB", "AST", "FG3M", "FGA", "FG3A", "FTA", "FGM", "FTM")


def compact_season_log(df):
    """Every fetched game (already cut before the event's US day), newest-first.

    Feeds the shadow season-rate model (EXP-20261025-11), which needs more than
    L10. Same fetch as L10, so no extra API calls. Never raises.
    """
    try:
        import pandas as pd
        dates = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        out = {"dates": [d.strftime("%Y-%m-%d") for d in dates],
               "seasons": [str(x) for x in df["_season"]],
               "season_types": [str(x) for x in df["_season_type"]]}
        if "MATCHUP" in df:
            # Team per game (first token of MATCHUP): S_v4 needs to know who moved.
            out["teams"] = [str(m).split()[0] if str(m).split() else "" for m in df["MATCHUP"]]
        for stat in SEASON_LOG_STATS:
            out[stat] = [float(x) for x in pd.to_numeric(df[stat], errors="coerce").fillna(0)]
        return out
    except Exception as exc:  # shadow data must never break extraction
        return {"error": f"{type(exc).__name__}: {exc}"}


def player_log_frame(player_id, season, date_to, season_type):
    """PlayerGameLog-shaped frame from ESPN (``player_id`` = ESPN athlete id).
    Returns ``(frame, source)``."""
    day = datetime.strptime(date_to, "%m/%d/%Y").date() if date_to else None
    return nba_espn_stats.espn_gamelog_frame(player_id, season, season_type, day), "espn"


def fetch_player_gamelog(player_id, player_name, n=10, season=None, as_of=None, include_previous=False, season_type="Regular Season"):
    """為單一球員提取 L10 完整 Box Score（Season-Agnostic: RS + Playoffs 合併）
    
    Explicit season/date queries keep historical shadow data distinct from current-season data.
    Merge completed RS + playoff games chronologically; never include event-day results.
    """
    try:
        import pandas as pd
        all_dfs = []
        sources = set()
        history_season = season or nba_season_for_date(as_of)
        date_to = history_date_to(as_of)

        if season_type == "Regular Season":
            # 1. Fetch playoff history from the explicitly selected season.
            try:
                df_po, source = player_log_frame(player_id, history_season, date_to, 'Playoffs')
                sources.add(source)
                if not df_po.empty:
                    df_po = df_po.copy()
                    df_po["_season_type"] = "Playoffs"
                    df_po["_season"] = history_season
                    all_dfs.append(df_po)
            except Exception as e:
                print(f"    ⚠️ Playoff gamelog 失敗 (non-critical): {e}")

        # 2. Fetch the same season's regular-season history, with retry.
        rs_success = False
        for attempt in range(2):
            try:
                df_rs, source = player_log_frame(player_id, history_season, date_to, season_type)
                sources.add(source)
                if not df_rs.empty:
                    df_rs = df_rs.copy()
                    df_rs["_season_type"] = season_type
                    df_rs["_season"] = history_season
                    all_dfs.append(df_rs)
                rs_success = True
                break
            except Exception as e:
                if attempt == 0:
                    print(f"    ⚠️ RS gamelog retry ({player_name}): {e}")
                else:
                    print(f"    ❌ RS gamelog 失敗 ({player_name}): {e}")

        if not rs_success:
            return None
        # Early regular season needs completed prior-season history until this
        # season has N games. Empty data is different from a failed current API.
        count = 0
        for frame in all_dfs:
            dates = pd.to_datetime(frame["GAME_DATE"], errors="coerce")
            count += int((dates < pd.Timestamp(history_cutoff_day(as_of))).sum()) if as_of else len(frame)
        if include_previous and season_type == "Regular Season" and count < n:
            prior = previous_nba_season(history_season)
            for kind in ["Playoffs", "Regular Season"]:
                try:
                    frame, source = player_log_frame(player_id, prior, date_to, kind)
                    sources.add(source)
                    if not frame.empty:
                        frame = frame.copy()
                        frame["_season_type"] = kind
                        frame["_season"] = prior
                        all_dfs.append(frame)
                except Exception as exc:
                    print(f"    ⚠️ Previous-season history unavailable ({player_name}, {kind}): {exc}")
        if not all_dfs:
            return None

        # Parse actual dates instead of relying on endpoint/concat ordering.
        df = pd.concat(all_dfs, ignore_index=True)
        df["_played_at"] = pd.to_datetime(df["GAME_DATE"], errors="coerce")
        df = df.dropna(subset=["_played_at"])
        if as_of:
            cutoff = pd.Timestamp(history_cutoff_day(as_of))
            df = df[df["_played_at"] < cutoff]
        df = df.drop_duplicates(subset=['GAME_DATE', 'MATCHUP'], keep='first')
        df = df.sort_values("_played_at", ascending=False, kind="stable")
        if df.empty:
            return None
        total_games = len(df)
        df_l10 = df.head(n)
        actual_l10_count = len(df_l10)
        playoff_in_l10 = int((df_l10["_season_type"] == "Playoffs").sum())
        rs_in_l10 = actual_l10_count - playoff_in_l10

        record = {
            "name": player_name,
            "games_played": total_games,
            "history_season": history_season,
            "history_seasons": list(dict.fromkeys(df_l10["_season"].tolist())),
            "l10_seasons": df_l10["_season"].tolist(),
            "history_date_to": date_to,
            "l10_season_types": df_l10["_season_type"].tolist(),
            "playoff_games_in_l10": playoff_in_l10,
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
        # ESPN is the only feed (it has no PLUS_MINUS; written as 0).
        record["source"] = "espn"
        record["season_log"] = compact_season_log(df)
        record["fit_inputs"] = compute_fit_inputs(
            df, nba_season_for_date(as_of) if as_of else history_season)
        # 計算統計量
        for stat in ["PTS", "REB", "AST", "STL", "BLK", "MIN", "FG3M"]:
            s = calc_stats(record[stat])
            record[f"{stat}_stats"] = s
            record[f"{stat}_label"] = cov_label(s["cov"])

        if playoff_in_l10 > 0:
            print(f"    📋 L{actual_l10_count}: {playoff_in_l10} playoff + {rs_in_l10} RS games")

        return record
    except Exception as e:
        print(f"  ⚠️ {player_name} gamelog 失敗: {e}")
        return None


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
def key_defenders_for_team(defender_data, team_abbr, *, limit=8):
    """The existing 20-attempt sample floor applies to totals, never PerGame."""
    candidates = [row for row in defender_data.values()
                  if canonical_team_abbr(row.get('team', '')) == canonical_team_abbr(team_abbr)
                  and row.get('D_FGA_unit') == 'total_attempts'
                  and row.get('D_FGA', 0) >= 20]
    return sorted(candidates, key=lambda row: row.get('PCT_PLUSMINUS', 0))[:limit]


def extract_single_game(game_info, adv_stats, defender_data, team_dvp, team_stats,
                        data_sources=None, opportunity_sources=None, team_context=None):
    """
    針對單場比賽提取雙方所有球員的深度數據。
    這是核心函數，輸出一個完整的 JSON 數據包。
    """
    away_abbr = game_info['away']['abbreviation']
    home_abbr = game_info['home']['abbreviation']
    away_name = game_info['away']['name']
    home_name = game_info['home']['name']
    target_season = nba_season_for_date(game_info.get('date'))
    season_context = classify_nba_season(game_info.get('date'), game_info)
    statistics_season = statistics_season_for_game(game_info.get('date'), game_info)

    print(f"\n🏀 ========== 深度提取: {away_name} @ {home_name} ==========")

    package = {
        "meta": {
            "game": game_info['name'],
            "date": game_info['date'],
            **season_context,
            "l10_order": "newest_first",
            "roster_season": target_season,
            "statistics_season": statistics_season,
            "history_mode": (
                "previous_season_reference" if statistics_season != target_season
                else "current_season_with_previous_history" if season_context["season_phase"] == "EARLY_REGULAR"
                else "current_season"
            ),
            "history_date_to": history_date_to(game_info.get('date')),
            "data_sources": data_sources or {},
            "statistics_contract": NBA_STATISTICS_CONTRACT,
            "defender_source": {"per_mode": "Totals", "sample_unit": "total_attempts",
                                "observed_players": len(defender_data),
                                "qualified_players": sum(row.get('D_FGA_unit') == 'total_attempts'
                                                         and row.get('D_FGA', 0) >= 20
                                                         for row in defender_data.values()),
                                **({"unavailable": TRACKING_UNAVAILABLE}
                                   if not defender_data and ((data_sources or {}).get("key_defenders") or {}).get("unavailable")
                                   else {})},
            "fallback_used": any(v.get("fallback_used") for v in (data_sources or {}).values()),
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
        "players": {away_abbr: [], home_abbr: []},
        "key_defenders": {away_abbr: [], home_abbr: []},
        "injuries": {away_abbr: {}, home_abbr: {}},
    }

    if season_context["season_phase"] == "PRESEASON":
        package["meta"]["preseason_rookie_history_contract"] = 1

    # 提取雙方陣容與數據
    availability_maps = {}
    for side, abbr, full_name in [("away", away_abbr, away_name), ("home", home_abbr, home_name)]:
        print(f"\n📋 [{abbr}] 提取 {full_name} 陣容...")
        roster = fetch_team_roster(abbr, target_season)

        print(f"  👥 陣容人數: {len(roster)}")

        # 抓取真實傷病名單並存儲到 metadata
        injury_map = fetch_team_injuries(abbr)
        availability_maps[abbr] = injury_map
        package["injuries"][abbr] = injury_map


        # 篩選核心球員 (有進階數據 = 有上場紀錄)
        core_players = []
        for p in roster:
            pid = p['player_id']
            adv = adv_stats.get(pid, {})
            if adv and adv.get('USG_PCT', 0) > 0:
                core_players.append(p)

        # 如果篩選太少，放寬條件
        if len(core_players) < 5 or season_context["season_phase"] == "PRESEASON":
            core_players = roster  # Do not drop priced starters by roster row order.

        print(f"  🎯 核心球員: {len(core_players)}")

        for p in core_players:
            pid = p['player_id']
            pname = p['name']
            statuses = [status for name, status in injury_map.items()
                        if player_name_key(name) == player_name_key(pname)]
            p_status = statuses[0] if len(statuses) == 1 else 'Active'
            p['status'] = p_status
            
            # 若為 Out 或明顯傷兵，標註並在某些場合可以略過，但這裡仍然提取以備不時之需（使用率重新分配）
            status_tag = f"[{p_status}]" if p_status != 'Active' else ""
            print(f"  📊 提取 {pname} {status_tag}...")

            # L10 Game Log
            rookie_preseason = (
                season_context["season_phase"] == "PRESEASON"
                and str(p.get("experience", "")).upper() == "R"
            )
            gamelog = fetch_player_gamelog(
                pid, pname, season=target_season if rookie_preseason else statistics_season,
                as_of=game_info.get('date'),
                include_previous=season_context["season_phase"] == "EARLY_REGULAR",
                season_type="Pre Season" if rookie_preseason else "Regular Season",
            )
            if rookie_preseason and gamelog:
                package["meta"]["history_mode"] = "previous_season_reference_with_current_preseason_rookies"

            adv = adv_stats.get(pid, {})

            player_entry = {
                "name": pname,
                "status": p_status,
                "player_id": int(pid),
                "player_id_source": "espn",
                "position": p.get('position') or '',
                "age": p.get('age', ''),
                "advanced": adv,
                "gamelog": gamelog,
            }
            
            if opportunity_sources is not None:
                opp_team = home_abbr if side == "away" else away_abbr
                player_entry["opportunity_features"] = nba_opportunities.build_features(
                    player_entry, abbr, canonical_team_abbr(opp_team), opportunity_sources,
                    tip=game_info['date'], season=statistics_season,
                    cutoff=history_date_to(game_info['date']), opponent_stats=team_stats.get(opp_team, {}))

            package["players"][abbr].append(player_entry)

        # 防守者
        # Availability must remove departed / unavailable players before the
        # top-eight context cap, otherwise old-season leaders consume the pool.
        package["key_defenders"][abbr] = key_defenders_for_team(defender_data, abbr, limit=None)

        # 🧠 Usage Redistribution (Module D1)
        usg_redist = compute_usage_redistribution(package["players"][abbr], abbr)
        if usg_redist:
            package.setdefault("usage_redistribution", {})[abbr] = usg_redist
        
        # 🧠 Correlation Warnings (Module D3)
        corr_warnings = compute_correlation_warnings(package["players"][abbr], abbr)
        if corr_warnings:
            package.setdefault("correlation_warnings", {})[abbr] = corr_warnings

    if opportunity_sources is not None:
        package["meta"]["opportunity_health"] = nba_opportunities.summarize(package["players"])
    if team_context is not None:
        # Shadow S_v2 input (EXP-20261025-13): what each side's OPPONENT allowed per game.
        try:
            cutoff_day = history_cutoff_day(game_info.get('date'))
            package["opponent_context"] = {
                away_abbr: nba_team_context.opponent_context(team_context, home_abbr, cutoff_day),
                home_abbr: nba_team_context.opponent_context(team_context, away_abbr, cutoff_day),
            }
            # Shadow S_v3 input (EXP-20261026-01): each side's own last-10 games.
            package["team_recent"] = {
                abbr: nba_team_context.team_recent(team_context, abbr, cutoff_day) for abbr in (away_abbr, home_abbr)
            }
        except Exception as exc:  # shadow data must never break extraction
            package["opponent_context"] = {"error": f"{type(exc).__name__}: {exc}"}
    # Shadow S2 input (EXP-20261111-03): rest, role and absences known before the game.
    try:
        import nba_minutes
        package["minutes_context"] = nba_minutes.game_context(
            target_season, history_date_to(game_info.get('date')),
            history_cutoff_day(game_info.get('date')), (away_abbr, home_abbr))
    except Exception as exc:  # shadow data must never break extraction
        package["minutes_context"] = {"status": "error", "error": f"{type(exc).__name__}: {exc}"}
    package["meta"]["stat_source"] = stat_source(package)
    return apply_availability(package, availability_maps)


# ==========================================
# 主程式
# ==========================================
def _write_verified_package(path, package):
    from datetime import timezone
    now = datetime.now(timezone.utc)
    tip = aware_time(package.get("meta", {}).get("date"))
    if tip is not None and tip <= now:
        raise AvailabilityUnavailable("game already started; cached pregame data is protected")
    if not availability_current(package, now=now):
        package = refresh_availability(package, fetch=fetch_team_injuries, now=now)
    temporary = path + ".availability.tmp"
    try:
        with open(temporary, "w", encoding="utf-8") as target:
            json.dump(package, target, ensure_ascii=False, indent=2, allow_nan=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi Claw Code V3 Extractor")
    parser.add_argument("--date", type=str, help="YYYYMMDD (AEST)", default=None)
    parser.add_argument("--game", type=str, help="Game tag e.g. PHX_CHA", default=None)
    parser.add_argument("--output", type=str, help="Output path (default nba_game_data_<TAG>.json)", default=None)
    parser.add_argument("--refresh-availability", help="Refresh only verified injuries/roster in a cached game JSON")
    args = parser.parse_args()
    if not args.refresh_availability and not args.game:
        parser.error("--game is required (one game per run, as the orchestrator calls it)")

    if args.refresh_availability:
        path = args.refresh_availability
        try:
            with open(path, encoding="utf-8") as source:
                package = json.load(source)
            package = refresh_availability(package, fetch=fetch_team_injuries)
            package.pop("official_injuries", None)   # retired (EXP-20261101-60)
        except RosterChanged as exc:
            print(f"⏳ {exc}")
            raise SystemExit(2)
        except (OSError, ValueError, AvailabilityUnavailable) as exc:
            print(f"⛔ availability_unavailable: {exc}")
            raise SystemExit(75)
        _write_verified_package(path, package)
        return

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
        found = [
            game
            for event in events
            if event_sydney_date(event) == aest_date.date()
            for game in parse_espn_events([event])
        ]
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

    # ── Step 2: 全聯盟預載 (ESPN — 只計一次) ──
    analysis_game = next(
        (game for game in games if args.game and canonical_game_tag(game['tag']) == canonical_game_tag(args.game)),
        min(games, key=lambda game: game['date']) if games else None,
    )
    stats_date = analysis_game['date'] if analysis_game else formatted_date
    statistics_season = statistics_season_for_game(stats_date, analysis_game)
    print(f"📚 歷史數據球季: {statistics_season} | 截止: {history_date_to(stats_date)}")
    tables = {}   # one ESPN computation per season, shared by both feeds

    def league(season_, as_of_):
        if season_ not in tables:
            sources_ = {}
            tables[season_] = (*espn_league_tables(season_, as_of_, sources_), sources_)
        return tables[season_]
    team_stats, adv_stats, data_sources = {}, {}, {}
    if games:
        # Season start: thin current feeds use / fill from last season, as before.
        team_stats, team_info = fetch_with_season_fallback(
            lambda s_, a_: league(s_, a_)[0], statistics_season, stats_date, MIN_TEAM_ROWS, "team_stats", fill_below=30)
        adv_stats, adv_info = fetch_with_season_fallback(
            lambda s_, a_: league(s_, a_)[1], statistics_season, stats_date, MIN_PLAYER_ROWS, "player_advanced")
        data_sources = dict(league(statistics_season, stats_date)[2])
        data_sources["team_stats"] = {**data_sources["team_stats"], **team_info}
        data_sources["player_advanced"] = {**data_sources["player_advanced"], **adv_info}
    defender_data, team_dvp = {}, {}   # tracking tables, retired with stats.nba.com
    # Fail closed: a package without team pace/defence and player usage is not
    # a degraded analysis, it is none.
    if games and (not team_stats or not adv_stats):
        print("❌ league_tables_unavailable: ESPN 計唔到球隊／球員進階數據；唔會用空白聯盟數據出分析")
        sys.exit(1)

    output_dir = Path(args.output).resolve().parent if args.output else Path.cwd()
    # Research-only opportunity evidence: one league capture shared by game runs.
    opportunity_sources = nba_opportunities.fetch_sources(
        statistics_season, history_date_to(stats_date),
        output_dir / "NBA_Opportunity_Sources.json") if games else {"status": "no_official_games", "sources": {}}
    try:  # shadow S_v2 input only; a failure here must never stop extraction
        team_context = nba_team_context.fetch_bundle(
            statistics_season, previous_nba_season(statistics_season), history_date_to(stats_date),
            output_dir / "NBA_Team_Context.json") if games else None
    except Exception as exc:
        print(f"⚠️ team context unavailable: {type(exc).__name__}: {exc}")
        team_context = {"status": "error", "tables": {}}
    print("📐 Opportunity sources: " + ", ".join(
        f"{name}={source.get('status')}" for name, source in opportunity_sources.get('sources', {}).items()))

    # ── Step 3: 單場深度提取 ──
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

    if not target_game:
        print(f"❌ official_game_not_found: {game_tag_input}，唔會以 synthetic game/date 代替官方賽程。")
        sys.exit(1)

    package = extract_single_game(target_game, adv_stats, defender_data, team_dvp, team_stats,
                                  data_sources=data_sources, opportunity_sources=opportunity_sources,
                                  team_context=team_context)

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
        print(f"   可能原因: ESPN 唔通／熔斷中 / 球隊 abbreviation 唔啱")
        sys.exit(1)

    # 儲存為 JSON
    output_path = args.output or f"nba_game_data_{target_game['tag']}.json"

    _write_verified_package(output_path, package)
    print(f"\n✅ 單場深度數據已儲存至: {output_path}")


    print("\n🏁 提取完成！")


if __name__ == "__main__":
    try:
        main()
    except AvailabilityUnavailable as exc:
        print(f"⛔ availability_unavailable: {exc}", file=sys.stderr)
        sys.exit(75)
