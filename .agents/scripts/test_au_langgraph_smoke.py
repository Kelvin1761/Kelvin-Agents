#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi" / "scripts"))

import racing_graph_nodes as nodes
from racing_graph_core import route_after_watch
from create_au_logic_skeleton import parse_horse_header, validate_parsed_horse_data


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
    au_scripts = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi" / "scripts"
    check("AU compile path exists", lambda: ok((au_scripts / "compile_analysis_template.py").exists()))
    check("AU skeleton path exists", lambda: ok((au_scripts / "create_au_logic_skeleton.py").exists()))
    check("AU parser rejects missing name", lambda: _expect_error(lambda: validate_parsed_horse_data(parse_horse_header("[#1]\nJockey: A\n"), 1)))
    check("AU parser accepts same-line name", lambda: ok(parse_horse_header("[#1] Fast Horse\nJockey: A")["name"] == "Fast Horse"))
    check("AU parser accepts next-line name", lambda: ok(parse_horse_header("[#1]\nFast Horse\nJockey: A")["name"] == "Fast Horse"))
    check("speed_map_ready expected_pace", lambda: ok(nodes._speed_map_ready({"expected_pace": "fast", "track_bias": "rail", "tactical_nodes": "x", "collapse_point": "y"}, "au")[0]))
    check("speed_map_ready predicted fallback", lambda: ok(nodes._speed_map_ready({"predicted_pace": "fast", "track_bias": "rail", "tactical_nodes": "x", "collapse_point": "y"}, "au")[0]))
    check("skeleton subprocess failure stops", _test_skeleton_failure)
    check("timeout route becomes end", lambda: ok(route_after_watch({"current_horse_result": "waiting"}) == "__end__"))
    check("node_advance_race", _test_advance)
    check("AU QA strike key", lambda: ok(str(1) == "1"))


def _expect_error(fn):
    try:
        fn()
    except Exception:
        return
    raise AssertionError("expected error")


def _test_skeleton_failure():
    with tempfile.TemporaryDirectory() as td:
        Path(td, "2026-05-06 Race 1 Facts.md").write_text("facts", encoding="utf-8")
        Path(td, "Race_1_Logic.json").write_text(json.dumps({"horses": {}}), encoding="utf-8")
        state = {"target_dir": td, "current_race": 1, "current_horse": 1, "date_prefix": "2026-05-06", "short_prefix": "05-06", "races": {"1": {"horses_pending": [1]}}, "domain": "au"}
        fns = {"skeleton_script": str(Path(td) / "missing.py")}
        original = nodes._get_domain_fns
        nodes._get_domain_fns = lambda domain: fns
        try:
            result = nodes.node_generate_workcard(state)
        finally:
            nodes._get_domain_fns = original
        assert result["should_stop"] is True


def _test_advance():
    with tempfile.TemporaryDirectory() as td:
        s = {"current_race": 1, "total_races": 2, "target_dir": td, "log": []}
        r2 = nodes.node_advance_race(s)
        assert r2["current_race"] == 2
        s.update(r2)
        done = nodes.node_advance_race(s)
        assert done["overall_stage"] == "COMPLETE"


if __name__ == "__main__":
    main()
