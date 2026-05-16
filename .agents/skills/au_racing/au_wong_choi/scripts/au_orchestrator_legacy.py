#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import argparse
import sys
import subprocess
import re
import json
import math
import time
import hashlib
import shutil

# Import rating engine for auto-verdict computation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts')))
from rating_engine_v2 import parse_matrix_scores, compute_base_grade, apply_fine_tune, grade_sort_index, apply_s_grade_guards
from racing_content_guard import scan_json_for_dummy, scan_text_for_dummy, quarantine_file
from validate_au_matrix_confidence import validate_au_matrix_confidence

AU_MATRIX_SCHEMA = {
    "stability": "core", "sectional": "core",
    "race_shape": "semi", "jockey_trainer": "semi",
    "class_weight": "aux", "track": "aux",
    "form_line": "aux",
}

AU_MATRIX_EXPECTED_KEYS = set(AU_MATRIX_SCHEMA)


def validate_au_race_ready_for_verdict(logic_data):
    horses = logic_data.get('horses', {})
    if not horses:
        raise ValueError("Verdict blocked: 'horses' key is empty or missing")
    errors = []
    for h_num, h_obj in horses.items():
        prefix = f"Horse {h_num} ({h_obj.get('horse_name', '?')})"
        matrix = _au_normalize_matrix(h_obj.get('matrix', {}))
        if not matrix:
            errors.append(f"{prefix}: matrix missing (final_rating-only horse not allowed)")
            continue
        missing = AU_MATRIX_EXPECTED_KEYS - set(matrix.keys())
        if missing:
            errors.append(f"{prefix}: missing matrix dimensions {sorted(missing)}")
        for de in scan_json_for_dummy(h_obj, allow_pending_fill=False, path=f"horses.{h_num}"):
            errors.append(f"{prefix}: {de}")
        for ve in validate_au_matrix_confidence(h_obj):
            errors.append(f"{prefix}: {ve}")
        core_logic = h_obj.get('core_logic', '')
        if not core_logic or core_logic.strip() in ('[FILL]', '', '待補充'):
            errors.append(f"{prefix}: core_logic is empty or placeholder")
    if errors:
        raise ValueError("Verdict generation blocked — race not ready:\n" + "\n".join(f"  - {e}" for e in errors))
AU_MATRIX_RESOURCE_REQUIREMENTS = {
    "stability": ("02b_form_analysis.md",),
    "sectional": ("02b_form_analysis.md", "02f_synthesis.md"),
    "race_shape": ("02d_pace_notes.md", "02a_pre_analysis.md"),
    "jockey_trainer": ("02e_jockey_trainer.md", "02c_track_and_gear.md"),
    "class_weight": ("02b_form_analysis.md",),
    "track": ("02c_track_and_gear.md",),
    "form_line": ("02b_form_analysis.md", "Facts.md"),
}
AU_MATRIX_LEGACY_8D_KEYS = {
    "裝備與距離", "Gear & Distance", "gear_distance", "gear_dist",
    "gearDistance", "gear_and_distance",
}
AU_LEGACY_TOP_LEVEL_FIELDS = {
    "analytical_breakdown", "sectional_forensic", "race_shape",
}

# AU Chinese/variant → canonical English key normalization
_AU_MATRIX_MAP = {
    "狀態與穩定性": "stability", "位置穩定性": "stability",
    "段速與引擎": "sectional", "段速質量": "sectional",
    "形勢與走位": "race_shape",
    "騎練訊號": "jockey_trainer", "練馬師訊號": "jockey_trainer",
    "級數與負重": "class_weight", "級數優勢": "class_weight",
    "場地適性": "track", "新鮮度/場地": "track",
    "賽績線": "form_line",
}

def _au_normalize_matrix(m_data):
    if not m_data:
        return m_data
    needs = any(k in _AU_MATRIX_MAP for k in m_data)
    if not needs:
        return m_data
    return {_AU_MATRIX_MAP.get(k, k): v for k, v in m_data.items()}


def validate_matrix_resource_checks_au(matrix: dict) -> list:
    """Ensure each AU matrix dimension cites the analyst resource it used."""
    errors = []
    normalized = _au_normalize_matrix(matrix) or {}
    for dim, required_files in AU_MATRIX_RESOURCE_REQUIREMENTS.items():
        dim_data = normalized.get(dim, {})
        if not isinstance(dim_data, dict):
            continue
        reasoning = str(dim_data.get('reasoning', ''))
        if '[FILL' in reasoning:
            continue
        if 'Resource Check:' not in reasoning and '資源檢查' not in reasoning:
            errors.append(
                f"WALL-024: matrix.{dim}.reasoning 缺少 [Resource Check: ...]。"
                "評級矩陣必須明示已讀對應 AU analyst resource。"
            )
            continue
        missing = [fname for fname in required_files if fname not in reasoning]
        if missing:
            errors.append(
                f"WALL-024: matrix.{dim}.reasoning Resource Check 缺少 {missing}。"
                "請按 WorkCard 對應維度必讀資源補回。"
            )
    return errors


def _auto_derive_trial_illusion_au(h_obj: dict) -> bool:
    if h_obj.get('trial_illusion', False):
        return True
    cl = h_obj.get('pre_analysis_checklist', {})
    if cl.get('primary_evidence_source') == 'trial_only':
        return True
    if cl.get('grade_without_trial') == 'no_data':
        return True
    return False


def _is_debut_runner_au(h_obj: dict) -> bool:
    """Career=0 official starts. Uses skeleton-derived fields first."""
    if h_obj.get('debut_runner', False):
        return True
    if str(h_obj.get('career_tag', '')).upper() == 'DEBUT':
        return True
    try:
        return int(h_obj.get('career_race_starts', 999)) == 0
    except (TypeError, ValueError):
        return False


def _apply_scenario_caps_au(grade: str, h_obj: dict) -> str:
    """Mirror compile_analysis_template.py scenario caps for auto verdict."""
    gi = grade_sort_index
    if _is_debut_runner_au(h_obj) and gi(grade) < gi('A-'):
        grade = 'A-'
    if h_obj.get('is_2yo', False) and gi(grade) < gi('A-'):
        grade = 'A-'
    if h_obj.get('distance_wall', False) and gi(grade) < gi('A-'):
        grade = 'A-'
    if h_obj.get('long_spell', False) and gi(grade) < gi('A-'):
        grade = 'A-'
    if _auto_derive_trial_illusion_au(h_obj) and gi(grade) < gi('B+'):
        grade = 'B+'
    wet_tier = h_obj.get('wet_track_tier', 0)
    if wet_tier == 4 and gi(grade) < gi('A-'):
        grade = 'A-'
    elif wet_tier == 5 and gi(grade) < gi('B+'):
        grade = 'B+'
    return grade


def _apply_v42_s_promotion_au(grade: str, m_data: dict) -> str:
    """Promote A+ to S-tier only via V4.2 ✅✅ conviction evidence."""
    if grade != 'A+':
        return grade
    core_dbl, semi_dbl = _au_count_core_semi_double(m_data)
    promo_steps = min(core_dbl, 2) + (1 if semi_dbl >= 2 else 0)
    if promo_steps >= 3:
        return 'S+'
    if promo_steps == 2:
        return 'S'
    if promo_steps == 1:
        return 'S-'
    return grade


def validate_v42_matrix_schema_au(h_entry: dict) -> list:
    """Reject old AU 8D matrix/skeleton output before grading or compile."""
    errors = []
    matrix = h_entry.get('matrix', {})
    if not isinstance(matrix, dict):
        return ["WALL-022: matrix 必須係 dict，請用 V4.2 7 維 skeleton 重新填寫。"]

    raw_keys = set(matrix)
    legacy_keys = sorted(raw_keys & AU_MATRIX_LEGACY_8D_KEYS)
    if legacy_keys:
        errors.append(
            "WALL-022: 偵測到舊 8 維矩陣欄位 "
            f"{legacy_keys}。V4.2 已取消獨立「裝備與距離」；"
            "距離併入 matrix.sectional，配備併入 matrix.jockey_trainer。"
        )

    normalized = _au_normalize_matrix(matrix)
    normalized_keys = set(normalized or {})
    duplicate_normalized = len(normalized_keys) != len(raw_keys)
    if duplicate_normalized:
        errors.append(
            "WALL-022: matrix 同時包含同義/新舊 key，normalize 後出現重複。"
            "請只保留 V4.2 canonical English keys。"
        )

    missing = sorted(AU_MATRIX_EXPECTED_KEYS - normalized_keys)
    unknown = sorted(normalized_keys - AU_MATRIX_EXPECTED_KEYS)
    if missing:
        errors.append(f"WALL-022: V4.2 7 維矩陣缺少 key: {missing}")
    if unknown:
        errors.append(f"WALL-022: V4.2 7 維矩陣出現未知 key: {unknown}")

    top_level_legacy = sorted(k for k in AU_LEGACY_TOP_LEVEL_FIELDS if k in h_entry)
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

def auto_compute_verdict(logic_data, facts_file):
    """Auto-compute verdict Top 4 from matrix grades. Eliminates LLM verdict stop."""
    validate_au_race_ready_for_verdict(logic_data)
    horses = logic_data.get('horses', {})
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    
    # Compute grade for each horse
    graded = []
    for h_num, h_obj in horses.items():
        m_data = _au_normalize_matrix(h_obj.get('matrix', {}))
        core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(m_data, AU_MATRIX_SCHEMA)
        b_grade = compute_base_grade(
            core_pass, semi_pass, aux_pass, core_fail, total_fail,
            matrix_dims=m_data, position_key="race_shape"
        )
        ft = h_obj.get('fine_tune', {})
        ft_dir = ft.get('direction', '無') if isinstance(ft, dict) else str(ft)
        f_grade = apply_fine_tune(b_grade, ft_dir)
        f_grade = _apply_scenario_caps_au(f_grade, h_obj)
        f_grade = _apply_v42_s_promotion_au(f_grade, m_data)
        f_grade, _ = apply_s_grade_guards(
            f_grade, h_obj, {}, {k: v.get('score', '➖') if isinstance(v, dict) else str(v) for k, v in m_data.items()}, {},
            sectional_key='sectional', class_key='class_weight',
            double_ticks=_count_matrix_double_ticks(m_data)
        )
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
    
    verdict = {
        'top4': [
            {'horse_number': str(h[0]), 'horse_name': h[1], 'grade': h[2]}
            for h in top4
        ],
        'confidence': confidence,
        'pace_flip_insurance': {
            'if_faster': {'benefit': faster_benefit or 'Top 4 中具末段優勢馬', 'hurt': faster_hurt or '前置高消耗馬'},
            'if_slower': {'benefit': slower_benefit or '前置/內檔馬', 'hurt': slower_hurt or '後上追勢馬'}
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


def _au_count_core_semi_double(matrix_data):
    """Count ✅✅ in core and semi-core dimensions for V4.2 promotion."""
    core_dbl = 0
    semi_dbl = 0
    for key, item in (matrix_data or {}).items():
        score = str(item.get('score', '') if isinstance(item, dict) else item)
        if '✅✅' not in score:
            continue
        dim_type = AU_MATRIX_SCHEMA.get(key, 'aux')
        if dim_type == 'core':
            core_dbl += 1
        elif dim_type == 'semi':
            semi_dbl += 1
    return core_dbl, semi_dbl


def verdict_needs_recompute_au(logic_data):
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


def load_qa_strikes_au(target_dir):
    strike_file = os.path.join(target_dir, '.qa_strikes.json')
    if not os.path.exists(strike_file):
        return {}
    try:
        with open(strike_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def qa_strike_count_au(strikes_data, race_num):
    return int(strikes_data.get(str(race_num), 0) or 0)


def has_open_qa_strike_au(strikes_data, race_num):
    return qa_strike_count_au(strikes_data, race_num) > 0


def validate_intelligence_package_au(path):
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
        'weather': ('weather', 'temperature', 'humidity', 'rain', 'wind', '天氣', '溫度', '濕度', '降雨', '風'),
        'track': ('track', 'going', 'rail', 'surface', '場地', '跑道', '欄位'),
        'bias': ('bias', 'pattern', 'leader', 'closer', '偏差', '前置', '後上'),
        'source': ('source', 'bom', 'bureau', 'racing', '來源', '資料來源'),
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


# ── Fix 2: .meeting_state.json Persistence ──

def build_meeting_state_au(target_dir, total_races, date_prefix):
    """Deep scan filesystem to build comprehensive state per-race (AU version)."""
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
    intel_ok, intel_issues = validate_intelligence_package_au(intel_file)
    state['intelligence_ready'] = intel_ok
    if intel_issues:
        state['intelligence_issues'] = intel_issues
    strikes_data = load_qa_strikes_au(target_dir)

    for r in range(1, total_races + 1):
        race_state = {
            'raw_data': False, 'facts': False, 'speed_map': False,
            'horses_total': 0, 'horses_done': 0, 'horses_pending': [],
            'batches_validated': 0, 'verdict': False, 'compiled': False,
            'mc_done': False, 'qa_passed': False, 'qa_strikes': 0,
            'stage': 'NOT_STARTED',
        }

        racecards = [f for f in os.listdir(target_dir) if f'Race {r}' in f and ('Racecard' in f or '排位表' in f)]
        race_state['raw_data'] = len(racecards) > 0

        facts_files = [f for f in os.listdir(target_dir) if re.search(rf'Race {r} Facts\.md', f)]
        if facts_files:
            race_state['facts'] = True
            try:
                with open(os.path.join(target_dir, facts_files[0]), 'r', encoding='utf-8') as f:
                    fc = f.read()
                horse_nums = re.findall(r'### (?:馬號|Horse) (\d+)', fc)
                if not horse_nums:
                    horse_nums = re.findall(r'### (\d+)[  —–-]', fc)
                race_state['horses_total'] = len(horse_nums)
            except Exception:
                pass

        logic_json = os.path.join(target_dir, f'Race_{r}_Logic.json')
        if os.path.exists(logic_json):
            try:
                with open(logic_json, 'r', encoding='utf-8') as f:
                    ld = json.load(f)
                sm = ld.get('race_analysis', {}).get('speed_map', {})
                sm_str = json.dumps(sm, ensure_ascii=False)
                if sm.get('predicted_pace') and '[FILL]' not in sm_str:
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

        an_file = os.path.join(target_dir, f'{date_prefix} Race {r} Analysis.md')
        if os.path.exists(an_file):
            try:
                with open(an_file, 'r', encoding='utf-8') as f:
                    ac = f.read()
                dummy_errs = scan_text_for_dummy(ac)
                if dummy_errs:
                    quarantine_file(an_file, f"build_meeting_state_au dummy scan (Race {r}):\n" + "\n".join(dummy_errs))
                    race_state['compiled'] = False
                    race_state['stage'] = 'REPAIR_NEEDED'
                elif '[FILL]' not in ac and 'FILL:' not in ac:
                    race_state['compiled'] = True
            except Exception:
                pass

        mc_file = os.path.join(target_dir, f'Race_{r}_MC_Results.json')
        race_state['mc_done'] = os.path.exists(mc_file)

        race_state['qa_strikes'] = qa_strike_count_au(strikes_data, r)

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

    state['next_action'] = determine_next_action_au(state)
    return state


def save_meeting_state_au(state_path, state):
    state['_last_updated'] = datetime.now().isoformat()
    state['next_action'] = determine_next_action_au(state)
    tmp_path = state_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, state_path)


def load_meeting_state_au(state_path):
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


def determine_next_action_au(state):
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
            return {'action': 'ANALYSE_HORSES', 'race': int(r_str),
                    'pending': rs.get('horses_pending', []),
                    'done': rs.get('horses_done', 0), 'total': rs.get('horses_total', 0)}
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


def print_meeting_dashboard_au(state):
    print(f"\n{'═' * 70}")
    print(f"📊 AU MEETING DASHBOARD — {state.get('total_races', '?')} 場賽事")
    print(f"{'═' * 70}")
    stage_icons = {
        'COMPLETE': '✅', 'AWAITING_MC': '🎲', 'QA_REPAIR': '🛠️', 'QA_BLOCKED': '🛑', 'AWAITING_COMPILE': '📝',
        'AWAITING_VERDICT': '⚖️', 'ANALYSING': '🔬', 'AWAITING_SPEED_MAP': '📍',
        'AWAITING_FACTS': '📋', 'AWAITING_RAW_DATA': '📥', 'NOT_STARTED': '⬜',
    }
    for r_str, rs in state.get('races', {}).items():
        icon = stage_icons.get(rs['stage'], '❓')
        horses_info = f"{rs['horses_done']}/{rs['horses_total']}" if rs['horses_total'] else '?'
        strikes = f" ⚠️x{rs['qa_strikes']}" if rs['qa_strikes'] > 0 else ""
        print(f"  Race {r_str:>2}: {icon} {rs['stage']:<22} | Horses: {horses_info:>5}{strikes}")
    na = state.get('next_action', {})
    print(f"{'─' * 70}")
    print(f"  📋 Next: {na.get('action', '?')}", end='')
    if na.get('race'):
        print(f" → Race {na['race']}", end='')
    if na.get('pending'):
        print(f" (pending: {na['pending']})", end='')
    print()
    print(f"{'═' * 70}\n")


# ── Fix 7: QA Diagnosis (AU) ──

def generate_qa_diagnosis_au(race_num, strike_num, qa_stdout, qa_stderr,
                              logic_json_path, analysis_path, runtime_dir):
    """Parse QA errors, classify root causes, generate diagnosis report (AU)."""
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

    affected_horses = []
    try:
        with open(logic_json_path, 'r', encoding='utf-8') as f:
            logic_data = json.load(f)
        for h_num, h_entry in logic_data.get('horses', {}).items():
            issues = []
            cl = h_entry.get('core_logic', '')
            if len(cl) < 80:
                issues.append(f'core_logic too short ({len(cl)} chars)')
            if issues:
                affected_horses.append((h_num, h_entry.get('horse_name', ''), issues))
    except Exception:
        pass

    report = []
    report.append(f"# 🔍 QA Diagnosis — Race {race_num} (Strike {strike_num}/3)")
    report.append(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    report.append(f"## Errors: {len(errors)}")
    for cat_name, cat_label in [
        ('LAZINESS', '🚨 Laziness'), ('CONTENT', '📝 Content'),
        ('FORMAT', '📋 Format'), ('DATA', '📊 Data')
    ]:
        if categories[cat_name]:
            report.append(f"### {cat_label}")
            for err in categories[cat_name]:
                report.append(f"- ❌ {err}")
            report.append("")
    if affected_horses:
        report.append("## Affected Horses")
        for h_num, h_name, issues in affected_horses:
            report.append(f"- Horse #{h_num} ({h_name}): {', '.join(issues)}")
    report.append("")
    report.append(f"⚠️ **Strike {strike_num}/3. Third failure = full stop.**")

    os.makedirs(runtime_dir, exist_ok=True)
    diag_path = os.path.join(runtime_dir, f"QA_Diagnosis_Race_{race_num}_Strike_{strike_num}.md")
    with open(diag_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))
    return diag_path


# ── Fix 8: Pre-Race Dummy Content Scanner (AU) ──

def scan_race_content_quality_au(logic_json_path):
    """Pre-race Python-only scan for dummy/template content (AU version)."""
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
        for phrase in DUMMY_PHRASES_AU:
            if phrase in core_logic:
                horse_issues.append(f'Dummy phrase: 「{phrase}」')
                break
        fluff_count = sum(1 for p in FLUFF_PHRASES_AU if p in core_logic)
        if fluff_count >= 2:
            horse_issues.append(f'Fluff phrases x{fluff_count}')
        if core_logic and '[FILL]' not in core_logic and len(core_logic) < 40:
            horse_issues.append(f'core_logic too short ({len(core_logic)} chars)')
        if core_logic in ('正常', '分析中', '待分析', ''):
            horse_issues.append(f'core_logic is placeholder: 「{core_logic}」')
        if horse_issues:
            contaminated.append({'horse_num': h_num, 'horse_name': h_entry.get('horse_name', ''), 'issues': horse_issues})

    result['contaminated_horses'] = contaminated

    all_logics = [h.get('core_logic', '') for h in horses.values()
                  if h.get('core_logic') and '[FILL]' not in h.get('core_logic', '')]
    if len(all_logics) >= 3:
        unique_logics = set(all_logics)
        if len(unique_logics) <= 2:
            result['issues'].append(f'Only {len(unique_logics)} unique core_logic across {len(all_logics)} horses')
            result['action'] = 'PURGE_ALL'
        logic_pairs = list(combinations(enumerate(all_logics), 2))
        high_sim = sum(1 for (_, a), (_, b) in logic_pairs if SequenceMatcher(None, a, b).ratio() > 0.60)
        if logic_pairs and high_sim / len(logic_pairs) > 0.5:
            result['issues'].append(f'{high_sim}/{len(logic_pairs)} pairs similarity >60%')
            result['action'] = 'PURGE_ALL'

    if contaminated and result['action'] == 'CLEAN':
        result['action'] = 'PURGE_PARTIAL'
    return result


# ── Fix 10: Context Injection Gateway (AU) ──

def print_context_injection_au():
    print("=" * 60)
    print("📋 CONTEXT INJECTION — Mandatory Rules (Python Auto-Injected)")
    print("=" * 60)
    print()
    print("🔴 Rule 1: Python Lead")
    print("   Orchestrator controls all flow. LLM only fills Logic.json.")
    print("   DO NOT decide which race/horse to do next.")
    print()
    print("🔴 Rule 2: Per-Horse Analysis")
    print("   Read WorkCard → Analyse → Fill JSON for each horse.")
    print("   DO NOT create auto_fill / batch_fill .py scripts.")
    print()
    print("🔴 Rule 3: core_logic Quality")
    print("   Must be ≥80 chars, cite specific data (dates/positions/weights).")
    print("   DO NOT write generic phrases like '表現尚可'.")
    print()
    print("🔴 Rule 4: If You Run Out of Context")
    print("   STOP + notify user to start new Conversation.")
    print("   NEVER sacrifice quality to speed up progress.")
    print()
    print("📖 Full Rules: SETUP.md (L51-111)")
    print("📖 Engine Directives: engine_directives.md")
    print("=" * 60)


def print_race_context_au(race_num, total_horses, pending_horses):
    print(f"\n{'─' * 50}")
    print(f"🏇 Race {race_num} — {total_horses} horses")
    print(f"📋 Pending: {pending_horses}")
    print(f"⚠️ Each horse: Read WorkCard → Analyse → Fill JSON")
    print(f"⚠️ core_logic ≥80 chars + cite specific data")
    print(f"{'─' * 50}\n")


def ensure_context_files_loaded_au(target_dir):
    files_to_check = [
        ('.meeting_state.json', '📊 Meeting State', 'CRITICAL'),
        ('_Meeting_Intelligence_Package.md', '🧠 Intelligence Package', 'HIGH'),
    ]
    print("\n📂 Context Files Status:")
    for filename, label, priority in files_to_check:
        path = os.path.join(target_dir, filename)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"   ✅ {label}: {filename} ({size:,} bytes)")
        else:
            print(f"   ❌ {label}: {filename} missing [{priority}]")


# ── Fix 3: Per-Batch Cross-Horse QA (AU) ──

def validate_batch_cross_horse_au(batch_horses, horses_dict, logic_json_path):
    """Validate a batch of horses for cross-horse quality issues (AU version)."""
    errors = []
    batch_entries = []
    for h in batch_horses:
        entry = horses_dict.get(str(h), {})
        if entry:
            batch_entries.append((str(h), entry))
    if len(batch_entries) < 2:
        return errors
    logics = [(h, e.get('core_logic', '')) for h, e in batch_entries
              if e.get('core_logic') and '[FILL]' not in e.get('core_logic', '')]
    if len(logics) >= 2:
        for (h1, l1), (h2, l2) in combinations(logics, 2):
            sim = SequenceMatcher(None, l1, l2).ratio()
            if sim > 0.60:
                errors.append(f"BATCH-001: Horse {h1} ↔ {h2} core_logic similarity {sim:.0%}")
    for h, e in batch_entries:
        e_str = json.dumps({k: v for k, v in e.items() if k not in ('base_rating', 'final_rating')}, ensure_ascii=False)
        fill_count = e_str.count('[FILL]')
        if fill_count > 0:
            errors.append(f"BATCH-002: Horse {h} still has {fill_count} [FILL]")
    scores = []
    for h, e in batch_entries:
        m = e.get('matrix', {})
        h_scores = [d.get('score', '') for d in m.values() if isinstance(d, dict)]
        scores.append(tuple(h_scores))
    if len(scores) >= 2 and len(set(scores)) == 1:
        errors.append(f"BATCH-003: All {len(scores)} horses have identical matrix scores")
    return errors

def parse_url_for_details(url):
    match = re.search(r'form-guide/horse-racing/([^/]+)-(\d{8})/', url)
    if not match:
        raise ValueError("Invalid URL format. Cannot extract Venue and Date.")
    venue = match.group(1).replace('-', ' ').title()
    date_str = match.group(2)
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return venue, formatted_date

def get_target_dir(venue, formatted_date, auto_create=False):
    base_dir = "."
    # Collect ALL candidate directories matching date + venue
    all_candidates = []
    for d in os.listdir(base_dir):
        if not os.path.isdir(d):
            continue
        # Match underscore format: YYYY-MM-DD_Venue_Race_...
        if d.startswith(f"{formatted_date}_{venue}_Race_"):
            all_candidates.append(d)
        # Match space format: YYYY-MM-DD Venue ...
        elif d.startswith(f"{formatted_date} {venue}"):
            all_candidates.append(d)

    if all_candidates:
        # Prioritise directories that contain "Race" (extractor output with actual data)
        # over bare venue-only directories (empty shells from preflight/auto_create)
        with_race = [d for d in all_candidates if 'Race' in d]
        if with_race:
            with_race.sort()
            return os.path.abspath(os.path.join(base_dir, with_race[0]))
        # Fallback to bare directory
        all_candidates.sort()
        return os.path.abspath(os.path.join(base_dir, all_candidates[0]))

    if auto_create:
        new_dir = os.path.abspath(os.path.join(base_dir, f"{formatted_date} {venue}"))
        os.makedirs(new_dir, exist_ok=True)
        return new_dir
    return None

def trigger_extractor(url):
    print(f"🚀 [Orchestrator] 啟動 AU Race Extractor 提取全日數據...")
    script_path = ".agents/skills/au_racing/au_race_extractor/scripts/extractor.py"
    if not os.path.exists(script_path):
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        sys.exit(1)
    try:
        subprocess.run([PYTHON, script_path, url, "all"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] 數據提取腳本執行失敗: {e}")
        sys.exit(1)

def discover_total_races(target_dir):
    combined = [f for f in os.listdir(target_dir) if re.search(r'Race \d+-(\d+)', f)]
    if combined:
        m = re.search(r'Race \d+-(\d+)', combined[0])
        if m:
            return int(m.group(1))

    racecards = [f for f in os.listdir(target_dir) if "Racecard.md" in f]
    max_race = 0
    for card in racecards:
        m = re.search(r'Race_(\d+)', card) or re.search(r'Race (\d+)', card)
        if m:
            race_num = int(m.group(1))
            if race_num > max_race:
                max_race = race_num
    return max_race

def check_raw_data_completeness(target_dir, total_races):
    missing_data = []
    combined_rc = any(re.search(r'Race 1-\d+ Racecard\.md', f) for f in os.listdir(target_dir))
    combined_fg = any(re.search(r'Race 1-\d+ Formguide\.md', f) for f in os.listdir(target_dir))
    if not (combined_rc and combined_fg):
        for race_num in range(1, total_races + 1):
            if not any(re.search(rf'Race {race_num} Formguide\.md', f) for f in os.listdir(target_dir)):
                missing_data.append(f"Race {race_num} Formguide.md")
            if not any(re.search(rf'Race {race_num}.*Racecard\.md', f) for f in os.listdir(target_dir)):
                missing_data.append(f"Race {race_num} Racecard.md")
    return missing_data

def get_racecard_path(target_dir, race_num):
    for f in os.listdir(target_dir):
        if re.search(r'Race 1-\d+ Racecard\.md', f): return os.path.join(target_dir, f)
        if f"Race {race_num}" in f and "Racecard.md" in f: return os.path.join(target_dir, f)
    return None

def get_formguide_path(target_dir, race_num):
    for f in os.listdir(target_dir):
        if re.search(r'Race 1-\d+ Formguide\.md', f): return os.path.join(target_dir, f)
        if f"Race {race_num}" in f and "Formguide.md" in f: return os.path.join(target_dir, f)
    return None

def get_horse_numbers(facts_path):
    if not os.path.exists(facts_path): return []
    with open(facts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    horses = []
    # Identify horse blocks
    blocks = re.split(r'(?=\[#\d+\]|### 馬匹 #\d+|### 馬號 \d+)', content)
    for b in blocks:
        m = re.search(r'\[#(\d+)\]|馬匹 #(\d+)|馬號 (\d+)', b)
        if m: 
            val = m.group(1) or m.group(2) or m.group(3)
            horses.append(int(val))
    return sorted(list(set(horses)))


def _parse_num_list_from_speed_map_line(value):
    return [int(x) for x in re.findall(r'\d+', value or '')]


def parse_au_speed_map_from_facts(facts_content):
    """Parse the first-class Python-generated speed map block from AU Facts.md."""
    m = re.search(
        r'^###\s*🗺️\s*自動步速圖.*?(?=^(?:###\s+馬匹|\[#\d+\]|\n={6,})|\Z)',
        facts_content,
        re.MULTILINE | re.DOTALL
    )
    if not m:
        return {}
    block = m.group(0)

    def _field(name):
        fm = re.search(rf'-\s*\*\*{re.escape(name)}:\*\*\s*(.+?)$', block, re.MULTILINE)
        return fm.group(1).strip() if fm else ''

    pace_val = _field('predicted_pace') or _field('expected_pace')
    speed_map = {
        'predicted_pace': pace_val,
        'expected_pace': pace_val,   # backward-compatible alias
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


def auto_build_au_speed_map_from_facts(facts_content, target_dir=None):
    """Parse the Facts Engine speed map from AU Facts.md.

    If the Facts Engine embedded a speed map block (🗺️ 自動步速圖), parse and return it.
    If no speed map block exists, return [FILL] placeholders so the pipeline stops
    at Step B for manual intervention.

    NOTE: The previous fallback heuristic (full-text keyword search) was removed because
    it produced severely inflated leader counts and universal 'Chaotic' pace predictions.
    """
    generated = parse_au_speed_map_from_facts(facts_content)
    if generated:
        return generated

    # No Facts Engine speed map found — return placeholders instead of guessing
    print("⚠️ Facts Engine 步速圖缺失！Pipeline 將停喺 Step B 等待人手填寫 speed_map。")
    print("   → 請確認 Facts.md 包含 '### 🗺️ 自動步速圖' block，或人手填寫 Logic.json speed_map。")
    return {
        'predicted_pace': '[FILL]',
        'expected_pace': '[FILL]',
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

def get_batches(horses, batch_size=3):
    return [horses[i:i + batch_size] for i in range(0, len(horses), batch_size)]

def update_session_tasks(target_dir, total_races, missing_raw, chk_weather, facts_status, analysis_status, batch_details):
    out_path = os.path.join(target_dir, "_session_tasks.md")
    lines = ["# 🏆 AU Wong Choi Live Session Tasks\n"]
    lines.append(f"- {'[ ]' if missing_raw else '[x]'} 賽事資料下載 (Race 1-{total_races})")
    lines.append(f"- {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    
    for r in range(1, total_races + 1):
        fc = '[x]' if facts_status.get(r, False) else '[ ]'
        an = '[x]' if analysis_status.get(r, False) else '[ ]'
        lines.append(f"\n## Race {r}")
        lines.append(f"- {fc} 事實錨點生成 (Facts.md)")
        lines.append(f"- {an} 戰略邏輯與盤口對照 (Analysis.md)")
        if not analysis_status.get(r, False) and r in batch_details:
            bd = batch_details[r]
            from itertools import chain
            done_horses = bd.get('done', [])
            all_batches = bd.get('batches', [])
            for idx, batch_horses in enumerate(all_batches):
                is_batch_done = all(h in done_horses for h in batch_horses)
                bc = '[x]' if is_batch_done else '[ ]'
                lines.append(f"  - {bc} Batch {idx+1} (馬匹: {batch_horses})")
                
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def _next_cmd(target_dir):
    """Print machine-readable re-run command for LLM auto-execution."""
    dir_arg = os.path.abspath(os.path.normpath(target_dir))
    print(f"\nNEXT_CMD: {PYTHON} .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py \"{dir_arg}\" --auto")


# ═══════════════════════════════════════════════════════════════
# V10 Helper Functions: Firewall Validation + File-Watch Loop
# ═══════════════════════════════════════════════════════════════

def extract_horse_facts_block(target_horse, facts_content):
    """Extract a single horse's facts block from AU Facts.md."""
    for marker_pat in [rf'\[#{target_horse}\]', rf'### 馬號 {target_horse} — ', rf'### 馬匹 #{target_horse} ']:
        h_match = re.search(marker_pat, facts_content)
        if h_match:
            h_start = h_match.start()
            h_next = re.search(r'(?:\[#\d+\]|### 馬號 \d+ — |### 馬匹 #\d+)', facts_content[h_match.end():])
            h_end = h_match.end() + h_next.start() if h_next else len(facts_content)
            return facts_content[h_start:h_end]
    return ""


def extract_fact_anchors(horse_block):
    """Extract key factual data points from a horse's Facts block for work card generation."""
    anchors = {}

    # Horse name, barrier, jockey, trainer
    m = re.search(r'### 馬匹 #(\d+)\s+(.+?)\s+\(檔位\s*(\d+)\)\s*\|\s*騎師:\s*(.+?)\s*\|\s*練馬師:\s*(.+?)$',
                  horse_block, re.MULTILINE)
    if m:
        anchors['name'] = m.group(2).strip()
        anchors['barrier'] = m.group(3)
        anchors['jockey'] = m.group(4).strip()
        anchors['trainer'] = m.group(5).strip()
    else:
        anchors['name'] = '未知'
        anchors['barrier'] = '?'
        anchors['jockey'] = '?'
        anchors['trainer'] = '?'

    # Recent form sequence
    m = re.search(r'近績序列解讀:\s*`([^`]+)`', horse_block)
    anchors['recent_form'] = m.group(1) if m else '無'

    # Career starts (official races)
    m = re.search(r'生涯:\s*(\d+):', horse_block)
    anchors['career_starts'] = m.group(1) if m else '0'
    m = re.search(r'生涯標記:\s*`(DEBUT|EARLY_CAREER|IMPORTED_DEBUT|ESTABLISHED)`', horse_block)
    if m:
        anchors['career_tag'] = m.group(1)
    else:
        starts_for_tag = int(anchors['career_starts'])
        if starts_for_tag == 0:
            anchors['career_tag'] = 'DEBUT'
        elif starts_for_tag <= 5:
            anchors['career_tag'] = 'EARLY_CAREER'
        else:
            anchors['career_tag'] = 'ESTABLISHED'

    # Fitness arc derivation
    starts = int(anchors['career_starts'])
    if starts == 0:
        anchors['fitness_arc'] = '初出馬（零正式賽事經驗）'
    elif starts == 1:
        anchors['fitness_arc'] = '二出'
    elif starts == 2:
        anchors['fitness_arc'] = 'Third-up（第三仗）'
    elif starts <= 5:
        anchors['fitness_arc'] = f'生涯第{starts + 1}場（早期生涯；不可寫成休出）'
    else:
        anchors['fitness_arc'] = f'Deep Prep（{starts}仗）'

    # Race shape
    m = re.search(r'加權走位形勢:\s*([^→]+?)→', horse_block)
    anchors['''race_shape_assessment'''] = m.group(1).strip() if m else '無數據'

    # Last run style
    m = re.search(r'走位 跑法.*?\|\s*(.+?)\s*\|', horse_block)
    anchors['last_run_style'] = m.group(1).strip() if m else '無數據'

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

    # Distance record for today's distance
    m = re.search(r'今仗\s*\d+m.*?:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['distance_record'] = m.group(1).strip() if m else '無紀錄'

    # Best distance
    m = re.search(r'⭐最佳', horse_block)
    if m:
        dist_m = re.search(r'([\d≤]+m?).*?⭐最佳', horse_block)
        anchors['best_distance'] = dist_m.group(1) if dist_m else '未知'
    else:
        anchors['best_distance'] = '數據不足'

    # Engine type
    m = re.search(r'引擎:\s*(.+?)\s*\|', horse_block)
    anchors['engine_type'] = m.group(1).strip() if m else '未知'

    # PI trend
    m = re.search(r'PI.*?趨勢:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['pi_trend'] = m.group(1).strip() if m else '數據不足'

    # L400 trend
    m = re.search(r'L400.*?趨勢:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['l400_trend'] = m.group(1).strip() if m else '數據不足'

    # Class movement (from table)
    class_moves = re.findall(r'[↑↓].*?(?:升班|降班)', horse_block)
    anchors['class_move'] = class_moves[0] if class_moves else '無明顯升降'

    # Last run remark
    remarks = re.findall(r'\|\s*[^|]*(?:Led|Settled|Held|Keen|Pushed|Sat|Box seat)[^|]*\|', horse_block)
    anchors['last_run_remark'] = remarks[0].strip('| ') if remarks else '無'

    # Gear / equipment hint, if present in Facts block
    m = re.search(r'(?:配備|Gear)[：:]\s*([^\n|]+)', horse_block, re.IGNORECASE)
    anchors['gear'] = m.group(1).strip() if m else '無明確配備變動'

    return anchors


def generate_work_card(horse_num, facts_content, logic_data, runtime_dir,
                       sm_pace, sm_bias, horse_idx=0, total_horses=1):
    """Generate a guided analysis work card for a SINGLE horse.

    Instead of dumping raw data and expecting the LLM to figure out what to do,
    this creates structured analytical questions with the horse's actual data
    embedded, forcing the LLM to produce data-specific reasoning.
    """
    horse_block = extract_horse_facts_block(horse_num, facts_content)
    if not horse_block:
        return None

    anchors = extract_fact_anchors(horse_block)
    race_class = logic_data.get('race_analysis', {}).get('race_class', '?')
    distance = logic_data.get('race_analysis', {}).get('distance', '?')
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {}) or {}
    pace_confidence = speed_map.get('pace_confidence', 'Unknown')
    style_confidence = speed_map.get('style_confidence', 'Unknown')

    card = []
    card.append(f"# 🐎 分析工作卡 [{horse_idx+1}/{total_horses}] — Horse #{horse_num} {anchors['name']}")
    card.append(f"**檔位: {anchors['barrier']} | 騎師: {anchors['jockey']} | 練馬師: {anchors['trainer']}**")
    card.append(f"📍 步速: {sm_pace} | Pace信心: {pace_confidence} | 跑法信心: {style_confidence} | 偏差: {sm_bias} | 班次: {race_class} | 距離: {distance}")
    if anchors.get('career_tag') in ('DEBUT', 'EARLY_CAREER', 'IMPORTED_DEBUT'):
        career_note = {
            'DEBUT': '初出馬：必讀 `02h_debut_guide.md`，7 維照用但證據來源改為試閘/Sire/騎練部署；硬封頂 A-，trial-only 更嚴格封頂 B/B+。',
            'EARLY_CAREER': '早期生涯：參考 `02h_debut_guide.md` Section B；必須寫「生涯第 X 場」，不可寫休出/First-up。',
            'IMPORTED_DEBUT': '進口馬初出：參考 `02h_debut_guide.md` Section B + `02e_jockey_trainer.md` Imported Upside Buffer；不可因無本地賽績直接扣死。',
        }[anchors['career_tag']]
        card.append(f"> ⚠️ **[CAREER_TAG: {anchors['career_tag']}]** — {career_note}")
    card.append("")
    card.append("---")
    card.append("## 📖 必讀資源 (分析前必須讀取)")
    card.append("**每個維度判斷前，必須讀取對應嘅 analyst 規則檔案。唔可以單純憑數據自由發揮。**")
    card.append("")
    card.append("| 維度 | 必讀資源 | 關鍵規則 |")
    card.append("|:---|:---|:---|")
    card.append("| 1️⃣ 狀態與穩定性 | `au_horse_analyst/resources/02b_form_analysis.md` Step 1 | Bounce Factor / Third-up 黃金期 / Deep Prep ≥6 衰退 / 長休距離封頂 / 試閘降權 |")
    card.append("| 2️⃣ 段速與引擎 | `au_horse_analyst/resources/02b_form_analysis.md` Step 2 + `02f_synthesis.md` merge rules | Type A/B/C 引擎分類 / 距離轉換風險矩陣 / 距離全勝專精 SIP-RR15 / Sire 距離投影 |")
    card.append("| 3️⃣ 形勢與走位 | `au_horse_analyst/resources/02d_pace_notes.md` + `02a_pre_analysis.md` Step 0.2 | Pace Confidence / Leader Dominance / Course Geometry / Small Field / Scratchings |")
    card.append("| 4️⃣ 騎練訊號 | `au_horse_analyst/resources/02e_jockey_trainer.md` Step 11-12 + `02c_track_and_gear.md` Step 5 | 出擊訊號 (Waller 3rd-Up / Maher Quick Backup 等) / 配備意圖 / Momentum Factor / Brand Trap |")
    card.append("| 5️⃣ 級數與負重 | `au_horse_analyst/resources/02b_form_analysis.md` Step 3 | Effective Rating 計算 / 見習減磅 SIP-7 / 省賽轉都會折扣 / 升班輕磅協同 |")
    card.append("| 6️⃣ 場地適性 | `au_horse_analyst/resources/02c_track_and_gear.md` Step 4 | Track Family Confidence / Soft 分級排序 / 場地勝率門檻 / 州際轉場懲罰 |")
    card.append("| 7️⃣ 賽績線 | Facts.md 賽績線表格 | 強組/弱組 (由 Python 預生成) + 對手後續追蹤(近3場Top-3) |")
    card.append("| 📊 評級矩陣 | `au_horse_analyst/resources/02f_synthesis.md` | 查表法 + 微調 Channel A/B |")
    card.append("| 🔒 覆蓋規則 | `au_horse_analyst/resources/02g_override_chain.md` | P1 核心防護牆 / P2 卡士碾壓 / P3 鐵腳保底 |")
    card.append("| 🐴 寬恕檔案 | `au_horse_analyst/resources/02c_track_and_gear.md` Step 6 | Forgive Run / V 型反彈 / 寬恕班次過濾器 |")
    if anchors.get('career_tag') in ('DEBUT', 'EARLY_CAREER', 'IMPORTED_DEBUT'):
        card.append("| 🐣 初出/早期生涯 | `au_horse_analyst/resources/02h_debut_guide.md` | DEBUT 改用試閘/Sire/騎練部署判維度；EARLY_CAREER 禁止寫休出/First-up |")
    card.append("")
    card.append("---")
    card.append("## ⚠️ 指引")
    card.append("- 每個維度必須根據下方列出嘅**具體數據** + 上方對應嘅 **analyst 規則**作出判斷")
    card.append("- 分數只可以係 ✅✅ / ✅ / ➖ / ❌ / ❌❌")
    card.append("- 理據必須引用具體數據（日期、場地、名次、PI 數值等）")
    card.append("- **AU V4.3 Confidence Gate:** 每個維度先寫 Evidence Confidence / Pace Confidence / Track Family Confidence；Low/Unknown 不可打 ✅✅")
    card.append("- **V4.2 reasoning 格式:** 第一行必須保留 `[Resource Check: ...]`，中段保留 `[數據/規則]` evidence slots，最後只寫一次 `→ [判讀: ...]`；唔好將判讀原文複製多一次")
    card.append("- V4.2 無獨立「裝備與距離」維度：距離證據併入 `sectional`；配備意圖併入 `jockey_trainer`；同一因素不可再重複做 fine_tune")
    card.append("- 唔可以寫「一般」、「尚可」、「配搭無特別異常」等模板化語句")
    card.append("---")
    card.append("")
    card.append("## 📐 填寫順序（嚴格執行）")
    card.append("1. **填寫 7 個矩陣維度** (`matrix.*.score` + `matrix.*.reasoning`) — reasoning 必須保留 evidence slots + 最後一行 `→ [判讀: ...]`")
    card.append("2. **填寫** `forgiveness_archive`")
    card.append("3. **最後填** `core_logic`")
    card.append("⚠️ V4.2: 唔再有 `analytical_breakdown`、`sectional_forensic`、standalone `race_shape` — 所有分析直接寫入 matrix reasoning")
    card.append("- ❌ 禁止直接從 Facts 數據跳到矩陣評分，必須經過分析推導")
    card.append("---")
    card.append("")

    # ── Dimension 1: 狀態與穩定性 [核心] ──
    card.append("## 1️⃣ 狀態與穩定性 [核心維度]")
    card.append(f"- 生涯標記: **{anchors['career_tag']}**")
    card.append(f"- 正式賽事場次: **{anchors['career_starts']}**")
    card.append(f"- 近績序列: `{anchors['recent_form']}`")
    card.append(f"- 狀態週期: **{anchors['fitness_arc']}**")
    card.append(f"- 上仗備註: {anchors['last_run_remark']}")
    card.append("👉 **你嘅判斷:** 先標 Evidence Confidence，再判 ✅✅/✅/➖/❌/❌❌；trial-only/少正式賽不可當穩定。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.stability.reasoning`")
    card.append("")

    # ── Dimension 2: 段速與引擎 [核心] ──
    card.append("## 2️⃣ 段速與引擎 [核心維度]")
    card.append(f"- PI 趨勢: {anchors.get('pi_trend', '數據不足')}")
    card.append(f"- L400 趨勢: {anchors.get('l400_trend', '數據不足')}")
    card.append(f"- 引擎類型: {anchors.get('engine_type', '未知')}")
    card.append(f"- 同程紀錄: {anchors.get('distance_record', '無紀錄')}")
    card.append(f"- 最佳距離/Sire投影: {anchors.get('best_distance', '數據不足')}")
    card.append(f"- 今仗步速預測: {sm_pace}")
    card.append("👉 **你嘅判斷:** 先標 Evidence Confidence；段速質素如何？今日距離是否配合引擎？若距離未驗證/增程風險大,不可輕易判 ✅✅。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.sectional.reasoning`")
    card.append("")

    # ── Dimension 3: 形勢與走位 [半核心] ──
    card.append("## 3️⃣ 形勢與走位 [半核心]")
    card.append(f"- 走位形勢: {anchors.get('''race_shape_assessment''', '無數據')}")
    card.append(f"- 上仗跑法: {anchors.get('last_run_style', '無數據')}")
    card.append(f"- 今仗檔位: {anchors.get('barrier', '?')}")
    card.append(f"- 跑道偏差: {sm_bias}")
    card.append("👉 **你嘅判斷:** 先標 Pace Confidence (Clear/Mixed/Low)，再判步速/檔位/跑法/track geometry 是否明確有利或不利。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.race_shape.reasoning`")
    card.append("")

    # ── Dimension 4: 騎練訊號 [半核心] ──
    card.append("## 4️⃣ 騎練訊號 [半核心]")
    card.append(f"- 騎師: {anchors.get('jockey', '?')}")
    card.append(f"- 練馬師: {anchors.get('trainer', '?')}")
    card.append(f"- 配備/裝備提示: {anchors.get('gear', '無明確配備變動')}")
    card.append("👉 **你嘅判斷:** 先標 Evidence Confidence；有冇出擊訊號？配備變動是否針對已確認問題？冇獨立訊號就寫 ➖，名氣騎練不可自動 ✅。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.jockey_trainer.reasoning`")
    card.append("")

    # ── Dimension 5: 級數與負重 [輔助] ──
    card.append("## 5️⃣ 級數與負重 [輔助]")
    card.append(f"- 今仗班次: {race_class}")
    card.append(f"- 班次變動: {anchors.get('class_move', '無明顯升降')}")
    card.append("👉 **你嘅判斷:** 先做 AU class normalization (Metro/Provincial/Country, BM/Set Weight/WFA)，再判班次有冇優勢及負重壓力。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.class_weight.reasoning`")
    card.append("")

    # ── Dimension 6: 場地適性 [輔助] ──
    card.append("## 6️⃣ 場地適性 [輔助]")
    card.append(f"- 好地紀錄: {anchors.get('good_record', '無')}")
    card.append(f"- 軟地紀錄: {anchors.get('soft_record', '無')}")
    card.append(f"- 同場紀錄: {anchors.get('course_record', '無')}")
    card.append("👉 **你嘅判斷:** 先標 Track Family Confidence，逐層檢查 same venue / geometry / direction / surface / going / interstate，再判今日場地適性。")
    card.append("📎 **健康評估規則:** 有健康事故+復原證據(後續好表現)=已復原(➖/✅); 有事故+未復原=風險(❌); 無事故=正常(✅)")
    card.append("📎 **引用 skeleton reasoning** → `matrix.track.reasoning`")
    card.append("")

    # ── Dimension 7: 賽績線 [輔助] ──
    card.append("## 7️⃣ 賽績線 [輔助]")
    card.append(f"- 賽績線強度: {anchors.get('formline_strength', '無資料')}")
    card.append("👉 **你嘅判斷:** 先標 Evidence Confidence；只用對手後續同級/高級表現支持加分，N/A / trial-only 不硬塞分。")
    card.append("📎 **引用 skeleton reasoning** → `matrix.form_line.reasoning`")
    card.append("")


    # ── Final synthesis ──
    card.append("---")
    card.append("## 📋 綜合部分（填完 7 個維度後）")
    card.append("- **core_logic**: 串連所有維度寫成連貫分析（必須引用具體賽事/數據）")
    card.append("- ⚠️ **core_logic 嚴禁寫出任何評級判斷**（如「評為X級」「屬A等馬匹」「判定為B+」）。只寫分析推演過程。")
    card.append("- **advantages**: 2-3 個主要優勢")
    card.append("- **disadvantages**: 2-3 個致命風險")
    card.append("- **fine_tune**: 方向(+/-/無) + trigger_code（從預定義列表揀）")
    card.append("")
    card.append("---")
    card.append("## 📄 原始賽績數據（嚴禁修改）")
    card.append(horse_block)

    # Write to file
    card_path = os.path.join(runtime_dir, f"Horse_{horse_num}_WorkCard.md")
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(card))

    return card_path


def watch_single_horse(json_file, horse_num, validate_fn, all_horses,
                       poll_interval=0.5, timeout_minutes=60):
    """Watch for a SINGLE horse to be filled and validated.
    Returns the horse entry dict on success, None on timeout.
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

    # Pre-check: maybe already filled
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
    print(f"\n👀 Python 正在監控 Horse #{horse_num}... (每 {poll_interval:g} 秒 | 超時 {timeout_minutes} 分鐘)")

    try:
        while True:
            elapsed = time.time() - start_time
            if elapsed > timeout_minutes * 60:
                print(f"\n⏰ Horse #{horse_num} 監控超時 ({timeout_minutes} 分鐘)！")
                return None

            # Heartbeat every 60s
            if time.time() - last_heartbeat > 60:
                mins = int(elapsed / 60)
                print(f"   💓 [{mins}m] 仍在等待 Horse #{horse_num}...")
                last_heartbeat = time.time()

            try:
                current_mtime = os.path.getmtime(json_file)
            except OSError:
                time.sleep(poll_interval)
                continue

            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                time.sleep(poll_interval)
                continue

            time.sleep(debounce_seconds)  # Debounce
            last_mtime = current_mtime

            # Read JSON with retry
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

            # V12: Restore race_analysis from snapshot (prevent LLM tampering)
            if _race_analysis_snapshot:
                current_ra = logic_data.get('race_analysis', {})
                if current_ra != _race_analysis_snapshot:
                    print(f"   🔒 V12: race_analysis 被修改，自動恢復 Python 快照")
                    logic_data['race_analysis'] = _race_analysis_snapshot
                    with open(json_file, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    own_write_mtime = os.path.getmtime(json_file)
                    last_mtime = own_write_mtime

            # Validate
            errors = validate_fn(horse_num, h_entry, horses_dict, all_horses, json_file)
            if errors:
                name = h_entry.get('horse_name', '')
                print(f"\n🚨 Horse #{horse_num} ({name}) Firewall 失敗!")
                for e in errors:
                    print(f"   ❌ {e}")
                print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
                # Reset core_logic to force redo
                h_entry['core_logic'] = '[FILL]'
                with open(json_file, 'w', encoding='utf-8') as wf:
                    json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                own_write_mtime = os.path.getmtime(json_file)
                last_mtime = own_write_mtime
            else:
                return h_entry

    except KeyboardInterrupt:
        print(f"\n⚠️ 用戶中斷！Horse #{horse_num} 未完成。")
        return None


def print_analysis_summary(horse_entry, horse_num):
    """Print a quality summary after a horse passes validation, providing positive feedback."""
    matrix = horse_entry.get('matrix', {})
    scores = []
    display_dims = [
        ('狀態', 'stability'),
        ('段速', 'sectional'),
        ('形勢', 'race_shape'),
        ('騎練', 'jockey_trainer'),
        ('級磅', 'class_weight'),
        ('場地', 'track'),
        ('賽線', 'form_line'),
    ]
    matrix = _au_normalize_matrix(matrix)
    for short_dim, dim_key in display_dims:
        data = matrix.get(dim_key, {})
        score = data.get('score', '?') if isinstance(data, dict) else str(data)
        scores.append(f"{short_dim}:{score}")

    print(f"   📊 矩陣: {' | '.join(scores)}")

    core_logic = horse_entry.get('core_logic', '')
    if core_logic and len(core_logic) > 20:
        print(f"   💡 邏輯: {core_logic[:80]}...")
        print(f"   📏 長度: {len(core_logic)} 字")

    # Quality check: score diversity
    all_scores = [d.get('score', '') for d in matrix.values() if isinstance(d, dict)]
    unique_scores = set(all_scores)
    if len(unique_scores) <= 2 and len(all_scores) >= 6:
        print(f"   ⚠️ 品質警告: 分數差異度低（只有 {len(unique_scores)} 種分數）— 可能需要重新審視")
    elif len(unique_scores) >= 4:
        print(f"   ✨ 分數差異度良好 ({len(unique_scores)} 種不同分數)")


# Fluff phrases that indicate lazy/template analysis
FLUFF_PHRASES_AU = [
    '配搭無特別異常', '一般而言', '整體尚可', '無特別優劣',
    '中規中矩', '表現平平', '沒有明顯', '無明顯',
    '暫時未有特別', '有待觀察', '資料有限',
]

# Dummy phrases from known auto_fill bypass scripts
DUMMY_PHRASES_AU = [
    '自動匹配系統法則', '具備潛力', '狀態待觀', '分析中', '待補充',
    '有一定競爭力', '表現尚可接受', '基於客觀數據自動判定',
    '符合各項賽事指標', '根據賽事數據',
]

def validate_au_firewalls(h, h_entry, horses_dict, all_horses, json_file):
    """AU-specific per-horse firewall validation. Returns list of error strings.
    V3: Added WALL-019 nonce prefix, WALL-017B dummy detection.
    """
    errors = []
    horse_name = h_entry.get('horse_name', '')
    core_logic = h_entry.get('core_logic', '')
    locked_nonce = h_entry.get('_validation_nonce', '')

    for err in scan_json_for_dummy(h_entry, allow_pending_fill=False):
        errors.append(f"WALL-DUMMY: {err}")

    # WALL-022: V4.2 matrix schema must be exactly 7 dimensions.
    errors.extend(validate_v42_matrix_schema_au(h_entry))
    errors.extend(validate_matrix_resource_checks_au(h_entry.get('matrix', {})))
    errors.extend(validate_au_matrix_confidence(h_entry))
    
    # WALL-008: Nonce validation
    if not locked_nonce:
        errors.append("WALL-008: Missing _validation_nonce")
    
    # WALL-019: Nonce prefix validation — only SKEL_ nonces from skeleton scripts are valid
    if locked_nonce and not locked_nonce.startswith('SKEL_'):
        errors.append(f"WALL-019: NONCE 格式無效 ('{locked_nonce[:20]}...')。只接受 SKEL_ 開頭嘅 nonce。")
    
    # WALL-009: base_rating/final_rating are now [AUTO] — computed by Python
    # No LLM validation needed; compile_analysis_template.py handles this
    
    # WALL-010: Pre-Analysis Checklist Consistency Check (V9.5)
    checklist = h_entry.get('pre_analysis_checklist', {})
    if checklist:
        ev_src = checklist.get('primary_evidence_source', '')
        trial_pct = checklist.get('trial_influence_pct', 0)
        grade_wo = checklist.get('grade_without_trial', '')
        trial_flag = h_entry.get('trial_illusion', False)
        career_tag = str(h_entry.get('career_tag', '')).upper()
        try:
            official_starts = int(h_entry.get('career_race_starts', checklist.get('career_race_starts', 999)))
        except (TypeError, ValueError):
            official_starts = 999
        try:
            checklist_starts = int(checklist.get('career_race_starts', official_starts))
        except (TypeError, ValueError):
            checklist_starts = -1

        if official_starts != 999 and checklist_starts != official_starts:
            errors.append(
                f"WALL-023: pre_analysis_checklist.career_race_starts={checklist_starts} "
                f"同 Python 官方 Career={official_starts} 不一致。請勿改 Python 預填生涯場次。"
            )

        is_debut = career_tag == 'DEBUT' or official_starts == 0 or h_entry.get('debut_runner', False)
        is_early = is_debut or career_tag == 'EARLY_CAREER' or official_starts <= 5

        if is_debut and ev_src == 'race_form':
            errors.append(
                "WALL-023: Career=0 初出馬不可填 primary_evidence_source='race_form'。"
                "請改為 trial_only / bloodline_only / mixed，並按 02h_debut_guide.md 判斷。"
            )

        if is_debut:
            normalized_matrix = _au_normalize_matrix(h_entry.get('matrix', {}))
            stability = normalized_matrix.get('stability', {}) if isinstance(normalized_matrix, dict) else {}
            form_line = normalized_matrix.get('form_line', {}) if isinstance(normalized_matrix, dict) else {}
            stability_score = stability.get('score', '') if isinstance(stability, dict) else str(stability)
            form_line_score = form_line.get('score', '') if isinstance(form_line, dict) else str(form_line)
            if '✅' in stability_score:
                errors.append(
                    "WALL-023: Career=0 初出馬必須用 02h_debut_guide.md；"
                    "matrix.stability 不可打 ✅，應以試閘/Sire/騎練資料保守判 ➖。"
                )
            if '✅' in form_line_score:
                errors.append(
                    "WALL-023: Career=0 初出馬無正式賽績線，matrix.form_line 不可打 ✅；"
                    "試閘對手只可低信心參考，最多 ➖。"
                )
            if core_logic and '[FILL' not in core_logic and not any(term in core_logic for term in ('初出', 'Career=0', 'debut', '試閘')):
                errors.append(
                    "WALL-023: Career=0 初出馬 core_logic 必須使用初出馬格式，"
                    "交代試閘/Sire/騎練部署、Pace Confidence 與 trial-only 封頂。"
                )

        if is_early and core_logic and '[FILL]' not in core_logic:
            banned = ['休出', '休後復出', 'First-up from spell', 'first-up from spell', 'spell return']
            hit = next((p for p in banned if p in core_logic), '')
            if hit:
                errors.append(
                    f"WALL-023: Career≤5 / {career_tag or official_starts} 馬匹不可寫成「{hit}」。"
                    "正確寫法係「初出馬」或「生涯第 X 場正式賽事」。"
                )
        
        if ev_src == 'trial_only' and not trial_flag:
            errors.append(
                f"WALL-010: 你自己答咗 primary_evidence_source='trial_only'，"
                f"但 trial_illusion=false。呢個前後矛盾！"
                f"請將 trial_illusion 設為 true（封頂 B+）。"
            )
        if grade_wo == 'no_data' and not trial_flag:
            errors.append(
                f"WALL-010: 你答咗 grade_without_trial='no_data'（冇試閘就冇數據），"
                f"但 trial_illusion=false。矛盾！請設 trial_illusion=true。"
            )
        try:
            if isinstance(trial_pct, str):
                trial_pct = int(trial_pct)
            if trial_pct > 50 and not trial_flag:
                errors.append(
                    f"WALL-010: trial_influence_pct={trial_pct}%（>50%），"
                    f"表示分析過度依賴試閘。請重新審視 trial_illusion 是否應為 true。"
                )
        except (ValueError, TypeError):
            pass
    
    # WALL-011: Fine-Tune Trigger Code Validation (V9.5)
    VALID_UP_CODES = {
        'PACE_FIT', 'JOCKEY_FIT', 'WEIGHT_SYNERGY', 'GEAR_POSITIVE',
        'TRAINER_TRACK', 'MOMENTUM_3WIN', 'MOMENTUM_2WIN',
        'WEIGHT_EXTREME', 'MID_CLASS_LIGHT', 'SOFT_LIGHT', 'LAST_WIN',
        'GEAR_RESET', 'DISTANCE_SPECIALIST', 'SIRE_DISTANCE',
        'TRACK_SWITCH', 'WET_TRACK', '無'
    }
    VALID_DOWN_CODES = {
        'FATAL_DRAW', 'INSIDE_TRAP', 'INTERSTATE', 'DISTANCE_JUMP',
        'WIN_REGRESSION', 'TOP_WEIGHT', 'PACE_AGAINST', 'JOCKEY_CLASH',
        'PACE_BURN', 'CONTRADICTION', '無'
    }
    ft = h_entry.get('fine_tune', {})
    ft_dir = ft.get('direction', '無')
    ft_code = ft.get('trigger_code', '無')
    
    if ft_code and ft_code not in ('[FILL: 代碼或「無」]', ''):
        all_valid = VALID_UP_CODES | VALID_DOWN_CODES
        if ft_code not in all_valid:
            errors.append(
                f"WALL-011: trigger_code '{ft_code}' 唔係合法代碼！"
                f"請從骨架註釋嘅預定義列表揀選。"
            )
        if ft_dir == '+' and ft_code in VALID_DOWN_CODES and ft_code != '無':
            errors.append(
                f"WALL-011: direction='+' 但 trigger_code='{ft_code}' 係降級代碼，矛盾！"
            )
        if ft_dir == '-' and ft_code in VALID_UP_CODES and ft_code != '無':
            errors.append(
                f"WALL-011: direction='-' 但 trigger_code='{ft_code}' 係升級代碼，矛盾！"
            )
    
    # WALL-012: Direction/Code Coupling (V9.5)
    if isinstance(ft, dict):
        ft_dir_012 = ft.get('direction', '無')
        ft_code_012 = ft.get('trigger_code', '無')
        
        if ft_dir_012 in ('+', '-') and ft_code_012 == '無':
            errors.append(
                f"WALL-012: direction='{ft_dir_012}' 但 trigger_code='無'。"
                f"如果要微調，必須從預定義列表揀選一個合法代碼。"
            )
        if ft_dir_012 == '無' and ft_code_012 != '無' and ft_code_012 not in ('[FILL: 代碼或「無」]', ''):
            errors.append(
                f"WALL-012: direction='無' 但 trigger_code='{ft_code_012}'。"
                f"如果無微調，trigger_code 都應該係「無」。"
            )
    
    # WALL-013: Anti-Double-Counting Warning (WARNING only, not error)
    DOUBLE_COUNT_MAP = {
        'GEAR_POSITIVE': 'jockey_trainer',
        'GEAR_RESET': 'jockey_trainer',
        'JOCKEY_FIT': 'jockey_trainer',
        'TRAINER_TRACK': 'jockey_trainer',
        'WEIGHT_SYNERGY': 'class_weight',
        'WEIGHT_EXTREME': 'class_weight',
        'MID_CLASS_LIGHT': 'class_weight',
        'MOMENTUM_3WIN': 'stability',
        'MOMENTUM_2WIN': 'stability',
        'LAST_WIN': 'stability',
        'PACE_FIT': 'race_shape',
        'PACE_AGAINST': 'race_shape',
        'FATAL_DRAW': 'race_shape',
        'DISTANCE_JUMP': 'sectional',
        'DISTANCE_SPECIALIST': 'sectional',
        'SIRE_DISTANCE': 'sectional',
        'TRACK_SWITCH': 'track',
        'WET_TRACK': 'track',
    }
    if isinstance(ft, dict):
        ft_code_013 = ft.get('trigger_code', '無')
        if ft_code_013 in DOUBLE_COUNT_MAP:
            mapped_dim = DOUBLE_COUNT_MAP[ft_code_013]
            matrix = _au_normalize_matrix(h_entry.get('matrix', {}))
            dim_data = matrix.get(mapped_dim, {})
            dim_score = dim_data.get('score', '➖') if isinstance(dim_data, dict) else str(dim_data)
            if '✅' in dim_score:
                print(
                    f"   ⚠️ WALL-013 雙重計算警告: trigger_code='{ft_code_013}' "
                    f"對應嘅矩陣維度「{mapped_dim}」已經係 {dim_score}。"
                    f"請確認微調理由唔係重複計算已有嘅 ✅。"
                )

    # WALL-016: Core Logic Fact Citation Check (V2.2)
    if core_logic and '[FILL]' not in core_logic and not errors:
        has_specific_date = bool(re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', core_logic))
        has_specific_track = bool(re.search(
            r'(?:Cranbourne|Flemington|Caulfield|Moonee Valley|Sandown|Pakenham|'
            r'Bendigo|Ballarat|Geelong|Mornington|Sale|Warrnambool|Echuca|'
            r'Randwick|Rosehill|Canterbury|Kensington|Newcastle)',
            core_logic
        ))
        has_pi_value = bool(re.search(r'PI\s*[=:：]?\s*[+\-]?\d', core_logic))
        has_numeric_evidence = bool(re.search(r'\d{2,}m|\d+(?:th|st|nd|rd)\b|\d+/\d+', core_logic))
        
        fact_score = sum([has_specific_date, has_specific_track, has_pi_value, has_numeric_evidence])
        if fact_score == 0:
            errors.append(
                f"WALL-016: core_logic 缺乏具體事實引用！"
                f"真正嘅分析應該包含至少一個：具體日期、場地名、PI 數值、或距離/名次數據。"
                f"當前文本疑似由模板腳本生成。"
            )

    # WALL-011B: Fluff Detection (V2 — matching HKJC pipeline)
    if core_logic and '[FILL]' not in core_logic:
        for phrase in FLUFF_PHRASES_AU:
            if phrase in core_logic:
                errors.append(
                    f"WALL-011B: core_logic 含有模板化語句「{phrase}」，"
                    f"請替換為具體數據分析"
                )
                break
    
    # WALL-017B: Dummy phrase detection — catch known auto_fill script outputs
    if core_logic and '[FILL]' not in core_logic:
        for phrase in DUMMY_PHRASES_AU:
            if phrase in core_logic:
                errors.append(
                    f"WALL-017B: core_logic 含有已知 bypass 腳本特徵碼「{phrase}」。"
                    f" 請刪除 auto_fill 腳本，用 LLM 做真正分析。"
                )
                break

    # WALL-020 (SIP-AU-018): core_logic 禁止自行寫評級判斷
    if core_logic and '[FILL]' not in core_logic:
        rating_patterns = re.findall(
            r'評為|評定為|判定為|屬[SA-D][+\-]?[級等]|'
            r'給予[SA-D]|定為[SA-D]|評級[為是][SA-D]',
            core_logic
        )
        if rating_patterns:
            errors.append(
                f"WALL-020 (SIP-AU-018): core_logic 含有自行評級判斷「{'、'.join(rating_patterns[:3])}」。"
                f"評級由 Python 引擎計算，core_logic 只可以寫分析推演過程。"
            )

    # WALL-015: Cross-horse core_logic similarity (V11)
    for other_h, other_entry in horses_dict.items():
        if str(other_h) == str(h):
            continue
        other_cl = str(other_entry.get('core_logic', ''))
        if not other_cl or '[FILL]' in other_cl or len(other_cl) < 40:
            continue
        if core_logic and len(core_logic) >= 40 and '[FILL]' not in core_logic:
            sim = SequenceMatcher(None, core_logic, other_cl).ratio()
            if sim > 0.60:
                errors.append(
                    f"WALL-015: core_logic similarity with Horse {other_h} is {sim:.0%}. "
                    f"Each horse's analysis must be unique."
                )
                break

    # WALL-021: V4.2 — Check matrix reasoning completeness
    matrix = h_entry.get('matrix', {})

    matrix_filled = all(
        '[FILL' not in str(v.get('score', ''))
        for v in matrix.values()
        if isinstance(v, dict)
    )

    reasoning_unfilled = []
    for k, v in matrix.items():
        if isinstance(v, dict) and '[FILL' in str(v.get('reasoning', '')):
            reasoning_unfilled.append(f'matrix.{k}.reasoning')

    if matrix_filled and reasoning_unfilled:
        errors.append(
            f"WALL-021: Matrix scores 已填但 reasoning 仍有 {len(reasoning_unfilled)} 個 [FILL]。"
            f" 必須先完成 reasoning 再填分數。"
            f" 未填: {', '.join(reasoning_unfilled[:5])}"
        )

    return errors


def validate_au_global_firewalls(horses_dict, all_horses, json_file):
    """AU global firewall checks (WALL-015 Batch Injection Detection). Returns list of error strings."""
    errors = []
    try:
        horses_with_logic = sum(
            1 for hk, hv in horses_dict.items()
            if hv.get('core_logic') and '[FILL]' not in str(hv.get('core_logic', ''))
        )
        if horses_with_logic >= len(all_horses) and len(all_horses) >= 5:
            nonces = [horses_dict.get(str(hh), {}).get('_validation_nonce', '') for hh in all_horses]
            unique_nonces = set(n for n in nonces if n)
            if len(unique_nonces) <= 2 and len(nonces) >= 5:
                errors.append(
                    f"WALL-015: 全場 {len(all_horses)} 匹馬只用咗 {len(unique_nonces)} 個 NONCE！"
                    f"正常流程每匹馬應有獨立 NONCE。疑似腳本批量注入。"
                )
    except Exception:
        pass
    return errors



# ═══════════════════════════════════════════════════════════════

def main():
    """AU Wong Choi Orchestrator — LangGraph Pipeline.
    
    All orchestration logic is now handled by the LangGraph StateGraph.
    Business logic functions (firewalls, validation, QA) remain in this file
    and are imported by racing_graph_nodes.py via the domain function registry.
    
    Legacy state machine removed — recoverable via git if needed.
    """
    parser = argparse.ArgumentParser(description="AU Wong Choi Racing Orchestrator (LangGraph)")
    parser.add_argument("url", help="Racenet Event URL or target directory path")
    parser.add_argument("--auto", action="store_true", help="Auto mode (preserved for compatibility)")
    parser.add_argument("--autopilot", action="store_true",
                        help="Enable LangGraph autopilot mode (alias for --auto)")
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
        venue, formatted_date = parse_url_for_details(url)
        target_dir = get_target_dir(venue, formatted_date)
        if not target_dir:
            # Try auto-create + extract
            target_dir = get_target_dir(venue, formatted_date, auto_create=True)
            if target_dir:
                trigger_extractor(url)
    else:
        target_dir = os.path.abspath(args.url)
        if not os.path.isdir(target_dir):
            print(f"❌ Not a valid directory: {target_dir}")
            sys.exit(1)

    if not target_dir or not os.path.isdir(target_dir):
        print("❌ Cannot resolve target directory")
        sys.exit(1)

    # ── Delegate to LangGraph ──
    _lg_scripts = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               '..', '..', '..', '..', 'scripts')
    sys.path.insert(0, os.path.abspath(_lg_scripts))
    from racing_graph_core import run_au_langgraph

    run_au_langgraph(target_dir, url, autopilot=args.auto or args.autopilot)


if __name__ == "__main__":
    main()
