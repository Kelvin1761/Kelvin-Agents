#!/usr/bin/env python3
"""
LangGraph Racing Pipeline — Node Functions
============================================
Domain-agnostic node functions supporting AU and HKJC.
Each node wraps existing business logic from the domain orchestrator.
Zero business logic changes — only orchestration restructuring.
"""
import os
import sys
import json
import re
import subprocess
import shutil
import time

# Cross-platform Python
PYTHON = "python3" if shutil.which("python3") else "python"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_AU_SCRIPTS = os.path.join(_SCRIPT_DIR, '..', 'skills', 'au_racing', 'au_wong_choi', 'scripts')
_HKJC_SCRIPTS = os.path.join(_SCRIPT_DIR, '..', 'skills', 'hkjc_racing', 'hkjc_wong_choi', 'scripts')
sys.path.insert(0, os.path.abspath(_AU_SCRIPTS))
sys.path.insert(0, os.path.abspath(_HKJC_SCRIPTS))
sys.path.insert(0, os.path.abspath(_SCRIPT_DIR))

# Domain-specific function registry
_DOMAIN_FN = {}

def _get_domain_fns(domain):
    """Lazy-load domain-specific functions. Returns dict of callable functions."""
    if domain in _DOMAIN_FN:
        return _DOMAIN_FN[domain]
    
    if domain == "hkjc":
        import hkjc_orchestrator as ho
        fns = {
            "check_raw": ho.check_raw_data_completeness,
            "validate_intel": ho.validate_intelligence_package,
            "get_racecard": ho.get_rc_fg_paths,  # returns (rc, fg) tuple
            "get_horse_numbers": ho.get_horse_numbers,
            "auto_speed_map": ho.auto_build_hkjc_speed_map_from_facts,
            "scan_quality": ho.scan_race_content_quality,
            "validate_firewalls": ho.validate_hkjc_firewalls,
            "validate_batch": ho.validate_batch_cross_horse,
            "validate_global": None,  # HKJC uses same batch validator
            "generate_workcard": ho.generate_hkjc_work_card,
            "watch_horse": ho.watch_single_horse_hkjc,
            "verdict_check": ho.verdict_needs_recompute,
            "auto_verdict": ho.auto_compute_verdict_hkjc,
            "qa_diagnosis": ho.generate_qa_diagnosis,
            "print_summary": ho.print_hkjc_analysis_summary,
            "skeleton_script": ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py",
            "compile_script": os.path.join(os.path.abspath(_HKJC_SCRIPTS), "compile_analysis_template.py"),
            "reports_script": ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_reports.py",
            "context_injection": ho.print_context_injection,
            "discover_races": ho.discover_total_races,
        }
    else:  # au (default)
        import au_orchestrator as ao
        fns = {
            "check_raw": ao.check_raw_data_completeness,
            "validate_intel": ao.validate_intelligence_package_au,
            "get_racecard": lambda td, r: (ao.get_racecard_path(td, r), ao.get_formguide_path(td, r)),
            "get_horse_numbers": ao.get_horse_numbers,
            "auto_speed_map": ao.auto_build_au_speed_map_from_facts,
            "scan_quality": ao.scan_race_content_quality_au,
            "validate_firewalls": ao.validate_au_firewalls,
            "validate_batch": ao.validate_batch_cross_horse_au,
            "validate_global": ao.validate_au_global_firewalls,
            "generate_workcard": ao.generate_work_card,
            "watch_horse": ao.watch_single_horse,
            "verdict_check": ao.verdict_needs_recompute_au,
            "auto_verdict": ao.auto_compute_verdict,
            "qa_diagnosis": ao.generate_qa_diagnosis_au,
            "print_summary": ao.print_analysis_summary,
            "skeleton_script": ".agents/skills/au_racing/au_wong_choi/scripts/create_au_logic_skeleton.py",
            "compile_script": os.path.join(os.path.abspath(_AU_SCRIPTS), "compile_analysis_template.py"),
            "reports_script": ".agents/skills/au_racing/au_wong_choi/scripts/generate_reports.py",
            "context_injection": ao.print_context_injection_au,
            "discover_races": ao.discover_total_races,
        }
    
    _DOMAIN_FN[domain] = fns
    return fns


def _log(msg):
    print(msg)
    return msg


# ═══════════════════════════════════════════════════════════════
# NODE: check_raw_data
# ═══════════════════════════════════════════════════════════════
def node_check_raw_data(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    missing = fns["check_raw"](state["target_dir"], state["total_races"])
    ready = len(missing) == 0
    if not ready:
        _log(f"🚨 State 0: Raw data missing: {missing}")
    else:
        _log("✅ Raw data complete")
    return {"raw_data_ready": ready, "log": [f"raw_data_ready={ready}"]}


# ═══════════════════════════════════════════════════════════════
# NODE: check_intelligence
# ═══════════════════════════════════════════════════════════════
def node_check_intelligence(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    path = os.path.join(state["target_dir"], "_Meeting_Intelligence_Package.md")
    ok, issues = fns["validate_intel"](path)
    if not ok:
        _log(f"🚨 State 1: Intelligence issues: {issues}")
    else:
        _log("✅ Meeting Intelligence Package validated")
    return {"intelligence_ready": ok, "log": [f"intel_ready={ok}"]}


# ═══════════════════════════════════════════════════════════════
# NODE: generate_facts
# ═══════════════════════════════════════════════════════════════
def node_generate_facts(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    total_races = state["total_races"]
    venue = state["venue"]
    all_done = True

    for r in range(1, total_races + 1):
        has_facts = any(re.search(rf'Race {r} Facts\.md', f) for f in os.listdir(target_dir))
        if not has_facts:
            all_done = False
            _log(f"  -> Generating Race {r} Facts...")
            rc_fg = fns["get_racecard"](target_dir, r)
            rc, fg = rc_fg if isinstance(rc_fg, tuple) else (rc_fg, None)
            cmd = [PYTHON, ".agents/scripts/inject_fact_anchors.py", rc, fg,
                   "--max-display", "5", "--venue", venue]
            subprocess.run(cmd, check=True)

    if all_done:
        _log("✅ All Facts.md already exist")
    else:
        _log("✅ Facts generation complete")
    return {"facts_ready": True, "log": ["facts_ready=True"]}


# ═══════════════════════════════════════════════════════════════
# NODE: setup_race
# ═══════════════════════════════════════════════════════════════
def node_setup_race(state):
    """Set up Logic.json skeleton + Speed Map for current_race."""
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    date_prefix = state["date_prefix"]
    short_prefix = state["short_prefix"]

    facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")

    # Create skeleton if needed
    if not os.path.exists(json_file):
        rc_fg = fns["get_racecard"](target_dir, r)
        rc_path = rc_fg[0] if isinstance(rc_fg, tuple) else rc_fg
        race_class, race_dist = "[FILL]", "[FILL]"
        if rc_path and os.path.exists(rc_path):
            with open(rc_path, 'r', encoding='utf-8') as f:
                hdr = f.readline().strip()
            dm = re.search(r'[—–-]\s*(\d{3,5})m', hdr)
            cm = re.search(r'\d+m\s*\|\s*([^|$]+)', hdr)
            if dm: race_dist = f"{dm.group(1)}m"
            if cm: race_class = cm.group(1).strip()

        try:
            with open(facts_file, 'r', encoding='utf-8') as f:
                fc = f.read()
            sm = fns["auto_speed_map"](fc, target_dir)
        except Exception:
            sm = {'predicted_pace': '[FILL]', 'expected_pace': '[FILL]',
                  'leaders': [], 'on_pace': [], 'mid_pack': [], 'closers': [],
                  'track_bias': '[FILL]', 'tactical_nodes': '[FILL]',
                  'collapse_point': '[FILL]'}

        init_json = {
            "race_analysis": {"race_number": r, "race_class": race_class,
                              "distance": race_dist, "speed_map": sm},
            "horses": {}
        }
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(init_json, f, ensure_ascii=False, indent=2)
        _log(f"   ✅ Created Race_{r}_Logic.json ({race_class} / {race_dist})")

    # Ensure speed map
    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    sm = logic_data.get('race_analysis', {}).get('speed_map', {})
    missing_sm = [k for k in ['expected_pace', 'track_bias', 'tactical_nodes', 'collapse_point']
                  if not sm.get(k) or sm.get(k) == '[FILL]']
    if missing_sm:
        with open(facts_file, 'r', encoding='utf-8') as f:
            fc = f.read()
        auto_sm = fns["auto_speed_map"](fc, target_dir)
        logic_data.setdefault('race_analysis', {})['speed_map'] = auto_sm
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(logic_data, f, ensure_ascii=False, indent=2)
        _log(f"   ✅ Speed Map injected ({auto_sm.get('expected_pace', '?')})")

    # Pre-race dummy scan
    scan = fns["scan_quality"](json_file)
    if scan['action'] == 'PURGE_ALL':
        _log(f"🚨 Race {r} dummy content detected — purging all horses")
        with open(json_file, 'r', encoding='utf-8') as f:
            d = json.load(f)
        d['horses'] = {}
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    # Get horse list + pending
    all_horses = fns["get_horse_numbers"](facts_file)
    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    horses_dict = logic_data.get('horses', {})

    validated = []
    pending = []
    for h in all_horses:
        entry = horses_dict.get(str(h), {})
        if not entry:
            pending.append(h)
            continue
        h_json = json.dumps({k: v for k, v in entry.items()
                             if k not in ('base_rating', 'final_rating')}, ensure_ascii=False)
        if '[FILL]' in h_json:
            pending.append(h)
            continue
        errors = fns["validate_firewalls"](h, entry, horses_dict, all_horses, json_file)
        if errors:
            horses_dict[str(h)]['core_logic'] = '[FILL]'
            logic_data['horses'] = horses_dict
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(logic_data, f, ensure_ascii=False, indent=2)
            pending.append(h)
        else:
            validated.append(h)

    if validated:
        _log(f"   ✅ {len(validated)}/{len(all_horses)} horses pre-validated")

    races = dict(state.get("races", {}))
    races[str(r)] = {
        "race_num": r, "horses_total": len(all_horses),
        "horses_done": validated, "horses_pending": pending,
        "speed_map_ready": True, "verdict_done": False,
        "compiled": False, "mc_done": False, "qa_strikes": 0,
        "qa_passed": False, "stage": "ANALYSING",
    }

    first_horse = pending[0] if pending else None
    _log(f"\n{'='*60}")
    _log(f"📋 Race {r}: {len(pending)} horses pending")
    _log(f"{'='*60}")

    return {
        "races": races,
        "current_horse": first_horse,
        "completed_in_session": 0,
        "log": [f"setup_race_{r}: {len(pending)} pending"],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: generate_workcard
# ═══════════════════════════════════════════════════════════════
def node_generate_workcard(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    h = state["current_horse"]
    date_prefix = state["date_prefix"]
    short_prefix = state["short_prefix"]

    facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")

    # Generate skeleton
    skeleton_script = fns["skeleton_script"]
    subprocess.run([PYTHON, skeleton_script, facts_file, str(r), str(h)],
                   capture_output=True, text=True)

    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    with open(facts_file, 'r', encoding='utf-8') as f:
        facts_content = f.read()

    sm = logic_data.get('race_analysis', {}).get('speed_map', {})
    sm_pace = sm.get('expected_pace', sm.get('predicted_pace', 'N/A'))
    sm_bias = sm.get('track_bias', 'N/A')

    races = state.get("races", {})
    race_state = races.get(str(r), {})
    pending = race_state.get("horses_pending", [])
    idx = pending.index(h) if h in pending else 0

    runtime_dir = os.path.join(target_dir, ".runtime")
    os.makedirs(runtime_dir, exist_ok=True)

    fns["generate_workcard"](h, facts_content, logic_data, runtime_dir,
                             sm_pace, sm_bias, horse_idx=idx, total_horses=len(pending))

    h_entry = logic_data.get('horses', {}).get(str(h), {})
    h_name = h_entry.get('horse_name', '?')
    _log(f"\n👉 LLM: Please analyse Horse #{h} ({h_name})")
    _log(f"   📋 WorkCard: .runtime/Horse_{h}_WorkCard.md")
    _log(f"   ✏️ Target: Race_{r}_Logic.json → horses.{h}")

    return {"log": [f"workcard_generated: horse_{h}"]}


# ═══════════════════════════════════════════════════════════════
# NODE: watch_and_validate
# ═══════════════════════════════════════════════════════════════
def node_watch_and_validate(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    h = state["current_horse"]

    facts_file = os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{state['short_prefix']} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    all_horses = fns["get_horse_numbers"](facts_file)

    result = fns["watch_horse"](json_file, h,
                                validate_fn=fns["validate_firewalls"],
                                all_horses=all_horses,
                                poll_interval=3, timeout_minutes=10)

    races = dict(state.get("races", {}))
    race_state = dict(races.get(str(r), {}))
    done = list(race_state.get("horses_done", []))
    pending = list(race_state.get("horses_pending", []))
    completed = state.get("completed_in_session", 0)

    if result:
        done.append(h)
        if h in pending:
            pending.remove(h)
        completed += 1

        # Lock validated horse
        with open(json_file, 'r', encoding='utf-8') as f:
            lock_data = json.load(f)
        if str(h) in lock_data.get('horses', {}):
            lock_data['horses'][str(h)]['_validated'] = True
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(lock_data, f, ensure_ascii=False, indent=2)

        fns["print_summary"](result, h)
        _log(f"   ✅ Horse #{h} validated [{completed}/{len(pending)+completed}]")
        h_result = "pass"
    else:
        _log(f"   ⏰ Horse #{h} timeout/interrupted")
        h_result = "timeout"

    race_state["horses_done"] = done
    race_state["horses_pending"] = pending
    races[str(r)] = race_state

    next_horse = pending[0] if pending else None

    return {
        "races": races,
        "current_horse": next_horse,
        "current_horse_result": h_result,
        "completed_in_session": completed,
        "log": [f"horse_{h}={h_result}"],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: batch_qa
# ═══════════════════════════════════════════════════════════════
def node_batch_qa(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    completed = state.get("completed_in_session", 0)

    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    races = dict(state.get("races", {}))
    race_state = dict(races.get(str(r), {}))
    pending = list(race_state.get("horses_pending", []))
    done = list(race_state.get("horses_done", []))

    # Get last 3 completed horses for batch check
    batch_nums = done[-3:] if len(done) >= 3 else done

    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    horses_dict = data.get('horses', {})

    errors = fns["validate_batch"](batch_nums, horses_dict, json_file)
    if errors:
        _log(f"   ⚠️ Batch QA ({batch_nums}) failed:")
        for e in errors:
            _log(f"      ❌ {e}")
        # Reset batch horses
        for bh in batch_nums:
            if str(bh) in horses_dict:
                horses_dict[str(bh)]['core_logic'] = '[FILL]'
                horses_dict[str(bh)]['_validated'] = False
                if bh in done:
                    done.remove(bh)
                if bh not in pending:
                    pending.append(bh)
        data['horses'] = horses_dict
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        pending.sort()
        _log(f"   🔄 Batch reset — will re-analyse")
    else:
        _log(f"   ✅ Batch QA passed ({batch_nums})")

    race_state["horses_done"] = done
    race_state["horses_pending"] = pending
    races[str(r)] = race_state

    next_horse = pending[0] if pending else None

    return {
        "races": races,
        "current_horse": next_horse,
        "log": [f"batch_qa: {'FAIL' if errors else 'PASS'}"],
    }


# ═══════════════════════════════════════════════════════════════
# NODE: global_qa
# ═══════════════════════════════════════════════════════════════
def node_global_qa(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]

    facts_file = os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{state['short_prefix']} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    all_horses = fns["get_horse_numbers"](facts_file)

    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    horses_dict = logic_data.get('horses', {})

    validate_global_fn = fns.get("validate_global")
    errors = validate_global_fn(horses_dict, all_horses, json_file) if validate_global_fn else []
    if errors:
        for e in errors:
            _log(f"🚨 {e}")
        return {"should_stop": True, "stop_reason": "WALL-015 global check failed",
                "log": ["global_qa=FAIL"]}

    _log(f"   ✅ WALL-015 Global QA passed")
    return {"log": ["global_qa=PASS"]}


# ═══════════════════════════════════════════════════════════════
# NODE: compute_verdict
# ═══════════════════════════════════════════════════════════════
def node_compute_verdict(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]

    facts_file = os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{state['short_prefix']} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")

    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)

    if fns["verdict_check"](logic_data):
        _log(f"⚙️ Auto-Verdict: Computing Top 4 for Race {r}...")
        verdict = fns["auto_verdict"](logic_data, facts_file)
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(logic_data, f, ensure_ascii=False, indent=2)
        t4 = ', '.join([f"#{v['horse_number']} {v['horse_name']} ({v['grade']})"
                        for v in verdict['top4']])
        _log(f"   ✅ Top 4: {t4}")

    return {"log": [f"verdict_race_{r}"]}


# ═══════════════════════════════════════════════════════════════
# NODE: compile_analysis
# ═══════════════════════════════════════════════════════════════
def node_compile_analysis(state):
    target_dir = state["target_dir"]
    r = state["current_race"]
    short_prefix = state["short_prefix"]
    date_prefix = state["date_prefix"]

    facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
    if not os.path.exists(facts_file):
        facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")

    fns = _get_domain_fns(state.get("domain", "au"))
    compile_script = fns["compile_script"]
    _log(f"⚙️ Compiling Race {r}...")
    res = subprocess.run([PYTHON, compile_script, facts_file, json_file, "--output", an_file])
    if res.returncode != 0:
        return {"should_stop": True, "stop_reason": f"Compile failed Race {r}",
                "log": [f"compile_race_{r}=FAIL"]}

    _log(f"   ✅ Compiled → {os.path.basename(an_file)}")
    return {"log": [f"compile_race_{r}=OK"]}


# ═══════════════════════════════════════════════════════════════
# NODE: run_monte_carlo
# ═══════════════════════════════════════════════════════════════
def node_run_monte_carlo(state):
    target_dir = state["target_dir"]
    r = state["current_race"]

    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    mc_out = os.path.join(target_dir, f"Race_{r}_MC_Results.json")

    # Find mc_simulator.py
    search_dir = os.path.abspath(_AU_SCRIPTS)
    mc_script = None
    for _ in range(8):
        candidate = os.path.join(search_dir, "mc_simulator.py")
        if os.path.exists(candidate):
            mc_script = candidate
            break
        parent = os.path.dirname(search_dir)
        if parent == search_dir:
            break
        search_dir = parent

    domain = state.get("domain", "au")
    platform = domain if domain != "hkjc" else "hkjc"
    if mc_script and os.path.exists(mc_script):
        _log(f"🎲 Running Monte Carlo for Race {r}...")
        res = subprocess.run([PYTHON, mc_script, "--input", json_file, "--platform", platform],
                             capture_output=True, text=True)
        if res.returncode == 0 and os.path.exists(mc_out):
            _log(f"   ✅ MC Results → Race_{r}_MC_Results.json")
        else:
            _log(f"   ⚠️ MC failed (non-blocking): {res.stderr[:200]}")
    else:
        _log(f"   ⚠️ mc_simulator.py not found")

    return {"log": [f"mc_race_{r}"]}


# ═══════════════════════════════════════════════════════════════
# NODE: final_qa
# ═══════════════════════════════════════════════════════════════
def node_final_qa(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    short_prefix = state["short_prefix"]

    an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")

    qa_script = os.path.join(_SCRIPT_DIR, "completion_gate_v2.py")
    domain = state.get("domain", "au")
    _log(f"🛡️ Running QA for Race {r}...")
    res = subprocess.run([PYTHON, qa_script, an_file, "--domain", domain],
                         capture_output=True, text=True)

    races = dict(state.get("races", {}))
    race_state = dict(races.get(str(r), {}))
    strikes = race_state.get("qa_strikes", 0)

    if res.returncode != 0:
        strikes += 1
        _log(f"❌ Race {r} QA failed! Strike {strikes}/3")
        if res.stdout:
            for line in res.stdout.strip().split('\n')[-5:]:
                _log(f"   {line}")

        # Generate diagnosis
        runtime_dir = os.path.join(target_dir, '.runtime')
        fns["qa_diagnosis"](r, strikes, res.stdout, res.stderr,
                           json_file, an_file, runtime_dir)

        race_state["qa_strikes"] = strikes
        race_state["qa_passed"] = False
        races[str(r)] = race_state

        if strikes >= 3:
            return {"races": races, "should_stop": True,
                    "stop_reason": f"Race {r} 3-strike stop",
                    "log": [f"qa_race_{r}=STRIKE_{strikes}"]}
        return {"races": races, "should_stop": True,
                "stop_reason": f"Race {r} QA fail strike {strikes}",
                "log": [f"qa_race_{r}=STRIKE_{strikes}"]}
    else:
        _log(f"\n{'🎉'*10}")
        _log(f"✅ Race {r} QA passed!")
        _log(f"{'🎉'*10}")
        race_state["qa_strikes"] = 0
        race_state["qa_passed"] = True
        race_state["stage"] = "COMPLETE"
        races[str(r)] = race_state
        return {"races": races, "log": [f"qa_race_{r}=PASS"]}


# ═══════════════════════════════════════════════════════════════
# NODE: advance_race
# ═══════════════════════════════════════════════════════════════
def node_advance_race(state):
    r = state["current_race"]
    total = state["total_races"]
    if r < total:
        next_r = r + 1
        _log(f"\n🔄 Race {r} complete! Advancing to Race {next_r}...")
        return {"current_race": next_r, "log": [f"advance_to_race_{next_r}"]}
    else:
        _log(f"\n🏆 All {total} races complete!")
        return {"overall_stage": "COMPLETE", "log": ["all_races_complete"]}


# ═══════════════════════════════════════════════════════════════
# NODE: generate_reports
# ═══════════════════════════════════════════════════════════════
def node_generate_reports(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    _log("🏆 Generating final reports...")
    try:
        subprocess.run([PYTHON, fns["reports_script"], target_dir], check=True)
        _log("✅ Reports generated")
    except subprocess.CalledProcessError:
        _log("⚠️ Report generation failed (non-blocking)")
    return {"overall_stage": "COMPLETE", "log": ["reports_done"]}
