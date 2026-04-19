#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
compute_rating_matrix.py — AU Wong Choi Protocol Rating Matrix Calculator
Mechanically computes the final grade from 8-dimension judgments.

Usage:
    python3 compute_rating_matrix.py --input <dimensions.json>
    python3 compute_rating_matrix.py --interactive

Input JSON format (per horse):
{
    "horses": [
        {
            "num": 1,
            "name": "Horse Name",
            "dimensions": {
                "fitness":  "✅",    // 核心: 狀態與穩定性
                "sectional": "✅",   // 核心: 段速與引擎
                "eem":       "➖",   // 半核心: EEM與形勢
                "jockey":    "✅",   // 半核心: 騎練訊號
                "class":     "✅",   // 輔助: 級數與負重
                "surface":   "➖",   // 輔助: 場地適性
                "form_line": "➖",   // 輔助: 賽績線
                "gear_dist": "➖"    // 輔助: 裝備與距離
            },
            "micro_up": [],        // 微調升級因素 (optional)
            "micro_down": [],      // 微調降級因素 (optional)
            "forgiveness_bonus": false  // 寬恕輔助加分 (optional)
        }
    ]
}

Output: Final grade + formatted matrix block per horse.
"""
import json
import sys
import argparse
from pathlib import Path


# ──────────────────────────────────────────────
# Grade Lookup Table (from 02f_synthesis.md)
# ──────────────────────────────────────────────

GRADE_ORDER = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D']

DIMENSION_TYPES = {
    'fitness':   'core',       # 狀態與穩定性
    'sectional': 'core',       # 段速與引擎
    'eem':       'semi_core',  # EEM與形勢
    'jockey':    'semi_core',  # 騎練訊號
    'class':     'auxiliary',  # 級數與負重
    'surface':   'auxiliary',  # 場地適性
    'form_line': 'auxiliary',  # 賽績線
    'gear_dist': 'auxiliary',  # 裝備與距離
}

DIMENSION_LABELS = {
    'fitness':   ('狀態與穩定性', '核心'),
    'sectional': ('段速與引擎', '核心'),
    'eem':       ('EEM與形勢', '半核心'),
    'jockey':    ('騎練訊號', '半核心'),
    'class':     ('級數與負重', '輔助'),
    'surface':   ('場地適性', '輔助'),
    'form_line': ('賽績線', '輔助'),
    'gear_dist': ('裝備與距離', '輔助'),
}


def count_dimensions(dims: dict) -> dict:
    """Count ✅, ➖, ❌ by dimension type."""
    counts = {
        'core_strong': 0, 'core_neutral': 0, 'core_weak': 0,
        'semi_strong': 0, 'semi_neutral': 0, 'semi_weak': 0,
        'aux_strong': 0,  'aux_neutral': 0,  'aux_weak': 0,
        'total_strong': 0, 'total_weak': 0,
        'has_core_weak': False,
    }

    for dim_key, value in dims.items():
        dim_type = DIMENSION_TYPES.get(dim_key, 'auxiliary')
        v = value.strip()

        if v == '✅':
            counts['total_strong'] += 1
            if dim_type == 'core':
                counts['core_strong'] += 1
            elif dim_type == 'semi_core':
                counts['semi_strong'] += 1
            else:
                counts['aux_strong'] += 1
        elif v == '❌':
            counts['total_weak'] += 1
            if dim_type == 'core':
                counts['core_weak'] += 1
                counts['has_core_weak'] = True
            elif dim_type == 'semi_core':
                counts['semi_weak'] += 1
            else:
                counts['aux_weak'] += 1
        else:  # ➖
            if dim_type == 'core':
                counts['core_neutral'] += 1
            elif dim_type == 'semi_core':
                counts['semi_neutral'] += 1
            else:
                counts['aux_neutral'] += 1

    return counts


def lookup_base_grade(counts: dict) -> tuple[str, str]:
    """Look up the base grade from the synthesis table. Returns (grade, rule_description)."""
    cs = counts['core_strong']
    ss = counts['semi_strong']
    axs = counts['aux_strong']
    tw = counts['total_weak']
    has_core_weak = counts['has_core_weak']

    # Core constraint: any core ❌ → cap at B+
    if has_core_weak:
        # Exception: sectional ✅ + eem ✅ → allow up to A-
        # (checked later as override)
        pass

    # S: 2 core ✅ + 2 semi ✅ + ≥2 aux ✅ + 0 ❌
    if cs >= 2 and ss >= 2 and axs >= 2 and tw == 0:
        return 'S', f'2核心✅ + 2半核心✅ + {axs}輔助✅ + 0❌'

    # S-: 2 core ✅ + 1 semi ✅ + ≥1 aux ✅ + 0 ❌
    if cs >= 2 and ss >= 1 and axs >= 1 and tw == 0:
        return 'S-', f'2核心✅ + {ss}半核心✅ + {axs}輔助✅ + 0❌'

    # A+: 2 core ✅ + 0 ❌
    if cs >= 2 and tw == 0:
        return 'A+', f'2核心✅ + 0❌'

    # A: 1 core ✅ + 1 semi ✅ + 0 ❌ (or 2 core ✅ + 1 ❌)
    if (cs >= 1 and ss >= 1 and tw == 0) or (cs >= 2 and tw <= 1):
        if cs >= 2 and tw <= 1:
            return 'A', f'2核心✅ + {tw}❌(容許1)'
        return 'A', f'{cs}核心✅ + {ss}半核心✅ + 0❌'

    # A-: 1 core ✅ + (1 semi ✅ or ➖) + ≤1 ❌
    if cs >= 1 and tw <= 1:
        return 'A-', f'{cs}核心✅ + ❌≤1'

    # B+: 1 core ✅ + ❌=2; or 2 semi ✅ + ❌≤1
    if (cs >= 1 and tw == 2) or (ss >= 2 and tw <= 1):
        if ss >= 2 and tw <= 1 and cs == 0:
            return 'B+', f'2半核心✅ + {tw}❌(Setup突圍)'
        return 'B+', f'{cs}核心✅ + {tw}❌'

    # B: 1 semi ✅ + ≥2 aux ✅ + ❌≤2
    if ss >= 1 and axs >= 2 and tw <= 2:
        return 'B', f'{ss}半核心✅ + {axs}輔助✅ + {tw}❌'

    # B-: No core/semi ✅, but ≥3 aux ✅ + ❌≤2
    if cs == 0 and ss == 0 and axs >= 3 and tw <= 2:
        return 'B-', f'0核心/半核心✅ + {axs}輔助✅ + {tw}❌'

    # C+: ❌=3 but at least 1 core/semi ✅
    if tw == 3 and (cs >= 1 or ss >= 1):
        return 'C+', f'{tw}❌ + 有{cs}核心/{ss}半核心✅挽救'

    # C: ❌=3, no core/semi ✅
    if tw == 3:
        return 'C', f'{tw}❌ + 完全無核心/半核心✅'

    # C-: ❌=4
    if tw == 4:
        return 'C-', f'{tw}❌'

    # D: ❌≥5 or no ✅ at all
    if tw >= 5 or counts['total_strong'] == 0:
        return 'D', f'{tw}❌ 或 完全無✅'

    # Fallback
    return 'C', f'未匹配明確規則 (core✅={cs}, semi✅={ss}, aux✅={axs}, ❌={tw})'


def apply_core_constraint(base_grade: str, counts: dict, dims: dict) -> tuple[str, str]:
    """Apply core constraint: core ❌ → cap at B+, with exception."""
    if not counts['has_core_weak']:
        return base_grade, ''

    grade_idx = GRADE_ORDER.index(base_grade) if base_grade in GRADE_ORDER else 6

    # Exception: sectional ✅ + eem ✅ → allow up to A-
    if dims.get('sectional', '').strip() == '✅' and dims.get('eem', '').strip() == '✅':
        if grade_idx < GRADE_ORDER.index('A-'):
            return 'A-', '核心❌但段速✅+EEM✅豁免 → 封頂A-'
        return base_grade, ''

    # Standard cap at B+
    if grade_idx < GRADE_ORDER.index('B+'):
        return 'B+', f'核心防護牆: 核心❌ → 封頂B+'
    return base_grade, ''


def apply_micro_adjustments(grade: str, micro_up: list, micro_down: list) -> tuple[str, str]:
    """Apply micro-adjustments (±1 grade max)."""
    if not micro_up and not micro_down:
        return grade, '無'

    grade_idx = GRADE_ORDER.index(grade) if grade in GRADE_ORDER else 6

    # Net adjustment: max(ups) - max(downs), capped at ±1
    up_val = 1 if micro_up else 0
    down_val = 1 if micro_down else 0
    net = up_val - down_val

    if net > 0 and grade_idx > 0:
        new_grade = GRADE_ORDER[grade_idx - 1]
        reasons = ', '.join(micro_up)
        return new_grade, f'升一級 ({reasons})'
    elif net < 0 and grade_idx < len(GRADE_ORDER) - 1:
        new_grade = GRADE_ORDER[grade_idx + 1]
        reasons = ', '.join(micro_down)
        return new_grade, f'降一級 ({reasons})'

    return grade, '升降互抵'


def compute_grade(horse: dict) -> dict:
    """Compute the full rating for a horse."""
    dims = horse['dimensions']
    counts = count_dimensions(dims)

    # Forgiveness bonus: +1 auxiliary ✅
    if horse.get('forgiveness_bonus'):
        counts['aux_strong'] += 1
        counts['total_strong'] += 1

    # Base grade
    base_grade, base_rule = lookup_base_grade(counts)

    # Core constraint
    constrained_grade, constraint_note = apply_core_constraint(base_grade, counts, dims)

    # Micro adjustments
    final_grade, micro_note = apply_micro_adjustments(
        constrained_grade,
        horse.get('micro_up', []),
        horse.get('micro_down', []),
    )

    return {
        'num': horse['num'],
        'name': horse['name'],
        'counts': counts,
        'base_grade': base_grade,
        'base_rule': base_rule,
        'constraint_note': constraint_note,
        'constrained_grade': constrained_grade,
        'micro_note': micro_note,
        'final_grade': final_grade,
        'dimensions': dims,
    }


def format_matrix_block(result: dict) -> str:
    """Format the complete 📊 評級矩陣 block."""
    dims = result['dimensions']
    counts = result['counts']

    lines = ["#### 📊 評級矩陣"]
    for dim_key in ['fitness', 'sectional', 'eem', 'jockey', 'class', 'surface', 'form_line', 'gear_dist']:
        label, tier = DIMENSION_LABELS[dim_key]
        value = dims.get(dim_key, '➖')
        lines.append(f"- **{label}** [{tier}]: `[{value}]` | 理據: `[{{{{LLM_FILL}}}}]`")

    core_weak_str = '有' if counts['has_core_weak'] else '無'
    lines.append(
        f"- **🔢 矩陣算術:** 核心✅={counts['core_strong']} | "
        f"半核心✅={counts['semi_strong']} | "
        f"輔助✅={counts['aux_strong']} | "
        f"總❌={counts['total_weak']} | "
        f"核心❌={core_weak_str} → 查表命中行={result['base_grade']}"
    )
    lines.append(f"- **基礎評級:** `[{result['base_grade']}]` | **規則**: `[{result['base_rule']}]`")

    if result['constraint_note']:
        lines.append(f"- **核心防護牆:** `[{result['constraint_note']}]`")

    lines.append(f"- **微調:** `[{result['micro_note']}]`")
    lines.append(f"- **覆蓋規則:** `[無]`")
    lines.append(f"\n⭐ **最終評級:** `[{result['final_grade']}]`")

    return '\n'.join(lines)


def rank_horses(results: list[dict]) -> list[dict]:
    """Rank horses by grade (primary), ✅ count (secondary), ❌ count (tertiary)."""
    def sort_key(r):
        grade_idx = GRADE_ORDER.index(r['final_grade']) if r['final_grade'] in GRADE_ORDER else 99
        return (grade_idx, -r['counts']['total_strong'], r['counts']['total_weak'])

    return sorted(results, key=sort_key)


def generate_verdict(ranked: list[dict]) -> str:
    """Generate the Top 4 verdict scaffold with pre-filled rankings."""
    labels = ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']
    lines = ["**Top 4 位置精選**\n"]

    for i, r in enumerate(ranked[:4]):
        lines.append(f"{labels[i]}")
        lines.append(f"- **馬號及馬名:** {r['num']} {r['name']}")
        lines.append(f"- **評級與✅數量:** `[{r['final_grade']}]` | ✅ {r['counts']['total_strong']}")
        lines.append(f"- **核心理據:** {{{{LLM_FILL}}}}")
        lines.append(f"- **最大風險:** {{{{LLM_FILL}}}}")
        lines.append("")

    return '\n'.join(lines)


def generate_csv(ranked: list[dict], race_id: str = 'Race_X') -> str:
    """Generate the Part 5 CSV block."""
    lines = ["```csv"]
    lines.append("race_id,horse_number,horse_name,grade,total_ticks,total_crosses,verdict,risk_level")
    for i, r in enumerate(ranked):
        if i < 4:
            verdict = f"TOP4_{i+1}"
            risk = 'LOW' if r['counts']['total_weak'] == 0 else ('MED' if r['counts']['total_weak'] <= 2 else 'HIGH')
        else:
            verdict = f"RATING_{r['final_grade'].replace('+', '_PLUS').replace('-', '_MINUS')}"
            risk = 'MED' if r['counts']['total_weak'] <= 2 else 'HIGH'
        lines.append(
            f"{race_id},{r['num']},{r['name']},"
            f"{r['final_grade']},{r['counts']['total_strong']},"
            f"{r['counts']['total_weak']},{verdict},{risk}"
        )
    lines.append("```")
    return '\n'.join(lines)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AU Wong Choi Protocol — Rating Matrix Calculator"
    )
    parser.add_argument("--input", type=str, help="Path to dimensions JSON file")
    parser.add_argument("--race-id", type=str, default="Race_X", help="Race ID for CSV")
    parser.add_argument("--output", type=str, default=None, help="Output file path")
    args = parser.parse_args()

    if not args.input:
        print("Usage: python3 compute_rating_matrix.py --input <dimensions.json> [--race-id Rosehill_R7]")
        print("\nExpected JSON format:")
        print(json.dumps({
            "horses": [{
                "num": 1, "name": "Example",
                "dimensions": {
                    "fitness": "✅", "sectional": "✅",
                    "eem": "➖", "jockey": "✅",
                    "class": "✅", "surface": "➖",
                    "form_line": "➖", "gear_dist": "➖"
                },
                "micro_up": [], "micro_down": [],
            }]
        }, ensure_ascii=False, indent=2))
        sys.exit(0)

    if not Path(args.input).exists():
        print(f"❌ File not found: {args.input}")
        sys.exit(1)

    data = json.loads(Path(args.input).read_text(encoding='utf-8'))
    horses = data.get('horses', [])

    if not horses:
        print("❌ No horses in input")
        sys.exit(1)

    results = [compute_grade(h) for h in horses]
    ranked = rank_horses(results)

    output_lines = []
    output_lines.append("# 📊 Rating Matrix 計算結果\n")

    for r in results:
        output_lines.append(f"\n## [{r['num']}] {r['name']}")
        output_lines.append(format_matrix_block(r))
        output_lines.append("")

    output_lines.append("\n---\n")
    output_lines.append("## 🏆 自動排名 Top 4\n")
    output_lines.append(generate_verdict(ranked))
    output_lines.append("\n---\n")
    output_lines.append("## 📊 CSV 匯出\n")
    output_lines.append(generate_csv(ranked, args.race_id))

    result_text = '\n'.join(output_lines)

    if args.output:
        Path(args.output).write_text(result_text, encoding='utf-8')
        print(f"✅ Rating matrix computed: {args.output}")
        top4_str = ', '.join(f"{r['name']}({r['final_grade']})" for r in ranked[:4])
        print(f"   📊 {len(horses)} horses | Top 4: {top4_str}")
    else:
        print(result_text)


if __name__ == '__main__':
    main()
