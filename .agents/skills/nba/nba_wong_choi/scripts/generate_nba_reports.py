#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
generate_nba_reports.py — NBA Wong Choi 預填骨架報告生成器 V2

將 Sportsbet 即時盤口 JSON + nba_extractor.py 深度 JSON 合併計算，
自動生成符合新版緊湊格式嘅 pre-filled skeleton report。

Key changes in V2:
  - Sportsbet line format: "10+" (not "O 10.5")
  - Hit rate calc: >= (not >)
  - Auto-combo engine with 5 combinations
  - Pre-filled combo tables with per-leg logic slots

Usage:
  python generate_nba_reports.py \
    --sportsbet path/to/Sportsbet_Odds_CHI_WSH.json \
    --extractor path/to/nba_game_data_CHI_WSH.json \
    --output path/to/Game_CHI_WSH_Skeleton.md

Version: 2.0.0
"""
import sys, io, os, json, math, argparse
from datetime import datetime

L10_ORDER = "newest_first"
PLAYER_MARKET = "PLAYER_MILESTONE"
TEAM_MARKET = "TEAM_MARKET"

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


# ─── Season Phase Detection ──────────────────────────────────────────────

def detect_season_phase(date_str=None, metadata=None):
    """
    Detect NBA season phase from date string.
    Returns: EARLY_SEASON, MID_SEASON, LATE_REGULAR, PLAY_IN, PLAYOFFS
    
    V3.1: Config-driven — reads nba_season_config.json instead of hardcoded dates.
    """
    metadata = metadata or {}
    meta_text = " ".join(str(metadata.get(k, "")) for k in (
        "season_phase", "season_type", "game_type", "game_status", "competition_type",
        "name", "shortName", "series", "event_type"))
    meta_upper = meta_text.upper()
    if "PLAYOFF" in meta_upper or "POSTSEASON" in meta_upper:
        return "PLAYOFFS"
    if "PLAY-IN" in meta_upper or "PLAY IN" in meta_upper:
        return "PLAY_IN"
    if "PRESEASON" in meta_upper:
        return "EARLY_SEASON"
    if metadata.get("season_phase") in {"EARLY_SEASON", "MID_SEASON", "LATE_REGULAR", "PLAY_IN", "PLAYOFFS"}:
        return metadata["season_phase"]

    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    try:
        # Handle various date formats
        for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
            try:
                d = datetime.strptime(date_str[:19], fmt)
                break
            except ValueError:
                continue
        else:
            d = datetime.now()
    except Exception:
        d = datetime.now()
    
    # Config-driven season calendar
    config = _load_season_config()
    if config:
        try:
            def _parse(key):
                return datetime.strptime(config[key], "%Y-%m-%d")
            
            if d <= _parse("early_season_end"):
                return "EARLY_SEASON"
            if d >= _parse("playoffs_start"):
                return "PLAYOFFS"
            if _parse("play_in_start") <= d <= _parse("play_in_end"):
                return "PLAY_IN"
            if _parse("late_regular_start") <= d <= _parse("late_regular_end"):
                return "LATE_REGULAR"
            return "MID_SEASON"
        except (KeyError, ValueError):
            pass  # Fall through to hardcoded fallback
    
    # Hardcoded fallback (2025-26 season)
    month, day = d.month, d.day
    if d.year == 2025 and month == 10:
        return "EARLY_SEASON"
    if d.year == 2025 and month == 11 and day <= 15:
        return "EARLY_SEASON"
    if d.year == 2026 and month == 3 and day >= 25:
        return "LATE_REGULAR"
    if d.year == 2026 and month == 4 and day <= 13:
        return "LATE_REGULAR"
    if d.year == 2026 and month == 4 and 14 <= day <= 18:
        return "PLAY_IN"
    if d.year == 2026 and month == 4 and day >= 19:
        return "PLAYOFFS"
    if d.year == 2026 and month in (5, 6):
        return "PLAYOFFS"
    
    return "MID_SEASON"


def _load_season_config():
    """Load NBA season config from nba_season_config.json."""
    config_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resources", "nba_season_config.json"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba_season_config.json"),
    ]
    for p in config_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
    return None

# ─── Math Engine ─────────────────────────────────────────────────────────

def compute_stats(data):
    n = len(data)
    if n == 0:
        return 0.0, 0.0, 0.0, 0.0
    avg = sum(data) / n
    s = sorted(data)
    med = (s[n//2 - 1] + s[n//2]) / 2 if n % 2 == 0 else s[n//2]
    variance = sum((x - avg) ** 2 for x in data) / n
    sd = math.sqrt(variance)
    cov = sd / avg if avg != 0 else 0.0
    return round(avg, 2), round(med, 1), round(sd, 2), round(cov, 3)


def grade_cov(cov):
    if cov <= 0.15: return "🛡️極穩"
    elif cov <= 0.25: return "✅穩定"
    elif cov <= 0.35: return "➖中波"
    else: return "🎲神經刀"


def weighted_avg(data):
    n = len(data)
    if n == 0: return 0.0
    # L10 is normalized as newest -> oldest. Recent games must carry higher weight.
    weights = []
    for i in range(n):
        if i < 3:
            weights.append(1.5)
        elif i < 7:
            weights.append(1.0)
        else:
            weights.append(0.7)
    return round(sum(d * w for d, w in zip(data, weights)) / sum(weights), 2)


def trend_label(data):
    if len(data) < 5: return "— 數據不足"
    l3 = sum(data[:3]) / 3
    l10 = sum(data) / len(data)
    diff = (l3 - l10) / l10 * 100 if l10 != 0 else 0
    if diff > 5: return "📈上升"
    elif diff < -5: return "📉下降"
    else: return "—持平"


def hit_rate(data, line_val):
    """Hit rate using >= (Sportsbet 10+ = 10 or more, i.e. >= 10)."""
    if not data: return 0.0, "0/0", []
    hits = sum(1 for x in data if x >= line_val)
    pct = round(hits / len(data) * 100, 1)
    count = f"{hits}/{len(data)}"
    misses = []
    for i, x in enumerate(data):
        if x < line_val:
            misses.append({"game": i+1, "value": x, "deficit": round(line_val - x, 1)})
    return pct, count, misses


def implied_prob(odds):
    if odds <= 0: return 0.0
    return round(100 / float(odds), 2)


def edge_calc(estimated_prob, implied):
    """Probability edge = estimated probability - implied probability (percentage points).
    Renamed conceptually to 'prob_edge_pp' in output. Kept function name for backward compat."""
    return round(estimated_prob - implied, 2)


def ev_pct_calc(est_prob, odds):
    """True EV%: (p × odds − 1) × 100.
    Tells you the actual expected return per unit staked.
    Example: prob=70%, odds=1.60 → EV = 0.70 × 1.60 - 1 = +12%"""
    if not odds or float(odds) <= 0 or est_prob <= 0:
        return 0.0
    p = est_prob / 100
    return round((p * float(odds) - 1) * 100, 2)


def confidence_multiplier(cov):
    """CoV-based confidence discount for EV.
    High CoV = less confident in our probability estimate → penalize EV."""
    if not isinstance(cov, (int, float)):
        return 0.65
    if cov <= 0.15:
        return 1.00
    elif cov <= 0.25:
        return 0.85
    elif cov <= 0.35:
        return 0.65
    else:
        return 0.40


def edge_grade(edge):
    if edge >= 15: return "💎核心高價值"
    elif edge >= 5: return "✅有價值"
    elif edge >= 0: return "➖邊緣"
    else: return "❌負EV"


# ─── Adjusted Win Probability Engine (V3 — 10-Factor) ─────────────────────
# V3: All 10 factors computed by Python. Zero LLM judgment.
# Factors: trend, cov, buffer, pace, minutes_floor, home_away,
#          b2b_fatigue, opp_defense, usg_shift, matchup_pace

def _minutes_floor_adj(spread):
    """Factor 5: Blowout risk → minutes reduction discount.
    V5.3: Halved penalties — original values were too aggressive,
    causing over-deflation when stacked with playoff_guard."""
    if not spread: return 0
    try:
        s = abs(float(spread))
    except (ValueError, TypeError):
        return 0
    if s >= 15: return -3  # V5.3: was -5
    if s >= 12: return -2  # V5.3: was -3
    if s >= 8.5: return -1  # V5.3: was -2
    return 0

def _home_away_adj(is_home, home_ppg, road_ppg):
    """Factor 6: Home/Away performance split."""
    if is_home is None: return 0
    if not home_ppg or not road_ppg or home_ppg == 'N/A' or road_ppg == 'N/A':
        return 1 if is_home else 0  # baseline home advantage
    try:
        h, r = float(home_ppg), float(road_ppg)
    except (ValueError, TypeError):
        return 1 if is_home else 0
    if r == 0: return 0
    diff_pct = (h - r) / r * 100
    if is_home:
        if diff_pct >= 15: return 4
        if diff_pct >= 5: return 2
        return 1
    else:
        if diff_pct >= 15: return -3
        if diff_pct >= 5: return -1
        return 0

def _b2b_fatigue_adj(is_b2b, is_home):
    """Factor 7: Back-to-back fatigue discount (2-4% per research)."""
    if not is_b2b: return 0
    return -2 if is_home else -4

def _opp_defense_adj(def_rank):
    """Factor 8: Opponent defensive rating impact."""
    if not def_rank or not isinstance(def_rank, (int, float)): return 0
    if def_rank <= 5: return -4
    if def_rank <= 10: return -2
    if def_rank <= 20: return 0
    if def_rank <= 25: return 2
    return 4

def _usg_shift_adj(bonus_usg):
    """Factor 9: USG redistribution from injured teammates."""
    if not bonus_usg or not isinstance(bonus_usg, (int, float)): return 0
    if bonus_usg > 5: return 5
    if bonus_usg >= 3: return 3
    if bonus_usg > 0: return 2
    return 0

def _matchup_pace_adj(team_pace, opp_pace):
    """Factor 10: Combined matchup pace vs league average."""
    if not team_pace or not opp_pace: return 0
    try:
        tp, op = float(team_pace), float(opp_pace)
    except (ValueError, TypeError):
        return 0
    avg_pace = (tp + op) / 2
    delta = avg_pace - 100.0  # 100 = league average baseline
    if delta >= 2: return 3
    if delta >= 1: return 1
    if delta <= -2: return -3
    if delta <= -1: return -1
    return 0

def kelly_fraction(est_prob, odds):
    """Half-Kelly criterion for conservative bankroll management.
    Returns fraction of bankroll to wager (0 if negative EV).
    """
    if not odds or odds <= 1 or est_prob <= 0:
        return 0.0
    b = odds - 1  # net payout per unit wagered
    p = est_prob / 100
    q = 1 - p
    f = (b * p - q) / b
    return round(max(0, f * 0.5), 4)  # Half Kelly

def calc_adjusted_winprob(base_rate, hit_l5=0, cov=0, avg=0, line_val=0,
                          opponent_def_rank=None, opponent_pace=None,
                          is_b2b=False, is_home=None, spread=None,
                          usg_bonus=0, defender_impact=None, amc=0,
                          home_ppg=None, road_ppg=None, team_pace=None,
                          l10=None, min_avg=0, season_phase="MID_SEASON"):
    """
    10-Factor Adjusted Win Probability Engine V3.1.
    All factors computed by Python — zero LLM judgment.
    base_rate: L10 hit rate (0-100)
    V3.1 additions: SIP-N01 bench minutes risk, SIP-N04 trend decline protection
    Returns: (adjusted_prob, breakdown_dict)
    """
    breakdown = {}
    l10 = l10 or []

    # ── Factor 1: Trend (L5 vs L10) ──
    delta = hit_l5 - base_rate
    if delta >= 20:     breakdown["trend"] = 8
    elif delta >= 10:   breakdown["trend"] = 5
    elif delta >= -10:  breakdown["trend"] = 0
    elif delta >= -20:  breakdown["trend"] = -5
    else:               breakdown["trend"] = -8

    # ── Factor 2: CoV Volatility ──
    if isinstance(cov, (int, float)):
        if cov <= 0.15:     breakdown["cov"] = 6
        elif cov <= 0.25:   breakdown["cov"] = 3
        elif cov <= 0.35:   breakdown["cov"] = 0
        elif cov <= 0.45:   breakdown["cov"] = -3
        else:               breakdown["cov"] = -6
    else:
        breakdown["cov"] = 0

    # ── Factor 3: Buffer + AMC ──
    buffer_ratio = (avg - line_val) / avg if avg > 0 else 0
    amc_bonus_val = 1 if amc > 5 else 0
    if buffer_ratio >= 0.25:     buf_base = 6
    elif buffer_ratio >= 0.15:   buf_base = 4
    elif buffer_ratio >= 0.05:   buf_base = 2
    elif buffer_ratio >= -0.05:  buf_base = 0
    elif buffer_ratio >= -0.15:  buf_base = -3
    else:                        buf_base = -6
    breakdown["buffer"] = max(-7, min(7, buf_base + amc_bonus_val))
    breakdown["_buffer_ratio"] = round(buffer_ratio * 100, 1)
    breakdown["_amc"] = amc

    # ── Factor 4: Opponent Pace ──
    if opponent_pace and isinstance(opponent_pace, (int, float)):
        pace_delta = opponent_pace - 100.0
        if pace_delta >= 3:      breakdown["pace"] = 3
        elif pace_delta >= 1.5:  breakdown["pace"] = 2
        elif pace_delta >= -1.5: breakdown["pace"] = 0
        elif pace_delta >= -3:   breakdown["pace"] = -2
        else:                    breakdown["pace"] = -3
    else:
        breakdown["pace"] = 0

    # ── Factor 5: Minutes Floor (Blowout Risk) ──
    breakdown["minutes_floor"] = _minutes_floor_adj(spread)

    # ── Factor 6: Home/Away Split ──
    breakdown["home_away"] = _home_away_adj(is_home, home_ppg, road_ppg)

    # ── Factor 7: B2B Fatigue ──
    breakdown["b2b_fatigue"] = _b2b_fatigue_adj(is_b2b, is_home)

    # ── Factor 8: Opponent Defensive Rating ──
    breakdown["opp_defense"] = _opp_defense_adj(opponent_def_rank)

    # ── Factor 9: USG Redistribution ──
    breakdown["usg_shift"] = _usg_shift_adj(usg_bonus)

    # ── Factor 10: Matchup Pace ──
    breakdown["matchup_pace"] = _matchup_pace_adj(team_pace, opponent_pace)

    # ── SIP-N04: Trend Decline Protection ──
    # If L1 (most recent game) is below the line AND trend is declining,
    # apply additional penalty to prevent false confidence from stale L10 data.
    # V5.3: Halved penalties — original -10/-5 caused massive over-deflation in playoffs.
    sip_n04_adj = 0
    if l10 and len(l10) >= 3 and line_val > 0:
        l1_val = l10[0]  # newest game (L10 is newest_first)
        l3_avg_val = sum(l10[:3]) / 3
        trend_declining = ("下降" in breakdown.get("_trend_label", "")) or (delta < -5)
        if l1_val < line_val and trend_declining:
            sip_n04_adj = -5   # V5.3: was -10
        elif l1_val < line_val:
            sip_n04_adj = -3   # V5.3: was -5
        elif l3_avg_val < line_val:
            sip_n04_adj = -3   # V5.3: was -5
    breakdown["sip_n04_trend_protect"] = sip_n04_adj

    # ── SIP-N01: Bench Minutes Risk ──
    # Playoffs: bench players with low avg minutes get penalized
    # V5.3: Halved penalties — rotation players (20-25 min) are still viable SGM targets.
    sip_n01_adj = 0
    if min_avg > 0 and min_avg < 20:
        sip_n01_adj = -5   # V5.3: was -10
    elif min_avg > 0 and min_avg < 25:
        sip_n01_adj = -3   # V5.3: was -5
    breakdown["sip_n01_bench_risk"] = sip_n01_adj

    # ── Playoff/Play-In Guard ──
    # V5.3: Reduced from -6/-3/-3/-3 (max -12) to -3/-2/-2/-2 (max -7).
    # Original penalties caused 15-20% cumulative over-deflation that wiped out
    # all positive-EV edges, leaving zero viable SGM candidates in tight games.
    playoff_adj = 0
    if season_phase in {"PLAYOFFS", "PLAY_IN"}:
        if min_avg and min_avg < 28:
            playoff_adj -= 3  # V5.3: was -6
        elif min_avg and min_avg < 32:
            playoff_adj -= 2  # V5.3: was -3
        if hit_l5 < base_rate:
            playoff_adj -= 2  # V5.3: was -3
        if isinstance(cov, (int, float)) and cov > 0.35:
            playoff_adj -= 2  # V5.3: was -3
    breakdown["playoff_guard"] = playoff_adj

    # ── Sum all factors (10 original + SIP guards) ──
    all_keys = ["trend", "cov", "buffer", "pace", "minutes_floor",
                "home_away", "b2b_fatigue", "opp_defense", "usg_shift", "matchup_pace",
                "sip_n04_trend_protect", "sip_n01_bench_risk", "playoff_guard"]
    total_adj = sum(breakdown[k] for k in all_keys)

    # V5.3: Penalty floor — prevent cumulative over-deflation.
    # Max total penalty capped at -20% to preserve meaningful edge differentiation.
    # Without this, stacked playoff penalties (-30 to -43%) destroy all positive EV.
    if total_adj < -20:
        total_adj = -20
        breakdown["_penalty_capped"] = True

    adjusted = max(5.0, min(98.0, base_rate + total_adj))
    breakdown["_python_adj"] = total_adj
    breakdown["_preliminary"] = round(adjusted, 1)
    breakdown["_total_adj"] = total_adj
    breakdown["_adjusted"] = round(adjusted, 1)

    return round(adjusted, 1), breakdown



# NOTE: generate_core_logic_narrative() removed in V7.
# LLM now writes the 核心邏輯 narrative directly, incorporating its own
# matchup/context/usg/defender judgments alongside the Python-computed factors.


def format_adjustment_line(base_rate, breakdown):
    """Format the 📐 adjustment detail line (10-Factor V3)."""
    parts = [f"基礎 {base_rate}%"]
    factor_names = {
        "trend": "走勢", "cov": "波動", "buffer": "安全墊", "pace": "節奏",
        "minutes_floor": "分鐘", "home_away": "主客", "b2b_fatigue": "B2B",
        "opp_defense": "防守", "usg_shift": "USG", "matchup_pace": "配速",
        "playoff_guard": "季後賽"
    }
    for key in ["trend", "cov", "buffer", "pace", "minutes_floor",
                "home_away", "b2b_fatigue", "opp_defense", "usg_shift", "matchup_pace",
                "playoff_guard"]:
        val = breakdown.get(key, 0)
        if val == 0:
            continue  # skip zero-impact factors for readability
        name = factor_names[key]
        if val >= 0:
            parts.append(f"{name} +{val}%")
        else:
            parts.append(f"{name} {val}%")
    adjusted = breakdown.get("_adjusted", base_rate)
    return " → ".join([parts[0]]) + " | " + " | ".join(parts[1:]) + f" | = {adjusted}%"

def find_player_in_extractor(ext_players, name, team_abbr):
    """Exact full name match only. No surname fallback to prevent Jr./Sr. collisions."""
    if team_abbr in ext_players:
        for p in ext_players[team_abbr]:
            if p.get("name", "").lower() == name.lower():
                return p
    return None


def build_player_card(player_name, team_abbr, sportsbet_data, ext_player, category,
                      opponent_def_rank=None, opponent_pace=None,
                      is_b2b=False, is_home=None, spread=None,
                      usg_bonus=0, defender_impact=None, top_defender_name="",
                      opponent_abbr="", season_phase="MID_SEASON"):
    card = {
        "name": player_name,
        "team": team_abbr,
        "category": category,
        "l10_order": L10_ORDER,
        "jersey": sportsbet_data.get("jersey", "?"),
        "last5_sportsbet": sportsbet_data.get("last5", []),
        "lines": sportsbet_data.get("lines", {}),
    }

    cat_map = {"points": "PTS", "threes_made": "FG3M", "rebounds": "REB", "assists": "AST"}
    stat_key = cat_map.get(category, "PTS")

    if ext_player:
        gl = ext_player.get("gamelog", {})
        adv = ext_player.get("advanced") or {}
        splits = ext_player.get("splits") or {}
        fatigue = ext_player.get("fatigue") or {}

        l10 = gl.get(stat_key, [])
        card["l10"] = l10
        card["position"] = ext_player.get("position", "?")

        avg, med, sd, cov = compute_stats(l10)
        card["avg"] = avg
        card["med"] = med
        card["sd"] = sd
        card["cov"] = cov
        card["cov_grade"] = grade_cov(cov)
        card["weighted_avg"] = weighted_avg(l10)
        card["trend"] = trend_label(l10)

        l5 = l10[:5] if len(l10) >= 5 else l10
        l3 = l10[:3] if len(l10) >= 3 else l10
        card["l5_avg"] = round(sum(l5) / len(l5), 2) if l5 else 0
        card["l3_avg"] = round(sum(l3) / len(l3), 2) if l3 else 0

        card["usg_pct"] = adv.get("USG_PCT", "N/A")
        card["ts_pct"] = adv.get("TS_PCT", "N/A")
        card["home_ppg"] = splits.get("Home_PPG", "N/A")
        card["road_ppg"] = splits.get("Road_PPG", "N/A")

        mins = gl.get("MIN", [])
        card["min_avg"] = round(sum(mins) / len(mins), 1) if mins else 0
        card["fatigue"] = fatigue
    else:
        # Use Sportsbet L5 as fallback
        l5 = sportsbet_data.get("last5", [])
        card["l10"] = l5  # Only L5 available
        avg, med, sd, cov = compute_stats(l5)
        card["avg"] = avg
        card["med"] = med
        card["sd"] = sd
        card["cov"] = cov
        card["cov_grade"] = grade_cov(cov)
        card["weighted_avg"] = weighted_avg(l5)
        card["trend"] = trend_label(l5)
        card["l5_avg"] = avg
        card["l3_avg"] = round(sum(l5[:3]) / len(l5[:3]), 2) if len(l5) >= 3 else avg
        card["usg_pct"] = "N/A"
        card["ts_pct"] = "N/A"
        card["home_ppg"] = "N/A"
        card["road_ppg"] = "N/A"
        card["min_avg"] = 0
        card["fatigue"] = {}
        card["position"] = "?"

    # Hit rates for each Sportsbet line
    card["line_analysis"] = {}
    data_for_hr = card["l10"]
    for line_val_str, odds_str in card["lines"].items():
        line_val = float(line_val_str)  # Sportsbet "10" = 10+, so threshold is >= 10
        
        # NOTE: Sportsbet Player Milestone lines (the ones users combine) are ALWAYS integers.
        # Decimal lines (like 12.5) are standard O/U lines and shouldn't pollute the SGM options.
        if not line_val.is_integer():
            continue
            
        hr_l10, hr_l10_count, misses = hit_rate(data_for_hr, line_val)
        l5_data = data_for_hr[:5] if len(data_for_hr) >= 5 else data_for_hr
        l3_data = data_for_hr[:3] if len(data_for_hr) >= 3 else data_for_hr
        hr_l5, hr_l5_count, _ = hit_rate(l5_data, line_val)
        hr_l3, hr_l3_count, _ = hit_rate(l3_data, line_val)
        imp = implied_prob(float(odds_str))
        # V3: 10-factor adjusted win probability (all Python-computed)
        est_prob, adj_breakdown = calc_adjusted_winprob(
            base_rate=hr_l10, hit_l5=hr_l5, cov=card["cov"],
            avg=card["avg"], line_val=line_val,
            opponent_def_rank=opponent_def_rank, opponent_pace=opponent_pace,
            is_b2b=is_b2b, is_home=is_home, spread=spread,
            usg_bonus=usg_bonus, defender_impact=defender_impact, amc=0,
            home_ppg=card.get("home_ppg"), road_ppg=card.get("road_ppg"),
            team_pace=None, l10=data_for_hr, min_avg=card.get("min_avg", 0),
            season_phase=season_phase)  # team_pace set at main() level
        ev = edge_calc(est_prob, imp)
        grade = edge_grade(ev)

        # V8: True EV% and confidence-adjusted EV
        true_ev = ev_pct_calc(est_prob, float(odds_str))
        conf_mult = confidence_multiplier(card["cov"])
        conf_adj_ev = round(true_ev * conf_mult, 2)

        # V7: Narrative now written by LLM (not Python)
        narrative = ""
        adj_line = format_adjustment_line(hr_l10, adj_breakdown)

        card["line_analysis"][line_val_str] = {
            "line": line_val,
            "line_display": f"{line_val_str}+",  # "10+" format
            "odds": odds_str,
            "implied_prob": imp,
            "estimated_prob": est_prob,
            "base_rate": hr_l10,
            "edge": ev,  # backward compat alias
            "prob_edge_pp": ev,  # V8: probability edge in percentage points
            "ev_pct": true_ev,  # V8: true EV%
            "confidence_adjusted_ev_pct": conf_adj_ev,  # V8: confidence-discounted EV
            "edge_grade": edge_grade(ev),
            "hit_l10": hr_l10, "hit_l10_count": hr_l10_count,
            "hit_l5": hr_l5, "hit_l5_count": hr_l5_count,
            "hit_l3": hr_l3, "hit_l3_count": hr_l3_count,
            "misses": misses,
            "verdict": "✅" if hr_l5 >= 70 else ("⚠️" if hr_l5 >= 50 else "❌"),
            "adj_breakdown": adj_breakdown,
            "adj_narrative": narrative,
            "adj_line": adj_line,
        }

    return card


# ─── Auto-Combo Engine ──────────────────────────────────────────────────

def build_leg_candidates(all_cards, team_odds=None, meta=None, injuries=None):
    """Build a flat list of all possible legs from player cards + team odds.
    V3.1: SIP-N01 bench minutes risk flag, SIP-N05 high CoV 3PM filter."""
    candidates = []
    cat_label = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}
    injuries = injuries or {}
    meta = meta or {}
    season_phase = meta.get("season_phase", "MID_SEASON")

    for card in all_cards:
        team_abbr = card["team"]
        player_name = card["name"]
        status = injuries.get(team_abbr, {}).get(player_name, "")
        
        # ⚠️ Skip players who are strictly OUT or injured so they do not pollute safely generated combos
        if status.lower() == "out":
            continue
        
        # Flag Day-To-Day players (excluded from 穩膽 only, allowed in other combos)
        is_day_to_day = status.lower() in ("day-to-day", "dtd")
            
        cl = cat_label.get(card["category"], card["category"])

        # SIP-N01: Flag bench minutes risk
        min_avg = card.get("min_avg", 0)
        bench_minutes_risk = (min_avg > 0 and min_avg < 25)

        for line_key, la in card.get("line_analysis", {}).items():
            odds = float(la["odds"])
            if odds < 1.01:  # Skip near-certainties
                continue

            # SIP-N05: Block high CoV 3PM legs from ALL combo pools
            # 3PM is inherently high variance; CoV > 0.5 makes it unpredictable
            if cl == "3PM" and card["cov"] > 0.5:
                continue

            # SIP-N04: Compute L3 average for trend protection
            l10_data = card.get("l10", [])
            l3_avg = round(sum(l10_data[:3]) / 3, 2) if len(l10_data) >= 3 else card["avg"]
            l1_val = l10_data[0] if l10_data else card["avg"]

            candidates.append({
                "market_type": PLAYER_MARKET,
                "player": card["name"],
                "team": card["team"],
                "category": cl,
                "line_display": la["line_display"],
                "line_val": la["line"],
                "odds": odds,
                "hit_l10": la["hit_l10"],
                "hit_l10_count": la["hit_l10_count"],
                "hit_l5": la["hit_l5"],
                "hit_l5_count": la["hit_l5_count"],
                "hit_l3": la["hit_l3"],
                "hit_l3_count": la["hit_l3_count"],
                "implied_prob": la["implied_prob"],
                "estimated_prob": la["estimated_prob"],
                "base_rate": la.get("base_rate", la["hit_l10"]),
                "edge": la["edge"],
                "prob_edge_pp": la.get("prob_edge_pp", la["edge"]),
                "ev_pct": la.get("ev_pct", 0.0),
                "confidence_adjusted_ev_pct": la.get("confidence_adjusted_ev_pct", 0.0),
                "edge_grade": la["edge_grade"],
                "cov": card["cov"],
                "cov_grade": card["cov_grade"],
                "avg": card["avg"],
                "l10": card["l10"],
                "sd": card["sd"],
                "med": card["med"],
                "weighted_avg": card["weighted_avg"],
                "trend": card["trend"],
                "adj_narrative": la.get("adj_narrative", ""),
                "adj_line": la.get("adj_line", ""),
                "correlation_flags": [],
                "selection_reject_reasons": [],
                "desc": f"{card['name']} ({card['team']}) {cl} {la['line_display']}",
                # SIP fields
                "bench_minutes_risk": bench_minutes_risk,
                "min_avg": min_avg,
                "l3_avg": l3_avg,
                "l1_val": l1_val,
                "day_to_day": is_day_to_day,
                "season_phase": season_phase,
            })

    # ── Team-level legs (ML / Spread / O/U) ──
    if team_odds and meta:
        away_abbr = meta.get("away", {}).get("abbr", "?")
        home_abbr = meta.get("home", {}).get("abbr", "?")
        team_legs = _build_team_legs(team_odds, away_abbr, home_abbr)
        candidates.extend(team_legs)

    return candidates


def _build_team_legs(odds, away_abbr, home_abbr):
    """Build team-level leg candidates from extractor odds data."""
    legs = []
    
    # Helper: create a team leg candidate (no L10 hit data — Analyst evaluates)
    def make_team_leg(desc, odds_val, est_prob=None):
        if not odds_val or odds_val == "?":
            return None
        try:
            odds_f = abs(float(odds_val))
            # Convert American odds to decimal if needed
            if odds_f >= 100:
                dec_odds = (odds_f / 100) + 1 if float(odds_val) > 0 else (100 / odds_f) + 1
            else:
                dec_odds = float(odds_val)
            if dec_odds < 1.01:
                return None
        except (ValueError, ZeroDivisionError):
            return None
        
        imp = implied_prob(dec_odds)
        ep = est_prob if est_prob else imp  # Default: no edge info for team legs
        ev = edge_calc(ep, imp)
        
        return {
            "market_type": TEAM_MARKET,
            "player": f"TEAM_{away_abbr}_{home_abbr}",
            "team": "TEAM",
            "category": "TEAM",
            "line_display": desc,
            "line_val": 0,
            "odds": dec_odds,
            "hit_l10": ep, "hit_l10_count": "—",
            "hit_l5": ep, "hit_l5_count": "—",
            "hit_l3": ep, "hit_l3_count": "—",
            "implied_prob": imp,
            "estimated_prob": ep,
            "edge": ev,
            "edge_grade": edge_grade(ev),
            "cov": 0, "cov_grade": "—",
            "avg": 0, "l10": [], "sd": 0, "med": 0,
            "weighted_avg": 0, "trend": "—",
            "correlation_flags": ["TEAM_MARKET_EXCLUDED_FROM_PLAYER_SGM_POOL"],
            "selection_reject_reasons": ["Team market is reported separately and not mixed into player milestone SGM auto-selection."],
            "desc": desc,
        }
    
    # Moneyline
    for abbr, key in [(away_abbr, "ml_away"), (home_abbr, "ml_home")]:
        ml = odds.get(key)
        leg = make_team_leg(f"{abbr} 獨贏 (ML)", ml)
        if leg:
            legs.append(leg)
    
    # Spread
    spread = odds.get("spread_away", odds.get("spread"))
    if spread and spread != "?":
        leg = make_team_leg(f"{away_abbr} {spread} (Spread)", "1.91")  # Standard -110 juice
        if leg:
            legs.append(leg)
        leg = make_team_leg(f"{home_abbr} +{str(spread).replace('-','').replace('+','')} (Spread)", "1.91")
        if leg:
            legs.append(leg)
    
    # Total O/U
    total = odds.get("total")
    if total and total != "?":
        leg = make_team_leg(f"Total O{total}", "1.91")
        if leg:
            legs.append(leg)
    
    return legs


def _is_player_milestone(leg):
    return leg.get("market_type") == PLAYER_MARKET


def _combo_odds(legs):
    odds = 1.0
    for leg in legs:
        odds *= leg["odds"]
    return odds


def _has_unique_players(legs):
    players = [leg.get("player") for leg in legs]
    return len(players) == len(set(players))


def _violates_same_team_scoring_cap(legs):
    team_pts = {}
    for leg in legs:
        if leg.get("category") == "PTS":
            team = leg.get("team")
            team_pts[team] = team_pts.get(team, 0) + 1
    return any(count > 2 for count in team_pts.values())


def _has_team_player_script_conflict(legs):
    return any(leg.get("market_type") == TEAM_MARKET for leg in legs) and any(
        leg.get("market_type") == PLAYER_MARKET for leg in legs)


def _combo_is_allowed(legs):
    return (
        _has_unique_players(legs)
        and not _violates_same_team_scoring_cap(legs)
        and not _has_team_player_script_conflict(legs)
    )


# ─── Correlation Penalty Engine (V8) ───────────────────────────────────
# NBA props are heavily correlated within same game/team/player.
# Naive joint probability (p1 × p2 × p3) overestimates combo hit rate.
# This penalty adjusts for known correlation patterns.

def _count_max_same_team(combo):
    """Count the max number of legs from any single team."""
    team_counts = {}
    for leg in combo:
        t = leg.get("team", "")
        if t and t != "TEAM":
            team_counts[t] = team_counts.get(t, 0) + 1
    return max(team_counts.values()) if team_counts else 0


def _count_same_player_legs(combo):
    """Count max legs from same player (should be 0 with unique-player rule)."""
    player_counts = {}
    for leg in combo:
        p = leg.get("player", "")
        player_counts[p] = player_counts.get(p, 0) + 1
    return max(player_counts.values()) if player_counts else 0


def _has_points_and_assists_synergy(combo):
    """Detect PTS + AST from same team (positive correlation: playmaker assists → teammate scores)."""
    team_cats = {}
    for leg in combo:
        t = leg.get("team", "")
        c = leg.get("category", "")
        if t not in team_cats:
            team_cats[t] = set()
        team_cats[t].add(c)
    return any("PTS" in cats and "AST" in cats for cats in team_cats.values())


def _has_multiple_overs_same_game(combo):
    """Detect 3+ over legs from same matchup (shared blowout/pace risk)."""
    team_count = {}
    for leg in combo:
        t = leg.get("team", "")
        if t and t != "TEAM":
            team_count[t] = team_count.get(t, 0) + 1
    return any(c >= 3 for c in team_count.values())


def _has_blowout_risk(combo):
    """Check if any leg has known blowout risk (spread >= 12)."""
    for leg in combo:
        adj = leg.get("adj_breakdown", {}) if isinstance(leg.get("adj_breakdown"), dict) else {}
        if adj.get("minutes_floor", 0) <= -2:
            return True
    return False


def correlation_penalty(combo):
    """Compute correlation penalty for an SGM combo.
    Returns a float between 0 and ~0.30 representing the probability discount.
    Higher = more correlated = more optimistic the naive joint prob is."""
    penalty = 0.0

    same_player_count = _count_same_player_legs(combo)
    same_team_max = _count_max_same_team(combo)

    # Same player multi-leg: very high correlation
    if same_player_count >= 2:
        penalty += 0.08

    # Same team 3+: ball usage ceiling
    if same_team_max >= 3:
        penalty += 0.06
    elif same_team_max >= 2:
        penalty += 0.02

    # PTS + AST from same team: positive correlation (small bonus)
    if _has_points_and_assists_synergy(combo):
        penalty -= 0.03

    # Multiple overs same game: shared pace/blowout risk
    if _has_multiple_overs_same_game(combo):
        penalty += 0.04

    # Blowout risk affects multiple legs
    if _has_blowout_risk(combo):
        penalty += 0.05

    return max(0.0, min(0.30, penalty))  # Cap at 30%


def compute_combo_ev(combo):
    """Compute combo-level EV with correlation adjustment.
    Returns dict with joint probability, correlation penalty, combo EV, and risk tier."""
    if not combo:
        return {}

    naive_joint_prob = 1.0
    combo_odds_val = 1.0
    for leg in combo:
        naive_joint_prob *= leg.get("estimated_prob", leg.get("hit_l10", 50)) / 100
        combo_odds_val *= leg["odds"]

    corr_penalty = correlation_penalty(combo)
    adjusted_joint_prob = naive_joint_prob * (1 - corr_penalty)
    combo_ev = (adjusted_joint_prob * combo_odds_val - 1) * 100

    # Confidence score: average leg confidence-adjusted EV
    avg_conf_ev = 0.0
    conf_evs = [leg.get("confidence_adjusted_ev_pct", 0) for leg in combo]
    if conf_evs:
        avg_conf_ev = sum(conf_evs) / len(conf_evs)

    # Risk tier classification
    if combo_ev >= 10 and corr_penalty < 0.10:
        risk_tier = "BANKER"
    elif combo_ev >= 5:
        risk_tier = "VALUE"
    elif combo_ev >= 0:
        risk_tier = "MARGINAL"
    else:
        risk_tier = "NEGATIVE"

    return {
        "naive_joint_prob": round(naive_joint_prob, 4),
        "correlation_penalty": round(corr_penalty, 3),
        "adjusted_joint_prob": round(adjusted_joint_prob, 4),
        "combo_decimal_odds": round(combo_odds_val, 2),
        "combo_ev_pct": round(combo_ev, 1),
        "avg_confidence_ev": round(avg_conf_ev, 1),
        "combo_risk_tier": risk_tier,
    }


def _mc_edge(leg):
    mc_lookup = leg.get("_mc_lookup", {})
    mc_key = f"{leg.get('player','')}|{leg.get('team','')}|{leg.get('category','')}|{leg.get('line_display','')}"
    mc_result = mc_lookup.get(mc_key, {})
    return mc_result.get("mc_edge")


def _value_bomb_confirmed(leg):
    mc_edge = _mc_edge(leg)
    if isinstance(mc_edge, (int, float)) and mc_edge >= 5:
        return True
    hit_l5 = leg.get("hit_l5", 0)
    hit_l10 = leg.get("hit_l10", 0)
    return hit_l5 >= max(55, hit_l10 - 10)


def _is_playoff_leg(leg):
    return leg.get("season_phase") in {"PLAYOFFS", "PLAY_IN"}


def _passes_playoff_gate(leg, tier):
    """Playoff mode keeps low-minute and stale-form props out of auto-combos.
    
    V5.1 Fixes:
    - min_avg threshold relaxed from 28 to 18 (many rotation players play 20-27 min)
    - min_avg = 0 (unknown) is treated as "pass" not "block"
    - l3_avg < line_val relaxed: only block if l3_avg < line_val * 0.8 (20% buffer)
    - Tier thresholds relaxed to account for 10-Factor adjustment deflation
    """
    if not _is_playoff_leg(leg):
        return True

    min_avg = leg.get("min_avg", 0)
    est_prob = leg.get("estimated_prob", leg.get("hit_l10", 0))
    hit_l5 = leg.get("hit_l5", 0)
    hit_l10 = leg.get("hit_l10", 0)
    line_val = leg.get("line_val", 0)
    l3_avg = leg.get("l3_avg", leg.get("avg", 0))
    mc_edge = _mc_edge(leg)

    # V5.1: Only block if min_avg is KNOWN and very low (<18)
    # min_avg=0 means unknown (extractor didn't provide) → don't penalize
    if min_avg > 0 and min_avg < 18:
        return False
    # V5.1: Relaxed l3_avg check — only block if L3 is severely below line (>20% gap)
    if line_val and l3_avg > 0 and l3_avg < line_val * 0.8:
        return False
    if leg.get("day_to_day", False):
        return False
    if isinstance(mc_edge, (int, float)) and mc_edge < -20:
        return False

    # V5.1: Use max(est_prob, hit_l10) to avoid 10-Factor over-deflation
    effective_prob = max(est_prob, hit_l10)

    if tier == "banker":
        return effective_prob >= 60 and hit_l5 >= 60
    if tier == "value":
        return effective_prob >= 50 and hit_l5 >= 50
    if tier == "high":
        if leg.get("category") == "3PM":
            return effective_prob >= 50 and hit_l5 >= 50
        return effective_prob >= 45 and hit_l5 >= 40
    if tier == "bomb":
        if isinstance(mc_edge, (int, float)):
            return mc_edge >= 3
        return effective_prob >= 50 and hit_l5 >= 50
    return True


def select_combo_1(candidates):
    """🛡️ 穩膽 V5: 2-3 ultra-safe legs targeting 2.0-3.2x.
    - L10 ≥ 80% AND L5 ≥ 80% (true recent consistency)
    - avg must exceed line by ≥ 15% (buffer safety)
    - Playoff gate: starter minutes + recent form required
    - SIP-N01: bench risk banned
    - SIP-N04: L3 < Line banned
    - 神經刀 banned"""

    def _has_buffer(c):
        """Check if player's avg exceeds line by at least 15%."""
        line_val = c.get("line_val", 0)
        avg = c.get("avg", 0)
        if line_val <= 0 or avg <= 0:
            return True  # Can't verify, allow through
        return (avg - line_val) / line_val >= 0.15

    pool = [c for c in candidates
            if _is_player_milestone(c)
            and c["hit_l10"] >= 80
            and c.get("hit_l5", 0) >= 80
            and c["edge"] >= 0  # V5.3: FW-11 blocks negative EV legs — must be >= 0
            and c["odds"] >= 1.20  # V5.2: Remove 'almost free' legs — each leg should carry meaningful odds
            and c.get("cov", 0) <= 0.65
            and not c.get("bench_minutes_risk", False)
            and not c.get("day_to_day", False)
            and c.get("l3_avg", c["avg"]) >= c.get("line_val", 0)
            and _has_buffer(c)
            and _passes_playoff_gate(c, "banker")]
    # F5: Prioritize L10 100% → 90% → 80% legs first, then by edge
    pool.sort(key=lambda x: (-x["hit_l10"], -x["hit_l5"], -x["edge"], x["odds"]))

    def score_fn(combo, odds, avg_hit, total_edge):
        # F5: Bonus for near-perfect hit rate legs
        perfect_bonus = sum(10 for leg in combo if leg["hit_l10"] >= 100)
        near_perfect_bonus = sum(5 for leg in combo if 90 <= leg["hit_l10"] < 100)
        return avg_hit * 0.6 + total_edge * 0.1 + len(combo) * 2 + perfect_bonus + near_perfect_bonus

    result = _greedy_build(pool,
                           target_min=2.0, target_max=3.5,  # V5.3: FW-11 floor is 2.0x
                           min_legs=2, max_legs=4,  # V5.3: Allow 4 legs to reach 2.0x target
                           score_fn=score_fn,
                           max_same_team_pts=2, max_same_team=3)

    # Fallback: relax to L10 ≥ 70% if strict pool is too small
    if not result:
        pool_relaxed = [c for c in candidates
                        if _is_player_milestone(c)
                        and c["hit_l10"] >= 70
                        and c.get("hit_l5", 0) >= 70
                        and c["edge"] >= 0  # V5.3: FW-11 blocks negative EV legs
                        and c["odds"] >= 1.15  # V5.2: Slightly relaxed from 1.20 for fallback
                        and c.get("cov", 0) <= 0.75
                        and not c.get("bench_minutes_risk", False)
                        and not c.get("day_to_day", False)
                        and c.get("l3_avg", c["avg"]) >= c.get("line_val", 0) * 0.85
                        and _passes_playoff_gate(c, "banker")]
        pool_relaxed.sort(key=lambda x: (-x["hit_l10"], -x["edge"], x["odds"]))
        result = _greedy_build(pool_relaxed,
                               target_min=2.0, target_max=4.0,  # V5.3: FW-11 floor is 2.0x
                               min_legs=2, max_legs=4,  # V5.3: Allow 4 legs
                               score_fn=score_fn,
                               max_same_team_pts=2, max_same_team=3)

    return result


# ─── Capped Greedy Builder (V5) ──────────────────────────────────────────
# Build toward the target odds range, but keep tier-specific max legs tight.

def _greedy_build(pool, target_min, target_max, min_legs, max_legs,
                  score_fn=None, max_same_team_pts=2, max_same_team=4):
    """Greedy capped SGM builder V5.
    
    Improvements over V4:
    - Validates combos via _combo_is_allowed() (team/player conflict guard)
    - Swap-out retry: if adding a leg overshoots target_max, tries swapping
      out the highest-odds existing leg to stay in range
    - Category dedup: prevents same-player multi-category stacking
    
    Returns the best combo found across multiple starting seeds.
    """
    if not pool:
        return []

    def _team_pts_count(combo, team):
        return sum(1 for leg in combo if leg.get("category") == "PTS" and leg.get("team") == team)

    def _team_count(combo, team):
        return sum(1 for leg in combo if leg.get("team") == team)

    def _try_build_from(seed_idx):
        combo = [pool[seed_idx]]
        used_players = {pool[seed_idx]["player"]}

        for candidate in pool:
            if len(combo) >= max_legs:
                break
            if candidate["player"] in used_players:
                continue
            # Same-team PTS cap
            if candidate.get("category") == "PTS" and _team_pts_count(combo, candidate["team"]) >= max_same_team_pts:
                continue
            # Same-team total cap (diversification)
            if _team_count(combo, candidate["team"]) >= max_same_team:
                continue

            test_combo = combo + [candidate]
            test_odds = _combo_odds(test_combo)

            # Validate structural rules (team/player conflicts)
            if not _combo_is_allowed(test_combo):
                continue

            # If adding this leg overshoots the max, try swap-out
            if test_odds > target_max and len(test_combo) >= min_legs:
                # Try removing the highest-odds leg (excluding seed) and re-check
                if len(combo) >= 2:
                    swap_candidates = sorted(range(1, len(combo)),
                                             key=lambda i: -combo[i]["odds"])
                    for swap_idx in swap_candidates[:3]:  # Try top 3 swaps
                        swapped = [l for i, l in enumerate(combo) if i != swap_idx] + [candidate]
                        if _combo_is_allowed(swapped) and _has_unique_players(swapped):
                            swapped_odds = _combo_odds(swapped)
                            if target_min <= swapped_odds <= target_max:
                                combo = swapped
                                used_players = {l["player"] for l in combo}
                                break
                continue

            combo.append(candidate)
            used_players.add(candidate["player"])

            # Smart stop: aim for the midpoint of target range, not just minimum
            # This ensures we build towards optimal odds, not just barely qualifying
            current_odds = _combo_odds(combo)
            sweet_spot = (target_min + target_max) / 2
            if current_odds >= sweet_spot and len(combo) >= min_legs:
                break  # At or past sweet spot — stop
            if current_odds >= target_min and len(combo) >= min_legs + 1:
                break  # Past minimum with extra leg cushion — stop

        final_odds = _combo_odds(combo)
        if len(combo) >= min_legs and target_min <= final_odds <= target_max:
            return combo
        # If we overshot slightly, still accept if within 20% tolerance
        if len(combo) >= min_legs and final_odds >= target_min and final_odds <= target_max * 1.2:
            return combo
        return None

    # Try multiple starting seeds and pick the best result
    best_combo = None
    best_score = -999

    for seed_idx in range(min(len(pool), 20)):  # Increased from 15 to 20 seeds
        result = _try_build_from(seed_idx)
        if result:
            odds = _combo_odds(result)
            if odds > target_max * 1.2:  # Hard ceiling
                continue
            avg_hit = sum(leg["hit_l10"] for leg in result) / len(result)
            avg_hit_l5 = sum(leg.get("hit_l5", leg["hit_l10"]) for leg in result) / len(result)
            total_edge = sum(leg["edge"] for leg in result)
            if score_fn:
                sc = score_fn(result, odds, avg_hit, total_edge)
            else:
                # Default: balance hit rate, recent form, edge, and diversification
                sc = avg_hit * 0.3 + avg_hit_l5 * 0.3 + total_edge * 0.2 + len(result) * 2
            if sc > best_score:
                best_combo = result
                best_score = sc

    return best_combo or []


def select_combo_2(candidates, exclude_descs=None):
    """🔥 價值膽 V5: Mid-risk 2-4 legs targeting 2.8-5.0x.
    L10 ≥ 60%, L5 ≥ 60%, edge ≥ 0, 神經刀 banned.
    Playoff gate removes low-minute and stale-form props."""
    exclude = set(exclude_descs or [])

    pool = [c for c in candidates
            if _is_player_milestone(c)
            and c["edge"] >= 0  # V5.3: FW-11 blocks negative EV legs
            and c["hit_l10"] >= 60
            and c.get("hit_l5", 0) >= 60
            and c["odds"] >= 1.20  # V5.2: Meaningful odds per leg
            and c.get("cov", 0) <= 0.75
            and not c.get("bench_minutes_risk", False)
            and _passes_playoff_gate(c, "value")
            and c["desc"] not in exclude]
    pool.sort(key=lambda x: (-x["hit_l10"], -x.get("hit_l5", 0), -x["edge"], x["odds"]))

    def score_fn(combo, odds, avg_hit, total_edge):
        closeness = 10 - abs(odds - 4.0) * 1.5
        avg_l5 = sum(c.get("hit_l5", c["hit_l10"]) for c in combo) / len(combo)
        return avg_hit * 0.35 + avg_l5 * 0.2 + total_edge * 0.15 + closeness * 0.3

    return _greedy_build(pool,
                         target_min=3.0, target_max=5.0,  # V5.3: FW-11 floor is 3.0x
                         min_legs=2, max_legs=4,
                         score_fn=score_fn,
                         max_same_team=3)


def select_combo_3(candidates, exclude_descs=None):
    """💎 高倍率 V5.3: 3-5 leg high-return shot targeting 8.0-15.0x.
    FW-11 enforces minimum 8.0x for combo 3.
    Relaxed gates: L10 ≥ 50%, L5 ≥ 50%, cross-team diversification.
    No volume stacking. Positive EV only."""
    exclude = set(exclude_descs or [])
    pool = [c for c in candidates
            if _is_player_milestone(c)
            and c["hit_l10"] >= 50
            and c.get("hit_l5", 0) >= 50
            and c["edge"] >= 0  # V5.3: FW-11 blocks negative EV legs
            and c["odds"] >= 1.15  # V5.2: Meaningful odds per leg
            and c.get("cov", 0) <= 0.85
            and not c.get("bench_minutes_risk", False)
            and _passes_playoff_gate(c, "high")
            and c["desc"] not in exclude]
    pool.sort(key=lambda x: (-x["hit_l10"], -x.get("hit_l5", 0), -x["edge"], x["odds"]))

    def score_fn(combo, odds, avg_hit, total_edge):
        avg_l5 = sum(c.get("hit_l5", c["hit_l10"]) for c in combo) / len(combo)
        closeness = 10 - abs(odds - 10.0)  # V5.3: Aim for 10x sweet spot
        return avg_hit * 0.4 + avg_l5 * 0.25 + total_edge * 0.1 + closeness * 0.25

    return _greedy_build(pool,
                         target_min=8.0, target_max=15.0,  # V5.3: FW-11 floor is 8.0x
                         min_legs=3, max_legs=5,  # V5.3: Allow up to 5 legs to reach 8.0x
                         score_fn=score_fn,
                         max_same_team=4)


def select_combo_x_value_bomb(candidates):
    """💣 Value Bomb V5: 2-3 legs targeting 5-15x.
    Safe base (L10 ≥ 80%, L5 ≥ 70%) + 1-2 edge spikes (Edge ≥ 10%, L10 ≥ 60%).
    Entertainment stake only."""

    # Phase 1: Safe foundation — strict quality
    safe_pool = [c for c in candidates
                 if _is_player_milestone(c)
                 and c["hit_l10"] >= 80
                 and c.get("hit_l5", 0) >= 70
                 and c["edge"] >= 0
                 and c["odds"] >= 1.05
                 and "神經刀" not in c.get("cov_grade", "")
                 and not c.get("bench_minutes_risk", False)
                 and _passes_playoff_gate(c, "bomb")]
    safe_pool.sort(key=lambda x: (-x["hit_l10"], -x.get("hit_l5", 0), x["odds"]))

    # Phase 2: Edge spikes — the 'bomb' component
    spike_pool = [c for c in candidates
                  if _is_player_milestone(c)
                  and c["edge"] >= 10
                  and c["hit_l10"] >= 60
                  and c.get("hit_l5", 0) >= 50
                  and _value_bomb_confirmed(c)
                  and _passes_playoff_gate(c, "bomb")]
    spike_pool.sort(key=lambda x: (-x["edge"], -x["hit_l10"]))

    if not spike_pool:
        return []

    # Phase 3: Build — 1-2 spikes first, fill with safe base
    combo = []
    used_players = set()

    for spike in spike_pool[:2]:
        if spike["player"] not in used_players:
            combo.append(spike)
            used_players.add(spike["player"])

    if not combo:
        return []

    for leg in safe_pool:
        if len(combo) >= 3:
            break
        if leg["player"] in used_players:
            continue
        # Same-team PTS cap
        if leg.get("category") == "PTS":
            same_team_pts = sum(1 for l in combo if l.get("category") == "PTS" and l.get("team") == leg["team"])
            if same_team_pts >= 2:
                continue
        # Cross-team cap
        same_team_total = sum(1 for l in combo if l.get("team") == leg["team"])
        if same_team_total >= 3:
            continue
        # Validate structural rules
        test_combo = combo + [leg]
        if not _combo_is_allowed(test_combo):
            continue

        combo.append(leg)
        used_players.add(leg["player"])

        current_odds = _combo_odds(combo)
        if current_odds >= 5.0 and len(combo) >= 2:
            break

    # Final validation
    if not _combo_is_allowed(combo):
        return []
    final_odds = _combo_odds(combo)
    if 2 <= len(combo) <= 3 and final_odds >= 5.0:
        return combo
    return []


# ─── Report Generation ──────────────────────────────────────────────────

def gen_meeting_intelligence(meta, odds, injuries, news, team_stats, season_phase="MID_SEASON"):
    lines = []
    away = meta.get("away", {})
    home = meta.get("home", {})
    away_name = away.get("name", "?")
    home_name = home.get("name", "?")
    away_abbr = away.get("abbr", "?")
    home_abbr = home.get("abbr", "?")

    lines.append(f"🎫 職業大戶 God Mode 單場分析 — {away_name} @ {home_name}")
    lines.append(f"")
    phase_str = f" ({season_phase})" if season_phase != "MID_SEASON" else ""
    lines.append(f"📅 數據鎖定: {meta.get('date', '?')} | NBA 賽季: 2025-26{phase_str}")
    lines.append(f"🧭 season_phase: **{season_phase}** | L10_ORDER: **{L10_ORDER}**")
    lines.append(f"🎯 盤口來源: **Sportsbet MCP Playwright 實時提取** (odds_source: SPORTSBET_LIVE)")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    spread = odds.get("spread_away", "?")
    total = odds.get("total", "?")
    ml_away = odds.get("ml_away", "?")
    ml_home = odds.get("ml_home", "?")

    lines.append(f"### 🏀 賽事背景")
    lines.append(f"| 項目 | 數據 |")
    lines.append(f"|------|------|")
    lines.append(f"| **讓分盤** | {away_abbr} {spread} |")
    lines.append(f"| **總分盤** | O/U {total} |")
    lines.append(f"| **獨贏** | {away_abbr} {ml_away} / {home_abbr} {ml_home} |")
    lines.append(f"| **節奏** | 中 |")
    lines.append(f"| **B2B** | 否 |")
    lines.append(f"")

    for abbr in [away_abbr, home_abbr]:
        ts = team_stats.get(abbr, {})
        if ts:
            lines.append(f"- {abbr}: PACE {ts.get('PACE', '?')} | OFF RTG {ts.get('OFF_RATING', '?')} | DEF RTG {ts.get('DEF_RATING', '?')}")

    lines.append(f"")
    lines.append(f"### 📋 傷病報告")
    for abbr in [away_abbr, home_abbr]:
        inj_data = injuries.get(abbr, {})
        if isinstance(inj_data, dict) and inj_data:
            for name_i, status in inj_data.items():
                lines.append(f"- {name_i} ({abbr}) — {status}")
        elif isinstance(inj_data, list) and inj_data:
            for inj in inj_data:
                if isinstance(inj, dict):
                    lines.append(f"- {inj.get('name', '?')} ({abbr}) — {inj.get('status', '?')}")
                else:
                    lines.append(f"- {inj} ({abbr})")
        else:
            lines.append(f"- {abbr}: 無傷兵報告")
    lines.append(f"")
    lines.append(f"---")
    return "\n".join(lines)


def gen_player_card(card):
    lines = []
    cat_label = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}
    cl = cat_label.get(card["category"], card["category"])
    l10_str = str(card.get("l10", []))

    lines.append(f"#### {card['name']} (#{card['jersey']}, {card['team']}) — {cl}")
    lines.append(f"| 🔢 數理引擎 | 🧠 邏輯引擎 |")
    lines.append(f"|:---|:---|")
    l5_data = card.get('l10', [])[:5] if len(card.get('l10', [])) >= 5 else card.get('last5_sportsbet', card.get('l10', []))
    lines.append(f"| **L5**: `{l5_data}` | **角色**: 核心主力 |")
    lines.append(f"| **L10 均值**: {card['avg']} \\| **中位**: {card['med']} | **USG%**: {card.get('usg_pct', 'N/A')} |")
    lines.append(f"| **SD**: {card['sd']} \\| **CoV**: {card['cov']} {card['cov_grade']} | **趨勢**: {card['trend']} |")
    lines.append(f"")

    # Sportsbet Line Analysis Table
    if card.get("line_analysis"):
        lines.append(f"**🎯 Sportsbet 盤口對照表 ({cl}):**")
        lines.append(f"| Line | Odds | 隱含勝率 | L10 命中 | L5 命中 | 預期勝率 | Edge | EV% | 判定 |")
        lines.append(f"|------|------|----------|----------|---------|----------|------|-----|------|")
        for lv, la in sorted(card["line_analysis"].items(), key=lambda x: float(x[0])):
            ld = la["line_display"]
            odds = la["odds"]
            ip = la["implied_prob"]
            hr10 = f"{la['hit_l10']}% ({la['hit_l10_count']})"
            hr5 = f"{la['hit_l5']}% ({la['hit_l5_count']})"
            adj_prob = la["estimated_prob"]
            ev = la["edge"]
            eg = la["edge_grade"]
            v = la["verdict"]
            ev_str = f"+{ev}%" if ev > 0 else f"{ev}%"
            true_ev = la.get("ev_pct", 0)
            true_ev_str = f"+{true_ev}%" if true_ev > 0 else f"{true_ev}%"
            lines.append(f"| {ld} | @{odds} | {ip}% | {hr10} | {hr5} | **{adj_prob}%** | {ev_str} {eg} | {true_ev_str} | {v} |")
        lines.append(f"")

    lines.append(f"---")
    return "\n".join(lines)


def gen_combo_section(combo_name, combo_emoji, combo_desc, legs):
    """Generate a complete combo section with pre-filled data."""
    lines = []

    if not legs:
        lines.append(f"### {combo_emoji} {combo_name}")
        lines.append(f"> ⚠️ 未能根據穩健 +EV 篩選條件搵到合適嘅 legs。此層級建議觀望，除非重新提取 Sportsbet 盤口後通過同一套 gate。")
        lines.append(f"")
        lines.append(f"---")
        return "\n".join(lines)

    # Calculate combo odds
    raw_combo_odds = 1.0
    combo_hit_parts = []
    avg_edge = 0
    for leg in legs:
        raw_combo_odds *= leg["odds"]
        # V3: Use adjusted probability
        combo_hit_parts.append(leg.get("estimated_prob", leg["hit_l10"]))
        avg_edge += leg["edge"]
    avg_edge = round(avg_edge / len(legs), 1)

    combo_hit = 1.0
    for h in combo_hit_parts:
        combo_hit *= (h / 100)
    combo_hit_pct = round(combo_hit * 100, 1)

    raw_combo_odds = round(raw_combo_odds, 2)
    payout = round(raw_combo_odds * 100, 0)

    # Header
    lines.append(f"### {combo_emoji} {combo_name} — 組合賠率 @{raw_combo_odds}")
    if combo_desc:
        lines.append(f"> {combo_desc}")
    if not _combo_is_allowed(legs):
        lines.append(f"> ⚠️ correlation_flags: SCRIPT_COLLISION_REVIEW_REQUIRED")
    lines.append(f"")

    # Legs table (V8: with EV%)
    lines.append(f"| Leg | 選項 | 賠率 | L10 命中 | 預期勝率 | Edge | EV% | CoV |")
    lines.append(f"|-----|------|------|----------|----------|------|-----|-----|")
    for i, leg in enumerate(legs):
        ev_str = f"+{leg['edge']}%" if leg['edge'] > 0 else f"{leg['edge']}%"
        true_ev = leg.get('ev_pct', 0)
        true_ev_str = f"+{true_ev}%" if true_ev > 0 else f"{true_ev}%"
        adj_p = leg.get('estimated_prob', leg['hit_l10'])
        lines.append(f"| 🧩 {i+1} | {leg['desc']} | @{leg['odds']} | {leg['hit_l10']}% ({leg['hit_l10_count']}) | **{adj_p}%** | {ev_str} | {true_ev_str} | {leg['cov']} {leg['cov_grade']} |")
    lines.append(f"")

    # Per-leg detailed analysis (V3: Python reasoning trace + Analyst [FILL])
    lines.append(f"**🎯 獨立關卡剖析:**")
    lines.append(f"")
    for i, leg in enumerate(legs):
        ev_str = f"+{leg['edge']}%" if leg['edge'] > 0 else f"{leg['edge']}%"
        adj_p = leg.get('estimated_prob', leg['hit_l10'])
        base_r = leg.get('base_rate', leg['hit_l10'])
        lines.append(f"**Leg {i+1} — {leg['desc']} @{leg['odds']}:**")
        if leg.get("correlation_flags"):
            lines.append(f"correlation_flags: {', '.join(leg['correlation_flags'])}")
        lines.append(f"📊 數據: L10 `{leg['l10']}` | AVG {leg['avg']} | MED {leg['med']} | SD {leg['sd']}")
        lines.append(f"隱含勝率 {leg['implied_prob']}% | Base Rate {base_r}% | 預期勝率 **{adj_p}%** | Edge: {ev_str} {leg['edge_grade']}")
        # Show 8-Factor adjustment breakdown — Python reasoning trace for LLM
        adj_line = leg.get('adj_line', '')
        if adj_line:
            lines.append(f"")
            lines.append(f"📐 **Python 推理 (8-Factor Adjusted Win Prob):**")
            lines.append(f"```")
            lines.append(f"Base Rate: {base_r}%")
            lines.append(f"{adj_line}")
            lines.append(f"→ Final Adjusted: {adj_p}%")
            lines.append(f"```")
            lines.append(f"> Python 選擇此 Leg 嘅原因: Base Rate {base_r}% 經 8-Factor 調整後 → {adj_p}%, Edge {ev_str} {leg['edge_grade']}")
        # Auto-generated core logic from Python
        narrative = leg.get('adj_narrative', '')
        if narrative:
            lines.append(f"🧠 **Python 自動核心邏輯**: {narrative}")
        else:
            lines.append(f"🧠 **Python 自動核心邏輯**: 數據面支持此盤口。")
        # MC inline integration (V2): embed MC result for this specific leg
        mc_lookup = leg.get('_mc_lookup', {})
        mc_key = f"{leg.get('player','')}|{leg.get('team','')}|{leg.get('category','')}|{leg.get('line_display','')}"
        mc_r = mc_lookup.get(mc_key)
        if mc_r:
            lines.append(f"📊 **MC 模擬 (10,000次)**: 命中率 **{mc_r.get('mc_prob',0)}%** | MC Edge: {'+' if mc_r.get('mc_edge',0) > 0 else ''}{mc_r.get('mc_edge',0)}% {'💎' if mc_r.get('mc_edge',0) >= 15 else ('✅' if mc_r.get('mc_edge',0) >= 5 else '➖')}")
        lines.append(f"")

    # Combo calculation — use adjusted prob
    odds_mult_parts = " × ".join(f"{leg['odds']}" for leg in legs)
    adj_probs = [leg.get('estimated_prob', leg['hit_l10']) for leg in legs]
    hit_mult_parts = " × ".join(f"{p}%" for p in adj_probs)

    # Auto-determine stake recommendation from true combo probability.
    num_legs = len(legs)

    if combo_hit_pct >= 55 and avg_edge >= 3 and num_legs <= 3:
        stake = "💰💰💰 標準注 (2-3 units) — 高信心穩膽"
    elif combo_hit_pct >= 40 and avg_edge >= 0 and num_legs <= 3:
        stake = "💰💰 半注 (1-2 units) — 中等信心"
    elif combo_hit_pct >= 25 and avg_edge >= 0 and num_legs <= 4:
        stake = "💰 試探注 (0.5-1 unit) — 整注命中率偏低"
    elif combo_hit_pct >= 15:
        stake = "💰 小額試探 (0.5 unit) — 高賠率投機"
    else:
        stake = "⚠️ 觀望 / 極小額 — 整注命中率偏低"

    # Auto-determine risk
    risk_factors = []
    high_cov_legs = [l for l in legs if isinstance(l["cov"], (int, float)) and l["cov"] > 0.35]
    neg_ev_legs = [l for l in legs if l["edge"] < 0]
    if high_cov_legs:
        names = ", ".join(l["desc"] for l in high_cov_legs)
        risk_factors.append(f"波動性風險 — {names} CoV 偏高 (神經刀)")
    if neg_ev_legs:
        names = ", ".join(l["desc"] for l in neg_ev_legs)
        risk_factors.append(f"負 EV 風險 — {names} 莊家有利")
    if combo_hit_pct < 40:
        risk_factors.append(f"低命中率 ({combo_hit_pct}%) — 需要所有關同時過")
    same_team = len(set(l.get("team", "") for l in legs)) == 1 and legs[0].get("team") != "TEAM"
    if same_team:
        risk_factors.append("同隊集中風險 — 球權分配可能互搶")
    if not risk_factors:
        risk_factors.append("整體風險可控")

    # Auto-generate 核心邏輯
    logic_parts = []
    if combo_hit_pct >= 70:
        logic_parts.append(f"組合命中率 {combo_hit_pct}% 高企")
    elif combo_hit_pct >= 50:
        logic_parts.append(f"組合命中率 {combo_hit_pct}% 中等")
    if avg_edge >= 10:
        logic_parts.append(f"平均 Edge {'+' if avg_edge > 0 else ''}{avg_edge}% 莊家顯著低估")
    elif avg_edge >= 5:
        logic_parts.append(f"平均 Edge +{avg_edge}% 正值有利")
    teams_in_combo = set(l.get("team", "") for l in legs if l.get("team") != "TEAM")
    if len(teams_in_combo) >= 2:
        logic_parts.append("跨隊分散降低相關性風險")
    elif same_team:
        logic_parts.append("同隊配搭需確認球權分配不衝突")
    all_stable = all(isinstance(l["cov"], (int, float)) and l["cov"] <= 0.35 for l in legs)
    if all_stable:
        logic_parts.append("全部 Leg CoV 穩定")
    core_logic = "。".join(logic_parts) + "。" if logic_parts else "數據面支持此組合。"

    # V8: Compute combo-level EV with correlation adjustment
    combo_ev_data = compute_combo_ev(legs)
    corr_penalty_val = combo_ev_data.get("correlation_penalty", 0)
    adj_joint_prob = combo_ev_data.get("adjusted_joint_prob", 0)
    adj_joint_prob_pct = round(adj_joint_prob * 100, 1)
    combo_ev_pct = combo_ev_data.get("combo_ev_pct", 0)
    risk_tier = combo_ev_data.get("combo_risk_tier", "—")
    risk_tier_emoji = {"BANKER": "🛡️", "VALUE": "🔥", "MARGINAL": "⚠️", "NEGATIVE": "❌"}.get(risk_tier, "—")

    lines.append(f"**📊 組合結算:**")
    lines.append(f"- **賠率相乘**: {odds_mult_parts} = **@{raw_combo_odds}**")
    lines.append(f"- **$100 回報**: **${int(payout)}**")
    lines.append(f"- **組合命中率 (naive)**: {hit_mult_parts} = **{combo_hit_pct}%**")
    if corr_penalty_val > 0:
        lines.append(f"- **關聯性懲罰**: -{round(corr_penalty_val*100, 1)}% (同隊/同場相關性扣減)")
        lines.append(f"- **調整後組合命中率**: **{adj_joint_prob_pct}%**")
    lines.append(f"- **平均 Edge**: {'+' if avg_edge > 0 else ''}{avg_edge}%")
    lines.append(f"- **Combo EV%**: {'+' if combo_ev_pct > 0 else ''}{combo_ev_pct}% {risk_tier_emoji} {risk_tier}")
    # Kelly Criterion (Half-Kelly) — use adjusted probability
    combo_odds_for_kelly = raw_combo_odds
    kelly_prob = adj_joint_prob_pct if corr_penalty_val > 0 else combo_hit_pct
    kelly_f = kelly_fraction(kelly_prob, combo_odds_for_kelly)
    kelly_stake = round(kelly_f * 1000, 0)
    lines.append(f"- **🎯 Kelly 注碼建議**: {kelly_f*100:.1f}% bankroll (Half-Kelly) → **${int(kelly_stake)}** / $1000")
    lines.append(f"- **🛡️ 組合核心邏輯**: {core_logic}")
    lines.append(f"- **⚠️ 主要風險**: {' / '.join(risk_factors)}")
    lines.append(f"- **建議注碼**: {stake}")
    lines.append(f"")
    lines.append(f"> ⚠️ 以上賠率為獨立 Leg 相乘。實際 Sportsbet SGM 價格可能因關聯性調整而不同，落注前請以 Sportsbet 顯示為準。")
    lines.append(f"")
    lines.append(f"---")
    return "\n".join(lines)


def gen_full_report(meta, odds, injuries, news, team_stats,
                    all_cards, sportsbet_time, season_phase="MID_SEASON"):
    sections = []

    away_abbr = meta.get("away", {}).get("abbr", "?")
    home_abbr = meta.get("home", {}).get("abbr", "?")
    away_name = meta.get("away", {}).get("name", "?")
    home_name = meta.get("home", {}).get("name", "?")

    # Header
    sections.append(f"# 🏀 NBA Wong Choi — {away_name} @ {home_name}")
    sections.append(f"**日期**: {meta.get('date', '?')} | **Sportsbet 提取時間**: {sportsbet_time}")
    sections.append(f"**odds_source**: SPORTSBET_LIVE ✅ | **引擎版本**: Adjusted Win Prob V8 (EV Quant + Correlation Penalty)")
    sections.append(f"**season_phase**: {season_phase} | **L10_ORDER**: {L10_ORDER} | **strategy**: SPORTSBET_MILESTONE_OVER_ONLY")
    sections.append(f"")

    # ── Blowout / Tank Warning Banner ──
    spread_val = odds.get("spread_away", None)
    abs_spread = 0
    if spread_val:
        try:
            abs_spread = abs(float(spread_val))
        except (ValueError, TypeError):
            pass
    # Tank detection: check if either team has very poor record (from standings)
    tank_warnings = []
    standings = odds.get("standings", {})
    for abbr in [away_abbr, home_abbr]:
        record = standings.get(abbr, "")
        if record:
            try:
                parts = record.split("-")
                if len(parts) == 2:
                    wins = int(parts[0])
                    losses = int(parts[1])
                    total = wins + losses
                    if total > 50 and wins < 25:  # Late season + terrible record = tanking
                        tank_warnings.append(f"{abbr} ({record}) 戰績極差，高度懷疑擺爛搶鑰匙")
                    elif total > 50 and wins < 30:
                        tank_warnings.append(f"{abbr} ({record}) 戰績偏差，存在擺爛可能")
            except (ValueError, IndexError):
                pass

    if abs_spread >= 8.5 or tank_warnings:
        sections.append(f"> [!CAUTION]")
        if abs_spread >= 15:
            sections.append(f"> 🚨 **極高 BLOWOUT 風險 (紅牌)** — 讓分盤 {spread_val}，大分差場次主力球員提前下場機率極高。")
            sections.append(f"> 建議: **避免主力 PTS Over**，改買低門檻 Prop 或助攻/籃板盤。")
        elif abs_spread >= 12:
            sections.append(f"> 🔴 **高 BLOWOUT 風險 (橙牌)** — 讓分盤 {spread_val}，垃圾時間風險顯著。")
            sections.append(f"> 建議: 謹慎操作 PTS Over，留意上場時間萎縮。")
        elif abs_spread >= 8.5:
            sections.append(f"> ⚠️ **BLOWOUT 風險 (黃牌)** — 讓分盤 {spread_val}，主力上場時間可能縮減。")
            sections.append(f"> 建議: 留意主力球員第四節上場時間。")
        for tw in tank_warnings:
            sections.append(f"> 🏳️ **擺爛/戰意警告**: {tw}")
            sections.append(f"> 建議: 注意該隊主力上場時間縮減、輪換陣容擴大。")
        sections.append(f"")

    # Meeting Intelligence
    sections.append(gen_meeting_intelligence(meta, odds, injuries, news, team_stats, season_phase))
    sections.append(f"")

    # ── Run Monte Carlo FIRST — build lookup for inline embedding ──
    mc_lookup = {}
    try:
        from monte_carlo_nba import run_monte_carlo_for_cards, format_mc_section, build_mc_lookup
        is_b2b_map = {}
        for t_abbr in [away_abbr, home_abbr]:
            fatigue = meta.get("away" if t_abbr == away_abbr else "home", {}).get("fatigue", {})
            is_b2b_map[t_abbr] = fatigue.get("is_b2b", False) if isinstance(fatigue, dict) else False
        
        mc_results = run_monte_carlo_for_cards(
            all_cards, spread=odds.get("spread_away"),
            is_b2b_map=is_b2b_map, team_stats=team_stats, meta=meta, n=10000,
            season_phase=season_phase)
        
        if mc_results:
            mc_lookup = build_mc_lookup(mc_results)
    except Exception as e:
        mc_results = []
        print(f"⚠️ Monte Carlo 預計算失敗: {e}")

    # ── Auto-Combo (placed FIRST for quick reference) ──
    candidates = build_leg_candidates(all_cards, team_odds=odds, meta=meta, injuries=injuries)

    _pc = [c for c in candidates if c.get('market_type') == PLAYER_MARKET]
    print(f"  📊 SGM Pool: {len(all_cards)} cards → {len(candidates)} candidates ({len(_pc)} player)")

    # Inject mc_lookup into every candidate leg so gen_combo_section can embed inline MC
    for c in candidates:
        c['_mc_lookup'] = mc_lookup

    combo_1 = select_combo_1(candidates)
    
    # F4: No cascading exclusion — each combo selects independently from full pool.
    # With multi-leg combos, overlap is acceptable and produces better results.
    combo_2 = select_combo_2(candidates)
    combo_3 = select_combo_3(candidates)
    combo_x = select_combo_x_value_bomb(candidates)

    sections.append(f"## 🎰 SGM Parlay 組合 (Python Auto-Selection V5)")
    sections.append(f"")
    sections.append(f"> [!IMPORTANT]")
    sections.append(f"> 以下組合由 Python V5 短腿數 + Playoff Gate 引擎自動篩選。所有數學數據不可修改。")
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 1: 穩膽 SGM (Low Risk)", "🛡️",
        f"2-3 Legs | L10/L5 ≥80% | 目標 2.0-3.2x",
        combo_1))
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 2: 價值膽 Multi-Leg (Mid Risk)", "🔥",
        f"2-4 Legs | L10/L5 ≥60% | 目標 2.8-5.0x",
        combo_2))
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 3: 高倍率 (High Return)", "💎",
        f"3-5 Legs | L10/L5 ≥50% | 目標 8.0-15.0x",
        combo_3))
    sections.append(f"")

    if combo_x:
        sections.append(gen_combo_section(
            "組合 X: 💣 Value Bomb (莊家低估)", "💣",
            f"2-3 Legs | 安全基座 + Edge≥10% 炸彈腿 | 目標 5.0-15.0x",
            combo_x))
        sections.append(f"")

    # Summary
    # Find strongest/weakest legs across all combos
    all_combo_legs = combo_1 + combo_2 + combo_3 + (combo_x or [])
    if all_combo_legs:
        best_leg = max(all_combo_legs, key=lambda x: x.get("ev_pct", x["edge"]))
        worst_leg = min(all_combo_legs, key=lambda x: x.get("ev_pct", x["edge"]))
        best_ev = best_leg.get('ev_pct', best_leg['edge'])
        worst_ev = worst_leg.get('ev_pct', worst_leg['edge'])
        sections.append(f"- **最強關**: {best_leg['desc']} @{best_leg['odds']} — EV% {'+' if best_ev > 0 else ''}{best_ev}% {best_leg['edge_grade']}")
        sections.append(f"- **最弱關**: {worst_leg['desc']} @{worst_leg['odds']} — EV% {'+' if worst_ev > 0 else ''}{worst_ev}% {worst_leg['edge_grade']}")
    else:
        sections.append(f"- 最強關: 未能篩選")
        sections.append(f"- 最弱關: 未能篩選")
    sections.append(f"- **賽前 60 分鐘必查**: 傷病更新 / 首發陣容確認 / Sportsbet 盤口變動 / B2B 情況")
    sections.append(f"")
    sections.append(f"---")
    sections.append(f"")

    # ── Monte Carlo Simulation Summary Table ──
    try:
        if mc_results:
            sections.append(format_mc_section(mc_results))
            sections.append("")
    except Exception as e:
        sections.append(f"\n> ⚠️ Monte Carlo 模擬暫時無法執行: {e}\n")

    # Player Cards (appendix — detailed reference)
    sections.append(f"## 📊 球員盤口詳細分析 (Appendix)")
    sections.append(f"")

    for team_abbr in [away_abbr, home_abbr]:
        team_cards = [c for c in all_cards if c["team"] == team_abbr]
        if team_cards:
            team_name_d = away_name if team_abbr == away_abbr else home_name
            sections.append(f"### 🏀 {team_name_d} ({team_abbr})")
            sections.append(f"")
            for card in team_cards:
                sections.append(gen_player_card(card))
                sections.append(f"")

    sections.append(f"---")
    sections.append(f"")
    sections.append(f"## ✅ 盤口數據來源驗證")
    sections.append(f"> **Sportsbet MCP Playwright** 即時提取 | 提取時間: {sportsbet_time}")
    sections.append(f"> 所有 Lines/Odds 來自 sportsbet.com.au DOM Snapshot")
    sections.append(f"> Sportsbet 線格式: \"10+\" = 10 分或以上 (≥10)")

    # Count remaining [FILL] slots
    full_text = "\n".join(sections)
    fill_count = full_text.count("[FILL")
    sections.append(f"")
    sections.append(f"## 📋 自檢")
    combo_count = sum(1 for c in [combo_1, combo_2, combo_3, combo_x] if c)
    sections.append(f"✅ Python 預填完成 | 組合數: {combo_count} | 未填寫項目 殘留: {fill_count} 個 (均為 Analyst 邏輯欄位)")

    return "\n".join(sections)


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi V2 — Pre-filled Skeleton Generator")
    parser.add_argument("--sportsbet", required=True, help="Sportsbet odds JSON (from sportsbet_parser.py)")
    parser.add_argument("--extractor", required=True, help="nba_extractor.py output JSON")
    parser.add_argument("--output", required=True, help="Output skeleton .md path")
    args = parser.parse_args()

    if not os.path.exists(args.sportsbet):
        print(f"❌ Sportsbet JSON 唔存在: {args.sportsbet}")
        print(f"⚠️ odds_not_found — 請重新執行 MCP Playwright 提取")
        sys.exit(1)

    if not os.path.exists(args.extractor):
        print(f"❌ Extractor JSON 唔存在: {args.extractor}")
        sys.exit(1)

    with open(args.sportsbet, 'r', encoding='utf-8') as f:
        sportsbet = json.load(f)
    with open(args.extractor, 'r', encoding='utf-8') as f:
        extractor = json.load(f)

    meta = extractor.get("meta", {})
    ex_odds = extractor.get("odds", {})
    injuries = extractor.get("injuries", {})
    news = extractor.get("news", {})
    team_stats = extractor.get("team_stats", {})
    ext_players = extractor.get("players", {})

    # F4: Fill missing odds from Sportsbet game_lines (when Action Network returns 0)
    sb_game_lines = sportsbet.get("game_lines", {})
    if sb_game_lines:
        for k, v in sb_game_lines.items():
            if v and (not ex_odds.get(k) or ex_odds.get(k) == "?"):
                ex_odds[k] = v
    sportsbet_time = sportsbet.get("extraction_time", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # V3: Extract additional context data
    key_defenders = extractor.get("key_defenders", {})
    usg_redistribution = extractor.get("usage_redistribution", {})
    correlation_warnings = extractor.get("correlation_warnings", {})

    away_abbr = meta.get("away", {}).get("abbr", "?")
    home_abbr = meta.get("home", {}).get("abbr", "?")
    
    date_str = meta.get("date", "?")
    season_phase = detect_season_phase(date_str, meta)
    meta["season_phase"] = season_phase
    meta["l10_order"] = L10_ORDER

    # V3: Pre-compute context for each team
    spread = ex_odds.get("spread_away", None)

    # Detect B2B from fatigue data (scan all players, if any has fatigue warning → B2B)
    team_b2b = {away_abbr: False, home_abbr: False}
    for abbr in [away_abbr, home_abbr]:
        for p in ext_players.get(abbr, []):
            fatigue = p.get("fatigue") or {}
            if fatigue.get("fatigue_pct", 0) > 0 or fatigue.get("warning", ""):
                team_b2b[abbr] = True
                break

    # Compute defender impact per opponent team (avg PCT_PLUSMINUS of top 3)
    def get_defender_impact(team_abbr):
        defenders = key_defenders.get(team_abbr, [])
        if not defenders:
            return None, ""
        top3 = defenders[:3]
        impacts = [d.get("PCT_PLUSMINUS", 0) for d in top3 if isinstance(d.get("PCT_PLUSMINUS"), (int, float))]
        if not impacts:
            return None, ""
        avg_impact = sum(impacts) / len(impacts)
        # Get top defender name for narrative
        top_name = top3[0].get("name", "") if top3 else ""
        return avg_impact, top_name

    # Build all player cards
    all_cards = []
    player_props = sportsbet.get("player_props", {})

    for category, players in player_props.items():
        for player_name, bet_data in players.items():
            # Try both teams for extractor match
            ext_p = find_player_in_extractor(ext_players, player_name, away_abbr)
            team = away_abbr
            if ext_p is None:
                ext_p = find_player_in_extractor(ext_players, player_name, home_abbr)
                team = home_abbr
            if ext_p is None:
                print(f"Skipping {player_name} - not in {away_abbr} or {home_abbr}")
                continue  # V7 Fix: Block cross-contamination from unified JSON

            # V3: Determine context for this player
            opponent = home_abbr if team == away_abbr else away_abbr
            opp_stats = team_stats.get(opponent, {})
            opp_def_rank = opp_stats.get("DEF_RANK", None)
            opp_pace = opp_stats.get("PACE", None)
            is_home = (team == home_abbr)
            is_b2b = team_b2b.get(team, False)
            usg_bonus = usg_redistribution.get(team, {}).get(player_name, {}).get("bonus_USG", 0)
            def_impact, top_def_name = get_defender_impact(opponent)

            card = build_player_card(
                player_name, team, bet_data, ext_p, category,
                opponent_def_rank=opp_def_rank, opponent_pace=opp_pace,
                is_b2b=is_b2b, is_home=is_home, spread=spread,
                usg_bonus=usg_bonus, defender_impact=def_impact,
                top_defender_name=top_def_name, opponent_abbr=opponent,
                season_phase=season_phase)
            all_cards.append(card)

    # Summary
    cats = {}
    for c in all_cards:
        cats[c['category']] = cats.get(c['category'], 0) + 1
    cat_str = ", ".join(f"{k}: {v}" for k, v in cats.items())
    print(f"📊 已處理 {len(all_cards)} 個球員×盤口組合 ({cat_str})")
    print(f"📐 引擎版本: Adjusted Win Prob V3 (10-Factor)")

    # Generate report
    report = gen_full_report(meta, ex_odds, injuries, news, team_stats,
                             all_cards, sportsbet_time, season_phase=season_phase)

    # Write
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ Pre-filled skeleton V8 已生成: {args.output}")
    print(f"   📐 引擎版本: Adjusted Win Prob V8 (EV Quant + Correlation Penalty)")
    print(f"   🧠 核心邏輯已自動生成 (無 [FILL] 佔位符)")
    print(f"   📎 下一步: NBA Analyst 審閱及補充分析")


if __name__ == "__main__":
    main()
