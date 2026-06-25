#!/usr/bin/env python3
"""
build_nba_ml_dataset.py — NBA ML Dataset Builder V1

永久保存所有 NBA 賽果 + 特徵數據，供未來 ML training 使用。
即使 API 日後唔再 available，data 依然留低咗。

What it does:
1. Scan all Wong Choi NBA Analysis/ folders for nba_game_data_*.json (features)
2. For each date, fetch Results_Brief via nba_api (labels / box scores)
3. Build consolidated feature + label dataset → NBA_ML_Dataset/
4. Save every raw Results_Brief permanently in NBA_ML_Dataset/results_brief/

Output:
  NBA_ML_Dataset/
    dataset.csv              — Main feature matrix (one row per player-stat-line)
    dataset_meta.json         — Metadata / column descriptions
    per_date/                 — Per-date raw feature JSON
    results_brief/            — Permanently archived box scores (Results_Brief_*.json)

Usage:
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --date 2026-05-14
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --skip-fetch
  python .agents/scripts/nba_ml/build_nba_ml_dataset.py --skip-verify
"""

import os
import sys
import json
import csv
import math
import argparse
import time
import io

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from pathlib import Path as _Path
PROJECT_ROOT = _Path(__file__).resolve().parents[4]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import NBA_ANALYSIS, NBA_ML_DATASET
ARCHIVE_DIR = str(NBA_ANALYSIS)
DATASET_DIR = str(NBA_ML_DATASET)

# Stat categories we care about
STAT_CATEGORIES = ["PTS", "REB", "AST", "FG3M"]
STAT_KEY_MAP = {"PTS": "pts", "REB": "reb", "AST": "ast", "FG3M": "fg3m"}

# Lines to evaluate per stat (standard Sportsbet milestones)
SPORTSBET_LINES = {
    "PTS": [10, 15, 20, 25, 30, 35, 40],
    "REB": [3, 5, 7, 9, 11, 13, 15],
    "AST": [2, 4, 6, 8, 10, 12],
    "FG3M": [1, 2, 3, 4, 5, 6],
}

API_SLEEP = 0.8

try:
    from nba_api.stats.endpoints import scoreboardv2, boxscoretraditionalv2
    NBA_API_OK = True
except ImportError:
    NBA_API_OK = False


# ─── Results Fetching (built-in, avoids broken reflector imports) ───

def _int(v, default=0):
    """Convert to int, handling None and non-numeric values."""
    if v is None:
        return default
    try:
        return int(v)
    except (ValueError, TypeError):
        return default

def fetch_boxscore(game_id):
    """Fetch box score for a specific game using BoxScoreTraditionalV2."""
    try:
        box = boxscoretraditionalv2.BoxScoreTraditionalV2(game_id=game_id)
        time.sleep(API_SLEEP)
        data = box.get_dict()
        players = []
        for rs in data.get('resultSets', []):
            if rs.get('name') == 'PlayerStats':
                headers = rs['headers']
                h_idx = {h: i for i, h in enumerate(headers)}
                for row in rs.get('rowSet', []):
                    players.append({
                        'name': row[h_idx.get('PLAYER_NAME', 0)],
                        'team': row[h_idx.get('TEAM_ABBREVIATION', 0)],
                        'position': row[h_idx.get('START_POSITION', 0)] or '',
                        'starter': bool(row[h_idx.get('START_POSITION', 0)]),
                        'minutes': row[h_idx.get('MIN', 0)] or '0',
                        'pts': _int(row[h_idx['PTS']]),
                        'reb': _int(row[h_idx['REB']]),
                        'ast': _int(row[h_idx['AST']]),
                        'fg3m': _int(row[h_idx['FG3M']]),
                        'stl': _int(row[h_idx['STL']]),
                        'blk': _int(row[h_idx['BLK']]),
                        'tov': _int(row[h_idx['TO']]),
                        'fgm': _int(row[h_idx['FGM']]),
                        'fga': _int(row[h_idx['FGA']]),
                        'ftm': _int(row[h_idx['FTM']]),
                        'plus_minus': _int(row[h_idx['PLUS_MINUS']]),
                    })
        return {'players': players}
    except Exception as e:
        print(f"    ⚠️ BoxScore error ({game_id}): {e}")
        return None


def parse_minutes(min_str):
    """Parse minutes string to float."""
    if isinstance(min_str, (int, float)):
        return float(min_str)
    if isinstance(min_str, str):
        if min_str.startswith('PT'):
            import re
            m = re.search(r'(\d+)M', min_str)
            return float(m.group(1)) if m else 0
        try:
            return float(min_str.split(':')[0]) if ':' in min_str else float(min_str)
        except (ValueError, IndexError):
            return 0
    return 0


def fetch_results_for_date(game_date):
    """Fetch Results_Brief for a US game date (YYYY-MM-DD).

    Saves to NBA_ML_Dataset/results_brief/Results_Brief_{game_date}.json
    Returns filepath if successful, None otherwise.
    """
    if not NBA_API_OK:
        print("  ❌ nba_api not installed. Run: pip install nba_api")
        return None

    target_dir = os.path.join(DATASET_DIR, "results_brief")
    os.makedirs(target_dir, exist_ok=True)

    out_path = os.path.join(target_dir, f"Results_Brief_{game_date}.json")
    if os.path.exists(out_path):
        print(f"  ⏭️  Results_Brief already exists: {out_path}")
        return out_path

    # Convert YYYY-MM-DD to MM/DD/YYYY for ScoreboardV2
    parts = game_date.split('-')
    if len(parts) == 3:
        game_date_api = f"{parts[1]}/{parts[2]}/{parts[0]}"
    else:
        game_date_api = game_date

    print(f"  📡 Fetching results for US date {game_date_api}...")

    try:
        sb = scoreboardv2.ScoreboardV2(game_date=game_date_api)
        time.sleep(API_SLEEP)
        data = sb.get_dict()
    except Exception as e:
        print(f"    ⚠️ ScoreboardV2 error: {e}")
        return None

    # Parse result sets
    result_sets = {rs['name']: rs for rs in data.get('resultSets', [])}
    game_header = result_sets.get('GameHeader', {})
    line_score = result_sets.get('LineScore', {})

    game_rows = game_header.get('rowSet', [])
    gh_headers = game_header.get('headers', [])
    ls_rows = line_score.get('rowSet', [])
    ls_headers = line_score.get('headers', [])

    if not game_rows:
        print(f"    ⚠️ No games found")
        return None

    print(f"     Found {len(game_rows)} games")

    # Build LineScore lookup: game_id -> {team_abbr -> stats}
    ls_idx = {h: i for i, h in enumerate(ls_headers)}
    ls_by_game = {}
    for row in ls_rows:
        gid = row[ls_idx['GAME_ID']]
        if gid not in ls_by_game:
            ls_by_game[gid] = {}
        team_abbr = row[ls_idx['TEAM_ABBREVIATION']]
        ls_by_game[gid][team_abbr] = row

    gh_idx = {h: i for i, h in enumerate(gh_headers)}
    results = []
    for row in game_rows:
        game_id = row[gh_idx['GAME_ID']]
        home_team_id = row[gh_idx['HOME_TEAM_ID']]
        visitor_team_id = row[gh_idx['VISITOR_TEAM_ID']]
        game_status = row[gh_idx['GAME_STATUS_TEXT']]

        # Find team info from LineScore
        game_ls = ls_by_game.get(game_id, {})
        teams_list = list(game_ls.keys())
        if len(teams_list) >= 2:
            t1_row = game_ls[teams_list[0]]
            t2_row = game_ls[teams_list[1]]
            # Determine home/away: home team ID is known
            # We don't easily know which is home from LineScore, check TeamLeaders
            # Use simple approach: just use both, figure out home/away later
            t1_abbr = t1_row[ls_idx['TEAM_ABBREVIATION']]
            t1_name = t1_row[ls_idx['TEAM_NAME']]
            t1_pts = _int(t1_row[ls_idx['PTS']])
            t2_abbr = t2_row[ls_idx['TEAM_ABBREVIATION']]
            t2_name = t2_row[ls_idx['TEAM_NAME']]
            t2_pts = _int(t2_row[ls_idx['PTS']])
        else:
            t1_abbr = t2_abbr = t1_name = t2_name = ''
            t1_pts = t2_pts = 0

        # Try TeamLeaders for better abbreviation mapping
        tl_set = result_sets.get('TeamLeaders', {})
        tl_rows = tl_set.get('rowSet', [])
        tl_headers = tl_set.get('headers', [])
        tl_idx = {h: i for i, h in enumerate(tl_headers)}
        home_abbr = visitor_abbr = ''
        home_name = visitor_name = ''
        home_pts = visitor_pts = 0
        for tl_row in tl_rows:
            if tl_row[tl_idx['GAME_ID']] == game_id:
                tabbr = tl_row[tl_idx['TEAM_ABBREVIATION']]
                tname = tl_row[tl_idx['TEAM_NICKNAME']]
                # Match to line score pts
                pts = t1_pts if tabbr == t1_abbr else (t2_pts if tabbr == t2_abbr else 0)
                # Assume first team in TeamLeaders for this game is home
                if not home_abbr:
                    home_abbr, home_name, home_pts = tabbr, tname, pts
                else:
                    visitor_abbr, visitor_name, visitor_pts = tabbr, tname, pts

        if not home_abbr and teams_list:
            # Fallback: just use LineScore order
            home_abbr, home_name = t1_abbr, t1_name
            visitor_abbr, visitor_name = t2_abbr, t2_name
            home_pts, visitor_pts = _int(t1_pts), _int(t2_pts)

        home_pts_i = _int(home_pts)
        visitor_pts_i = _int(visitor_pts)
        final_score = f"{visitor_abbr} {visitor_pts_i} - {home_pts_i} {home_abbr}" if visitor_abbr and home_abbr else f"Final"

        result = {
            'game_id': game_id,
            'status': game_status,
            'away': {'team': visitor_abbr, 'name': visitor_name, 'score': visitor_pts_i},
            'home': {'team': home_abbr, 'name': home_name, 'score': home_pts_i},
            'final_score': final_score,
            'margin': abs(home_pts_i - visitor_pts_i),
            'blowout': abs(home_pts_i - visitor_pts_i) >= 20,
            'winner': home_abbr if home_pts_i > visitor_pts_i else visitor_abbr,
        }

        # Fetch detailed box score
        print(f"     📊 Box score: {result['final_score']}...")
        boxscore = fetch_boxscore(game_id)

        if boxscore and boxscore.get('players'):
            players = boxscore['players']
            result['players'] = players

            # Low minutes alert
            low_min = [p for p in players if p['starter'] and parse_minutes(p['minutes']) < 20]
            if low_min:
                result['low_minutes_alert'] = [
                    f"{p['name']} ({p['team']}) — {p['minutes']} MIN" for p in low_min
                ]
        else:
            result['players'] = []

        results.append(result)

    brief = {
        '_version': 'RESULTS_BRIEF_V1',
        '_note': 'Permanently archived box scores for ML training. Generated by build_nba_ml_dataset.py',
        'date': game_date,
        'total_games': len(results),
        'games': results,
    }

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(brief, f, ensure_ascii=False, indent=2)

    print(f"     ✅ Saved: {out_path} ({len(results)} games)")
    return out_path


# ─── Feature Extraction ───

def find_archive_folders():
    """Find all archive folders that contain nba_game_data_*.json or equivalent."""
    folders = []
    for entry in sorted(os.listdir(ARCHIVE_DIR)):
        path = os.path.join(ARCHIVE_DIR, entry)
        if not os.path.isdir(path):
            continue
        feature_files = (
            [f for f in os.listdir(path) if f.startswith("nba_game_data_") and f.endswith(".json")]
            or [f for f in os.listdir(path) if "_data.json" in f and f.startswith("Game_")]
        )
        if feature_files:
            folders.append((entry, path, feature_files))
    return folders


def extract_date_from_game_data(filepath):
    """Extract game date from nba_game_data JSON meta."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        date_str = data.get("meta", {}).get("date", "")
        if date_str:
            return date_str[:10]
    except Exception:
        pass
    return None


def extract_game_data(filepath):
    """Extract structured feature rows from nba_game_data JSON.

    Returns list of dicts, one row per (player, stat_category, line_value).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"    ❌ Error reading {filepath}: {e}")
        return []

    meta = data.get("meta", {})
    game_date = (meta.get("date") or "")[:10]
    away_abbr = (meta.get("away") or {}).get("abbr", "")
    home_abbr = (meta.get("home") or {}).get("abbr", "")
    game_tag = f"{away_abbr}_{home_abbr}"

    team_stats = data.get("team_stats", {})

    rows = []

    for abbr in [away_abbr, home_abbr]:
        is_home = abbr == home_abbr
        opp_abbr = home_abbr if is_home else away_abbr
        opp_stats = team_stats.get(opp_abbr, {})
        opp_def_rating = opp_stats.get("DEF_RATING", 0)
        opp_pace = opp_stats.get("PACE", 98.0)
        opp_def_rank = opp_stats.get("DEF_RANK", 0)

        for player in data.get("players", {}).get(abbr, []):
            name = player.get("name", "")
            position = player.get("position", "")
            advanced = player.get("advanced", {})
            splits = player.get("splits") or {}
            gamelog = player.get("gamelog") or {}
            fatigue = player.get("fatigue") or {}
            prop_analytics = player.get("prop_analytics") or {}

            usg_pct = advanced.get("USG_PCT", 0)
            ts_pct = advanced.get("TS_PCT", 0)
            player_def_rtg = advanced.get("DEF_RATING", 0)
            min_played = float(advanced.get("MIN") or 0)
            min_arr = gamelog.get("MIN") or []
            min_stats = gamelog.get("MIN_stats") or {}
            min_avg = min_stats.get("avg", round(sum(min_arr) / len(min_arr), 1) if min_arr else 0)

            # Split data
            split_fields = {
                "home_ppg": splits.get("Home_PPG", 0) or 0,
                "away_ppg": splits.get("Road_PPG", 0) or 0,
                "home_rpg": splits.get("Home_RPG", 0) or 0,
                "away_rpg": splits.get("Road_RPG", 0) or 0,
                "home_apg": splits.get("Home_APG", 0) or 0,
                "away_apg": splits.get("Road_APG", 0) or 0,
                "home_fg3m": splits.get("Home_FG3M", 0) or 0,
                "away_fg3m": splits.get("Road_FG3M", 0) or 0,
            }

            # B2B / fatigue
            b2b_flag = 1 if fatigue and fatigue.get("is_b2b", False) else 0
            normal_ppg = (fatigue or {}).get("normal_ppg", 0) or 0
            b2b_ppg = (fatigue or {}).get("b2b_ppg", 0) or 0
            b2b_ppg_diff_pct = round((b2b_ppg - normal_ppg) / normal_ppg, 4) if normal_ppg > 0 else 0
            rest_days = (fatigue or {}).get("rest_days", 1) if fatigue else 1

            # Defender impact from key_defenders (top defender of opponent)
            defender_pm = 0
            for d in data.get("key_defenders", {}).get(opp_abbr, []):
                defender_pm = d.get("PCT_PLUSMINUS", 0)
                break

            # Usage redistribution (teammate injuries)
            usg_bonus = 0
            for redist in (data.get("usage_redistribution", {}) or {}).values():
                if isinstance(redist, dict) and redist.get("player") == name:
                    usg_bonus = redist.get("usage_bonus_pct", 0) or 0
                    break

            base_row = {
                "game_date": game_date,
                "game_tag": game_tag,
                "player": name,
                "team": abbr,
                "opponent": opp_abbr,
                "position": position,
                "is_home": 1 if is_home else 0,
                "min_avg": min_avg,
                "min_played": min_played,
                "usg_pct": usg_pct,
                "ts_pct": ts_pct,
                "def_rtg": player_def_rtg,
                "opp_def_rating": opp_def_rating,
                "opp_def_rank": opp_def_rank,
                "opp_pace": opp_pace,
                "defender_pm": defender_pm,
                "usg_bonus_pct": usg_bonus,
                "b2b_flag": b2b_flag,
                "b2b_ppg_diff_pct": b2b_ppg_diff_pct,
                "rest_days": rest_days,
                **split_fields,
            }

            for stat in STAT_CATEGORIES:
                pa = prop_analytics.get(stat) or {}
                gl_stats = gamelog.get(f"{stat}_stats") or {}
                arr = gamelog.get(stat) or []

                l10_avg = gl_stats.get("avg", 0)
                l10_sd = gl_stats.get("sd", 0)
                l10_cov = gl_stats.get("cov", 0)
                l10_med = gl_stats.get("med", 0)

                l5_arr = arr[:5] if len(arr) >= 5 else arr
                l5_avg = round(sum(l5_arr) / len(l5_arr), 1) if l5_arr else 0
                l3_arr = arr[:3] if len(arr) >= 3 else arr
                l3_avg = round(sum(l3_arr) / len(l3_arr), 1) if l3_arr else 0

                pace_adj = round((opp_pace - 98.0) / 98.0 * l10_avg, 1) if l10_avg > 0 else 0
                pace_projected = round(l10_avg + pace_adj, 1)

                for line in SPORTSBET_LINES.get(stat, []):
                    row = dict(base_row)
                    row["stat_category"] = stat
                    row["line_value"] = line
                    row["l10_avg"] = l10_avg
                    row["l10_sd"] = l10_sd
                    row["l10_cov"] = l10_cov
                    row["l10_med"] = l10_med
                    row["l5_avg"] = l5_avg
                    row["l3_avg"] = l3_avg
                    row["pace_projected"] = pace_projected

                    # Hit rates from prop_analytics or manual
                    if pa and "sportsbet_lines" in pa:
                        matched = [li for li in pa["sportsbet_lines"] if li.get("line") == line]
                        if matched:
                            row["hit_rate_l10"] = matched[0].get("hit_rate_L10", 0)
                            row["hit_rate_l5"] = matched[0].get("hit_rate_L5", 0)
                            row["hit_rate_l3"] = matched[0].get("hit_rate_L3", 0)
                            row["amc"] = matched[0].get("AMC", 0)
                        else:
                            hits = sum(1 for x in arr if x > line) if arr else 0
                            row["hit_rate_l10"] = round(hits / len(arr) * 100, 0) if arr else 0
                            h5 = sum(1 for x in l5_arr if x > line) if l5_arr else 0
                            row["hit_rate_l5"] = round(h5 / len(l5_arr) * 100, 0) if l5_arr else 0
                            h3 = sum(1 for x in l3_arr if x > line) if l3_arr else 0
                            row["hit_rate_l3"] = round(h3 / len(l3_arr) * 100, 0) if l3_arr else 0
                            clr = [x - line for x in arr if x > line] if arr else []
                            row["amc"] = round(sum(clr) / len(clr), 1) if clr else 0
                    else:
                        hits = sum(1 for x in arr if x > line) if arr else 0
                        row["hit_rate_l10"] = round(hits / len(arr) * 100, 0) if arr else 0
                        h5 = sum(1 for x in l5_arr if x > line) if l5_arr else 0
                        row["hit_rate_l5"] = round(h5 / len(l5_arr) * 100, 0) if l5_arr else 0
                        h3 = sum(1 for x in l3_arr if x > line) if l3_arr else 0
                        row["hit_rate_l3"] = round(h3 / len(l3_arr) * 100, 0) if l3_arr else 0
                        clr = [x - line for x in arr if x > line] if arr else []
                        row["amc"] = round(sum(clr) / len(clr), 1) if clr else 0

                    row["actual_value"] = None
                    row["hit"] = None
                    rows.append(row)

    return rows


# ─── Label Matching ───

# ESPN → NBA standard abbreviation mapping (feature files use ESPN abbr)
ESPN_TO_STANDARD = {
    "GS": "GSW", "NO": "NOP", "NY": "NYK",
    "SA": "SAS", "UTAH": "UTA", "WSH": "WAS",
}
STANDARD_TO_ESPN = {v: k for k, v in ESPN_TO_STANDARD.items()}


def load_results_brief(filepath):
    """Load Results_Brief and build player lookup by game tag (incl ESPN variants)."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None

    games = data.get("games", [])
    if not games:
        return None

    lookup = {}
    for game in games:
        home = game.get("home", {}).get("team", "")
        away = game.get("away", {}).get("team", "")
        standard_tags = [f"{away}_{home}", f"{home}_{away}"]
        # Also add ESPN abbreviation variants
        espn_home = STANDARD_TO_ESPN.get(home, home)
        espn_away = STANDARD_TO_ESPN.get(away, away)
        espn_tags = [f"{espn_away}_{espn_home}", f"{espn_home}_{espn_away}"]

        players = {}
        for p in game.get("players", []):
            name = p.get("name", "")
            if name:
                players[name] = p
        for tag in set(standard_tags + espn_tags):
            lookup[tag] = {"players": players, "final_score": game.get("final_score", "")}

    return lookup


def match_results(rows, results_lookup):
    """Attach actual values and hit/miss to feature rows."""
    game_tag = rows[0].get("game_tag", "") if rows else ""
    game_data = results_lookup.get(game_tag)
    if not game_data:
        rev_tag = game_tag.split("_")[1] + "_" + game_tag.split("_")[0] if "_" in game_tag else ""
        game_data = results_lookup.get(rev_tag)

    if not game_data:
        if rows:
            print(f"    ⚠️ No game match in results for tag '{game_tag}' — available tags: {list(results_lookup.keys())[:6]}")
        return rows

    players_lookup = game_data.get("players", {})

    for row in rows:
        pname = row["player"]
        stat = row["stat_category"]
        line = row["line_value"]
        stat_key = STAT_KEY_MAP.get(stat, stat.lower())

        ps = players_lookup.get(pname)
        if ps:
            actual = int(ps.get(stat_key, 0))
            row["actual_value"] = actual
            row["hit"] = 1 if actual >= line else 0

    return rows


# ─── Main Pipeline ───

def build_consolidated_dataset(folders, skip_fetch=False, skip_verify=False):
    """Build the full dataset from all archive folders."""
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(os.path.join(DATASET_DIR, "per_date"), exist_ok=True)
    os.makedirs(os.path.join(DATASET_DIR, "results_brief"), exist_ok=True)

    all_rows = []
    stats = {
        "dates_processed": 0, "dates_skipped": 0,
        "total_feature_rows": 0, "labeled_rows": 0,
        "hits": 0, "misses": 0,
    }

    for folder_name, folder_path, feature_files in folders:
        print(f"\n{'='*60}")
        print(f"📂 {folder_name}")

        sample_file = os.path.join(folder_path, feature_files[0])
        game_date = extract_date_from_game_data(sample_file)
        if not game_date:
            print(f"  ⚠️  Cannot determine game date, skipping")
            stats["dates_skipped"] += 1
            continue

        print(f"  📅 Game date: {game_date}")

        # Extract features from all game_data files in this folder
        date_rows = []
        for ff in feature_files:
            fpath = os.path.join(folder_path, ff)
            rows = extract_game_data(fpath)
            date_rows.extend(rows)
            # game_tag is already set in extract_game_data from meta (away_abbr_home_abbr)

        if not date_rows:
            print(f"  ⚠️  No feature rows")
            continue

        print(f"  📊 Feature rows: {len(date_rows)}")

        # Fetch + match labels
        if not skip_fetch:
            results_path = os.path.join(DATASET_DIR, "results_brief", f"Results_Brief_{game_date}.json")
            if not os.path.exists(results_path):
                results_path = fetch_results_for_date(game_date)

            if results_path and os.path.exists(results_path):
                results_lookup = load_results_brief(results_path)
                if results_lookup:
                    # Collect rows by game_tag for proper matching
                    from collections import defaultdict
                    by_tag = defaultdict(list)
                    for r in date_rows:
                        by_tag[r["game_tag"]].append(r)

                    matched_all = []
                    for tag, tag_rows in by_tag.items():
                        matched = match_results(tag_rows, results_lookup)
                        matched_all.extend(matched)

                    date_rows = matched_all

                    labeled = sum(1 for r in date_rows if r["hit"] is not None)
                    hits = sum(1 for r in date_rows if r["hit"] == 1)
                    misses = sum(1 for r in date_rows if r["hit"] == 0)
                    print(f"  🏷️  Labeled: {labeled}/{len(date_rows)} ({hits} H, {misses} M)")
                    stats["labeled_rows"] += labeled
                    stats["hits"] += hits
                    stats["misses"] += misses
                else:
                    print(f"  ⚠️  Results_Brief empty")
            else:
                print(f"  ⚠️  No Results_Brief available")
        else:
            print(f"  ⏭️  Skipping label fetch")

        # Save per-date snapshot
        date_output = os.path.join(DATASET_DIR, "per_date", f"dataset_{game_date}.json")
        with open(date_output, "w", encoding="utf-8") as f:
            json.dump(date_rows, f, ensure_ascii=False, indent=2)
        print(f"  💾 Saved: {date_output}")

        all_rows.extend(date_rows)
        stats["dates_processed"] += 1
        stats["total_feature_rows"] += len(date_rows)

    return all_rows, stats


def write_csv(rows, filepath):
    if not rows:
        print("❌ No rows to write")
        return
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"✅ CSV: {filepath} ({len(rows)} rows)")


def main():
    parser = argparse.ArgumentParser(description="NBA ML Dataset Builder V1")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip fetching Results_Brief from nba_api")
    parser.add_argument("--skip-verify", action="store_true",
                        help="Skip running verify_props_hits")
    parser.add_argument("--date", type=str,
                        help="Process only this date (YYYY-MM-DD)")
    args = parser.parse_args()

    print("🏀 NBA ML Dataset Builder V1")
    print("=" * 60)

    folders = find_archive_folders()
    print(f"\n📂 Found {len(folders)} archive folders with feature data")

    if args.date:
        folders = [(n, p, f) for n, p, f in folders if args.date in n]
        print(f"   Filtered to {len(folders)} folders")

    if not folders:
        print("❌ No matching folders found")
        sys.exit(1)

    for name, _, ffs in folders:
        print(f"   {name}: {len(ffs)} game files")

    rows, stats = build_consolidated_dataset(folders, args.skip_fetch, args.skip_verify)

    print(f"\n{'='*60}")
    print(f"📊 DATASET BUILD COMPLETE")
    print(f"   Dates: {stats['dates_processed']}")
    print(f"   Feature rows: {stats['total_feature_rows']}")
    if not args.skip_fetch:
        print(f"   Labeled: {stats['labeled_rows']}")
        print(f"   Hits: {stats['hits']} | Misses: {stats['misses']}")
        if stats['labeled_rows'] > 0:
            hr = stats['hits'] / stats['labeled_rows'] * 100
            print(f"   Hit rate: {hr:.1f}%")
    print(f"{'='*60}")

    csv_path = os.path.join(DATASET_DIR, "dataset.csv")
    write_csv(rows, csv_path)

    meta = {
        "_version": "NBA_ML_DATASET_V1",
        "total_rows": len(rows),
        "labeled_rows": stats.get("labeled_rows", 0),
        "total_hits": stats.get("hits", 0),
        "total_misses": stats.get("misses", 0),
        "dates_processed": stats["dates_processed"],
        "stat_categories": STAT_CATEGORIES,
        "lines_per_stat": SPORTSBET_LINES,
        "feature_columns": list(rows[0].keys()) if rows else [],
        "target_column": "hit",
    }
    meta_path = os.path.join(DATASET_DIR, "dataset_meta.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"✅ Meta: {meta_path}")

    print(f"\n📁 All data → {DATASET_DIR}/")
    print(f"   dataset.csv (main matrix)")
    print(f"   dataset_meta.json (columns)")
    print(f"   per_date/ (raw per-date)")
    print(f"   results_brief/ (box scores — permanent)")


if __name__ == "__main__":
    main()
