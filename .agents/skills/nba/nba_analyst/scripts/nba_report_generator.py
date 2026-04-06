"""
nba_report_generator.py — NBA Template-Compliant Report Generator (V7.1)

Reads extracted JSON data package and generates a deterministic, template-compliant
report. ALL numerical and factual fields are filled from the verified JSON data.
Only genuinely subjective prose fields remain as [FILL_LLM].

Improvements in V7.1:
- Compute home/away splits from gamelog matchup strings
- Auto-compute situational adjustments from rules in 02_volatility_engine.md
- Fill defender data from team_dvp
- Compute rest days from gamelog dates
- Fill core logic, risk, and confidence from data patterns
- Better candidate selection (meaningful lines, not trivially low)

Usage:
  python nba_report_generator.py --input Game_1_TOR_BOS_data.json --output Game_1_TOR_BOS_Full_Analysis.txt
"""

import sys, io, json, math, argparse
from datetime import datetime, timedelta

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Bet365 Strict Lines
BET365_LINES = {
    "PTS": [4.5, 9.5, 14.5, 19.5, 24.5, 29.5, 34.5, 39.5, 44.5, 49.5],
    "REB": [2.5, 4.5, 6.5, 9.5, 12.5, 14.5, 16.5, 19.5],
    "AST": [2.5, 4.5, 6.5, 9.5, 12.5, 14.5],
    "FG3M": [0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5, 7.5],
}
CORE_STATS = ["PTS", "REB", "AST", "FG3M"]
SGM_DISCOUNT = {2: 0.65, 3: 0.60, 4: 0.55, 5: 0.50}
STAT_LABEL = {"PTS": "得分", "REB": "籃板", "AST": "助攻", "FG3M": "三分球", "STL": "偷球", "BLK": "蓋帽"}


def weighted_avg(arr):
    n = len(arr)
    if n == 0: return 0.0
    weights = [0.5 + (1.0 * i / max(n - 1, 1)) for i in range(n)]
    return round(sum(d * w for d, w in zip(arr, weights)) / sum(weights), 2)


def trend_label(arr):
    if len(arr) < 5: return "— 持平"
    l3 = sum(arr[-3:]) / 3
    l10 = sum(arr) / len(arr)
    diff = (l3 - l10) / l10 * 100 if l10 != 0 else 0
    if diff > 5: return "📈 上升"
    elif diff < -5: return "📉 下降"
    return "— 持平"


def edge_rating(edge):
    if edge > 15: return "💎 核心高價值"
    elif edge > 10: return "✅ 有價值"
    elif edge > 5: return "➖ 邊緣"
    return "❌ 不推薦"


def compute_home_away_splits(gamelog, stat):
    """Compute home/away averages from L10 gamelog matchup strings."""
    matchups = gamelog.get("l10_matchups", [])
    raw = gamelog.get(stat, [])
    if not matchups or not raw or len(matchups) != len(raw):
        return {"home_avg": 0, "away_avg": 0, "home_games": 0, "away_games": 0}
    home_vals = [raw[i] for i, m in enumerate(matchups) if "vs." in m]
    away_vals = [raw[i] for i, m in enumerate(matchups) if "@" in m]
    return {
        "home_avg": round(sum(home_vals) / len(home_vals), 1) if home_vals else 0,
        "away_avg": round(sum(away_vals) / len(away_vals), 1) if away_vals else 0,
        "home_games": len(home_vals),
        "away_games": len(away_vals),
    }


def compute_rest_days(gamelog):
    """Estimate rest days from L10 dates."""
    dates = gamelog.get("l10_dates", [])
    if not dates or len(dates) < 2:
        return "N/A"
    try:
        from datetime import datetime as dt
        latest = dt.strptime(dates[0], "%b %d, %Y")
        prev = dt.strptime(dates[1], "%b %d, %Y")
        delta = (latest - prev).days - 1  # rest days between last 2 games
        if delta <= 0:
            return "0 天 (B2B ⚠️)"
        elif delta == 1:
            return "1 天"
        elif delta == 2:
            return "2 天"
        else:
            return f"{delta} 天 (充分休息 ✅)"
    except:
        return "N/A"


def compute_minutes_stability(gamelog):
    """Check if minutes are stable from L10 MIN data."""
    mins = gamelog.get("MIN", [])
    if not mins or len(mins) < 5:
        return {"avg": 0, "stable": True, "warning": ""}
    avg_min = round(sum(mins) / len(mins), 1)
    min_min = min(mins)
    max_min = max(mins)
    spread = max_min - min_min
    warning = ""
    if spread > 10:
        warning = f"⚠️ 上場時間波動大 ({min_min}-{max_min} min)"
    if avg_min < 20:
        warning = f"⚠️ 上場時間不足 (L10: {avg_min} min)"
    return {"avg": avg_min, "stable": spread <= 10, "warning": warning}


def compute_situational_adjustments(leg, is_home, opp_def_rank, opp_pace, own_pace, rest_days_str, gamelog):
    """Auto-compute situational adjustments per volatility engine rules."""
    adjustments = []
    total = 0.0
    raw = leg["raw"]
    avg = leg["avg"]
    cov = leg["cov"]
    l3_avg = leg.get("l3_avg", avg)
    
    # CoV adjustment
    if cov < 0.20:
        adjustments.append(("CoV 極度穩定紅利", +1.0))
        total += 1.0
    elif cov > 0.40:
        adjustments.append(("CoV 神經刀懲罰", -1.5))
        total -= 1.5
    
    # L3 trend
    if avg > 0:
        if l3_avg < avg * 0.85:
            adjustments.append(("L3 低潮 (近期狀態下滑)", -2.0))
            total -= 2.0
        elif l3_avg > avg * 1.15:
            adjustments.append(("L3 爆發 (近期狀態火熱)", +1.0))
            total += 1.0
    
    # Opponent defense
    try:
        rank = int(opp_def_rank)
        if rank <= 5:
            adjustments.append((f"對手防守 Top {rank} (整體壓制)", -1.0))
            total -= 1.0
        elif rank >= 26:
            adjustments.append((f"對手防守 Bottom {31 - rank} (整體放水)", +1.0))
            total += 1.0
    except (ValueError, TypeError):
        pass
    
    # Pace adjustment
    try:
        p_opp = float(opp_pace)
        p_own = float(own_pace)
        league_avg = 100.0
        if p_opp > p_own + 3:
            adjustments.append(("Pace-Up (慢遇快)", +1.0))
            total += 1.0
        elif p_opp < p_own - 3:
            adjustments.append(("Pace-Down (快遇慢)", -1.0))
            total -= 1.0
    except (ValueError, TypeError):
        pass
    
    # Home/Away
    if not is_home:
        pass  # No automatic penalty for away, but check B2B
    
    # Rest days
    if "B2B" in rest_days_str:
        adjustments.append(("B2B 疲勞", -2.5))
        total -= 2.5
    elif "充分休息" in rest_days_str:
        adjustments.append(("充分休息紅利", +1.0))
        total += 1.0
    
    # Minutes stability
    mins = gamelog.get("MIN", [])
    if mins:
        avg_min = sum(mins) / len(mins)
        if avg_min < 28:
            adjustments.append((f"上場時間偏低 ({avg_min:.0f}min)", -1.5))
            total -= 1.5
    
    return adjustments, round(total, 1)


def generate_core_logic(leg, is_home, ha_splits, rest_str, team_stats):
    """Auto-generate core logic text from data patterns."""
    bl = leg["best_bet365"]
    raw = leg["raw"]
    stat = leg["stat"]
    line = bl["line"]
    hit = bl["hit_rate_L10"]
    name = leg["name"]
    
    parts = []
    
    # Hit rate narrative
    if hit == 100:
        parts.append(f"{name} 近 10 場 100% 達標（{bl['hits']}），穩定性極高。")
    elif hit >= 90:
        parts.append(f"{name} 近 10 場 {hit}% 達標（{bl['hits']}），僅 1 場未過線。")
    elif hit >= 80:
        miss_count = 10 - int(bl["hits"].split("/")[0])
        parts.append(f"{name} 近 10 場 {hit}% 達標（{bl['hits']}），有 {miss_count} 場未過線但整體穩健。")
    else:
        parts.append(f"{name} 近 10 場 {hit}% 達標（{bl['hits']}）。")
    
    # Average vs line
    surplus = round(leg["avg"] - line, 1)
    if surplus > 0:
        parts.append(f"L10 均值 {leg['avg']} 高於盤口 {line} 達 {surplus}，存在顯著緩衝空間。")
    
    # Home/away context
    if is_home and ha_splits["home_avg"] > 0:
        parts.append(f"今場主場作戰，L10 主場{STAT_LABEL.get(stat, stat)}均值 {ha_splits['home_avg']}。")
    elif not is_home and ha_splits["away_avg"] > 0:
        parts.append(f"今場客場作戰，L10 客場{STAT_LABEL.get(stat, stat)}均值 {ha_splits['away_avg']}。")
    
    # USG context for PTS
    if stat == "PTS" and leg["usg"] > 25:
        parts.append(f"USG% 高達 {leg['usg']}，作為球隊核心進攻箭頭，得分產量有強力保障。")
    elif stat == "AST" and leg["usg"] > 20:
        parts.append(f"組織核心角色穩固，球權使用率 {leg['usg']}%，助攻輸出有系統性保障。")
    elif stat == "REB":
        parts.append(f"籃板搶奪能力穩定，L10 均值 {leg['avg']}，場場有穩定產出。")
    
    return " ".join(parts)


def generate_risk_text(leg, ha_splits, is_home):
    """Auto-generate risk assessment."""
    bl = leg["best_bet365"]
    raw = leg["raw"]
    stat = leg["stat"]
    cov = leg["cov"]
    
    risks = []
    if cov > 0.35:
        risks.append(f"波動性偏高 (CoV={cov})，表現容易大起大落")
    
    # Check for recent dip
    if leg["l3_avg"] < leg["avg"] * 0.85:
        risks.append(f"近 3 場走勢下滑 (L3: {leg['l3_avg']} vs L10: {leg['avg']})")
    
    if stat == "PTS":
        risks.append("對手若實施聯防/包夾策略，出手權可能被壓縮")
    elif stat == "AST":
        risks.append("隊友手感極度冰冷，傳球無法轉為助攻")
    elif stat == "REB":
        risks.append("犯規麻煩導致上場時間大幅縮減")
    elif stat == "FG3M":
        risks.append("外線手感冰冷，三分命中率下滑")
    
    if not is_home:
        risks.append("客場作戰可能受場地適應影響")
    
    return "；".join(risks) if risks else "無顯著風險"


def generate_confidence_text(leg, bl):
    """Auto-generate confidence text."""
    hit = bl["hit_rate_L10"]
    edge = bl.get("edge", 0)
    cov = leg["cov"]
    
    if hit >= 90 and edge > 20 and cov < 0.30:
        return f"極高。命中率 {hit}%、Edge {edge}%、波動極低 (CoV={cov})，三重保護。"
    elif hit >= 80 and edge > 10:
        return f"高。命中率 {hit}% + Edge {edge}%，數據面強力支撐。"
    elif hit >= 70:
        return f"中高。命中率 {hit}%，但需留意波動性 (CoV={cov})。"
    else:
        return f"中等。命中率 {hit}% 偏低，需要配合情境因素判斷。"


def find_best_bet365_line(bet365_lines, direction="Over", min_hit_l10=70):
    candidates = [bl for bl in bet365_lines if bl["direction"] == direction and bl.get("hit_rate_L10", 0) >= min_hit_l10]
    if not candidates: return None
    if direction == "Over":
        candidates.sort(key=lambda x: x["line"], reverse=True)
    else:
        candidates.sort(key=lambda x: x["line"])
    return candidates[0]


def select_candidate_legs(players_data, min_usg=10):
    candidates = []
    for team, players in players_data.items():
        for p in players:
            name = p.get("name", "")
            status = p.get("status", "Active")
            if status and status.lower() in ["out"]: continue
            adv = p.get("advanced", {}) or {}
            usg = adv.get("USG_PCT", 0)
            ts = adv.get("TS_PCT", 0)
            if usg < min_usg: continue
            
            prop_analytics = p.get("prop_analytics", {})
            if not isinstance(prop_analytics, dict): continue
            gamelog = p.get("gamelog", {}) or {}
            
            for stat in CORE_STATS:
                pa = prop_analytics.get(stat)
                if not pa or not isinstance(pa, dict): continue
                raw = pa.get("raw", [])
                if len(raw) < 5: continue
                bet365_lines = pa.get("bet365_lines", [])
                if not bet365_lines: continue
                
                banker = find_best_bet365_line(bet365_lines, "Over", 80)
                value = find_best_bet365_line(bet365_lines, "Over", 70)
                if not banker and not value: continue
                best = banker or value
                
                # Skip trivially low lines for starters
                avg = pa.get("avg", 0)
                if stat == "PTS" and best["line"] < 9.5 and avg > 15: continue
                if stat == "REB" and best["line"] < 2.5 and avg > 5: continue
                if stat == "AST" and best["line"] < 2.5 and avg > 5: continue
                
                candidates.append({
                    "name": name, "team": team, "status": status, "stat": stat,
                    "raw": raw, "avg": pa.get("avg", 0), "med": pa.get("med", 0),
                    "sd": pa.get("sd", 0), "cov": pa.get("cov", 0),
                    "cov_label": pa.get("cov_label", ""), "l5_avg": pa.get("l5_avg", 0),
                    "l3_avg": pa.get("l3_avg", 0), "banker_line": pa.get("banker_line", 0),
                    "value_line": pa.get("value_line", 0), "pace_adj": pa.get("pace_adj", 0),
                    "pace_projected": pa.get("pace_projected", 0),
                    "location": pa.get("location", ""), "location_avg": pa.get("location_avg", 0),
                    "usg": usg, "ts": ts, "advanced": adv,
                    "banker_bet365": banker, "value_bet365": value, "best_bet365": best,
                    "bet365_lines": bet365_lines, "all_player_data": p, "gamelog": gamelog,
                })
    
    for c in candidates:
        best = c["best_bet365"]
        score = best.get("hit_rate_L10", 0) * 0.5 + best.get("edge", 0) * 0.3 + c["usg"] * 0.1
        if c["cov"] < 0.25: score += 5
        if c["cov"] > 0.40: score -= 5
        c["score"] = score
    
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates


def format_leg_block(leg, leg_num, game_data):
    """Generate a FULLY filled leg analysis block."""
    bl = leg["best_bet365"]
    raw = leg["raw"]
    adv = leg.get("advanced", {})
    player_data = leg.get("all_player_data", {})
    gamelog = leg.get("gamelog", {}) or {}
    meta = game_data.get("meta", {})
    team_stats = game_data.get("team_stats", {})
    team_dvp = game_data.get("team_dvp", {})
    
    # Determine opponent
    away_abbr = meta.get("away", {}).get("abbr", "?")
    home_abbr = meta.get("home", {}).get("abbr", "?")
    is_home = leg["team"] == home_abbr
    opp_abbr = away_abbr if is_home else home_abbr
    own_abbr = leg["team"]
    
    opp_stats = team_stats.get(opp_abbr, {})
    own_stats = team_stats.get(own_abbr, {})
    opp_dvp = team_dvp.get(opp_abbr, {})
    
    # Hit rates
    hit_l10 = bl.get("hit_rate_L10", 0)
    hit_l5 = bl.get("hit_rate_L5", 0)
    hit_l3 = bl.get("hit_rate_L3", 0)
    implied = bl.get("implied_prob", 52.6)
    estimated = bl.get("estimated_prob", hit_l10)
    edge = bl.get("edge", 0)
    # Use est_odds from the data (dynamic model), fallback to computing from implied_prob
    odds_est = bl.get("est_odds", round(100 / implied, 2) if implied > 0 else 1.90)
    
    # Miss analysis
    line_val = bl.get("line", 0)
    misses = []
    matchups = gamelog.get("l10_matchups", [])
    for i, v in enumerate(raw):
        if v <= line_val:
            opp = matchups[i] if i < len(matchups) else f"Game {i+1}"
            misses.append(f"Game {i+1} ({opp}): {v} (差距: {round(v - line_val, 1)})")
    miss_text = " | ".join(misses) if misses else "全部達標 ✅"
    
    w_avg = weighted_avg(raw)
    trend = trend_label(raw)
    conf_score = min(10, max(1, round(hit_l10 / 10 - (leg["cov"] * 5) + (edge / 10), 1)))
    pace_proj = leg.get("pace_projected", leg["avg"])
    
    # Home/Away splits from gamelog
    ha_splits = compute_home_away_splits(gamelog, leg["stat"])
    location_label = "主場 (Home)" if is_home else "客場 (Road)"
    home_ppg = ha_splits["home_avg"]
    road_ppg = ha_splits["away_avg"]
    
    # Rest days
    rest_str = compute_rest_days(gamelog)
    
    # Minutes
    min_info = compute_minutes_stability(gamelog)
    
    # H2H
    h2h = player_data.get("h2h")
    h2h_text = "N/A (數據不足)"
    h2h_trend = "中性"
    if h2h and isinstance(h2h, dict):
        h2h_text = f"{h2h.get('total_games', 0)} 場 | PTS AVG: {h2h.get('PTS_avg', 0)}"
        if h2h.get("PTS_avg", 0) > leg["avg"] * 1.15:
            h2h_trend = "📈 H2H 加成 (+1)"
        elif h2h.get("PTS_avg", 0) < leg["avg"] * 0.85:
            h2h_trend = "📉 H2H 減持 (-1)"
    
    # Defensive matchup from team DVP
    opp_dfg = opp_dvp.get("D_FG_PCT", "N/A")
    opp_pctpm = opp_dvp.get("PCT_PLUSMINUS", "N/A")
    if isinstance(opp_dfg, float): opp_dfg = f"{opp_dfg:.1%}"
    if isinstance(opp_pctpm, float): opp_pctpm = f"{opp_pctpm:+.1%}"
    
    opp_def_rank = opp_stats.get("DEF_RANK", "?")
    opp_def_label = f"第{opp_def_rank}" if opp_def_rank != "?" else "N/A"
    
    # Scoring type inference
    if leg["stat"] == "PTS":
        scoring_type = "混合型" if leg.get("ts", 0) > 55 else "投射型"
    elif leg["stat"] == "FG3M":
        scoring_type = "投射型"
    else:
        scoring_type = "N/A (非得分指標)"
    
    # Situational adjustments
    adjustments, adj_total = compute_situational_adjustments(
        leg, is_home, opp_def_rank,
        opp_stats.get("PACE", 100), own_stats.get("PACE", 100),
        rest_str, gamelog
    )
    adj_lines = [f"  - {desc}: {val:+.1f}" for desc, val in adjustments]
    adj_text = "\n".join(adj_lines) if adj_lines else "  - 無顯著調整項"
    adj_projected = round(leg["avg"] + adj_total, 1)
    
    # Core logic, risk, confidence — auto-generated from data
    core_logic = generate_core_logic(leg, is_home, ha_splits, rest_str, team_stats)
    risk_text = generate_risk_text(leg, ha_splits, is_home)
    confidence_text = generate_confidence_text(leg, bl)
    
    # Defender — use team-level DVP data
    key_defenders = game_data.get("key_defenders", {}).get(opp_abbr, [])
    if key_defenders and isinstance(key_defenders, list) and len(key_defenders) > 0:
        top_def = key_defenders[0]
        def_name = top_def.get("name", top_def.get("PLAYER_NAME", "N/A"))
        def_dfg = top_def.get("D_FG_PCT", "N/A")
        def_pctpm = top_def.get("PCT_PLUSMINUS", "N/A")
        if isinstance(def_dfg, float): def_dfg = f"{def_dfg:.1%}"
        if isinstance(def_pctpm, float): def_pctpm = f"{def_pctpm:+.1%}"
    else:
        def_name = f"{opp_abbr} 整隊防守"
        def_dfg = opp_dfg
        def_pctpm = opp_pctpm
    
    # Defense pressure assessment
    try:
        pctpm_val = float(opp_dvp.get("PCT_PLUSMINUS", 0))
        if pctpm_val < -0.04:
            def_assess = f"🔒 精英防守壓制 ({opp_abbr} 防守效率{opp_def_label})"
        elif pctpm_val < -0.01:
            def_assess = f"中等防守壓力 ({opp_abbr} 防守效率{opp_def_label})"
        else:
            def_assess = f"防守壓力偏低 ({opp_abbr} 防守效率{opp_def_label}，有利進攻)"
    except:
        def_assess = f"{opp_abbr} 防守效率{opp_def_label}"
    
    min_warning = f" | {min_info['warning']}" if min_info["warning"] else ""
    
    block = f"""#### 🧩 Leg {leg_num}: {leg["name"]} ({leg["team"]}) — {leg["stat"]} Over {bl["line"]}+

| 🔢 數理引擎 | 🧠 邏輯引擎 |
|:---|:---|
| 賠率：~{odds_est} | 核心邏輯：{core_logic} |
| 命中率：L10={hit_l10}% L5={hit_l5}% L3={hit_l3}% | ⚠️ 最大不達標風險：{risk_text} |
| 信心分：{conf_score}/10 | 💪 克服風險信心度：{confidence_text} |

**+EV 篩選：**
- 隱含勝率={implied}% | 預估勝率={estimated}% | Edge={edge}%
- Edge 評級：{edge_rating(edge)}

**📊 數據卡：**
- L10 逐場：{raw}
- 未達標場次剖析：{miss_text}
- L10 均值：{leg["avg"]} | 中位數：{leg["med"]} | SD：{leg["sd"]} | CoV：{leg["cov"]} → 分級：{leg["cov_label"]}
- Weighted AVG：{w_avg} | 趨勢：{trend}{min_warning}

**📊 進階數據：**
- USG%：{leg["usg"]} | TS%：{leg["ts"]}
- Pace-Adjusted Projection：{pace_proj}

**🛡️ 防守對位：**
- 對位防守者：{def_name} | D_FG%：{def_dfg} | PCT_PLUSMINUS：{def_pctpm}
- 壓制評估：{def_assess}
- 得分類型：{scoring_type}

**📍 場景分裂：**
- 今日：{location_label} | Home {STAT_LABEL.get(leg["stat"], leg["stat"])} AVG：{home_ppg} ({ha_splits["home_games"]}場) | Road {STAT_LABEL.get(leg["stat"], leg["stat"])} AVG：{road_ppg} ({ha_splits["away_games"]}場)
- 休息日數：{rest_str}
- H2H 歷史：{h2h_text}
- H2H 趨勢：{h2h_trend}

**🧮 情境調整值：**
{adj_text}
- 總調整值：{adj_total:+.1f}
- 調整後預期值：{adj_projected} (AVG {leg["avg"]} {adj_total:+.1f})
"""
    return block


def build_combo_analysis(legs, combo_label):
    n = len(legs)
    # Use est_odds from data (dynamic model based on line/avg ratio)
    odds_list = []
    for l in legs:
        bl = l["best_bet365"]
        o = bl.get("est_odds", round(100 / bl.get("implied_prob", 52.6), 2) if bl.get("implied_prob", 0) > 0 else 1.90)
        odds_list.append(o)
    
    raw_mult = round(math.prod(odds_list), 2)
    disc = SGM_DISCOUNT.get(n, 0.60)
    final = round(raw_mult * disc, 2)
    hits = [l["best_bet365"].get("hit_rate_L10", 0) for l in legs]
    combo_hit = round(math.prod(h/100 for h in hits) * 100, 1)
    
    # Per-leg odds breakdown
    leg_details = []
    for i, (l, o) in enumerate(zip(legs, odds_list), 1):
        leg_details.append(f"Leg {i} ({l['name']} {l['stat']} O{l['best_bet365']['line']}): @{o}")
    leg_breakdown = "\n".join(f"  - {d}" for d in leg_details)
    
    odds_calc = " × ".join(str(o) for o in odds_list) + f" = {raw_mult}"
    hit_calc = " × ".join(f"{h}%" for h in hits) + f" = {combo_hit}%"
    
    combo_edge = round(combo_hit - (100/final), 1) if final > 0 else 0
    conf = min(10, max(1, round(combo_hit / 10 - 1, 1)))
    
    main_risk = "高波動球員表現不穩" if any(l["cov"] > 0.35 for l in legs) else "球員同時遭遇上場時間縮減"
    
    # Suggested bet sizing based on confidence
    if conf >= 8:
        bet_size = "💰 標準注 (2-3 units)"
    elif conf >= 6:
        bet_size = "💰 半注 (1-2 units)"
    else:
        bet_size = "💰 試探注 (0.5-1 unit)"
    
    return f"""#### 📊 組合 {combo_label} 分析
**各 Leg 賠率：**
{leg_breakdown}
- 原始組合賠率：{odds_calc}
- SGM 折扣後賠率：{raw_mult} × {disc} = **@{final}**
- 💵 $100 投注回報：**${round(final * 100)}**
- 組合命中率：{hit_calc}
- 組合信心分：{conf}/10
- +EV 評估：組合 Edge={combo_edge}%
- 建議注碼：{bet_size}
- ⚠️ 主要風險：{main_risk}
"""


def pick_legs(pool, n, exclude_keys=None):
    if exclude_keys is None: exclude_keys = set()
    picked, used = [], set()
    for c in pool:
        key = f"{c['name']}_{c['stat']}"
        if key in exclude_keys or c['name'] in used: continue
        picked.append(c)
        used.add(c['name'])
        if len(picked) >= n: break
    return picked


def generate_report(data, top_n=8):
    meta = data.get("meta", {})
    away = meta.get("away", {})
    home = meta.get("home", {})
    odds = data.get("odds", {})
    news = data.get("news", {})
    players_data = data.get("players", {})
    team_stats = data.get("team_stats", {})
    
    away_abbr, home_abbr = away.get("abbr", "?"), home.get("abbr", "?")
    away_name, home_name = away.get("name", "?"), home.get("name", "?")
    
    spread = odds.get("spread_away", "N/A")
    total = odds.get("total", "N/A")
    standings = odds.get("standings", {})
    
    away_stats = team_stats.get(away_abbr, {})
    home_stats = team_stats.get(home_abbr, {})
    
    try:
        pace_avg = (float(away_stats.get("PACE", 100)) + float(home_stats.get("PACE", 100))) / 2
        pace_label = "高" if pace_avg > 102 else ("低" if pace_avg < 98 else "中")
    except: pace_label = "中"
    
    # B2B detection from gamelog dates
    b2b_teams = []
    for team_abbr, team_players in players_data.items():
        for p in team_players:
            gl = p.get("gamelog", {})
            if gl:
                rest = compute_rest_days(gl)
                if "B2B" in rest:
                    b2b_teams.append(team_abbr)
                break
    b2b_tag = f"⚠️ {', '.join(set(b2b_teams))} B2B" if b2b_teams else "無 B2B"
    
    # Blowout risk
    blowout_warn = ""
    try:
        s = float(spread)
        if abs(s) >= 8.5:
            blowout_warn = f"\n- ⚠️ **BLOWOUT RISK 大炒高危**：讓分 {spread}，主力上場時間可能縮減！"
    except: pass
    
    # Injuries
    injuries_data = data.get("injuries", {})
    injury_lines = []
    for team_abbr in [away_abbr, home_abbr]:
        team_inj = injuries_data.get(team_abbr, {})
        for name, status in team_inj.items():
            if status and status.lower() not in ["active", "none", ""]:
                injury_lines.append(f"- {name} ({team_abbr}) — {status}")
                
    injury_text = "\n".join(injury_lines) if injury_lines else "- 無重大傷病"
    
    # Rosters
    roster_lines = []
    for team_abbr, team_players in players_data.items():
        active = [p["name"] for p in team_players if not p.get("status") or p.get("status", "").lower() in ["active", "none", ""]]
        roster_lines.append(f"- {team_abbr}: {', '.join(active[:8])}")
    
    # News
    news_lines = []
    for team_abbr, team_news in news.items():
        if isinstance(team_news, list):
            for n_item in team_news[:3]:
                hl = n_item.get("headline", "") if isinstance(n_item, dict) else str(n_item)
                news_lines.append(f"- [{team_abbr}] {hl}")
    news_text = "\n".join(news_lines) if news_lines else "- 無重大新聞"
    
    # Defenders
    key_defenders = data.get("key_defenders", {})
    def_lines = []
    team_dvp = data.get("team_dvp", {})
    for team_abbr in [away_abbr, home_abbr]:
        defs = key_defenders.get(team_abbr, [])
        dvp = team_dvp.get(team_abbr, {})
        if defs and isinstance(defs, list):
            for d in defs[:2]:
                dname = d.get("name", d.get("PLAYER_NAME", "?"))
                dfg = d.get("D_FG_PCT", "?")
                pctpm = d.get("PCT_PLUSMINUS", "?")
                if isinstance(dfg, float): dfg = f"{dfg:.1%}"
                if isinstance(pctpm, float): pctpm = f"{pctpm:+.1%}"
                def_lines.append(f"- {team_abbr}: {dname} — D_FG%: {dfg} | PCT_PM: {pctpm}")
        elif dvp:
            dfg = dvp.get("D_FG_PCT", "?")
            pctpm = dvp.get("PCT_PLUSMINUS", "?")
            if isinstance(dfg, float): dfg = f"{dfg:.1%}"
            if isinstance(pctpm, float): pctpm = f"{pctpm:+.1%}"
            def_lines.append(f"- {team_abbr} 整隊: D_FG%: {dfg} | PCT_PM: {pctpm}")
    def_text = "\n".join(def_lines) if def_lines else "- 數據不足"
    
    # Select candidates
    candidates = select_candidate_legs(players_data, min_usg=10)
    if len(candidates) < 2:
        return f"⛔ {away_name} @ {home_name} 今場建議觀望\n理由：合格 Legs 不足 ({len(candidates)} 個)\n"
    
    seen = set()
    unique = []
    for c in candidates:
        key = f"{c['name']}_{c['stat']}"
        if key not in seen:
            seen.add(key)
            unique.append(c)
    
    # Build combos
    c1a_pool = sorted(unique, key=lambda x: (x["best_bet365"]["hit_rate_L10"], -x["cov"]), reverse=True)
    c1a = pick_legs(c1a_pool, 2)
    
    c1b = []
    for leg in c1a:
        vbl = find_best_bet365_line(leg["bet365_lines"], "Over", 70)
        if vbl and vbl["line"] > leg["best_bet365"]["line"]:
            nl = dict(leg); nl["best_bet365"] = vbl; c1b.append(nl)
        else: c1b.append(leg)
    
    used_1a = {f"{l['name']}_{l['stat']}" for l in c1a}
    c2_pool = sorted(unique, key=lambda x: (x["best_bet365"]["edge"], x["best_bet365"]["hit_rate_L10"]), reverse=True)
    c2 = pick_legs(c2_pool, 2, used_1a)
    if len(c2) < 2: c2 = pick_legs(c2_pool, 2)
    
    c3_pool = sorted(unique, key=lambda x: x["best_bet365"]["edge"], reverse=True)
    c3 = pick_legs(c3_pool, 3)
    
    # Build report
    L = []
    L.append(f"🎫 職業大戶 God Mode 單場分析 — {away_name} vs {home_name}")
    L.append(f"\n📅 數據鎖定：{meta.get('extracted_at', 'N/A')[:10]} | NBA 賽季：2025-26\n")
    L.append(f"---\n")
    L.append(f"### 🏀 賽事背景")
    L.append(f"- 讓分：{spread} | 總分盤：O/U {total} | 節奏：{pace_label} | B2B：{b2b_tag}")
    L.append(f"- {away_abbr} PACE: {away_stats.get('PACE', '?')} DEF: 第{away_stats.get('DEF_RANK', '?')} | {home_abbr} PACE: {home_stats.get('PACE', '?')} DEF: 第{home_stats.get('DEF_RANK', '?')}")
    L.append(f"- 戰績：{away_abbr} {standings.get(away_abbr, 'N/A')} | {home_abbr} {standings.get(home_abbr, 'N/A')}{blowout_warn}\n")
    L.append(f"### 📋 傷病與隱蔽缺陣剔除/變動名單\n{injury_text}\n")
    L.append(f"### ✅ 雙方預計上陣陣容\n" + "\n".join(roster_lines) + "\n")
    L.append(f"### 🛡️ 關鍵防禦大閘狀態\n{def_text}\n")
    L.append(f"### 📰 新聞情境摘要 (NEWS_DIGEST)\n{news_text}\n")
    L.append(f"---\n\n## 🏆 推薦單場 SGM 組合\n")
    
    combos = [("1A", "🛡️ 穩膽組合（極限防斷保本路線）", c1a),
              ("1B", "🔥 高水位正盤膽（+EV 獲利路線，基於 1A 延伸）", c1b),
              ("2", "🔥 均衡 +EV 價值膽（主力正盤與對位弱點針對）", c2),
              ("3", "💎 價值型小博大（高倍率進取型）", c3)]
    
    for label, title, legs in combos:
        if not legs: continue
        
        # Calculate final odds for header
        odds_list = []
        for l in legs:
            bl = l["best_bet365"]
            o = bl.get("est_odds", round(100 / bl.get("implied_prob", 52.6), 2) if bl.get("implied_prob", 0) > 0 else 1.90)
            odds_list.append(o)
        raw_mult = round(math.prod(odds_list), 2)
        disc = SGM_DISCOUNT.get(len(legs), 0.60)
        final_odds = round(raw_mult * disc, 2)
        
        L.append(f"---\n\n### 組合 {label}：{title}— 組合賠率：~@{final_odds}\n")
        for i, leg in enumerate(legs, 1):
            L.append(format_leg_block(leg, i, data))
            L.append(f"---\n")
        L.append(build_combo_analysis(legs, label))
        if label == "1B":
            L.append(f"- vs 1A 對比：1B 將部分盤口提升至價值線，賠率更高但命中率略降\n")
    
    # Summary
    L.append(f"---\n\n### 🧠 總結與賽前必做")
    if c1a:
        L.append(f"- 最強關：Leg 1（{c1a[0]['name']} {c1a[0]['stat']}）— 命中率 {c1a[0]['best_bet365']['hit_rate_L10']}%，穩定性最高")
        w = c1a[-1] if len(c1a) > 1 else c1a[0]
        L.append(f"- 最弱關：Leg {len(c1a)}（{w['name']} {w['stat']}）— CoV {w['cov']}，波動性最高")
    L.append(f"- 賽前 60 分鐘必查：確認傷病名單更新、盤口走勢變動、先發陣容公佈\n")
    
    # Self-check
    L.append(f"---\n\n### 📋 批次完成自檢")
    combo_count = sum(1 for _, _, legs in combos if legs)
    total_legs = sum(len(legs) for _, _, legs in combos if legs)
    report_text = "\n".join(L)
    fill_count = report_text.count("[FILL_LLM")
    L.append(f"✅ 單場完成：{combo_count} 組組合 (1A/1B/2/3) | {total_legs} 支 Legs")
    L.append(f"每支 Leg 含 數理引擎+邏輯引擎+EV篩選+數據卡+進階數據+防守對位+場景分裂+情境調整 全 8 大區塊")
    L.append(f"[FILL_LLM] 殘留數 = {fill_count}\n")
    
    return "\n".join(L)


def main():
    parser = argparse.ArgumentParser(description="NBA Report Generator V7.1")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", help="Output report file")
    parser.add_argument("--top-n", type=int, default=8)
    args = parser.parse_args()
    
    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    report = generate_report(data, top_n=args.top_n)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"✅ Report written to: {args.output}")
        print(f"   Total lines: {len(report.splitlines())}")
        print(f"   [FILL_LLM] placeholders: {report.count('[FILL_LLM')}")
    else:
        print(report)


if __name__ == "__main__":
    main()
