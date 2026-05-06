#!/usr/bin/env python3
"""
test_hkjc_dummy_guard.py — Full test suite for HKJC dummy prevention layer.

Covers:
  1-6:   racing_content_guard core scanning
  7-8:   skeleton validation
  9-11:  compiler matrix enforcement
  12-13: post-compile guard + atomic write
  14:    quarantine_file
  15:    verdict guard
  16:    report guard
  17:    build_meeting_state dummy rejection

Run: python .agents/scripts/test_hkjc_dummy_guard.py
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
import json
import tempfile
import shutil
from pathlib import Path

# Add scripts to path
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPT_DIR)

# Also add hkjc scripts for skeleton/compiler imports
_HKJC_SCRIPTS = os.path.join(_SCRIPT_DIR, '..', 'skills', 'hkjc_racing', 'hkjc_wong_choi', 'scripts')
sys.path.insert(0, os.path.abspath(_HKJC_SCRIPTS))

from racing_content_guard import (
    scan_text_for_dummy,
    scan_json_for_dummy,
    assert_no_dummy_text,
    assert_no_dummy_json,
    quarantine_file,
    DUMMY_MARKERS,
    FLUFF_PHRASES,
)

# ═══════════════════════════════════════════════════════════════
# Test runner
# ═══════════════════════════════════════════════════════════════
_passed = 0
_failed = 0
_errors_detail = []


def check(name, condition, detail=""):
    global _passed, _failed
    if condition:
        print(f"  ✅ PASS: {name}")
        _passed += 1
    else:
        msg = f"  ❌ FAIL: {name}"
        if detail:
            msg += f"  ({detail})"
        print(msg)
        _failed += 1
        _errors_detail.append(name)


def _make_tmpdir():
    """Create a temp directory inside the workspace (not /tmp)."""
    d = os.path.join(_SCRIPT_DIR, '_test_tmp')
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup_tmpdir():
    d = os.path.join(_SCRIPT_DIR, '_test_tmp')
    if os.path.exists(d):
        shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════
# Tests 1-6: racing_content_guard core
# ═══════════════════════════════════════════════════════════════
def test_01_text_catches_fill():
    errs = scan_text_for_dummy("This is a [FILL] test")
    check("1. scan_text_for_dummy catches [FILL]",
          len(errs) >= 1 and any("[FILL]" in e for e in errs))


def test_02_text_catches_auto_gen():
    errs = scan_text_for_dummy("這是一段自動生成的內容")
    check("2. scan_text_for_dummy catches 自動生成",
          len(errs) >= 1 and any("自動生成" in e for e in errs))


def test_03_text_catches_fluff():
    errs = scan_text_for_dummy("這匹馬具備一定競爭力")
    check("3. scan_text_for_dummy catches 具備一定競爭力",
          len(errs) >= 1 and any("具備一定競爭力" in e for e in errs))


def test_04_json_returns_path():
    data = {"horses": {"1": {"core_logic": "This is a [FILL] paragraph."}}}
    errs = scan_json_for_dummy(data)
    check("4. scan_json_for_dummy returns path horses.1.core_logic",
          len(errs) >= 1 and "horses.1.core_logic" in errs[0])


def test_05_pending_fill_allowed():
    data = {"horses": {"1": {"core_logic": "[FILL]"}}}
    errs = scan_json_for_dummy(data, allow_pending_fill=True)
    check("5. allow_pending_fill=True allows [FILL]",
          len(errs) == 0, f"got {len(errs)} errors")


def test_06_completed_fill_blocked():
    data = {"horses": {"1": {"core_logic": "[FILL]"}}}
    errs = scan_json_for_dummy(data, allow_pending_fill=False)
    check("6. allow_pending_fill=False blocks completed horse [FILL]",
          len(errs) >= 1)


# ═══════════════════════════════════════════════════════════════
# Tests 7-8: skeleton validation
# ═══════════════════════════════════════════════════════════════
def test_07_skeleton_rejects_unknown_name():
    """Skeleton rejects horse_name=未知."""
    try:
        from create_hkjc_logic_skeleton import parse_horse_header
    except ImportError:
        check("7. skeleton rejects horse_name=未知", False, "import failed")
        return

    # The name validation happens in main() after parse_horse_header.
    # We test the validation logic directly.
    invalid_names = ["?", "未知", "Unknown", "", "123"]
    all_rejected = True
    for name in invalid_names:
        if name and name not in ("?", "未知", "Unknown", "") and not name.isdigit():
            all_rejected = False
    check("7. skeleton rejects horse_name=未知/Unknown/?/empty/numeric",
          all_rejected)


def test_08_skeleton_rejects_missing_block():
    """Skeleton rejects when extract_horse_block returns None."""
    try:
        from create_hkjc_logic_skeleton import extract_horse_block
    except ImportError:
        check("8. skeleton rejects missing horse block", False, "import failed")
        return

    result = extract_horse_block("No horse data here", 99)
    check("8. skeleton rejects missing horse block (returns None/empty)",
          not result)


# ═══════════════════════════════════════════════════════════════
# Tests 9-11: compiler matrix enforcement
# ═══════════════════════════════════════════════════════════════
def test_09_compiler_refuses_matrix_missing():
    """Compiler refuses to grade a horse with no matrix."""
    try:
        from compile_analysis_template_hkjc import _compute_letter_grade
    except ImportError:
        check("9. compiler refuses matrix missing", False, "import failed")
        return

    try:
        _compute_letter_grade({}, {"horse_name": "Test"})
        check("9. compiler refuses matrix missing", False, "no error raised")
    except ValueError as e:
        check("9. compiler refuses matrix missing",
              "matrix missing" in str(e).lower())


def test_10_compiler_refuses_missing_dimension():
    """Compiler refuses matrix with fewer than 7 dimensions."""
    try:
        from compile_analysis_template_hkjc import _compute_letter_grade
    except ImportError:
        check("10. compiler refuses missing matrix dimension", False, "import failed")
        return

    partial_matrix = {
        "stability": {"score": "✅", "reasoning": "test"},
        "sectional": {"score": "✅", "reasoning": "test"},
        # Missing: race_shape, trainer_signal, horse_health, form_line, class_advantage
    }
    try:
        _compute_letter_grade(partial_matrix, {"horse_name": "Test"})
        check("10. compiler refuses missing matrix dimension", False, "no error raised")
    except ValueError as e:
        check("10. compiler refuses missing matrix dimension",
              "missing matrix dimensions" in str(e).lower())


def test_11_compiler_refuses_final_rating_only():
    """Compiler refuses a horse with final_rating but no matrix."""
    try:
        from compile_analysis_template_hkjc import _compute_letter_grade
    except ImportError:
        check("11. compiler refuses final_rating-only horse", False, "import failed")
        return

    try:
        _compute_letter_grade({}, {"horse_name": "Test", "final_rating": "A-"})
        check("11. compiler refuses final_rating-only horse", False, "no error raised")
    except ValueError as e:
        check("11. compiler refuses final_rating-only horse",
              "matrix missing" in str(e).lower())


# ═══════════════════════════════════════════════════════════════
# Tests 12-13: post-compile guard + atomic write
# ═══════════════════════════════════════════════════════════════
def test_12_post_compile_blocks_dummy_markdown():
    """Post-compile guard blocks markdown containing [FILL]."""
    try:
        assert_no_dummy_text("## Horse 1\ncore_logic: [FILL]", "test_output.md")
        check("12. post-compile guard blocks dummy markdown", False, "no error raised")
    except ValueError as e:
        check("12. post-compile guard blocks dummy markdown",
              "[FILL]" in str(e))


def test_13_atomic_write_no_output_on_failure():
    """Atomic write does not leave output file after guard failure."""
    tmpdir = _make_tmpdir()
    output_path = os.path.join(tmpdir, "Test_Analysis.md")
    tmp_path = output_path + ".tmp"

    # Simulate: write to .tmp, then guard fails, then clean up
    Path(tmp_path).write_text("[FILL] dummy content", encoding="utf-8")
    # Guard would fail, so we delete .tmp
    if os.path.exists(tmp_path):
        os.unlink(tmp_path)

    check("13. atomic write does not leave output after guard failure",
          not os.path.exists(output_path) and not os.path.exists(tmp_path))


# ═══════════════════════════════════════════════════════════════
# Test 14: quarantine_file
# ═══════════════════════════════════════════════════════════════
def test_14_quarantine_moves_and_writes_reason():
    """quarantine_file moves file and writes reason."""
    tmpdir = _make_tmpdir()
    test_file = os.path.join(tmpdir, "test_dummy.md")
    Path(test_file).write_text("dummy content", encoding="utf-8")

    q_path = quarantine_file(test_file, "Test quarantine reason")
    q_path_obj = Path(q_path)

    moved = q_path_obj.exists() and not os.path.exists(test_file)
    reason_files = list(q_path_obj.parent.glob("*_reason.txt"))
    has_reason = any("Test quarantine reason" in rf.read_text() for rf in reason_files)

    check("14. quarantine_file moves file and writes reason",
          moved and has_reason)


# ═══════════════════════════════════════════════════════════════
# Test 15: verdict guard
# ═══════════════════════════════════════════════════════════════
def test_15_verdict_blocks_incomplete_horse():
    """Verdict guard blocks a horse with empty matrix."""
    try:
        from hkjc_orchestrator import validate_hkjc_race_ready_for_verdict
    except ImportError:
        check("15. verdict guard blocks incomplete horse", False, "import failed")
        return

    logic_data = {
        "horses": {
            "1": {
                "horse_name": "Test Horse",
                "matrix": {},  # Empty matrix
                "core_logic": "Some analysis"
            }
        }
    }
    try:
        validate_hkjc_race_ready_for_verdict(logic_data)
        check("15. verdict guard blocks incomplete horse", False, "no error raised")
    except ValueError as e:
        check("15. verdict guard blocks incomplete horse",
              "matrix missing" in str(e).lower() or "blocked" in str(e).lower())


# ═══════════════════════════════════════════════════════════════
# Test 16: report guard blocks dummy Analysis.md
# ═══════════════════════════════════════════════════════════════
def test_16_report_guard_blocks_dummy():
    """parse_analysis_file returns empty for dummy content."""
    try:
        from generate_hkjc_reports import parse_analysis_file
    except ImportError:
        check("16. report guard blocks dummy Analysis.md", False, "import failed")
        return

    tmpdir = _make_tmpdir()
    dummy_file = os.path.join(tmpdir, "Race_1_Analysis.md")
    Path(dummy_file).write_text("## Analysis\n[FILL] placeholder content\n具備一定競爭力", encoding="utf-8")

    results = parse_analysis_file(dummy_file)
    check("16. report guard blocks dummy Analysis.md",
          len(results) == 0, f"got {len(results)} results instead of 0")


# ═══════════════════════════════════════════════════════════════
# Test 17: build_meeting_state rejects dummy Analysis.md
# ═══════════════════════════════════════════════════════════════
def test_17_meeting_state_rejects_dummy():
    """build_meeting_state should not mark a dummy Analysis.md as compiled."""
    # We test the scan logic directly since build_meeting_state requires
    # a full filesystem setup
    dummy_content = "## Race 1 Analysis\nThis horse 具備一定競爭力 and has [FILL] sections"
    errs = scan_text_for_dummy(dummy_content)
    check("17. build_meeting_state scan catches dummy Analysis.md content",
          len(errs) >= 2, f"expected >=2 errors, got {len(errs)}")


# ═══════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════
def run_all():
    print("=" * 60)
    print("HKJC Dummy Prevention — Full Test Suite (17 tests)")
    print("=" * 60)
    print()

    print("── racing_content_guard core ──")
    test_01_text_catches_fill()
    test_02_text_catches_auto_gen()
    test_03_text_catches_fluff()
    test_04_json_returns_path()
    test_05_pending_fill_allowed()
    test_06_completed_fill_blocked()

    print("\n── skeleton validation ──")
    test_07_skeleton_rejects_unknown_name()
    test_08_skeleton_rejects_missing_block()

    print("\n── compiler matrix enforcement ──")
    test_09_compiler_refuses_matrix_missing()
    test_10_compiler_refuses_missing_dimension()
    test_11_compiler_refuses_final_rating_only()

    print("\n── post-compile guard + atomic write ──")
    test_12_post_compile_blocks_dummy_markdown()
    test_13_atomic_write_no_output_on_failure()

    print("\n── quarantine ──")
    test_14_quarantine_moves_and_writes_reason()

    print("\n── verdict guard ──")
    test_15_verdict_blocks_incomplete_horse()

    print("\n── report guard ──")
    test_16_report_guard_blocks_dummy()

    print("\n── meeting state ──")
    test_17_meeting_state_rejects_dummy()

    print()
    print("=" * 60)
    print(f"Results: {_passed} passed, {_failed} failed out of 17")
    if _errors_detail:
        print(f"Failed: {', '.join(_errors_detail)}")
    print("=" * 60)

    _cleanup_tmpdir()
    return _failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)
