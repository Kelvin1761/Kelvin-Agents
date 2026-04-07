#!/usr/bin/env python3
"""
generate_nba_reports.py — NBA Wong Choi 預填骨架報告生成器 V2

將 Bet365 即時盤口 JSON + nba_extractor.py 深度 JSON 合併計算，
自動生成符合新版緊湊格式嘅 pre-filled skeleton report。

Key changes in V2:
  - Bet365 line format: "10+" (not "O 10.5")
  - Hit rate calc: >= (not >)
  - Auto-combo engine with 5 combinations
  - Pre-filled combo tables with per-leg logic slots

Usage:
  python generate_nba_reports.py \
    --bet365 path/to/Bet365_Odds_CHI_WSH.json \
    --extractor path/to/nba_game_data_CHI_WSH.json \
    --output path/to/Game_CHI_WSH_Skeleton.md

Version: 2.0.0
"""
import sys, io, os, json, math, argparse
from datetime import datetime

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

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
    weights = [0.5 + (1.0 * i / max(n - 1, 1)) for i in range(n)]
    return round(sum(d * w for d, w in zip(data, weights)) / sum(weights), 2)


def trend_label(data):
    if len(data) < 5: return "— 數據不足"
    l3 = sum(data[-3:]) / 3
    l10 = sum(data) / len(data)
    diff = (l3 - l10) / l10 * 100 if l10 != 0 else 0
    if diff > 5: return "📈上升"
    elif diff < -5: return "📉下降"
    else: return "—持平"


def hit_rate(data, line_val):
    """Hit rate using >= (Bet365 '10' means '10 or above')."""
    if not data: return 0.0, "0/0", []
    hits = sum(1 for x in data if x >= line_val)
    pct = round(hits / len(data) * 100, 1)
    count = f"{hits}/{len(data)}"
    misses = []
    for i, x in enumerate(data):
        if x < line_val:
            misses.append({"game": i+1, "value": x, "deficit": round(x - line_val, 1)})
    return pct, count, misses


def implied_prob(odds):
    if odds <= 0: return 0.0
    return round(100 / float(odds), 2)


def edge_calc(estimated_prob, implied):
    """Edge = estimated probability - implied probability."""
    return round(estimated_prob - implied, 2)


def edge_grade(edge):
    if edge >= 15: return "💎核心高價值"
    elif edge >= 5: return "✅有價值"
    elif edge >= 0: return "➖邊緣"
    else: return "❌負EV"


# ─── Data Merging ───────────────────────────────────────────────────────

def find_player_in_extractor(ext_players, name, team_abbr):
    if team_abbr in ext_players:
        for p in ext_players[team_abbr]:
            if p.get("name", "").lower() == name.lower():
                return p
    last_name = name.split()[-1].lower() if name else ""
    if team_abbr in ext_players:
        for p in ext_players[team_abbr]:
            p_last = p.get("name", "").split()[-1].lower()
            if p_last == last_name:
                return p
    return None


def build_player_card(player_name, team_abbr, bet365_data, ext_player, category):
    card = {
        "name": player_name,
        "team": team_abbr,
        "category": category,
        "jersey": bet365_data.get("jersey", "?"),
        "last5_bet365": bet365_data.get("last5", []),
        "lines": bet365_data.get("lines", {}),
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

        l5 = l10[-5:] if len(l10) >= 5 else l10
        l3 = l10[-3:] if len(l10) >= 3 else l10
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
        # Use Bet365 L5 as fallback
        l5 = bet365_data.get("last5", [])
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
        card["l3_avg"] = round(sum(l5[-3:]) / len(l5[-3:]), 2) if len(l5) >= 3 else avg
        card["usg_pct"] = "N/A"
        card["ts_pct"] = "N/A"
        card["home_ppg"] = "N/A"
        card["road_ppg"] = "N/A"
        card["min_avg"] = 0
        card["fatigue"] = {}
        card["position"] = "?"

    # Hit rates for each Bet365 line
    card["line_analysis"] = {}
    data_for_hr = card["l10"]
    for line_val_str, odds_str in card["lines"].items():
        line_val = float(line_val_str)  # Bet365 "10" = 10+, so threshold is >= 10
        hr_l10, hr_l10_count, misses = hit_rate(data_for_hr, line_val)
        l5_data = data_for_hr[-5:] if len(data_for_hr) >= 5 else data_for_hr
        l3_data = data_for_hr[-3:] if len(data_for_hr) >= 3 else data_for_hr
        hr_l5, hr_l5_count, _ = hit_rate(l5_data, line_val)
        hr_l3, hr_l3_count, _ = hit_rate(l3_data, line_val)
        imp = implied_prob(float(odds_str))
        est_prob = hr_l10  # Use L10 hit rate as estimated probability
        ev = edge_calc(est_prob, imp)

        card["line_analysis"][line_val_str] = {
            "line": line_val,
            "line_display": f"{line_val_str}+",  # "10+" format
            "odds": odds_str,
            "implied_prob": imp,
            "estimated_prob": est_prob,
            "edge": ev,
            "edge_grade": edge_grade(ev),
            "hit_l10": hr_l10, "hit_l10_count": hr_l10_count,
            "hit_l5": hr_l5, "hit_l5_count": hr_l5_count,
            "hit_l3": hr_l3, "hit_l3_count": hr_l3_count,
            "misses": misses,
            "verdict": "✅" if hr_l5 >= 70 else ("⚠️" if hr_l5 >= 50 else "❌"),
        }

    return card


# ─── Auto-Combo Engine ──────────────────────────────────────────────────

def build_leg_candidates(all_cards, team_odds=None, meta=None, injuries=None):
    """Build a flat list of all possible legs from player cards + team odds."""
    candidates = []
    cat_label = {"points": "PTS", "threes_made": "3PM", "rebounds": "REB", "assists": "AST"}
    injuries = injuries or {}

    for card in all_cards:
        team_abbr = card["team"]
        player_name = card["name"]
        status = injuries.get(team_abbr, {}).get(player_name, "")
        
        # ⚠️ Skip players who are strictly OUT or injured so they do not pollute safely generated combos
        if status.lower() == "out":
            continue
            
        cl = cat_label.get(card["category"], card["category"])
        for line_key, la in card.get("line_analysis", {}).items():
            odds = float(la["odds"])
            if odds < 1.01:  # Skip near-certainties
                continue
            candidates.append({
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
                "edge": la["edge"],
                "edge_grade": la["edge_grade"],
                "cov": card["cov"],
                "cov_grade": card["cov_grade"],
                "avg": card["avg"],
                "l10": card["l10"],
                "sd": card["sd"],
                "med": card["med"],
                "weighted_avg": card["weighted_avg"],
                "trend": card["trend"],
                "desc": f"{card['name']} ({card['team']}) {cl} {la['line_display']}",
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
        leg = make_team_leg(f"Total U{total}", "1.91")
        if leg:
            legs.append(leg)
    
    return legs


def select_combo_1(candidates):
    """穩膽: Best 2 legs with high hit rate, targeting combined odds > 2x."""
    TARGET_MIN = 2.0
    pool = [c for c in candidates
            if c["hit_l10"] >= 70 and c["odds"] >= 1.2]
    pool.sort(key=lambda x: (-x["hit_l10"], -x["edge"], -x["odds"]))
    
    best_combo = None
    best_score = -999
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            combo_odds = pool[i]["odds"] * pool[j]["odds"]
            combo_edge = pool[i]["edge"] + pool[j]["edge"]
            avg_hit = (pool[i]["hit_l10"] + pool[j]["hit_l10"]) / 2
            if combo_odds >= TARGET_MIN and avg_hit >= 70:
                # Score: prefer high hit rate + high edge + odds close to 2-3x sweet spot
                score = avg_hit * 0.5 + combo_edge * 0.3 + min(combo_odds, 3.0) * 10
                if score > best_score:
                    best_combo = [pool[i], pool[j]]
                    best_score = score
    
    if best_combo:
        return best_combo
    
    # Fallback: relax hit rate
    for i in range(min(len(pool), 15)):
        for j in range(i + 1, min(len(pool), 15)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            combo_odds = pool[i]["odds"] * pool[j]["odds"]
            if combo_odds >= TARGET_MIN:
                return [pool[i], pool[j]]
    return pool[:2] if len(pool) >= 2 else pool


def select_combo_2(candidates, exclude_descs=None):
    """均衡: Target combined odds > 3x, aiming for 5x."""
    TARGET_MIN, TARGET_MAX = 3.0, 6.0
    TARGET_IDEAL = 5.0
    exclude = set(exclude_descs or [])
    pool = [c for c in candidates
            if c["edge"] >= -5 and c["hit_l10"] >= 40 and c["desc"] not in exclude]
    pool.sort(key=lambda x: (-x["edge"], -x["odds"]))
    
    best_combo = None
    best_score = -999
    for i in range(min(len(pool), 20)):
        for j in range(i + 1, min(len(pool), 20)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            combo_odds = pool[i]["odds"] * pool[j]["odds"]
            combo_edge = pool[i]["edge"] + pool[j]["edge"]
            if TARGET_MIN <= combo_odds <= TARGET_MAX:
                # Score: prefer odds near 5x + high edge
                closeness = 10 - abs(combo_odds - TARGET_IDEAL) * 2
                score = combo_edge * 0.4 + closeness * 0.6
                if score > best_score:
                    best_combo = [pool[i], pool[j]]
                    best_score = score
    
    if best_combo:
        return best_combo
    
    # Fallback: relax to 2.5-8x, or try 3 legs
    for i in range(min(len(pool), 15)):
        for j in range(i + 1, min(len(pool), 15)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            combo_odds = pool[i]["odds"] * pool[j]["odds"]
            if 2.5 <= combo_odds <= 8.0:
                return [pool[i], pool[j]]
    return []


def select_combo_3(candidates, exclude_descs=None):
    """高倍率進取: 3 legs targeting combined odds 8-10x."""
    TARGET_MIN, TARGET_MAX = 8.0, 12.0
    exclude = set(exclude_descs or [])
    pool = [c for c in candidates
            if c["hit_l10"] >= 40 and c["odds"] >= 1.3
            and c["desc"] not in exclude]
    pool.sort(key=lambda x: (-x["edge"], -x["odds"]))
    
    # Try 3-leg combinations targeting 8-10x
    best_combo = None
    best_edge = -999
    for i in range(min(len(pool), 15)):
        for j in range(i + 1, min(len(pool), 15)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            for k in range(j + 1, min(len(pool), 15)):
                if pool[k]["player"] in (pool[i]["player"], pool[j]["player"]):
                    continue
                combo_odds = pool[i]["odds"] * pool[j]["odds"] * pool[k]["odds"]
                combo_edge = pool[i]["edge"] + pool[j]["edge"] + pool[k]["edge"]
                if TARGET_MIN <= combo_odds <= TARGET_MAX and combo_edge > best_edge:
                    best_combo = [pool[i], pool[j], pool[k]]
                    best_edge = combo_edge
    
    if best_combo:
        return best_combo
    
    # Fallback: relax to 5-15x range
    for i in range(min(len(pool), 12)):
        for j in range(i + 1, min(len(pool), 12)):
            if pool[i]["player"] == pool[j]["player"]:
                continue
            for k in range(j + 1, min(len(pool), 12)):
                if pool[k]["player"] in (pool[i]["player"], pool[j]["player"]):
                    continue
                combo_odds = pool[i]["odds"] * pool[j]["odds"] * pool[k]["odds"]
                combo_edge = pool[i]["edge"] + pool[j]["edge"] + pool[k]["edge"]
                if 5.0 <= combo_odds <= 15.0 and combo_edge > best_edge:
                    best_combo = [pool[i], pool[j], pool[k]]
                    best_edge = combo_edge
    return best_combo or []


def select_combo_x_value_bomb(candidates):
    """Value Bomb: Significant +EV where bookies undervalue (Edge ≥ 15%)"""
    pool = [c for c in candidates
            if c["edge"] >= 15 and c["hit_l10"] >= 60]
    pool.sort(key=lambda x: -x["edge"])
    if not pool:
        # Relax to edge >= 10
        pool = [c for c in candidates
                if c["edge"] >= 10 and c["hit_l10"] >= 55]
        pool.sort(key=lambda x: -x["edge"])
    selected = []
    used_players = set()
    for c in pool:
        if c["player"] not in used_players:
            selected.append(c)
            used_players.add(c["player"])
        if len(selected) >= 3:
            break
    return selected


# ─── Report Generation ──────────────────────────────────────────────────

def gen_meeting_intelligence(meta, odds, injuries, news, team_stats):
    lines = []
    away = meta.get("away", {})
    home = meta.get("home", {})
    away_name = away.get("name", "?")
    home_name = home.get("name", "?")
    away_abbr = away.get("abbr", "?")
    home_abbr = home.get("abbr", "?")

    lines.append(f"🎫 職業大戶 God Mode 單場分析 — {away_name} @ {home_name}")
    lines.append(f"")
    lines.append(f"📅 數據鎖定: {meta.get('date', '?')} | NBA 賽季: 2025-26")
    lines.append(f"🎯 盤口來源: **Bet365 MCP Playwright 實時提取** (odds_source: BET365_LIVE)")
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
    lines.append(f"| **節奏** | [FILL: 高/中/低] |")
    lines.append(f"| **B2B** | [FILL] |")
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
    lines.append(f"| **L5**: `{card.get('last5_bet365', [])}` | **角色**: [FILL] |")
    lines.append(f"| **L10 均值**: {card['avg']} \\| **中位**: {card['med']} | **USG%**: {card.get('usg_pct', 'N/A')} |")
    lines.append(f"| **SD**: {card['sd']} \\| **CoV**: {card['cov']} {card['cov_grade']} | **趨勢**: {card['trend']} |")
    lines.append(f"")

    # Bet365 Line Analysis Table
    if card.get("line_analysis"):
        lines.append(f"**🎯 Bet365 盤口對照表 ({cl}):**")
        lines.append(f"| Line | Odds | 隱含勝率 | L10 命中 | L5 命中 | Edge | 判定 |")
        lines.append(f"|------|------|----------|----------|---------|------|------|")
        for lv, la in sorted(card["line_analysis"].items(), key=lambda x: float(x[0])):
            ld = la["line_display"]
            odds = la["odds"]
            ip = la["implied_prob"]
            hr10 = f"{la['hit_l10']}% ({la['hit_l10_count']})"
            hr5 = f"{la['hit_l5']}% ({la['hit_l5_count']})"
            ev = la["edge"]
            eg = la["edge_grade"]
            v = la["verdict"]
            ev_str = f"+{ev}%" if ev > 0 else f"{ev}%"
            lines.append(f"| {ld} | @{odds} | {ip}% | {hr10} | {hr5} | {ev_str} {eg} | {v} |")
        lines.append(f"")

    lines.append(f"---")
    return "\n".join(lines)


def gen_combo_section(combo_name, combo_emoji, combo_desc, legs):
    """Generate a complete combo section with pre-filled data."""
    lines = []

    if not legs:
        lines.append(f"### {combo_emoji} {combo_name}")
        lines.append(f"> ⚠️ 未能根據篩選條件搵到合適嘅 legs。Analyst 可手動選擇。")
        lines.append(f"")
        lines.append(f"---")
        return "\n".join(lines)

    # Calculate combo odds
    raw_combo_odds = 1.0
    combo_hit_parts = []
    avg_edge = 0
    for leg in legs:
        raw_combo_odds *= leg["odds"]
        combo_hit_parts.append(leg["hit_l10"])
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
    lines.append(f"")

    # Legs table
    lines.append(f"| Leg | 選項 | 賠率 | L10 命中 | L5 命中 | Edge | CoV |")
    lines.append(f"|-----|------|------|----------|---------|------|-----|")
    for i, leg in enumerate(legs):
        ev_str = f"+{leg['edge']}%" if leg['edge'] > 0 else f"{leg['edge']}%"
        lines.append(f"| 🧩 {i+1} | {leg['desc']} | @{leg['odds']} | {leg['hit_l10']}% ({leg['hit_l10_count']}) | {leg['hit_l5']}% ({leg['hit_l5_count']}) | {ev_str} | {leg['cov']} {leg['cov_grade']} |")
    lines.append(f"")

    # Per-leg detailed analysis (auto-generated)
    lines.append(f"**🎯 獨立關卡剖析:**")
    lines.append(f"")
    for i, leg in enumerate(legs):
        ev_str = f"+{leg['edge']}%" if leg['edge'] > 0 else f"{leg['edge']}%"
        lines.append(f"**Leg {i+1} — {leg['desc']} @{leg['odds']}:**")
        lines.append(f"📊 數據: L10 `{leg['l10']}` | AVG {leg['avg']} | MED {leg['med']} | SD {leg['sd']}")
        lines.append(f"隱含勝率 {leg['implied_prob']}% | 預估勝率 {leg['estimated_prob']}% (L10) | Edge: {ev_str} {leg['edge_grade']}")
        # Auto-generate per-leg rationale
        leg_reasons = []
        if leg['hit_l10'] >= 80:
            leg_reasons.append(f"L10 命中率 {leg['hit_l10']}% 極穩定")
        elif leg['hit_l10'] >= 60:
            leg_reasons.append(f"L10 命中率 {leg['hit_l10']}% 中等偏穩")
        else:
            leg_reasons.append(f"L10 命中率 {leg['hit_l10']}% 偏低，需留意")
        if isinstance(leg['cov'], (int, float)):
            if leg['cov'] <= 0.25:
                leg_reasons.append("CoV 極低 → 輸出穩定如機械")
            elif leg['cov'] <= 0.35:
                leg_reasons.append("CoV 中等 → 波動可控")
            else:
                leg_reasons.append(f"CoV {leg['cov']} 偏高 → 輸出時高時低")
        if leg['edge'] >= 15:
            leg_reasons.append(f"Edge {ev_str} 莊家顯著低估")
        elif leg['edge'] >= 5:
            leg_reasons.append(f"Edge {ev_str} 正值有利")
        elif leg['edge'] >= 0:
            leg_reasons.append(f"Edge {ev_str} 接近均衡")
        else:
            leg_reasons.append(f"Edge {ev_str} 莊家有利")
        if isinstance(leg.get('trend'), str) and '↑' in str(leg.get('trend', '')):
            leg_reasons.append("近期趨勢向上 ↑")
        lines.append(f"💡 **分析**: {' | '.join(leg_reasons)}")
        lines.append(f"🧠 **核心邏輯**: [FILL]")
        lines.append(f"")

    # Combo calculation
    odds_mult_parts = " × ".join(f"{leg['odds']}" for leg in legs)
    hit_mult_parts = " × ".join(f"{leg['hit_l10']}%" for leg in legs)

    # Auto-determine stake recommendation
    if combo_hit_pct >= 70 and avg_edge >= 5:
        stake = "💰💰💰 標準注 (2-3 units) — 高信心穩膽"
    elif combo_hit_pct >= 50 and avg_edge >= 0:
        stake = "💰💰 半注 (1-2 units) — 中等信心"
    elif combo_hit_pct >= 30:
        stake = "💰 試探注 (0.5-1 unit) — 高賠率投機"
    else:
        stake = "⚠️ 觀望 / 小額試探 — 命中率偏低"

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

    lines.append(f"**📊 組合結算:**")
    lines.append(f"- **賠率相乘**: {odds_mult_parts} = **@{raw_combo_odds}**")
    lines.append(f"- **$100 回報**: **${int(payout)}**")
    lines.append(f"- **組合命中率**: {hit_mult_parts} = **{combo_hit_pct}%**")
    lines.append(f"- **平均 Edge**: {'+' if avg_edge > 0 else ''}{avg_edge}%")
    lines.append(f"- **🛡️ 組合核心邏輯**: {core_logic}")
    lines.append(f"- **⚠️ 主要風險**: {' / '.join(risk_factors)}")
    lines.append(f"- **建議注碼**: {stake}")
    lines.append(f"")
    lines.append(f"> ⚠️ 以上賠率為獨立 Leg 相乘。實際 Bet365 SGM 價格可能因關聯性調整而不同，落注前請以 Bet365 顯示為準。")
    lines.append(f"")
    lines.append(f"---")
    return "\n".join(lines)


def gen_full_report(meta, odds, injuries, news, team_stats,
                    all_cards, bet365_time):
    sections = []

    away_abbr = meta.get("away", {}).get("abbr", "?")
    home_abbr = meta.get("home", {}).get("abbr", "?")
    away_name = meta.get("away", {}).get("name", "?")
    home_name = meta.get("home", {}).get("name", "?")

    # Header
    sections.append(f"# 🏀 NBA Wong Choi — {away_name} @ {home_name}")
    sections.append(f"**日期**: {meta.get('date', '?')} | **Bet365 提取時間**: {bet365_time}")
    sections.append(f"**odds_source**: BET365_LIVE ✅")
    sections.append(f"")

    # Meeting Intelligence
    sections.append(gen_meeting_intelligence(meta, odds, injuries, news, team_stats))
    sections.append(f"")

    # ── Auto-Combo (placed FIRST for quick reference) ──
    candidates = build_leg_candidates(all_cards, team_odds=odds, meta=meta, injuries=injuries)

    combo_1 = select_combo_1(candidates)
    
    used_descs = set(c["desc"] for c in combo_1)
    
    remaining = [c for c in candidates if c["desc"] not in used_descs]
    combo_2 = select_combo_2(remaining)
    used_descs |= set(c["desc"] for c in combo_2)
    
    remaining = [c for c in candidates if c["desc"] not in used_descs]
    combo_3 = select_combo_3(remaining)
    
    combo_x = select_combo_x_value_bomb(candidates)

    sections.append(f"## 🎰 SGM Parlay 組合 (Python Auto-Selection)")
    sections.append(f"")
    sections.append(f"> [!IMPORTANT]")
    sections.append(f"> 以下組合由 Python 自動從球員數據篩選並計算。所有數學數據不可修改。")
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 1: 穩膽 SGM (Low Risk)", "🛡️",
        "高命中率 + 組合賠率 >2x",
        combo_1))
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 2: 均衡 +EV 價值膽 (Mid Risk)", "🔥",
        "組合賠率 >3x, 目標 5x",
        combo_2))
    sections.append(f"")

    sections.append(gen_combo_section(
        "組合 3: 高倍率進取型", "💎",
        "3 Legs 高倍率組合",
        combo_3))
    sections.append(f"")

    if combo_x:
        sections.append(gen_combo_section(
            "組合 X: 💣 Value Bomb (莊家低估)", "💣",
            "顯著 +EV 機會 — 莊家明顯低估，Edge ≥10%+",
            combo_x))
        sections.append(f"")

    # Summary
    # Find strongest/weakest legs across all combos
    all_combo_legs = combo_1 + combo_2 + combo_3 + (combo_x or [])
    if all_combo_legs:
        best_leg = max(all_combo_legs, key=lambda x: x["edge"])
        worst_leg = min(all_combo_legs, key=lambda x: x["edge"])
        sections.append(f"- **最強關**: {best_leg['desc']} @{best_leg['odds']} — Edge {'+' if best_leg['edge'] > 0 else ''}{best_leg['edge']}% {best_leg['edge_grade']}")
        sections.append(f"- **最弱關**: {worst_leg['desc']} @{worst_leg['odds']} — Edge {'+' if worst_leg['edge'] > 0 else ''}{worst_leg['edge']}% {worst_leg['edge_grade']}")
    else:
        sections.append(f"- 最強關: 未能篩選")
        sections.append(f"- 最弱關: 未能篩選")
    sections.append(f"- **賽前 60 分鐘必查**: 傷病更新 / 首發陣容確認 / Bet365 盤口變動 / B2B 情況")
    sections.append(f"")
    sections.append(f"---")
    sections.append(f"")

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
    sections.append(f"> **Bet365 MCP Playwright** 即時提取 | 提取時間: {bet365_time}")
    sections.append(f"> 所有 Lines/Odds 來自 bet365.com.au DOM Snapshot")
    sections.append(f"> Bet365 線格式: \"10+\" = 10 分或以上 (≥10)")

    # Count remaining [FILL] slots
    full_text = "\n".join(sections)
    fill_count = full_text.count("[FILL")
    sections.append(f"")
    sections.append(f"## 📋 自檢")
    combo_count = sum(1 for c in [combo_1, combo_2, combo_3, combo_x] if c)
    sections.append(f"✅ Python 預填完成 | 組合數: {combo_count} | `[FILL]` 殘留: {fill_count} 個 (均為 Analyst 邏輯欄位)")

    return "\n".join(sections)


# ─── Main ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi V2 — Pre-filled Skeleton Generator")
    parser.add_argument("--bet365", required=True, help="Bet365 odds JSON (from bet365_parser.py)")
    parser.add_argument("--extractor", required=True, help="nba_extractor.py output JSON")
    parser.add_argument("--output", required=True, help="Output skeleton .md path")
    args = parser.parse_args()

    if not os.path.exists(args.bet365):
        print(f"❌ Bet365 JSON 唔存在: {args.bet365}")
        print(f"⚠️ odds_not_found — 請重新執行 MCP Playwright 提取")
        sys.exit(1)

    if not os.path.exists(args.extractor):
        print(f"❌ Extractor JSON 唔存在: {args.extractor}")
        sys.exit(1)

    with open(args.bet365, 'r', encoding='utf-8') as f:
        bet365 = json.load(f)
    with open(args.extractor, 'r', encoding='utf-8') as f:
        extractor = json.load(f)

    meta = extractor.get("meta", {})
    ex_odds = extractor.get("odds", {})
    injuries = extractor.get("injuries", {})
    news = extractor.get("news", {})
    team_stats = extractor.get("team_stats", {})
    ext_players = extractor.get("players", {})
    bet365_time = bet365.get("extraction_time", datetime.now().strftime("%Y-%m-%d %H:%M"))

    away_abbr = meta.get("away", {}).get("abbr", "?")
    home_abbr = meta.get("home", {}).get("abbr", "?")

    # Build all player cards
    all_cards = []
    player_props = bet365.get("player_props", {})

    for category, players in player_props.items():
        for player_name, bet_data in players.items():
            # Try both teams for extractor match
            ext_p = find_player_in_extractor(ext_players, player_name, away_abbr)
            team = away_abbr
            if ext_p is None:
                ext_p = find_player_in_extractor(ext_players, player_name, home_abbr)
                team = home_abbr
            if ext_p is None:
                team = "?"  # Unknown team - still add with Bet365 data only

            card = build_player_card(player_name, team, bet_data, ext_p, category)
            all_cards.append(card)

    # Summary
    cats = {}
    for c in all_cards:
        cats[c['category']] = cats.get(c['category'], 0) + 1
    cat_str = ", ".join(f"{k}: {v}" for k, v in cats.items())
    print(f"📊 已處理 {len(all_cards)} 個球員×盤口組合 ({cat_str})")

    # Generate report
    report = gen_full_report(meta, ex_odds, injuries, news, team_stats,
                             all_cards, bet365_time)

    # Write
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"✅ Pre-filled skeleton V2 已生成: {args.output}")
    print(f"   📎 下一步: NBA Analyst 填寫 [FILL] 邏輯欄位")


if __name__ == "__main__":
    main()
