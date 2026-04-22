#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
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

# Import shared qualitative rating engine v2 (replaces deprecated grading_engine)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../scripts")))
from rating_engine_v2 import compute_base_grade, compute_weighted_score, apply_fine_tune, parse_matrix_scores, grade_sort_index, grade_idx, apply_s_grade_guards, GRADE_ORDER, grade_up


# ── Single Horse Pipeline ────────────────────────────────────

def compute_one(h: dict) -> dict:
    dims = h['dimensions']
    matrix_keys_map = {
        "stability": "core", "sectional": "core",
        "eem": "aux", "jockey_trainer": "semi",
        "class_weight": "aux", "track": "aux", 
        "form_line": "aux", "gear_distance": "aux",
    }
    
    core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(dims, matrix_keys_map)
    
    fg = h.get('forgiveness_bonus', False)
    if fg:
        aux_pass += 1
        
    w_score = compute_weighted_score(core_pass, semi_pass, aux_pass, core_fail, total_fail)
    base = compute_base_grade(core_pass, semi_pass, aux_pass, core_fail, total_fail)
    
    net = len(h.get('micro_up', [])) - len(h.get('micro_down', []))
    ft_dir = '+' if net > 0 else ('-' if net < 0 else '')
    after_ft = apply_fine_tune(base, ft_dir)
    
    # ── SIP-9 + SIP-SL01 S-Grade Inflation Guards ──
    counts = {
        'core_strong': core_pass, 'semi_strong': semi_pass, 'aux_strong': aux_pass,
        'total_strong': core_pass + semi_pass + aux_pass, 'total_weak': total_fail,
        'has_core_weak': core_fail > 0,
    }
    final, guard_note = apply_s_grade_guards(
        after_ft, h, counts, dims, {},
        sectional_key='sectional', class_key='class_weight'
    )
    
    return {
        'num': h['num'],
        'name': h['name'],
        'jockey': h.get('jockey', ''),
        'trainer': h.get('trainer', ''),
        'weight_kg': h.get('weight_kg', 0),
        'barrier': h.get('barrier', 0),
        'dimensions': dims,
        'counts': {'total_strong': core_pass+semi_pass+aux_pass, 'total_weak': total_fail},
        'effective_ticks': w_score,
        'base_grade': base,
        'micro_grade': after_ft,
        'final_grade': final,
        'guard_note': guard_note,
        'stability_index': h.get('stability_index', 0),
        'weighted_score': w_score
    }


# ── AU Override Chain (14 rules from 02g_override_chain.md) ─────────
# Priority: P0 > P1 > P2 > P3 > P4 > P5 > P6 > P7
# Ceiling always beats floor when conflicting.

def apply_au_overrides(result: dict, horse: dict, ctx: dict) -> dict:
    """Post-processing override chain for AU racing.
    Applies caps and floors in priority order to the final_grade."""
    grade = result['final_grade']
    dims = result.get('dimensions', {})
    notes = []

    # Track the strictest ceiling applied (ceiling always beats floor)
    lowest_ceiling_idx = 0  # S = index 0 (no cap)

    # Helper: cap grade (ceiling)
    def cap(g, ceiling, note):
        nonlocal lowest_ceiling_idx
        ceil_idx = grade_idx(ceiling)
        if grade_idx(g) < ceil_idx:
            notes.append(note)
            if ceil_idx > lowest_ceiling_idx:
                lowest_ceiling_idx = ceil_idx
            return ceiling
        # Even if grade already below ceiling, track it
        if ceil_idx > lowest_ceiling_idx:
            lowest_ceiling_idx = ceil_idx
        return g

    # Helper: floor grade (minimum) — cannot exceed lowest ceiling
    def floor(g, minimum, note):
        # Enforce: ceiling always beats floor
        effective_min = minimum
        if lowest_ceiling_idx > 0 and grade_idx(minimum) < lowest_ceiling_idx:
            effective_min = GRADE_ORDER[lowest_ceiling_idx]
        if grade_idx(g) > grade_idx(effective_min):
            notes.append(note)
            return effective_min
        return g

    si = horse.get('stability_index', result.get('stability_index', 0))
    risk_markers = horse.get('risk_markers', [])
    risk_count = len(risk_markers) if isinstance(risk_markers, list) else int(risk_markers or 0)

    # ── P0: Absolute Risk Cap ──
    if risk_count >= 4:
        grade = 'D'
        notes.append(f'P0風險封頂: {risk_count}項風險標記 → 自動D')
        result['final_grade'] = grade
        result['override_notes'] = notes
        return result  # All floors disabled

    # ── P1: Core Engine Wall (already in compute_one via engine) ──
    # (handled by rating_engine_v2 apply_core_constraint if needed)

    # ── P2: Scenario Caps (High) ──
    # 2YO cap
    if horse.get('is_2yo', False):
        grade = cap(grade, 'A-', 'P2: 2歲馬封頂A-')

    # Distance wall
    if horse.get('distance_wall', False):
        grade = cap(grade, 'A-', 'P2: 距離牆封頂A-')

    # Long spell
    if horse.get('long_spell', False):
        grade = cap(grade, 'A-', 'P2: 久休封頂A-')

    # ── P3: Scenario Caps (Medium) ──
    # Trial illusion
    if horse.get('trial_illusion', False):
        grade = cap(grade, 'B+', 'P3: 試閘虛火封頂B+')

    # Wet track unknown/risk (SIP-RF02)
    wet_tier = horse.get('wet_track_tier', 0)
    is_wet = ctx.get('going', '').lower().startswith(('soft', 'heavy'))
    if is_wet and wet_tier == 4:
        grade = cap(grade, 'A-', 'P3 SIP-RF02: 濕地未知封頂A-')
    elif is_wet and wet_tier == 5:
        grade = cap(grade, 'B+', 'P3 SIP-RF02: 濕地風險封頂B+')

    # Good track win rate cap (SIP-RR14)
    good_wr = horse.get('good_track_win_rate', None)
    good_sample = horse.get('good_track_sample', 0)
    is_good = 'good' in ctx.get('going', '').lower()
    if is_good and good_sample >= 8 and good_wr is not None and good_wr <= 0.15:
        grade = cap(grade, 'B', 'P3 SIP-RR14: Good地勝率≤15%封頂B')

    # Track geometry cap for closers
    closer_cap_track = horse.get('closer_cap_track', False)
    if closer_cap_track:
        field_size = ctx.get('field_size', 0)
        has_sec_pass = '✅' in str(dims.get('sectional', ''))
        if field_size >= 13 and has_sec_pass:
            pass  # Cap removed
        elif field_size >= 13:
            grade = cap(grade, 'A-', 'P3: 急彎後追(大場)封頂A-')
        else:
            grade = cap(grade, 'B+', 'P3: 急彎後追馬封頂B+')

    # Rosehill 1200m traffic chain
    if horse.get('rosehill_1200_traffic', False):
        grade = cap(grade, 'B-', 'P3: 玫瑰崗1200m塞車封頂B-')

    # ── P4: S-Grade Guards (already applied in compute_one) ──
    # SIP-9/SIP-SL01 handled above

    # ── Compound risk escalation (2-3 items) ──
    if risk_count == 3:
        grade = cap(grade, 'C+', 'P2風險升級: 3項風險標記封頂C+')
    elif risk_count == 2:
        grade = cap(grade, 'B', 'P2風險升級: 2項風險標記封頂B')

    # ── P5: High-Priority Floors ──
    # SIP-RR17 Wet track momentum floor
    momentum = horse.get('momentum_level', '')
    if is_wet and momentum in ('positive', 'strong'):
        grade = floor(grade, 'B+', f'P5 SIP-RR17: 濕地動力保底B+ ({momentum})')

    # ── P6: Super Iron Legs Floor ──
    if si > 0.7:
        grade = floor(grade, 'B+', f'P6: 超級鐵腳保底B+ (SI={si})')
    # ── P7: Iron Legs Floor ──
    elif si > 0.5:
        grade = floor(grade, 'B', f'P7: 鐵腳保底B (SI={si})')

    # Class override floor
    has_sec = '✅' in str(dims.get('sectional', ''))
    has_cls = '✅' in str(dims.get('class_weight', ''))
    if has_sec and has_cls:
        grade = floor(grade, 'B', 'P7: 級數首選保底B')

    # EEM is now shape/consumption context only; do not upgrade grade by itself.
    if horse.get('eem_3_high_drain', False) and horse.get('good_barrier', False):
        notes.append('P7: EEM連續高消耗只作風險/形勢註記，不單獨升級')

    # [SIP-C14-3] 2YO rating anomaly check
    if horse.get('is_2yo', False) and horse.get('rating_top3_field', False):
        if grade_idx(grade) >= grade_idx('C-'):
            grade = floor(grade, 'B-', 'P7 SIP-C14-3: 2YO高Rating異常保底B-')

    # Long-distance class override
    if horse.get('class_advantage_2bm', False) and ctx.get('distance', 0) >= 2000:
        pace = ctx.get('pace_type', '').lower()
        if pace in ('moderate', 'crawl'):
            notes.append('P7: 長途慢步速級數覆寫 — 斷尾微調不觸發')

    # Ceiling always beats Floor — enforce
    # (Already enforced by processing caps before floors)

    result['final_grade'] = grade
    result['override_notes'] = notes
    return result


def rank_horses(results: list) -> list:
    def sort_key(r):
        gi = grade_sort_index(r['final_grade'])
        return (gi, -r['weighted_score'])
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
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    parser = argparse.ArgumentParser(description='AU Rating Matrix Calculator')
    parser.add_argument('--input', required=True, help='Path to dimensions.json')
    parser.add_argument('--output', help='Output file path (optional)')
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    ctx = data.get('race_context', {})
    horses = data.get('horses', [])

    results = [compute_one(h) for h in horses]
    # Apply AU-specific override chain (P0-P7 caps/floors)
    results = [apply_au_overrides(r, h, ctx) for r, h in zip(results, horses)]
    ranked = rank_horses(results)

    # Print ranking table
    print("=" * 70)
    print(f"AU Rating Matrix — {ctx.get('venue', '?')} R{ctx.get('race_number', '?')} {ctx.get('distance', '?')}m {ctx.get('class', '?')}")
    print("=" * 70)
    print(f"{'#':<4} {'Name':<20} {'Base':<5} {'Final':<5} {'✅':<4} {'❌':<4} {'Eff':<6} {'Guard'}")
    print("-" * 70)
    for r in ranked:
        gn = r.get('guard_note', '')
        print(f"{r['num']:<4} {r['name']:<20} {r['base_grade']:<5} {r['final_grade']:<5} "
              f"{r['counts']['total_strong']:<4} {r['counts']['total_weak']:<4} {r['effective_ticks']:<6.1f} {gn}")
    print("=" * 70)

    # Generate verdict skeleton
    verdict = generate_verdict(ranked, ctx)
    print("\n" + verdict)

    if args.output:
        Path(args.output).write_text(verdict, encoding='utf-8')
        print(f"\n✅ Verdict skeleton written to {args.output}")


if __name__ == '__main__':
    main()
