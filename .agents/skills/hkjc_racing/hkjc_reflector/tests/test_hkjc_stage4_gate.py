from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from hkjc_no_regression_gate import evaluate_stage4_candidate  # noqa: E402


def _records() -> list[dict]:
    records = []
    for day in range(1, 21):
        actual = {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8}
        records.append(
            {
                "date": f"2026-01-{day:02d}",
                "actual_pos": actual,
                "models": {
                    "current_live": {
                        "picks": [4, 5, 6, 7, 1, 2, 3, 8],
                        "gold": False,
                        "good": False,
                    },
                    "candidate": {
                        "picks": [1, 2, 3, 4, 5, 6, 7, 8],
                        "gold": True,
                        "good": True,
                    },
                },
            }
        )
    return records


def test_hkjc_live_gate_uses_primary_gold_good_and_locked_terminal():
    verdict = evaluate_stage4_candidate(
        _records(), "candidate", leakage_audit_passed=True
    )
    assert verdict["verdict"] == "PRIMARY_WIN"


def test_hkjc_live_gate_fails_closed_without_leakage_audit():
    verdict = evaluate_stage4_candidate(
        _records(), "candidate", leakage_audit_passed=False
    )
    assert verdict == {
        "verdict": "REJECT",
        "reason": "leakage_audit_failed",
        "detail": {},
    }
