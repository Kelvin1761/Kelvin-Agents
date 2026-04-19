#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
fetch_nba_h2h.py — H2H Historic Data Integration V2 (Multi-API Cascading Fallback)

Three-tier API fallback for fetching historical head-to-head matchup data:
  🥇 Tier 1: nba_api (stats.nba.com) — official, most comprehensive
  🥈 Tier 2: balldontlie.io — stable REST API, free tier
  🥉 Tier 3: ESPN Hidden API — unofficial, unstable
  💀 Tier 4: Mock data (last resort, Factor 11 weight = 0)

Usage:
  python fetch_nba_h2h.py --team_a BOS --team_b MIA --line 5.5
"""

import argparse
import json
import os
import random
import traceback
from datetime import datetime

# ─── Team ID Mappings ────────────────────────────────────────────────────

# ESPN team IDs (for Tier 3 fallback)
ESPN_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 17, "CHA": 30, "CHI": 4, "CLE": 5,
    "DAL": 6, "DEN": 7, "DET": 8, "GSW": 9, "HOU": 10, "IND": 11,
    "LAC": 12, "LAL": 13, "MEM": 29, "MIA": 14, "MIL": 15, "MIN": 16,
    "NOP": 3, "NYK": 18, "OKC": 25, "ORL": 19, "PHI": 20, "PHX": 21,
    "POR": 22, "SAC": 23, "SAS": 24, "TOR": 28, "UTA": 26, "WAS": 27,
}

# balldontlie team IDs
BDL_TEAM_IDS = {
    "ATL": 1, "BOS": 2, "BKN": 3, "CHA": 4, "CHI": 5, "CLE": 6,
    "DAL": 7, "DEN": 8, "DET": 9, "GSW": 10, "HOU": 11, "IND": 12,
    "LAC": 13, "LAL": 14, "MEM": 15, "MIA": 16, "MIL": 17, "MIN": 18,
    "NOP": 19, "NYK": 20, "OKC": 21, "ORL": 22, "PHI": 23, "PHX": 24,
    "POR": 25, "SAC": 26, "SAS": 27, "TOR": 28, "UTA": 29, "WAS": 30,
}


# ─── Tier 1: nba_api (Official stats.nba.com) ────────────────────────────

def _fetch_h2h_nba_api(team_a, team_b, seasons=3):
    """Tier 1: Official NBA stats via nba_api package."""
    from nba_api.stats.endpoints import LeagueGameFinder
    from nba_api.stats.static import teams
    import time

    team_a_info = teams.find_team_by_abbreviation(team_a)
    team_b_info = teams.find_team_by_abbreviation(team_b)

    if not team_a_info or not team_b_info:
        raise ValueError(f"Team not found: {team_a} or {team_b}")

    team_a_id = team_a_info['id']
    team_b_id = team_b_info['id']

    # Rate limit courtesy: 1 second between requests
    time.sleep(1)

    finder = LeagueGameFinder(
        team_id_nullable=team_a_id,
        vs_team_id_nullable=team_b_id,
        season_type_nullable='Regular Season',
        timeout=15,
    )
    games_df = finder.get_data_frames()[0]

    if games_df.empty:
        raise ValueError(f"No games found for {team_a} vs {team_b}")

    # Take last N seasons worth of games (usually 2-4 per season)
    games_df = games_df.head(seasons * 4)  # Max ~12 games

    margins = []
    for _, row in games_df.iterrows():
        # PLUS_MINUS from team_a's perspective
        margins.append(float(row.get('PLUS_MINUS', 0)))

    if not margins:
        raise ValueError("No margin data extracted")

    return {
        "mean_margin": round(sum(margins) / len(margins), 1),
        "past_margins": margins,
        "games_found": len(margins),
        "source": "nba_api (stats.nba.com)",
    }


# ─── Tier 2: balldontlie.io REST API ─────────────────────────────────────

def _fetch_h2h_balldontlie(team_a, team_b, seasons=None):
    """Tier 2: balldontlie.io REST API."""
    import requests

    if seasons is None:
        seasons = ["2025", "2024", "2023"]

    api_key = os.environ.get("BALLDONTLIE_API_KEY", "")
    base_url = "https://api.balldontlie.io/v1"
    headers = {"Authorization": api_key} if api_key else {}

    team_a_id = BDL_TEAM_IDS.get(team_a)
    team_b_id = BDL_TEAM_IDS.get(team_b)

    if not team_a_id or not team_b_id:
        raise ValueError(f"Team ID not found for {team_a} or {team_b}")

    all_games = []
    for season in seasons:
        resp = requests.get(
            f"{base_url}/games",
            params={"seasons[]": season, "per_page": 100},
            headers=headers,
            timeout=10,
        )
        if resp.status_code == 429:
            raise ConnectionError("balldontlie rate limited (HTTP 429)")
        if resp.status_code != 200:
            raise ConnectionError(f"balldontlie HTTP {resp.status_code}")

        data = resp.json().get("data", [])
        # Filter for H2H matchups
        for game in data:
            ht = game.get("home_team", {}).get("id")
            vt = game.get("visitor_team", {}).get("id")
            if {ht, vt} == {team_a_id, team_b_id}:
                home_score = game.get("home_team_score", 0)
                away_score = game.get("visitor_team_score", 0)
                if home_score and away_score:
                    # margin from team_a perspective
                    if ht == team_a_id:
                        margin = home_score - away_score
                    else:
                        margin = away_score - home_score
                    all_games.append({
                        "margin": margin,
                        "date": game.get("date", ""),
                    })

    if not all_games:
        raise ValueError(f"No H2H games found on balldontlie for {team_a} vs {team_b}")

    margins = [g["margin"] for g in all_games]
    return {
        "mean_margin": round(sum(margins) / len(margins), 1),
        "past_margins": margins,
        "games_found": len(margins),
        "source": "balldontlie.io",
    }


# ─── Tier 3: ESPN Hidden API ─────────────────────────────────────────────

def _fetch_h2h_espn(team_a, team_b):
    """Tier 3: ESPN hidden API (unofficial, unstable)."""
    import requests

    espn_a = ESPN_TEAM_IDS.get(team_a)
    espn_b = ESPN_TEAM_IDS.get(team_b)

    if not espn_a or not espn_b:
        raise ValueError(f"ESPN team ID not found for {team_a} or {team_b}")

    url = f"https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{espn_a}/schedule"
    resp = requests.get(url, timeout=10)

    if resp.status_code != 200:
        raise ConnectionError(f"ESPN API returned {resp.status_code}")

    schedule = resp.json()
    events = schedule.get("events", [])

    margins = []
    for event in events:
        competitions = event.get("competitions", [{}])
        for comp in competitions:
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            team_ids = {int(c.get("id", 0)) for c in competitors}
            if espn_a in team_ids and espn_b in team_ids:
                scores = {}
                for c in competitors:
                    scores[int(c["id"])] = int(c.get("score", {}).get("value", 0) if isinstance(c.get("score"), dict) else c.get("score", 0))

                if scores.get(espn_a) and scores.get(espn_b):
                    margin = scores[espn_a] - scores[espn_b]
                    margins.append(margin)

    if not margins:
        raise ValueError(f"No H2H games found on ESPN for {team_a} vs {team_b}")

    return {
        "mean_margin": round(sum(margins) / len(margins), 1),
        "past_margins": margins,
        "games_found": len(margins),
        "source": "ESPN hidden API",
    }


# ─── Tier 4: Mock Data (last resort) ─────────────────────────────────────

def _generate_mock_h2h(team_a, team_b):
    """Tier 4: Generate mock H2H data (original fallback behavior)."""
    past_margins = [random.randint(-15, 15) for _ in range(5)]
    return {
        "mean_margin": round(sum(past_margins) / len(past_margins), 1),
        "past_margins": past_margins,
        "games_found": 5,
        "source": "⚠️ MOCK DATA (all APIs failed)",
        "is_mock": True,
    }


# ─── Unified Entry Point (Cascading Fallback Orchestrator) ───────────────

def fetch_h2h_historic_data(team_a, team_b, stat_type="points_margin"):
    """
    Multi-API Cascading Fallback for H2H data.
    Tries: nba_api → balldontlie → ESPN → mock data.
    Always returns a valid dict — never fails.
    """
    errors = []

    print(f"🔄 Fetching H2H Historic Data for {team_a} vs {team_b}...")

    # Tier 1: nba_api
    try:
        data = _fetch_h2h_nba_api(team_a, team_b)
        print(f"  ✅ H2H data from Tier 1: nba_api ({data['games_found']} games)")
        return data
    except Exception as e:
        errors.append(f"Tier 1 (nba_api): {e}")
        print(f"  ⚠️ Tier 1 failed: {e}")

    # Tier 2: balldontlie
    try:
        data = _fetch_h2h_balldontlie(team_a, team_b)
        print(f"  ✅ H2H data from Tier 2: balldontlie ({data['games_found']} games)")
        return data
    except Exception as e:
        errors.append(f"Tier 2 (balldontlie): {e}")
        print(f"  ⚠️ Tier 2 failed: {e}")

    # Tier 3: ESPN
    try:
        data = _fetch_h2h_espn(team_a, team_b)
        print(f"  ✅ H2H data from Tier 3: ESPN ({data['games_found']} games)")
        return data
    except Exception as e:
        errors.append(f"Tier 3 (ESPN): {e}")
        print(f"  ⚠️ Tier 3 failed: {e}")

    # Tier 4: Mock data (last resort)
    print(f"  💀 All API tiers failed. Using mock data.")
    for err in errors:
        print(f"     {err}")
    data = _generate_mock_h2h(team_a, team_b)
    data["_api_errors"] = errors
    return data


def calculate_h2h_probability_injection(team_a, team_b, current_line):
    """
    Compares the historical average to the current bookmaker line.
    Returns a probability adjustment weight and LLM context injection text.
    """
    h2h_data = fetch_h2h_historic_data(team_a, team_b)
    mean_margin = h2h_data["mean_margin"]
    source = h2h_data.get("source", "unknown")
    is_mock = h2h_data.get("is_mock", False)
    games_found = h2h_data.get("games_found", 0)

    discrepancy = mean_margin - current_line

    # Probability injection: 1.5% per point of discrepancy
    # But if using mock data, Factor 11 weight = 0
    prob_bump = discrepancy * 1.5 if not is_mock else 0

    margins_str = str(h2h_data.get("past_margins", []))

    injection_text = (
        f"⚔️ **H2H 歷史交手權重 (H2H Injection)**:\n"
        f" 📡 數據源: {source} ({games_found} games)\n"
        f" {team_a} 對 {team_b} 歷史場均淨勝: {mean_margin:+.1f} 分\n"
        f" 歷史淨勝分佈: {margins_str}\n"
        f" 莊家開盤 (Line): {team_a} {current_line:+.1f}\n"
        f" 現價偏差 (Discrepancy): {discrepancy:+.1f} 分\n"
    )

    if is_mock:
        injection_text += f" ⚠️ 警告: 使用 Mock Data — Factor 11 權重自動歸零\n"
    elif discrepancy > 3.0:
        injection_text += f" 📈 結論: {team_a} 歷史明顯剋制對手，建議勝率模型注入 +{abs(prob_bump):.1f}%。\n"
    elif discrepancy < -3.0:
        injection_text += f" 📉 結論: {team_a} 歷史明顯被對手剋制，建議勝率模型扣減 -{abs(prob_bump):.1f}%。\n"
    else:
        injection_text += f" ⚖️ 結論: 歷史交手與現盤相符，無須大幅微調勝率權重。\n"

    print("\n--- LLM Context Injection String ---")
    print(injection_text)
    return injection_text


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NBA H2H Historic Data Fetcher V2 (Multi-API Fallback)")
    parser.add_argument('--team_a', type=str, required=True, help="Home Team (e.g. BOS)")
    parser.add_argument('--team_b', type=str, required=True, help="Away Team (e.g. MIA)")
    parser.add_argument('--line', type=float, required=True, help="Current Bookmaker Line for Team A (e.g. 5.5)")
    args = parser.parse_args()

    calculate_h2h_probability_injection(args.team_a, args.team_b, args.line)
