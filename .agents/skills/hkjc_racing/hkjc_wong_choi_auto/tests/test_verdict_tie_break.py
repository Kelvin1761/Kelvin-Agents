"""VERDICT-002 must use the same tie-break as ensure_verdict.

rank_score is the 2-dp display score. Two horses can tie on it while their raw
scores differ; ensure_verdict then orders by raw score. The validator used to
break the tie on the display score instead, so a correctly ordered race whose
higher-raw horse had the larger number was refused outright (2026-10-10).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))

from hkjc_racing_engine.renderer import ensure_verdict  # noqa: E402
from hkjc_racing_engine.validation import _validate_verdict  # noqa: E402


def _logic():
    horses = {}
    # Same display score 72.10 → same rank_score; horse 7 has the higher raw.
    for number, raw in (("3", 67.4012), ("7", 67.4030), ("1", 60.0)):
        display = 72.10 if number != "1" else 55.0
        horses[number] = {"horse_name": f"H{number}", "python_auto": {
            "ability_score": display,
            "ability_score_raw": raw,
            "official_ranking_score": display,
            "grade": "B+",
        }}
    return {"horses": horses}


def test_display_tie_with_different_raw_is_not_refused():
    logic = _logic()
    ensure_verdict(logic)
    order = [item["horse_number"] for item in logic["python_auto_verdict"]["ranking"]]
    assert order == ["7", "3", "1"]
    scored = [(n, h["python_auto"]) for n, h in logic["horses"].items()]
    errors = _validate_verdict(logic, scored)
    assert not [e for e in errors if e.startswith("VERDICT-002")], errors
