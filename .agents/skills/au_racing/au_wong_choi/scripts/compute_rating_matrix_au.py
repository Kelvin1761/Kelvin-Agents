#!/usr/bin/env python3
"""
compute_rating_matrix_au.py — AU Wong Choi Protocol Rating Matrix Calculator
Generates Verdict skeleton (Part 3+4+5) with Python-prefilled data.

Usage:
    python compute_rating_matrix_au.py --input <dimensions.json> [--output <file>]

Input JSON format:
{
    "race_context": {
        "venue": "Randwick",
        "distance": 1200,
        "surface": "turf",
        "going": "Good 4",
        "race_number": 3,
        "class": "BM72",
        "pace_type": "genuine",
        "weather_stability": "STABLE"
    },
    "horses": [
        {
            "num": 1, "name": "Horse Name",
            "jockey": "J McDonald", "trainer": "C Waller",
            "weight_kg": 58.5, "barrier": 3,
            "dimensions": {
                "stability": "✅", "sectional": "✅",
                "eem": "➖", "jockey_trainer": "✅",
                "class_weight": "✅", "track": "➖",
                "form_line": "N/A", "gear_distance": "➖"
            },
            "forgiveness_bonus": false,
            "micro_up": [],
            "micro_down": [],
            "stability_index": 0.55
        }
    ]
}
"""

import json
import sys
import argparse
from pathlib import Path


# ── Grade System ──────────────────────────────────────────────

GRADE_ORDER = [
    'S+', 'S', 'S-',
    'A+', 'A', 'A-',
    'B+', 'B', 'B-',
    'C+', 'C', 'C-',
    'D+', 'D',
]

def grade_idx(g: str) -> int:
    try:
        return GRADE_ORDER.index(g)
    except ValueError:
        return len(GRADE_ORDER)


# ── Dimension Classification ─────────────────────────────────

CORE = ['stability', 'sectional']
HALF = ['eem', 'jockey_trainer']
AUX  = ['class_weight', 'track', 'form_line', 'gear_distance']

DIM_LABELS = {
    'stability': '狀態與穩定性',
    'sectional': '段速與引擎',
    'eem': 'EEM與形勢',
    'jockey_trainer': '騎練訊號',
    'class_weight': '級數與負重',
    'track': '場地適性',
    'form_line': '賽績線',
    'gear_distance': '裝備與距離',
}


def count_dims(dims: dict) -> dict:
    counts = {
        'core_strong': 0, 'core_weak': 0,
        'half_strong': 0, 'half_weak': 0,
        'aux_strong': 0, 'aux_weak': 0,
        'total_strong': 0, 'total_weak': 0,
    }
    for d in CORE:
        v = dims.get(d, '➖')
        if v == '✅': counts['core_strong'] += 1; counts['total_strong'] += 1
        elif v == '❌': counts['core_weak'] += 1; counts['total_weak'] += 1
    for d in HALF:
        v = dims.get(d, '➖')
        if v == '✅': counts['half_strong'] += 1; counts['total_strong'] += 1
        elif v == '❌': counts['half_weak'] += 1; counts['total_weak'] += 1
    for d in AUX:
        v = dims.get(d, '➖')
        if v == '✅': counts['aux_strong'] += 1; counts['total_strong'] += 1
        elif v == '❌': counts['aux_weak'] += 1; counts['total_weak'] += 1
    return counts


def effective_ticks(counts: dict) -> float:
    return counts['core_strong'] * 2.0 + counts['half_strong'] * 1.5 + counts['aux_strong'] * 1.0


# ── Lookup Table ──────────────────────────────────────────────

def lookup_base_grade(counts: dict) -> str:
    cs, hs, aw, tw = counts['core_strong'], counts['half_strong'], counts['aux_strong'], counts['total_weak']
    cw = counts['core_weak']
    if cw >= 1:
        if tw >= 3: return 'D'
        if cs == 0 and hs == 0: return 'D+'
        return 'C'
    if cs == 2 and hs >= 1 and tw == 0: return 'S'
    if cs == 2 and hs >= 1 and tw <= 1: return 'S-'
    if cs == 2 and tw <= 1: return 'A+'
    if cs == 2: return 'A'
    if cs == 1 and hs >= 1 and tw == 0: return 'A-'
    if cs == 1 and hs >= 1: return 'B+'
    if cs == 1: return 'B'
    if hs >= 2 and aw >= 2: return 'B-'
    if hs >= 1 and aw >= 2: return 'C+'
    if aw >= 3: return 'C'
    if tw >= 5 and cs == 0:
        if aw >= 1: return 'D+'
        return 'D'
    return 'C-'


def apply_micro(grade: str, ups: list, downs: list) -> str:
    idx = grade_idx(grade)
    net = len(ups) - len(downs)
    new_idx = max(0, min(len(GRADE_ORDER) - 1, idx - net))
    return GRADE_ORDER[new_idx]


# ── Single Horse Pipeline ────────────────────────────────────

def compute_one(h: dict) -> dict:
    dims = h['dimensions']
    counts = count_dims(dims)
    base = lookup_base_grade(counts)
    fg = h.get('forgiveness_bonus', False)
    if fg:
        counts['aux_strong'] += 1
        counts['total_strong'] += 1
        base = lookup_base_grade(counts)
    micro = apply_micro(base, h.get('micro_up', []), h.get('micro_down', []))
    final = micro
    return {
        'num': h['num'],
        'name': h['name'],
        'jockey': h.get('jockey', ''),
        'trainer': h.get('trainer', ''),
        'weight_kg': h.get('weight_kg', 0),
        'barrier': h.get('barrier', 0),
        'dimensions': dims,
        'counts': counts,
        'effective_ticks': effective_ticks(counts),
        'base_grade': base,
        'micro_grade': micro,
        'final_grade': final,
        'stability_index': h.get('stability_index', 0),
    }


def rank_horses(results: list) -> list:
    def sort_key(r):
        gi = grade_idx(r['final_grade'])
        return (gi, -r['effective_ticks'], r['counts']['total_weak'])
    return sorted(results, key=sort_key)


def generate_verdict(ranked: list, ctx: dict) -> str:
    """Generate complete Part 3+4+5 skeleton with Python-prefilled data (AU version)."""
    labels = ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']
    weather_stability = ctx.get('weather_stability', 'STABLE')
    race_num = ctx.get('race_number', '?')
    distance = ctx.get('distance', '?')
    race_class = ctx.get('class', '?')

    lines = [
        "## [第三部分] 🏆 全場最終決策\n",
        f"**Speed Map 回顧:** {{{{LLM_FILL}}}}",
        "",
        "**Top 4 位置精選**\n",
    ]

    # Top 4 prefilled
    for i, r in enumerate(ranked[:4]):
        lines.append(labels[i])
        lines.append(f"- **馬號及馬名:** {r['num']} {r['name']}")
        lines.append(f"- **評級與✅數量:** `[{r['final_grade']}]` | ✅ {r['counts']['total_strong']}")
        lines.append(f"- **核心理據:** {{{{LLM_FILL}}}}")
        lines.append(f"- **最大風險:** {{{{LLM_FILL}}}}")
        lines.append("")

    # Top 2 Place Confidence
    if len(ranked) >= 2:
        lines.append("**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**")
        lines.append(f"🥇 {ranked[0]['name']}:`{{{{LLM_FILL}}}}` — 最大威脅:{{{{LLM_FILL}}}}")
        lines.append(f"🥈 {ranked[1]['name']}:`{{{{LLM_FILL}}}}` — 最大威脅:{{{{LLM_FILL}}}}")
        lines.append("")

    # Exotic Pool Recommendation (SIP-FL03)
    lines.append("**[SIP-FL03] 🎰 Exotic 組合投注池建議:**")
    top4 = ranked[:4]
    top4_grades = [r['final_grade'] for r in top4]
    # Auto-check trigger: ≥3 horses within 1 grade + no S-level dominator
    grade_spread = max(grade_idx(g) for g in top4_grades) - min(grade_idx(g) for g in top4_grades) if top4_grades else 99
    has_s_dominator = any(grade_idx(g) <= grade_idx('S-') for g in top4_grades[:1])
    if grade_spread <= 2 and not has_s_dominator:
        core_pool = ", ".join([f"#{r['num']} {r['name']}" for r in top4])
        lines.append(f"📦 **Box Trifecta 核心池:** {core_pool}")
        lines.append("📊 **投注邏輯:** {{LLM_FILL}}")
    else:
        lines.append("本場暫不適用 — 有明確獨贏首選(評級斷層明顯)")
    lines.append("")

    # Dual-Track Top 4 (SIP-RR01) — only if UNSTABLE
    if weather_stability == 'UNSTABLE':
        lines.append("**[SIP-RR01] 📗📙 雙軌場地 Top 4:**")
        lines.append("📗 **預期場地 Top 4:** (同上)")
        lines.append("📙 **備選場地 Top 4:** {{LLM_FILL}}")
        lines.append("**🔄 關鍵排名變化摘要:** {{LLM_FILL}}")
        lines.append("")

    lines.append("---\n")

    # Part 4: Analysis Traps
    lines.append("## [第四部分] 分析陷阱\n")
    lines.append("- **市場預期警告:** {{LLM_FILL}}")
    lines.append("")

    # Market-Engine Divergence (SIP-SL04)
    lines.append("**[SIP-SL04] 🔍 市場-引擎偏差重新審視:** {{LLM_FILL}}")
    lines.append("")

    # Pace Flip Insurance
    lines.append("**🔄 步速逆轉保險 (Pace Flip Insurance):**")
    lines.append("- 若步速比預測更快 → 最受惠:{{LLM_FILL}} | 最受損:{{LLM_FILL}}")
    lines.append("- 若步速比預測更慢 → 最受惠:{{LLM_FILL}} | 最受損:{{LLM_FILL}}")
    lines.append("- **整體潛在機會建議:** {{LLM_FILL}}")
    lines.append("")

    # Emergency Brake Protocol (auto-check)
    lines.append("**🚨 緊急煞車檢查 (Emergency Brake Protocol):**")
    a_minus_or_above = any(grade_idx(g) <= grade_idx('A-') for g in top4_grades)
    if not a_minus_or_above:
        lines.append("- ⚠️ 低信心賽事 (LOW CONFIDENCE RACE) — 建議保守部署")
    diff = 0
    if len(top4) >= 2:
        diff = abs(grade_idx(top4[0]['final_grade']) - grade_idx(top4[1]['final_grade']))
        if diff >= 2:
            lines.append("- ⚠️ 獨贏局 (ONE-HORSE RACE)")
    c_or_below = sum(1 for r in ranked if grade_idx(r['final_grade']) >= grade_idx('C'))
    if len(ranked) > 0 and c_or_below / len(ranked) > 0.5:
        lines.append("- ⚠️ 混戰 (DIFFICULT RACE) — 建議輕注")
    if a_minus_or_above and diff < 2 and (len(ranked) == 0 or c_or_below / len(ranked) <= 0.5):
        lines.append("- ✅ 無觸發")
    lines.append("")

    # Upset Potential Warning (SIP-RR07)
    field_size = len(ranked)
    upset_score = 0
    if field_size >= 14: upset_score += 2
    if weather_stability == 'UNSTABLE': upset_score += 2
    if not a_minus_or_above: upset_score += 2
    lines.append(f"**[SIP-RR07] ⚠️ 爆冷潛力預警:** 爆冷指數: {upset_score}/10")
    if upset_score >= 6:
        lines.append("⚠️ 高爆冷潛力賽事 — 建議保守部署")
    lines.append("")

    # Exotic Anchors
    lines.append("**📊 穩建馬外報建議 (Exotic Anchors):** {{LLM_FILL}}")
    lines.append("")

    # Underhorse Signal Summary
    lines.append("**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):** {{LLM_FILL}}")
    lines.append("")

    # Part 5: CSV
    lines.append("---\n")
    lines.append("## [第五部分] 📊 數據庫匯出 (CSV)\n")
    lines.append("```csv")
    for i, r in enumerate(ranked[:4]):
        lines.append(f"{race_num}, {race_class}, {distance}m, {r['jockey']}, {r['trainer']}, {r['num']}, {r['name']}, {r['final_grade']}")
    lines.append("```")

    return "\n".join(lines)


def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description='AU Rating Matrix Calculator')
    parser.add_argument('--input', required=True, help='Path to dimensions.json')
    parser.add_argument('--output', help='Output file path (optional)')
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    ctx = data.get('race_context', {})
    horses = data.get('horses', [])

    results = [compute_one(h) for h in horses]
    ranked = rank_horses(results)

    # Print ranking table
    print("=" * 70)
    print(f"AU Rating Matrix — {ctx.get('venue', '?')} R{ctx.get('race_number', '?')} {ctx.get('distance', '?')}m {ctx.get('class', '?')}")
    print("=" * 70)
    print(f"{'#':<4} {'Name':<20} {'Base':<5} {'Final':<5} {'✅':<4} {'❌':<4} {'Eff':<6}")
    print("-" * 70)
    for r in ranked:
        print(f"{r['num']:<4} {r['name']:<20} {r['base_grade']:<5} {r['final_grade']:<5} "
              f"{r['counts']['total_strong']:<4} {r['counts']['total_weak']:<4} {r['effective_ticks']:<6.1f}")
    print("=" * 70)

    # Generate verdict skeleton
    verdict = generate_verdict(ranked, ctx)
    print("\n" + verdict)

    if args.output:
        Path(args.output).write_text(verdict, encoding='utf-8')
        print(f"\n✅ Verdict skeleton written to {args.output}")


if __name__ == '__main__':
    main()
