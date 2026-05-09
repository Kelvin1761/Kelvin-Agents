#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi" / "scripts"))

from racing_content_guard import assert_no_dummy_text, quarantine_file, scan_json_for_dummy, scan_text_for_dummy
from create_hkjc_logic_skeleton import validate_parsed_horse_header
from create_au_logic_skeleton import extract_horse_block, validate_parsed_horse_data
from compile_analysis_template_hkjc import _compute_letter_grade
from compile_analysis_template import _validate_au_logic_for_compile
from au_orchestrator import validate_au_race_ready_for_verdict, build_meeting_state_au

_AU_REPORTS = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi" / "scripts" / "generate_reports.py"
_spec = importlib.util.spec_from_file_location("au_generate_reports_for_test", _AU_REPORTS)
_au_reports = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_au_reports)
_report_ready = _au_reports._report_ready


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        raise


def ok(expr):
    assert expr


def main():
    check("scan_text catches [FILL]", lambda: ok(scan_text_for_dummy("abc [FILL]")))
    check("scan_text catches 自動生成", lambda: ok(scan_text_for_dummy("自動生成")))
    check("scan_text catches fluff", lambda: ok(scan_text_for_dummy("具備一定競爭力")))
    check("json path precision", lambda: ok(scan_json_for_dummy({"horses": {"1": {"core_logic": "[FILL]"}}})[0].startswith("horses.1.core_logic")))
    check("pending fill allowed", lambda: ok(not scan_json_for_dummy({"x": "[FILL]"}, allow_pending_fill=True)))
    check("completed fill blocked", lambda: ok(scan_json_for_dummy({"x": "[FILL]"}, allow_pending_fill=False)))
    check("HKJC rejects unknown name", lambda: _expect_error(lambda: validate_parsed_horse_header({"num": 1, "name": "未知", "barrier": 1, "weight": 120}, 1)))
    check("AU missing horse block", lambda: ok(extract_horse_block("[#1] Horse\n", 2) is None))
    check("HKJC compiler refuses matrix missing", lambda: _expect_error(lambda: _compute_letter_grade({}, {"horse_name": "A"})))
    check("AU compiler refuses missing dimension", lambda: _expect_error(lambda: _validate_au_logic_for_compile({"horses": {"1": {"horse_name": "A", "core_logic": "real", "matrix": {}}}})))
    check("verdict blocks final_rating-only", lambda: _expect_error(lambda: validate_au_race_ready_for_verdict({"horses": {"1": {"horse_name": "A", "core_logic": "real", "final_rating": "A"}}})))
    check("post compile guard blocks dummy", lambda: _expect_error(lambda: assert_no_dummy_text("Analysis [FILL]", "Analysis.md")))
    check("atomic guard no output", _test_atomic_no_output)
    check("quarantine moves reason", _test_quarantine)
    check("report guard blocks dummy", _test_report_guard)
    check("build state quarantines dummy analysis", _test_build_state_quarantine)


def _expect_error(fn):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("expected error")


def _test_atomic_no_output():
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "Race 1 Analysis.md"
        try:
            assert_no_dummy_text("[FILL]", str(out))
            out.write_text("bad", encoding="utf-8")
        except Exception:
            pass
        assert not out.exists()


def _test_quarantine():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "Race 1 Analysis.md"
        p.write_text("[FILL]", encoding="utf-8")
        dest = quarantine_file(str(p), "bad")
        assert not p.exists()
        assert Path(dest).exists()
        assert Path(dest + ".reason.txt").exists()


def _test_report_guard():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "Race 1 Analysis.md"
        p.write_text("[FILL]", encoding="utf-8")
        Path(td, "Race_1_Logic.json").write_text(json.dumps({"horses": {}}), encoding="utf-8")
        ok, reasons = _report_ready(td, str(p), 1)
        assert not ok and reasons


def _test_build_state_quarantine():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "2026-05-06 Race 1 Analysis.md"
        p.write_text("[FILL]", encoding="utf-8")
        state = build_meeting_state_au(td, 1, "2026-05-06")
        assert state["races"]["1"]["compiled"] is False
        assert list((Path(td) / ".runtime" / "quarantine").glob("*"))


if __name__ == "__main__":
    main()
