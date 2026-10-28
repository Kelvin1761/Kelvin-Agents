"""Use the real installer in an isolated HOME; never call host launchctl."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[4]
INSTALLER = ROOT / ".agents/skills/central_wong_choi/install_production_runtime.sh"
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.runtime_snapshot_state import SnapshotStateError, disabled_jobs


def test_disabled_registry_accepts_observed_native_tokens_and_rejects_unknown():
    assert disabled_jobs('''
disabled services = {
    "paused" => disabled
    "running" => enabled
}
''') == {"paused": True, "running": False}
    with pytest.raises(SnapshotStateError):
        disabled_jobs('disabled services = { "unknown" => maybe }')


@pytest.fixture
def isolated_runtime(tmp_path):
    home = tmp_path / "home"
    agents = home / "Library/LaunchAgents"
    agents.mkdir(parents=True)
    label = "com.antigravity.hkjc-wong-choi.prerace"
    (agents / (label + ".plist")).write_bytes(b"old plist\n")
    loaded = tmp_path / "loaded.json"
    loaded.write_text(json.dumps({label: {"loaded": True, "disabled": False}}))
    calls = tmp_path / "mutations.jsonl"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(f'''#!{sys.executable}
import json, os, sys
from pathlib import Path
states = json.loads(Path(os.environ["TEST_JOB_STATES"]).read_text())
command = sys.argv[1]
if command == "print-disabled":
    print("disabled services = {{")
    for label, state in states.items():
        print('  "' + label + '" => ' + str(state["disabled"]).lower())
    print("}}")
elif command == "print":
    label = sys.argv[-1].rsplit("/", 1)[-1]
    if not states.get(label, {{}}).get("loaded", False):
        print('Could not find service "' + label + '"', file=sys.stderr)
        raise SystemExit(113)
    print("state = waiting")
else:
    with open(os.environ["TEST_JOB_MUTATIONS"], "a") as output:
        output.write(json.dumps(sys.argv[1:]) + "\\n")
    label = (Path(sys.argv[-1]).name.removesuffix(".plist") if command == "bootstrap"
             else sys.argv[-1].rsplit("/", 1)[-1])
    state = states.setdefault(label, {{"loaded": False, "disabled": False}})
    if command == "bootout":
        if os.environ.get("TEST_BOOTOUT_FAIL") == label:
            raise SystemExit(9)
        state["loaded"] = False
    elif command == "bootstrap":
        if state["disabled"]:
            raise SystemExit(7)
        state["loaded"] = True
    elif command in {{"enable", "disable"}}:
        state["disabled"] = command == "disable"
    Path(os.environ["TEST_JOB_STATES"]).write_text(json.dumps(states))
''')
    launchctl.chmod(0o755)
    env = {**os.environ, "HOME": str(home), "WC_LAUNCH_AGENTS_DIR": str(agents),
           "WC_LAUNCHCTL_BIN": str(launchctl), "WC_TENNIS_DB_POINTER": str(home / "pointer"),
           "WC_TENNIS_RUNTIME_ROOT": str(home / "tennis"),
           "TEST_JOB_STATES": str(loaded), "TEST_JOB_MUTATIONS": str(calls)}
    return agents, label, loaded, calls, env, tmp_path / "snapshot"


def invoke(env, *args):
    return subprocess.run(["/bin/zsh", str(INSTALLER), *map(str, args)],
                          env=env, capture_output=True, text=True, timeout=30)


def test_outer_restore_after_unchanged_busy_deferral_never_touches_jobs(isolated_runtime):
    agents, label, _, calls, env, snapshot = isolated_runtime
    captured = invoke(env, "--snapshot", snapshot)
    assert captured.returncode == 0, captured.stderr
    # The installer's busy preflight returned before changing anything. The
    # controller's recovery call must not stop the running production jobs.
    result = invoke(env, "--restore", snapshot)
    assert result.returncode == 0, result.stderr
    assert not calls.exists(), "unchanged recovery must never bootout/bootstrap/enable jobs"
    assert (agents / (label + ".plist")).read_bytes() == b"old plist\n"


def test_snapshot_records_loaded_and_disabled_state(isolated_runtime):
    _, label, loaded, _, env, snapshot = isolated_runtime
    loaded.write_text(json.dumps({label: {"loaded": False, "disabled": True}}))
    result = invoke(env, "--snapshot", snapshot)
    assert result.returncode == 0, result.stderr
    proof = json.loads((snapshot / ".launchd-state.json").read_text())
    assert proof["jobs"][label]["loaded"] is False
    assert proof["jobs"][label]["disabled"] is True


def test_restore_keeps_prior_unloaded_disabled_state_and_leaves_other_jobs_alone(isolated_runtime):
    agents, label, loaded, calls, env, snapshot = isolated_runtime
    other = "com.antigravity.nba-wong-choi.health"
    (agents / (other + ".plist")).write_bytes(b"other job\n")
    loaded.write_text(json.dumps({label: {"loaded": False, "disabled": True},
                                 other: {"loaded": True, "disabled": False}}))
    assert invoke(env, "--snapshot", snapshot).returncode == 0
    (agents / (label + ".plist")).write_bytes(b"candidate plist\n")
    result = invoke(env, "--restore", snapshot)
    assert result.returncode == 0, result.stderr
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert not any(command[0] == "bootstrap" for command in commands)
    assert any(command[0] == "disable" and command[-1].endswith("/" + label) for command in commands)
    assert not any(other in argument for command in commands for argument in command)
    assert (agents / (label + ".plist")).read_bytes() == b"old plist\n"


@pytest.mark.parametrize("defect", ["damaged-proof", "missing-proof", "changed-backup"])
def test_unverified_snapshot_blocks_before_any_launchd_mutation(isolated_runtime, defect):
    agents, label, _, calls, env, snapshot = isolated_runtime
    assert invoke(env, "--snapshot", snapshot).returncode == 0
    if defect == "damaged-proof":
        (snapshot / ".launchd-state.json").write_text("corrupt")
    elif defect == "missing-proof":
        (snapshot / ".launchd-state.json").unlink()
    else:
        (snapshot / (label + ".plist")).write_bytes(b"different historical bytes\n")
    result = invoke(env, "--restore", snapshot)
    assert result.returncode != 0
    assert not calls.exists()
    assert (agents / (label + ".plist")).read_bytes() == b"old plist\n"


def test_loaded_job_without_plist_is_not_a_restorable_snapshot(isolated_runtime):
    agents, label, _, calls, env, snapshot = isolated_runtime
    (agents / (label + ".plist")).unlink()
    result = invoke(env, "--snapshot", snapshot)
    assert result.returncode != 0
    assert not (snapshot / ".complete").exists()
    assert not calls.exists()


def test_failed_bootout_never_reports_success_or_overwrites_loaded_job(isolated_runtime):
    agents, label, loaded, calls, env, snapshot = isolated_runtime
    loaded.write_text(json.dumps({label: {"loaded": False, "disabled": False}}))
    assert invoke(env, "--snapshot", snapshot).returncode == 0
    loaded.write_text(json.dumps({label: {"loaded": True, "disabled": False}}))
    candidate = b"candidate still loaded\n"
    (agents / (label + ".plist")).write_bytes(candidate)
    env["TEST_BOOTOUT_FAIL"] = label
    result = invoke(env, "--restore", snapshot)
    assert result.returncode != 0
    assert (agents / (label + ".plist")).read_bytes() == candidate
    assert json.loads(loaded.read_text())[label]["loaded"] is True
    assert all(json.loads(line)[0] == "bootout" for line in calls.read_text().splitlines())


def test_restore_enables_before_bootstrap_then_restores_previous_flags(isolated_runtime):
    agents, label, loaded, _, env, snapshot = isolated_runtime
    assert invoke(env, "--snapshot", snapshot).returncode == 0
    loaded.write_text(json.dumps({label: {"loaded": False, "disabled": True}}))
    (agents / (label + ".plist")).write_bytes(b"candidate\n")
    result = invoke(env, "--restore", snapshot)
    assert result.returncode == 0, result.stderr
    assert json.loads(loaded.read_text())[label] == {"loaded": True, "disabled": False}
    assert (agents / (label + ".plist")).read_bytes() == b"old plist\n"
