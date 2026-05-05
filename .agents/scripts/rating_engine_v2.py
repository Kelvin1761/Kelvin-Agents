#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
"""
rating_engine_v2.py — Universal Qualitative Rating Engine v2
============================================================
Canonical grading system for HKJC and AU horse racing analysis.

Design: Qualitative pattern matching (NOT weighted scoring).
Both HKJC and AU import this module for base grade + shared logic.

Flow:
  1. LLM assigns ticks to dimensions → count_dimensions()
  2. lookup_base_grade() → pattern match against rule table
  3. apply_core_constraint() → core fail wall
  4. apply_micro_adjustments() → ±1 grade step
  5. apply_s_grade_guards() → SIP-9/SL01 inflation prevention
  6. Platform-specific overrides (in HKJC/AU scripts)
"""

# Grade hierarchy from best to worst
GRADE_ORDER = ['S+', 'S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D']


# ── Grade Utilities ──────────────────────────────────

def grade_idx(g: str) -> int:
    """Get sort index for a grade (lower = better). Unknown = 99."""
    return GRADE_ORDER.index(g) if g in GRADE_ORDER else 99


def grade_up(g: str, n: int = 1) -> str:
    """Move grade up (better) by n steps. Cannot exceed S."""
    i = grade_idx(g)
    return GRADE_ORDER[max(0, i - n)]


def grade_down(g: str, n: int = 1) -> str:
    """Move grade down (worse) by n steps. Cannot go below D."""
    i = grade_idx(g)
    return GRADE_ORDER[min(len(GRADE_ORDER) - 1, i + n)]


# ── Step 14.1: Count Dimensions ─────────────────────

def count_dimensions(dims: dict, type_map: dict) -> dict:
    """
    Count tick marks by dimension type.

    Args:
        dims: {'stability': '✅', 'sectional': '❌', ...}
        type_map: {'stability': 'core', 'position': 'semi_core', ...}

    Returns dict with core_strong, semi_strong, aux_strong,
    total_strong, total_weak, has_core_weak, etc.
    """
    counts = {
        'core_strong': 0, 'core_neutral': 0, 'core_weak': 0,
        'semi_strong': 0, 'semi_neutral': 0, 'semi_weak': 0,
        'aux_strong': 0, 'aux_neutral': 0, 'aux_weak': 0,
        'total_strong': 0, 'total_weak': 0,
        'has_core_weak': False,
    }
    for dim_key, value in dims.items():
        v = str(value).strip()
        if v in ('N/A', '不計入', ''):
            continue
        dim_type = type_map.get(dim_key, 'auxiliary')
        # 5-tier display + 3-tier calculation:
        # ✅✅ and ✅ both count as 1 pass (not 2)
        # ❌❌ and ❌ both count as 1 fail (not 2)
        # Double-ticks are for display/tiebreaking only
        if '✅' in v:
            counts['total_strong'] += 1
            if dim_type == 'core':
                counts['core_strong'] += 1
            elif dim_type == 'semi_core':
                counts['semi_strong'] += 1
            else:
                counts['aux_strong'] += 1
        elif '❌' in v:
            counts['total_weak'] += 1
            if dim_type == 'core':
                counts['core_weak'] += 1
                counts['has_core_weak'] = True
            elif dim_type == 'semi_core':
                counts['semi_weak'] += 1
            else:
                counts['aux_weak'] += 1
        else:
            if dim_type == 'core':
                counts['core_neutral'] += 1
            elif dim_type == 'semi_core':
                counts['semi_neutral'] += 1
            else:
                counts['aux_neutral'] += 1
    return counts


# ── Step 14.2: Base Grade Lookup (Qualitative Pattern Matching) ──

def lookup_base_grade(c: dict) -> tuple:
    """
    Strict qualitative pattern matching.
    Same dimension pattern ALWAYS produces the same base grade.
    Identical rule table for both HKJC and AU.
    """
    cs = c['core_strong']
    ss = c['semi_strong']
    axs = c['aux_strong']
    tw = c['total_weak']

    # V4.2: A+ = full package (was S). S-tier only via ✅✅ promotion.
    if cs >= 2 and ss >= 2 and axs >= 2 and tw == 0:
        return 'A+', f'2核心✅ + 2半核心✅ + {axs}輔助✅ + 0❌ (全滿)'
    if cs >= 2 and tw == 0:
        return 'A', f'2核心✅ + 0❌'
    if (cs >= 1 and ss >= 1 and tw == 0) or (cs >= 2 and tw <= 1):
        return 'A-', f'{cs}核心✅ + {ss}半核心✅ + {tw}❌'
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


# ── Core Constraint Wall ─────────────────────────────

def apply_core_constraint(grade: str, counts: dict, dims: dict,
                          sectional_key: str = 'sectional',
                          position_key: str = '形勢與走位') -> tuple:
    """
    Core ❌ → hard cap at B+.
    Exception: sectional ✅ + position ✅ → cap at A-.
    """
    if not counts['has_core_weak']:
        return grade, ''
    sec = str(dims.get(sectional_key, '')).strip()
    pos = str(dims.get(position_key, '')).strip()
    if '✅' in sec and '✅' in pos:
        if grade_idx(grade) < grade_idx('A-'):
            return 'A-', '核心❌但段速✅+形勢✅豁免 → 封頂A-'
        return grade, ''
    if grade_idx(grade) < grade_idx('B+'):
        return 'B+', '核心防護牆: 核心❌ → 封頂B+'
    return grade, ''


# ── Step 14.2B: Micro-adjustments ────────────────────

def apply_micro_adjustments(grade: str, up: list, down: list) -> tuple:
    """Apply fine-tune ±1 grade step. Net +/- only."""
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


# ── S-Grade Inflation Guards (SIP-9 + SIP-SL01 + SIP-AU-020) ─────

def apply_s_grade_guards(grade: str, horse: dict, counts: dict,
                         dims: dict, ctx: dict,
                         sectional_key: str = 'sectional',
                         class_key: str = 'class_advantage',
                         double_ticks: int = -1) -> tuple:
    """
    S-grade inflation prevention guards.
    Applies to both HKJC and AU.

    SIP-9:     S/S- must have sectional ✅ or class ✅ (hard proof)
    SIP-SL01:  S/S-/A+ must have recent top-3 finish in last 3 starts
    SIP-AU-020: V4.2 conviction gate mirrors promotion steps:
                S- requires ≥1 ✅✅, S requires ≥2 ✅✅, S+ requires ≥3 ✅✅

    Args:
        double_ticks: Number of ✅✅ dimensions. Pass -1 to skip SIP-AU-020.
    """
    notes = []

    # Only applies to S-tier grades
    if grade_idx(grade) > grade_idx('A+'):
        return grade, ''

    # ── SIP-AU-020: Double-Tick Conviction Gate ──
    # V4.2 S-tier is promotion-only: S-/S/S+ require 1/2/3 promotion evidence.
    if double_ticks >= 0 and grade in ('S+', 'S', 'S-'):
        if grade == 'S+' and double_ticks < 3:
            grade = 'A+'
            notes.append(f'SIP-AU-020信心度: S+級需≥3個✅✅ (實際{double_ticks}) → 封頂A+')
        elif grade == 'S' and double_ticks < 2:
            grade = 'A+'
            notes.append(f'SIP-AU-020信心度: S級需≥2個✅✅ (實際{double_ticks}) → 封頂A+')
        elif grade == 'S-' and double_ticks < 1:
            grade = 'A+'
            notes.append(f'SIP-AU-020信心度: S-級需≥1個✅✅ (實際{double_ticks}) → 封頂A+')

    # ── SIP-9: Purity Guard ──
    # S/S- requires hard proof: sectional OR class must be ✅
    if grade in ('S', 'S-'):
        sec = str(dims.get(sectional_key, '')).strip()
        cls = str(dims.get(class_key, '')).strip()
        has_hard_proof = ('✅' in sec) or ('✅' in cls)
        if not has_hard_proof:
            if grade_idx(grade) < grade_idx('A+'):
                grade = 'A+'
                notes.append('SIP-9純度: S/S-無段速/級數硬性✅ → 封頂A+')

    # ── SIP-SL01: Recency & Hardness Guard ──
    # S/S- must have at least 1 top-3 finish in last 3 starts
    if grade in ('S', 'S-'):
        recent_top3 = horse.get('recent_3_top3', None)
        if recent_top3 is not None and not recent_top3:
            if grade_idx(grade) < grade_idx('A+'):
                grade = 'A+'
                notes.append('SIP-SL01實戰驗證: 近3仗無入位 → 封頂A+')

    # ── SIP-SL01 Extension: A+ Third-up Check ──
    # A+ with core stability based purely on Third-up + no recent placing
    if grade == 'A+':
        third_up_only = horse.get('stability_third_up_only', False)
        recent_top3 = horse.get('recent_3_top3', None)
        if third_up_only and recent_top3 is not None and not recent_top3:
            grade = 'A'
            notes.append('SIP-SL01擴展: A+純靠Third-up無近期入位 → 降A')

    return grade, '; '.join(notes) if notes else ''


# ── Backward-Compatible Shims (from deprecated grading_engine.py) ──
# These allow consumers to migrate imports without changing function calls.
# Internally they use the qualitative method, NOT weighted scoring.

def parse_matrix_scores(matrix_data: dict, schema: dict) -> tuple:
    """
    Parse a matrix dictionary using the provided schema.
    schema: {"stability": "core", "position": "semi", ...}
    Returns: (core_pass, semi_pass, aux_pass, core_fail, total_fail)

    5-tier display + 3-tier calculation (V9.5):
    ✅✅ and ✅ both count as 1 pass (not 2).
    ❌❌ and ❌ both count as 1 fail (not 2).
    Double-ticks are preserved for display and tiebreaking only.
    """
    core_pass = semi_pass = aux_pass = 0
    core_fail = total_fail = 0

    for key, c_type in schema.items():
        if key not in matrix_data:
            continue
        item = matrix_data[key]
        score_str = str(item.get('score', '➖') if isinstance(item, dict) else item)

        # V9.5: ✅✅ counts as 1 pass, ❌❌ counts as 1 fail
        # (Double-ticks are display/tiebreaker only, not double-counted)
        passes = 1 if '✅' in score_str else 0
        fails = 1 if '❌' in score_str else 0

        if c_type in ('core',):
            core_pass += passes
            core_fail += fails
        elif c_type in ('semi', 'semi_core'):
            semi_pass += passes
        elif c_type in ('aux', 'auxiliary'):
            aux_pass += passes
        total_fail += fails

    return core_pass, semi_pass, aux_pass, core_fail, total_fail


def count_double_ticks(matrix_data: dict, schema: dict = None) -> int:
    """Count ✅✅ double-ticks for tiebreaking. Higher = stronger conviction."""
    count = 0
    data = matrix_data if schema is None else matrix_data
    for key, item in data.items():
        score_str = str(item.get('score', '➖') if isinstance(item, dict) else item)
        if '✅✅' in score_str:
            count += 1
    return count


def compute_base_grade(core_pass: int, semi_pass: int, aux_pass: int,
                       core_fail: int, total_fail: int,
                       matrix_dims: dict = None,
                       sectional_key: str = '段速與引擎',
                       position_key: str = '形勢與走位') -> str:
    """Shim: compute base grade from tick counts (qualitative, not weighted).
    
    V9.5: When matrix_dims is provided, applies Core Engine Wall
    (core ❌ → hard cap B+, with sectional✅+position✅ exception → A-).
    """
    counts = {
        'core_strong': core_pass, 'semi_strong': semi_pass, 'aux_strong': aux_pass,
        'total_strong': core_pass + semi_pass + aux_pass, 'total_weak': total_fail,
        'has_core_weak': core_fail > 0,
        'core_neutral': 0, 'semi_neutral': 0, 'aux_neutral': 0,
        'core_weak': core_fail, 'semi_weak': 0, 'aux_weak': 0,
    }
    grade, _ = lookup_base_grade(counts)
    
    # V9.5: Apply Core Engine Wall when matrix dims are available
    if matrix_dims is not None and counts['has_core_weak']:
        # Build dims lookup from matrix_dims for apply_core_constraint
        dims = {}
        for k, v in matrix_dims.items():
            score = v.get('score', '➖') if isinstance(v, dict) else str(v)
            dims[k] = score
        grade, _ = apply_core_constraint(grade, counts, dims,
                                         sectional_key=sectional_key,
                                         position_key=position_key)
    
    return grade


def compute_weighted_score(core_pass: int, semi_pass: int, aux_pass: int,
                           core_fail: int, total_fail: int) -> int:
    """Shim: kept for display purposes only. NOT used for grading anymore."""
    score = (core_pass * 3) + (semi_pass * 2) + (aux_pass * 1)
    score -= core_fail * 4
    non_core_fail = total_fail - core_fail
    score -= non_core_fail * 1
    return score


def apply_fine_tune(base_grade: str, direction: str) -> str:
    """Shim: apply ±1 grade step from direction string (+/-/=)."""
    if base_grade not in GRADE_ORDER:
        return base_grade
    idx = GRADE_ORDER.index(base_grade)
    direction = (direction or '').strip()
    if direction == '+':
        idx = max(0, idx - 1)
    elif direction == '-':
        idx = min(len(GRADE_ORDER) - 1, idx + 1)
    return GRADE_ORDER[idx]


def grade_sort_index(grade: str) -> int:
    """Alias for grade_idx (backward-compatible name)."""
    return grade_idx(grade)


# ── Self-Test ────────────────────────────────────────

def _self_test():
    """Validate grading engine against known test cases."""
    print('=' * 70)
    print('Rating Engine v2 — Self-Test (Qualitative Pattern Matching)')
    print('=' * 70)

    all_pass = True

    # ── Test 1: lookup_base_grade ──
    print('\n[1] Base Grade Lookup Tests:')
    grade_tests = [
        # (label, core, semi, aux, total_weak, expected)
        ('A+ (full house)',            2, 2, 2, 0, 'A+'),
        ('A+ (3 aux)',                 2, 2, 3, 0, 'A+'),
        ('A  (2c+1s+1a)',             2, 1, 1, 0, 'A'),
        ('A  (2c only)',              2, 0, 0, 0, 'A'),
        ('A- (1c+1s+0x)',             1, 1, 0, 0, 'A-'),
        ('A- (2c+1x)',                2, 0, 0, 1, 'A-'),
        ('A- (1c+0x)',                1, 0, 0, 0, 'A-'),
        ('A- (1c+1x)',                1, 0, 0, 1, 'A-'),
        ('B+ (1c+2x)',                1, 0, 0, 2, 'B+'),
        ('B+ (2s+0x setup)',          0, 2, 0, 0, 'B+'),
        ('B  (1s+2a+1x)',             0, 1, 2, 1, 'B'),
        ('B- (0c/0s+3a)',             0, 0, 3, 0, 'B-'),
        ('C+ (3x+1c save)',           1, 0, 0, 3, 'C+'),
        ('C  (3x no save)',           0, 0, 0, 3, 'C'),
        ('C- (4x)',                   0, 0, 0, 4, 'C-'),
        ('D+ (5x+has tick)',          1, 0, 0, 5, 'D+'),
        ('D  (5x+no tick)',           0, 0, 0, 5, 'D'),
    ]
    for label, cs, ss, axs, tw, expected in grade_tests:
        counts = {
            'core_strong': cs, 'semi_strong': ss, 'aux_strong': axs,
            'total_strong': cs + ss + axs, 'total_weak': tw,
            'has_core_weak': False,
            'core_neutral': 0, 'semi_neutral': 0, 'aux_neutral': 0,
            'core_weak': 0, 'semi_weak': 0, 'aux_weak': 0,
        }
        result, _ = lookup_base_grade(counts)
        ok = '\u2705' if result == expected else '\u274c'
        if result != expected:
            all_pass = False
        print(f'  {ok} {label}: got={result} expected={expected}')

    # ── Test 2: Core Constraint ──
    print('\n[2] Core Constraint Tests:')
    cc_tests = [
        ('A+ + core fail -> B+', 'A+', True, '\u27a1\ufe0f', '\u27a1\ufe0f', 'B+'),
        ('A+ + core fail + sec+pos pass -> A-', 'A+', True, '✅', '✅', 'A-'),
        ('B + core fail -> B (already below)', 'B', True, '\u27a1\ufe0f', '\u27a1\ufe0f', 'B'),
        ('S + no core fail -> S', 'S', False, '\u2705', '\u2705', 'S'),
    ]
    for label, g, has_cw, sec, pos, expected in cc_tests:
        counts = {'has_core_weak': has_cw}
        dims = {'sectional': sec, '形勢與走位': pos}
        result, _ = apply_core_constraint(g, counts, dims)
        ok = '\u2705' if result == expected else '\u274c'
        if result != expected:
            all_pass = False
        print(f'  {ok} {label}: got={result}')

    # ── Test 3: Micro Adjustments ──
    print('\n[3] Micro Adjustment Tests:')
    ma_tests = [
        ('A + up -> A+', 'A', ['pace'], [], 'A+'),
        ('A + down -> A-', 'A', [], ['barrier'], 'A-'),
        ('A + up+down -> A', 'A', ['pace'], ['barrier'], 'A'),
        ('S + up -> S+ (V4.2)', 'S', ['pace'], [], 'S+'),
        ('D + down -> D (floor)', 'D', [], ['weight'], 'D'),
    ]
    for label, g, up, down, expected in ma_tests:
        result, _ = apply_micro_adjustments(g, up, down)
        ok = '\u2705' if result == expected else '\u274c'
        if result != expected:
            all_pass = False
        print(f'  {ok} {label}: got={result}')

    # ── Test 4: S-Grade Guards (legacy, no double_ticks) ──
    print('\n[4] S-Grade Guard Tests (SIP-9 + SIP-SL01):')
    sg_tests = [
        ('S + no hard proof -> A+',
         'S', {'sectional': '\u27a1\ufe0f', 'class_advantage': '\u27a1\ufe0f'}, True, 'A+'),
        ('S + sec pass -> S (pass SIP-9)',
         'S', {'sectional': '\u2705', 'class_advantage': '\u27a1\ufe0f'}, True, 'S'),
        ('S + cls pass -> S (pass SIP-9)',
         'S', {'sectional': '\u27a1\ufe0f', 'class_advantage': '\u2705'}, True, 'S'),
        ('S- + no recent top3 -> A+',
         'S-', {'sectional': '\u2705', 'class_advantage': '\u27a1\ufe0f'}, False, 'A+'),
        ('S- + sec pass + recent top3 -> S-',
         'S-', {'sectional': '\u2705', 'class_advantage': '\u27a1\ufe0f'}, True, 'S-'),
        ('A -> A (guards skip)',
         'A', {'sectional': '\u27a1\ufe0f', 'class_advantage': '\u27a1\ufe0f'}, False, 'A'),
    ]
    for label, g, dims, recent_ok, expected in sg_tests:
        horse = {'recent_3_top3': recent_ok}
        counts = {'core_strong': 2, 'semi_strong': 2, 'aux_strong': 2,
                  'total_strong': 6, 'total_weak': 0}
        result, note = apply_s_grade_guards(g, horse, counts, dims, {})
        ok = '\u2705' if result == expected else '\u274c'
        if result != expected:
            all_pass = False
        print(f'  {ok} {label}: got={result} {f"({note})" if note else ""}')

    # ── Test 5: SIP-AU-020 Double-Tick Conviction Gate ──
    print('\n[5] SIP-AU-020 Double-Tick Conviction Gate:')
    dt_tests = [
        # (label, grade, double_ticks, expected)
        ('S+ + 3 dticks -> S+ (pass)',  'S+', 3, 'S+'),
        ('S+ + 2 dticks -> A+ (fail)',  'S+', 2, 'A+'),
        ('S + 2 dticks -> S (pass)',    'S',  2, 'S'),
        ('S + 1 dtick -> A+ (fail)',    'S',  1, 'A+'),
        ('S- + 1 dtick -> S- (pass)',   'S-', 1, 'S-'),
        ('S- + 0 dticks -> A+ (fail)',  'S-', 0, 'A+'),
        ('S + 3 dticks -> S (pass)',    'S',  3, 'S'),
        ('S + 1 dtick -> A+ (fail)',    'S',  1, 'A+'),
        ('S- + 3 dticks -> S- (pass)',  'S-', 3, 'S-'),
        ('A+ + 0 dticks -> A+ (skip)',  'A+', 0, 'A+'),
        ('S + -1 dticks -> S (skip)',   'S', -1, 'S'),
    ]
    for label, g, dt, expected in dt_tests:
        horse = {'recent_3_top3': True}
        counts = {'core_strong': 2, 'semi_strong': 2, 'aux_strong': 2,
                  'total_strong': 6, 'total_weak': 0}
        dims = {'sectional': '✅', 'class_advantage': '✅'}
        result, note = apply_s_grade_guards(g, horse, counts, dims, {},
                                            double_ticks=dt)
        ok = '\u2705' if result == expected else '\u274c'
        if result != expected:
            all_pass = False
        print(f'  {ok} {label}: got={result} {f"({note})" if note else ""}')

    msg = 'All tests passed! \u2705' if all_pass else 'SOME TESTS FAILED \u274c'
    print(f'\n{msg}')
    return all_pass


if __name__ == '__main__':
    import sys
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    success = _self_test()
    sys.exit(0 if success else 1)
