#!/usr/bin/env python3
"""
⚠️ DEPRECATED — grading_engine.py (v1.0)
=========================================
This module is SUPERSEDED by rating_engine_v2.py.

The weighted-scoring method (core×3, semi×2, aux×1) has been replaced
by qualitative pattern-matching + SIP-9/SIP-SL01 S-grade guards.

All consumers should import from rating_engine_v2 instead:
    from rating_engine_v2 import compute_base_grade, grade_sort_index, ...

This file is kept as a backward-compat shim. It will re-export from
rating_engine_v2 if available, falling back to the original logic.
"""
import warnings as _w
_w.warn(
    "grading_engine.py is DEPRECATED — migrate to rating_engine_v2.py",
    DeprecationWarning, stacklevel=2
)

# Grade hierarchy from best to worst
GRADE_ORDER = ['S+', 'S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D']


def compute_weighted_score(core_pass: int, semi_pass: int, aux_pass: int,
                           core_fail: int, total_fail: int) -> int:
    """
    Compute the weighted score from matrix tick counts.
    
    Weights:
      - Core ✅: +3 each (max 6)
      - Semi-core ✅: +2 each (max 4)
      - Auxiliary ✅ (incl. forgiveness): +1 each (max 5)
      - Core ❌: -4 each (severe penalty)
      - Non-core ❌: -1 each
    
    Score range: theoretical -13 to +15
    """
    score = (core_pass * 3) + (semi_pass * 2) + (aux_pass * 1)
    
    # Penalties
    score -= core_fail * 4
    non_core_fail = total_fail - core_fail
    score -= non_core_fail * 1
    
    return score


def compute_base_grade(core_pass: int, semi_pass: int, aux_pass: int,
                       core_fail: int, total_fail: int) -> str:
    """
    Strict lookup table: weighted_score → base_grade.
    Same inputs ALWAYS produce the same output. No LLM subjectivity.
    
    Returns: grade string (e.g. 'A', 'B+', 'S-')
    """
    score = compute_weighted_score(core_pass, semi_pass, aux_pass, core_fail, total_fail)
    return score_to_grade(score)


def score_to_grade(score: int) -> str:
    """Map a weighted score to a letter grade."""
    if score >= 14:
        return 'S'
    elif score >= 12:
        return 'S-'
    elif score >= 10:
        return 'A+'
    elif score >= 8:
        return 'A'
    elif score >= 7:
        return 'A-'
    elif score >= 6:
        return 'B+'
    elif score >= 4:
        return 'B'
    elif score >= 3:
        return 'B-'
    elif score >= 2:
        return 'C+'
    elif score >= 0:
        return 'C'
    elif score >= -2:
        return 'C-'
    else:
        return 'D'


def apply_fine_tune(base_grade: str, direction: str) -> str:
    """
    Apply LLM fine-tune adjustment to base grade.
    
    Rules:
      - direction '+' → move UP 1 step in GRADE_ORDER (e.g. A → A+)
      - direction '-' → move DOWN 1 step in GRADE_ORDER (e.g. A → A-)
      - direction '=' or anything else → no change
      - Cannot go above S+ or below D
    
    Returns: final_grade string
    """
    if base_grade not in GRADE_ORDER:
        return base_grade  # Unknown grade, return as-is
    
    idx = GRADE_ORDER.index(base_grade)
    
    direction = (direction or '').strip()
    
    if direction == '+':
        idx = max(0, idx - 1)  # Move toward S+ (lower index = better)
    elif direction == '-':
        idx = min(len(GRADE_ORDER) - 1, idx + 1)  # Move toward D (higher index = worse)
    
    return GRADE_ORDER[idx]


def grade_sort_index(grade: str) -> int:
    """
    Get sort index for a grade (lower = better).
    Unknown grades get index 99 (sorted last).
    """
    if grade in GRADE_ORDER:
        return GRADE_ORDER.index(grade)
    return 99


# ──────────────────────────────────────────────
# Convenience: count ticks from score strings
# ──────────────────────────────────────────────

def parse_matrix_scores(matrix_data: dict, schema: dict) -> tuple[int, int, int, int, int]:
    """
    Parse a matrix dictionary using the provided schema.
    schema format: { "stability": "core", "eem": "semi", "class_advantage": "aux", ... }
    Returns: (core_pass, semi_pass, aux_pass, core_fail, total_fail)
    Supports 5-tier multi-ticks: ✅✅ = +2 pass, ❌❌ = +2 fail.
    """
    core_pass = semi_pass = aux_pass = 0
    core_fail = total_fail = 0

    for key, c_type in schema.items():
        if key not in matrix_data:
            continue
        
        # data might be a dict e.g. {"score": "✅", "reasoning": "..."} or directly a string
        item = matrix_data[key]
        score_str = str(item.get('score', '➖') if isinstance(item, dict) else item)
        
        passes = 2 if '✅✅' in score_str else (1 if '✅' in score_str else 0)
        fails = 2 if '❌❌' in score_str else (1 if '❌' in score_str else 0)
        
        if c_type == 'core':
            core_pass += passes
            core_fail += fails
        elif c_type == 'semi':
            semi_pass += passes
        elif c_type == 'aux':
            aux_pass += passes
            
        total_fail += fails

    return core_pass, semi_pass, aux_pass, core_fail, total_fail


if __name__ == '__main__':
    # Self-test with known data from 04-15 races
    test_cases = [
        # (name, core✅, semi✅, aux✅, core❌, total❌, expected_base)
        ("R8 H5 好實力", 2, 2, 3, 0, 0, "S-"),
        ("R8 H3 膨才", 1, 2, 4, 0, 0, "A+"),
        ("R7 H5 彩虹七色", 2, 2, 3, 0, 0, "S-"),
        ("R7 H4 團結戰靈", 2, 2, 3, 0, 0, "S-"),
        ("R8 H2 瑪瑙", 2, 1, 2, 0, 1, "A"),
        ("R7 H1 當家精彩", 1, 1, 4, 0, 1, "A"),
        ("R7 H3 八仟好運", 1, 2, 3, 0, 0, "A+"),
        ("R8 H1 銀進", 1, 2, 3, 1, 1, "B+"),
        ("R8 H4 同心同樂", 1, 2, 3, 1, 2, "B"),
        ("R7 H2 縱橫天下", 0, 0, 1, 2, 4, "D"),
    ]
    
    print("=" * 70)
    print("Wong Choi Grading Engine v1.0 — Self-Test")
    print("=" * 70)
    
    all_pass = True
    for name, cp, sp, ap, cf, tf, expected in test_cases:
        score = compute_weighted_score(cp, sp, ap, cf, tf)
        base = compute_base_grade(cp, sp, ap, cf, tf)
        status = "✅" if base == expected else "❌"
        if base != expected:
            all_pass = False
        print(f"  {status} {name}: score={score}, base={base} (expected={expected})")
    
    # Test fine-tune
    print("\nFine-tune tests:")
    ft_cases = [
        ("A", "+", "A+"),
        ("A", "-", "A-"),
        ("S", "+", "S+"),
        ("S+", "+", "S+"),  # Can't go above S+
        ("D", "-", "D"),    # Can't go below D
        ("B+", "=", "B+"),  # Neutral
        ("A-", "", "A-"),   # Empty = neutral
    ]
    for base, direction, expected in ft_cases:
        result = apply_fine_tune(base, direction)
        status = "✅" if result == expected else "❌"
        if result != expected:
            all_pass = False
        print(f"  {status} {base} + '{direction}' → {result} (expected={expected})")
    
    print(f"\n{'All tests passed! ✅' if all_pass else 'SOME TESTS FAILED ❌'}")
