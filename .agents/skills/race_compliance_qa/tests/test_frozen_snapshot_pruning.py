"""Prediction snapshots are frozen copies; walking them fails a healthy meeting.

A snapshot is SUPPOSED to disagree with the current Logic once a meeting is
re-scored. The artifact maps are keyed by race number, so a snapshot copy can
displace the live file and the check then compares the wrong pair. AU writes
`_prediction_snapshots` and was excluded; HKJC writes `Prediction_Snapshots`
and was not, so the 2026-09-06 ShaTin morning refresh failed rc=1 on TOP4-001
while its live Analysis and live Logic agreed exactly.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from race_compliance_scan import is_frozen_path, iter_live_files  # noqa: E402


@pytest.mark.parametrize("folder", [
    "_prediction_snapshots",          # AU
    "Prediction_Snapshots",           # HKJC -- the one that was missed
    "prediction_snapshots",
    "_pre_v52_backup",
    "quarantine",
    ".hidden",
    "Some Backup Copy",
])
def test_frozen_subtrees_are_pruned(tmp_path, folder):
    target = tmp_path / folder / "20260904T005441+1000" / "Race_1_Logic.json"
    assert is_frozen_path(target, tmp_path)


def test_the_live_meeting_files_are_not_pruned(tmp_path):
    assert not is_frozen_path(tmp_path / "Race_1_Logic.json", tmp_path)
    assert not is_frozen_path(tmp_path / "Race Analysis" / "Race_1.md", tmp_path)


def test_iter_live_files_returns_the_live_copy_only(tmp_path):
    (tmp_path / "Prediction_Snapshots" / "20260904T005441+1000").mkdir(parents=True)
    (tmp_path / "Prediction_Snapshots" / "20260904T005441+1000"
     / "Race_1_Logic.json").write_text("{}", encoding="utf-8")
    live = tmp_path / "Race_1_Logic.json"
    live.write_text("{}", encoding="utf-8")
    found = list(iter_live_files(tmp_path, "Race_*_Logic.json"))
    assert found == [live]
