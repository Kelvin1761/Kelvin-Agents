from __future__ import annotations

import plistlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from verify_research_calendar import verify_calendar  # noqa: E402


LABEL = "com.antigravity.central-wong-choi.research-review"
SLOTS = [{"Hour": 7, "Minute": 10}, {"Weekday": 1, "Hour": 9, "Minute": 0}]


def write_plist(path, calendar, **extra):
    path.write_bytes(plistlib.dumps({"Label": LABEL, "StartCalendarInterval": calendar, **extra}))
    return path


def test_semantic_calendar_match_ignores_entry_order(tmp_path):
    template = write_plist(tmp_path / "source", SLOTS)
    installed = write_plist(tmp_path / "installed", list(reversed(SLOTS)))
    assert verify_calendar(template, installed)["status"] == "aligned"


def test_single_daily_dictionary_remains_supported(tmp_path):
    template = write_plist(tmp_path / "source", SLOTS[0])
    installed = write_plist(tmp_path / "installed", [SLOTS[0]])
    assert verify_calendar(template, installed)["status"] == "aligned"


@pytest.mark.parametrize("calendar", [SLOTS[:1], SLOTS + [{"Hour": 12, "Minute": 0}],
    [{"Weekday": 2, "Hour": 9, "Minute": 0}], []])
def test_missing_extra_or_wrong_installed_slot_fails(tmp_path, calendar):
    template = write_plist(tmp_path / "source", SLOTS)
    installed = write_plist(tmp_path / "installed", calendar)
    with pytest.raises(ValueError):
        verify_calendar(template, installed)


@pytest.mark.parametrize("extra", [{"RunAtLoad": True}, {"Label": "foreign-job"}])
def test_unexpected_run_at_load_or_label_fails(tmp_path, extra):
    template = write_plist(tmp_path / "source", SLOTS)
    installed = write_plist(tmp_path / "installed", SLOTS, **extra)
    with pytest.raises(ValueError):
        verify_calendar(template, installed)


@pytest.mark.parametrize("calendar", [
    [{"Hour": True, "Minute": 10}], [{"Hour": 24, "Minute": 10}],
    [{"Hour": 7, "Minute": 60}], [{"Weekday": 8, "Hour": 9, "Minute": 0}],
    SLOTS + [SLOTS[0]], [{"Hour": 7, "Minute": 10, "Unknown": 1}],
])
def test_invalid_calendar_is_not_alignment(tmp_path, calendar):
    template = write_plist(tmp_path / "source", calendar)
    installed = write_plist(tmp_path / "installed", calendar)
    with pytest.raises(ValueError):
        verify_calendar(template, installed)


def test_symlinked_plist_is_rejected(tmp_path):
    template = write_plist(tmp_path / "source", SLOTS)
    installed = tmp_path / "installed"
    installed.symlink_to(template)
    with pytest.raises(ValueError):
        verify_calendar(template, installed)


def test_unified_installer_verifies_calendar_before_completion():
    installer = Path(__file__).resolve().parents[1] / "install_production_runtime.sh"
    source = installer.read_text()
    assert "verify_research_calendar.py" in source
    assert source.index("verify_research_calendar.py") < source.index("\nCOMPLETED=1")
