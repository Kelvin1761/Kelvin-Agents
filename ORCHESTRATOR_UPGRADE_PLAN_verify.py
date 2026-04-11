#!/usr/bin/env python3
"""
upgrade_verification.py — Orchestrator Upgrade Progress Tracker & Verifier
==========================================================================

PURPOSE:
  This script objectively verifies which upgrade steps have been ACTUALLY
  completed by scanning the real source files. It does NOT rely on manual
  checkbox tracking — it checks the code itself.

USAGE:
  python3 ORCHESTRATOR_UPGRADE_PLAN_verify.py

  Run this BEFORE starting work to see what's left.
  Run this AFTER each step to confirm it worked.
  
  Gemini / Opus / Sonnet: Run this script FIRST when you enter a new session.
  It will tell you exactly what to do next.

OUTPUT:
  Prints a clear status report showing:
  ✅ = Verified complete (code changes confirmed in source files)
  ❌ = Not done yet (code changes NOT found)
  ⚠️ = Partially done (some changes found, others missing)
"""

import os
import re
import sys
import json

# ============================================================
# CONFIG — All paths relative to project root
# ============================================================
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

HKJC_COMPILER = os.path.join(PROJECT_ROOT, ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py")
AU_COMPILER = os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_wong_choi/scripts/compile_analysis_template.py")
HKJC_ORCHESTRATOR = os.path.join(PROJECT_ROOT, ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py")
AU_ORCHESTRATOR = os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py")
AU_SKILL = os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_wong_choi/SKILL.md")
AU_PIPELINE = os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_wong_choi/resources/00_pipeline_and_execution.md")
SPEED_MAP_SCRIPT = os.path.join(PROJECT_ROOT, ".agents/scripts/predict_speed_map.py")
COMPLETION_GATE = None  # Will search for it

# Orphaned agents
ORPHANED_AGENTS = [
    os.path.join(PROJECT_ROOT, ".agents/skills/hkjc_racing/hkjc_batch_qa/SKILL.md"),
    os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_batch_qa/SKILL.md"),
    os.path.join(PROJECT_ROOT, ".agents/skills/hkjc_racing/hkjc_compliance/SKILL.md"),
    os.path.join(PROJECT_ROOT, ".agents/skills/au_racing/au_compliance/SKILL.md"),
]


def read_file(path):
    """Safely read a file, return empty string if not found."""
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except (FileNotFoundError, IOError):
        return ""


def find_completion_gate():
    """Search for completion_gate script."""
    for root, dirs, files in os.walk(os.path.join(PROJECT_ROOT, ".agents")):
        for f in files:
            if "completion_gate" in f and f.endswith(".py"):
                return os.path.join(root, f)
    return None


# ============================================================
# VERIFICATION CHECKS
# ============================================================

def check_step_1():
    """Step 1: HKJC Compiler full restructure"""
    code = read_file(HKJC_COMPILER)
    if not code:
        return "❌", "File not found", []

    checks = []
    missing = []

    # Check 1: 段速法醫 section exists
    if "段速法醫" in code and "sectional_forensic" in code:
        checks.append("✅ 段速法醫 section")
    else:
        missing.append("段速法醫 section (reads sectional_forensic from JSON)")

    # Check 2: EEM 能量 section exists
    if "EEM 能量" in code and "eem_energy" in code:
        checks.append("✅ EEM 能量 section")
    else:
        missing.append("EEM 能量 section (reads eem_energy from JSON)")

    # Check 3: 寬恕檔案 section exists
    if "寬恕檔案" in code and "forgiveness_archive" in code:
        checks.append("✅ 寬恕檔案 section")
    else:
        missing.append("寬恕檔案 section (reads forgiveness_archive from JSON)")

    # Check 4: 14.2B 微調 exists
    if "14.2B" in code and "fine_tune" in code:
        checks.append("✅ 14.2B 微調")
    else:
        missing.append("14.2B 微調 line (reads fine_tune from JSON)")

    # Check 5: 14.3 覆蓋 exists
    if "14.3" in code and "override" in code:
        checks.append("✅ 14.3 覆蓋")
    else:
        missing.append("14.3 覆蓋 line (reads override from JSON)")

    # Check 6: Evidence anchor (<details>)
    if "evidence_step_0_14" in code or "法醫級推演錨點" in code:
        checks.append("✅ Evidence anchor")
    else:
        missing.append("Evidence anchor (<details> block for Step 0-14)")

    # Check 7: Old duplicate injection lines removed (h_fact['trends'] was injected independently)
    old_trends_inject = "h_fact.get('trends')" in code and "h_fact.get('engine')" in code and "h_fact.get('new_dims')" in code
    if not old_trends_inject:
        checks.append("✅ Old duplicate Facts injection removed (trends/engine/new_dims)")
    else:
        missing.append("Remove old standalone h_fact['trends'], h_fact['engine'], h_fact['new_dims'] injection lines")

    # Check 8: Expanded analytical_breakdown (should have >5 items)
    breakdown_items = len(re.findall(r"h_analysis\.get\(", code))
    if breakdown_items >= 8:
        checks.append(f"✅ Expanded analytical breakdown ({breakdown_items} items)")
    else:
        missing.append(f"Expand analytical_breakdown (currently {breakdown_items} items, need ≥8)")

    if not missing:
        return "✅", "All compiler sections present", checks
    elif len(checks) > 0:
        return "⚠️", f"{len(missing)} sections still missing", missing
    else:
        return "❌", "Not started", missing


def check_step_2():
    """Step 2: AU Compiler full restructure"""
    code = read_file(AU_COMPILER)
    if not code:
        return "❌", "File not found", []

    checks = []
    missing = []

    # Same checks as Step 1 but for AU
    if "段速" in code and "sectional_forensic" in code:
        checks.append("✅ Sectional forensic section")
    else:
        missing.append("Sectional forensic section")

    if "fine_tune" in code and ("微調" in code or "fine_tune" in code):
        checks.append("✅ Fine-tune (14.2B)")
    else:
        missing.append("Fine-tune 14.2B (reads fine_tune from JSON)")

    if "override" in code and ("覆蓋" in code):
        checks.append("✅ Override (14.3)")
    else:
        missing.append("Override 14.3 (reads override from JSON)")

    if "最大競爭優勢" in code or "advantages" in code:
        checks.append("✅ 最大競爭優勢 line")
    else:
        missing.append("最大競爭優勢 line (reads advantages from JSON)")

    if "dual_track" in code or "雙軌" in code:
        checks.append("✅ Dual-track grading")
    else:
        missing.append("場地雙軌評級 section (AU-specific)")

    if "基礎評級" in code:
        checks.append("✅ 基礎評級 line in matrix")
    else:
        missing.append("基礎評級 line after matrix arithmetic")

    # Check expanded horse section
    if "班次負重" in code or "引擎距離" in code:
        checks.append("✅ Expanded 馬匹剖析")
    else:
        missing.append("Expand 馬匹剖析 from 1 line to 5 items")

    if not missing:
        return "✅", "All compiler sections present", checks
    elif len(checks) > 0:
        return "⚠️", f"{len(missing)} sections still missing", missing
    else:
        return "❌", "Not started", missing


def check_step_3():
    """Step 3: HKJC Orchestrator Logic.json schema expansion"""
    code = read_file(HKJC_ORCHESTRATOR)
    if not code:
        return "❌", "File not found", []

    markers = [
        ("sectional_forensic", "sectional_forensic JSON key"),
        ("eem_energy", "eem_energy JSON key"),
        ("forgiveness_archive", "forgiveness_archive JSON key"),
        ("fine_tune", "fine_tune JSON key"),
        ("evidence_step_0_14", "evidence_step_0_14 JSON key"),
    ]

    found = []
    missing = []
    for marker, desc in markers:
        if marker in code:
            found.append(f"✅ {desc}")
        else:
            missing.append(desc)

    if not missing:
        return "✅", "All JSON keys specified in stdout", found
    elif len(found) > 0:
        return "⚠️", f"{len(missing)} keys not yet in stdout", missing
    else:
        return "❌", "Not started", missing


def check_step_4():
    """Step 4: Batch 0 Speed Map mandatory fields"""
    hkjc = read_file(HKJC_ORCHESTRATOR)
    au = read_file(AU_ORCHESTRATOR)
    
    missing = []
    if "track_bias" not in hkjc or "tactical_nodes" not in hkjc:
        missing.append("HKJC Batch 0 missing track_bias/tactical_nodes in stdout")
    if "track_bias" not in au or "tactical_nodes" not in au:
        missing.append("AU Batch 0 missing track_bias/tactical_nodes in stdout")

    if "collapse_point" not in hkjc:
        missing.append("HKJC Batch 0 missing collapse_point")
    if "collapse_point" not in au:
        missing.append("AU Batch 0 missing collapse_point")

    if not missing:
        return "✅", "Both orchestrators have full Speed Map directives", []
    else:
        return "❌", f"{len(missing)} items missing", missing


def check_step_5():
    """Step 5: AU Orchestrator 5-step forensic awakening"""
    code = read_file(AU_ORCHESTRATOR)
    if not code:
        return "❌", "File not found", []

    # Check for the 5-step pattern
    markers = [
        "情境標籤",      # Step 0.5
        "段速法醫",      # Steps 4-10
        "8 維度",        # Step 14
        "核心邏輯",      # Writing requirement
        "fine_tune",     # Step 5 requirement
    ]

    found = sum(1 for m in markers if m in code)
    if found >= 4:
        return "✅", "5-step forensic awakening present", []
    elif found >= 2:
        return "⚠️", f"Only {found}/5 markers found", [m for m in markers if m not in code]
    else:
        return "❌", "AU still uses weak 2-line awakening", [m for m in markers if m not in code]


def check_step_6():
    """Step 6: Unify Logic.json format (AU list → dict)"""
    code = read_file(AU_ORCHESTRATOR)
    if "dict 格式" in code or "禁止用 list" in code:
        return "✅", "Dict format directive present", []
    else:
        return "❌", "AU stdout doesn't specify dict format for horses", []


def check_step_7():
    """Step 7: Uncomment HKJC report + add cost tracker"""
    code = read_file(HKJC_ORCHESTRATOR)
    if not code:
        return "❌", "File not found", []

    missing = []
    # Check report generation is NOT commented out
    report_lines = [l.strip() for l in code.split('\n') if 'generate_hkjc_reports' in l]
    if report_lines:
        if all(l.startswith('#') for l in report_lines):
            missing.append("generate_hkjc_reports.py still commented out")
    else:
        missing.append("generate_hkjc_reports.py call not found at all")

    # Check cost tracker exists
    if "session_cost_tracker" in code:
        pass  # OK
    else:
        missing.append("session_cost_tracker.py not called")

    if not missing:
        return "✅", "Report + cost tracker active", []
    else:
        return "❌", "Missing components", missing


def check_step_8():
    """Step 8: AU Orchestrator local folder fallback"""
    code = read_file(AU_ORCHESTRATOR)
    if 'os.path.isdir' in code or 'startswith("http")' in code:
        return "✅", "Local folder fallback present", []
    else:
        return "❌", "No local folder fallback — only accepts URLs", []


def check_step_9():
    """Step 9: Unify AU SKILL.md to V8"""
    skill = read_file(AU_SKILL)
    if not skill:
        return "❌", "File not found", []

    missing = []
    if "First Action" in skill or "絕對第一且唯一動作" in skill:
        pass
    else:
        missing.append("V8 First Action Lock not in AU SKILL.md")

    if "Hybrid Protocol" in skill or "V4.2" in skill:
        missing.append("Old Hybrid Protocol V4.2 still present — should be removed")

    if not missing:
        return "✅", "AU SKILL.md upgraded to V8", []
    else:
        return "❌", "AU SKILL.md still uses old architecture", missing


def check_step_10():
    """Step 10: Speed Map auto-generation script"""
    if os.path.exists(SPEED_MAP_SCRIPT):
        code = read_file(SPEED_MAP_SCRIPT)
        if "classify" in code or "leader" in code.lower():
            return "✅", "Speed Map script exists and has classification logic", []
        else:
            return "⚠️", "Script exists but may be incomplete", []
    else:
        return "❌", "predict_speed_map.py not found", []


RATING_MATRIX_SCRIPT = os.path.join(PROJECT_ROOT, ".agents/scripts/compute_rating_matrix.py")

def check_step_10_5():
    """Step 10.5: compute_rating_matrix.py (auto rating/fine-tune/override)"""
    if not os.path.exists(RATING_MATRIX_SCRIPT):
        return "❌", "compute_rating_matrix.py not found — THIS IS THE MOST CRITICAL NEW SCRIPT", \
               ["Creates: .agents/scripts/compute_rating_matrix.py",
                "Purpose: Auto-compute base_rating from ✅/❌ counts (lookup table)",
                "Purpose: Auto-apply 30 fine-tune rules (14.2B)",
                "Purpose: Auto-apply 15 override rules (14.3)",
                "Purpose: Auto-rank horses by rating → ✅ → ❌",
                "See ORCHESTRATOR_UPGRADE_PLAN.md Step 10.5 for full spec"]
    
    code = read_file(RATING_MATRIX_SCRIPT)
    checks = []
    missing = []
    
    # base_rating lookup function (accepts either naming)
    if ("compute_base_rating" in code or "lookup_base_grade" in code or 
        "base_rating" in code or "base_grade" in code):
        checks.append("✅ Base rating lookup")
    else:
        missing.append("Base rating lookup function (S to D)")
    
    # fine-tune rules (accepts either naming)
    if ("fine_tune" in code or "fine_tune_rules" in code or 
        "apply_micro" in code or "micro_up" in code or "micro_down" in code):
        checks.append("✅ Fine-tune rules")
    else:
        missing.append("Fine-tune rules (14.2B)")
    
    # override chain (accepts either naming)
    if ("override" in code or "override_chain" in code or 
        "apply_core_constraint" in code or "constrained_grade" in code):
        checks.append("✅ Override chain")
    else:
        missing.append("Override rules (14.3)")
    
    if not missing:
        return "✅", "Rating matrix auto-computation script complete", checks
    elif len(checks) > 0:
        return "⚠️", f"{len(missing)} components missing", missing
    else:
        return "❌", "Script exists but is empty/incomplete", missing


def check_step_11():
    """Step 11: Strengthen completion_gate_v2.py"""
    global COMPLETION_GATE
    COMPLETION_GATE = find_completion_gate()
    if not COMPLETION_GATE:
        return "⚠️", "completion_gate script not found in .agents/", []

    code = read_file(COMPLETION_GATE)
    missing = []

    if "核心邏輯" in code and ("字數" in code or "len(" in code or "word" in code.lower()):
        pass
    else:
        missing.append("Per-horse core_logic word count check")

    if "[FILL]" in code or "FILL" in code:
        pass
    else:
        missing.append("[FILL] residual scan")

    if "14.2B" in code:
        pass
    else:
        missing.append("14.2B existence check")

    if "段速" in code or "EEM" in code:
        pass
    else:
        missing.append("Sectional/EEM existence check")

    if not missing:
        return "✅", "QA gate has all required checks", []
    elif len(missing) < 4:
        return "⚠️", f"{len(missing)} checks still missing", missing
    else:
        return "❌", "QA gate needs strengthening", missing


def check_step_12():
    """Step 12: Archive orphaned agents"""
    missing = []
    for path in ORPHANED_AGENTS:
        content = read_file(path)
        if not content:
            continue  # File doesn't exist, that's fine
        if "DEPRECATED" in content or "deprecated" in content:
            pass
        else:
            missing.append(f"{os.path.basename(os.path.dirname(path))}/SKILL.md not marked deprecated")

    if not missing:
        return "✅", "All orphaned agents marked deprecated", []
    else:
        return "❌", f"{len(missing)} agents not yet marked", missing


# ============================================================
# MAIN REPORT
# ============================================================

def main():
    print("=" * 70)
    print("🔍 ORCHESTRATOR UPGRADE VERIFICATION REPORT")
    print(f"📅 Project Root: {PROJECT_ROOT}")
    print("=" * 70)
    print()

    steps = [
        ("Phase A: Compiler Full Upgrade", [
            (1, "HKJC Compiler full restructure", check_step_1),
            (2, "AU Compiler full restructure", check_step_2),
        ]),
        ("Phase B: Orchestrator Directive Enhancement", [
            (3, "HKJC Logic.json schema expansion", check_step_3),
            (4, "Batch 0 Speed Map mandatory fields", check_step_4),
            (5, "AU Orchestrator 5-step forensic awakening", check_step_5),
            (6, "Unify Logic.json format (dict)", check_step_6),
        ]),
        ("Phase C: Infrastructure Fixes", [
            (7, "Uncomment HKJC report + cost tracker", check_step_7),
            (8, "AU Orchestrator local folder fallback", check_step_8),
            (9, "AU SKILL.md → V8 architecture", check_step_9),
            (10, "Speed Map auto-generation script", check_step_10),
            ("10.5", "compute_rating_matrix.py (AUTO rating)", check_step_10_5),
        ]),
        ("Phase D: QA Enhancement + Cleanup", [
            (11, "Strengthen completion_gate_v2.py", check_step_11),
            (12, "Archive orphaned agents", check_step_12),
        ]),
    ]

    total_done = 0
    total_steps = 0
    next_step = None

    for phase_name, phase_steps in steps:
        print(f"📦 {phase_name}")
        print("-" * 50)
        for step_num, step_name, check_fn in phase_steps:
            total_steps += 1
            try:
                status, summary, details = check_fn()
            except Exception as e:
                status, summary, details = "❌", f"Error: {e}", []

            if status == "✅":
                total_done += 1

            print(f"  Step {str(step_num):>4s}: {status} {step_name}")
            if summary:
                print(f"           → {summary}")
            if details and status != "✅":
                for d in details[:5]:  # Show max 5 details
                    print(f"             • {d}")

            # Track first incomplete step
            if next_step is None and status != "✅":
                next_step = (step_num, step_name, details)
        print()

    # Summary
    print("=" * 70)
    print(f"📊 PROGRESS: {total_done}/{total_steps} steps completed")
    pct = (total_done / total_steps * 100) if total_steps > 0 else 0
    bar_filled = int(pct / 5)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    print(f"   [{bar}] {pct:.0f}%")
    print()

    if total_done == total_steps:
        print("🎉 ALL STEPS COMPLETE! Run verification tests (Steps 13-16).")
        print("   See ORCHESTRATOR_UPGRADE_PLAN.md for test commands.")
    elif next_step:
        num, name, details = next_step
        print(f"👉 NEXT ACTION: Step {num} — {name}")
        print(f"   📖 Read ORCHESTRATOR_UPGRADE_PLAN.md 'STEP {num}' section for full instructions.")
        if details:
            print(f"   📋 Specific items needed:")
            for d in details[:5]:
                print(f"      • {d}")
    print()
    print("=" * 70)

    return 0 if total_done == total_steps else 1


if __name__ == "__main__":
    sys.exit(main())
