import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
verify_math.py — Wong Choi AU 自動化 Step 14.2A 數學驗證

用 Python regex 精確數 ✅/➖/❌ 符號，查表得出正確評級，
同 LLM 寫嘅 ⭐ 最終評級做交叉校驗。

Usage:
  python verify_math.py <analysis_file.md>
  python verify_math.py <directory_of_analysis_files>
  python verify_math.py <file.md> --fix        # 自動修正並覆寫
  python verify_math.py <file.md> --json       # JSON 輸出

Exit codes:
  0 = All horses PASS
  1 = At least one horse has a grade mismatch
  2 = File not found or no horses
"""
import sys, io, re, json, os, pathlib, argparse
from dataclasses import dataclass, field, asdict
from typing import Optional

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Grading Table (from 02_algorithmic_engine.md lines 692-705)
# ──────────────────────────────────────────────
# Each rule: (core_check, semi_core_check, aux_check, cross_check) → grade
# Checks return True if the horse meets that grade's requirements
# We check top-down; first match wins.

GRADE_ORDER = ['S', 'S-', 'A+', 'A', 'A-', 'B+', 'B', 'B-', 'C+', 'C', 'C-', 'D+', 'D']

DIMENSION_CATEGORIES = {
    # AU Wong Choi dimension names
    '狀態與穩定性': 'core',
    '段速與引擎': 'core',
    '形勢與走位': 'semi_core',
    '風向形勢': 'semi_core',      # Straight sprint variant
    '騎練訊號': 'semi_core',
    '級數與負重': 'aux',
    '場地適性': 'aux',
    '賽績線': 'aux',
    '裝備與距離': 'aux',
    # HKJC Wong Choi dimension names
    '穩定性': 'core',
    '段速質量': 'core',
    '形勢與走位(潛力)': 'semi_core',
    '形勢與走位(潛力v2)': 'semi_core',
    'race_shape': 'semi_core',
    '練馬師訊號': 'semi_core',
    '情境適配': 'aux',
    '路程/新鮮度': 'aux',
    '路程': 'aux',
    '新鮮度': 'aux',
    '級數優勢': 'aux',
}

# Regex patterns for dimension lines in the rating matrix
# Matches both AU and HKJC formats:
#   - **狀態與穩定性** [核心]: `[✅]` | ...
#   - 穩定性 [核心]: `❌` | ...
MATRIX_LINE_RE = re.compile(
    r'-\s*\*?\*?(.+?)\*?\*?\s*\[(?:核心|半核心|輔助|輔助\(可選\))\]'
    r'[：:]\s*[`\s\[]*([✅➖❌]|不計入)',
    re.UNICODE
)

# Override detection patterns
PSI_RE = re.compile(r'穩定指數[：:]\s*[`\s]*([\d.]+)', re.UNICODE)
AGE_RE = re.compile(r'(2yo|2歲|two.?year|2YO)', re.IGNORECASE)
RATING_RE = re.compile(r'評分[：:]\s*[`\s]*(\d+)', re.UNICODE)

# Also match the "🔢 矩陣算術" summary line
MATRIX_ARITHMETIC_RE = re.compile(
    r'🔢\s*矩陣算術\s*\*?\*?[：:]?\s*\*?\*?\s*'
    r'核心✅\s*=\s*\[?(\d+)\]?\s*[|｜]\s*'
    r'半核心✅\s*=\s*\[?(\d+)\]?\s*[|｜]\s*'
    r'輔助✅\s*=\s*\[?(\d+)\]?\s*[|｜]\s*'
    r'總❌\s*=\s*\[?(\d+)\]?',
    re.UNICODE
)

# Match the stated base grade — handles `[B+]` or `B+`
BASE_GRADE_RE = re.compile(
    r'基礎評級[：:]?\*?\*?\s*[`\s\[]*([SABCDF][+\-]?)',
    re.UNICODE
)

# Match the final grade — handles `[B+]` or `B+`
FINAL_GRADE_RE = re.compile(
    r'⭐\s*\*?\*?最終評級[：:]?\*?\*?\s*[`\s\[]*([SABCDF][+\-]?)',
    re.UNICODE
)

# Horse header patterns (supports both Kelvin and Heison formats)
HORSE_HEADER_RE = re.compile(
    r'(?:'
    r'###?\s*【No\.?\s*(\d+)】\s*(.+?)(?:\（|[\(])'   # ### 【No.1】Name（
    r'|'
    r'\*\*\[?\s*(\d+)\]?\s+(.+?)\*\*\s*\|'            # **[1] Name** |
    r'|'
    r'###\s+(\d+)\s+(.+?)\s*\|'                        # ### 1 Name |
    r')',
    re.MULTILINE
)


@dataclass
class DimensionResult:
    name: str
    category: str  # core, semi_core, aux
    verdict: str   # ✅, ➖, ❌


@dataclass
class OverrideAlert:
    rule: str
    triggered: bool
    detail: str = ''


@dataclass
class HorseVerification:
    number: int
    name: str
    # Parsed from matrix lines
    dimensions: list = field(default_factory=list)
    core_ticks: int = 0
    semi_core_ticks: int = 0
    aux_ticks: int = 0
    total_crosses: int = 0
    has_core_cross: bool = False
    # Parsed from 🔢 line (LLM's own count)
    llm_core_ticks: Optional[int] = None
    llm_semi_core_ticks: Optional[int] = None
    llm_aux_ticks: Optional[int] = None
    llm_total_crosses: Optional[int] = None
    # Grades
    computed_base_grade: str = ''
    llm_base_grade: str = ''
    llm_final_grade: str = ''
    # Verification results
    count_match: bool = True
    grade_match: bool = True
    issues: list = field(default_factory=list)
    # Override alerts
    overrides: list = field(default_factory=list)


def categorize_dimension(name: str) -> str:
    """Map a dimension name to its category."""
    name_clean = name.strip().rstrip('*').lstrip('*').strip()
    for key, cat in DIMENSION_CATEGORIES.items():
        if key in name_clean:
            return cat
    return 'aux'  # Default to auxiliary if unknown


def parse_matrix(block: str) -> list:
    """Parse the 📊 rating matrix section and extract all dimension verdicts."""
    dims = []
    # Find the rating matrix section
    matrix_start = block.find('📊')
    if matrix_start == -1:
        return dims

    # Only search within the matrix section (up to next section or end)
    matrix_end = len(block)
    for marker in ['💡', '⭐', '---', '####']:
        pos = block.find(marker, matrix_start + 2)
        if pos != -1 and pos < matrix_end:
            # Don't use 💡 or ⭐ that are within the matrix section header
            if pos > matrix_start + 10:
                matrix_end = pos

    matrix_text = block[matrix_start:matrix_end]

    for match in MATRIX_LINE_RE.finditer(matrix_text):
        dim_name = match.group(1).strip().rstrip('*').lstrip('*').strip()
        verdict = match.group(2)
        category = categorize_dimension(dim_name)
        dims.append(DimensionResult(
            name=dim_name,
            category=category,
            verdict=verdict
        ))

    return dims


def count_verdicts(dimensions: list) -> dict:
    """Count ✅/➖/❌ by category. Skip '不計入' (N/A) dimensions."""
    counts = {
        'core_ticks': 0, 'semi_core_ticks': 0, 'aux_ticks': 0,
        'total_crosses': 0, 'has_core_cross': False,
    }
    for dim in dimensions:
        if dim.verdict == '不計入':
            continue  # N/A — excluded from grade calculation
        if dim.verdict == '✅':
            if dim.category == 'core':
                counts['core_ticks'] += 1
            elif dim.category == 'semi_core':
                counts['semi_core_ticks'] += 1
            else:
                counts['aux_ticks'] += 1
        elif dim.verdict == '❌':
            counts['total_crosses'] += 1
            if dim.category == 'core':
                counts['has_core_cross'] = True
    return counts


def lookup_base_grade(core_t: int, semi_t: int, aux_t: int,
                      total_x: int, has_core_x: bool) -> str:
    """
    Look up the base grade from the grading table.
    Based on 02_algorithmic_engine.md lines 692-705.

    Semi-core ✅ can dual-count: they count towards core conditions AND aux conditions.
    But semi-core alone cannot replace a core ✅ as the S-level gate.
    """
    # S: 2 core ✅ + 2 semi-core ✅ + ≥2 aux ✅ + zero ❌
    if core_t >= 2 and semi_t >= 2 and aux_t >= 2 and total_x == 0:
        return 'S'

    # S-: 2 core ✅ + 1 semi-core ✅ + ≥1 aux ✅ + zero ❌
    if core_t >= 2 and semi_t >= 1 and aux_t >= 1 and total_x == 0:
        return 'S-'

    # A+: 2 core ✅ + zero ❌
    if core_t >= 2 and total_x == 0:
        return 'A+'

    # A: 1 core ✅ + 1 semi-core ✅ + zero ❌  OR  2 core ✅ + ≤1 ❌
    if (core_t >= 1 and semi_t >= 1 and total_x == 0) or \
       (core_t >= 2 and total_x <= 1):
        return 'A'

    # A-: 1 core ✅ + (1 semi-core ✅ or ➖) + ❌ ≤ 1
    if core_t >= 1 and total_x <= 1:
        return 'A-'

    # B+: 1 core ✅ + ❌ = 2  OR  2 semi-core ✅ + ❌ ≤ 1
    if (core_t >= 1 and total_x == 2) or \
       (semi_t >= 2 and total_x <= 1):
        return 'B+'

    # B: 1 semi-core ✅ + ≥2 aux ✅ + ❌ ≤ 2
    if semi_t >= 1 and aux_t >= 2 and total_x <= 2:
        return 'B'

    # B-: No core/semi-core ✅, but ≥3 aux ✅ + ❌ ≤ 2
    if core_t == 0 and semi_t == 0 and aux_t >= 3 and total_x <= 2:
        return 'B-'

    # C+: ❌ = 3, but at least 1 core/semi-core ✅
    if total_x == 3 and (core_t >= 1 or semi_t >= 1):
        return 'C+'

    # C: ❌ = 3, no core/semi-core ✅
    if total_x == 3 and core_t == 0 and semi_t == 0:
        return 'C'

    # C-: ❌ = 4
    if total_x == 4:
        return 'C-'

    # D+: ❌ ≥ 5 but still has at least 1 ✅
    total_ticks = core_t + semi_t + aux_t
    if total_x >= 5 and total_ticks >= 1:
        return 'D+'

    # D: ❌ ≥ 5 or zero ✅ total
    if total_x >= 5 or total_ticks == 0:
        return 'D'

    # Fallback — shouldn't normally reach here
    # Handle edge cases not explicitly in the table
    if core_t >= 1 and total_x >= 3:
        return 'C+'
    if total_x >= 3:
        return 'C'

    return 'C'


def grade_to_numeric(grade: str) -> float:
    """Convert grade to numeric for comparison."""
    mapping = {
        'S': 13, 'S-': 12, 'A+': 11, 'A': 10, 'A-': 9,
        'B+': 8, 'B': 7, 'B-': 6, 'C+': 5, 'C': 4, 'C-': 3, 'D+': 2, 'D': 1
    }
    return mapping.get(grade, 0)


def grade_diff(g1: str, g2: str) -> float:
    """How many grade levels apart."""
    return abs(grade_to_numeric(g1) - grade_to_numeric(g2))


def split_horses(text: str) -> list:
    """Split analysis text into individual horse blocks."""
    matches = list(HORSE_HEADER_RE.finditer(text))
    horses = []
    for i, m in enumerate(matches):
        num = m.group(1) or m.group(3) or m.group(5)
        name = (m.group(2) or m.group(4) or m.group(6) or '').strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        horses.append({
            'number': int(num) if num else 0,
            'name': name,
            'block': block,
        })
    return horses


def verify_horse(horse: dict) -> HorseVerification:
    """Verify a single horse's grade against the computed grade."""
    block = horse['block']
    result = HorseVerification(
        number=horse['number'],
        name=horse['name'],
    )

    # 1. Parse matrix dimensions
    result.dimensions = parse_matrix(block)
    if not result.dimensions:
        result.issues.append('NO_MATRIX_FOUND: 找唔到 📊 評級矩陣')
        result.count_match = False
        result.grade_match = False
        return result

    # 2. Count verdicts
    counts = count_verdicts(result.dimensions)
    result.core_ticks = counts['core_ticks']
    result.semi_core_ticks = counts['semi_core_ticks']
    result.aux_ticks = counts['aux_ticks']
    result.total_crosses = counts['total_crosses']
    result.has_core_cross = counts['has_core_cross']

    # 3. Parse LLM's own 🔢 count
    arith_match = MATRIX_ARITHMETIC_RE.search(block)
    if arith_match:
        result.llm_core_ticks = int(arith_match.group(1))
        result.llm_semi_core_ticks = int(arith_match.group(2))
        result.llm_aux_ticks = int(arith_match.group(3))
        result.llm_total_crosses = int(arith_match.group(4))

        # Check if LLM's count matches our count
        if result.llm_core_ticks != result.core_ticks:
            result.count_match = False
            result.issues.append(
                f'COUNT_MISMATCH_CORE: LLM 數 核心✅={result.llm_core_ticks}, '
                f'實際={result.core_ticks}'
            )
        if result.llm_semi_core_ticks != result.semi_core_ticks:
            result.count_match = False
            result.issues.append(
                f'COUNT_MISMATCH_SEMI: LLM 數 半核心✅={result.llm_semi_core_ticks}, '
                f'實際={result.semi_core_ticks}'
            )
        if result.llm_aux_ticks != result.aux_ticks:
            result.count_match = False
            result.issues.append(
                f'COUNT_MISMATCH_AUX: LLM 數 輔助✅={result.llm_aux_ticks}, '
                f'實際={result.aux_ticks}'
            )
        if result.llm_total_crosses != result.total_crosses:
            result.count_match = False
            result.issues.append(
                f'COUNT_MISMATCH_CROSS: LLM 數 總❌={result.llm_total_crosses}, '
                f'實際={result.total_crosses}'
            )
    else:
        result.issues.append('NO_ARITHMETIC_LINE: 找唔到 🔢 矩陣算術行')

    # 4. Compute correct base grade
    result.computed_base_grade = lookup_base_grade(
        result.core_ticks, result.semi_core_ticks, result.aux_ticks,
        result.total_crosses, result.has_core_cross
    )

    # 5. Parse LLM's stated base grade
    base_match = BASE_GRADE_RE.search(block)
    if base_match:
        result.llm_base_grade = base_match.group(1)
    else:
        result.issues.append('NO_BASE_GRADE: 找唔到基礎評級行')

    # 6. Parse LLM's final grade
    final_match = FINAL_GRADE_RE.search(block)
    if final_match:
        result.llm_final_grade = final_match.group(1)
    else:
        result.issues.append('NO_FINAL_GRADE: 找唔到 ⭐ 最終評級')

    # 7. Grade verification
    # Base grade must match table lookup exactly
    if result.llm_base_grade and result.llm_base_grade != result.computed_base_grade:
        result.grade_match = False
        result.issues.append(
            f'BASE_GRADE_MISMATCH: 查表應為 [{result.computed_base_grade}], '
            f'LLM 寫 [{result.llm_base_grade}]'
        )

    # Final grade can differ from base by at most 1 level (micro-adjustment)
    if result.llm_final_grade and result.computed_base_grade:
        diff = grade_diff(result.llm_final_grade, result.computed_base_grade)
        if diff > 1:
            result.grade_match = False
            result.issues.append(
                f'FINAL_GRADE_DRIFT: 基礎={result.computed_base_grade}, '
                f'最終={result.llm_final_grade}, 差距={diff}級 '
                f'(微調最多1級)'
            )

    # 8. Core constraint check: any core ❌ → max B+
    if result.has_core_cross and result.llm_final_grade:
        if grade_to_numeric(result.llm_final_grade) > grade_to_numeric('B+'):
            result.grade_match = False
            result.issues.append(
                f'CORE_CONSTRAINT_VIOLATION: 有核心❌但最終評級='
                f'{result.llm_final_grade} (封頂 B+)'
            )

    # 9. Override rule checks
    result.overrides = check_overrides(block, result)
    for ov in result.overrides:
        if ov.triggered:
            result.issues.append(f'OVERRIDE_{ov.rule}: {ov.detail}')

    return result


def check_overrides(block: str, result: 'HorseVerification') -> list:
    """Check mechanical override rules against the analysis block."""
    alerts = []

    # Override 1: Core cap (already checked above, record for report)
    alerts.append(OverrideAlert(
        rule='CORE_CAP',
        triggered=result.has_core_cross and bool(result.llm_final_grade) and
                  grade_to_numeric(result.llm_final_grade) > grade_to_numeric('B+'),
        detail=f'核心❌ 封頂 B+ (LLM={result.llm_final_grade})' if result.has_core_cross else ''
    ))

    # Override 2: 2YO cap → max A-
    is_2yo = bool(AGE_RE.search(block))
    two_yo_violated = False
    if is_2yo and result.llm_final_grade:
        if grade_to_numeric(result.llm_final_grade) > grade_to_numeric('A-'):
            two_yo_violated = True
    alerts.append(OverrideAlert(
        rule='2YO_CAP',
        triggered=two_yo_violated,
        detail=f'2YO 封頂 A- (LLM={result.llm_final_grade})' if two_yo_violated else ''
    ))

    # Override 3: Iron-leg floor (PSI > 0.7 → min B)
    psi_match = PSI_RE.search(block)
    iron_leg_violated = False
    if psi_match:
        psi = float(psi_match.group(1))
        if psi > 0.7 and result.llm_final_grade:
            if grade_to_numeric(result.llm_final_grade) < grade_to_numeric('B'):
                iron_leg_violated = True
                alerts.append(OverrideAlert(
                    rule='IRON_LEG_FLOOR',
                    triggered=True,
                    detail=f'PSI={psi} > 0.7 → 保底 B (LLM={result.llm_final_grade})'
                ))
    if not iron_leg_violated:
        alerts.append(OverrideAlert(rule='IRON_LEG_FLOOR', triggered=False))

    return alerts


# Regex for detecting unfilled template markers
FILL_MARKER_RE = re.compile(r'\[FILL[:\s].*?\]|\{\{LLM_FILL\}\}|\[FILL\]', re.UNICODE)


def verify_file(filepath: str) -> dict:
    """Verify all horses in an analysis file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    horses = split_horses(text)
    if not horses:
        return {
            'file': str(filepath),
            'passed': False,
            'horses': [],
            'summary': {'total': 0, 'passed': 0, 'failed': 0,
                        'count_errors': 0, 'grade_errors': 0,
                        'override_alerts': 0, 'fill_residuals': 0},
            'issues': ['NO_HORSES_FOUND'],
        }

    results = [verify_horse(h) for h in horses]

    # Check for unfilled [FILL] / {{LLM_FILL}} markers
    fill_markers = FILL_MARKER_RE.findall(text)
    fill_residuals = len(fill_markers)

    count_errors = sum(1 for r in results if not r.count_match)
    grade_errors = sum(1 for r in results if not r.grade_match)
    override_alerts = sum(1 for r in results
                         for ov in r.overrides if ov.triggered)
    passed_count = sum(1 for r in results if r.count_match and r.grade_match and not r.issues)
    failed_count = len(results) - passed_count
    all_passed = failed_count == 0 and fill_residuals == 0

    return {
        'file': str(filepath),
        'passed': all_passed,
        'horses': [asdict(r) for r in results],
        'summary': {
            'total': len(results),
            'passed': passed_count,
            'failed': failed_count,
            'count_errors': count_errors,
            'grade_errors': grade_errors,
            'override_alerts': override_alerts,
            'fill_residuals': fill_residuals,
        },
    }


def fix_file(filepath: str, report: dict) -> int:
    """Auto-fix grade mismatches in the analysis file. Returns count of fixes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    fixes = 0
    for h in report['horses']:
        if not h['issues']:
            continue

        computed = h['computed_base_grade']
        llm_base = h['llm_base_grade']
        llm_final = h['llm_final_grade']

        # Fix 1: Base grade mismatch
        if llm_base and computed and llm_base != computed:
            for issue in h['issues']:
                if 'BASE_GRADE_MISMATCH' in issue:
                    old_pattern = f'基礎評級' + r'[：:]' + r'.*?' + re.escape(f'[{llm_base}]')
                    # Simple string replacement for base grade
                    old_str = f'`[{llm_base}]`'
                    new_str = f'`[{computed}]`'
                    # Find base grade line and replace
                    base_re = re.compile(
                        r'(基礎評級[：:].*?)`\[' + re.escape(llm_base) + r'\]`',
                        re.UNICODE
                    )
                    new_text = base_re.sub(
                        lambda m: m.group(1) + f'`[{computed}]`', text, count=1
                    )
                    if new_text != text:
                        text = new_text
                        fixes += 1
                        print(f'   🔧 #{h["number"]} 基礎評級: [{llm_base}] → [{computed}]')

        # Fix 2: Final grade drift (>1 level from computed base)
        if llm_final and computed:
            diff = grade_diff(llm_final, computed)
            if diff > 1:
                # Clamp final grade to ±1 from computed base
                computed_num = grade_to_numeric(computed)
                final_num = grade_to_numeric(llm_final)
                if final_num > computed_num:
                    target = GRADE_ORDER[max(0, GRADE_ORDER.index(computed) - 1)]
                else:
                    target = GRADE_ORDER[min(len(GRADE_ORDER)-1, GRADE_ORDER.index(computed) + 1)]

                final_re = re.compile(
                    r'(⭐\s*\*?\*?最終評級[：:]\*?\*?\s*)`\[?' + re.escape(llm_final) + r'\]?`',
                    re.UNICODE
                )
                new_text = final_re.sub(
                    lambda m: m.group(1) + f'`[{target}]`', text, count=1
                )
                if new_text != text:
                    text = new_text
                    fixes += 1
                    print(f'   🔧 #{h["number"]} 最終評級: [{llm_final}] → [{target}]')

        # Fix 3: Arithmetic line count mismatch
        for issue in h['issues']:
            if 'COUNT_MISMATCH' in issue:
                arith_re = re.compile(
                    r'(🔢\s*矩陣算術[：:]?\s*)'
                    r'核心✅\s*=\s*\[?\d+\]?\s*[|｜]\s*'
                    r'半核心✅\s*=\s*\[?\d+\]?\s*[|｜]\s*'
                    r'輔助✅\s*=\s*\[?\d+\]?\s*[|｜]\s*'
                    r'總❌\s*=\s*\[?\d+\]?',
                    re.UNICODE
                )
                ct = h['core_ticks']
                st = h['semi_core_ticks']
                at = h['aux_ticks']
                tx = h['total_crosses']
                replacement = (
                    f'🔢 矩陣算術: '
                    f'核心✅=[{ct}] | 半核心✅=[{st}] | '
                    f'輔助✅=[{at}] | 總❌=[{tx}]'
                )
                new_text = arith_re.sub(replacement, text, count=1)
                if new_text != text:
                    text = new_text
                    fixes += 1
                    print(f'   🔧 #{h["number"]} 矩陣算術行已修正')
                break  # Only fix arithmetic once per horse

    # Fix 4: CSV grade alignment
    csv_block_re = re.compile(r'```csv\n(.+?)```', re.DOTALL)
    csv_match = csv_block_re.search(text)
    if csv_match:
        csv_text = csv_match.group(1)
        csv_fixed = csv_text
        for h in report['horses']:
            if h['llm_final_grade'] and h['computed_base_grade']:
                # If final grade was fixed, update CSV too
                computed = h['computed_base_grade']
                llm_final = h['llm_final_grade']
                if grade_diff(llm_final, computed) > 1:
                    computed_num = grade_to_numeric(computed)
                    final_num = grade_to_numeric(llm_final)
                    if final_num > computed_num:
                        target = GRADE_ORDER[max(0, GRADE_ORDER.index(computed) - 1)]
                    else:
                        target = GRADE_ORDER[min(len(GRADE_ORDER)-1, GRADE_ORDER.index(computed) + 1)]
                    # Replace in CSV — grade is typically last field
                    horse_name = h['name'].split('（')[0].split('(')[0].strip()
                    if horse_name and llm_final in csv_fixed:
                        csv_fixed = csv_fixed.replace(
                            f', {llm_final}\n', f', {target}\n', 1
                        )
                        csv_fixed = csv_fixed.replace(
                            f', {llm_final},', f', {target},', 1
                        )
        if csv_fixed != csv_text:
            text = text.replace(csv_text, csv_fixed)
            fixes += 1
            print(f'   🔧 CSV 評級已同步修正')

    if fixes > 0:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f'   💾 已寫入 {fixes} 項修正到 {os.path.basename(filepath)}')

    return fixes


def print_report(report: dict):
    """Print human-readable report."""
    fname = os.path.basename(report['file'])
    status = '✅ ALL PASS' if report['passed'] else '❌ DRIFT DETECTED'
    s = report['summary']

    print(f"\n{'=' * 65}")
    print(f"🔢 verify_math.py — {fname}")
    print(f"   Status: {status}")
    print(f"   Horses: {s['total']} total, {s['passed']} ✅, {s['failed']} ❌")
    print(f"   Count errors: {s['count_errors']}  |  Grade errors: {s['grade_errors']}")
    print(f"   Override alerts: {s.get('override_alerts', 0)}")
    if s.get('fill_residuals', 0) > 0:
        print(f"   ⚠️ FILL 殘留: {s['fill_residuals']} 個未填充標記")

    for h in report['horses']:
        num = h['number']
        name = h['name']
        ct = h['core_ticks']
        st = h['semi_core_ticks']
        at = h['aux_ticks']
        tx = h['total_crosses']
        computed = h['computed_base_grade']
        llm_base = h['llm_base_grade'] or '?'
        llm_final = h['llm_final_grade'] or '?'

        # Determine status icon
        if not h['issues']:
            icon = '✅'
        elif any('MISMATCH' in i or 'VIOLATION' in i or 'DRIFT' in i for i in h['issues']):
            icon = '❌'
        else:
            icon = '⚠️'

        print(f"\n   {icon} #{num} {name}")
        print(f"      計數: 核心✅={ct}  半核心✅={st}  輔助✅={at}  總❌={tx}")
        print(f"      查表: [{computed}]  LLM基礎: [{llm_base}]  LLM最終: [{llm_final}]")

        if h['issues']:
            for issue in h['issues']:
                print(f"      → {issue}")

        # Print override check summary
        for ov in h.get('overrides', []):
            status = '⚠️ TRIGGERED' if ov['triggered'] else '✅ OK'
            detail = f" — {ov['detail']}" if ov['detail'] else ''
            print(f"      🔍 {ov['rule']}: {status}{detail}")

    print(f"\n{'=' * 65}")


def main():
    parser = argparse.ArgumentParser(
        description='Wong Choi AU — Step 14.2A 自動化數學驗證'
    )
    parser.add_argument('path', help='Analysis .md file or directory')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON instead of text')
    parser.add_argument('--fix', action='store_true',
                        help='Auto-fix grade mismatches (writes back to file)')
    args = parser.parse_args()

    path = pathlib.Path(args.path)
    files = []

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(path.glob('*_Analysis.md'))
        if not files:
            files = sorted(path.glob('*Analysis*.md'))
    else:
        print(f'Error: {path} not found')
        sys.exit(2)

    if not files:
        print(f'No analysis files found in {path}')
        sys.exit(2)

    all_reports = []
    any_failed = False

    for f in files:
        report = verify_file(str(f))
        all_reports.append(report)
        if not report['passed']:
            any_failed = True

    # Auto-fix mode
    if args.fix:
        total_fixes = 0
        for i, f in enumerate(files):
            report = all_reports[i]
            if not report['passed']:
                print(f"\n🔧 Auto-fixing {os.path.basename(str(f))}...")
                fixes = fix_file(str(f), report)
                total_fixes += fixes
        if total_fixes > 0:
            print(f"\n🔧 Total fixes applied: {total_fixes}")
            print(f"🔄 Re-verifying...")
            # Re-verify after fixes
            all_reports = []
            any_failed = False
            for f in files:
                report = verify_file(str(f))
                all_reports.append(report)
                if not report['passed']:
                    any_failed = True

    if args.json:
        # Simplify output — remove full dimension details for brevity
        for report in all_reports:
            for h in report['horses']:
                h.pop('dimensions', None)
        print(json.dumps(all_reports, ensure_ascii=False, indent=2))
    else:
        total_horses = 0
        total_passed = 0
        for r in all_reports:
            print_report(r)
            total_horses += r['summary']['total']
            total_passed += r['summary']['passed']

        print(f"\n{'=' * 65}")
        print(f"📊 TOTAL: {len(all_reports)} files, "
              f"{total_horses} horses, "
              f"{total_passed} ✅ verified, "
              f"{total_horses - total_passed} ❌ drift")
        print(f"{'=' * 65}")

    sys.exit(1 if any_failed else 0)


if __name__ == '__main__':
    main()
