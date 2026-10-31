from __future__ import annotations

import os
import json
import plistlib
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from _runtime_owned_test_helpers import owned_cli, owned_publication


@pytest.fixture(autouse=True)
def isolated_cutover_control(tmp_path, monkeypatch):
    monkeypatch.setenv("WONGCHOI_CONTROL_STATE_ROOT", str(tmp_path / "control-state"))
    monkeypatch.delenv("WC_RUNTIME_CUTOVER_FD", raising=False)


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALLER = (
    REPO_ROOT
    / ".agents/skills/central_wong_choi/install_production_runtime.sh"
)


@pytest.mark.parametrize("central_fails", [False, True])
def test_full_gate_runs_central_tests_and_propagates_failure(tmp_path, central_fails):
    """Exercise the real runner with stub suites, never production installers."""
    root = tmp_path / "gate"
    root.mkdir()
    (root / "tennis-wong-choi").mkdir()
    runner = root / "run_tests.sh"
    runner.write_bytes((REPO_ROOT / "run_tests.sh").read_bytes())
    calls = root / "calls.jsonl"
    python = root / "suite-python"
    python.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "with open(os.environ['GATE_CALLS'], 'a') as output:\n"
        "    output.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "raise SystemExit(7 if os.environ['FAIL_CENTRAL'] == '1' and "
        "'.agents/skills/central_wong_choi/tests' in sys.argv else 0)\n",
        encoding="utf-8",
    )
    python.chmod(0o755)
    env = {**os.environ, "PYTHON_BIN": str(python), "GATE_CALLS": str(calls),
           "FAIL_CENTRAL": "1" if central_fails else "0"}
    result = subprocess.run(["bash", str(runner)], cwd=root, env=env,
                            capture_output=True, text=True, timeout=20)
    invoked = [json.loads(line) for line in calls.read_text().splitlines()]
    assert sum(".agents/skills/central_wong_choi/tests" in row for row in invoked) == 1
    assert len(invoked) >= 15  # Retain the original 14 Python suites too.
    assert any("tests" in row for row in invoked)  # Continue through Tennis after a failure.
    assert result.returncode == (1 if central_fails else 0), result.stdout + result.stderr
    assert ("FAIL  Central Wong Choi" if central_fails else "PASS  Central Wong Choi") in result.stdout


@pytest.mark.parametrize("pointer_existed", [False, True])
def test_runtime_installer_snapshot_restore_is_exact_and_idempotent(
    tmp_path: Path, pointer_existed: bool,
) -> None:
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    snapshot = tmp_path / "snapshot"
    fake_launchctl = tmp_path / "launchctl"
    fake_launchctl.write_text('''#!/bin/sh
case "$1" in
  print-disabled) printf 'disabled services = {\\n}\\n'; exit 0;;
  print)
    label="${2##*/}"
    [ ! -f "$WC_LAUNCH_AGENTS_DIR/$label.plist" ] || exit 0
    echo "Could not find service" >&2; exit 113;;
esac
exit 0
''', encoding="utf-8")
    fake_launchctl.chmod(0o755)
    existing = agents / "com.antigravity.hkjc-wong-choi.prerace.plist"
    introduced = agents / "com.antigravity.nba-wong-choi.health.plist"
    existing.write_text("old plist\n", encoding="utf-8")
    pointer = tmp_path / "tennis-db-pointer"
    runtime = tmp_path / "tennis-runtime"
    if pointer_existed:
        pointer.write_bytes(b"original-db-path\n")
        pointer.chmod(0o640)
    env = os.environ.copy()
    env.update(
        {
            "WC_LAUNCH_AGENTS_DIR": str(agents),
            "WC_LAUNCHCTL_BIN": str(fake_launchctl),
            "WC_TENNIS_DB_POINTER": str(pointer),
            "WC_TENNIS_RUNTIME_ROOT": str(runtime),
        }
    )

    subprocess.run(
        ["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    owned_publication(env, snapshot, existing.stem)
    owned_publication(env, snapshot, introduced.stem)
    owned_cli(env, snapshot, "begin-pointer")
    owned_cli(env, snapshot, "publish-pointer")

    for _attempt in range(2):
        subprocess.run(
            ["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
            env=env,
            text=True,
            capture_output=True,
            check=True,
        )
        assert existing.read_text(encoding="utf-8") == "old plist\n"
        assert not introduced.exists()
        if pointer_existed:
            assert pointer.read_bytes() == b"original-db-path\n"
            assert pointer.stat().st_mode & 0o777 == 0o640
        else:
            assert not pointer.exists()

    # Removing metadata from a bound attempt is damage, not a legacy downgrade.
    for metadata in snapshot.glob(".tennis-db-pointer-*"):
        metadata.unlink()
    pointer.write_bytes(b"newer-config-outside-legacy-snapshot\n")
    damaged = subprocess.run(["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
                             env=env, capture_output=True, text=True)
    assert damaged.returncode != 0
    assert pointer.read_bytes() == b"newer-config-outside-legacy-snapshot\n"


@pytest.mark.parametrize("change", ["value", "removed", "symlink", "different_path"])
def test_runtime_pointer_restore_refuses_detected_concurrent_change(tmp_path, change):
    agents = tmp_path / "agents"
    agents.mkdir()
    snapshot = tmp_path / "snapshot"
    pointer = tmp_path / "db-pointer"
    pointer.write_bytes(b"original\n")
    protected = tmp_path / "protected"
    protected.write_bytes(b"newer-owner-value\n")
    marker = tmp_path / "launchctl-called"
    launchctl = tmp_path / "launchctl"
    launchctl.write_text(f'''#!/bin/sh
case "$1" in
  print-disabled) printf 'disabled services = {{\\n}}\\n'; exit 0;;
  print)
    label="${{2##*/}}"
    [ ! -f "$WC_LAUNCH_AGENTS_DIR/$label.plist" ] || exit 0
    echo "Could not find service" >&2; exit 113;;
esac
touch "{marker}"
exit 0
''')
    launchctl.chmod(0o755)
    env = {**os.environ, "WC_LAUNCH_AGENTS_DIR": str(agents),
           "WC_LAUNCHCTL_BIN": str(launchctl), "WC_TENNIS_DB_POINTER": str(pointer),
           "WC_TENNIS_RUNTIME_ROOT": str(tmp_path / "runtime")}
    subprocess.run(["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
                   env=env, capture_output=True, text=True, check=True)
    if change == "value":
        pointer.write_bytes(b"newer-owner-value\n")
    elif change == "removed":
        pointer.unlink()
    elif change == "symlink":
        pointer.unlink()
        pointer.symlink_to(protected)
    else:
        env["WC_TENNIS_DB_POINTER"] = str(protected)
    result = subprocess.run(["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
                            env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert not marker.exists()  # Fail before changing any loaded service.
    assert protected.read_bytes() == b"newer-owner-value\n"
    if change == "value":
        assert pointer.read_bytes() == b"newer-owner-value\n"
    elif change == "removed":
        assert not pointer.exists()
    elif change == "symlink":
        assert pointer.is_symlink()


@pytest.mark.parametrize("unsafe", ["symlink", "directory", "fifo", "oversized"])
def test_runtime_pointer_snapshot_rejects_unsafe_config(tmp_path, unsafe):
    pointer = tmp_path / "pointer"
    protected = tmp_path / "protected"
    protected.write_bytes(b"untouched\n")
    if unsafe == "symlink":
        pointer.symlink_to(protected)
    elif unsafe == "directory":
        pointer.mkdir()
    elif unsafe == "fifo":
        os.mkfifo(pointer)
    else:
        pointer.write_bytes(b"x" * 4097)
    snapshot = tmp_path / "snapshot"
    env = {**os.environ, "WC_TENNIS_DB_POINTER": str(pointer),
           "WC_LAUNCH_AGENTS_DIR": str(tmp_path / "absent-agents")}
    result = subprocess.run(["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not (snapshot / ".complete").exists()
    assert protected.read_bytes() == b"untouched\n"


@pytest.mark.parametrize("active_run,acceptance,calendar_ok,attempt", [
    (False, True, True, "internal"), (True, True, True, "internal"),
    (False, False, True, "internal"), (False, True, False, "internal"),
    (False, True, True, "outer"), (False, True, True, "outer-conflict"),
    (False, True, True, "bound-bootstrap-failure"),
])
def test_runtime_installer_full_cutover_in_isolated_home(tmp_path: Path, active_run: bool, acceptance: bool, calendar_ok: bool, attempt: str) -> None:
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    pointer = home / ".wongchoi_tennis_db"
    original_pointer = b"original-live-db-path\n"
    pointer.write_bytes(original_pointer)
    runtime = tmp_path / "tennis-runtime"
    runtime.mkdir()
    with sqlite3.connect(runtime / "tennis_wc.db") as connection:
        connection.execute("CREATE TABLE smoke (id INTEGER PRIMARY KEY)")
    (runtime / ".env").write_text(
        "TENNIS_PROVIDER=composite\nODDS_PROVIDER=sportsbet\n",
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_launchctl = fake_bin / "launchctl"
    fake_launchctl.write_text('''#!/usr/bin/python3
import json, os, plistlib, sys
from pathlib import Path
root = Path(os.environ["WC_LAUNCH_AGENTS_DIR"])
label = "com.antigravity.central-wong-choi.research-review"
marker = root / "calendar-fault-injected"
with open(os.environ["TEST_LAUNCHCTL_CALLS"], "a") as output:
    output.write(json.dumps({"op": sys.argv[1], "after_foreign_write": marker.exists()}) + "\\n")
if sys.argv[1] == "print-disabled":
    print("disabled services = {\\n}")
if sys.argv[1] == "print" and not (root / (sys.argv[-1].rsplit("/", 1)[-1] + ".plist")).is_file():
    print("Could not find service", file=sys.stderr)
    raise SystemExit(113)
if (os.environ.get("TEST_BOUND_BOOTSTRAP_FAILURE") == "1" and sys.argv[1] == "bootstrap"
        and Path(sys.argv[-1]).stem == label):
    raise SystemExit(9)
if (os.environ["TEST_CALENDAR_MISMATCH"] == "1" and sys.argv[1] == "enable"
        and sys.argv[-1].endswith("/" + label) and not marker.exists()):
    path = root / (label + ".plist")
    payload = plistlib.loads(path.read_bytes())
    payload["StartCalendarInterval"] = {"Hour": 7, "Minute": 10}
    path.write_bytes(plistlib.dumps(payload))
    marker.touch()
''', encoding="utf-8")
    fake_launchctl.chmod(0o755)
    # Process discovery belongs to the fixture too: a real scheduled run on the
    # host must neither break the isolated success case nor satisfy its guard test.
    fake_pgrep = fake_bin / "pgrep"
    fake_pgrep.write_text(f"#!/bin/sh\nexit {0 if active_run else 1}\n", encoding="utf-8")
    fake_pgrep.chmod(0o755)
    fake_python = fake_bin / "tennis-python"
    fake_python.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_python.chmod(0o755)
    warm = tmp_path / "warm"
    warm.mkdir()
    research_python = fake_bin / "research-python"
    research_python.write_text('''#!/usr/bin/python3
import json, sys
from pathlib import Path
from datetime import datetime, timezone
script = Path(sys.argv.pop(1))
sys.path.insert(0, str(script.parent))
import central_research_review as review
if "--initialize" in sys.argv or "--status" in sys.argv:
    raise SystemExit(review.main())
state = Path(sys.argv[sys.argv.index("--state-root") + 1])
contract = review.load_runtime_contract()
import os
accepted = os.environ["TEST_RESEARCH_ACCEPTANCE"] == "1"
path = state / "runs" / "central" / "test" / "research-review" / "acceptance.json"
payload = {
    "schema_version": review.RUN_SCHEMA,
    "status": "succeeded" if accepted else "failed",
    "started_at": datetime.now(timezone.utc).isoformat(), "run_log": str(path),
    "evaluation_release_id": contract.evaluation_release_id,
    "evaluation_release_commit": contract.evaluation_release_commit,
    "model_promotion_allowed": False, "telegram_delivery_confirmed": False,
    "domains": {domain: {
        "disposition": "succeeded" if accepted else "blocked", "status": "fixture",
        "model_promotion_allowed": False, "telegram_delivery_confirmed": False,
    } for domain in contract.domains},
}
print(json.dumps(review._write_run(path, payload)))
raise SystemExit(0 if accepted else 1)
''', encoding="utf-8")
    research_python.chmod(0o755)
    au_runner = str(
        REPO_ROOT
        / ".agents/skills/au_racing/au_daily_auto/run_au_daily_schedule.sh"
    )
    au_auxiliary = str(
        REPO_ROOT
        / ".agents/skills/au_racing/au_daily_auto/run_au_auxiliary.sh"
    )
    au_labels = {
        "com.antigravity.au-wong-choi.bot": au_auxiliary,
        "com.antigravity.au-wong-choi.evening": au_runner,
        "com.antigravity.au-wong-choi.healthcheck": au_auxiliary,
        "com.antigravity.au-wong-choi.morning": au_runner,
    }
    for label, runner in au_labels.items():
        with (agents / f"{label}.plist").open("wb") as handle:
            plistlib.dump(
                {
                    "Label": label,
                    "ProgramArguments": ["/bin/zsh", runner],
                    "WorkingDirectory": str(REPO_ROOT),
                },
                handle,
            )
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(home),
            "PATH": f"{fake_bin}:{env.get('PATH', '')}",
            "WC_LAUNCH_AGENTS_DIR": str(agents),
            "WC_LAUNCHCTL_BIN": str(fake_launchctl),
            "WC_RUNTIME_NO_PROBE": "1",
            "WC_TENNIS_RUNTIME_ROOT": str(runtime),
            "TENNIS_PYTHON_BIN": str(fake_python),
            "TENNIS_ANALYSIS_OUTPUT_ROOT": str(tmp_path / "mirror"),
            "WC_RESEARCH_PYTHON_BIN": str(research_python),
            "TEST_RESEARCH_ACCEPTANCE": "1" if acceptance else "0",
            "TEST_CALENDAR_MISMATCH": "0" if calendar_ok else "1",
            "TEST_LAUNCHCTL_CALLS": str(tmp_path / "native-calls.jsonl"),
            "TEST_BOUND_BOOTSTRAP_FAILURE": "1" if attempt == "bound-bootstrap-failure" else "0",
            "WONGCHOI_CONTROL_STATE_ROOT": str(tmp_path / "control"),
            "WC_WARM_ARCHIVE_ROOT": str(warm),
            "WONGCHOI_AU_DATA_ROOT": str(tmp_path / "au"),
        }
    )

    install_arguments = []
    outer = tmp_path / "outer-snapshot"
    outer_proof = None
    foreign = agents / "com.antigravity.hkjc-wong-choi.prerace.plist"
    if attempt.startswith("outer"):
        captured = subprocess.run(["/bin/zsh", str(INSTALLER), "--snapshot", str(outer)],
                                  env=env, text=True, capture_output=True, timeout=30)
        assert captured.returncode == 0, captured.stderr
        outer_proof = (outer / ".launchd-state.json").read_bytes()
        expected_commit = subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True).strip()
        install_arguments = ["--install-from-snapshot", str(outer), "--expected-commit", expected_commit]
        if attempt == "outer-conflict":
            foreign.write_bytes(plistlib.dumps({"Label": foreign.stem, "ProgramArguments": ["/foreign/owner"]}))
    result = subprocess.run(
        ["/bin/zsh", str(INSTALLER), *install_arguments],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert "runtime cutover stage: interpreter preflight" in result.stdout
    assert "runtime cutover stage: active-run preflight" in result.stdout

    if attempt == "outer-conflict":
        assert result.returncode != 0
        assert plistlib.loads(foreign.read_bytes())["ProgramArguments"] == ["/foreign/owner"]
        assert pointer.read_bytes() == original_pointer
        assert (outer / ".launchd-state.json").read_bytes() == outer_proof
        assert not (outer / ".write-ownership").exists()
        assert "native recovery evidence retained:" in result.stderr
        calls = [json.loads(line) for line in (tmp_path / "native-calls.jsonl").read_text().splitlines()]
        assert not any(row["op"] in {"bootout", "bootstrap", "enable", "disable"} for row in calls)
        return
    if attempt == "bound-bootstrap-failure":
        assert result.returncode != 0
        assert "unified attempt owns recovery" in result.stderr
        assert "CRITICAL:" not in result.stderr
        assert pointer.read_bytes() == original_pointer
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        retained = list((tmp_path / "control/activation-recovery").glob("wc-native-attempt-*"))
        assert len(retained) == 1
        assert len(list((retained[0] / ".write-ownership").glob("*.begin.json"))) == 21
        return
    if active_run:
        assert result.returncode != 0
        assert "automation run is active; cutover deferred" in result.stderr
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        assert pointer.read_bytes() == original_pointer
        return
    if not acceptance:
        assert result.returncode != 0
        assert "runtime cutover failed" in result.stderr
        assert not (agents / "com.antigravity.central-wong-choi.research-review.plist").exists()
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        assert pointer.read_bytes() == original_pointer
        receipt = tmp_path / "control/runs/central/test/research-review/acceptance.json"
        assert '"status": "failed"' in receipt.read_text()
        return
    if not calendar_ok:
        assert result.returncode != 0
        assert "installed research calendar differs" in result.stdout
        assert "runtime cutover failed" in result.stderr
        # The fake native actor changed the published plist to an UNOWNED
        # calendar. Recovery must preserve it and all evidence, not erase it.
        foreign = agents / "com.antigravity.central-wong-choi.research-review.plist"
        assert plistlib.loads(foreign.read_bytes())["StartCalendarInterval"] == {"Hour": 7, "Minute": 10}
        assert "CRITICAL: launchd plist restore failed" in result.stderr
        assert "native recovery evidence retained:" in result.stderr
        snapshots = list((tmp_path / "control/activation-recovery").glob("wc-native-attempt-*"))
        assert len(snapshots) == 1
        assert (snapshots[0] / ".write-ownership/plan.json").exists()
        assert (snapshots[0] / ".launchd-state.json").exists()
        assert (snapshots[0] / ".tennis-db-pointer-original").read_bytes() == original_pointer
        assert pointer.read_text().strip() == str(runtime / "tennis_wc.db")
        calls = [json.loads(line) for line in (tmp_path / "native-calls.jsonl").read_text().splitlines()]
        assert not any(row["after_foreign_write"] and row["op"] in {"bootout", "bootstrap", "enable", "disable"}
                       for row in calls)
        return
    assert result.returncode == 0, result.stdout + result.stderr
    stages = [line.removeprefix("runtime cutover stage: ")
              for line in result.stdout.splitlines()
              if line.startswith("runtime cutover stage: ")]
    assert stages == ["NBA result timer preflight", "interpreter preflight", "SQLite preflight", "active-run preflight",
                      "AU preflight", "snapshot", "HKJC installer", "NBA installer",
                      "Tennis installer", "Central installer", "calendar verification",
                      "loaded runtime verification"]
    installed = plistlib.loads((agents / "com.antigravity.central-wong-choi.research-review.plist").read_bytes())
    template = plistlib.loads((INSTALLER.parent / "launchd/com.antigravity.central-wong-choi.research-review.plist.template").read_bytes())
    assert installed["StartCalendarInterval"] == template["StartCalendarInterval"]
    assert "production runtime cutover verified" in result.stdout
    if attempt == "outer":
        assert (outer / ".launchd-state.json").read_bytes() == outer_proof
        plan = json.loads((outer / ".write-ownership/plan.json").read_text())
        assert plan["snapshot_root"] == str(outer.resolve())
        assert len(list((outer / ".write-ownership").glob("*.begin.json"))) == 21
        assert not list((tmp_path / "control/activation-recovery").glob("wc-native-attempt-*"))
    assert (home / ".wongchoi_tennis_db").read_text(encoding="utf-8").strip() == str(
        runtime / "tennis_wc.db"
    )


@pytest.mark.parametrize("fault", ["interrupt", "copyfail", "bootstrapfail", "concurrent", "none"])
def test_research_installer_interruption_and_publication_rollback(tmp_path: Path, fault: str) -> None:
    # Exercise the real installer, but never host launchd or production evidence.
    skill = tmp_path / "repo/.agents/skills/central_wong_choi"
    (skill / "scripts").mkdir(parents=True)
    (skill / "launchd").mkdir()
    shared = skill.parent / "shared_wong_choi"
    shared.mkdir()
    shutil.copyfile(REPO_ROOT / ".agents/skills/shared_wong_choi/runtime_cutover_lease.py",
                    shared / "runtime_cutover_lease.py")
    installer = skill / "install_research_review.sh"
    shutil.copyfile(INSTALLER.parent / installer.name, installer)
    label = "com.antigravity.central-wong-choi.research-review"
    shutil.copyfile(INSTALLER.parent / "launchd" / f"{label}.plist.template", skill / "launchd" / f"{label}.plist.template")
    (skill / "scripts/run_central_research_review.sh").write_text(
        '#!/bin/sh\ncase "$1" in --initialize|--status) exit 0;; esac\nprintf \'{"run_log":"fixture-receipt"}\\n\'\n', encoding="utf-8"
    )
    agents = tmp_path / "agents"
    agents.mkdir()
    dest = agents / f"{label}.plist"
    old = b"old research plist\n"
    dest.write_bytes(old)
    loaded = tmp_path / "loaded"
    loaded.touch()
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    launchctl = fake_bin / "launchctl"
    launchctl.write_text('''#!/usr/bin/python3
import os, signal, sys
from pathlib import Path
root = Path(os.environ["TEST_INSTALL_ROOT"])
loaded = root / "loaded"
once = root / "injected"
dest = Path(os.environ["TEST_INSTALL_DEST"])
fault = os.environ["TEST_INSTALL_FAULT"]
op = sys.argv[1]
with (root / "calls").open("a") as output:
    output.write(op + "\\n")
if op == "print":
    raise SystemExit(0 if loaded.exists() else 1)
if op == "bootout":
    loaded.unlink(missing_ok=True)
    if fault == "interrupt" and not once.exists():
        once.touch()
        os.kill(os.getppid(), signal.SIGTERM)
if op == "bootstrap":
    if fault in ("bootstrapfail", "concurrent") and not once.exists():
        once.touch()
        if fault == "concurrent":
            dest.write_bytes(b"other session plist\\n")
        raise SystemExit(1)
    loaded.touch()
''', encoding="utf-8")
    launchctl.chmod(0o755)
    fake_cp = fake_bin / "cp"
    fake_cp.write_text('''#!/usr/bin/python3
import os, subprocess, sys
from pathlib import Path
if os.environ["TEST_INSTALL_FAULT"] == "copyfail" and any(arg.endswith("/candidate.plist") for arg in sys.argv[1:]):
    Path(sys.argv[-1]).write_bytes(b"partial copy")
    raise SystemExit(1)
raise SystemExit(subprocess.call(["/bin/cp", *sys.argv[1:]]))
''', encoding="utf-8")
    fake_cp.chmod(0o755)
    env = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
           "WC_LAUNCH_AGENTS_DIR": str(agents), "WC_LAUNCHCTL_BIN": str(launchctl),
           "TEST_INSTALL_ROOT": str(tmp_path), "TEST_INSTALL_DEST": str(dest), "TEST_INSTALL_FAULT": fault}
    result = subprocess.run(["/bin/zsh", str(installer)], env=env, capture_output=True, text=True, timeout=30)
    assert (tmp_path / "calls").exists(), "fixture must reach native command boundary"
    if fault == "none":
        assert result.returncode == 0, result.stderr
        assert plistlib.loads(dest.read_bytes())["Label"] == label
        assert loaded.exists()
    elif fault == "concurrent":
        assert result.returncode != 0
        assert dest.read_bytes() == b"other session plist\n"
        assert "rollback blocked" in result.stderr
    else:
        assert result.returncode != 0
        assert dest.read_bytes() == old
        assert loaded.exists(), "failed install must restore the previously loaded job"



@pytest.mark.parametrize("command", [
    "python3 hkjc_daily_schedule.py --mode prerace",
    "/usr/bin/python3 -X dev ./nba_daily_schedule.py --mode postgame",
    "/Framework/Python -W ignore -u /repo/tennis_preclose_refresh.py",
    "python3 -m tennis_daily_schedule --mode daily",
    "python3 ./central_daily_maintenance.py",
    "python3 -X faulthandler ./central_research_review.py",
    "python3 ./au_daily_schedule.py",
    "python3 ./au_healthcheck.py",
    "/bin/zsh ./run_central_research_review.sh",
    "/bin/bash -e ./run_hkjc_daily_schedule.sh",
])
def test_active_run_guard_covers_scheduled_entrypoints(command):
    import re
    script = INSTALLER.read_text()
    pattern = re.search(r"if pgrep -f '([^']+)'", script).group(1)
    pattern = pattern.replace('[[:space:]]', r'\s').replace('[^[:space:]]', r'\S')
    assert re.search(pattern, command), command


def test_active_run_guard_does_not_confuse_release_scope_paths_with_running_jobs():
    import re
    pattern = re.search(r"if pgrep -f '([^']+)'", INSTALLER.read_text()).group(1)
    pattern = pattern.replace('[[:space:]]', r'\s').replace('[^[:space:]]', r'\S')
    for command in (
        '/usr/bin/python3 /repo/scoped_release.py --path .agents/skills/nba/nba_daily_auto/nba_daily_schedule.py',
        'python3 -m pytest tests/test_nba_daily_schedule.py',
        'python3 unrelated.py /repo/central_research_review.py',
        '/bin/zsh /repo/保存.sh --path /repo/run_hkjc_daily_schedule.sh',
    ):
        assert not re.search(pattern, command), command


@pytest.mark.parametrize("probe_status", [0, 1, 2, 127])
def test_native_active_preflight_fails_closed_on_probe_error(tmp_path, probe_status):
    script = INSTALLER.read_text()
    start = script.index('print -r -- "runtime cutover stage: active-run preflight"')
    end = script.index('# AU must already', start)
    probe = tmp_path / 'pgrep'
    probe.write_text('#!/bin/sh\nexit ' + str(probe_status) + '\n')
    probe.chmod(0o755)
    result = subprocess.run(['/bin/zsh', '-c', 'set -eu\n' + script[start:end]],
                            env={**os.environ, 'PATH': str(tmp_path) + ':/usr/bin:/bin'},
                            text=True, capture_output=True)
    assert (result.returncode == 0) == (probe_status == 1), result.stderr
    if probe_status not in (0, 1):
        assert 'process discovery failed' in result.stderr


@pytest.mark.parametrize("defect", ["missing-marker", "symlink-marker", "wrong-sha", "missing-sha"])
def test_bound_native_attempt_rejects_invalid_marker_or_sha_before_preflights(tmp_path, defect):
    home = tmp_path / "home"
    home.mkdir()
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir(mode=0o700)
    protected = tmp_path / "protected"
    protected.write_bytes(b"unrelated evidence")
    if defect == "symlink-marker":
        (snapshot / ".complete").symlink_to(protected)
    elif defect not in {"missing-marker"}:
        (snapshot / ".complete").touch()
    commit = subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"], text=True).strip()
    args = ["--install-from-snapshot", str(snapshot)]
    if defect != "missing-sha":
        args += ["--expected-commit", "0" * 40 if defect == "wrong-sha" else commit]
    env = {**os.environ, "HOME": str(home), "WONGCHOI_CONTROL_STATE_ROOT": str(tmp_path / "control")}
    result = subprocess.run(["/bin/zsh", str(INSTALLER), *args], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "runtime cutover stage:" not in result.stdout
    assert not (home / "Library/LaunchAgents").exists()
    assert protected.read_bytes() == b"unrelated evidence"
    assert not (snapshot / ".write-ownership").exists()


@pytest.mark.parametrize("command,expected", [
    ("python3 -X dev ./nba_daily_schedule.py", True),
    ("python3 -Xdev -W ignore ./tennis_preclose_refresh.py", True),
    ("python3 -u -m package.central_research_review", True),
    ("/bin/zsh -f ./run_central_daily_maintenance.sh", True),
    ("python3 -- ./au_healthcheck.py", True),
    ("python3 scoped_release.py --path ./nba_daily_schedule.py", False),
    ("python3 -m pytest tests/test_tennis_preclose_refresh.py", False),
    ("/bin/zsh 保存.sh --path ./run_nba_daily_schedule.sh", False),
])
def test_native_guard_pattern_uses_real_extended_regex(command, expected):
    import re
    pattern = re.search(r"if pgrep -f '([^']+)'", INSTALLER.read_text()).group(1)
    result = subprocess.run(['/usr/bin/grep', '-E', pattern], input=command + '\n',
                            text=True, capture_output=True)
    assert result.returncode in (0, 1), result.stderr
    assert (result.returncode == 0) == expected


def test_actual_native_preflight_detects_owned_relative_x_process(tmp_path):
    # This is a harmless owned sleeper, never a real scheduler or launchd job.
    import time
    sleeper = tmp_path / 'central_research_review.py'
    sleeper.write_text('import time\ntime.sleep(60)\n')
    process = subprocess.Popen([sys.executable, '-X', 'dev', './' + sleeper.name], cwd=tmp_path)
    try:
        time.sleep(0.1)
        assert process.poll() is None
        script = INSTALLER.read_text()
        start = script.index('print -r -- "runtime cutover stage: active-run preflight"')
        end = script.index('# AU must already', start)
        result = subprocess.run(['/bin/zsh', '-c', 'set -eu\n' + script[start:end]],
                                text=True, capture_output=True)
        assert result.returncode != 0
        assert 'automation run is active; cutover deferred' in result.stderr
    finally:
        process.terminate()
        process.wait(timeout=10)
