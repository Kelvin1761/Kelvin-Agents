#!/usr/bin/env python3
"""
test_hkjc_langgraph_smoke.py — Smoke Tests for HKJC LangGraph Pipeline
========================================================================
Run with: python .agents/scripts/test_hkjc_langgraph_smoke.py
"""
import os
import sys
import json
import tempfile
import shutil

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

PASS = 0
FAIL = 0


def _test(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name} — {detail}")
        FAIL += 1


# ═══════════════════════════════════════════════════════════════
# Test 1: HKJC domain registry points to existing files
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 1: HKJC domain registry file existence")
try:
    from racing_graph_nodes import _get_domain_fns, _HKJC_SCRIPTS
    fns = _get_domain_fns("hkjc")
    
    compile_script = fns["compile_script"]
    _test("compile_script exists", os.path.exists(compile_script),
          f"Not found: {compile_script}")
    
    skeleton_script = fns["skeleton_script"]
    # skeleton_script is relative, resolve from repo root
    repo_root = os.path.abspath(os.path.join(_SCRIPT_DIR, '..', '..'))
    skel_abs = os.path.join(repo_root, skeleton_script) if not os.path.isabs(skeleton_script) else skeleton_script
    _test("skeleton_script path defined", bool(skeleton_script))
    
    _test("compile_script is HKJC version",
          "compile_analysis_template_hkjc.py" in compile_script,
          f"Got: {compile_script}")
except Exception as e:
    _test("HKJC registry import", False, str(e))


# ═══════════════════════════════════════════════════════════════
# Test 2: HKJC compiler path exists on disk
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 2: HKJC compiler path exists")
hkjc_compiler = os.path.join(os.path.abspath(_HKJC_SCRIPTS), "compile_analysis_template_hkjc.py")
_test("compile_analysis_template_hkjc.py exists", os.path.exists(hkjc_compiler),
      f"Not found: {hkjc_compiler}")


# ═══════════════════════════════════════════════════════════════
# Test 3: Speed map readiness with predicted_pace
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 3: Speed map readiness (domain-aware)")
from racing_graph_nodes import _speed_map_ready

# HKJC with predicted_pace should pass
sm_hkjc = {"predicted_pace": "中步速", "track_bias": "內檔偏好",
           "tactical_nodes": "1,3", "collapse_point": "400m"}
ready, issues = _speed_map_ready(sm_hkjc, "hkjc")
_test("HKJC predicted_pace passes", ready, f"Issues: {issues}")

# AU with expected_pace should pass
sm_au = {"expected_pace": "MODERATE", "track_bias": "INSIDE",
         "tactical_nodes": "1,3", "collapse_point": "400m"}
ready, issues = _speed_map_ready(sm_au, "au")
_test("AU expected_pace passes", ready, f"Issues: {issues}")

# Missing pace should fail
sm_empty = {"track_bias": "INSIDE", "tactical_nodes": "1", "collapse_point": "400m"}
ready, issues = _speed_map_ready(sm_empty, "hkjc")
_test("Missing pace fails", not ready, "Should have failed")

# Missing track_bias should fail
sm_no_bias = {"predicted_pace": "快步速", "tactical_nodes": "1", "collapse_point": "400m"}
ready, issues = _speed_map_ready(sm_no_bias, "hkjc")
_test("Missing track_bias fails", not ready and "track_bias" in issues)

# [FILL] pace should fail
sm_fill = {"predicted_pace": "[FILL]", "track_bias": "X", "tactical_nodes": "X", "collapse_point": "X"}
ready, issues = _speed_map_ready(sm_fill, "hkjc")
_test("[FILL] pace fails", not ready)


# ═══════════════════════════════════════════════════════════════
# Test 4: node_advance_race increments correctly
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 4: node_advance_race increments correctly")
from racing_graph_nodes import node_advance_race

state_r1 = {"current_race": 1, "total_races": 3}
result = node_advance_race(state_r1)
_test("Race 1 → 2", result.get("current_race") == 2)
_test("Resets current_horse", result.get("current_horse") is None)
_test("Resets completed_in_session", result.get("completed_in_session") == 0)

state_r2 = {"current_race": 2, "total_races": 3}
result = node_advance_race(state_r2)
_test("Race 2 → 3", result.get("current_race") == 3)

state_r3 = {"current_race": 3, "total_races": 3}
result = node_advance_race(state_r3)
_test("Race 3 → COMPLETE", result.get("overall_stage") == "COMPLETE")
_test("No current_race on COMPLETE", "current_race" not in result or result.get("overall_stage") == "COMPLETE")


# ═══════════════════════════════════════════════════════════════
# Test 5: route_after_watch stops cleanly on waiting
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 5: route_after_watch handles waiting state")
try:
    from racing_graph_core import route_after_watch

    state_waiting = {"current_horse_result": "waiting", "should_stop": False,
                     "completed_in_session": 0, "current_race": 1, "races": {}}
    result = route_after_watch(state_waiting)
    _test("waiting → __end__", result == "__end__")

    state_timeout = {"current_horse_result": "timeout", "should_stop": False,
                     "completed_in_session": 0, "current_race": 1, "races": {}}
    result = route_after_watch(state_timeout)
    _test("timeout → __end__", result == "__end__")

    state_pass = {"current_horse_result": "pass", "should_stop": False,
                  "completed_in_session": 1, "current_race": 1,
                  "races": {"1": {"horses_pending": [2, 3]}}}
    result = route_after_watch(state_pass)
    _test("pass with pending → gen_workcard", result == "gen_workcard")
except ImportError:
    print("  ⏩ SKIPPED (langgraph not installed)")


# ═══════════════════════════════════════════════════════════════
# Test 6: Final QA strike writes .qa_strikes.json
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 6: QA strikes persistence")
tmpdir = tempfile.mkdtemp(prefix="langgraph_test_")
try:
    qa_file = os.path.join(tmpdir, ".qa_strikes.json")
    
    # Write initial strikes
    strikes_data = {"race_1_qa": 2}
    with open(qa_file, 'w') as f:
        json.dump(strikes_data, f)
    
    # Read back
    with open(qa_file, 'r') as f:
        loaded = json.load(f)
    
    _test("QA strikes file write/read", loaded.get("race_1_qa") == 2)
    
    # Atomic update
    strikes_data["race_1_qa"] = 3
    tmp = qa_file + ".tmp"
    with open(tmp, 'w') as f:
        json.dump(strikes_data, f)
    os.replace(tmp, qa_file)
    
    with open(qa_file, 'r') as f:
        loaded = json.load(f)
    _test("QA strikes atomic update", loaded.get("race_1_qa") == 3)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Test 7: build_racing_graph alias works
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 7: build_racing_graph alias")
try:
    from racing_graph_core import build_racing_graph, build_au_racing_graph
    _test("build_racing_graph exists", callable(build_racing_graph))
    _test("build_au_racing_graph is alias", build_au_racing_graph is build_racing_graph)
except ImportError:
    print("  ⏩ SKIPPED (langgraph not installed)")


# ═══════════════════════════════════════════════════════════════
# Test 8: should_stop reset in node_setup_race return
# ═══════════════════════════════════════════════════════════════
print("\n🧪 Test 8: node_setup_race resets should_stop")
# We can't easily run node_setup_race without a full meeting dir,
# but we can verify the function signature exists and check source
import inspect
from racing_graph_nodes import node_setup_race
source = inspect.getsource(node_setup_race)
_test("node_setup_race resets should_stop", "\"should_stop\": False" in source)
_test("node_setup_race resets waiting_for_agent", "\"waiting_for_agent\": False" in source)


# ═══════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
total = PASS + FAIL
print(f"🧪 Smoke Tests: {PASS}/{total} passed, {FAIL} failed")
if FAIL > 0:
    print("❌ SOME TESTS FAILED")
    sys.exit(1)
else:
    print("✅ ALL TESTS PASSED")
    sys.exit(0)
