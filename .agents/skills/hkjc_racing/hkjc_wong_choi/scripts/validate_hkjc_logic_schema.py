#!/usr/bin/env python3
"""
validate_hkjc_logic_schema.py — HKJC V4.2 Pre-Compile Schema Validator
========================================================================
Lightweight gate that runs BEFORE the compiler. If this fails, the
pipeline MUST NOT produce an Analysis.md.

Usage:
  python validate_hkjc_logic_schema.py <Logic.json>

Exit codes:
  0  = all checks pass
  1  = schema violations found (details printed)
  2  = file error (missing, unparseable)

Can also be imported and called programmatically:
  from validate_hkjc_logic_schema import validate_logic_json
  result = validate_logic_json(logic_data)
  if not result['pass']:
      for err in result['errors']:
          print(err)
"""

import json
import os
import re
import sys

# Import central schema constants
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hkjc_schema import (
    HKJC_SCHEMA_VERSION,
    HKJC_PLATFORM,
    HKJC_MATRIX_EXPECTED_KEYS,
    HKJC_MATRIX_SCHEMA,
    HKJC_VALID_SCORES,
    HKJC_VALID_SCORES_WITH_NA,
    HKJC_CORE_SEMI_SCORES,
    HKJC_AUX_SCORES,
    HKJC_LEGACY_8D_KEYS,
    HKJC_LEGACY_TOP_LEVEL_FIELDS,
    DUMMY_PHRASES,
    FLUFF_PHRASES,
)

# Pattern to detect concrete data anchors in core_logic
_DATA_ANCHOR_RE = re.compile(
    r'\d+[秒磅米m]'           # e.g. 22.5秒, 133磅, 1200m
    r'|L400\s*[=:≈]?\s*\d'    # L400=22.5
    r'|\d+-\d+-\d+'            # 2-1-3 form sequences
    r'|第\d+名'                # 第3名
    r'|\d{1,2}/\d{1,2}'       # dates 04/12
    r'|\d+\.?\d*[sS]'         # 22.5s
)


def validate_logic_json(logic_data: dict) -> dict:
    """Validate an HKJC Logic JSON dict against V4.2 schema.

    Returns:
        {
            'pass': bool,
            'errors': list[str],   # Error messages with codes
            'warnings': list[str], # Non-blocking warnings
            'stats': {
                'horses_checked': int,
                'horses_passed': int,
                'horses_failed': int,
            }
        }
    """
    errors = []
    warnings = []
    stats = {'horses_checked': 0, 'horses_passed': 0, 'horses_failed': 0}

    # ── SCHEMA-001: schema_version ──
    sv = logic_data.get('schema_version', '')
    if sv != HKJC_SCHEMA_VERSION:
        if not sv:
            errors.append(
                f"SCHEMA-001: 缺少 schema_version。"
                f" 必須為 '{HKJC_SCHEMA_VERSION}'。"
            )
        else:
            errors.append(
                f"SCHEMA-001: schema_version 為 '{sv}'，"
                f" 必須為 '{HKJC_SCHEMA_VERSION}'。"
            )

    # ── SCHEMA-002: platform ──
    platform = logic_data.get('platform', '')
    if platform != HKJC_PLATFORM:
        if not platform:
            warnings.append(
                f"SCHEMA-002: 缺少 platform 欄位。"
                f" 建議設為 '{HKJC_PLATFORM}'。"
            )
        elif platform != HKJC_PLATFORM:
            errors.append(
                f"SCHEMA-002: platform 為 '{platform}'，"
                f" HKJC Logic JSON 必須為 '{HKJC_PLATFORM}'。"
            )

    # ── Check race_analysis exists ──
    race_analysis = logic_data.get('race_analysis', {})
    if not isinstance(race_analysis, dict) or not race_analysis:
        warnings.append("SCHEMA-INFO: race_analysis 區塊缺失或為空。")

    # ── Per-horse validation ──
    horses = logic_data.get('horses', {})
    if not isinstance(horses, dict) or not horses:
        errors.append("SCHEMA-ERR: 'horses' key 缺失或為空，無法驗證。")
        return {'pass': not errors, 'errors': errors, 'warnings': warnings, 'stats': stats}

    for h_num, h_entry in horses.items():
        stats['horses_checked'] += 1
        horse_errors = _validate_horse(h_num, h_entry, horses)
        if horse_errors:
            stats['horses_failed'] += 1
            errors.extend(horse_errors)
        else:
            stats['horses_passed'] += 1

    return {
        'pass': not errors,
        'errors': errors,
        'warnings': warnings,
        'stats': stats,
    }


def _validate_horse(h_num: str, h_entry: dict, all_horses: dict) -> list:
    """Validate a single horse entry. Returns list of error strings."""
    errors = []
    horse_name = h_entry.get('horse_name', '?')
    prefix = f"Horse {h_num} ({horse_name})"

    if not isinstance(h_entry, dict):
        return [f"{prefix}: SCHEMA-ERR: horse entry is not a dict"]

    # ── SCHEMA-003: 7 matrix keys present ──
    matrix = h_entry.get('matrix', {})
    if not isinstance(matrix, dict):
        errors.append(f"{prefix}: SCHEMA-003: matrix 必須係 dict，目前為 {type(matrix).__name__}")
        return errors

    matrix_keys = set(matrix.keys())
    missing = sorted(HKJC_MATRIX_EXPECTED_KEYS - matrix_keys)
    if missing:
        errors.append(f"{prefix}: SCHEMA-003: 7D 矩陣缺少 key: {missing}")

    # ── SCHEMA-004: No legacy 8D keys ──
    legacy_found = sorted(matrix_keys & HKJC_LEGACY_8D_KEYS)
    if legacy_found:
        errors.append(
            f"{prefix}: SCHEMA-004: 偵測到舊 8D 矩陣欄位 {legacy_found}。"
            " HKJC V4.2 只接受 7 維。"
        )

    # ── SCHEMA-005: No legacy top-level fields ──
    top_legacy = sorted(k for k in HKJC_LEGACY_TOP_LEVEL_FIELDS if k in h_entry)
    if top_legacy:
        errors.append(
            f"{prefix}: SCHEMA-005: 偵測到舊版 top-level 分析欄位 {top_legacy}。"
            " V4.2 已改為 matrix-only reasoning。"
        )

    # ── Per-dimension checks ──
    for dim_key in HKJC_MATRIX_EXPECTED_KEYS:
        dim_data = matrix.get(dim_key)
        if dim_data is None:
            continue  # Already caught by SCHEMA-003

        if not isinstance(dim_data, dict):
            errors.append(
                f"{prefix}: SCHEMA-006: matrix.{dim_key} 必須係 dict "
                f"(包含 score + reasoning)，目前為 {type(dim_data).__name__}"
            )
            continue

        # ── SCHEMA-006: score + reasoning structure ──
        score = dim_data.get('score', '')
        reasoning = dim_data.get('reasoning', '')

        if 'score' not in dim_data:
            errors.append(f"{prefix}: SCHEMA-006: matrix.{dim_key} 缺少 'score' 欄位")
        if 'reasoning' not in dim_data:
            errors.append(f"{prefix}: SCHEMA-006: matrix.{dim_key} 缺少 'reasoning' 欄位")

        # ── SCHEMA-007: Score is valid ──
        score_str = str(score).strip()
        if '[FILL' in score_str:
            errors.append(
                f"{prefix}: SCHEMA-008: matrix.{dim_key}.score 仍為 [FILL]，"
                " 必須填入有效分數。"
            )
        elif score_str not in HKJC_VALID_SCORES_WITH_NA:
            dim_type = HKJC_MATRIX_SCHEMA.get(dim_key, 'aux')
            valid = HKJC_CORE_SEMI_SCORES if dim_type in ('core', 'semi') else HKJC_AUX_SCORES
            if score_str not in valid and score_str != 'N/A':
                errors.append(
                    f"{prefix}: SCHEMA-007: matrix.{dim_key}.score '{score_str}' "
                    f"不是有效分數。{dim_type} 維度有效值: {sorted(valid)}"
                )

        # ── SCHEMA-008: Reasoning not [FILL] ──
        reasoning_str = str(reasoning).strip()
        if '[FILL' in reasoning_str and len(reasoning_str) < 50:
            errors.append(
                f"{prefix}: SCHEMA-008: matrix.{dim_key}.reasoning 仍為 placeholder。"
                " 必須填入基於數據的分析。"
            )

    # ── SCHEMA-009: core_logic substance ──
    core_logic = str(h_entry.get('core_logic', ''))
    if '[FILL]' in core_logic or not core_logic.strip():
        errors.append(f"{prefix}: SCHEMA-009: core_logic 未填寫或為 [FILL]。")
    elif len(core_logic.strip()) < 50:
        errors.append(
            f"{prefix}: SCHEMA-009: core_logic 只有 {len(core_logic.strip())} 字，"
            " 至少需要 50 字。"
        )

    # ── SCHEMA-010: core_logic data anchors ──
    if core_logic and '[FILL]' not in core_logic and len(core_logic.strip()) >= 50:
        anchors = _DATA_ANCHOR_RE.findall(core_logic)
        if len(anchors) < 2:
            errors.append(
                f"{prefix}: SCHEMA-010: core_logic 只有 {len(anchors)} 個數據錨點，"
                " 至少需要 2 個 (如 L400=22.5秒、近績序列、名次)。"
            )

    # ── DUMMY-001: Dummy phrase check ──
    for phrase in DUMMY_PHRASES:
        if phrase in core_logic:
            errors.append(
                f"{prefix}: DUMMY-001: core_logic 含有已知 bypass 腳本特徵碼"
                f"「{phrase}」。請用 LLM 做真正分析。"
            )
            break

    # ── FLUFF-001: Fluff phrase check ──
    fluff_count = sum(1 for p in FLUFF_PHRASES if p in core_logic)
    if fluff_count >= 2:
        errors.append(
            f"{prefix}: FLUFF-001: core_logic 含有 {fluff_count} 個空泛套語。"
            " 請用具體數據取代。"
        )

    return errors


def validate_file(json_path: str) -> dict:
    """Load a Logic.json file and validate it."""
    if not os.path.exists(json_path):
        return {
            'pass': False,
            'errors': [f"FILE-ERR: 找不到檔案 {json_path}"],
            'warnings': [],
            'stats': {'horses_checked': 0, 'horses_passed': 0, 'horses_failed': 0},
        }

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        return {
            'pass': False,
            'errors': [f"FILE-ERR: JSON 解析失敗: {e}"],
            'warnings': [],
            'stats': {'horses_checked': 0, 'horses_passed': 0, 'horses_failed': 0},
        }

    return validate_logic_json(data)


def main():
    """CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage: python validate_hkjc_logic_schema.py <Logic.json>")
        sys.exit(2)

    json_path = sys.argv[1]
    result = validate_file(json_path)

    # Print results
    fname = os.path.basename(json_path)
    total = result['stats']['horses_checked']
    passed = result['stats']['horses_passed']
    failed = result['stats']['horses_failed']

    if result['pass']:
        print(f"✅ {fname}: V4.2 schema validation PASSED ({total} horses, all OK)")
        for w in result['warnings']:
            print(f"  ⚠️ {w}")
        sys.exit(0)
    else:
        print(f"❌ {fname}: V4.2 schema validation FAILED ({failed}/{total} horses)")
        print()
        for err in result['errors']:
            print(f"  ❌ {err}")
        print()
        for w in result['warnings']:
            print(f"  ⚠️ {w}")
        sys.exit(1)


if __name__ == '__main__':
    main()
