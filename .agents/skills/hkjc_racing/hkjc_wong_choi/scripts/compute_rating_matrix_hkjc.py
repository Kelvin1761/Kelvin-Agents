#!/usr/bin/env python3
"""
compute_rating_matrix_hkjc.py — HKJC Wong Choi Protocol Rating Matrix Calculator
Full implementation of Step 14.2 including all override rules.

Usage:
    python3 compute_rating_matrix_hkjc.py --input <dimensions.json> [--race-id HV_R7]

Input JSON format:
{
    "race_context": {
        "venue": "HV",  // "ST" or "HV"
        "distance": 1200,
        "surface": "turf",  // "turf" or "awt"
        "rail": "C+3",
        "pace_type": "genuine_fast"
    },
    "horses": [
        {
            "num": 1, "name": "馬名",
            "weight_lbs": 126, "barrier": 3, "age": 4,
            "jockey_rank": 2, "jockey_first_ride": false,
            "dimensions": {
                "stability": "✅", "sectional": "✅",
                "eem": "➖", "trainer_signal": "✅",
                "scenario": "✅", "distance_freshness": "➖",
                "form_line": "N/A", "class_advantage": "➖"
            },
            "forgiveness_bonus": false,
            "micro_up": [],
            "micro_down": [],
            "risk_markers": 0,
            "stability_index": 0.55,
            "overvalue_flag": false,
            "last_4_finishes": [1,2,3,5],
            "last_4_top5_no_top3": false,
            "downtrend": false,
            "last_race_won": true,
            "weight_gain_lbs": 6,
            "is_debut": false,
            "is_3yo": false,
            "season_wins": 2,
            "recent_4_wins": 1,
            "l10_top3_count": 6,
            "same_venue_dist_top3": 0,
            "hv_specialist_conditions": {}
        }
    ]
}
"""
import json, sys, argparse
from pathlib import Path
from typing import Optional

GRADE_ORDER = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D']

DIMENSION_TYPES = {
    'stability':          'core',
    'sectional':          'core',
    'eem':                'semi_core',
    'trainer_signal':     'semi_core',
    'scenario':           'auxiliary',
    'distance_freshness': 'auxiliary',
    'form_line':          'auxiliary',
    'class_advantage':    'auxiliary',
}

DIMENSION_LABELS = {
    'stability':          ('位置穩定性', '核心'),
    'sectional':          ('段速質量', '核心'),
    'eem':                ('EEM 潛力', '半核心'),
    'trainer_signal':     ('練馬師訊號', '半核心'),
    'scenario':           ('情境適配', '輔助'),
    'distance_freshness': ('路程/新鮮度', '輔助'),
    'form_line':          ('賽績線', '輔助(可選)'),
    'class_advantage':    ('級數優勢', '輔助'),
}

def grade_idx(g: str) -> int:
    return GRADE_ORDER.index(g) if g in GRADE_ORDER else 99

def grade_up(g: str, n: int = 1) -> str:
    i = grade_idx(g)
    return GRADE_ORDER[max(0, i - n)]

def grade_down(g: str, n: int = 1) -> str:
    i = grade_idx(g)
    return GRADE_ORDER[min(len(GRADE_ORDER) - 1, i + n)]


# ── Step 14.1: Count dimensions ──────────────

def count_dimensions(dims: dict) -> dict:
    counts = {
        'core_strong': 0, 'core_neutral': 0, 'core_weak': 0,
        'semi_strong': 0, 'semi_neutral': 0, 'semi_weak': 0,
        'aux_strong': 0, 'aux_neutral': 0, 'aux_weak': 0,
        'total_strong': 0, 'total_weak': 0,
        'has_core_weak': False,
    }
    for dim_key, value in dims.items():
        v = value.strip()
        if v in ('N/A', '不計入'):
            continue
        dim_type = DIMENSION_TYPES.get(dim_key, 'auxiliary')
        if v == '✅':
            counts['total_strong'] += 1
            if dim_type == 'core': counts['core_strong'] += 1
            elif dim_type == 'semi_core': counts['semi_strong'] += 1
            else: counts['aux_strong'] += 1
        elif v == '❌':
            counts['total_weak'] += 1
            if dim_type == 'core':
                counts['core_weak'] += 1
                counts['has_core_weak'] = True
            elif dim_type == 'semi_core': counts['semi_weak'] += 1
            else: counts['aux_weak'] += 1
        else:
            if dim_type == 'core': counts['core_neutral'] += 1
            elif dim_type == 'semi_core': counts['semi_neutral'] += 1
            else: counts['aux_neutral'] += 1
    return counts


# ── Step 14.2: Base Grade Lookup ──────────────

def lookup_base_grade(c: dict) -> tuple:
    cs, ss, axs, tw = c['core_strong'], c['semi_strong'], c['aux_strong'], c['total_weak']
    if cs >= 2 and ss >= 2 and axs >= 2 and tw == 0:
        return 'S', f'2核心✅ + 2半核心✅ + {axs}輔助✅ + 0❌'
    if cs >= 2 and ss >= 1 and axs >= 1 and tw == 0:
        return 'S-', f'2核心✅ + {ss}半核心✅ + {axs}輔助✅ + 0❌'
    if cs >= 2 and tw == 0:
        return 'A+', f'2核心✅ + 0❌'
    if (cs >= 1 and ss >= 1 and tw == 0) or (cs >= 2 and tw <= 1):
        return 'A', f'{cs}核心✅ + {ss}半核心✅ + {tw}❌'
    if cs >= 1 and tw <= 1:
        return 'A-', f'{cs}核心✅ + ❌≤1'
    if (cs >= 1 and tw == 2) or (ss >= 2 and tw <= 1):
        return 'B+', f'{cs}核心✅/{ss}半核心✅ + {tw}❌'
    if ss >= 1 and axs >= 2 and tw <= 2:
        return 'B', f'{ss}半核心✅ + {axs}輔助✅ + {tw}❌'
    if cs == 0 and ss == 0 and axs >= 3 and tw <= 2:
        return 'B-', f'0核心/半核心✅ + {axs}輔助✅'
    if tw == 3 and (cs >= 1 or ss >= 1):
        return 'C+', f'{tw}❌ + 有核心/半核心✅挽救'
    if tw == 3:
        return 'C', f'{tw}❌ + 無核心/半核心✅'
    if tw == 4:
        return 'C-', f'{tw}❌'
    ts = c['total_strong']
    if tw >= 5 and (cs >= 1 or ss >= 1 or axs >= 2):
        return 'D+', f'{tw}❌ + 有✅({ts})'
    if tw >= 5 or ts == 0:
        return 'D', f'{tw}❌ / 無✅'
    return 'C', f'未匹配 (core✅={cs}, semi✅={ss}, aux✅={axs}, ❌={tw})'


# ── Core Constraint ──────────────

def apply_core_constraint(grade: str, counts: dict, dims: dict) -> tuple:
    if not counts['has_core_weak']:
        return grade, ''
    if dims.get('sectional', '').strip() == '✅' and dims.get('eem', '').strip() == '✅':
        if grade_idx(grade) < grade_idx('A-'):
            return 'A-', '核心❌但段速✅+EEM✅豁免 → 封頂A-'
        return grade, ''
    if grade_idx(grade) < grade_idx('B+'):
        return 'B+', '核心防護牆: 核心❌ → 封頂B+'
    return grade, ''


# ── Step 14.2B: Micro-adjustments ──────────────

def apply_micro_adjustments(grade: str, up: list, down: list) -> tuple:
    if not up and not down:
        return grade, '無'
    i = grade_idx(grade)
    net = (1 if up else 0) - (1 if down else 0)
    if net > 0 and i > 0:
        return GRADE_ORDER[i - 1], f'升一級 ({", ".join(up)})'
    elif net < 0 and i < len(GRADE_ORDER) - 1:
        return GRADE_ORDER[i + 1], f'降一級 ({", ".join(down)})'
    if up and down:
        return grade, f'升降互抵 (↑{", ".join(up)} / ↓{", ".join(down)})'
    return grade, '無'


# ── Step 14.2C: D-Grade Longshot Scan ──────────────

def d_grade_longshot_scan(grade: str, horse: dict) -> tuple:
    """If D/C-/C, check for strong positive signals → force upgrade."""
    if grade not in ('D', 'C-', 'C', 'D+'):
        return grade, ''
    
    signals = horse.get('longshot_signals', [])
    if not signals:
        return grade, ''
    
    if len(signals) >= 1:
        if grade in ('D', 'D+'):
            return 'C-', f'冷門掃描: {len(signals)}項正面訊號 → D升C-'
        elif grade in ('C-', 'C'):
            return 'B-', f'冷門掃描: {len(signals)}項正面訊號 → {grade}升B-'
    return grade, ''


# ── Step 14.2E: B+ Upgrade Scan (HV) ──────────────

def b_plus_upgrade_scan(grade: str, horse: dict, ctx: dict) -> tuple:
    """HV B+ specialist upgrade."""
    if grade != 'B+' or ctx.get('venue') != 'HV':
        return grade, ''
    
    conditions_met = 0
    reasons = []
    
    if horse.get('same_venue_dist_top3', 0) >= 1:
        conditions_met += 1; reasons.append('同場同程入三甲')
    if any(f <= 5 for f in horse.get('last_4_finishes', [])[-3:]):
        conditions_met += 1; reasons.append('近3仗有前5')
    if horse.get('barrier', 99) <= 6:
        conditions_met += 1; reasons.append('好檔位')
    w = horse.get('weight_lbs', 130)
    if w <= horse.get('field_median_weight', 126):
        conditions_met += 1; reasons.append('輕磅')
    if horse.get('jockey_rank', 99) <= 10:
        conditions_met += 1; reasons.append('Top-10騎師')
    
    if conditions_met >= 2:
        return 'A-', f'B+ HV專家升級 ({", ".join(reasons[:3])})'
    return grade, ''


# ── Step 14.3: Override Rules ──────────────

def apply_overrides(grade: str, horse: dict, counts: dict, dims: dict, ctx: dict) -> tuple:
    notes = []
    
    # 1. Risk escalation (highest priority)
    risk = horse.get('risk_markers', 0)
    if risk >= 4:
        grade = 'D'
        notes.append(f'風險封頂: {risk}項風險標記 → 自動D')
        return grade, '; '.join(notes)
    if risk == 3:
        if grade_idx(grade) < grade_idx('C+'):
            grade = 'C+'
            notes.append(f'風險封頂: 3項風險 → 封頂C+')
    if risk == 2:
        if grade_idx(grade) < grade_idx('B'):
            grade = 'B'
            notes.append(f'風險封頂: 2項風險 → 封頂B')
    
    # 2. Overvalue correction
    if horse.get('overvalue_flag'):
        sec = dims.get('sectional', '').strip()
        scn = dims.get('scenario', '').strip()
        if sec != '✅' and scn != '✅':
            if grade_idx(grade) < grade_idx('B'):
                grade = 'B'
                notes.append('溢價封頂: 段速/情境非✅ → 封頂B')
    
    # 3. 3YO top weight cap
    if horse.get('is_3yo') and horse.get('weight_lbs', 0) >= 133:
        if grade_idx(grade) < grade_idx('B+'):
            grade = 'B+'
            notes.append('三歲頂磅封頂: ≥133lb → 封頂B+')

    # 4. HV Weight gap cap
    if ctx.get('venue') == 'HV':
        w = horse.get('weight_lbs', 0)
        lightest = horse.get('field_lightest_weight', w)
        gap = w - lightest
        dist = ctx.get('distance', 1200)
        # Distance modifier
        adj = -2 if dist <= 1200 else (2 if dist >= 1650 else 0)
        if w >= 130 and gap >= (21 + adj):
            if grade_idx(grade) < grade_idx('B+'):
                grade = 'B+'
                notes.append(f'谷草重度磅差: {gap}lb → 封頂B+')
        elif w >= 130 and gap >= (18 + adj):
            if grade_idx(grade) < grade_idx('A-'):
                grade = 'A-'
                notes.append(f'谷草中度磅差: {gap}lb → 封頂A-')
        elif w >= 130 and gap >= (15 + adj):
            grade = grade_down(grade, 1) if grade_idx(grade) <= grade_idx('A-') else grade
            if gap >= (15 + adj):
                notes.append(f'谷草輕度磅差: {gap}lb → 降半級')
    
    # 5. Floor rules (lower priority than caps)
    stab_idx = horse.get('stability_index', 0)
    if stab_idx > 0.7:  # Super iron legs
        if grade_idx(grade) > grade_idx('B+'):
            grade = 'B+'
            notes.append('超級鐵腳保底: 穩定指數>0.7 → 保底B+')
    elif stab_idx > 0.5:  # Iron legs
        if grade_idx(grade) > grade_idx('B'):
            grade = 'B'
            notes.append('鐵腳保底: 穩定指數>0.5 → 保底B')
    
    # 6. Class override
    sec = dims.get('sectional', '').strip()
    cls = dims.get('class_advantage', '').strip()
    eem = dims.get('eem', '').strip()
    if sec == '✅' and (cls == '✅' or eem == '✅'):
        if grade_idx(grade) > grade_idx('B'):
            grade = 'B'
            notes.append('級數首選保底: 段速✅+級數/EEM✅ → 保底B')
    
    # 7. Track specialist floor
    if horse.get('same_venue_dist_wins', 0) >= 5:
        if grade_idx(grade) > grade_idx('C+'):
            grade = 'C+'
            notes.append('場地專家保底: ≥5勝同場同程 → 保底C+')
    
    return grade, '; '.join(notes) if notes else '無'


# ── SIP-RR20: Risk Discount Ranking ──────────────

def compute_effective_ticks(horse: dict, counts: dict, ctx: dict) -> float:
    """Compute effective ✅ count with risk discounts for tie-breaking."""
    eff = float(counts['total_strong'])
    discounts = []
    
    # Top weight
    if horse.get('is_top_weight'):
        eff -= 0.5; discounts.append('頂磅-0.5')
    
    # Wide barrier (>=75% of field)
    if horse.get('barrier', 0) >= horse.get('field_size', 14) * 0.75:
        eff -= 0.5; discounts.append('大外檔-0.5')
    
    # Weak jockey
    if horse.get('jockey_rank', 0) > horse.get('field_size', 14) * 0.5:
        eff -= 0.25; discounts.append('弱騎師-0.25')
        if horse.get('jockey_first_ride'):
            eff -= 0.25; discounts.append('首配-0.25')
    
    # Weight gain
    if horse.get('weight_gain_lbs', 0) >= 6:
        eff -= 0.25; discounts.append(f"+{horse['weight_gain_lbs']}lb-0.25")
        # Compound: weight gain + quick backup
        if horse.get('days_since_last', 99) <= 21:
            eff -= 0.5; discounts.append('加磅+密跑-0.5')
    
    # Stable placer bonus
    last4 = horse.get('last_4_finishes', [])
    if len(last4) >= 4 and sum(1 for f in last4[-6:] if f <= 5) >= 4:
        if any(f <= 3 for f in last4):
            eff += 0.25; discounts.append('穩定入位+0.25')
    
    # HV heavy weight penalty
    if ctx.get('venue') == 'HV':
        w = horse.get('weight_lbs', 0)
        lightest = horse.get('field_lightest_weight', w)
        if w >= 130 and (w - lightest) >= 15:
            eff -= 0.5; discounts.append('谷草磅差-0.5')
        if w <= lightest + 2:
            eff += 0.25; discounts.append('谷草輕磅+0.25')
    
    # Cap total discount
    total_discount = counts['total_strong'] - eff
    if total_discount > 1.5:
        eff = counts['total_strong'] - 1.5
    
    return eff, discounts


# ── Main Compute ──────────────

def compute_grade(horse: dict, ctx: dict) -> dict:
    dims = horse['dimensions']
    counts = count_dimensions(dims)
    
    if horse.get('forgiveness_bonus'):
        counts['aux_strong'] += 1
        counts['total_strong'] += 1
    
    base_grade, base_rule = lookup_base_grade(counts)
    
    # S- quality gate
    if base_grade == 'S-':
        if horse.get('micro_down'):
            base_grade = 'A+'
            base_rule += ' | S-品質閘門:有降級因素→A+'
        elif horse.get('risk_markers', 0) >= 2:
            base_grade = 'A+'
            base_rule += ' | S-品質閘門:風險≥2→A+'
        elif horse.get('same_venue_dist_top3', 0) == 0 and not horse.get('is_debut'):
            base_grade = 'A+'
            base_rule += ' | S-品質閘門:首跑此場地→A+'
    
    constrained_grade, constraint_note = apply_core_constraint(base_grade, counts, dims)
    adjusted_grade, micro_note = apply_micro_adjustments(
        constrained_grade, horse.get('micro_up', []), horse.get('micro_down', [])
    )
    
    # D-grade scan
    scanned_grade, scan_note = d_grade_longshot_scan(adjusted_grade, horse)
    
    # B+ HV upgrade scan
    upgraded_grade, upgrade_note = b_plus_upgrade_scan(scanned_grade, horse, ctx)
    
    # Override rules
    final_grade, override_note = apply_overrides(upgraded_grade, horse, counts, dims, ctx)
    
    # Effective ticks for ranking
    eff_ticks, discounts = compute_effective_ticks(horse, counts, ctx)
    
    return {
        'num': horse['num'],
        'name': horse['name'],
        'counts': counts,
        'base_grade': base_grade, 'base_rule': base_rule,
        'constraint_note': constraint_note,
        'micro_note': micro_note,
        'scan_note': scan_note,
        'upgrade_note': upgrade_note,
        'override_note': override_note,
        'final_grade': final_grade,
        'effective_ticks': eff_ticks,
        'risk_discounts': discounts,
        'dimensions': dims,
    }


def format_matrix_block(r: dict) -> str:
    dims = r['dimensions']
    c = r['counts']
    lines = ["#### 📊 評級矩陣 (Step 14)"]
    for dk in ['stability', 'sectional', 'eem', 'trainer_signal',
               'scenario', 'distance_freshness', 'form_line', 'class_advantage']:
        label, tier = DIMENSION_LABELS[dk]
        v = dims.get(dk, '➖')
        if v in ('N/A', '不計入'):
            lines.append(f"- {label} [{tier}]: `[不計入]` | 理據: `[{{{{LLM_FILL}}}}]`")
        else:
            lines.append(f"- {label} [{tier}]: `[{v}]` | 理據: `[{{{{LLM_FILL}}}}]`")
    
    cw = '有' if c['has_core_weak'] else '無'
    lines.append(f"- **🔢 矩陣算術:** 核心✅={c['core_strong']} | 半核心✅={c['semi_strong']} | "
                 f"輔助✅={c['aux_strong']} | 總❌={c['total_weak']} | 核心❌={cw} → 查表命中行={r['base_grade']}")
    lines.append(f"- **基礎評級:** `[{r['base_grade']}]` | **規則**: `[{r['base_rule']}]`")
    if r['constraint_note']:
        lines.append(f"- **核心防護牆:** `[{r['constraint_note']}]`")
    lines.append(f"- **微調:** `[{r['micro_note']}]`")
    if r['scan_note']:
        lines.append(f"- **冷門掃描:** `[{r['scan_note']}]`")
    if r['upgrade_note']:
        lines.append(f"- **B+升級掃描:** `[{r['upgrade_note']}]`")
    lines.append(f"- **覆蓋規則:** `[{r['override_note']}]`")
    if r['risk_discounts']:
        lines.append(f"- **SIP-RR20 折扣:** {', '.join(r['risk_discounts'])} → 有效✅={r['effective_ticks']:.2f}")
    lines.append(f"\n⭐ **最終評級:** `[{r['final_grade']}]`")
    return '\n'.join(lines)


def rank_horses(results: list) -> list:
    def sort_key(r):
        gi = grade_idx(r['final_grade'])
        return (gi, -r['effective_ticks'], r['counts']['total_weak'])
    return sorted(results, key=sort_key)


def generate_verdict(ranked: list) -> str:
    """Generate complete Part 3 + Part 4 skeleton with Python-prefilled data."""
    labels = ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']
    lines = [
        "#### [第三部分] 最終預測 (The Verdict)\n",
        "- **跑道形勢:** {{LLM_FILL}}",
        "- **信心指數:** `{{LLM_FILL}}`",
        "- **關鍵變數:** {{LLM_FILL}}\n",
        "**🏆 Top 4 位置精選**\n",
    ]
    for i, r in enumerate(ranked[:4]):
        lines.append(labels[i])
        lines.append(f"- **馬號及馬名:** {r['num']} {r['name']}")
        lines.append(f"- **評級與✅數量:** `[{r['final_grade']}]` | ✅ {r['counts']['total_strong']} (有效: {r['effective_ticks']:.1f})")
        lines.append(f"- **核心理據:** {{{{LLM_FILL}}}}")
        lines.append(f"- **最大風險:** {{{{LLM_FILL}}}}")
        lines.append("")

    # Top 2 Place Confidence
    if len(ranked) >= 2:
        lines.append("**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**")
        lines.append(f"🥇 {ranked[0]['name']}:`{{{{LLM_FILL}}}}` — 最大威脅:{{{{LLM_FILL}}}}")
        lines.append(f"🥈 {ranked[1]['name']}:`{{{{LLM_FILL}}}}` — 最大威脅:{{{{LLM_FILL}}}}")
        lines.append("")

    # Pace Flip Insurance
    lines.append("**🔄 步速逆轉保險 (Pace Flip Insurance):**")
    lines.append("- 若步速比預測更快 → 最受惠:{{LLM_FILL}} | 最受損:{{LLM_FILL}}")
    lines.append("- 若步速比預測更慢 → 最受惠:{{LLM_FILL}} | 最受損:{{LLM_FILL}}")
    lines.append("")

    # Emergency Brake Protocol (auto-check)
    lines.append("**🚨 緊急煞車檢查 (Emergency Brake Protocol):**")
    top4 = ranked[:4]
    top4_grades = [r['final_grade'] for r in top4]
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

    # Part 4: Blind Spots
    lines.append("---\n")
    lines.append("#### [第四部分] 分析盲區\n")
    lines.append("**1. 段速含金量:** {{LLM_FILL}}")
    lines.append("**2. 風險管理:** {{LLM_FILL}}")
    lines.append("**3. 試閘與預期假象:** {{LLM_FILL}}")
    lines.append("**4. 特定與場地風險:** {{LLM_FILL}}")
    lines.append("**5. 步速情境分支:**")
    lines.append("- 快步速:最利 → {{LLM_FILL}};最不利 → {{LLM_FILL}}")
    lines.append("- 慢步速:最利 → {{LLM_FILL}};最不利 → {{LLM_FILL}}")
    lines.append("**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse):** {{LLM_FILL}}")
    lines.append("**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):** {{LLM_FILL}}")
    lines.append("")

    return '\n'.join(lines)


def generate_csv(ranked: list, race_id: str = 'Race_X') -> str:
    lines = ["```csv", "race_id,horse_number,horse_name,grade,total_ticks,eff_ticks,total_crosses,verdict,risk_level"]
    for i, r in enumerate(ranked):
        v = f"TOP4_{i+1}" if i < 4 else f"RATING_{r['final_grade'].replace('+','P').replace('-','M')}"
        rl = 'LOW' if r['counts']['total_weak'] == 0 else ('MED' if r['counts']['total_weak'] <= 2 else 'HIGH')
        lines.append(f"{race_id},{r['num']},{r['name']},{r['final_grade']},{r['counts']['total_strong']},{r['effective_ticks']:.1f},{r['counts']['total_weak']},{v},{rl}")
    lines.append("```")
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="HKJC Wong Choi — Rating Matrix Calculator")
    parser.add_argument("--input", type=str, help="Path to dimensions JSON file")
    parser.add_argument("--race-id", type=str, default="Race_X")
    parser.add_argument("--output", type=str, default=None)
    args = parser.parse_args()

    if not args.input:
        print("Usage: python3 compute_rating_matrix_hkjc.py --input <dims.json> [--race-id HV_R7]")
        sys.exit(0)

    if not Path(args.input).exists():
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    ctx = data.get('race_context', {})
    horses = data.get('horses', [])

    if not horses:
        print("❌ No horses"); sys.exit(1)

    results = [compute_grade(h, ctx) for h in horses]
    ranked = rank_horses(results)

    out = []
    out.append("# 📊 HKJC Rating Matrix 計算結果\n")
    for r in results:
        out.append(f"\n## [{r['num']}] {r['name']}")
        out.append(format_matrix_block(r))
        out.append("")
    out.append("\n---\n## 🏆 自動排名 Top 4\n")
    out.append(generate_verdict(ranked))
    out.append("\n---\n## 📊 CSV 匯出\n")
    out.append(generate_csv(ranked, args.race_id))

    result_text = '\n'.join(out)
    if args.output:
        Path(args.output).write_text(result_text, encoding='utf-8')
        top4_str = ', '.join(f"{r['name']}({r['final_grade']})" for r in ranked[:4])
        print(f"✅ Rating matrix computed: {args.output}")
        print(f"   📊 {len(horses)} horses | Top 4: {top4_str}")
    else:
        print(result_text)


if __name__ == '__main__':
    main()
