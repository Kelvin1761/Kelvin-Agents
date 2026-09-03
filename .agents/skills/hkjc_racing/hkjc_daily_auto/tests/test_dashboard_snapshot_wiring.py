"""HKJC must hand `deploy.sh` a snapshot, not let it republish the live one.

`deploy.sh` has three branches. With `WC_DASHBOARD_BASE_SNAPSHOT` it publishes
the scheduler's snapshot; with `WC_ALLOW_DASHBOARD_FULL_RESCAN` it rescans; and
otherwise it downloads the live projection and republishes it **unchanged**.
`au_daily_schedule` sets the variable, HKJC never did, so every prerace run
reported a successful deploy while no HKJC meeting analysed after 2026-07-12
reached the board.
"""
from __future__ import annotations

import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL))

import hkjc_daily_schedule as sched  # noqa: E402


def test_run_cmd_accepts_an_env_overlay(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["env"] = kwargs.get("env") or {}

        class R:
            returncode = 0
            stdout = ""
        return R()

    monkeypatch.setattr(sched.subprocess, "run", fake_run)
    sched.run_cmd(["true"], env_overlay={"WC_DASHBOARD_BASE_SNAPSHOT": "/tmp/x.json"})
    assert seen["env"]["WC_DASHBOARD_BASE_SNAPSHOT"] == "/tmp/x.json"
    # The inherited environment must survive the overlay.
    assert "PATH" in seen["env"]


def test_snapshot_is_built_from_the_live_projection_plus_this_meeting(monkeypatch, tmp_path):
    calls = []

    def fake_run_cmd(cmd, **kwargs):
        calls.append([str(c) for c in cmd])
        # emulate both steps writing their output file
        for flag in ("--output", "--output-json"):
            if flag in cmd:
                Path(cmd[cmd.index(flag) + 1]).write_text("{}", encoding="utf-8")
        return 0, ""

    monkeypatch.setattr(sched, "run_cmd", fake_run_cmd)
    out = sched.build_dashboard_snapshot(tmp_path)
    assert out is not None and out.exists()
    assert any("fetch_live_snapshot.py" in " ".join(c) for c in calls)
    merge = next(c for c in calls if "generate_static.py" in " ".join(c))
    assert "--base-snapshot" in merge and "--meeting-dir" in merge
    assert merge[merge.index("--meeting-dir") + 1] == str(tmp_path)


def test_a_failed_fetch_falls_back_instead_of_publishing_a_half_snapshot(monkeypatch, tmp_path):
    monkeypatch.setattr(sched, "run_cmd", lambda cmd, **kw: (1, "boom"))
    assert sched.build_dashboard_snapshot(tmp_path) is None


def test_a_failed_merge_falls_back(monkeypatch, tmp_path):
    def fake_run_cmd(cmd, **kwargs):
        if "--output" in cmd:            # the fetch step succeeds
            Path(cmd[cmd.index("--output") + 1]).write_text("{}", encoding="utf-8")
            return 0, ""
        return 1, "merge failed"          # the merge step does not
    monkeypatch.setattr(sched, "run_cmd", fake_run_cmd)
    assert sched.build_dashboard_snapshot(tmp_path) is None


def test_multiple_settled_meetings_chain_instead_of_overwriting(monkeypatch, tmp_path):
    """Post-race can hand over two meetings; the second must build on the first.

    Re-fetching the live projection per meeting would keep only the last merge.
    """
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    bases = []

    def fake_run_cmd(cmd, **kwargs):
        cmd = [str(c) for c in cmd]
        for flag in ("--output", "--output-json"):
            if flag in cmd:
                Path(cmd[cmd.index(flag) + 1]).write_text("{}", encoding="utf-8")
        if "--base-snapshot" in cmd:
            bases.append(cmd[cmd.index("--base-snapshot") + 1])
        return 0, ""

    monkeypatch.setattr(sched, "run_cmd", fake_run_cmd)
    out = sched.build_dashboard_snapshot(a, b)
    assert out is not None
    assert len(bases) == 2
    # The second merge starts from the first merge's output, not from live.
    assert bases[0].endswith("live-dashboard-data.json")
    assert bases[1].endswith("dashboard-data-0.json")


def test_no_meeting_dirs_is_a_no_op(tmp_path):
    assert sched.build_dashboard_snapshot() is None
