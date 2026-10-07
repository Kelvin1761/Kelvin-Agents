import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import cloudflare_deploy_hook as hook


class _Result:
    returncode = 0


def test_build_target_snapshot_ignores_non_meeting(tmp_path):
    assert hook._build_target_snapshot(tmp_path) is None


def test_run_deploy_passes_merged_snapshot_to_deploy(tmp_path):
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    snapshot = meeting / "Dashboard_Snapshot" / "post-success-dashboard-data.json"
    snapshot.parent.mkdir()
    snapshot.write_text("{}", encoding="utf-8")

    captured = {}

    def fake_run(command, **kwargs):
        captured.update(kwargs)
        return type("Result", (), {"returncode": 0})()

    with patch.object(hook, "_build_target_snapshot", return_value=snapshot), \
            patch.object(hook.subprocess, "run", side_effect=fake_run):
        assert hook._run_deploy(
            source="test",
            target_dir=meeting,
            allow_failure=False,
            clear_queue_on_success=False,
        )

    assert captured["env"]["WC_DASHBOARD_BASE_SNAPSHOT"] == str(snapshot)


def test_build_target_snapshot_fetches_then_merges_meeting(tmp_path):
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    (meeting / "Race_1_Auto_Analysis.md").write_text("ready", encoding="utf-8")
    fetch_script = tmp_path / "fetch_live_snapshot.py"
    generator = tmp_path / "generate_static.py"
    fetch_script.touch()
    generator.touch()
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if "--output" in command:
            Path(command[command.index("--output") + 1]).write_text("{}", encoding="utf-8")
        if "--output-json" in command:
            Path(command[command.index("--output-json") + 1]).write_text("{}", encoding="utf-8")
        return _Result()

    with patch.object(hook, "DASHBOARD_FETCH_LIVE", fetch_script), \
            patch.object(hook, "DASHBOARD_GENERATOR", generator), \
            patch.object(hook.subprocess, "run", side_effect=fake_run):
        result = hook._build_target_snapshot(meeting)

    assert result == meeting / "Dashboard_Snapshot" / "post-success-dashboard-data.json"
    assert len(calls) == 2
    assert calls[0][0][1] == str(fetch_script)
    assert calls[1][0][1] == str(generator)
    assert calls[1][1]["cwd"] == hook.DASHBOARD_ROOT


def test_run_deploy_refuses_stale_success_for_scored_meeting(tmp_path):
    meeting = tmp_path / "2026-10-07_HappyValley"
    meeting.mkdir()
    (meeting / "Race_1_Auto_Analysis.md").write_text("ready", encoding="utf-8")

    with patch.object(hook, "_build_target_snapshot", return_value=None), \
            patch.object(hook.subprocess, "run") as deploy:
        assert not hook._run_deploy(
            source="test",
            target_dir=meeting,
            allow_failure=True,
            clear_queue_on_success=False,
        )

    deploy.assert_not_called()
