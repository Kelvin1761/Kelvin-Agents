#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
compute_nba_props.py — NBA Wong Choi Protocol Volatility & Props Calculator
Mechanically computes CoV, situational adjustments, bet lines, +EV, and Over downside risk.

Usage:
    python compute_nba_props.py --input <players.json> [--output <results.md>]

Input JSON format:
{
    "game_context": {
        "game_id": "LAL_vs_BOS",
        "player_team": "LAL",
        "opponent": "BOS",
        "is_home": true,
        "rest_days": 2,
        "opp_pace": 100.2,
        "league_avg_pace": 99.5,
        "opp_def_rating": 108.5,
        "opp_def_rank": 8,
        "spread": -5.5,
        "is_b2b": false,
        "is_3in4": false
    },
    "players": [
        {
            "name": "LeBron James",
            "prop_type": "points",
            "l10": [28, 32, 25, 30, 22, 35, 28, 31, 26, 29],
            "home_ppg": 28.5,
            "away_ppg": 25.3,
            "rest_split": 27.8,
            "usg_pct": 31.2,
            "ts_pct": 58.5,
            "defender_name": "Jaylen Brown",
            "defender_dfg_pct": 45.2,
            "defender_pct_pm": -0.02,
            "h2h_data": [30, 28, 35],
            "odds_over": 1.90,
            "odds_under": 1.90,
            "book_line": 27.5,
            "situational": {
                "teammate_out_usage_boost": false,
                "negative_news": false,
                "positive_news": false,
                "sharp_money_over": false,
                "vegas_trap": false,
                "opp_center_monster": false,
                "opp_rebounder_out": false
            }
        }
    ]
}
"""
import json, sys, math, argparse
from pathlib import Path


# ── Step 2: Volatility Calculations ──────────────

def compute_volatility(l10: list) -> dict:
    """Compute AVG, MED, SD, CoV, Weighted AVG from L10 data."""
    n = len(l10)
    if n == 0:
        return {'avg': 0, 'med': 0, 'sd': 0, 'cov': 0, 'weighted_avg': 0, 'cov_grade': '❌'}

    avg = sum(l10) / n
    sorted_l10 = sorted(l10)
    med = (sorted_l10[n//2 - 1] + sorted_l10[n//2]) / 2 if n % 2 == 0 else sorted_l10[n//2]
    variance = sum((x - avg) ** 2 for x in l10) / n
    sd = math.sqrt(variance)
    cov = sd / avg if avg > 0 else 0

    # L3 weighted average
    weights_l3 = 1.5
    weights_l47 = 1.0
    weights_l810 = 0.7
    weighted_sum = 0
    weight_total = 0
    for i, val in enumerate(l10):
        if i < 3:
            w = weights_l3
        elif i < 7:
            w = weights_l47
        else:
            w = weights_l810
        weighted_sum += val * w
        weight_total += w
    weighted_avg = weighted_sum / weight_total if weight_total > 0 else avg

    # CoV grade
    if cov < 0.15:
        cov_grade = '🛡️ 極度穩定'
        cov_tier = 'banker'
    elif cov < 0.25:
        cov_grade = '✅ 穩定'
        cov_tier = 'value'
    elif cov < 0.35:
        cov_grade = '➖ 一般波動'
        cov_tier = 'risky'
    else:
        cov_grade = '🎲 神經刀'
        cov_tier = 'avoid'

    # Trend detection
    trend_diff = weighted_avg - avg
    if trend_diff > 2.0:
        trend = '↑ 近期上升'
    elif trend_diff < -2.0:
        trend = '↓ 近期下滑'
    else:
        trend = '→ 穩定'

    return {
        'avg': round(avg, 1),
        'med': round(med, 1),
        'sd': round(sd, 2),
        'cov': round(cov, 3),
        'weighted_avg': round(weighted_avg, 1),
        'cov_grade': cov_grade,
        'cov_tier': cov_tier,
        'trend': trend,
        'trend_diff': round(trend_diff, 1),
    }


# ── Step 2 Part 2: Situational Adjustments ──────────────

def compute_adjustments(player: dict, ctx: dict, vol: dict) -> dict:
    """Apply all 20+ adjustment rules from 02_volatility_engine.md."""
    adjustments = []
    total = 0.0

    # L3 trend
    l10 = player['l10']
    l3_avg = sum(l10[:3]) / 3
    if l3_avg < vol['avg'] * 0.85:
        adjustments.append(('L3 低潮', -2.0))
        total -= 2.0
    elif l3_avg > vol['avg'] * 1.15:
        adjustments.append(('L3 爆發 (警惕回歸)', +1.0))
        total += 1.0

    # Defender matchup
    dfg = player.get('defender_dfg_pct', 50)
    dpm = player.get('defender_pct_pm', 0)
    if dpm < -0.04:
        adjustments.append(('🔒 精英防守對位', -2.0))
        total -= 2.0
    elif dpm < -0.02:
        adjustments.append(('強防守壓制', -1.0))
        total -= 1.0

    # Team defense
    opp_rank = ctx.get('opp_def_rank', 15)
    if opp_rank <= 5:
        adjustments.append(('對手整體防守 Top 5', -1.0))
        total -= 1.0
    elif opp_rank >= 26:
        adjustments.append(('對手整體防守 Bottom 5', +1.0))
        total += 1.0

    # Fatigue
    if ctx.get('is_3in4'):
        adjustments.append(('終極疲勞: 3-IN-4 Nights', -3.0))
        total -= 3.0
    elif ctx.get('is_b2b'):
        if not ctx.get('is_home'):
            adjustments.append(('重度疲勞: 客場 B2B', -2.5))
            total -= 2.5
        else:
            adjustments.append(('輕度疲勞: 主場 B2B', -1.5))
            total -= 1.5

    # CoV bonus/penalty
    if vol['cov'] < 0.20:
        adjustments.append(('穩定性紅利', +1.0))
        total += 1.0
    elif vol['cov'] > 0.40:
        adjustments.append(('波動性懲罰', -1.5))
        total -= 1.5

    # Pace adjustment
    opp_pace = ctx.get('opp_pace', 99.5)
    league_pace = ctx.get('league_avg_pace', 99.5)
    pace_diff = opp_pace - league_pace
    if pace_diff > 2:
        adjustments.append(('Pace-Up (慢遇快)', +1.0))
        total += 1.0
    elif pace_diff < -2:
        adjustments.append(('Pace-Down (快遇慢)', -1.0))
        total -= 1.0

    # Pace-adjusted projection
    pace_adj_value = (pace_diff / league_pace * vol['avg']) if league_pace > 0 else 0

    # Situational flags
    sit = player.get('situational', {})
    if sit.get('teammate_out_usage_boost'):
        adjustments.append(('隊友傷缺紅利', +1.5))
        total += 1.5
    if sit.get('negative_news'):
        adjustments.append(('負面新聞/不穩定因素', -2.0))
        total -= 2.0
    if sit.get('positive_news'):
        adjustments.append(('正面動態', +1.0))
        total += 1.0
    if sit.get('sharp_money_over'):
        adjustments.append(('Sharp Money 順勢買大', +1.0))
        total += 1.0
    if sit.get('vegas_trap'):
        adjustments.append(('莊家誘餌/聰明錢買小', -2.0))
        total -= 2.0
    if sit.get('opp_center_monster'):
        adjustments.append(('對手籃板怪獸上陣', -2.0))
        total -= 2.0
    if sit.get('opp_rebounder_out'):
        adjustments.append(('對手禁區籃板手缺陣', +1.5))
        total += 1.5

    # Rest day bonus
    rest = ctx.get('rest_days', 1)
    if rest >= 4:
        adjustments.append(('超額休息紅利 (4+日)', +1.5))
        total += 1.5
    elif rest == 3:
        adjustments.append(('休息日紅利 (3日)', +1.0))
        total += 1.0

    # H2H
    h2h = player.get('h2h_data', [])
    if len(h2h) >= 3:
        h2h_avg = sum(h2h) / len(h2h)
        h2h_diff_pct = (h2h_avg - vol['avg']) / vol['avg'] * 100 if vol['avg'] > 0 else 0
        if h2h_diff_pct > 15:
            adjustments.append(('📈 H2H 加成 (歷史宰殺)', +1.0))
            total += 1.0
        elif h2h_diff_pct < -15:
            adjustments.append(('📉 H2H 減持 (被壓制)', -1.0))
            total -= 1.0

    adjusted_projection = round(vol['avg'] + total, 1)

    return {
        'adjustments': adjustments,
        'total_adjustment': round(total, 1),
        'adjusted_projection': adjusted_projection,
        'pace_adj_value': round(pace_adj_value, 2),
    }


# ── Step 3: Bet Line Generation ──────────────

def compute_bet_lines(vol: dict, adj: dict, player: dict) -> dict:
    """Generate banker and value lines."""
    avg = vol['avg']
    sd = vol['sd']
    total_adj = adj['total_adjustment']
    l10 = player['l10']

    # Banker line: AVG - 0.5 * SD + adjustments
    banker_raw = avg - 0.5 * sd + total_adj
    banker_line = round(banker_raw * 2) / 2  # Round to nearest 0.5

    # Value line: MED + positive adjustments only
    pos_adj = sum(v for _, v in adj['adjustments'] if v > 0)
    value_raw = vol['med'] + pos_adj
    value_line = round(value_raw * 2) / 2

    # Hit rates
    banker_hits = sum(1 for x in l10 if x >= banker_line)
    value_hits = sum(1 for x in l10 if x >= value_line)
    banker_hit_rate = banker_hits / len(l10) * 100 if l10 else 0
    value_hit_rate = value_hits / len(l10) * 100 if l10 else 0

    # AMC (average margin of clearing)
    over_amounts = [x - banker_line for x in l10 if x >= banker_line]
    amc = sum(over_amounts) / len(over_amounts) if over_amounts else 0

    # Book line analysis
    book_line = player.get('book_line', banker_line)
    book_hits = sum(1 for x in l10 if x >= book_line)
    book_hit_rate = book_hits / len(l10) * 100 if l10 else 0

    # AMC rating
    if amc >= 3.0:
        amc_label = '🚀 碾壓優勢'
    elif amc >= 1.0:
        amc_label = '✅ 健康空間'
    elif amc >= 0.5:
        amc_label = '⚠️ 汗水單'
    else:
        amc_label = '❌ 空間不足'

    return {
        'banker_line': banker_line,
        'value_line': value_line,
        'banker_hit_rate': round(banker_hit_rate, 0),
        'value_hit_rate': round(value_hit_rate, 0),
        'book_line': book_line,
        'book_hit_rate': round(book_hit_rate, 0),
        'amc': round(amc, 1),
        'amc_label': amc_label,
    }


# ── Step 3 Part 2: +EV Screening ──────────────

def compute_ev(lines: dict, player: dict) -> dict:
    """Compute +EV analysis."""
    book_line = player.get('book_line', lines['banker_line'])
    odds_over = player.get('odds_over', 1.90)
    odds_under = player.get('odds_under', 1.90)

    # Estimated true probability
    est_prob = min(95, lines['book_hit_rate'])
    implied_prob = (1 / odds_over * 100) if odds_over > 0 else 50
    edge = round(est_prob - implied_prob, 1)

    if edge > 15:
        ev_grade = '💎 核心高價值'
    elif edge > 10:
        ev_grade = '✅ 有價值'
    elif edge > 5:
        ev_grade = '➖ 邊緣'
    else:
        ev_grade = '❌ 不推薦'

    return {
        'est_true_prob': round(est_prob, 1),
        'implied_prob': round(implied_prob, 1),
        'edge': edge,
        'ev_grade': ev_grade,
    }


# ── Downside Risk Detection (Over-only strategy) ──────────────

def compute_under_score(player: dict, vol: dict, ctx: dict) -> dict:
    """Systematic downside risk scoring. This never recommends Under bets."""
    score = 0
    reasons = []

    if vol['cov'] > 0.30:
        score += 1; reasons.append(f"CoV>{vol['cov']:.2f}")
    
    if ctx.get('opp_def_rank', 15) <= 5:
        score += 2; reasons.append('強防隊')
    
    dpm = player.get('defender_pct_pm', 0)
    if dpm < -0.04:
        score += 2; reasons.append('精英防守對位')
    
    if not ctx.get('is_home'):
        score += 1; reasons.append('客場')
    
    if ctx.get('is_b2b'):
        score += 1; reasons.append('B2B')
    
    if vol['trend_diff'] < -2:
        score += 1; reasons.append('L3下滑')
    
    sit = player.get('situational', {})
    if sit.get('vegas_trap'):
        score += 2; reasons.append('Vegas Trap')
    
    book = player.get('book_line', vol['avg'])
    if book > vol['avg'] + 0.5 * vol['sd']:
        score += 1; reasons.append('賣線過高')

    if score >= 5:
        verdict = '🚨 強烈降級或剔除 Over'
    elif score >= 3:
        verdict = '✅ Over 只可高賠觀察'
    else:
        verdict = '❌ 無明顯 downside 風險'

    return {
        'score': score,
        'reasons': reasons,
        'verdict': verdict,
    }


# ── Safety Gate ──────────────

def safety_check(player: dict, vol: dict, lines: dict) -> dict:
    """Check for fatal flaws."""
    flaws = []
    passed = True

    if lines['book_hit_rate'] < 60:
        flaws.append(f"命中率過低: {lines['book_hit_rate']}% (<60%)")
        passed = False

    if vol['cov'] > 0.40 and vol['cov_tier'] == 'avoid':
        flaws.append(f"極度波動: CoV={vol['cov']:.3f}")

    if lines['amc'] < 0.5:
        flaws.append(f"空間不足: AMC={lines['amc']}")

    return {'passed': passed, 'flaws': flaws}


# ── Output ──────────────

def format_player_report(name: str, vol: dict, adj: dict, lines: dict,
                         ev: dict, under: dict, safety: dict, player: dict) -> str:
    """Format a single player's complete analysis."""
    out = []
    out.append(f"### 🏀 {name} ({player.get('prop_type', 'points').upper()})")
    
    # Data card
    l10 = player['l10']
    out.append(f"**L10 數組:** `{l10}`")
    out.append(f"\n**📊 數理引擎:**")
    out.append(f"| 指標 | 數值 |")
    out.append(f"|:---|:---|")
    out.append(f"| AVG | {vol['avg']} |")
    out.append(f"| MED | {vol['med']} |")
    out.append(f"| SD | {vol['sd']} |")
    out.append(f"| CoV | {vol['cov']:.3f} ({vol['cov_grade']}) |")
    out.append(f"| Weighted AVG | {vol['weighted_avg']} |")
    out.append(f"| 趨勢 | {vol['trend']} (差: {vol['trend_diff']:+.1f}) |")

    # Adjustments
    out.append(f"\n**🔧 情境調整:**")
    if adj['adjustments']:
        for reason, val in adj['adjustments']:
            out.append(f"- {reason}: `{val:+.1f}`")
    else:
        out.append(f"- 無調整")
    out.append(f"- **總調整值:** `{adj['total_adjustment']:+.1f}`")
    out.append(f"- **調整後預期值:** `{adj['adjusted_projection']}`")

    # Bet lines
    out.append(f"\n**📈 盤口雙線:**")
    out.append(f"| 線路 | 數值 | L10 命中率 |")
    out.append(f"|:---|:---|:---|")
    out.append(f"| 穩膽線 | {lines['banker_line']} | {lines['banker_hit_rate']:.0f}% |")
    out.append(f"| 價值線 | {lines['value_line']} | {lines['value_hit_rate']:.0f}% |")
    out.append(f"| 莊家盤口 | {lines['book_line']} | {lines['book_hit_rate']:.0f}% |")
    out.append(f"- **AMC:** {lines['amc']} ({lines['amc_label']})")

    # +EV
    out.append(f"\n**💰 +EV 分析:**")
    out.append(f"- 預估勝率: {ev['est_true_prob']}% | 隱含勝率: {ev['implied_prob']}%")
    out.append(f"- **Edge: {ev['edge']:+.1f}%** → {ev['ev_grade']}")

    # Downside risk
    out.append(f"\n**📉 Over Downside Risk:**")
    out.append(f"- Downside 分數: **{under['score']}** ({', '.join(under['reasons']) if under['reasons'] else '無觸發'})")
    out.append(f"- {under['verdict']}")

    # Safety
    status = '✅ PASS' if safety['passed'] else '❌ FAIL'
    out.append(f"\n**🛡️ 安全檢查:** {status}")
    for flaw in safety['flaws']:
        out.append(f"- ⚠️ {flaw}")

    # Final verdict
    if safety['passed'] and ev['edge'] > 5:
        tier = '穩膽' if vol['cov_tier'] in ('banker',) else ('價值' if vol['cov_tier'] == 'value' else '高賠')
        out.append(f"\n**✅ 合格 Leg 候選** | 層級: `{tier}` | Edge: {ev['edge']:+.1f}%")
    elif not safety['passed']:
        out.append(f"\n**❌ 不合格** — 致命缺陷")
    else:
        out.append(f"\n**⚠️ 邊緣候選** — Edge 不足")

    return '\n'.join(out)


def main():
    parser = argparse.ArgumentParser(description="NBA Wong Choi — Props Calculator")
    parser.add_argument("--input", type=str, help="Path to players JSON file")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if not args.input:
        print("Usage: python compute_nba_props.py --input <players.json>")
        sys.exit(0)

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    ctx = data.get('game_context', {})
    players = data.get('players', [])

    out = []
    out.append(f"# 🏀 NBA Props 計算結果")
    out.append(f"**賽事:** {ctx.get('game_id', 'Unknown')} | {'主場' if ctx.get('is_home') else '客場'} | 休息: {ctx.get('rest_days', '?')}日")
    out.append(f"**對手防守:** 排名 #{ctx.get('opp_def_rank', '?')} | PACE: {ctx.get('opp_pace', '?')}\n")

    qualified = []
    for p in players:
        vol = compute_volatility(p['l10'])
        adj = compute_adjustments(p, ctx, vol)
        lines = compute_bet_lines(vol, adj, p)
        ev = compute_ev(lines, p)
        under = compute_under_score(p, vol, ctx)
        safety = safety_check(p, vol, lines)

        out.append(format_player_report(p['name'], vol, adj, lines, ev, under, safety, p))
        out.append(f"\n{'─' * 50}\n")

        if safety['passed'] and ev['edge'] > 5:
            qualified.append({
                'name': p['name'],
                'prop_type': p.get('prop_type', 'points'),
                'line': lines['book_line'],
                'edge': ev['edge'],
                'tier': vol['cov_tier'],
                'hit_rate': lines['book_hit_rate'],
            })

    # Summary
    out.append(f"\n## 📋 合格 Leg 候選池")
    if qualified:
        out.append(f"| # | 球員 | 指標 | 盤口 | Edge | 層級 | 命中率 |")
        out.append(f"|:--|:-----|:-----|:-----|:-----|:-----|:-------|")
        for i, q in enumerate(qualified):
            out.append(f"| {i+1} | {q['name']} | {q['prop_type']} | {q['line']} | {q['edge']:+.1f}% | {q['tier']} | {q['hit_rate']:.0f}% |")
    else:
        out.append("**⚠️ 無合格候選 — 全部被安全檢查排除**")

    result_text = '\n'.join(out)
    if args.output:
        Path(args.output).write_text(result_text, encoding='utf-8')
        print(f"✅ NBA props computed: {args.output}")
        print(f"   📊 {len(players)} players | {len(qualified)} qualified legs")
    else:
        print(result_text)


if __name__ == '__main__':
    main()
