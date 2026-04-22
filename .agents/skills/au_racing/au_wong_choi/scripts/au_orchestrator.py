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
from rating_engine_v2 import parse_matrix_scores, compute_base_grade, apply_fine_tune, grade_sort_index

AU_MATRIX_SCHEMA = {
    "狀態與穩定性": "core", "段速與引擎": "core",
    "形勢與走位": "semi", "騎練訊號": "semi",
    "級數與負重": "aux", "場地適性": "aux",
    "賽績線": "aux", "裝備與距離": "aux",
}

def auto_compute_verdict(logic_data, facts_file):
    """Auto-compute verdict Top 4 from matrix grades. Eliminates LLM verdict stop."""
    horses = logic_data.get('horses', {})
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    
    # Compute grade for each horse
    graded = []
    for h_num, h_obj in horses.items():
        m_data = h_obj.get('matrix', {})
        core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(m_data, AU_MATRIX_SCHEMA)
        b_grade = compute_base_grade(core_pass, semi_pass, aux_pass, core_fail, total_fail)
        ft = h_obj.get('fine_tune', {})
        ft_dir = ft.get('direction', '無') if isinstance(ft, dict) else str(ft)
        f_grade = apply_fine_tune(b_grade, ft_dir)
        grade_i = grade_sort_index(f_grade)
        tick_count = _count_matrix_ticks(m_data)
        double_ticks = _count_matrix_double_ticks(m_data)
        graded.append((h_num, h_obj.get('horse_name', ''), f_grade, grade_i, tick_count, double_ticks))
    
    # Sort by grade, then signal strength, then horse number.
    graded.sort(key=lambda x: (x[3], -x[4], -x[5], int(x[0]) if str(x[0]).isdigit() else 999))
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
                if '[FILL]' not in ac and 'FILL:' not in ac:
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
    dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date}_{venue}_Race_")]
    if not dirs:
        dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date} {venue}")]
    if dirs:
        return os.path.abspath(os.path.join(base_dir, dirs[0]))
    
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
        'leaders': _parse_num_list_from_speed_map_line(_field('leaders')),
        'on_pace': _parse_num_list_from_speed_map_line(_field('on_pace')),
        'mid_pack': _parse_num_list_from_speed_map_line(_field('mid_pack')),
        'closers': _parse_num_list_from_speed_map_line(_field('closers')),
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
        'leaders': [],
        'on_pace': [],
        'mid_pack': [],
        'closers': [],
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

    # Fitness arc derivation
    starts = int(anchors['career_starts'])
    if starts == 0:
        anchors['fitness_arc'] = '初出馬（零正式賽事經驗）'
    elif starts == 1:
        anchors['fitness_arc'] = '二出'
    elif starts == 2:
        anchors['fitness_arc'] = 'Third-up（第三仗）'
    elif starts <= 5:
        anchors['fitness_arc'] = f'輕度備戰（{starts}仗）'
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

    card = []
    card.append(f"# 🐎 分析工作卡 [{horse_idx+1}/{total_horses}] — Horse #{horse_num} {anchors['name']}")
    card.append(f"**檔位: {anchors['barrier']} | 騎師: {anchors['jockey']} | 練馬師: {anchors['trainer']}**")
    card.append(f"📍 步速: {sm_pace} | 偏差: {sm_bias} | 班次: {race_class} | 距離: {distance}")
    card.append(f"📖 評級矩陣規則: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md")
    card.append(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md")
    card.append("")
    card.append("---")
    card.append("## ⚠️ 指引")
    card.append("- 每個維度必須根據下方列出嘅**具體數據**作出判斷")
    card.append("- 分數只可以係 ✅✅ / ✅ / ➖ / ❌ / ❌❌")
    card.append("- 理據必須引用具體數據（日期、場地、名次、PI 數值等）")
    card.append("- 唔可以寫「一般」、「尚可」、「配搭無特別異常」等模板化語句")
    card.append("---")
    card.append("")

    # ── Dimension 1: 狀態與穩定性 [核心] ──
    card.append("## 1️⃣ 狀態與穩定性 [核心維度]")
    card.append(f"- 正式賽事場次: **{anchors['career_starts']}**")
    card.append(f"- 近績序列: `{anchors['recent_form']}`")
    card.append(f"- 狀態週期: **{anchors['fitness_arc']}**")
    card.append(f"- 上仗備註: {anchors['last_run_remark']}")
    card.append("👉 **你嘅判斷:** ✅✅/✅/➖/❌/❌❌？寫 1-2 句引用上述數據嘅理據。")
    card.append("")

    # ── Dimension 2: 段速與引擎 [核心] ──
    card.append("## 2️⃣ 段速與引擎 [核心維度]")
    card.append(f"- PI 趨勢: {anchors.get('pi_trend', '數據不足')}")
    card.append(f"- L400 趨勢: {anchors.get('l400_trend', '數據不足')}")
    card.append(f"- 引擎類型: {anchors.get('engine_type', '未知')}")
    card.append(f"- 今仗步速預測: {sm_pace}")
    card.append("👉 **你嘅判斷:** 段速質素如何？引擎同今仗步速配唔配？")
    card.append("")

    # ── Dimension 3: 形勢與走位 [半核心] ──
    card.append("## 3️⃣ 形勢與走位 [半核心]")
    card.append(f"- 走位形勢: {anchors.get('''race_shape_assessment''', '無數據')}")
    card.append(f"- 上仗跑法: {anchors.get('last_run_style', '無數據')}")
    card.append(f"- 今仗檔位: {anchors.get('barrier', '?')}")
    card.append(f"- 跑道偏差: {sm_bias}")
    card.append("👉 **你嘅判斷:** 步速/檔位/跑法形勢是否明確有利？步速/檔位/走位形勢是否明確有利或不利？。")
    card.append("")

    # ── Dimension 4: 騎練訊號 [半核心] ──
    card.append("## 4️⃣ 騎練訊號 [半核心]")
    card.append(f"- 騎師: {anchors.get('jockey', '?')}")
    card.append(f"- 練馬師: {anchors.get('trainer', '?')}")
    card.append("👉 **你嘅判斷:** 有冇出擊訊號？騎練組合有冇特殊意義？冇資料就寫 ➖。")
    card.append("")

    # ── Dimension 5: 級數與負重 [輔助] ──
    card.append("## 5️⃣ 級數與負重 [輔助]")
    card.append(f"- 今仗班次: {race_class}")
    card.append(f"- 班次變動: {anchors.get('class_move', '無明顯升降')}")
    card.append("👉 **你嘅判斷:** 班次有冇優勢？有冇超班降班？")
    card.append("")

    # ── Dimension 6: 場地適性 [輔助] ──
    card.append("## 6️⃣ 場地適性 [輔助]")
    card.append(f"- 好地紀錄: {anchors.get('good_record', '無')}")
    card.append(f"- 軟地紀錄: {anchors.get('soft_record', '無')}")
    card.append(f"- 同場紀錄: {anchors.get('course_record', '無')}")
    card.append("👉 **你嘅判斷:** 對今日場地有冇經驗？有冇贏過？")
    card.append("")

    # ── Dimension 7: 賽績線 [輔助] ──
    card.append("## 7️⃣ 賽績線 [輔助]")
    card.append(f"- 賽績線強度: {anchors.get('formline_strength', '無資料')}")
    card.append("👉 **你嘅判斷:** 對手後續表現強唔強？強組/弱組？")
    card.append("")

    # ── Dimension 8: 裝備與距離 [輔助] ──
    card.append("## 8️⃣ 裝備與距離 [輔助]")
    card.append(f"- 今仗距離: {distance}")
    card.append(f"- 距離紀錄: {anchors.get('distance_record', '無紀錄')}")
    card.append(f"- 最佳距離: {anchors.get('best_distance', '數據不足')}")
    card.append("👉 **你嘅判斷:** 路程啱唔啱？裝備有冇變？")
    card.append("")

    # ── Final synthesis ──
    card.append("---")
    card.append("## 📋 綜合部分（填完 8 個維度後）")
    card.append("- **core_logic**: 串連所有維度寫成連貫分析（必須引用具體賽事/數據）")
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
                       poll_interval=3, timeout_minutes=10):
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

    print(f"\n👀 Python 正在監控 Horse #{horse_num}... (每 {poll_interval} 秒 | 超時 {timeout_minutes} 分鐘)")

    try:
        while True:
            time.sleep(poll_interval)

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
                continue

            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                continue

            time.sleep(0.5)  # Debounce
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
    for dim in ['狀態與穩定性', '段速與引擎', '形勢與走位', '騎練訊號',
                '級數與負重', '場地適性', '賽績線', '裝備與距離']:
        data = matrix.get(dim, {})
        score = data.get('score', '?') if isinstance(data, dict) else str(data)
        # Compact display
        short_dim = dim[:4]
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
        'WEIGHT_EXTREME', 'MID_CLASS_LIGHT', 'SOFT_LIGHT', 'LAST_WIN', '無'
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
        'GEAR_POSITIVE': '裝備與距離',
        'JOCKEY_FIT': '騎練訊號',
        'WEIGHT_SYNERGY': '級數與負重',
        'WEIGHT_EXTREME': '級數與負重',
        'MID_CLASS_LIGHT': '級數與負重',
        'MOMENTUM_3WIN': '狀態與穩定性',
        'MOMENTUM_2WIN': '狀態與穩定性',
        'LAST_WIN': '狀態與穩定性',
    }
    if isinstance(ft, dict):
        ft_code_013 = ft.get('trigger_code', '無')
        if ft_code_013 in DOUBLE_COUNT_MAP:
            mapped_dim = DOUBLE_COUNT_MAP[ft_code_013]
            matrix = h_entry.get('matrix', {})
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
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Racenet Event URL or target directory path")
    parser.add_argument("--auto", action="store_true", help="Auto mode for resumed NEXT_CMD execution")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    url = args.url
    target_dir = None

    if url.startswith("http"):
        venue, formatted_date = parse_url_for_details(url)
    else:
        # Directory resume mode (same as HKJC)
        target_dir = os.path.abspath(url)
        if not os.path.isdir(target_dir):
            print(f"❌ [Error] 提供的路徑 {target_dir} 不是有效目錄。")
            sys.exit(1)
        dir_name = os.path.basename(target_dir)
        parts = dir_name.split(" ", 1)
        formatted_date = parts[0] if parts else "unknown"
        venue = parts[1] if len(parts) > 1 else "Unknown"
        url = None

    print("="*60)
    print("🏇 AU Wong Choi Orchestrator (State Machine V11)")
    print("="*60)
    
    # V11: Context Injection Gateway
    print_context_injection_au()

    if not target_dir:
        target_dir = get_target_dir(venue, formatted_date)
    if not target_dir:
        if not url:
            print("❌ [Error] 找不到目標目錄且無 URL 可提取資料。")
            sys.exit(1)
        print("📂 找不到目標數據庫，將執行 State 0 (提取資料)...")
        target_dir = get_target_dir(venue, formatted_date, auto_create=True)
        trigger_extractor(url)
        if not os.path.isdir(target_dir):
            print("❌ [Fatal] 爬蟲執行後仍找不到目標資料夾！")
            sys.exit(1)
    
    # ── Preflight Security Check ──
    preflight_script = ".agents/scripts/preflight_environment_check.py"
    if os.path.exists(preflight_script):
        pf_result = subprocess.run(
            [PYTHON, preflight_script, target_dir, "--domain", "au",
             "--session-start", str(SESSION_START_TIME)],
            capture_output=True, text=True
        )
        print(pf_result.stdout)
        if pf_result.returncode == 2:
            print("🛑 Preflight check FAILED — 請清理可疑檔案後再執行！")
            sys.exit(2)
            
    total_races = discover_total_races(target_dir)
    print(f"✅ 目標目錄: {os.path.basename(target_dir)}")
    print(f"✅ 賽事總數: {total_races} 場\n")
    
    date_prefix = os.path.basename(target_dir).split(" ")[0]
    short_prefix = date_prefix[5:] if len(date_prefix) == 10 else date_prefix

    # V11: Build/Load Meeting State
    state_path = os.path.join(target_dir, '.meeting_state.json')
    meeting_state = load_meeting_state_au(state_path)
    if meeting_state:
        print("📊 已載入 .meeting_state.json (V11 Resume)")
    else:
        meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
        save_meeting_state_au(state_path, meeting_state)
        print("📊 已建立 .meeting_state.json (V11 Fresh)")
    print_meeting_dashboard_au(meeting_state)
    ensure_context_files_loaded_au(target_dir)

    # --- STATE 0: Idempotent Raw Data Check ---
    missing_raw = check_raw_data_completeness(target_dir, total_races)
    chk_raw = "[ ]" if missing_raw else "[x]"
    
    # --- Check higher states ---
    weather_file = os.path.join(target_dir, "_Meeting_Intelligence_Package.md")
    intel_ok, intel_issues = validate_intelligence_package_au(weather_file)
    chk_weather = "[x]" if intel_ok else "[ ]"
    
    facts_done = 0
    skel_done = 0
    analysis_passed = 0
    
    facts_status = {}
    analysis_status = {}
    batch_details = {}
    strikes_for_status = load_qa_strikes_au(target_dir)
    
    for r in range(1, total_races + 1):
        facts_status[r] = any(re.search(rf'Race {r} Facts\.md', f) for f in os.listdir(target_dir))
        if facts_status[r]: 
            facts_done += 1
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            if not os.path.exists(facts_file):
                facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
            horses = get_horse_numbers(facts_file)
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            done_horses = []
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        j_data = json.load(f)
                        if 'horses' in j_data:
                            done_horses = [int(k) for k, v in j_data['horses'].items()
                                           if v and '[FILL]' not in json.dumps(
                                               {fk: fv for fk, fv in v.items() if fk not in ('base_rating', 'final_rating')},
                                               ensure_ascii=False)]
                except Exception:
                    pass
            batch_details[r] = {
                'batches': get_batches(horses, 3),
                'done': done_horses,
                'horses': horses
            }
            
        an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
        if os.path.exists(an_file):
            with open(an_file, 'r', encoding='utf-8') as _af:
                content = _af.read()
            if "[FILL]" not in content and "FILL:" not in content:
                if has_open_qa_strike_au(strikes_for_status, r):
                    analysis_status[r] = False
                else:
                    analysis_passed += 1
                    analysis_status[r] = True

    chk_facts = "[x]" if facts_done == total_races else "[ ]"
    chk_analysis = "[x]" if analysis_passed == total_races else "[ ]"

    # Persist tasks to _session_tasks.md
    update_session_tasks(target_dir, total_races, missing_raw, chk_weather, facts_status, analysis_status, batch_details)

    print("📊 執行進度 (Task List Checklist):")
    print(f"  {chk_raw} 賽事資料下載")
    print(f"  {chk_weather} 天氣與場地情報")
    print(f"  {chk_facts} 事實錨點生成")
    print(f"  {chk_analysis} JSON 組合與合規 QA")
    print("  (詳細進度已輸出至: _session_tasks.md)")

    # ── Information Isolation (V9.4) ─────────────────────────────
    _current_race = None
    for _r in range(1, total_races + 1):
        if not analysis_status.get(_r, False):
            _current_race = _r
            break
    if _current_race and _current_race in batch_details:
        _bd = batch_details[_current_race]
        _done_n = len(_bd.get('done', []))
        _total_n = len(_bd.get('horses', []))
        print(f"\n📋 當前任務: Race {_current_race} ({_done_n}/{_total_n} 匹馬已完成)")
    elif _current_race:
        print(f"\n📋 當前任務: Race {_current_race} (等待開始)")
    else:
        print(f"\n📋 所有賽事分析已完成！")
    print("="*60 + "\n")

    # --- RACE DISTANCE & CLASS CONFIRMATION ---
    distance_errors = []
    _race_info_cache = {}
    for r in range(1, total_races + 1):
        rc_path = get_racecard_path(target_dir, r)
        race_dist = "?"
        race_class = ""
        if rc_path and os.path.exists(rc_path):
            with open(rc_path, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
            dist_m = re.search(r'[—–-]\s*(\d{3,5})m', header)
            class_m = re.search(r'\d+m\s*\|\s*([^|$]+)', header)
            if dist_m:
                race_dist = f"{dist_m.group(1)}m"
            if class_m:
                race_class = class_m.group(1).strip()
        
        if race_dist == "?":
            distance_errors.append(r)
        
        _race_info_cache[r] = (race_dist, race_class)
    
    if _current_race and _current_race in _race_info_cache:
        _cd, _cc = _race_info_cache[_current_race]
        print(f"📏 當前賽事: R{_current_race} — {_cd} | {_cc}")
    
    if distance_errors:
        print(f"\n🚨 [WARNING] 部分賽事距離提取失敗")
        print("   請檢查 Racecard header 格式是否包含 '— XXXm'\n")
    else:
        print(f"✅ 賽事距離確認正確！\n")

    # --- 3-Strike QA Tracker ---
    qa_tracker_file = os.path.join(target_dir, ".qa_strikes.json")
    strikes = {}
    if os.path.exists(qa_tracker_file):
        try:
            with open(qa_tracker_file, 'r', encoding='utf-8') as f:
                strikes = json.load(f)
        except: pass
        
    def save_strikes():
        with open(qa_tracker_file, 'w', encoding='utf-8') as f:
            json.dump(strikes, f)

    # ── First-run status report ──
    if not args.auto and analysis_passed < total_races:
        print("🚀 首次賽日總結完成；無需人工確認，繼續自動推進。")

    # --- EXECUTION STATE MACHINE ---
    if missing_raw:
        if not url:
            print("🚨 State 0: 原始數據缺失且無 URL（目錄模式），無法自動提取！")
            print("👉 請使用 Racenet URL 重新執行。")
            sys.exit(1)
        print("🚨 State 0: 發現原始數據缺失！自動呼叫 Extractor 進行修補...")
        trigger_extractor(url)
        print("✅ 數據修補完畢！")
        _next_cmd(target_dir)
        sys.exit(0)

    if chk_weather == "[ ]":
        if os.path.exists(weather_file):
            print("🚨 State 1 Firewall: `_Meeting_Intelligence_Package.md` failed authenticity checks.")
            for issue in intel_issues:
                print(f"   ❌ {issue}")
            print("👉 Rebuild it from real weather/track/bias sources. Dummy/stub files are blocked.")
            notify_telegram("🚨 **AU State 1 Firewall**\nMeeting Intelligence Package failed authenticity checks.")
            _next_cmd(target_dir)
            sys.exit(1)
        if not url:
            print("⚙️ State 1: 缺少 MIP 且無 URL（目錄模式）。")
            print("👉 請手動建立 _Meeting_Intelligence_Package.md 或使用 URL 重新執行。")
            _next_cmd(target_dir)
            sys.exit(0)
        print("⚙️ State 1: 自動生成場地天氣情報 (_Meeting_Intelligence_Package.md)...")
        intel_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_meeting_intel.py")
        if os.path.exists(intel_script):
            try:
                subprocess.run([
                    PYTHON, intel_script,
                    "--url", url,
                    "--target-dir", target_dir,
                    "--venue", venue,
                    "--date", formatted_date
                ], check=True)
                print("✅ Meeting Intelligence Package 自動生成完畢！")
                if os.path.exists(weather_file):
                    chk_weather = "[x]"
                else:
                    print("❌ 生成失敗: _Meeting_Intelligence_Package.md 未被建立")
                    print("👉 請手動建立 _Meeting_Intelligence_Package.md")
                    notify_telegram("🚨 **AU State 1 Failed**\nMIP 自動生成失敗，請手動處理。")
                    _next_cmd(target_dir)
                    sys.exit(0)
            except subprocess.CalledProcessError as e:
                print(f"❌ MIP 生成腳本執行失敗: {e}")
                print("👉 Fallback: 請手動建立 _Meeting_Intelligence_Package.md")
                notify_telegram("🚨 **AU State 1 Failed**\nMIP 自動生成腳本執行失敗，請手動處理。")
                _next_cmd(target_dir)
                sys.exit(0)
        else:
            print(f"❌ 找不到 generate_meeting_intel.py: {intel_script}")
            print("👉 LLM Agent 請注意：請調查今日場地天氣與賽道偏差，並於此目錄建立 `_Meeting_Intelligence_Package.md`。")
            notify_telegram("🚨 **AU State 1 Action Required**\n缺少場地天氣與賽道偏差，請手動生成 `_Meeting_Intelligence_Package.md`。")
            _next_cmd(target_dir)
            sys.exit(0)

    if chk_facts == "[ ]":
        print("⚙️ State 2: 正在補全缺失之 Facts.md...")
        for r in range(1, total_races + 1):
            facts_path = None
            for f in os.listdir(target_dir):
                if re.search(rf'Race {r} Facts\.md', f):
                    facts_path = os.path.join(target_dir, f)
                    break
            
            if not facts_path:
                print(f"  -> 生成 Race {r} Facts...")
                rc = get_racecard_path(target_dir, r)
                fg = get_formguide_path(target_dir, r)
                cmd = [PYTHON, ".agents/scripts/inject_fact_anchors.py", rc, fg, "--max-display", "5", "--venue", venue]
                subprocess.run(cmd, check=True)
                
        print("✅ Facts 全部生成完畢！自動無縫推進前往 State 3 執行分析...")

    # ═══════════════════════════════════════════════════════════════
    # STATE 2.5 + 3: V10 Unified Per-Race Loop (File-Watch Architecture)
    # Python is the controller. LLM only fills JSON.
    # ═══════════════════════════════════════════════════════════════
    if chk_analysis == "[ ]":
        skeleton_script = ".agents/skills/au_racing/au_wong_choi/scripts/create_au_logic_skeleton.py"
        
        for r in range(1, total_races + 1):
            # ── Skip completed races ──
            an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
            if os.path.exists(an_file):
                try:
                    with open(an_file, 'r', encoding='utf-8') as _af:
                        _recheck_content = _af.read()
                    if "[FILL]" not in _recheck_content and "FILL:" not in _recheck_content:
                        if has_open_qa_strike_au(strikes, r):
                            print(f"   ⚠️ Race {r} has unresolved QA strike; forcing compile/QA rerun")
                        else:
                            print(f"   ✅ Race {r} 已完成 (跳過)")
                            continue
                except Exception:
                    pass
            if analysis_status.get(r, False) and not has_open_qa_strike_au(strikes, r):
                continue
            
            print(f"\n{'─'*60}")
            print(f"🐎 正在處理 Race {r}...")
            print(f"{'─'*60}")
            
            # V11: Pre-Race Dummy Content Scanner
            _scan_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            scan_result = scan_race_content_quality_au(_scan_json)
            if scan_result['action'] == 'PURGE_ALL':
                print(f"🚨 Race {r} Pre-Race Scan: dummy content detected!")
                for _si in scan_result['issues']:
                    print(f"   ❌ {_si}")
                try:
                    with open(_scan_json, 'r', encoding='utf-8') as _sf:
                        _sd = json.load(_sf)
                    _sd['horses'] = {}
                    with open(_scan_json, 'w', encoding='utf-8') as _sf:
                        json.dump(_sd, _sf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            elif scan_result['action'] == 'PURGE_PARTIAL':
                print(f"⚠️ Race {r} Pre-Race Scan: partial dummy content")
                try:
                    with open(_scan_json, 'r', encoding='utf-8') as _sf:
                        _sd = json.load(_sf)
                    for _ch in scan_result['contaminated_horses']:
                        _hnum = _ch['horse_num']
                        print(f"   🗑️ Horse #{_hnum} ({_ch['horse_name']}): {_ch['issues']}")
                        if _hnum in _sd.get('horses', {}):
                            _sd['horses'][_hnum]['core_logic'] = '[FILL]'
                    with open(_scan_json, 'w', encoding='utf-8') as _sf:
                        json.dump(_sd, _sf, ensure_ascii=False, indent=2)
                except Exception:
                    pass
            else:
                print(f"   ✅ Race {r} Pre-Race Scan: clean")
            
            # ── FLUSH_HINT: Context Window Reset Signal ──
            if r > 1:
                print(f"")
                print(f"{'#'*60}")
                print(f"### FLUSH_HINT ###")
                print(f"# LLM Agent — 請立即丟棄上場賽事所有馬匹個別分析記憶。")
                print(f"# Race {r} 係全新獨立分析單元。")
                print(f"# 只參考以下資源：")
                print(f"#   → .runtime/Horse_N_Context.md (每匹馬獨立)")
                print(f"#   → Race {r} Facts.md (本場事實錨點)")
                print(f"# 上場馬匹名字、評分、走勢均與本場無關，請勿帶入。")
                print(f"{'#'*60}")
                print(f"")

            # Preflight check for each race
            if os.path.exists(preflight_script):
                pf_r = subprocess.run(
                    [PYTHON, preflight_script, target_dir, "--domain", "au",
                     "--session-start", str(SESSION_START_TIME)],
                    capture_output=True, text=True
                )
                if pf_r.returncode == 2:
                    print(pf_r.stdout)
                    print("🛑 Preflight FAILED mid-session!")
                    sys.exit(2)
            
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            if not os.path.exists(facts_file):
                facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            
            # ── Step A: Ensure Logic JSON exists ──
            if not os.path.exists(json_file):
                _rc_path = get_racecard_path(target_dir, r)
                _race_class, _race_dist = "[FILL]", "[FILL]"
                if _rc_path and os.path.exists(_rc_path):
                    try:
                        with open(_rc_path, 'r', encoding='utf-8') as _rc_f:
                            _hdr = _rc_f.readline().strip()
                        _dm = re.search(r'[\u2014\u2013-]\s*(\d{3,5})m', _hdr)
                        _cm = re.search(r'\d+m\s*\|\s*([^|$]+)', _hdr)
                        if _dm: _race_dist = f"{_dm.group(1)}m"
                        if _cm: _race_class = _cm.group(1).strip()
                    except Exception:
                        pass
                try:
                    with open(facts_file, 'r', encoding='utf-8') as _facts_init:
                        _facts_init_text = _facts_init.read()
                    _initial_speed_map = auto_build_au_speed_map_from_facts(_facts_init_text, target_dir)
                except Exception:
                    _initial_speed_map = {
                        "expected_pace": "[FILL]", "leaders": [], "on_pace": [],
                        "mid_pack": [], "closers": [],
                        "track_bias": "[FILL]", "tactical_nodes": "[FILL]", "collapse_point": "[FILL]"
                    }
                _init_json = {
                    "race_analysis": {
                        "race_number": r, "race_class": _race_class, "distance": _race_dist,
                        "speed_map": _initial_speed_map
                    },
                    "horses": {}
                }
                with open(json_file, 'w', encoding='utf-8') as _wf:
                    json.dump(_init_json, _wf, ensure_ascii=False, indent=2)
                _sm_source = _init_json["race_analysis"]["speed_map"].get("source", "PENDING")
                print(f"   ✅ 已自動建立 `Race_{r}_Logic.json` 骨架 ({_race_class} / {_race_dist}) + Speed Map ({_sm_source})")
            
            # ── Step B: Check Speed Map ──
            try:
                with open(json_file, 'r', encoding='utf-8') as _f:
                    logic_data = json.load(_f)
            except Exception:
                logic_data = {}
            
            sm = logic_data.get('race_analysis', {}).get('speed_map', {})
            _sm_check_keys = ['expected_pace', 'track_bias', 'tactical_nodes', 'collapse_point']
            missing_sm = [k for k in _sm_check_keys if not sm.get(k) or sm.get(k) == '[FILL]']
            
            if missing_sm:
                try:
                    with open(facts_file, 'r', encoding='utf-8') as _sm_facts:
                        _sm_facts_content = _sm_facts.read()
                    auto_speed_map = auto_build_au_speed_map_from_facts(_sm_facts_content, target_dir)
                    logic_data.setdefault('race_analysis', {})['speed_map'] = auto_speed_map
                    with open(json_file, 'w', encoding='utf-8') as _sm_out:
                        json.dump(logic_data, _sm_out, ensure_ascii=False, indent=2)
                    sm = auto_speed_map
                    print(f"   ✅ Race {r} Speed Map 自動注入 ({auto_speed_map['expected_pace']}) — 繼續推進")
                except Exception as exc:
                    print(f"❌ Speed Map 自動生成失敗: {exc}")
                    _next_cmd(target_dir)
                    sys.exit(1)
            
            # ── Step C: Get all horses ──
            try:
                all_horses = get_horse_numbers(facts_file)
            except:
                all_horses = []
            
            if not all_horses:
                print(f"⚠️ Race {r}: 無法從 Facts.md 提取馬匹列表")
                continue
            
            # ── Step D: Read facts content for context generation ──
            try:
                with open(facts_file, 'r', encoding='utf-8') as _f:
                    facts_content = _f.read()
            except:
                facts_content = ""
            
            horses_dict = logic_data.get('horses', {})
            
            # ── Step E: Validate already-filled + collect pending ──
            validated_count = 0
            pending_horses = []
            
            for h in all_horses:
                hkey = str(h)
                h_entry = horses_dict.get(hkey, {})
                
                if not h_entry:
                    pending_horses.append(h)
                    continue
                
                h_json_for_check = json.dumps(
                    {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                    ensure_ascii=False
                )
                
                if '[FILL]' in h_json_for_check:
                    pending_horses.append(h)
                    continue
                
                # Validate
                errors = validate_au_firewalls(h, h_entry, horses_dict, all_horses, json_file)
                
                if errors:
                    horse_name = h_entry.get('horse_name', '')
                    print(f"\n🚨 Horse #{h} ({horse_name}) firewall failed!")
                    for e in errors:
                        print(f"   ❌ {e}")
                    horses_dict[hkey]['core_logic'] = '[FILL]'
                    logic_data['horses'] = horses_dict
                    with open(json_file, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    pending_horses.append(h)
                else:
                    validated_count += 1
            
            if validated_count > 0:
                print(f"   ✅ {validated_count}/{len(all_horses)} 匹馬已驗證通過")
            
            # ── Step F+G: Per-Horse Sequential Analysis (V10.1 Quality Architecture) ──
            # Instead of generating ALL skeletons at once and watching for bulk completion,
            # we now process ONE horse at a time: generate work card → watch → validate → next.
            # This prevents the LLM from taking shortcuts with batch-fill scripts.
            if pending_horses:
                # Determine venue-specific track module
                _dir_parts = os.path.basename(target_dir).split(" ", 1)
                _au_venue = _dir_parts[1].lower().replace(" ", "_") if len(_dir_parts) > 1 else ""
                _au_track_file = f"04b_track_{_au_venue}.md"
                _au_track_path = os.path.join(".agents", "skills", "au_racing", "au_horse_analyst", "resources", _au_track_file)
                _au_track_exists = os.path.exists(os.path.join(target_dir, "..", "..", "..", _au_track_path)) or os.path.exists(_au_track_path)
                
                _sm_data = logic_data.get('race_analysis', {}).get('speed_map', {})
                _sm_pace = _sm_data.get('expected_pace', _sm_data.get('predicted_pace', 'N/A'))
                _sm_bias = _sm_data.get('track_bias', 'N/A')
                
                runtime_dir = os.path.join(target_dir, ".runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                
                print(f"\n{'='*60}")
                print(f"📋 Race {r}: {len(pending_horses)} 匹馬待分析（逐匹驅動模式）")
                print(f"{'='*60}")
                print(f"📖 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md")
                print(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md")
                if _au_track_exists:
                    print(f"📖 場地模組: {_au_track_path}")
                print(f"📍 步速: {_sm_pace} | 偏差: {_sm_bias}")
                
                completed_in_session = 0
                
                for horse_idx, ph in enumerate(pending_horses):
                    print(f"\n{'─'*60}")
                    print(f"🐎 [{horse_idx+1}/{len(pending_horses)}] 正在處理 Horse #{ph}")
                    print(f"{'─'*60}")
                    
                    # 1. Generate skeleton (if not already present)
                    skel_result = subprocess.run(
                        [PYTHON, skeleton_script, facts_file, str(r), str(ph)],
                        capture_output=True, text=True
                    )
                    if skel_result.returncode != 0:
                        print(f"❌ Skeleton generation failed: Race {r} Horse #{ph}")
                        if skel_result.stdout:
                            print(skel_result.stdout[-1000:])
                        if skel_result.stderr:
                            print(skel_result.stderr[-1000:])
                        meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
                        save_meeting_state_au(state_path, meeting_state)
                        _next_cmd(target_dir)
                        sys.exit(1)
                    if skel_result.stdout.strip():
                        for line in skel_result.stdout.strip().split('\n'):
                            if '✅' in line or '⚙️' in line:
                                print(f"   {line.strip()}")
                    
                    # 2. Reload JSON to get the nonce
                    with open(json_file, 'r', encoding='utf-8') as _jf:
                        logic_data = json.load(_jf)
                    
                    # 3. Generate guided Work Card (the key quality improvement)
                    card_path = generate_work_card(
                        ph, facts_content, logic_data, runtime_dir,
                        _sm_pace, _sm_bias,
                        horse_idx=horse_idx, total_horses=len(pending_horses)
                    )
                    
                    # 4. Also write legacy Context file for backward compat
                    h_entry = logic_data.get('horses', {}).get(str(ph), {})
                    locked_nonce = h_entry.get('_validation_nonce', 'MISSING')
                    horse_facts_block = extract_horse_facts_block(ph, facts_content)
                    ctx_path = os.path.join(runtime_dir, f"Horse_{ph}_Context.md")
                    with open(ctx_path, "w", encoding="utf-8") as _ctx_f:
                        _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                        _ctx_f.write(f"📖 分析引擎: .agents/skills/au_racing/au_horse_analyst/SKILL.md\n")
                        _ctx_f.write(f"📖 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md\n")
                        _ctx_f.write(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md\n")
                        if _au_track_exists:
                            _ctx_f.write(f"📖 場地模組: {_au_track_path}\n")
                        _ctx_f.write(f"📖 合規參考: .agents/scripts/completion_gate_v2.py + Orchestrator 內置批次 QA\n")
                        _ctx_f.write(f"📍 步速判定: {_sm_pace} | 跑道偏差: {_sm_bias}\n\n")
                        _ctx_f.write(horse_facts_block)
                    
                    # Copy to Active_Horse_Context.md for backward compat
                    active_ctx = os.path.join(runtime_dir, "Active_Horse_Context.md")
                    shutil.copy2(ctx_path, active_ctx)
                    
                    # 5. Print instructions for THIS SINGLE HORSE
                    h_name = h_entry.get('horse_name', '?')
                    print(f"\n👉 LLM: 請讀取以下檔案並分析 Horse #{ph} ({h_name}):")
                    print(f"   📋 工作卡: .runtime/Horse_{ph}_WorkCard.md")
                    print(f"   📄 原始數據: .runtime/Horse_{ph}_Context.md")
                    print(f"   ✏️ 填寫目標: Race_{r}_Logic.json → horses.{ph}")
                    print(f"\n   ⚠️ 只做呢一匹馬！Python 會自動偵測變動並驗證。")
                    
                    # 6. Watch for THIS SINGLE HORSE to pass validation
                    result = watch_single_horse(
                        json_file, ph,
                        validate_fn=validate_au_firewalls,
                        all_horses=all_horses,
                        poll_interval=3,
                        timeout_minutes=10
                    )
                    
                    if result:
                        completed_in_session += 1
                        
                        # V11: Lock validated horse
                        with open(json_file, 'r', encoding='utf-8') as _lf:
                            _lock_data = json.load(_lf)
                        if str(ph) in _lock_data.get('horses', {}):
                            _lock_data['horses'][str(ph)]['_validated'] = True
                            _h_matrix = _lock_data['horses'][str(ph)].get('matrix', {})
                            _tags = []
                            for _dim, _dv in _h_matrix.items():
                                if isinstance(_dv, dict):
                                    _sc = _dv.get('score', '')
                                    if _sc == '✅✅':
                                        _tags.append(f'#{_dim}_strong')
                                    elif _sc == '❌❌':
                                        _tags.append(f'#{_dim}_weak')
                            if _tags:
                                _lock_data['horses'][str(ph)]['scenario_tags'] = ' '.join(_tags)
                            with open(json_file, 'w', encoding='utf-8') as _wf:
                                json.dump(_lock_data, _wf, ensure_ascii=False, indent=2)
                        
                        print(f"\n   ✅ Horse #{ph} ({h_name}) 驗證通過！ [{completed_in_session}/{len(pending_horses)}]")
                        print_analysis_summary(result, ph)
                        print(f"\n   ### FLUSH: Horse #{ph} 分析完畢 — 清除記憶準備下一匹 ###")
                        
                        # V11: Per-batch QA (every 3 horses)
                        if completed_in_session % 3 == 0 and completed_in_session > 0:
                            _batch_start = completed_in_session - 3
                            _batch_nums = pending_horses[_batch_start:completed_in_session]
                            with open(json_file, 'r', encoding='utf-8') as _bf:
                                _batch_data = json.load(_bf)
                            _batch_horses_dict = _batch_data.get('horses', {})
                            _batch_errors = validate_batch_cross_horse_au(_batch_nums, _batch_horses_dict, json_file)
                            if _batch_errors:
                                print(f"\n   ⚠️ Batch QA ({_batch_nums}) issues:")
                                for _be in _batch_errors:
                                    print(f"      ❌ {_be}")
                                for _bh in _batch_nums:
                                    if str(_bh) in _batch_horses_dict:
                                        _batch_horses_dict[str(_bh)]['core_logic'] = '[FILL]'
                                        _batch_horses_dict[str(_bh)]['_validated'] = False
                                _batch_data['horses'] = _batch_horses_dict
                                with open(json_file, 'w', encoding='utf-8') as _wf:
                                    json.dump(_batch_data, _wf, ensure_ascii=False, indent=2)
                                print(f"   🔄 Batch reset — will re-analyse")
                            else:
                                print(f"\n   ✅ Batch QA passed ({_batch_nums})")
                        
                        # V11: Save meeting state
                        meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
                        save_meeting_state_au(state_path, meeting_state)
                    else:
                        print(f"\n   ⏰ Horse #{ph} 超時或被中斷。")
                        print(f"   已完成 {completed_in_session}/{len(pending_horses)} 匹馬。")
                        print(f"   重跑 Orchestrator 可從斷點繼續。")
                        meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
                        save_meeting_state_au(state_path, meeting_state)
                        _next_cmd(target_dir)
                        sys.exit(0)
                
                # All horses done — reload final data
                with open(json_file, 'r', encoding='utf-8') as _jf:
                    logic_data = json.load(_jf)
                
                print(f"\n✅ Race {r} 所有 {len(pending_horses)} 匹馬驗證通過！")
            
            # ── Step H: WALL-015 Global Check ──
            horses_dict = logic_data.get('horses', {})
            global_errors = validate_au_global_firewalls(horses_dict, all_horses, json_file)
            if global_errors:
                for ge in global_errors:
                    print(f"🚨 {ge}")
                print(f"請清理 JSON 後重跑。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step I: 3-Strike Check ──
            if strikes.get(str(r), 0) >= 3:
                print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗 (Strike-3 Fallback)。")
                print(f"系統已中斷自動化，請人類直接打開 `{os.path.basename(json_file)}` 修正長度與邏輯！")
                notify_telegram(f"❌ **AU Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，請人工介入！")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step J: Auto-Verdict ──
            verdict_data = logic_data.get('race_analysis', {}).get('verdict')
            if verdict_needs_recompute_au(logic_data):
                print(f"\n⚙️ Auto-Verdict: 正在為 Race {r} 自動計算 Top 4 排序...")
                verdict = auto_compute_verdict(logic_data, facts_file)
                with open(json_file, 'w', encoding='utf-8') as _wf:
                    json.dump(logic_data, _wf, ensure_ascii=False, indent=2)
                t4_display = ', '.join([f"#{v['horse_number']} {v['horse_name']} ({v['grade']})" for v in verdict['top4']])
                print(f"   ✅ Top 4: {t4_display}")
                notify_telegram(f"✅ **AU Race {r} Auto-Verdict**\nTop 4: {t4_display}")
            
            # ── Step K: Compile ──
            print(f"⚙️ 發現 Race {r} JSON 所有馬匹已聚齊！正在編譯...")
            compile_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compile_analysis_template.py")
            compile_cmd = [PYTHON, compile_script_path, facts_file, json_file, "--output", an_file]
            res = subprocess.run(compile_cmd)
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(json_file)}。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                _next_cmd(target_dir)
                sys.exit(1)
            
            # Post-compile verification
            if not os.path.exists(an_file):
                print(f"❌ 編譯完成但 Analysis.md 未生成！請檢查 compile 腳本。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step L: Monte Carlo Simulation (mc_simulator.py v2.2) ──
            print(f"🎲 Running Monte Carlo simulation for Race {r}...")
            # Robust path discovery: walk up from script dir to find workspace root
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            _search_dir = _script_dir
            mc_simulator_script = None
            for _ in range(8):  # Max 8 levels up
                _candidate = os.path.join(_search_dir, "mc_simulator.py")
                if os.path.exists(_candidate):
                    mc_simulator_script = _candidate
                    break
                _parent = os.path.dirname(_search_dir)
                if _parent == _search_dir:
                    break
                _search_dir = _parent
            if not mc_simulator_script:
                mc_simulator_script = os.path.join(_script_dir, "..", "..", "..", "..", "..", "mc_simulator.py")
            mc_json_out = os.path.join(target_dir, f"Race_{r}_MC_Results.json")

            if os.path.exists(mc_simulator_script):
                mc_res = subprocess.run(
                    [PYTHON, mc_simulator_script, "--input", json_file, "--platform", "au"],
                    capture_output=True, text=True
                )
                if mc_res.returncode == 0 and os.path.exists(mc_json_out):
                    print(f"✅ MC Results generated → Race_{r}_MC_Results.json")
                    # Parse concordance summary from stdout
                    for line in mc_res.stdout.strip().split('\n'):
                        if 'Concordance' in line or '⚠️' in line:
                            print(f"   {line.strip()}")
                else:
                    print(f"⚠️ MC simulation failed (non-blocking): {mc_res.stderr[:300]}")
            else:
                print(f"⚠️ mc_simulator.py not found: {mc_simulator_script}")
            
            # ── Step M: QA (V11: capture_output + diagnosis + 3-strike) ──
            print(f"🛡️ 正在進行 Batch QA (completion_gate_v2.py)...")
            qa_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts", "completion_gate_v2.py")
            qa_res = subprocess.run(
                [PYTHON, qa_script, an_file, "--domain", "au"],
                capture_output=True, text=True
            )
            if qa_res.returncode != 0:
                print(f"\n❌ Race {r} QA 驗證失敗！")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                if qa_res.stdout:
                    for _ql in qa_res.stdout.strip().split('\n')[-10:]:
                        print(f"   {_ql}")
                
                # V11: Generate QA Diagnosis Report
                runtime_dir = os.path.join(target_dir, '.runtime')
                diag_path = generate_qa_diagnosis_au(
                    race_num=r, strike_num=strikes[str(r)],
                    qa_stdout=qa_res.stdout, qa_stderr=qa_res.stderr,
                    logic_json_path=json_file, analysis_path=an_file,
                    runtime_dir=runtime_dir
                )
                print(f"📋 Diagnosis: {os.path.basename(diag_path)}")
                
                if strikes[str(r)] >= 3:
                    print(f"\n🚨 [CRITICAL] Race {r} 3-Strike Stop!")
                    notify_telegram(f"❌ **AU Race {r} 3-Strike Stop**")
                    meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
                    save_meeting_state_au(state_path, meeting_state)
                    _next_cmd(target_dir)
                    sys.exit(1)
                else:
                    print(f"⚠️ Strike {strikes[str(r)]}/3 — fix and re-run Orchestrator")
                    meeting_state = build_meeting_state_au(target_dir, total_races, short_prefix)
                    save_meeting_state_au(state_path, meeting_state)
                    _next_cmd(target_dir)
                    sys.exit(1)
            else:
                print(f"\n{'🎉'*10}")
                print(f"✅ Race {r} Batch QA 通過！")
                print(f"{'🎉'*10}")
                if str(r) in strikes:
                    del strikes[str(r)]
                    save_strikes()
            
            # ── Step N: Auto-advance to next race (no exit) ──
            if r < total_races:
                print(f"\n{'─'*60}")
                print(f"🔄 Race {r} 完成！自動推進到 Race {r+1}...")
                print(f"{'─'*60}")
                # Continue the for-loop to process next race automatically
                continue

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！正在產製 Excel 報告...")
    try:
        subprocess.run([PYTHON, ".agents/skills/au_racing/au_wong_choi/scripts/generate_reports.py", target_dir], check=True)
        subprocess.run([PYTHON, ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "au"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ State 4 failed: {e.cmd} exited with code {e.returncode}")
        print("🛑 停止 dashboard deploy，請先修復報表 / cost tracker 問題。")
        sys.exit(e.returncode)
    
    print("☁️ State 5: 準備推送 Dashboard 至 Cloudflare...")
    push_script = "Horse Racing Dashboard/deploy.sh"
    if os.path.exists(push_script) and shutil.which("bash"):
        subprocess.run(["bash", push_script])
        print("✅ 雲端同步完成！")
    elif os.path.exists(push_script):
        print("⚠️ bash not found (Windows), skipping dashboard deploy. Run manually.")
    else:
        print("👉 (未偵測到 Dashboard 自動推送腳本，請手動發佈)。")
        
    print("\n🎉 [SUCCESS] AU Wong Choi Pipeline 任務全數擊破！")
    notify_telegram("🎉 **AU Wong Choi 任務完成**\n所有分析已順利通過 QA 及編譯！")
    
if __name__ == "__main__":
    main()
