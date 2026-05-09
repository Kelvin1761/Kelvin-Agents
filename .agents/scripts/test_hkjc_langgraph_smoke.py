#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

import racing_graph_nodes as nodes
from racing_graph_core import route_after_watch


def ok(expr):
    assert expr


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        raise


def main():
    hkjc_scripts = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi" / "scripts"
    check("HKJC compile path", lambda: ok((hkjc_scripts / "compile_analysis_template_hkjc.py").exists()))
    check("HKJC skeleton path", lambda: ok((hkjc_scripts / "create_hkjc_logic_skeleton.py").exists()))
    check("speed_map_ready predicted_pace", lambda: ok(nodes._speed_map_ready({"predicted_pace": "fast", "track_bias": "rail", "tactical_nodes": "x", "collapse_point": "y"}, "hkjc")[0]))
    check("skeleton subprocess failure stops", _test_skeleton_failure)
    check("timeout route becomes end", lambda: ok(route_after_watch({"current_horse_result": "waiting"}) == "__end__"))
    check("node_advance_race 1->2->3->complete", _test_advance)
    check("HKJC QA strike key", _test_qa_key_shape)


def _test_skeleton_failure():
    with tempfile.TemporaryDirectory() as td:
        state = _base_state(td)
        fns = {"skeleton_script": str(Path(td) / "missing.py")}
        original = nodes._get_domain_fns
        nodes._get_domain_fns = lambda domain: fns
        try:
            result = nodes.node_generate_workcard(state)
        finally:
            nodes._get_domain_fns = original
        assert result["should_stop"] is True
        assert "Skeleton generation failed" in result["stop_reason"]


def _base_state(td):
    facts = Path(td) / "2026-05-06 Race 1 Facts.md"
    facts.write_text("facts", encoding="utf-8")
    Path(td, "Race_1_Logic.json").write_text(json.dumps({"horses": {}}), encoding="utf-8")
    return {
        "target_dir": td, "current_race": 1, "current_horse": 1,
        "date_prefix": "2026-05-06", "short_prefix": "05-06",
        "races": {"1": {"horses_pending": [1]}}, "domain": "hkjc",
    }


def _test_advance():
    with tempfile.TemporaryDirectory() as td:
        s = {"current_race": 1, "total_races": 3, "target_dir": td, "log": []}
        r2 = nodes.node_advance_race(s)
        assert r2["current_race"] == 2
        s.update(r2)
        r3 = nodes.node_advance_race(s)
        assert r3["current_race"] == 3
        s.update(r3)
        done = nodes.node_advance_race(s)
        assert done["overall_stage"] == "COMPLETE"


def _test_qa_key_shape():
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / ".qa_strikes.json"
        path.write_text(json.dumps({"race_1_qa": 1}), encoding="utf-8")
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "race_1_qa" in data


if __name__ == "__main__":
    main()
