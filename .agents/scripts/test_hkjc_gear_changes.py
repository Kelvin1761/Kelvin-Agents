#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".agents" / "scripts"))

from scrape_hkjc_horse_profile import detect_gear_changes


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
    check("removed gear plus first-time visor continues as V", _test_removed_gear_marker_is_not_active)
    check("numeric gear suffix compares as base gear", _test_numeric_suffix_is_base_gear)
    check("removed current gear counts as removal", _test_current_removed_marker_removes_active_gear)
    check("real multi-gear removal still triggers SIP-HV2", _test_real_multi_gear_removal)


def _test_removed_gear_marker_is_not_active():
    result = detect_gear_changes([{"gear": "B-/V1"}], "V")
    assert result["signal"] == "無變動"
    assert result["last"] == "V"
    assert result["today"] == "V"
    assert result["added"] == set()
    assert result["removed"] == set()
    assert result["sip_hv2"] is False


def _test_numeric_suffix_is_base_gear():
    cases = [
        ("B2", "B", "B"),
        ("TT1", "TT", "TT"),
        ("XB/SR2", "SR/XB", "SR/XB"),
        ("CP-/B1/TT2", "B/TT", "B/TT"),
    ]
    for last_gear, today_gear, expected in cases:
        result = detect_gear_changes([{"gear": last_gear}], today_gear)
        assert result["signal"] == "無變動"
        assert result["last"] == expected
        assert result["today"] == expected
        assert result["sip_hv2"] is False


def _test_current_removed_marker_removes_active_gear():
    result = detect_gear_changes([{"gear": "PC2/TT"}], "PC-/TT")
    assert result["signal"] == "🔧 除去 PC"
    assert result["last"] == "PC/TT"
    assert result["today"] == "TT"
    assert result["added"] == set()
    assert result["removed"] == {"PC"}
    assert result["sip_hv2"] is False


def _test_real_multi_gear_removal():
    result = detect_gear_changes([{"gear": "B/XB/TT"}], "TT")
    assert result["last"] == "B/TT/XB"
    assert result["today"] == "TT"
    assert result["added"] == set()
    assert result["removed"] == {"B", "XB"}
    assert result["sip_hv2"] is True
    assert "大幅配備變動" in result["signal"]


if __name__ == "__main__":
    main()
