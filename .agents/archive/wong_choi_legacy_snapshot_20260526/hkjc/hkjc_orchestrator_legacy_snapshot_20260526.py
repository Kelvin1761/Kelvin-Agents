#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import argparse
import sys
import subprocess
import re
import json
import time
import shutil

import urllib.request

# Import rating engine for auto-verdict computation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts')))
from rating_engine_v2 import parse_matrix_scores, compute_base_grade, apply_fine_tune, grade_sort_index, apply_s_grade_guards
from racing_content_guard import scan_json_for_dummy, scan_text_for_dummy, quarantine_file
from validate_hkjc_matrix_confidence import validate_hkjc_matrix_confidence, apply_hkjc_matrix_caps

# Import SIP engine V2 for automated SIP rule evaluation
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sip_engine import evaluate_horse_sips, evaluate_race_sips, format_sip_summary, get_race_context_flags
    SIP_ENGINE_AVAILABLE = True
except ImportError:
    SIP_ENGINE_AVAILABLE = False

# ── V4.2: Import all schema constants from central hkjc_schema.py ──
from hkjc_schema import (
    HKJC_SCHEMA_VERSION,
    HKJC_MATRIX_SCHEMA,
    HKJC_MATRIX_EXPECTED_KEYS,
    HKJC_MATRIX_RESOURCE_REQUIREMENTS,
    HKJC_LEGACY_8D_KEYS as HKJC_MATRIX_LEGACY_8D_KEYS,
    HKJC_LEGACY_TOP_LEVEL_FIELDS,
    ZH_EN_MATRIX_MAP as _ZH_EN_MATRIX_MAP,
    DUMMY_PHRASES,
    FLUFF_PHRASES,
    normalize_matrix_keys as _normalize_matrix,
)


def validate_matrix_resource_checks_hkjc(matrix: dict) -> list:
    """Ensure each HKJC matrix dimension cites the analyst resource it used."""
    errors = []
    normalized = _normalize_matrix(matrix) or {}
    for dim, required_files in HKJC_MATRIX_RESOURCE_REQUIREMENTS.items():
        dim_data = normalized.get(dim, {})
        if not isinstance(dim_data, dict):
            continue
        reasoning = str(dim_data.get('reasoning', ''))
        if '[FILL' in reasoning:
            continue
        if 'Resource Check:' not in reasoning and '資源檢查' not in reasoning:
            errors.append(
                f"WALL-024: matrix.{dim}.reasoning 缺少 [Resource Check: ...]。"
                "評級矩陣必須明示已讀對應 HKJC analyst resource。"
            )
            continue
        missing = [fname for fname in required_files if fname not in reasoning]
        if missing:
            errors.append(
                f"WALL-024: matrix.{dim}.reasoning Resource Check 缺少 {missing}。"
                "請按 WorkCard 對應維度必讀資源補回。"
            )
    return errors

def validate_v42_matrix_schema_hkjc(h_entry: dict) -> list:
    """Reject old HKJC 8D matrix/skeleton output before grading or compile."""
    errors = []
    matrix = h_entry.get('matrix', {})
    if not isinstance(matrix, dict):
        return ["WALL-022: matrix 必須係 dict，請用 V4.2 7 維 skeleton 重新填寫。"]

    raw_keys = set(matrix)
    legacy_keys = sorted(raw_keys & HKJC_MATRIX_LEGACY_8D_KEYS)
    if legacy_keys:
        errors.append(
            "WALL-022: 偵測到舊 8 維矩陣欄位 "
            f"{legacy_keys}。HKJC V4.2 只接受 7 維；"
            "距離證據併入 matrix.sectional，配備/部署併入 matrix.trainer_signal，"
            "休賽健康/場地新鮮感併入 matrix.horse_health。"
        )

    normalized = _normalize_matrix(matrix)
    normalized_keys = set(normalized or {})
    if len(normalized_keys) != len(raw_keys):
        errors.append(
            "WALL-022: matrix 同時包含同義/新舊 key，normalize 後出現重複。"
            "請只保留 HKJC V4.2 canonical English keys。"
        )

    missing = sorted(HKJC_MATRIX_EXPECTED_KEYS - normalized_keys)
    unknown = sorted(normalized_keys - HKJC_MATRIX_EXPECTED_KEYS)
    if missing:
        errors.append(f"WALL-022: HKJC V4.2 7 維矩陣缺少 key: {missing}")
    if unknown:
        errors.append(f"WALL-022: HKJC V4.2 7 維矩陣出現未知 key: {unknown}")

    top_level_legacy = sorted(k for k in HKJC_LEGACY_TOP_LEVEL_FIELDS if k in h_entry)
    if top_level_legacy:
        errors.append(
            f"WALL-022: 偵測到舊版 top-level 分析欄位 {top_level_legacy}。"
            "V4.2 已改為 matrix-only reasoning，請用最新 skeleton。"
        )

    return errors

def _matrix_score_value(matrix_data, key):
    item = (matrix_data or {}).get(key, {})
    return str(item.get('score', '') if isinstance(item, dict) else item)

def _race_shape_risk(matrix_data):
    score = _matrix_score_value(matrix_data, 'race_shape')
    if '❌' in score:
        return 2
    if '➖' in score or not score:
        return 1
    return 0

def _rating_sort_tuple(grade_i, core_pass, tick_count, double_ticks, total_fail,
                       core_fail, matrix_data, horse_num):
    """Top 2 oriented tiebreak: ability first, then conviction, then risk."""
    h_num_sort = int(horse_num) if str(horse_num).isdigit() else 999
    return (
        grade_i,
        -core_pass,
        -double_ticks,
        total_fail,
        core_fail,
        _race_shape_risk(matrix_data),
        -tick_count,
        h_num_sort,
    )


def _is_debut_runner_hkjc(h_obj: dict) -> bool:
    if h_obj.get('debut_runner', False) or h_obj.get('is_debut', False):
        return True
    if str(h_obj.get('career_tag', '')).upper() == 'DEBUT':
        return True
    try:
        return int(h_obj.get('career_race_starts', h_obj.get('hk_starts', 999))) == 0
    except (TypeError, ValueError):
        return False


def _apply_debut_cap_hkjc(grade: str, h_obj: dict) -> str:
    """Debut runners keep normal matrix arithmetic but cannot exceed A."""
    if _is_debut_runner_hkjc(h_obj) and grade_sort_index(grade) < grade_sort_index('A'):
        return 'A'
    return grade

def _top4_core_ticks(horses, h_num):
    """Count core+semi ✅ for a horse — used in verdict transparency."""
    h = horses.get(str(h_num), {})
    m = _normalize_matrix(h.get('matrix', {}))
    core_p, semi_p, _, _, _ = parse_matrix_scores(m, HKJC_MATRIX_SCHEMA)
    return core_p + semi_p


def _top4_fail_count(horses, h_num):
    """Count total ❌ for a horse — used in verdict transparency."""
    h = horses.get(str(h_num), {})
    m = _normalize_matrix(h.get('matrix', {}))
    _, _, _, _, total_f = parse_matrix_scores(m, HKJC_MATRIX_SCHEMA)
    return total_f


HKJC_REQUIRED_MATRIX_DIMS = {
    'stability', 'sectional', 'race_shape', 'trainer_signal',
    'horse_health', 'form_line', 'class_advantage',
}


def validate_hkjc_race_ready_for_verdict(logic_data):
    """Pre-verdict gate: ensure every horse is fully analysed.

    Checks:
      1. 'horses' key exists and is non-empty
      2. Every horse has a complete 7D matrix
      3. No [FILL] / dummy markers in any horse entry
      4. No generic fluff phrases
      5. No final_rating-only horse (matrix must be present)
      6. core_logic exists and is not empty / generic

    Raises ValueError with structured details on first failure.
    """
    horses = logic_data.get('horses', {})
    if not horses:
        raise ValueError("Verdict blocked: 'horses' key is empty or missing")

    errors = []
    for h_num, h_obj in horses.items():
        prefix = f"Horse {h_num} ({h_obj.get('horse_name', '?')})"

        # Matrix must exist
        matrix = h_obj.get('matrix', {})
        if not matrix:
            errors.append(f"{prefix}: matrix missing (final_rating-only horse not allowed)")
            continue

        # 7D completeness
        normalized = _normalize_matrix(matrix)
        missing_dims = HKJC_REQUIRED_MATRIX_DIMS - set(normalized.keys())
        if missing_dims:
            errors.append(f"{prefix}: missing matrix dimensions {sorted(missing_dims)}")

        for ve in validate_hkjc_matrix_confidence(h_obj):
            errors.append(f"{prefix}: {ve}")

        # Dummy / fluff scan
        dummy_errs = scan_json_for_dummy(h_obj, allow_pending_fill=False, path=f"horses.{h_num}")
        for de in dummy_errs:
            errors.append(f"{prefix}: {de}")

        # core_logic must exist and have substance
        core_logic = h_obj.get('core_logic', '')
        if not core_logic or core_logic.strip() in ('[FILL]', '', '待補充'):
            errors.append(f"{prefix}: core_logic is empty or placeholder")

    if errors:
        raise ValueError(
            "Verdict generation blocked — race not ready:\n"
            + "\n".join(f"  - {e}" for e in errors)
        )


def auto_compute_verdict_hkjc(logic_data, facts_path):
    """Auto-compute verdict Top 4 from matrix grades. Eliminates LLM verdict stop."""
    # Full pre-verdict validation
    validate_hkjc_race_ready_for_verdict(logic_data)

    horses = logic_data.get('horses', {})
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    
    # Compute grade for each horse
    graded = []
    for h_num, h_obj in horses.items():
        m_data = _normalize_matrix(h_obj.get('matrix', {}))
        core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(m_data, HKJC_MATRIX_SCHEMA)
        b_grade = compute_base_grade(
            core_pass, semi_pass, aux_pass, core_fail, total_fail,
            matrix_dims=m_data, position_key="race_shape"
        )
        ft = h_obj.get('fine_tune', {})
        ft_dir = ft.get('direction', '無') if isinstance(ft, dict) else str(ft)
        f_grade = apply_fine_tune(b_grade, ft_dir)
        # V4.2: ✅✅ promotion from A+
        if f_grade == 'A+':
            core_dbl, semi_dbl = _count_core_semi_double(m_data)
            promo_steps = min(core_dbl, 2) + (1 if semi_dbl >= 2 else 0)
            if promo_steps >= 3: f_grade = 'S+'
            elif promo_steps == 2: f_grade = 'S'
            elif promo_steps == 1: f_grade = 'S-'
        f_grade = _apply_debut_cap_hkjc(f_grade, h_obj)
        f_grade, cap_notes = apply_hkjc_matrix_caps(f_grade, h_obj)
        f_grade, _ = apply_s_grade_guards(
            f_grade, h_obj, {}, {k: v.get('score', '➖') if isinstance(v, dict) else str(v) for k, v in m_data.items()}, {},
            sectional_key='sectional', class_key='class_advantage',
            double_ticks=_count_matrix_double_ticks(m_data)
        )
        f_grade = _apply_debut_cap_hkjc(f_grade, h_obj)
        f_grade, more_cap_notes = apply_hkjc_matrix_caps(f_grade, h_obj)
        if more_cap_notes:
            h_obj["rating_cap_notes"] = sorted(set(cap_notes + more_cap_notes))
        grade_i = grade_sort_index(f_grade)
        tick_count = _count_matrix_ticks(m_data)
        double_ticks = _count_matrix_double_ticks(m_data)
        sort_key = _rating_sort_tuple(
            grade_i, core_pass, tick_count, double_ticks,
            total_fail, core_fail, m_data, h_num
        )
        graded.append((h_num, h_obj.get('horse_name', ''), f_grade, sort_key, tick_count, double_ticks))
    
    # Sort by grade, then core ability, conviction, risk profile, and horse number.
    graded.sort(key=lambda x: x[3])
    top4 = graded[:4]
    
    # Auto pace_flip_insurance from speed_map
    leaders = speed_map.get('leaders', [])
    closers = speed_map.get('closers', [])
    leader_names = {h_num: h_obj.get('horse_name', '') for h_num, h_obj in horses.items() if str(h_num) in [str(x) for x in leaders]}
    closer_names = {h_num: h_obj.get('horse_name', '') for h_num, h_obj in horses.items() if str(h_num) in [str(x) for x in closers]}
    
    faster_benefit = ''
    faster_hurt = ''
    slower_benefit = ''
    slower_hurt = ''
    if closer_names:
        best_closer = list(closer_names.items())[0]
        faster_benefit = f"{best_closer[0]}號 {best_closer[1]}"
    if leader_names:
        best_leader = list(leader_names.items())[0]
        slower_benefit = f"{best_leader[0]}號 {best_leader[1]}"
        faster_hurt = f"{best_leader[0]}號 {best_leader[1]}"
    if closer_names:
        worst_closer = list(closer_names.items())[-1]
        slower_hurt = f"{worst_closer[0]}號 {worst_closer[1]}"
    if top4:
        first = top4[0]
        second = top4[1] if len(top4) > 1 else top4[0]
        faster_benefit = faster_benefit or f"{first[0]}號 {first[1]}"
        faster_hurt = faster_hurt or f"{second[0]}號 {second[1]}"
        slower_benefit = slower_benefit or f"{first[0]}號 {first[1]}"
        slower_hurt = slower_hurt or f"{second[0]}號 {second[1]}"

    top_grade = top4[0][2] if top4 else 'C'
    confidence = '高' if top_grade in ('S', 'S-', 'A+', 'A') else ('中' if top_grade in ('A-', 'B+') else '低')
    pace_label = speed_map.get('predicted_pace') or speed_map.get('expected_pace') or 'Moderate'
    track_bias = speed_map.get('track_bias') or '以自動形勢圖作保守判斷'
    
    verdict = {
        'top4': [
            {'horse_number': str(h[0]), 'horse_name': h[1], 'grade': h[2],
             'tick_count': h[4], 'core_ticks': _top4_core_ticks(horses, h[0]),
             'total_fail': _top4_fail_count(horses, h[0]),
             'core_logic': horses.get(str(h[0]), {}).get('core_logic', '')}
            for h in top4
        ],
        'full_ranking': [
            {'horse_number': str(h[0]), 'horse_name': h[1], 'grade': h[2],
             'tick_count': h[4]}
            for h in graded
        ],
        'confidence': confidence,
        'track_scenario': f"{pace_label} pace；{track_bias}",
        'key_variables': '步速是否如預期、內外檔形勢、熱門馬能否避開早段消耗',
        'pace_flip_insurance': {
            'if_faster': {'benefit': faster_benefit or 'Top 4 中具末段優勢馬', 'hurt': faster_hurt or '前置高消耗馬'},
            'if_slower': {'benefit': slower_benefit or '前置/內檔馬', 'hurt': slower_hurt or '後上追勢馬'}
        },
        'emergency_brake': '若臨場退出、場地突然變化或步速圖與預期完全相反，需重跑 Orchestrator 重新編譯。',
        'blind_spots': {
            'sectionals': '段速由 Facts 錨點與矩陣綜合，未以單一 L400 直接定勝負。',
            'risk_management': 'Top 4 已按評級、✅數量與強信號排序。',
            'trials_illusion': '試閘/短樣本馬不可單靠印象升級。',
            'age_risk': '老馬、頂磅及外檔馬已視為主要風險來源。',
            'pace_collapse_darkhorse': faster_benefit or '未有明確步速崩潰冷門'
        }
    }
    
    logic_data.setdefault('race_analysis', {})['verdict'] = verdict
    return verdict


def _count_matrix_ticks(matrix_data):
    count = 0
    for item in (matrix_data or {}).values():
        score = str(item.get('score', '') if isinstance(item, dict) else item)
        if '✅' in score:
            count += 1
    return count


def _count_matrix_double_ticks(matrix_data):
    count = 0
    for item in (matrix_data or {}).values():
        score = str(item.get('score', '') if isinstance(item, dict) else item)
        if '✅✅' in score:
            count += 1
    return count


def _count_core_semi_double(matrix_data):
    """Count ✅✅ in core and semi-core dimensions for V4.2 promotion."""
    core_dbl = 0
    semi_dbl = 0
    for key, item in (matrix_data or {}).items():
        score = str(item.get('score', '') if isinstance(item, dict) else item)
        if '✅✅' not in score:
            continue
        dim_type = HKJC_MATRIX_SCHEMA.get(key, 'aux')
        if dim_type == 'core':
            core_dbl += 1
        elif dim_type == 'semi':
            semi_dbl += 1
    return core_dbl, semi_dbl


def verdict_needs_recompute(logic_data):
    verdict = logic_data.get('race_analysis', {}).get('verdict')
    if not isinstance(verdict, dict):
        return True
    top4 = verdict.get('top4')
    if not isinstance(top4, list) or len(top4) < 4:
        return True
    verdict_str = json.dumps(verdict, ensure_ascii=False)
    if any(marker in verdict_str for marker in ('[AUTO]', '[N/A]', 'PLACEHOLDER', '{{LLM_FILL}}', '[FILL]')):
        return True
    fli = verdict.get('pace_flip_insurance', {})
    for pace_key in ('if_faster', 'if_slower'):
        pace = fli.get(pace_key, {}) if isinstance(fli, dict) else {}
        if not pace.get('benefit') or not pace.get('hurt'):
            return True
    return False

# Cross-platform Python executable
PYTHON = "python3" if shutil.which("python3") else "python"

RACE_FILE_KIND_TERMS = {
    'racecard': ('排位表', 'Racecard'),
    'formguide': ('賽績', 'Formguide'),
    'facts': ('Facts.md',),
    'analysis': ('Analysis.md',),
}


def race_file_pattern(race_num, kind=None):
    """Return a regex that matches one race number without matching Race 10 for Race 1."""
    race_part = rf'(?:^|[\s_-])Race\s*0?{int(race_num)}(?!\d)'
    if not kind:
        return re.compile(race_part, re.IGNORECASE)
    terms = RACE_FILE_KIND_TERMS.get(kind, (kind,))
    term_part = '|'.join(re.escape(term) for term in terms)
    return re.compile(rf'{race_part}.*(?:{term_part})', re.IGNORECASE)


def matches_race_file(filename, race_num, kind=None):
    return bool(race_file_pattern(race_num, kind).search(filename))


def extract_race_number(filename):
    match = re.search(r'(?:^|[\s_-])Race\s*0?(\d+)(?!\d)', filename, re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_date_prefix(target_dir):
    """Normalize meeting folder names like 2026-04-12_ShaTin or 2026-04-12 ShaTin to MM-DD."""
    base = os.path.basename(os.path.normpath(target_dir))
    match = re.match(r'(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?:[ _-].*)?$', base)
    if match:
        return f"{match.group('month')}-{match.group('day')}"
    match = re.match(r'(?P<month>\d{2})-(?P<day>\d{2})(?:[ _-].*)?$', base)
    if match:
        return f"{match.group('month')}-{match.group('day')}"
    raise ValueError(
        f"Cannot derive MM-DD prefix from target directory '{base}'. "
        "Expected names like 2026-04-12_ShaTin or 2026-04-12 ShaTin."
    )


def load_qa_strikes(target_dir):
    strike_file = os.path.join(target_dir, '.qa_strikes.json')
    if not os.path.exists(strike_file):
        return {}
    try:
        with open(strike_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def qa_strike_count(strikes_data, race_num):
    return int(strikes_data.get(f'race_{race_num}_qa', 0) or 0)


def has_open_qa_strike(strikes_data, race_num):
    return qa_strike_count(strikes_data, race_num) > 0


def validate_intelligence_package(path):
    """Reject placeholder/dummy meeting intelligence so LLM cannot bypass State 1."""
    if not os.path.exists(path):
        return False, ['file missing']
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
    except OSError as exc:
        return False, [f'cannot read file: {exc}']

    stripped = content.strip()
    issues = []
    if len(stripped) < 500:
        issues.append('too short for real meeting intelligence')

    banned = ['[FILL]', '[AUTO]', 'TODO', 'dummy', 'stub', 'placeholder', '待補', '暫無資料']
    lowered = stripped.lower()
    for phrase in banned:
        if phrase.lower() in lowered:
            issues.append(f'contains placeholder marker: {phrase}')

    required_groups = {
        'weather': ('天氣', 'temperature', '溫度', 'humidity', '濕度', 'rain', '降雨', 'wind', '風'),
        'going': ('場地', 'going', '地面', '跑道'),
        'bias': ('偏差', 'bias', '欄', 'rail', '內欄', '外欄'),
        'source': ('來源', 'source', 'HKJC', 'Observatory', '天文台', 'Jockey Club'),
    }
    for label, terms in required_groups.items():
        if not any(term.lower() in lowered for term in terms):
            issues.append(f'missing {label} evidence')

    return not issues, issues


def notify_telegram(msg):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../scripts/send_telegram_msg.py")
    if os.path.exists(script_path):
        subprocess.run([PYTHON, script_path, msg])

# Session start time for preflight check
SESSION_START_TIME = time.time()

# ═══════════════════════════════════════════════════════════════
# V11 INFRASTRUCTURE — Meeting State, QA Diagnosis, Dummy Scanner, Context Injection
# ═══════════════════════════════════════════════════════════════

from datetime import datetime
from difflib import SequenceMatcher
from itertools import combinations

# DUMMY_PHRASES and FLUFF_PHRASES now imported from hkjc_schema.py


# ── Fix 2: .meeting_state.json Persistence ──

def build_meeting_state(target_dir, total_races, date_prefix):
    """Deep scan filesystem to build comprehensive state per-race.
    Priority: raw_data → intelligence → facts → speed_map → analysis → mc → qa
    """
    state = {
        '_version': 'V11',
        '_generated': datetime.now().isoformat(),
        '_target_dir': target_dir,
        'total_races': total_races,
        'date_prefix': date_prefix,
        'races': {},
        'next_action': None,
    }

    intel_file = os.path.join(target_dir, '_Meeting_Intelligence_Package.md')
    intel_ok, intel_issues = validate_intelligence_package(intel_file)
    state['intelligence_ready'] = intel_ok
    if intel_issues:
        state['intelligence_issues'] = intel_issues
    strikes_data = load_qa_strikes(target_dir)

    for r in range(1, total_races + 1):
        race_state = {
            'raw_data': False,
            'facts': False,
            'speed_map': False,
            'horses_total': 0,
            'horses_done': 0,
            'horses_pending': [],
            'batches_validated': 0,
            'verdict': False,
            'compiled': False,
            'mc_done': False,
            'qa_passed': False,
            'qa_strikes': 0,
            'stage': 'NOT_STARTED',
        }

        # Check raw data (racecard)
        racecards = [f for f in os.listdir(target_dir) if matches_race_file(f, r, 'racecard')]
        race_state['raw_data'] = len(racecards) > 0

        # Check facts
        facts_files = [f for f in os.listdir(target_dir) if matches_race_file(f, r, 'facts')]
        if facts_files:
            race_state['facts'] = True
            facts_path = os.path.join(target_dir, facts_files[0])
            try:
                from create_hkjc_logic_skeleton import extract_horse_block
                with open(facts_path, 'r', encoding='utf-8') as f:
                    fc = f.read()
                horse_nums = re.findall(r'### 馬號 (\d+) —', fc)
                race_state['horses_total'] = len(horse_nums)
            except Exception:
                pass

        # Check Logic.json
        logic_json = os.path.join(target_dir, f'Race_{r}_Logic.json')
        if os.path.exists(logic_json):
            try:
                with open(logic_json, 'r', encoding='utf-8') as f:
                    ld = json.load(f)
                sm = ld.get('race_analysis', {}).get('speed_map', {})
                sm_str = json.dumps(sm, ensure_ascii=False)
                if sm.get('predicted_pace') and sm['predicted_pace'] != '[FILL]' and '[FILL]' not in sm_str:
                    race_state['speed_map'] = True

                horses_dict = ld.get('horses', {})
                done_count = 0
                pending = []
                for hk, hv in horses_dict.items():
                    h_str = json.dumps({k: v for k, v in hv.items() if k not in ('base_rating', 'final_rating')}, ensure_ascii=False)
                    if '[FILL]' not in h_str:
                        done_count += 1
                    else:
                        pending.append(int(hk) if hk.isdigit() else hk)
                race_state['horses_done'] = done_count
                race_state['horses_pending'] = pending

                if ld.get('race_analysis', {}).get('verdict'):
                    race_state['verdict'] = True
            except (json.JSONDecodeError, OSError):
                pass

        # Check Analysis.md — full dummy scan + quarantine
        an_file = os.path.join(target_dir, f'{date_prefix} Race {r} Analysis.md')
        if os.path.exists(an_file):
            try:
                with open(an_file, 'r', encoding='utf-8') as f:
                    ac = f.read()
                dummy_errs = scan_text_for_dummy(ac)
                if dummy_errs:
                    # Quarantine the dummy Analysis.md
                    reason = f"build_meeting_state dummy scan (Race {r}):\n" + "\n".join(dummy_errs)
                    quarantine_file(an_file, reason)
                    race_state['compiled'] = False
                    race_state['stage'] = 'REPAIR_NEEDED'
                elif '缺失核心' in ac or '未分析' in ac:
                    race_state['compiled'] = False
                else:
                    race_state['compiled'] = True
            except Exception:
                pass

        # Check MC Results
        mc_file = os.path.join(target_dir, f'Race_{r}_MC_Results.json')
        race_state['mc_done'] = os.path.exists(mc_file)

        # QA status (check strikes file)
        race_state['qa_strikes'] = qa_strike_count(strikes_data, r)

        # Open QA strikes must keep the race out of COMPLETE until the gate passes again.
        if race_state['qa_strikes'] >= 3:
            race_state['stage'] = 'QA_BLOCKED'
        elif race_state['qa_strikes'] > 0:
            race_state['stage'] = 'QA_REPAIR'
        elif race_state['compiled'] and race_state['mc_done']:
            race_state['qa_passed'] = True
            race_state['stage'] = 'COMPLETE'
        elif race_state['compiled']:
            race_state['stage'] = 'AWAITING_MC'
        elif race_state['verdict']:
            race_state['stage'] = 'AWAITING_COMPILE'
        elif race_state['horses_done'] == race_state['horses_total'] and race_state['horses_total'] > 0:
            race_state['stage'] = 'AWAITING_VERDICT'
        elif race_state['speed_map']:
            race_state['stage'] = 'ANALYSING'
        elif race_state['facts']:
            race_state['stage'] = 'AWAITING_SPEED_MAP'
        elif race_state['raw_data']:
            race_state['stage'] = 'AWAITING_FACTS'
        else:
            race_state['stage'] = 'AWAITING_RAW_DATA'

        state['races'][str(r)] = race_state

    state['next_action'] = determine_next_action(state)
    return state


def save_meeting_state(state_path, state):
    """Atomic write with timestamp."""
    state['_last_updated'] = datetime.now().isoformat()
    state['next_action'] = determine_next_action(state)
    tmp_path = state_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, state_path)


def load_meeting_state(state_path):
    """Load + validate existing state."""
    if not os.path.exists(state_path):
        return None
    try:
        with open(state_path, 'r', encoding='utf-8') as f:
            state = json.load(f)
        if state.get('_version') != 'V11':
            return None
        return state
    except (json.JSONDecodeError, OSError):
        return None


def determine_next_action(state):
    """Priority: MISSING_RAW > AWAITING_INTEL > AWAITING_FACTS > SPEED_MAP > ANALYSIS > COMPILE > MC > QA"""
    if not state.get('intelligence_ready'):
        return {'action': 'CREATE_INTELLIGENCE_PACKAGE', 'race': None}

    for r_str, rs in state.get('races', {}).items():
        if rs['stage'] == 'AWAITING_RAW_DATA':
            return {'action': 'EXTRACT_RAW_DATA', 'race': int(r_str)}
        if rs['stage'] == 'AWAITING_FACTS':
            return {'action': 'GENERATE_FACTS', 'race': int(r_str)}
        if rs['stage'] == 'AWAITING_SPEED_MAP':
            return {'action': 'FILL_SPEED_MAP', 'race': int(r_str)}
        if rs['stage'] == 'ANALYSING':
            return {
                'action': 'ANALYSE_HORSES',
                'race': int(r_str),
                'pending': rs.get('horses_pending', []),
                'done': rs.get('horses_done', 0),
                'total': rs.get('horses_total', 0),
            }
        if rs['stage'] == 'AWAITING_VERDICT':
            return {'action': 'COMPUTE_VERDICT', 'race': int(r_str)}
        if rs['stage'] == 'AWAITING_COMPILE':
            return {'action': 'COMPILE', 'race': int(r_str)}
        if rs['stage'] == 'AWAITING_MC':
            return {'action': 'RUN_MC', 'race': int(r_str)}
        if rs['stage'] == 'QA_REPAIR':
            return {'action': 'REPAIR_QA_FAILURE', 'race': int(r_str), 'strikes': rs.get('qa_strikes', 0)}
        if rs['stage'] == 'QA_BLOCKED':
            return {'action': 'HUMAN_QA_INTERVENTION', 'race': int(r_str), 'strikes': rs.get('qa_strikes', 0)}

    return {'action': 'ALL_COMPLETE', 'race': None}


def print_meeting_dashboard(state):
    """ASCII dashboard showing all races' pipeline stages."""
    print(f"\n{'═' * 70}")
    print(f"📊 MEETING DASHBOARD — {state.get('total_races', '?')} 場賽事")
    print(f"{'═' * 70}")

    stage_icons = {
        'COMPLETE': '✅',
        'AWAITING_MC': '🎲',
        'QA_REPAIR': '🛠️',
        'QA_BLOCKED': '🛑',
        'AWAITING_COMPILE': '📝',
        'AWAITING_VERDICT': '⚖️',
        'ANALYSING': '🔬',
        'AWAITING_SPEED_MAP': '📍',
        'AWAITING_FACTS': '📋',
        'AWAITING_RAW_DATA': '📥',
        'NOT_STARTED': '⬜',
    }

    for r_str, rs in state.get('races', {}).items():
        icon = stage_icons.get(rs['stage'], '❓')
        horses_info = f"{rs['horses_done']}/{rs['horses_total']}" if rs['horses_total'] else '?'
        strikes = f" ⚠️x{rs['qa_strikes']}" if rs['qa_strikes'] > 0 else ""
        print(f"  Race {r_str:>2}: {icon} {rs['stage']:<22} | 馬匹: {horses_info:>5}{strikes}")

    na = state.get('next_action', {})
    print(f"{'─' * 70}")
    print(f"  📋 Next: {na.get('action', '?')}", end='')
    if na.get('race'):
        print(f" → Race {na['race']}", end='')
    if na.get('pending'):
        print(f" (待分析: {na['pending']})", end='')
    print()
    print(f"{'═' * 70}\n")


# ── Fix 7: QA Diagnosis ──

def generate_qa_diagnosis(race_num, strike_num, qa_stdout, qa_stderr,
                          logic_json_path, analysis_path, runtime_dir):
    """Parse QA errors, classify root causes, generate actionable diagnosis report."""
    errors = []
    for line in (qa_stdout or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('- ') or stripped.startswith('❌'):
            errors.append(stripped.lstrip('- ❌').strip())

    categories = {'FORMAT': [], 'CONTENT': [], 'LAZINESS': [], 'DATA': []}
    for err in errors:
        err_up = err.upper()
        if 'LAZY' in err_up or '相似' in err or '模板' in err:
            categories['LAZINESS'].append(err)
        elif 'FILL' in err_up or '字數' in err or 'word' in err_up or '太短' in err:
            categories['CONTENT'].append(err)
        elif 'P34' in err_up or 'MISSING' in err_up or 'tag' in err_up or '缺失' in err:
            categories['FORMAT'].append(err)
        else:
            categories['DATA'].append(err)

    # Load Logic.json to identify affected horses
    affected_horses = []
    try:
        with open(logic_json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
        for h_num, h_entry in logic_data.get('horses', {}).items():
            issues = []
            cl = h_entry.get('core_logic', '')
            if len(cl) < 80:
                issues.append(f'core_logic 太短 ({len(cl)} 字)')
            matrix = h_entry.get('matrix', {})
            for dim, d in matrix.items():
                if isinstance(d, dict):
                    r_text = d.get('reasoning', '')
                    if '[FILL]' in r_text or '[判讀: FILL]' in r_text:
                        issues.append(f'matrix.{dim} 未完成')
            if issues:
                affected_horses.append((h_num, h_entry.get('horse_name', ''), issues))
    except Exception:
        pass

    # Generate report
    report = []
    report.append(f"# 🔍 QA 診斷報告 — Race {race_num} (Strike {strike_num}/3)")
    report.append(f"**生成時間**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append("---")
    report.append("")

    total = len(errors)
    report.append(f"## 📊 錯誤總覽: {total} 個問題")
    report.append("")
    report.append("| 類別 | 數量 | 嚴重度 |")
    report.append("|------|:---:|:---:|")
    if categories['LAZINESS']:
        report.append(f"| 🚨 偷懶/模板 | {len(categories['LAZINESS'])} | CRITICAL |")
    if categories['CONTENT']:
        report.append(f"| 📝 內容不足 | {len(categories['CONTENT'])} | HIGH |")
    if categories['FORMAT']:
        report.append(f"| 📋 格式缺失 | {len(categories['FORMAT'])} | MEDIUM |")
    if categories['DATA']:
        report.append(f"| 📊 數據錯誤 | {len(categories['DATA'])} | HIGH |")
    report.append("")

    for cat_name, cat_label in [
        ('LAZINESS', '🚨 偷懶/模板偵測'), ('CONTENT', '📝 內容不足'),
        ('FORMAT', '📋 格式缺失'), ('DATA', '📊 數據錯誤')
    ]:
        if categories[cat_name]:
            report.append(f"## {cat_label}")
            for err in categories[cat_name]:
                report.append(f"- ❌ {err}")
            report.append("")

    if affected_horses:
        report.append("## 🐎 受影響馬匹")
        for h_num, h_name, issues in affected_horses:
            report.append(f"### Horse #{h_num} ({h_name})")
            for issue in issues:
                report.append(f"- {issue}")
            report.append("")

    report.append("---")
    report.append("## ✅ 修復指引")
    report.append("")
    if categories['LAZINESS']:
        report.append("### 偷懶問題修復")
        report.append("1. 重新閱讀每匹受影響馬匹嘅 WorkCard.md")
        report.append("2. core_logic 必須引用該馬匹獨有嘅賽績/數據")
        report.append("3. 嚴禁複製其他馬匹嘅分析文字")
        report.append("")
    if categories['CONTENT']:
        report.append("### 內容不足修復")
        report.append("1. 確認每匹馬嘅 core_logic ≥80 字")
        report.append("2. 確認所有 [FILL] / [判讀: FILL] 已被替換")
        report.append("")
    if categories['FORMAT']:
        report.append("### 格式修復")
        report.append("呢啲係 compile 腳本嘅問題，通常唔需要 LLM 修復。")
        report.append("")
    if categories['DATA']:
        report.append("### 數據錯誤修復")
        report.append("1. 核對 Facts.md 原始數據")
        report.append("2. 確認馬名、檔位、負磅等基礎資料正確")
        report.append("")

    report.append("---")
    report.append(f"⚠️ **呢個係 Strike {strike_num}/3。第 3 次失敗將停機等候人工介入。**")

    os.makedirs(runtime_dir, exist_ok=True)
    diag_path = os.path.join(runtime_dir, f"QA_Diagnosis_Race_{race_num}_Strike_{strike_num}.md")
    with open(diag_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    return diag_path


# ── Fix 8: Pre-Race Dummy Content Scanner ──

def scan_race_content_quality(logic_json_path):
    """Pre-race Python-only scan for dummy/template content in Logic.json.
    Zero LLM token cost — pure Python string matching.
    Returns dict: contaminated_horses, issues, action (CLEAN/PURGE_PARTIAL/PURGE_ALL)
    """
    result = {'contaminated_horses': [], 'issues': [], 'action': 'CLEAN'}

    if not os.path.exists(logic_json_path):
        return result

    try:
        with open(logic_json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return result

    horses = data.get('horses', {})
    if not horses:
        return result

    contaminated = []
    for h_num, h_entry in horses.items():
        horse_issues = []
        core_logic = h_entry.get('core_logic', '')

        # Check 1: Dummy phrases
        for phrase in DUMMY_PHRASES:
            if phrase in core_logic:
                horse_issues.append(f'Dummy phrase: 「{phrase}」')
                break

        # Check 2: Fluff phrases ≥2
        fluff_count = sum(1 for p in FLUFF_PHRASES if p in core_logic)
        if fluff_count >= 2:
            horse_issues.append(f'Fluff phrases x{fluff_count}')

        # Check 3: Too short but not [FILL]
        if core_logic and '[FILL]' not in core_logic and len(core_logic) < 40:
            horse_issues.append(f'core_logic 太短 ({len(core_logic)} 字)')

        # Check 4: Matrix reasoning all identical
        reasonings = []
        matrix = h_entry.get('matrix', {})
        for dim, dim_data in matrix.items():
            if isinstance(dim_data, dict):
                r_txt = dim_data.get('reasoning', '')
                if isinstance(r_txt, list):
                    r_txt = '\\n'.join(str(x) for x in r_txt)
                if r_txt and '[FILL]' not in r_txt and '[判讀' not in r_txt:
                    reasonings.append(r_txt)
        if len(reasonings) >= 4:
            unique_r = set(reasonings)
            if len(unique_r) <= 2:
                horse_issues.append(f'Matrix reasoning 只有 {len(unique_r)} 種 (全部 {len(reasonings)} 個維度)')

        # Check 5: Missing NONCE
        h_json_str = json.dumps(h_entry, ensure_ascii=False)
        if '[FILL]' not in h_json_str and not h_entry.get('_validation_nonce'):
            horse_issues.append('缺少 NONCE — 可能未經 skeleton 腳本')

        # Check 6: Placeholder core_logic
        if core_logic in ('正常', '分析中', '待分析', ''):
            horse_issues.append(f'core_logic 係 placeholder: 「{core_logic}」')

        if horse_issues:
            contaminated.append({
                'horse_num': h_num,
                'horse_name': h_entry.get('horse_name', ''),
                'issues': horse_issues,
            })

    result['contaminated_horses'] = contaminated

    # Cross-horse: all core_logic identical
    all_logics = [h.get('core_logic', '') for h in horses.values()
                  if h.get('core_logic') and '[FILL]' not in h.get('core_logic', '')
                  and '[判讀' not in h.get('core_logic', '')]
    if len(all_logics) >= 3:
        unique_logics = set(all_logics)
        if len(unique_logics) <= 2:
            result['issues'].append(f'全場只有 {len(unique_logics)} 種 core_logic ({len(all_logics)} 匹馬)')
            result['action'] = 'PURGE_ALL'

    # Cross-horse: SequenceMatcher similarity
    if len(all_logics) >= 3:
        logic_pairs = list(combinations(enumerate(all_logics), 2))
        high_sim = sum(
            1 for (_, a), (_, b) in logic_pairs
            if SequenceMatcher(None, a, b).ratio() > 0.60
        )
        if logic_pairs and high_sim / len(logic_pairs) > 0.5:
            result['issues'].append(f'{high_sim}/{len(logic_pairs)} pairs 相似度 >60%')
            result['action'] = 'PURGE_ALL'

    if contaminated and result['action'] == 'CLEAN':
        result['action'] = 'PURGE_PARTIAL'

    return result


# ── Fix 10: Context Injection Gateway ──

def print_context_injection():
    """Print critical rules directly in console output. LLM always sees this."""
    print("=" * 60)
    print("📋 CONTEXT INJECTION — 必讀規則 (Python 自動注入)")
    print("=" * 60)
    print()
    print("🔴 規則 1：Python Lead")
    print("   Orchestrator 控制所有流程。LLM 只負責填 Logic.json。")
    print("   嚴禁自行決定做邊場邊匹。")
    print()
    print("🔴 規則 2：逐匹分析")
    print("   每匹馬必須讀 WorkCard → 分析 → 填 JSON。")
    print("   嚴禁建立 auto_fill / batch_fill .py 腳本。")
    print()
    print("🔴 規則 3：core_logic 品質")
    print("   必須 ≥80 字、引用具體數據（日期/名次/L400/負磅）。")
    print("   嚴禁寫「正常」「一般」等模板化語句。")
    print()
    print("🔴 規則 4：如果做唔完")
    print("   停止 + 通知用戶開新 Conversation。")
    print("   絕對唔好為咗趕進度而降低分析質素。")
    print()
    print("📖 完整規則: SETUP.md (L51-111)")
    print("📖 機讀指令: engine_directives.md")
    print("=" * 60)


def print_race_context(race_num, total_horses, pending_horses):
    """Per-race context reminder."""
    print(f"\n{'─' * 50}")
    print(f"🏇 Race {race_num} — {total_horses} 匹馬")
    print(f"📋 待分析: {pending_horses}")
    print(f"⚠️ 每匹馬必須讀 WorkCard → 獨立分析 → 填 JSON")
    print(f"⚠️ core_logic ≥80字 + 引用具體數據")
    print(f"{'─' * 50}\n")


def ensure_context_files_loaded(target_dir):
    """Check and print which critical context files exist."""
    files_to_check = [
        ('.meeting_state.json', '📊 Meeting State', 'CRITICAL'),
        ('_Meeting_Intelligence_Package.md', '🧠 Intelligence Package', 'HIGH'),
    ]
    print("\n📂 Context Files 狀態：")
    for filename, label, priority in files_to_check:
        path = os.path.join(target_dir, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"   ✅ {label}: {filename} ({size:,} bytes)")
        else:
            print(f"   ❌ {label}: {filename} 缺失 [{priority}]")

    directives_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        '..', 'resources', 'engine_directives.md'
    )
    if os.path.exists(directives_path):
        print(f"   ✅ 🤖 Engine Directives: engine_directives.md")
    else:
        print(f"   ❌ 🤖 Engine Directives: 缺失 [CRITICAL]")


# ── Fix 3: Per-Batch Cross-Horse QA ──

def validate_batch_cross_horse(batch_horses, horses_dict, logic_json_path):
    """Validate a batch of horses for cross-horse quality issues.
    BATCH-001: Cross-horse reasoning similarity >60%
    BATCH-002: [FILL] residuals
    BATCH-003: Score diversity (all same = batch fill)
    Returns list of error strings. Empty = pass.
    """
    errors = []
    batch_entries = []
    for h in batch_horses:
        entry = horses_dict.get(str(h), {})
        if entry:
            batch_entries.append((str(h), entry))

    if len(batch_entries) < 2:
        return errors

    # BATCH-001: Cross-horse core_logic similarity
    logics = [(h, e.get('core_logic', '')) for h, e in batch_entries
              if e.get('core_logic') and '[FILL]' not in e.get('core_logic', '')]
    if len(logics) >= 2:
        for (h1, l1), (h2, l2) in combinations(logics, 2):
            sim = SequenceMatcher(None, l1, l2).ratio()
            if sim > 0.60:
                errors.append(f"BATCH-001: Horse {h1} ↔ {h2} core_logic 相似度 {sim:.0%}")

    # BATCH-002: [FILL] residuals
    for h, e in batch_entries:
        e_str = json.dumps({k: v for k, v in e.items() if k not in ('base_rating', 'final_rating')}, ensure_ascii=False)
        fill_count = e_str.count('[FILL]')
        if fill_count > 0:
            errors.append(f"BATCH-002: Horse {h} 仍有 {fill_count} 個 [FILL]")

    # BATCH-003: Score diversity
    scores = []
    for h, e in batch_entries:
        m = e.get('matrix', {})
        h_scores = [d.get('score', '') for d in m.values() if isinstance(d, dict)]
        scores.append(tuple(h_scores))
    if len(scores) >= 2 and len(set(scores)) == 1:
        errors.append(f"BATCH-003: 全部 {len(scores)} 匹馬 matrix scores 完全相同")

    return errors

def parse_url_for_details(url):
    match = re.search(r'RaceDate=(\d{4})/(\d{2})/(\d{2}).*?&Racecourse=([A-Za-z]+)', url, re.IGNORECASE)
    
    if not match:
        print(f"🔍 [Auto-Discovery] URL lacks explicit RaceDate. Fetching HTML to resolve next meeting date...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
            # Look for racedate=2026/04/12&Racecourse=ST matches in HTML
            html_match = re.search(r'racedate=(\d{4})/(\d{2})/(\d{2})&amp;Racecourse=([A-Za-z]+)', html, re.IGNORECASE)
            if not html_match:
                html_match = re.search(r'racedate=(\d{4})/(\d{2})/(\d{2})&Racecourse=([A-Za-z]+)', html, re.IGNORECASE)
            
            if html_match:
                print(f"✅ [Auto-Discovery] Found next meeting: {html_match.group(1)}/{html_match.group(2)}/{html_match.group(3)} at {html_match.group(4)}")
                match = html_match
            else:
                raise ValueError("Invalid HKJC URL format and could not auto-discover from HTML. Cannot extract Venue and Date.")
        except Exception as e:
            raise ValueError(f"Failed to auto-discover date from URL: {e}")

    date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    venue_code = match.group(4).upper()
    venue_map = {"ST": "ShaTin", "HV": "HappyValley"}
    venue = venue_map.get(venue_code, venue_code)
    
    resolved_url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={match.group(1)}/{match.group(2)}/{match.group(3)}&Racecourse={venue_code}&RaceNo=1"
    
    return venue, date_str, resolved_url

def get_target_dir(venue, formatted_date, auto_create=False):
    base_dir = "."
    dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date}_{venue}")]
    if dirs:
        return os.path.abspath(os.path.join(base_dir, dirs[0]))
    
    if auto_create:
        new_dir = os.path.abspath(os.path.join(base_dir, f"{formatted_date}_{venue}"))
        os.makedirs(new_dir, exist_ok=True)
        return new_dir
    return None

def detect_total_races_from_url(url):
    """Detect actual number of races from HKJC racecard HTML page.
    Parses RaceNo= references to find the maximum race number.
    Falls back to 9 (HV default) or 11 (ST default) if detection fails.
    """
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as response:
            html = response.read().decode('utf-8')
        race_nos = set(int(x) for x in re.findall(r'RaceNo=(\d+)', html))
        if race_nos:
            max_race = max(race_nos)
            print(f"✅ [Auto-Detection] 從 HKJC 頁面偵測到 {max_race} 場賽事 (RaceNo: {sorted(race_nos)})")
            return max_race
    except Exception as e:
        print(f"⚠️ [Auto-Detection] 無法偵測場數: {e}")

    # Fallback: guess from venue in URL
    if 'HV' in url.upper():
        print(f"⚠️ [Fallback] 跑馬地預設 9 場")
        return 9
    else:
        print(f"⚠️ [Fallback] 沙田預設 11 場")
        return 11


def trigger_extractor(url, target_dir):
    print(f"🚀 [Orchestrator] 啟動 HKJC Race Extractor 提取全日數據...")
    script_path = ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts/batch_extract.py"
    if not os.path.exists(script_path):
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        sys.exit(1)
    # Dynamically detect actual race count instead of hardcoding 1-11
    total = detect_total_races_from_url(url)
    race_range = f"1-{total}"
    print(f"📋 [Orchestrator] 提取場次範圍: {race_range}")
    try:
        subprocess.run([PYTHON, script_path, "--base_url", url, "--races", race_range, "--output_dir", target_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] 數據提取腳本執行失敗: {e}")
        sys.exit(1)

def discover_total_races(target_dir):
    """Discover total races from extracted racecard files.
    Filters out empty/shell files (<500 bytes) to avoid counting
    races that don't actually exist on the race day.
    """
    MIN_RACECARD_SIZE = 500  # bytes — valid racecards are typically 3-4KB+
    racecards = [
        f for f in os.listdir(target_dir)
        if extract_race_number(f) is not None
        and any(term in f for term in RACE_FILE_KIND_TERMS['racecard'])
    ]
    max_race = 0
    skipped = []
    for card in racecards:
        race_num = extract_race_number(card)
        if race_num is not None:
            card_path = os.path.join(target_dir, card)
            card_size = os.path.getsize(card_path) if os.path.exists(card_path) else 0
            if card_size < MIN_RACECARD_SIZE:
                skipped.append((race_num, card_size))
                continue
            if race_num > max_race:
                max_race = race_num
    if skipped:
        skipped_str = ', '.join(f'Race {r} ({s}B)' for r, s in sorted(skipped))
        print(f"⚠️ [discover_total_races] 過濾空殼排位表: {skipped_str}")
    return max_race

def check_raw_data_completeness(target_dir, total_races):
    missing_data = []
    
    if not any("全日出賽馬匹資料 (PDF).md" in f for f in os.listdir(target_dir)):
        missing_data.append("全日出賽馬匹資料 (PDF).md")
        
    for race_num in range(1, total_races + 1):
        if not any(matches_race_file(f, race_num, 'formguide') for f in os.listdir(target_dir)):
            missing_data.append(f"Race {race_num} 賽績.md")
        if not any(matches_race_file(f, race_num, 'racecard') for f in os.listdir(target_dir)):
            missing_data.append(f"Race {race_num} 排位表.md")
    return missing_data

def get_rc_fg_paths(target_dir, race_num):
    rc, fg = None, None
    for f in os.listdir(target_dir):
        if matches_race_file(f, race_num, 'racecard'):
            rc = os.path.join(target_dir, f)
        if matches_race_file(f, race_num, 'formguide'):
            fg = os.path.join(target_dir, f)
    return rc, fg
    
def get_horse_numbers(facts_file):
    # Parse facts file to get list of horse numbers
    with open(facts_file, 'r', encoding='utf-8') as f:
        content = f.read()
    horse_pattern = re.compile(r'^### 馬號 (\d+) —', re.MULTILINE)
    horses = [int(m.group(1)) for m in horse_pattern.finditer(content)]
    return horses


def _parse_num_list_from_speed_map_line(value):
    return [int(x) for x in re.findall(r'\d+', value or '')]


def parse_hkjc_speed_map_from_facts(facts_content):
    """Parse the first-class Python-generated speed map block from Facts.md."""
    m = re.search(
        r'^###\s*🗺️\s*自動步速圖.*?(?=^###\s+馬號|\n={6,}|\Z)',
        facts_content,
        re.MULTILINE | re.DOTALL
    )
    if not m:
        return {}
    block = m.group(0)

    def _field(name):
        fm = re.search(rf'-\s*\*\*{re.escape(name)}:\*\*\s*(.+?)$', block, re.MULTILINE)
        return fm.group(1).strip() if fm else ''

    speed_map = {
        'predicted_pace': _field('predicted_pace'),
        'pace_confidence': _field('pace_confidence'),
        'style_confidence': _field('style_confidence'),
        'leaders': _parse_num_list_from_speed_map_line(_field('leaders')),
        'pressers': _parse_num_list_from_speed_map_line(_field('pressers')),
        'on_pace': _parse_num_list_from_speed_map_line(_field('on_pace')),
        'mid_pack': _parse_num_list_from_speed_map_line(_field('mid_pack')),
        'closers': _parse_num_list_from_speed_map_line(_field('closers')),
        'style_evidence': _field('style_evidence'),
        'track_bias': _field('track_bias'),
        'tactical_nodes': _field('tactical_nodes'),
        'collapse_point': _field('collapse_point'),
        'source': _field('source') or 'FACTS_SPEED_MODEL',
    }
    required = ('predicted_pace', 'track_bias', 'tactical_nodes', 'collapse_point')
    if not all(speed_map.get(k) for k in required):
        return {}
    return speed_map


def auto_build_hkjc_speed_map_from_facts(facts_content, target_dir=None):
    """Parse the Facts Engine speed map from Facts.md.

    If the Facts Engine embedded a speed map block (🗺️ 自動步速圖), parse and return it.
    If no speed map block exists (e.g. Facts generation failed), return [FILL] placeholders
    so the pipeline stops at Step B for manual intervention.

    NOTE: The previous fallback heuristic (full-text keyword search) was removed because
    it produced severely inflated leader counts and universal 'Chaotic' pace predictions.
    Speed maps are too important for analysis to be auto-guessed from noisy text.
    """
    generated = parse_hkjc_speed_map_from_facts(facts_content)
    if generated:
        return generated

    # No Facts Engine speed map found — return placeholders instead of guessing
    print("⚠️ Facts Engine 步速圖缺失！Pipeline 將停喺 Step B 等待人手填寫 speed_map。")
    print("   → 請確認 Facts.md 包含 '### 🗺️ 自動步速圖' block，或人手填寫 Logic.json speed_map。")
    return {
        'predicted_pace': '[FILL]',
        'pace_confidence': '[FILL]',
        'style_confidence': '[FILL]',
        'leaders': [],
        'pressers': [],
        'on_pace': [],
        'mid_pack': [],
        'closers': [],
        'style_evidence': '[FILL]',
        'track_bias': '[FILL]',
        'tactical_nodes': '[FILL]',
        'collapse_point': '[FILL]',
        'source': 'MISSING_NEEDS_MANUAL_FILL',
    }

def get_batches(horses, size=3):
    return [horses[i:i + size] for i in range(0, len(horses), size)]

def update_session_tasks(target_dir, total_races, missing_raw, chk_weather, chk_facts_done, analysis_status_dict):
    tasks_path = os.path.join(target_dir, "_session_tasks.md")
    
    lines = ["# HKJC Session Tasks\n"]
    lines.append("## 基礎建設")
    
    chk_pdf = '[ ]' if any("PDF" in str(m) for m in missing_raw) else '[x]'
    lines.append(f"- {chk_pdf} 官方大報表 PDF 提取 (starter_all_chi.pdf)")
    
    raw_files_missing = any("賽績" in str(m) for m in missing_raw) or any("排位表" in str(m) for m in missing_raw)
    lines.append(f"- {'[ ]' if raw_files_missing else '[x]'} 原始賽事資料下載 (Race 1-{total_races})")
    lines.append(f"- {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    lines.append(f"- {'[x]' if chk_facts_done == total_races else '[ ]'} 事實錨點 Facts.md 全部生成 ({chk_facts_done}/{total_races})\n")
    
    lines.append("## 馬匹分析 (Batch Status)")
    for r in range(1, total_races + 1):
        status = analysis_status_dict.get(r, "待啟動")
        chk = "[x]" if "完成" in status else "[ ]"
        lines.append(f"- {chk} **Race {r}**: {status}")

    with open(tasks_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return tasks_path

def run_preflight_check(target_dir):
    """Run preflight environment scan to detect suspicious files."""
    preflight_script = ".agents/scripts/preflight_environment_check.py"
    if os.path.exists(preflight_script):
        result = subprocess.run(
            [PYTHON, preflight_script, target_dir, "--domain", "hkjc",
             "--session-start", str(SESSION_START_TIME)],
            capture_output=True, text=True, encoding='utf-8'
        )
        print(result.stdout)
        if result.returncode == 2:
            print("🛑 Preflight check FAILED — 請清理可疑檔案後再執行！")
            sys.exit(2)


def _next_cmd(target_dir):
    """Print machine-readable re-run command for LLM auto-execution."""
    dir_arg = os.path.abspath(os.path.normpath(target_dir))
    print(f"\nNEXT_CMD: {PYTHON} .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py \"{dir_arg}\" --auto")


# ═══════════════════════════════════════════════════════════════
# V10 Helper Functions: Firewall Validation + File-Watch Loop
# ═══════════════════════════════════════════════════════════════

def extract_hkjc_horse_facts_block(target_horse, facts_content):
    """Extract a single horse's facts block from HKJC Facts.md."""
    h_block_match = re.search(rf'### 馬號 {target_horse} — ', facts_content)
    if h_block_match:
        h_start = h_block_match.start()
        h_next = re.search(r'### 馬號 \d+ — ', facts_content[h_block_match.end():])
        h_end = h_block_match.end() + h_next.start() if h_next else len(facts_content)
        return facts_content[h_start:h_end]
    return ""


def extract_hkjc_fact_anchors(horse_block):
    """Extract key factual data points from a HKJC horse's Facts block for work card generation."""
    anchors = {}

    # Horse name, jockey, trainer, weight, barrier
    m = re.search(r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?)(?: \| 練馬師:\s*(.+?))? \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)',
                  horse_block)
    if m:
        anchors['name'] = m.group(2).strip()
        anchors['jockey'] = m.group(3).strip()
        anchors['trainer'] = m.group(4).strip() if m.group(4) else '未知'
        anchors['weight'] = m.group(5)
        anchors['barrier'] = m.group(6)
    else:
        anchors['name'] = '未知'
        anchors['jockey'] = '?'
        anchors['trainer'] = '?'
        anchors['weight'] = '?'
        anchors['barrier'] = '?'

    # Recent form (Last 10)
    m = re.search(r'Last 10.*?:\s*`([^`]+)`', horse_block)
    anchors['recent_form'] = m.group(1) if m else '無'

    # Career stats
    m = re.search(r'生涯[：:]\s*(\d+)[：:]', horse_block)
    anchors['career_starts'] = m.group(1) if m else '0'
    hk_starts_m = re.search(r'港賽\s*(\d+)', horse_block)
    anchors['hk_starts'] = hk_starts_m.group(1) if hk_starts_m else anchors['career_starts']

    # Fitness arc
    starts = int(anchors['career_starts'])
    hk_starts = int(anchors['hk_starts'])
    if starts == 0:
        anchors['fitness_arc'] = '初出馬'
    elif starts == 1:
        anchors['fitness_arc'] = '二出'
    elif starts == 2:
        anchors['fitness_arc'] = 'Third-up'
    elif starts <= 5:
        anchors['fitness_arc'] = f'輕度備戰（{starts}仗）'
    else:
        anchors['fitness_arc'] = f'Deep Prep（{starts}仗）'

    # Debut / Import horse detection
    debut_text_hint = bool(re.search(r'無往績記錄|首出|首次出賽|新馬', horse_block))
    anchors['is_debut'] = starts == 0 and hk_starts == 0 and debut_text_hint
    anchors['is_import'] = False
    if anchors['is_debut']:
        # Detect imported horse via PPG/ISG tags or overseas form markers
        if re.search(r'PPG|ISG|自購新馬|進口|Previously trained|Imported', horse_block, re.IGNORECASE):
            anchors['is_import'] = True
            anchors['import_origin'] = 'Unknown'
        elif re.search(r'(?:AUS|EUR|GB|IRE|JPN|NZ|FR|USA)\s*[:：]', horse_block):
            anchors['is_import'] = True
            anchors['import_origin'] = 'Detected'
    elif starts <= 2:
        # Low-start runners that may also be imports adapting
        if re.search(r'PPG|ISG|自購新馬|進口|Previously trained|Imported', horse_block, re.IGNORECASE):
            anchors['is_import'] = True
            anchors['import_origin'] = 'Adapting'

    # Race shape assessment
    m = re.search(r'加權走位形勢:\s*([^→]+?)→', horse_block)
    anchors['''race_shape_assessment'''] = m.group(1).strip() if m else '無數據'

    # Formline strength
    m = re.search(r'\*\*綜合評估:\*\*\s*(.+?)(?:\n|$)', horse_block)
    anchors['formline_strength'] = m.group(1).strip() if m else '無資料'

    # Track records
    m = re.search(r'好地:\s*([^\|]+)', horse_block)
    anchors['good_record'] = m.group(1).strip() if m else '無'
    m = re.search(r'軟地:\s*([^\|]+)', horse_block)
    anchors['soft_record'] = m.group(1).strip() if m else '無'
    m = re.search(r'同場:\s*([^\|]+)', horse_block)
    anchors['course_record'] = m.group(1).strip() if m else '無'

    # Engine type
    m = re.search(r'引擎:\s*(.+?)\s*\|', horse_block)
    anchors['engine_type'] = m.group(1).strip() if m else '未知'

    # Distance record
    m = re.search(r'今仗\s*\d+m.*?:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['distance_record'] = m.group(1).strip() if m else '無紀錄'

    # Best distance
    m = re.search(r'⭐最佳', horse_block)
    if m:
        dist_m = re.search(r'([\d≤]+m?).*?⭐最佳', horse_block)
        anchors['best_distance'] = dist_m.group(1) if dist_m else '未知'
    else:
        anchors['best_distance'] = '數據不足'

    # Last run remark
    remarks = re.findall(r'\|\s*[^|]*(?:Led|Settled|Held|Keen|Pushed|Sat|Box seat)[^|]*\|', horse_block)
    anchors['last_run_remark'] = remarks[0].strip('| ') if remarks else '無'

    return anchors


def load_draw_stats_for_workcard(race_num: int, barrier: int) -> dict:
    """Load per-horse draw stats from hkjc_draw_stats.json."""
    # hkjc_draw_stats.json lives in .agents/scripts/ (same dir imported by sys.path at top)
    scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts'))
    json_path = os.path.join(scripts_dir, 'hkjc_draw_stats.json')
    if not os.path.exists(json_path):
        return {}
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            ds = json.load(f)
        for race in ds.get('races', []):
            if race.get('race') == race_num:
                for d in race.get('draws', []):
                    if d.get('draw') == barrier:
                        return d
                # Race found but barrier not in data (e.g. barrier 13-14)
                max_draw = max(d['draw'] for d in race['draws']) if race['draws'] else 0
                return {'verdict': f'⚠️超出範圍(最大檔{max_draw})', 'win_pct': 'N/A', 'quinella_pct': 'N/A', 'place_pct': 'N/A'}
    except Exception:
        pass
    return {}


def load_full_draw_table_for_workcard(race_num: int) -> str:
    """Load full draw stats table for a race, formatted as Markdown for WorkCard."""
    scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts'))
    json_path = os.path.join(scripts_dir, 'hkjc_draw_stats.json')
    if not os.path.exists(json_path):
        return ''
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            ds = json.load(f)
        for race in ds.get('races', []):
            if race.get('race') == race_num:
                draws = race.get('draws', [])
                if not draws:
                    return ''
                lines = [f"📊 **全場檔位統計** (第{race_num}場 {race.get('distance','?')}m {race.get('surface','?')}):",
                         "| 檔位 | 出賽 | 上名% | 入Q% | 勝率% | 判定 |",
                         "|:---:|:---:|:---:|:---:|:---:|:---:|"]
                for d in sorted(draws, key=lambda x: x['draw']):
                    lines.append(
                        f"| {d['draw']} | {d.get('starts','?')} | {d.get('place_pct','?')} | "
                        f"{d.get('quinella_pct','?')} | {d['win_pct']} | {d['verdict']} |")
                avg_place = race.get('avg_place_pct', '?')
                avg_win = race.get('avg_win_pct', '?')
                lines.append(f"*平均上名率: {avg_place}% | 平均勝率: {avg_win}%*")
                return '\n'.join(lines)
    except Exception:
        pass
    return ''


def generate_hkjc_work_card(horse_num, facts_content, logic_data, runtime_dir,
                            sm_pace, sm_bias, horse_idx=0, total_horses=1,
                            race_num=1):
    """Generate a guided analysis work card for a SINGLE HKJC horse."""
    horse_block = extract_hkjc_horse_facts_block(horse_num, facts_content)
    if not horse_block:
        return None

    anchors = extract_hkjc_fact_anchors(horse_block)
    race_class = logic_data.get('race_analysis', {}).get('race_class', '?')
    distance = logic_data.get('race_analysis', {}).get('distance', '?')
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {}) or {}
    pace_confidence = speed_map.get('pace_confidence', 'Unknown')
    style_confidence = speed_map.get('style_confidence', 'Unknown')

    card = []
    card.append(f"# 🐎 分析工作卡 [{horse_idx+1}/{total_horses}] — 馬號 {horse_num} {anchors['name']}")
    card.append(f"**檔位: {anchors['barrier']} | 騎師: {anchors['jockey']} | 練馬師: {anchors['trainer']} | 負磅: {anchors['weight']}**")
    card.append(f"📍 步速: {sm_pace} | Pace信心: {pace_confidence} | 跑法信心: {style_confidence} | 偏差: {sm_bias} | 班次: {race_class} | 距離: {distance}")
    if anchors.get('is_import'):
        card.append("> ⚠️ **[CAREER_TAG: IMPORTED_DEBUT]** — 必讀 `05b_debut_guide.md`；用進口馬香港首出模板處理海外轉譯與適應期封頂。")
    elif anchors.get('is_debut'):
        card.append("> ⚠️ **[CAREER_TAG: DEBUT]** — 必讀 `05b_debut_guide.md`；使用初出馬專用模板，穩定性/賽績線不得沿用正常賽績格式。")
    card.append("")
    card.append("---")
    card.append("## 📖 必讀資源 (分析前必須讀取)")
    card.append("**每個維度判斷前，必須讀取對應嘅 analyst 規則檔案。唔可以單純憑數據自由發揮。**")
    card.append("")
    card.append("| 維度 | 必讀資源 | 關鍵規則 |")
    card.append("|:---|:---|:---|")
    card.append("| 1️⃣ 狀態與穩定性 | `05_forensic_analysis.md` | 逐場可靠性+近6場數據+頭馬距離 / SIP-HK01 |")
    card.append("| 2️⃣ 段速質量 | `03_engine_pace_context.md` + `04_engine_corrections.md` | 正賽段速；初出馬改用 Sire/試閘/晨操 readiness |")
    card.append("| 3️⃣ 形勢與走位 | `05_forensic_analysis.md` | 檔位數據+今日預計走位+近3-5仗走位消耗 / SIP-HK02；不引用 race-level speed_map 評分 |")
    card.append("| 4️⃣ 騎練訊號 | `07b_trainer_signals.md` + `07c_jockey_profiles.md` | 配備+近6場騎師歷史+人馬配搭 / SIP-HK06 |")
    card.append("| 5️⃣ 馬匹健康 | `05_forensic_analysis.md` + `10a/10b/10c_track_*.md` | 醫療紀錄+休賽+體重 |")
    card.append("| 6️⃣ 賽績線 | Facts.md 賽績線表格 | 精簡摘要 (Python 預生成) |")
    card.append("| 7️⃣ 級數優勢 | `06_rating_engine.md` | 班次變動+負重對比 / SIP-HK04 / SIP-HK07 |")
    card.append("| 📊 評級矩陣 | `06_rating_engine.md` | 7 維度查表法 + 微調 + 寬恕加分 |")
    card.append("| 🔗 因子交互 | `11_factor_interaction.md` | 降班群聚互銷 SIP-HK05 / MC-Logic Divergence SIP-HK08 |")
    card.append("")
    card.append("---")
    card.append("## ⚠️ 指引")
    card.append("- 每個維度必須根據 skeleton reasoning 注入嘅**Python 預計算數據** + 上方對應嘅 **analyst 規則**作出判斷")
    card.append("- 分數只可以係 ✅✅ / ✅ / ➖ / ❌ / ❌❌")
    card.append("- 理據必須引用具體數據（日期、場地、名次、PI 數值等）")
    card.append("- **V4.2 reasoning 格式:** 第一行必須保留 `[Resource Check: ...]`，中段保留 `[數據/規則]` evidence slots，最後只寫一次 `→ [判讀: ...]`；唔好將判讀原文複製多一次")
    card.append("- 唔可以寫「一般」、「尚可」、「配搭無特別異常」等模板化語句")
    card.append("---")
    card.append("")

    card.append("## 📐 填寫順序（嚴格執行）")
    card.append("1. **填寫 7 個矩陣維度** (`matrix.*.score` + `matrix.*.reasoning`) — reasoning 必須保留 evidence slots + 最後一行 `→ [判讀: ...]`")
    card.append("2. **填寫** `race_forgiveness`、`interaction_matrix`、`forgiveness_bonus`")
    card.append("3. **最後填** `core_logic`、`advantages`、`disadvantages`")
    card.append("- ⚠️ V4.2: 唔再有 `analytical_breakdown`、`sectional_forensic`、standalone `race_shape` — 所有分析直接寫入 matrix reasoning")
    card.append("- ❌ 禁止直接從 Facts 數據跳到矩陣評分，必須經過分析推導")
    card.append("---")
    card.append("")
    card.append("## 🚫 輸出格式禁令 [V4.3 新增]")
    card.append("**以下獨立 section 全部禁止出現在矩陣外面，所有數據必須消化在 7 維度矩陣內：**")
    card.append("- ❌ 禁止: 獨立 `#### 🏇 晨操摘要` section → 晨操數據已注入 `狀態與穩定性` + `騎練訊號`")
    card.append("- ❌ 禁止: 獨立 `#### 🐴 馬匹剖析` section → 所有賽績數據已分佈在矩陣各維度")
    card.append("- ❌ 禁止: 獨立 `#### 🔗 賽績線` 完整表格 → 賽績線精簡摘要已在矩陣維度 6️⃣")
    card.append("- ✅ 正確格式: 馬匹 header → 直接進入 `#### 🧮 評級矩陣` → 結論")
    card.append("---")
    card.append("")

    horse_entry = logic_data.get('horses', {}).get(str(horse_num), {})
    trackwork = horse_entry.get('trackwork', {}) if isinstance(horse_entry, dict) else {}
    tw_digest = trackwork.get('stability_digest', {}) if isinstance(trackwork, dict) else {}
    tw_load = tw_digest.get('workout_load_21d', {}) if isinstance(tw_digest, dict) else {}
    # ── Build Python-Driven Output Template (V4.3) ──
    # All data is pre-filled from skeleton reasoning; LLM only fills [FILL] judgment slots
    matrix = horse_entry.get('matrix', {}) if isinstance(horse_entry, dict) else {}

    # Helper: format skeleton reasoning lines for output template
    def _fmt_reasoning(dim_key):
        dim = matrix.get(dim_key, {})
        reasoning = dim.get('reasoning', '數據不足')
        # Split multi-line reasoning into bullet points
        lines = []
        for part in reasoning.split('\n'):
            part = part.strip()
            if part:
                lines.append(f"  - {part}")
        return '\n'.join(lines) if lines else '  - 數據不足'

    # Build trackwork summary for stability dimension
    tw_summary = ''
    if trackwork:
        status_zh = {'ok': '已提取', 'partial': '部分提取', 'missing': '缺資料', 'failed': '提取失敗'}.get(str(trackwork.get('status', 'missing')), str(trackwork.get('status', 'missing')))
        mode_zh = {
            'status_continuity': '狀態延續', 'pattern_replay': '翻案復刻',
            'debut_pressure': '初出備戰', 'insufficient_data': '資料不足',
        }.get(str(tw_digest.get('career_category', 'insufficient_data')), str(tw_digest.get('career_category', 'insufficient_data')))
        trend_zh = {'improving': '加強中', 'stable': '穩定', 'easing': '放緩', 'interrupted': '中斷', 'unknown': '未明'}.get(str(tw_digest.get('workout_intensity_trend', 'unknown')), str(tw_digest.get('workout_intensity_trend', 'unknown')))
        positives_zh = '、'.join(tw_digest.get('stability_positive_flags', []) or []) or '無'
        risks_zh = '、'.join(tw_digest.get('stability_risk_flags', []) or []) or '無'
        tw_summary = (
            f"  - 晨操 digest: status={status_zh}, mode={mode_zh}, "
            f"load=快操{tw_load.get('gallops', 0)}/試閘{tw_load.get('trials', 0)}/"
            f"踱步{tw_load.get('trotting', 0)}/游水{tw_load.get('swimming', 0)}/"
            f"空白{tw_load.get('blank_days', 0)}, trend={trend_zh}, "
            f"maintenance={tw_digest.get('maintenance_score')}, "
            f"readiness={tw_digest.get('readiness_score')}, "
            f"pattern_replay={tw_digest.get('pattern_replay_score')}, "
            f"positives={positives_zh}, risks={risks_zh}, "
            f"instruction={tw_digest.get('llm_stability_instruction', '無')}\n"
            f"  - 晨操判讀規則: 正式賽績與晨操 50/50；近績差馬要將晨操視為翻案入口"
        )

    # ── Python-Driven Output Template ──
    card.append("## 📄 Python-Driven 輸出模板 [V4.3]")
    card.append("**以下係你必須使用嘅輸出格式。所有數據行已由 Python 預填，你只需填寫 `[FILL]` 部分。**")
    card.append("**❌ 禁止喺矩陣外面加任何獨立 section（馬匹剖析/晨操摘要/賽績線表格）**")
    card.append("**✅ 直接輸出以下模板，保留所有 Python 預填數據行，只填判讀。**")
    card.append("")
    card.append("```output_template")

    # ── Dimension 1: Stability ──
    card.append(f"#### 🧮 評級矩陣 (7-Dimension Matrix)")
    card.append("")
    card.append(f"##### 狀態與穩定性 [半核心]: `[FILL: ✅✅/✅/➖/❌/❌❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 近6場/全賽績穩定性、名次波動、頭馬距離趨勢；醫療事故作廢規則")
    card.append(f"  - Resource Check: 05_forensic_analysis.md / 穩定性+醫療事故作廢規則")
    card.append(_fmt_reasoning('stability'))
    if tw_summary:
        card.append(tw_summary)
    card.append(f"  - 📂 必須閱讀 Facts.md「📋 完整賽績檔案」全部賽事記錄")
    card.append(f"  - 📎 必讀: 05_forensic_analysis.md (穩定性計算 + 醫療事故自動作廢規則)")
    card.append(f"  - 📊 **判讀:** `[FILL: ~50字判讀，引用具體數據]`")
    card.append("")

    # ── Dimension 2: Sectional ──
    card.append(f"##### 🔬 段速質量 (包含段速法醫) [核心]: `[FILL: ✅✅/✅/➖/❌/❌❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 引擎類型、L400/L600、全段速剖面 Δ、完成時間偏差")
    card.append(f"  - Resource Check: 03_engine_pace_context.md + 04_engine_corrections.md + 05_forensic_analysis.md")
    card.append(_fmt_reasoning('sectional'))
    card.append(f"  - 📂 必須閱讀 Facts.md「📋 完整賽績檔案」全部段速數據")
    card.append(f"  - 📎 必讀: 03_engine_pace_context.md + 04_engine_corrections.md + 05_forensic_analysis.md")
    card.append(f"  - 📊 **判讀:** `[FILL: ~50字判讀，引用具體數據]`")
    card.append("")

    # ── Dimension 3: Race Shape ──
    card.append(f"##### 形勢與走位 [半核心]: `[FILL: ✅✅/✅/➖/❌/❌❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 今日預計位置、跑法、檔位統計、近仗走位；不引用 race-level speed_map 評分")
    card.append(f"  - Resource Check: 05_forensic_analysis.md / 形勢走位")
    card.append(_fmt_reasoning('race_shape'))
    card.append(f"  - 📎 必讀: 05_forensic_analysis.md")
    card.append(f"  - 📊 **判讀:** `[FILL: ~50字判讀，引用具體數據]`")
    card.append("")

    # ── Dimension 4: Trainer Signal ──
    card.append(f"##### 練馬師訊號 [核心]: `[FILL: ✅✅/✅/➖/❌/❌❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 練馬師部署、騎師配搭、近6場騎師歷史、換騎效應")
    card.append(f"  - Resource Check: 07b_trainer_signals.md + 07c_jockey_profiles.md")
    card.append(_fmt_reasoning('trainer_signal'))
    card.append(f"  - 📎 必讀: 07b_trainer_signals.md + 07c_jockey_profiles.md")
    card.append(f"  - 📊 **判讀:** `[FILL: ~50字判讀，引用具體數據]`")
    card.append("")

    # ── Dimension 5: Horse Health ──
    card.append(f"##### 馬匹健康 / 新鮮感 [輔助]: `[FILL: ✅/➖/❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 休賽日數、體重趨勢、健康掃描、場地轉換新鮮感")
    card.append(f"  - Resource Check: 05_forensic_analysis.md + 10a/10b/10c_track_*.md")
    card.append(_fmt_reasoning('horse_health'))
    card.append(f"  - 📎 健康評估規則: 有事故+復原證據=已復原(➖/✅); 有事故+未復原=風險(❌); 無事故=正常(✅)")
    card.append(f"  - 📊 **判讀:** `[FILL: ~50字判讀，引用具體數據]`")
    card.append("")

    # ── Dimension 6: Form Line ──
    fl_score_default = 'N/A' if anchors.get('is_debut') else '[FILL: ✅✅/✅/➖/❌]'
    card.append(f"##### 賽績線 [輔助]: `{fl_score_default}`")
    card.append(f"  - 🧭 **V4.2檢查點:** Facts.md 賽績線強度、對手後續表現、強組/弱組判定")
    card.append(f"  - Resource Check: Facts.md 賽績線表格 + 05_forensic_analysis.md")
    card.append(_fmt_reasoning('form_line'))
    card.append(f"  - 📎 必讀: 05_forensic_analysis.md (賽績線)")
    card.append(f"  - 📊 **判讀:** `[FILL: ~30字判讀]`")
    card.append("")

    # ── Dimension 7: Class Advantage ──
    card.append(f"##### 級數優勢 [輔助]: `[FILL: ✅✅/✅/➖/❌]`")
    card.append(f"  - 🧭 **V4.2檢查點:** 班次升降、評分趨勢、負磅甜蜜點、頂磅壓力")
    card.append(f"  - Resource Check: 06_rating_engine.md")
    card.append(_fmt_reasoning('class_advantage'))
    card.append(f"  - 📎 必讀: 06_rating_engine.md + 場地模組 10a/10b/10c")
    card.append(f"  - 📊 **判讀:** `[FILL: ~30字判讀]`")
    card.append("")

    # ── Matrix Arithmetic + Conclusion ──
    card.append("**🔢 矩陣算術:** [AUTO — 根據你填嘅 ✅/❌ 計數]")
    card.append("**14.2 基礎評級:** `[AUTO]` | **規則**: `[AUTO]`")
    card.append("**14.2B 微調:** 通道A: `[FILL]` | 通道B(SYN/CON): `[FILL]` | 觸發: `[FILL]`")
    card.append("**🔗 互動矩陣 [ANCHOR-互動矩陣]:** SYN: `[FILL]` | CON: `[FILL]` | CONTRA: `[FILL]`")
    card.append("**14.3 覆蓋:** `[FILL or 無]`")
    card.append("")
    card.append("#### 💡 結論與評語")
    card.append("> - **核心邏輯:** [FILL: ~100字自然段落]")
    card.append("> - **最大競爭優勢:** [FILL: 2-3點，每點≥10字]")
    card.append("> - **最大失敗風險:** [FILL: 2-3點，每點≥10字]")
    card.append("")
    card.append("**⭐ 最終評級:** `[AUTO]`")
    card.append("```")
    card.append("")
    card.append("---")

    # ── Debut Horse Dedicated Analysis Path ──
    if anchors.get('is_debut'):
        card.append("## 🆕 初出馬專屬分析路徑")
        card.append("⚠️ **此馬為首次出賽，以下維度必須使用替代數據源：**")
        card.append("- **穩定性** → 預設 ➖；可用備戰穩定性升/跌")
        card.append("- **段速質量** → 用 Sire 早熟/距離適性 + 試閘速度 + 晨操 readiness 替代")
        card.append("- **賽績線** → **強制 N/A（不計入矩陣）**")
        card.append("- **評級算術** → final rating 最高 A")
        card.append("")
        sire_profile = horse_entry.get('debut_sire_profile', {}) if isinstance(horse_entry, dict) else {}
        trial_profile = horse_entry.get('debut_trial_profile', {}) if isinstance(horse_entry, dict) else {}
        readiness_flags = horse_entry.get('debut_readiness_flags', []) if isinstance(horse_entry, dict) else []
        card.append("### 🧬 Sire / Trial / Readiness Evidence")
        card.append(f"- Sire profile: `{json.dumps(sire_profile, ensure_ascii=False) if sire_profile else 'missing'}`")
        card.append(f"- Trial profile: `{json.dumps(trial_profile, ensure_ascii=False) if trial_profile else 'missing'}`")
        card.append(f"- Readiness flags: `{', '.join(readiness_flags) if readiness_flags else '無'}`")
        card.append("---")
        card.append("")

    # ── Import Horse Dedicated Analysis Path ──
    if anchors.get('is_import'):
        card.append("## 🌏 進口馬專屬分析路徑")
        card.append(f"⚠️ **此馬為海外進口馬 (偵測來源: {anchors.get('import_origin', 'Unknown')})**")
        card.append("")
        card.append("### 海外賽績轉譯 (必填)")
        card.append("| 項目 | 判斷 |")
        card.append("|:---|:---|")
        card.append("| 原產地 | [FILL: AUS/EUR/JPN/其他] |")
        card.append("| 海外最高班次 | [FILL] |")
        card.append("| 對應香港班次 | [FILL: 一班/二班/三班/四班/五班] |")
        card.append("| 場地轉換風險 | [FILL: 低/中/高] |")
        card.append("| 在港試閘表現 | [FILL: 出色/普通/失望] |")
        card.append("")
        card.append("⚠️ 進口馬適應期封頂：首戰=B+ (港試閘佳→A-) | 第2仗入前5=正常 | 第3仗起=正常")
        card.append("---")
        card.append("")

    # ── SIP Trigger Section (V2: Facts.md driven) ──
    if SIP_ENGINE_AVAILABLE:
        _sip_horse_data = {
            'horse_name': anchors.get('name', ''),
            'wins': 0 if anchors.get('career_starts', '0') != '0' else None,
            'starts': int(anchors.get('career_starts', '0')) if anchors.get('career_starts', '0').isdigit() else 0,
            'weight': int(anchors.get('weight', '126')) if str(anchors.get('weight', '')).isdigit() else 126,
            'barrier': int(anchors.get('barrier', '5')) if str(anchors.get('barrier', '')).isdigit() else 5,
            'margin_trend': anchors.get('race_shape_assessment', ''),
            'formline_strength': anchors.get('formline_strength', ''),
            'recent_form': anchors.get('recent_form', ''),
        }
        _sip_race_ctx = {
            'distance': distance,
            'track': '草地',
            'field_size': total_horses,
        }
        _horse_sips = evaluate_horse_sips(_sip_horse_data, _sip_race_ctx)
        _race_sips = evaluate_race_sips(_sip_race_ctx, {})
        _ctx_flags = get_race_context_flags(_sip_race_ctx)
        sip_text = format_sip_summary(_horse_sips, _race_sips, _ctx_flags)
        card.append(sip_text)

    card.append("## 🔟 core_logic 寫作指引")
    card.append("- **約 100 字**流暢廣東話分析")
    card.append("- **必須涵蓋**: 近態趨勢 → 檔位形勢 → 段速能力 → 整體前景")
    card.append("- **必須引用**: 具體數字（近績名次、L400 時間、負磅、休賽日數）")
    card.append("")
    card.append("---")
    card.append("## 📄 原始賽績數據（嚴禁修改）")
    card.append(horse_block)

    card_path = os.path.join(runtime_dir, f"Horse_{horse_num}_WorkCard.md")
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(card))
    return card_path


def watch_single_horse_hkjc(json_file, horse_num, validate_fn, all_horses,
                            poll_interval=0.5, timeout_minutes=60,
                            skeleton_snapshot=None):
    """Watch for a SINGLE HKJC horse to be filled and validated.
    V12: Added race_analysis tamper protection — Python-computed fields are immutable.
    """
    hkey = str(horse_num)
    last_mtime = os.path.getmtime(json_file)
    own_write_mtime = 0
    start_time = time.time()
    last_heartbeat = time.time()

    # V12: Snapshot race_analysis (Python-computed, immutable to LLM)
    _race_analysis_snapshot = None
    try:
        with open(json_file, 'r', encoding='utf-8') as _snap_f:
            _snap_data = json.load(_snap_f)
        _race_analysis_snapshot = json.loads(json.dumps(_snap_data.get('race_analysis', {})))
    except Exception:
        pass

    # Pre-check
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            init_data = json.load(f)
        h_entry = init_data.get('horses', {}).get(hkey, {})
        if h_entry:
            h_check = json.dumps(
                {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                ensure_ascii=False
            )
            if '[FILL]' not in h_check:
                errors = validate_fn(horse_num, h_entry, init_data.get('horses', {}), all_horses, json_file)
                if not errors:
                    return h_entry
    except Exception:
        pass

    poll_interval = max(0.1, float(poll_interval))
    debounce_seconds = min(0.2, poll_interval)
    print(f"\n👀 Python 正在監控 馬號 {horse_num}... (每 {poll_interval:g} 秒 | 超時 {timeout_minutes} 分鐘)")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_minutes * 60:
                print(f"\n⏰ 馬號 {horse_num} 監控超時！")
                return None
            if time.time() - last_heartbeat > 60:
                mins = int(elapsed / 60)
                print(f"   💓 [{mins}m] 仍在等待 馬號 {horse_num}...")
                last_heartbeat = time.time()
            try:
                current_mtime = os.path.getmtime(json_file)
            except OSError:
                time.sleep(poll_interval)
                continue
            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                time.sleep(poll_interval)
                continue
            time.sleep(debounce_seconds)
            last_mtime = current_mtime

            logic_data = None
            for attempt in range(3):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        logic_data = json.load(f)
                    break
                except (json.JSONDecodeError, OSError):
                    if attempt < 2:
                        time.sleep(0.5)
            if logic_data is None:
                continue

            horses_dict = logic_data.get('horses', {})
            h_entry = horses_dict.get(hkey, {})
            if not h_entry:
                continue
            h_check = json.dumps(
                {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                ensure_ascii=False
            )
            if '[FILL]' in h_check:
                continue

            # V11.1: Skeleton Preservation Merge — auto-merge LLM input into skeleton
            if skeleton_snapshot:
                h_entry = deep_merge_skeleton(skeleton_snapshot, h_entry)
                horses_dict[hkey] = h_entry
                logic_data['horses'] = horses_dict

            # V12: Restore race_analysis from snapshot (prevent LLM tampering)
            if _race_analysis_snapshot:
                current_ra = logic_data.get('race_analysis', {})
                if current_ra != _race_analysis_snapshot:
                    print(f"   🔒 V12: race_analysis 被修改，自動恢復 Python 快照")
                    logic_data['race_analysis'] = _race_analysis_snapshot

            if skeleton_snapshot or _race_analysis_snapshot:
                with open(json_file, 'w', encoding='utf-8') as wf:
                    json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                own_write_mtime = os.path.getmtime(json_file)
                last_mtime = own_write_mtime

            errors = validate_fn(horse_num, h_entry, horses_dict, all_horses, json_file)
            if errors:
                name = h_entry.get('horse_name', '')
                print(f"\n🚨 馬號 {horse_num} ({name}) Firewall 失敗!")
                for e in errors:
                    print(f"   ❌ {e}")
                print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
                h_entry['core_logic'] = '[FILL]'
                with open(json_file, 'w', encoding='utf-8') as wf:
                    json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                own_write_mtime = os.path.getmtime(json_file)
                last_mtime = own_write_mtime
            else:
                return h_entry

    except KeyboardInterrupt:
        print(f"\n⚠️ 用戶中斷！馬號 {horse_num} 未完成。")
        return None


def print_hkjc_analysis_summary(horse_entry, horse_num):
    """Print quality summary for HKJC horse analysis."""
    matrix = _normalize_matrix(horse_entry.get('matrix', {}))
    scores = []
    display_dims = [
        ('狀態', 'stability'),
        ('段速', 'sectional'),
        ('形勢', 'race_shape'),
        ('騎練', 'trainer_signal'),
        ('健康', 'horse_health'),
        ('賽線', 'form_line'),
        ('級數', 'class_advantage'),
    ]
    for short_dim, dim in display_dims:
        data = matrix.get(dim, {})
        score = data.get('score', '?') if isinstance(data, dict) else str(data)
        scores.append(f"{short_dim}:{score}")
    print(f"   📊 矩陣: {' | '.join(scores)}")

    core_logic = horse_entry.get('core_logic', '')
    if core_logic and len(core_logic) > 20:
        print(f"   💡 邏輯: {core_logic[:80]}...")
        print(f"   📏 長度: {len(core_logic)} 字")

    all_scores = [d.get('score', '') for d in matrix.values() if isinstance(d, dict)]
    unique_scores = set(all_scores)
    if len(unique_scores) <= 2 and len(all_scores) >= 6:
        print(f"   ⚠️ 品質警告: 分數差異度低（只有 {len(unique_scores)} 種分數）")
    elif len(unique_scores) >= 4:
        print(f"   ✨ 分數差異度良好 ({len(unique_scores)} 種不同分數)")


def deep_merge_skeleton(skeleton, llm_input):
    """Deep-merge LLM's filled values INTO the original skeleton.
    
    Ensures all skeleton fields are preserved even if LLM writes a
    simplified format. This is a preventive design — not a validation wall.
    
    Rules:
    - skeleton keys are always preserved (even if LLM omits them)
    - LLM's new keys are accepted (e.g. _validated)
    - dict values are recursively merged
    - [FILL]/[AUTO] placeholders are replaced by LLM values
    - locked data (no [FILL]) keeps LLM's version if changed
    """
    merged = dict(skeleton)  # Start from skeleton as base
    
    for key, llm_val in llm_input.items():
        if key not in skeleton:
            # LLM added a new key (e.g. _validated, scenario_tags) — accept it
            merged[key] = llm_val
            continue
        
        skel_val = skeleton[key]
        
        # Both are dicts → recursive merge
        if isinstance(skel_val, dict) and isinstance(llm_val, dict):
            merged[key] = deep_merge_skeleton(skel_val, llm_val)
            continue
        
        # Skeleton value contains [FILL] → LLM is expected to replace it
        if isinstance(skel_val, str) and '[FILL]' in skel_val:
            merged[key] = llm_val
            continue
        
        # Skeleton value is [AUTO] → orchestrator computes later
        if isinstance(skel_val, str) and '[AUTO]' in skel_val:
            merged[key] = llm_val if (isinstance(llm_val, str) and '[AUTO]' not in llm_val) else skel_val
            continue
        
        # Otherwise keep LLM's version (it may have legitimately updated)
        merged[key] = llm_val
    
    return merged


# Fluff phrases that indicate lazy/template analysis
FLUFF_PHRASES = [
    '配搭無特別異常', '一般而言', '整體尚可', '無特別優劣',
    '中規中矩', '表現平平', '沒有明顯', '無明顯',
    '暫時未有特別', '有待觀察', '資料有限',
    # V2: LLM lazy-generation patterns (sounds analytical but zero data)
    '此項指標表現優異', '完全符合預期', '這個維度的表現相當穩定',
    '展現出強大實力', '無明顯破綻', '分數絕對買至名歸',
    '綜合各項變數', '深入分析段速與消耗', '結合騎練動態與馬匹狀態',
    '根據近期賽績數據', '在這方面展現', '表現相當穩定',
]

# Dummy phrases from known auto_fill scripts (auto_fill_loop.py / auto_expert_analyst.py)
DUMMY_PHRASES = [
    '自動匹配系統法則', '具備潛力', '狀態待觀', '分析中', '待補充',
    '有一定競爭力', '表現尚可接受', '基於客觀數據自動判定',
    '符合各項賽事指標', '根據賽事數據',
]

def validate_hkjc_firewalls(h, h_entry, horses_dict, all_horses, json_file):
    """HKJC-specific per-horse firewall validation. Returns list of error strings.
    V3: Added WALL-012~017 to catch auto_fill bypass scripts.
    """
    errors = []
    
    # Check for [FILL] or fluff using dummy guard
    dummy_errs = scan_json_for_dummy(h_entry, allow_pending_fill=False)
    if dummy_errs:
        for err in dummy_errs:
            errors.append(f"WALL-DUMMY: {err}")
            
    locked_nonce = h_entry.get('_validation_nonce', '')
    errors.extend(validate_v42_matrix_schema_hkjc(h_entry))
    errors.extend(validate_matrix_resource_checks_hkjc(h_entry.get('matrix', {})))
    
    # WALL-008: Nonce validation
    if not locked_nonce:
        errors.append(f"WALL-008: 缺失防偽標籤 _validation_nonce (可能使用了不合規的 Batch Script 繞過)")
    
    # WALL-019: Nonce prefix validation — only SKEL_ nonces from skeleton scripts are valid
    if locked_nonce and not locked_nonce.startswith('SKEL_'):
        errors.append(f"WALL-019: NONCE 格式無效 ('{locked_nonce[:20]}...')。只接受 SKEL_ 開頭嘅 nonce（由 skeleton 腳本生成）。"
                      f" 如果你見到 AUTO_FILL_ 開頭，代表有 bypass 腳本偽造咗 nonce。")
    
    # WALL-009: Matrix completeness — all 7 dimensions must have valid scores
    matrix = h_entry.get('matrix', {})
    valid_scores = {'✅✅', '✅', '➖', '❌', '❌❌'}
    filled_dims = 0
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            score = dim_data.get('score', '')
            if score in valid_scores:
                filled_dims += 1
    if filled_dims < 6:  # At least 6 of 7 dimensions
        errors.append(f"WALL-009: 矩陣維度不足 ({filled_dims}/7)，至少需要 6 個有效維度")
    
    # WALL-010: Score variety — at least 2 different scores (prevent all-same lazy fill)
    if filled_dims >= 6:
        unique_scores = set()
        for dim_data in matrix.values():
            if isinstance(dim_data, dict):
                score = dim_data.get('score', '')
                if score in valid_scores:
                    unique_scores.add(score)
        if len(unique_scores) < 2:
            errors.append(f"WALL-010: 分數差異度過低 (只有 {len(unique_scores)} 種分數)，可能為批量填充")
    
    # WALL-011: Fluff detection — core_logic must not contain template phrases
    core_logic = str(h_entry.get('core_logic', ''))
    for phrase in FLUFF_PHRASES:
        if phrase in core_logic:
            errors.append(f"WALL-011: core_logic 含有模板化語句「{phrase}」，請替換為具體數據分析")
            break  # Only report first fluff hit
    
    # WALL-012: core_logic minimum substance — at least 50 Chinese characters
    chi_chars = len(re.findall(r'[\u4e00-\u9fff]', core_logic))
    if chi_chars < 50:
        errors.append(f"WALL-012: core_logic 過短 ({chi_chars} 個中文字，至少需要 50 個)。"
                      f" 請寫出 2-4 句引用具體賽績數據嘅分析。")
    
    # WALL-013: matrix reasoning substance — at least 4 dimensions with ≥10 chars reasoning
    substantial_dims = 0
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            reasoning = str(dim_data.get('reasoning', ''))
            reasoning_chi = len(re.findall(r'[\u4e00-\u9fff]', reasoning))
            if reasoning_chi >= 10:
                substantial_dims += 1
    if substantial_dims < 4:
        errors.append(f"WALL-013: 矩陣 reasoning 實質性不足 (只有 {substantial_dims}/7 個維度有 ≥10 字嘅分析)。"
                      f" 每個維度嘅 reasoning 必須引用具體數據。")
    
    # WALL-020: Data anchor check — reasoning must contain concrete references, not just template prose
    # Check that at least 4 dimensions have a number/date/percentage/L400 reference
    data_anchor_pattern = re.compile(r'\d+[%％]|\d{1,2}/\d{1,2}|L400|L600|\d+磅|\d+m|\d+秒|\d+\.\d+|\d+日|\d+-\d+-\d+|\d+仗|\d+場')
    anchored_dims = 0
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            reasoning = str(dim_data.get('reasoning', ''))
            if data_anchor_pattern.search(reasoning):
                anchored_dims += 1
    if anchored_dims < 4:
        errors.append(f"WALL-020: 矩陣 reasoning 欠缺具體數據錨點 (只有 {anchored_dims}/7 個維度引用了數字/日期/百分比)。"
                      f" 每個 reasoning 必須引用至少一個具體數據 (例如: L400 時間、勝率百分比、近績名次)。")
    
    # WALL-020B: Fluff detection in matrix reasoning (not just core_logic)
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            reasoning = str(dim_data.get('reasoning', ''))
            for phrase in FLUFF_PHRASES:
                if phrase in reasoning:
                    errors.append(f"WALL-020B: matrix.{dim_name}.reasoning 含有懶惰模板語句「{phrase}」。請替換為引用具體數據嘅分析。")
                    break

    # WALL-026: Race shape must stay limited to draw, position, and traffic evidence.
    normalized_for_shape = _normalize_matrix(matrix)
    race_shape = normalized_for_shape.get('race_shape', {}) if isinstance(normalized_for_shape, dict) else {}
    race_shape_reasoning = str(race_shape.get('reasoning', '')) if isinstance(race_shape, dict) else ''
    verdict_match = re.search(r'→\s*\[判讀[：:]\s*(.+?)\]', race_shape_reasoning)
    verdict_text = verdict_match.group(1) if verdict_match else ''
    pace_terms = ('步速', 'PACE_TYPE', '快步速', '慢步速', '龜速', '自殺式', 'predicted_pace')
    if any(term in verdict_text for term in pace_terms):
        errors.append(
            "WALL-026: matrix.race_shape.reasoning 以 race-level speed_map 作主要判讀。"
            "形勢與走位只可用檔位數據、今日預計走位、近仗走位消耗/受阻作評分理由。"
        )

    # WALL-025: Debut template lock — prevent normal-race scoring from leaking in.
    is_debut_runner = (
        h_entry.get('debut_runner', False)
        or h_entry.get('is_debut', False)
        or str(h_entry.get('career_tag', '')).upper() == 'DEBUT'
    )
    if is_debut_runner:
        normalized_matrix = _normalize_matrix(matrix)
        stability = normalized_matrix.get('stability', {}) if isinstance(normalized_matrix, dict) else {}
        sectional = normalized_matrix.get('sectional', {}) if isinstance(normalized_matrix, dict) else {}
        trainer_signal = normalized_matrix.get('trainer_signal', {}) if isinstance(normalized_matrix, dict) else {}
        form_line = normalized_matrix.get('form_line', {}) if isinstance(normalized_matrix, dict) else {}
        stability_score = stability.get('score', '') if isinstance(stability, dict) else str(stability)
        sectional_score = sectional.get('score', '') if isinstance(sectional, dict) else str(sectional)
        trainer_reasoning = str(trainer_signal.get('reasoning', '')) if isinstance(trainer_signal, dict) else ''
        form_line_score = form_line.get('score', '') if isinstance(form_line, dict) else str(form_line)
        if not all(k in h_entry for k in ('debut_sire_profile', 'debut_trial_profile', 'debut_readiness_flags')):
            errors.append(
                "WALL-025: 初出馬 Logic JSON 缺少 debut_sire_profile / debut_trial_profile / debut_readiness_flags；"
                "請重新由最新 create_hkjc_logic_skeleton.py 生成 WorkCard/template。"
            )
        if '✅' in stability_score or '❌' in stability_score:
            stability_reasoning = str(stability.get('reasoning', '')) if isinstance(stability, dict) else ''
            prep_terms = (
                '備戰', '晨操', '操練', '試閘', 'trial', 'Trial', 'readiness',
                '體重', '健康', '加壓', '連貫', '中斷', '游水', '水中步行機'
            )
            if not any(term in stability_reasoning for term in prep_terms):
                errors.append(
                    "WALL-025: 初出馬 matrix.stability 可按備戰穩定性評分，但 ✅/❌ 必須引用 "
                    "操練連貫、試閘次數、readiness、體重/健康或中斷/反覆等 evidence；"
                    "不可用正式賽績穩定性模板。"
                )
            if '❌' in stability_score and any(term in stability_reasoning for term in ('無正式賽績', '無往績', '0仗', '零仗')):
                errors.append(
                    "WALL-025: 初出馬不可因『無正式賽績/無往績』本身將 stability 判 ❌；"
                    "若判 ❌，必須來自備戰中斷、trial反覆、健康或體重風險。"
                )
        if '✅' in form_line_score or '❌' in form_line_score:
            errors.append(
                "WALL-025: 初出馬無正式賽績線，matrix.form_line 不可打 ✅；"
                "亦不可當 ❌；必須為 N/A / 不計入。"
            )
        if '✅' in sectional_score:
            sectional_reasoning = str(sectional.get('reasoning', '')) if isinstance(sectional, dict) else ''
            has_sire = any(term in sectional_reasoning for term in ('Sire', 'sire', '父', '父系', '血統', 'AWD', '早熟'))
            has_trial = any(term in sectional_reasoning for term in ('試閘', 'trial', 'Trial', '晨操', 'readiness', '末段', '催策'))
            if not (has_sire and has_trial):
                errors.append(
                    "WALL-025: 初出馬 matrix.sectional 打 ✅/✅✅ 時，必須同時引用 Sire/血統距離證據 "
                    "及 trial/trackwork readiness 證據；不可沿用正式賽 L400 模板。"
                )
        final_rating = str(h_entry.get('final_rating', '')).strip()
        if final_rating and final_rating not in ('[AUTO]', 'AUTO', '[待計算]'):
            if grade_sort_index(final_rating) < grade_sort_index('A'):
                errors.append("WALL-025: 初出馬 final_rating 不可高於 A；A+/S-tier 必須封頂為 A。")
        readiness_flags = h_entry.get('debut_readiness_flags', []) or []
        trial_profile = h_entry.get('debut_trial_profile', {}) if isinstance(h_entry.get('debut_trial_profile', {}), dict) else {}
        try:
            readiness_score = int(trial_profile.get('readiness_score') or 0)
        except (TypeError, ValueError):
            readiness_score = 0
        strong_debut_work = readiness_score >= 70 or bool(readiness_flags) or int(trial_profile.get('trials_21d') or 0) >= 2
        if strong_debut_work and '待正式賽績驗證' in trainer_reasoning:
            errors.append(
                "WALL-025: 初出馬已有操練加壓/試閘/readiness 強訊號，trainer_signal 不可只寫「待正式賽績驗證」；"
                "應正面評估騎練部署是否可給 ✅。"
            )
        if '[FILL' not in core_logic and not any(term in core_logic for term in ('初出', '首出', '無往績', 'Career=0')):
            errors.append(
                "WALL-025: 初出馬 core_logic 必須明確使用初出馬格式，"
                "交代無正式賽績、試閘/晨操/騎練證據與評級封頂。"
            )

    # WALL-013B: Anti-double-counting warning (warning only, mirrors AU V4.2)
    # V4.2 merges gear/distance/health evidence into the 7D matrix. If the same
    # factor is also used as fine_tune, warn the analyst without blocking.
    double_count_map = {
        'GEAR_POSITIVE': 'trainer_signal',
        'GEAR_RESET': 'trainer_signal',
        'JOCKEY_FIT': 'trainer_signal',
        'TRAINER_INTENT': 'trainer_signal',
        'WEIGHT_SYNERGY': 'class_advantage',
        'WEIGHT_EXTREME': 'class_advantage',
        'MID_CLASS_LIGHT': 'class_advantage',
        'PACE_FIT': 'sectional',
        'PACE_AGAINST': 'sectional',
        'FATAL_DRAW': 'race_shape',
        'DISTANCE_JUMP': 'sectional',
        'DISTANCE_SPECIALIST': 'sectional',
        'SIRE_DISTANCE': 'sectional',
        'HEALTH_FRESHNESS': 'horse_health',
        'TRACK_SWITCH': 'horse_health',
    }
    ft = h_entry.get('fine_tune', {})
    if isinstance(ft, dict):
        ft_tokens = [
            str(ft.get('trigger_code', '')),
            str(ft.get('trigger', '')),
            str(ft.get('channel_a', '')),
            str(ft.get('channel_b', '')),
        ]
        normalized_matrix = _normalize_matrix(matrix)
        for ft_code, mapped_dim in double_count_map.items():
            if not any(ft_code and ft_code in token for token in ft_tokens):
                continue
            dim_data = normalized_matrix.get(mapped_dim, {}) if isinstance(normalized_matrix, dict) else {}
            dim_score = dim_data.get('score', '➖') if isinstance(dim_data, dict) else str(dim_data)
            if '✅' in dim_score:
                print(
                    f"   ⚠️ WALL-013B 雙重計算警告: fine_tune='{ft_code}' "
                    f"對應嘅矩陣維度「{mapped_dim}」已經係 {dim_score}。"
                    f"請確認微調理由唔係重複計算已有嘅 ✅。"
                )
    
    # WALL-014: Factual anchor — core_logic must mention the horse name
    horse_name = h_entry.get('horse_name', '')
    if horse_name and len(horse_name) > 1:
        # Check for horse name in core_logic (allow partial match for Chinese names)
        name_parts = [horse_name]
        if len(horse_name) >= 4:
            name_parts.append(horse_name[:4])  # First 4 chars of name
        if not any(part in core_logic for part in name_parts):
            errors.append(f"WALL-014: core_logic 未提及馬名「{horse_name}」。"
                          f" 分析必須針對呢匹馬，唔係通用模板。")
    
    # WALL-017: Dummy phrase detection — catch known auto_fill script outputs
    for phrase in DUMMY_PHRASES:
        if phrase in core_logic:
            errors.append(f"WALL-017: core_logic 含有已知 bypass 腳本特徵碼「{phrase}」。"
                          f" 請刪除 auto_fill 腳本，用 LLM 做真正分析。")
            break
    # Also check matrix reasoning for dummy phrases
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            reasoning = str(dim_data.get('reasoning', ''))
            for phrase in DUMMY_PHRASES:
                if phrase in reasoning:
                    errors.append(f"WALL-017: matrix.{dim_name}.reasoning 含有 bypass 特徵碼「{phrase}」")
                    break
    
    # WALL-015: Cross-horse core_logic similarity (V11)
    # Checks this horse's core_logic against all other completed horses
    for other_h, other_entry in horses_dict.items():
        if str(other_h) == str(h):
            continue
        other_cl = str(other_entry.get('core_logic', ''))
        if not other_cl or '[FILL]' in other_cl or len(other_cl) < 40:
            continue
        if len(core_logic) >= 40 and '[FILL]' not in core_logic:
            sim = SequenceMatcher(None, core_logic, other_cl).ratio()
            if sim > 0.60:
                errors.append(
                    f"WALL-015: core_logic 同馬號 {other_h} 相似度 {sim:.0%}。"
                    f" 每匹馬嘅分析必須獨立、獨特。"
                )
                break  # Only report first similarity hit

    # WALL-016: core_logic must contain concrete data anchors (V11)
    if core_logic and '[FILL]' not in core_logic and len(core_logic) >= 40:
        data_count = len(data_anchor_pattern.findall(core_logic))
        if data_count < 2:
            errors.append(
                f"WALL-016: core_logic 只有 {data_count} 個數據錨點 (至少需要 2 個)。"
                f" 必須引用具體數字 (如 L400=22.5秒、近6仗=2-1-3-4-2-1)。"
            )

    # WALL-021: advantages/disadvantages substance check
    _reject_placeholders = {'[無]', '[FILL]', '無', '暫無', '暫無明顯優勢', '暫無明顯風險',
                            '風險不大', '優勢不明顯', 'N/A', 'n/a', '-', '—'}
    for field_name in ('advantages', 'disadvantages'):
        field_val = str(h_entry.get(field_name, '[FILL]')).strip()
        field_chi = len(re.findall(r'[\u4e00-\u9fff]', field_val))
        if field_val in _reject_placeholders or field_chi < 10:
            label = '最大競爭優勢' if field_name == 'advantages' else '最大失敗風險'
            errors.append(
                f"WALL-021: {field_name} ({label}) 過短或為佔位符 ('{field_val[:30]}', {field_chi}字)。"
                f" 請列出 2-3 個具體要點，每點 ≥10 字並引用數據。"
            )

    # WALL-022: V4.2 Matrix reasoning substance — each filled dimension must have ≥20 chars reasoning
    matrix = h_entry.get('matrix', {})
    shallow_dims = []
    for dim_key, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            score = dim_data.get('score', '')
            reasoning = str(dim_data.get('reasoning', ''))
            if score in valid_scores and len(reasoning) < 20:
                shallow_dims.append(dim_key)
    if shallow_dims:
        errors.append(
            f"WALL-022: 矩陣 reasoning 過淺 ({len(shallow_dims)} 個維度 <20字)。"
            f" 每個維度必須引用具體數據。淺層: {', '.join(shallow_dims)}"
        )

    # STAB-TW soft-to-action checks: trackwork should be digested when available.
    trackwork = h_entry.get('trackwork', {})
    if isinstance(trackwork, dict):
        digest = trackwork.get('stability_digest', {})
        if isinstance(digest, dict) and digest.get('data_status') == 'ok':
            category = digest.get('career_category')
            stability = matrix.get('stability', {}) if isinstance(matrix, dict) else {}
            trainer_signal = matrix.get('trainer_signal', {}) if isinstance(matrix, dict) else {}
            stability_reasoning = str(stability.get('reasoning', '')) if isinstance(stability, dict) else ''
            trainer_reasoning = str(trainer_signal.get('reasoning', '')) if isinstance(trainer_signal, dict) else ''
            combined_text = f"{stability_reasoning}\n{trainer_reasoning}\n{core_logic}"
            flags = digest.get('stability_positive_flags', []) or []
            risk_flags = digest.get('stability_risk_flags', []) or []
            pattern_score = digest.get('pattern_replay_score')
            readiness = digest.get('readiness_score')
            try:
                pattern_score_num = int(pattern_score) if pattern_score is not None else 0
            except (TypeError, ValueError):
                pattern_score_num = 0
            try:
                readiness_num = int(readiness) if readiness is not None else 0
            except (TypeError, ValueError):
                readiness_num = 0

            if category == 'status_continuity':
                if 'maintenance' not in combined_text and '體能維持' not in combined_text and not any(flag in combined_text for flag in flags):
                    errors.append("STAB-TW-001: 晨操 status_continuity 已有 digest，但 stability/core_logic 未引用 maintenance_score 或晨操 flags。請用 50/50 方式合併賽績與晨操。")
            if category == 'pattern_replay' and pattern_score_num >= 70:
                if '復刻' not in combined_text and 'pattern_replay' not in combined_text:
                    errors.append("STAB-TW-002: 近績差伏兵型晨操 pattern_replay_score >=70，但 reasoning 未引用晨操翻案訊號。不可單憑近績死扣。")
            if category == 'debut_pressure':
                st_score = stability.get('score', '') if isinstance(stability, dict) else ''
                if ('✅' in st_score or '❌' in st_score) and not any(term in stability_reasoning for term in ('晨操', '操練', '試閘', 'readiness', '備戰', '體重', '健康', '中斷')):
                    errors.append("STAB-TW-003: 初出馬 stability 若非 ➖，必須引用備戰穩定性 evidence；不可沿用正式賽績穩定性模板。")
                if readiness_num >= 80 and '賽日騎師有參與操練' in flags:
                    if '騎師' not in trainer_reasoning and '賽日騎師' not in trainer_reasoning:
                        errors.append("TRAINER-TW-001: 初出馬 readiness>=80 且有賽日騎師參與，但 trainer_signal.reasoning 未引用騎師親操 / 加壓曲線。")
            if '操練中斷' in risk_flags:
                st_score = stability.get('score', '') if isinstance(stability, dict) else ''
                if '✅' in st_score and '操練中斷' not in stability_reasoning:
                    errors.append("STAB-TW-004: stability 已判 ✅，但晨操有操練中斷；請解釋負面風險點樣被抵消。")

    return errors


# ═══════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════

def main():
    """HKJC Wong Choi Orchestrator — LangGraph Pipeline.
    
    All orchestration logic is now handled by the LangGraph StateGraph.
    Business logic functions (firewalls, validation, QA) remain in this file
    and are imported by racing_graph_nodes.py via the domain function registry.
    
    Legacy state machine removed — recoverable via git if needed.
    """
    parser = argparse.ArgumentParser(description="HKJC Wong Choi Racing Orchestrator (LangGraph)")
    parser.add_argument("url", help="HKJC Race URL or target directory path")
    parser.add_argument("--auto", action="store_true", help="Auto mode (preserved for compatibility)")
    parser.add_argument("--autopilot", action="store_true",
                        help="Enable LangGraph autopilot mode (alias for --auto)")
    parser.add_argument("--allow-missing-trackwork", action="store_true",
                        help="Allow analysis to continue if HKJC trackwork extraction is missing or failed")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    # ── Resolve target directory ──
    target_dir = None
    url = None

    if args.url.startswith("http"):
        url = args.url
        venue, formatted_date, resolved_url = parse_url_for_details(url)
        url = resolved_url
        target_dir = get_target_dir(venue, formatted_date)
        if not target_dir:
            target_dir = get_target_dir(venue, formatted_date, auto_create=True)
            if target_dir:
                trigger_extractor(url, target_dir)
    else:
        target_dir = os.path.abspath(args.url)
        if not os.path.isdir(target_dir):
            print(f"❌ Not a valid directory: {target_dir}")
            sys.exit(1)

    if not target_dir or not os.path.isdir(target_dir):
        print("❌ Cannot resolve target directory")
        sys.exit(1)

    # ── Preflight Security Check ──
    run_preflight_check(target_dir)

    # ── Delegate to LangGraph ──
    _lg_scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', '..', '..', '..', 'scripts')
    sys.path.insert(0, os.path.abspath(_lg_scripts))
    from racing_graph_core import run_hkjc_langgraph

    run_hkjc_langgraph(
        target_dir,
        url,
        autopilot=args.auto or args.autopilot,
        allow_missing_trackwork=args.allow_missing_trackwork,
    )


if __name__ == "__main__":
    main()
