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
PYTHON = sys.executable

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_AU_SCRIPTS = os.path.join(_SCRIPT_DIR, '..', 'skills', 'au_racing', 'au_wong_choi', 'scripts')
_HKJC_SCRIPTS = os.path.join(_SCRIPT_DIR, '..', 'skills', 'hkjc_racing', 'hkjc_wong_choi', 'scripts')
sys.path.insert(0, os.path.abspath(_AU_SCRIPTS))
sys.path.insert(0, os.path.abspath(_HKJC_SCRIPTS))
sys.path.insert(0, os.path.abspath(_SCRIPT_DIR))

from racing_agent_runner import invoke_agent, format_agent_result
from racing_session_manager import persist_graph_state

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
            "skeleton_script": os.path.join(os.path.abspath(_HKJC_SCRIPTS), "create_hkjc_logic_skeleton.py"),
            "trackwork_script": os.path.join(os.path.abspath(_SCRIPT_DIR), "..", "skills", "hkjc_racing", "hkjc_race_extractor", "scripts", "extract_trackwork.py"),
            "compile_script": os.path.join(os.path.abspath(_HKJC_SCRIPTS), "compile_analysis_template_hkjc.py"),
            "reports_script": os.path.join(os.path.abspath(_HKJC_SCRIPTS), "generate_hkjc_reports.py"),
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
            "skeleton_script": os.path.join(os.path.abspath(_AU_SCRIPTS), "create_au_logic_skeleton.py"),
            "trackwork_script": None,
            "compile_script": os.path.join(os.path.abspath(_AU_SCRIPTS), "compile_analysis_template.py"),
            "reports_script": os.path.join(os.path.abspath(_AU_SCRIPTS), "generate_reports.py"),
            "context_injection": ao.print_context_injection_au,
            "discover_races": ao.discover_total_races,
        }
    
    _DOMAIN_FN[domain] = fns
    return fns


def _log(msg):
    print(msg)
    return msg


def _watch_poll_interval() -> float:
    raw = os.environ.get("RACING_WATCH_POLL_INTERVAL", "0.5").strip()
    try:
        return max(0.1, float(raw))
    except ValueError:
        return 0.5


def _persist_node_state(state, updates):
    """Persist best-effort node progress without changing LangGraph updates."""
    target_dir = state.get("target_dir") if isinstance(state, dict) else None
    if not target_dir:
        return updates

    merged = dict(state)
    merged.update(updates)
    if isinstance(state.get("log"), list) and isinstance(updates.get("log"), list):
        merged["log"] = state.get("log", []) + updates.get("log", [])

    try:
        persist_graph_state(target_dir, merged)
    except Exception as exc:
        _log(f"⚠️ Session persist failed: {exc}")
    return updates


def _speed_map_ready(sm: dict, domain: str):
    """Check speed map readiness with domain-aware pace key handling.
    Returns (ready: bool, issues: list[str]).
    """
    issues = []
    if domain == "hkjc":
        pace = sm.get("predicted_pace") or sm.get("expected_pace")
    else:
        pace = sm.get("expected_pace") or sm.get("predicted_pace")
    if not pace or pace == "[FILL]":
        issues.append("pace")
    for key in ["track_bias", "tactical_nodes", "collapse_point"]:
        if not sm.get(key) or sm.get(key) == "[FILL]":
            issues.append(key)
    return len(issues) == 0, issues


def _find_trackwork_files(target_dir, total_races):
    """Find per-race HKJC trackwork files without Race 1 / Race 10 collisions."""
    try:
        files = os.listdir(target_dir)
    except OSError:
        return {}, list(range(1, int(total_races or 0) + 1))

    matched = {}
    total = int(total_races or 0)
    for r in range(1, total + 1):
        patterns = [
            rf"Race\s*0?{r}(?!\d).*晨操\.json$",
            rf"Race_0?{r}(?!\d).*晨操\.json$",
            rf".*Race\s*0?{r}(?!\d).*Trackwork.*\.json$",
            rf".*Race_0?{r}(?!\d).*Trackwork.*\.json$",
        ]
        race_matches = [
            f for f in files
            if any(re.search(p, f, re.IGNORECASE) for p in patterns)
        ]
        if race_matches:
            matched[r] = race_matches

    missing_races = sorted(set(range(1, total + 1)) - set(matched.keys()))
    return matched, missing_races


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
    updates = {"raw_data_ready": ready, "log": [f"raw_data_ready={ready}"]}
    return _persist_node_state(state, updates)


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
    updates = {"intelligence_ready": ok, "log": [f"intel_ready={ok}"]}
    return _persist_node_state(state, updates)


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
            if state.get("domain", "au") == "hkjc":
                script_path = os.path.join(os.path.abspath(_SCRIPT_DIR), "inject_hkjc_fact_anchors.py")
                out_path = fg.replace("賽績.md", "Facts.md")
                cmd = [PYTHON, script_path, fg, "--output", out_path, "--venue", venue, "--race-num", str(r)]
            else:
                script_path = os.path.join(os.path.abspath(_SCRIPT_DIR), "inject_fact_anchors.py")
                cmd = [PYTHON, script_path, rc, fg,
                       "--max-display", "5", "--venue", venue]
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                _log(f"   ⚠️ Facts generation failed for Race {r} (non-blocking): {e}")

    if all_done:
        _log("✅ All Facts.md already exist")
    else:
        _log("✅ Facts generation complete")
    updates = {"facts_ready": True, "log": ["facts_ready=True"]}
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: extract_trackwork
# ═══════════════════════════════════════════════════════════════
def node_extract_trackwork(state):
    """Extract and verify HKJC trackwork digest after Facts generation."""
    domain = state.get("domain", "au")
    required = bool(state.get("trackwork_required", domain == "hkjc"))
    allow_missing = bool(state.get("allow_missing_trackwork", False))

    if domain != "hkjc":
        updates = {
            "trackwork_ready": False,
            "trackwork_status": "not_required",
            "log": ["trackwork=not_required"],
        }
        return _persist_node_state(state, updates)

    fns = _get_domain_fns(domain)
    script = fns.get("trackwork_script")
    target_dir = state["target_dir"]
    total_races = int(state.get("total_races", 0) or 0)

    if not script or not os.path.exists(script):
        if required and not allow_missing:
            updates = {
                "trackwork_ready": False,
                "trackwork_status": "missing_script",
                "should_stop": True,
                "stop_reason": "HKJC trackwork extraction script is missing. Analysis stopped before setup_race.",
                "log": ["trackwork=missing_script"],
            }
            return _persist_node_state(state, updates)
        updates = {
            "trackwork_ready": False,
            "trackwork_status": "missing_script",
            "log": ["trackwork=missing_script_allow_continue"],
        }
        return _persist_node_state(state, updates)

    matched, missing_races = _find_trackwork_files(target_dir, total_races)
    if total_races and not missing_races:
        _log(f"✅ Trackwork already exists ({len(matched)}/{total_races})")
        updates = {
            "trackwork_ready": True,
            "trackwork_status": "cached",
            "log": ["trackwork=cached"],
        }
        return _persist_node_state(state, updates)

    date_prefix = state.get("date_prefix", "")
    iso_prefix = ""
    m_dir_date = re.search(r'(\d{4})-(\d{2})-(\d{2})', os.path.basename(target_dir))
    if m_dir_date:
        iso_prefix = f"{m_dir_date.group(1)}-{m_dir_date.group(2)}-{m_dir_date.group(3)}"

    url = state.get("url")
    venue = state.get("venue", "")
    venue_norm = venue
    if str(venue).lower().startswith("happy") or "跑馬地" in str(venue):
        venue_norm = "HV"
    elif str(venue).lower().startswith("sha") or "沙田" in str(venue):
        venue_norm = "ST"
    if iso_prefix:
        racedate = iso_prefix.replace("-", "/")
    else:
        racedate = date_prefix.replace("-", "/") if date_prefix else ""
    races_arg = f"1-{total_races}" if total_races else "1"
    cmd = [PYTHON, script, "--output_dir", target_dir, "--races", races_arg, "--fail-soft"]
    if url:
        cmd.extend(["--base_url", url])
    else:
        cmd.extend(["--racedate", racedate, "--racecourse", venue_norm])

    _log("🏇 Extracting HKJC trackwork digest (fail-soft)...")
    res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
    if res.stdout.strip():
        for line in res.stdout.strip().splitlines()[-5:]:
            _log(f"   {line}")
    if res.returncode != 0:
        err = (res.stderr or res.stdout or "").strip()[:300]
        if required and not allow_missing:
            reason = f"HKJC trackwork extraction failed before analysis: {err}"
            _log(f"   🚨 {reason}")
            updates = {
                "trackwork_ready": False,
                "trackwork_status": "failed",
                "should_stop": True,
                "stop_reason": reason,
                "log": ["trackwork=failed"],
            }
            return _persist_node_state(state, updates)
        _log(f"   ⚠️ Trackwork extraction failed, continuing by explicit override: {err}")
        updates = {
            "trackwork_ready": False,
            "trackwork_status": "failed_allowed",
            "log": ["trackwork=failed_allowed"],
        }
        return _persist_node_state(state, updates)

    matched, missing_races = _find_trackwork_files(target_dir, total_races)
    if missing_races:
        if required and not allow_missing:
            reason = f"HKJC trackwork missing for races {missing_races}. Analysis stopped before setup_race."
            _log(f"   🚨 {reason}")
            updates = {
                "trackwork_ready": False,
                "trackwork_status": "missing",
                "should_stop": True,
                "stop_reason": reason,
                "log": ["trackwork=missing"],
            }
            return _persist_node_state(state, updates)
        _log(f"   ⚠️ Trackwork missing for races {missing_races}, continuing by explicit override")
        updates = {
            "trackwork_ready": False,
            "trackwork_status": "missing_allowed",
            "log": ["trackwork=missing_allowed"],
        }
        return _persist_node_state(state, updates)

    _log(f"   ✅ Trackwork status: ok ({len(matched)} races)")
    updates = {"trackwork_ready": True, "trackwork_status": "ok", "log": ["trackwork=ok"]}
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: setup_race
# ═══════════════════════════════════════════════════════════════
def node_setup_race(state):
    """Set up Logic.json skeleton + Speed Map for current_race."""
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    date_prefix = state["date_prefix"]
    domain = state.get("domain", "au")
    short_prefix = state["short_prefix"]

    facts_files = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, facts_files[0]) if facts_files else os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
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

    # Ensure speed map (domain-aware pace key)
    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    sm = logic_data.get('race_analysis', {}).get('speed_map', {})
    if domain == "au" and sm.get("predicted_pace") and not sm.get("expected_pace"):
        sm["expected_pace"] = sm.get("predicted_pace")
        logic_data.setdefault("race_analysis", {})["speed_map"] = sm
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(logic_data, f, ensure_ascii=False, indent=2)
    sm_ready, sm_issues = _speed_map_ready(sm, domain)
    if not sm_ready:
        _log(f"   ⚠️ Speed Map incomplete ({sm_issues}), re-injecting...")
        with open(facts_file, 'r', encoding='utf-8') as f:
            fc = f.read()
        auto_sm = fns["auto_speed_map"](fc, target_dir)
        logic_data.setdefault('race_analysis', {})['speed_map'] = auto_sm
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(logic_data, f, ensure_ascii=False, indent=2)
        pace_key = 'predicted_pace' if domain == 'hkjc' else 'expected_pace'
        _log(f"   ✅ Speed Map injected (pace={auto_sm.get(pace_key, auto_sm.get('expected_pace', '?'))})")

    # SIP-AU-022: Speed Map Coverage Validation
    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)
    sm = logic_data.get('race_analysis', {}).get('speed_map', {})
    sm_all_nums = set()
    for grp in ('leaders', 'on_pace', 'mid_pack', 'closers'):
        sm_all_nums.update(sm.get(grp, []))
    all_horses_check = fns["get_horse_numbers"](facts_file)
    if all_horses_check:
        sm_coverage = len(sm_all_nums & set(all_horses_check)) / len(all_horses_check)
        if sm_coverage < 0.9:
            _log(f"   ⚠️ SIP-AU-022: Speed Map 覆蓋率 {sm_coverage:.0%} (<90%)")
            _log(f"      缺失馬匹: {sorted(set(all_horses_check) - sm_all_nums)}")
            _log(f"      → 請確保所有參賽馬匹喺 speed_map 有位置歸類")
        else:
            _log(f"   ✅ SIP-AU-022: Speed Map 覆蓋率 {sm_coverage:.0%}")

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

    updates = {
        "races": races,
        "current_horse": first_horse,
        "completed_in_session": 0,
        "should_stop": False,
        "stop_reason": "",
        "waiting_for_agent": False,
        "log": [f"setup_race_{r}: {len(pending)} pending"],
    }
    return _persist_node_state(state, updates)


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

    _ffs = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, _ffs[0]) if _ffs else os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")

    # Generate skeleton — Task 4: capture result and validate
    skeleton_script = fns["skeleton_script"]
    skel_res = subprocess.run([PYTHON, skeleton_script, facts_file, str(r), str(h)],
                              capture_output=True, text=True, encoding='utf-8')
    if skel_res.returncode != 0:
        err = (skel_res.stderr or skel_res.stdout or "").strip()[:500]
        reason = f"Skeleton generation failed for Race {r} Horse {h}: {err}"
        _log(f"🚨 {reason}")
        updates = {"should_stop": True, "stop_reason": reason,
                   "log": [f"skeleton_fail: race_{r}_horse_{h}"]}
        return _persist_node_state(state, updates)

    with open(json_file, 'r', encoding='utf-8') as f:
        logic_data = json.load(f)

    # Task 4: Verify horse entry exists after skeleton generation
    h_entry = logic_data.get('horses', {}).get(str(h), {})
    h_name = h_entry.get('horse_name', '?')
    if not h_entry or h_name in ('?', '未知', ''):
        reason = f"Skeleton produced no valid entry for Race {r} Horse {h} (horse_name='{h_name}')"
        _log(f"🚨 {reason}")
        updates = {"should_stop": True, "stop_reason": reason,
                   "log": [f"skeleton_empty: race_{r}_horse_{h}"]}
        return _persist_node_state(state, updates)

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

    domain = state.get("domain", "au")
    if domain == "hkjc":
        fns["generate_workcard"](h, facts_content, logic_data, runtime_dir,
                                 sm_pace, sm_bias, horse_idx=idx, total_horses=len(pending),
                                 race_num=r)
    else:
        fns["generate_workcard"](h, facts_content, logic_data, runtime_dir,
                                 sm_pace, sm_bias, horse_idx=idx, total_horses=len(pending))

    # ── Career tag injection into WorkCard (V2.2) ──
    career_tag_m = None
    block_m = re.search(
        rf'(?:\[#{h}\]|### 馬匹 #{h}\b|### 馬號 {h}\b).*?'
        rf'(?=(?:\[#\d+\]|### 馬匹 #\d+\b|### 馬號 \d+\b)|\Z)',
        facts_content,
        re.DOTALL,
    )
    search_scope = block_m.group(0) if block_m else facts_content
    career_tag_m = re.search(
        r'生涯標記:\s*`(DEBUT|IMPORTED_DEBUT|ESTABLISHED)`',
        search_scope,
    )

    if career_tag_m:
        ctag = career_tag_m.group(1)
        if ctag in ('DEBUT', 'IMPORTED_DEBUT'):
            wc_path = os.path.join(runtime_dir, f"Horse_{h}_WorkCard.md")
            if os.path.exists(wc_path):
                with open(wc_path, 'r', encoding='utf-8') as f:
                    wc_content = f.read()
                if f"[CAREER_TAG: {ctag}]" not in wc_content:
                    tag_header = (
                        f"\n> ⚠️ **[CAREER_TAG: {ctag}]** — "
                        f"{'初出馬：請載入 debut_guide 並按初出維度判定。Rating Cap A-。' if ctag == 'DEBUT' else ''}"
                        f"{'進口馬初出：請載入 debut_guide (Section B)。' if ctag == 'IMPORTED_DEBUT' else ''}"
                        f"\n\n"
                    )
                    with open(wc_path, 'w', encoding='utf-8') as f:
                        f.write(tag_header + wc_content)
                    _log(f"   🏷️ Career tag [{ctag}] injected into WorkCard")

    # ── Task 6: Autopilot agent invocation ──
    if state.get("autopilot"):
        wc_path = os.path.join(runtime_dir, f"Horse_{h}_WorkCard.md")
        agent_result = invoke_agent(
            domain=domain,
            target_dir=target_dir,
            race=r,
            horse=h,
            workcard_path=wc_path,
            logic_json_path=json_file,
        )

        _log(f"   🤖 Autopilot: {format_agent_result(agent_result)}")

        if agent_result["status"] == "missing_command":
            updates = {
                "should_stop": True,
                "stop_reason": "Autopilot requested but RACING_AGENT_CMD is not set.",
                "log": ["autopilot_no_cmd"],
            }
            return _persist_node_state(state, updates)

        if agent_result["status"] == "timeout":
            updates = {
                "should_stop": True,
                "waiting_for_agent": True,
                "current_horse_result": "waiting",
                "stop_reason": f"Waiting for agent to complete Race {r} Horse {h}",
                "log": [f"autopilot_timeout: race_{r}_horse_{h}"],
            }
            return _persist_node_state(state, updates)

        if agent_result["status"] == "failed":
            detail = agent_result.get("stderr_tail") or agent_result.get("stdout_tail") or "unknown error"
            updates = {
                "should_stop": True,
                "stop_reason": f"Autopilot failed for Race {r} Horse {h}: {detail}",
                "log": [f"autopilot_failed: race_{r}_horse_{h}"],
            }
            return _persist_node_state(state, updates)

    _log(f"\n👉 LLM: Please analyse Horse #{h} ({h_name})")
    _log(f"   📋 WorkCard: .runtime/Horse_{h}_WorkCard.md")
    _log(f"   ✏️ Target: Race_{r}_Logic.json → horses.{h}")
    _log(f"   🔴 REMINDER: Read WorkCard → Fill JSON → check_command_status → next horse. DO NOT stop or report progress. Python controls flow.")

    updates = {"log": [f"workcard_generated: horse_{h}"]}
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: watch_and_validate
# ═══════════════════════════════════════════════════════════════
def node_watch_and_validate(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]
    h = state["current_horse"]

    _ffs = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, _ffs[0]) if _ffs else os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    all_horses = fns["get_horse_numbers"](facts_file)

    result = fns["watch_horse"](json_file, h,
                                validate_fn=fns["validate_firewalls"],
                                all_horses=all_horses,
                                poll_interval=_watch_poll_interval(), timeout_minutes=60)

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
        # Task 5: Resumable timeout — don't mark as fatal
        _log(f"   ⏰ Horse #{h} timeout — waiting for agent to complete")
        h_result = "waiting"

    race_state["horses_done"] = done
    race_state["horses_pending"] = pending
    races[str(r)] = race_state

    next_horse = h if h_result == "waiting" else (pending[0] if pending else None)

    updates = {
        "races": races,
        "current_horse": next_horse,
        "current_horse_result": h_result,
        "completed_in_session": completed,
        "log": [f"horse_{h}={h_result}"],
    }
    if h_result == "waiting":
        updates.update({
            "should_stop": True,
            "waiting_for_agent": True,
            "stop_reason": f"Waiting for agent to complete Race {r} Horse {h}",
        })
    return _persist_node_state(state, updates)


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

    updates = {
        "races": races,
        "current_horse": next_horse,
        "log": [f"batch_qa: {'FAIL' if errors else 'PASS'}"],
    }
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: global_qa
# ═══════════════════════════════════════════════════════════════
def node_global_qa(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]

    _ffs = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, _ffs[0]) if _ffs else os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
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
        updates = {"should_stop": True, "stop_reason": "WALL-015 global check failed",
                   "log": ["global_qa=FAIL"]}
        return _persist_node_state(state, updates)

    _log(f"   ✅ WALL-015 Global QA passed")
    updates = {"log": ["global_qa=PASS"]}
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: compute_verdict
# ═══════════════════════════════════════════════════════════════
def node_compute_verdict(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    r = state["current_race"]

    _ffs = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, _ffs[0]) if _ffs else os.path.join(target_dir, f"{state['date_prefix']} Race {r} Facts.md")
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

    updates = {"log": [f"verdict_race_{r}"]}
    return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: compile_analysis
# ═══════════════════════════════════════════════════════════════
def node_compile_analysis(state):
    target_dir = state["target_dir"]
    r = state["current_race"]
    short_prefix = state["short_prefix"]
    date_prefix = state["date_prefix"]
    domain = state.get("domain", "au")

    _ffs = [f for f in os.listdir(target_dir) if f.endswith(f"Race {r} Facts.md")]
    facts_file = os.path.join(target_dir, _ffs[0]) if _ffs else os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
    json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
    an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")

    fns = _get_domain_fns(domain)
    compile_script = fns["compile_script"]

    # Task 2: Preflight existence check
    if not os.path.exists(compile_script):
        reason = f"Compile script not found: {compile_script}"
        _log(f"🚨 {reason}")
        updates = {"should_stop": True, "stop_reason": reason,
                   "log": [f"compile_race_{r}=MISSING_SCRIPT"]}
        return _persist_node_state(state, updates)

    # ── V4.2: Schema validation gate (HKJC only) ──
    if domain == "hkjc":
        try:
            from validate_hkjc_logic_schema import validate_logic_json
            with open(json_file, 'r', encoding='utf-8') as f:
                logic_data = json.load(f)
            result = validate_logic_json(logic_data)
            if not result['pass']:
                error_summary = "; ".join(result['errors'][:5])
                reason = f"V4.2 schema validation failed for Race {r}: {error_summary}"
                _log(f"🚨 {reason}")
                for err in result['errors']:
                    _log(f"   ❌ {err}")
                updates = {"should_stop": True, "stop_reason": reason,
                           "log": [f"compile_race_{r}=SCHEMA_FAIL"]}
                return _persist_node_state(state, updates)
            _log(f"   ✅ V4.2 schema validation passed ({result['stats']['horses_passed']}/{result['stats']['horses_checked']} horses)")
        except ImportError:
            _log("   ⚠️ validate_hkjc_logic_schema not importable — skipping schema gate")

    _log(f"⚙️ Compiling Race {r}...")
    res = subprocess.run([PYTHON, compile_script, facts_file, json_file, "--output", an_file])
    if res.returncode != 0:
        updates = {"should_stop": True, "stop_reason": f"Compile failed Race {r}",
                   "log": [f"compile_race_{r}=FAIL"]}
        return _persist_node_state(state, updates)

    _log(f"   ✅ Compiled → {os.path.basename(an_file)}")
    updates = {"log": [f"compile_race_{r}=OK"]}
    return _persist_node_state(state, updates)


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
                             capture_output=True, text=True, encoding='utf-8')
        if res.returncode == 0 and os.path.exists(mc_out):
            _log(f"   ✅ MC Results → Race_{r}_MC_Results.json")
        else:
            _log(f"   ⚠️ MC failed (non-blocking): {res.stderr[:200]}")
    else:
        _log(f"   ⚠️ mc_simulator.py not found")

    updates = {"log": [f"mc_race_{r}"]}
    return _persist_node_state(state, updates)


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
                         capture_output=True, text=True, encoding='utf-8')

    races = dict(state.get("races", {}))
    race_state = dict(races.get(str(r), {}))

    # Task 7: Load persisted QA strikes
    qa_strikes_file = os.path.join(target_dir, ".qa_strikes.json")
    persisted_strikes = {}
    try:
        if os.path.exists(qa_strikes_file):
            with open(qa_strikes_file, 'r', encoding='utf-8') as f:
                persisted_strikes = json.load(f)
    except Exception:
        pass
    strike_key = f"race_{r}_qa" if domain == "hkjc" else str(r)
    strikes = persisted_strikes.get(strike_key, race_state.get("qa_strikes", 0))

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

        # Task 7: Persist strikes atomically
        persisted_strikes[strike_key] = strikes
        _tmp = qa_strikes_file + ".tmp"
        with open(_tmp, 'w', encoding='utf-8') as f:
            json.dump(persisted_strikes, f, indent=2)
        os.replace(_tmp, qa_strikes_file)

        if strikes >= 3:
            updates = {"races": races, "should_stop": True,
                       "stop_reason": f"Race {r} 3-strike stop",
                       "log": [f"qa_race_{r}=STRIKE_{strikes}"]}
            return _persist_node_state(state, updates)
        updates = {"races": races, "should_stop": True,
                   "stop_reason": f"Race {r} QA fail strike {strikes}",
                   "log": [f"qa_race_{r}=STRIKE_{strikes}"]}
        return _persist_node_state(state, updates)
    else:
        _log(f"\n{'🎉'*10}")
        _log(f"✅ Race {r} QA passed!")
        _log(f"{'🎉'*10}")
        race_state["qa_strikes"] = 0
        race_state["qa_passed"] = True
        race_state["stage"] = "COMPLETE"
        races[str(r)] = race_state

        # Task 7: Reset persisted strikes on pass
        persisted_strikes[strike_key] = 0
        _tmp = qa_strikes_file + ".tmp"
        with open(_tmp, 'w', encoding='utf-8') as f:
            json.dump(persisted_strikes, f, indent=2)
        os.replace(_tmp, qa_strikes_file)

        updates = {"races": races, "log": [f"qa_race_{r}=PASS"]}
        return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: advance_race
# ═══════════════════════════════════════════════════════════════
def node_advance_race(state):
    """Advance to next race with full horse-level state reset."""
    r = state["current_race"]
    total = state["total_races"]
    if r < total:
        next_r = r + 1
        _log(f"\n🔄 Race {r} complete! Advancing to Race {next_r}...")
        updates = {
            "current_race": next_r,
            "current_horse": None,
            "current_horse_result": None,
            "completed_in_session": 0,
            "should_stop": False,
            "stop_reason": "",
            "overall_stage": "ANALYSING",
            "log": [f"advance_to_race_{next_r}"],
        }
        return _persist_node_state(state, updates)
    else:
        _log(f"\n🏆 All {total} races complete!")
        updates = {"overall_stage": "COMPLETE", "log": ["all_races_complete"]}
        return _persist_node_state(state, updates)


# ═══════════════════════════════════════════════════════════════
# NODE: generate_reports
# ═══════════════════════════════════════════════════════════════
def node_generate_reports(state):
    fns = _get_domain_fns(state.get("domain", "au"))
    target_dir = state["target_dir"]
    _log("🏆 Generating final reports...")
    try:
        cmd = [PYTHON, fns["reports_script"], target_dir]
        if state.get("domain", "au") == "hkjc":
            cmd = [PYTHON, fns["reports_script"], "--target_dir", target_dir]
        subprocess.run(cmd, check=True)
        _log("✅ Reports generated")
    except subprocess.CalledProcessError:
        _log("⚠️ Report generation failed (non-blocking)")
    updates = {"overall_stage": "COMPLETE", "log": ["reports_done"]}
    return _persist_node_state(state, updates)
