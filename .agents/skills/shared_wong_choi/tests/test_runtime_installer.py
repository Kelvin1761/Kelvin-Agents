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


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALLER = (
    REPO_ROOT
    / ".agents/skills/central_wong_choi/install_production_runtime.sh"
)

# Models real launchd: `bootout` of a running job returns while it is still
# exiting (`print` keeps succeeding for a few polls) and `bootstrap` fails with
# exit 5 until the unload has finished. Every call is logged.
STATEFUL_LAUNCHCTL = """#!/usr/bin/python3
import os, sys
from pathlib import Path
root = Path(os.environ["TEST_LAUNCHD_STATE"])
root.mkdir(exist_ok=True)
with (root / "calls.log").open("a") as log:
    log.write(" ".join(sys.argv[1:]) + "\\n")
op, label = sys.argv[1], sys.argv[-1].rsplit("/", 1)[-1].removesuffix(".plist")
loaded, exiting = root / f"{label}.loaded", root / f"{label}.exiting"
stuck = os.environ.get("TEST_LAUNCHD_STUCK", "")
def draining():
    if not exiting.exists():
        return False
    left = int(exiting.read_text())
    if left <= 0 and label != stuck:
        exiting.unlink()
        return False
    exiting.write_text(str(max(left - 1, 0)))
    return True
if op == "print":
    raise SystemExit(0 if loaded.exists() or draining() else 113)
if op == "bootout":
    if loaded.exists():
        loaded.unlink()
        exiting.write_text(os.environ.get("TEST_LAUNCHD_EXIT_POLLS", "3"))
    raise SystemExit(0)
if op == "bootstrap":
    if loaded.exists() or draining():
        raise SystemExit(5)
    loaded.touch()
raise SystemExit(0)
"""


def _stateful_launchctl(tmp_path: Path) -> tuple[Path, Path]:
    fake = tmp_path / "stateful-launchctl"
    fake.write_text(STATEFUL_LAUNCHCTL, encoding="utf-8")
    fake.chmod(0o755)
    return fake, tmp_path / "launchd-state"


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
    fake_launchctl, launchd_state = _stateful_launchctl(tmp_path)
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
            "TEST_LAUNCHD_STATE": str(launchd_state),
            "WC_RESTORE_POLL_SECONDS": "0.01",
            "WC_RESTORE_RETRY_SECONDS": "0.01",
        }
    )

    subprocess.run(
        ["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    existing.write_text("candidate plist\n", encoding="utf-8")
    introduced.write_text("new plist\n", encoding="utf-8")
    pointer.write_text(str(runtime / "tennis_wc.db") + "\n", encoding="utf-8")

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

    # A pre-change snapshot has no pointer proof; never guess what it contained.
    for metadata in snapshot.glob(".tennis-db-pointer-*"):
        metadata.unlink()
    pointer.write_bytes(b"newer-config-outside-legacy-snapshot\n")
    subprocess.run(["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
                   env=env, capture_output=True, text=True, check=True)
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
    launchctl.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 0\n')
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


@pytest.mark.parametrize("active_run,acceptance,calendar_ok", [
    (False, True, True), (True, True, True), (False, False, True), (False, True, False),
])
def test_runtime_installer_full_cutover_in_isolated_home(tmp_path: Path, active_run: bool, acceptance: bool, calendar_ok: bool) -> None:
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
import os, plistlib, sys
from pathlib import Path
root = Path(os.environ["WC_LAUNCH_AGENTS_DIR"])
label = "com.antigravity.central-wong-choi.research-review"
marker = root / "calendar-fault-injected"
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
import json, os, sys
from pathlib import Path
script = Path(sys.argv.pop(1))
sys.path.insert(0, str(script.parent))
import central_research_review as review
if "--initialize" in sys.argv and os.environ["TEST_RESEARCH_ACCEPTANCE"] != "1":
    print(json.dumps({"status": "blocked"}))
    raise SystemExit(1)
if "--initialize" in sys.argv or "--status" in sys.argv:
    raise SystemExit(review.main())
# Activation must never run a review pass (40-60 min; 2026-11 timeouts).
Path(os.environ["TEST_FULL_PASS_MARKER"]).touch()
raise SystemExit(99)
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
            "TEST_FULL_PASS_MARKER": str(tmp_path / "full-pass-ran"),
            "TEST_CALENDAR_MISMATCH": "0" if calendar_ok else "1",
            "WONGCHOI_CONTROL_STATE_ROOT": str(tmp_path / "control"),
            "WC_WARM_ARCHIVE_ROOT": str(warm),
            "WONGCHOI_AU_DATA_ROOT": str(tmp_path / "au"),
        }
    )

    result = subprocess.run(
        ["/bin/zsh", str(INSTALLER)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert "runtime cutover stage: interpreter preflight" in result.stdout
    assert "runtime cutover stage: active-run preflight" in result.stdout
    assert not (tmp_path / "full-pass-ran").exists()

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
        assert '"status": "blocked"' in result.stdout
        return
    if not calendar_ok:
        assert result.returncode != 0
        assert "installed research calendar differs" in result.stdout
        assert "runtime cutover failed" in result.stderr
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        assert pointer.read_bytes() == original_pointer
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
    assert (home / ".wongchoi_tennis_db").read_text(encoding="utf-8").strip() == str(
        runtime / "tennis_wc.db"
    )


@pytest.mark.parametrize("fault", ["interrupt", "copyfail", "bootstrapfail", "concurrent", "statusfail", "none"])
def test_research_installer_interruption_and_publication_rollback(tmp_path: Path, fault: str) -> None:
    # Exercise the real installer, but never host launchd or production evidence.
    skill = tmp_path / "repo/.agents/skills/central_wong_choi"
    (skill / "scripts").mkdir(parents=True)
    (skill / "launchd").mkdir()
    installer = skill / "install_research_review.sh"
    shutil.copyfile(INSTALLER.parent / installer.name, installer)
    label = "com.antigravity.central-wong-choi.research-review"
    shutil.copyfile(INSTALLER.parent / "launchd" / f"{label}.plist.template", skill / "launchd" / f"{label}.plist.template")
    (skill / "scripts/run_central_research_review.sh").write_text(
        '#!/bin/sh\ncase "$1" in --initialize) exit 0;; --status) [ "$TEST_INSTALL_FAULT" = statusfail ] && exit 1; exit 0;; esac\nexit 99\n', encoding="utf-8"
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



def test_active_run_guard_does_not_confuse_release_scope_paths_with_running_jobs():
    import re
    script=INSTALLER.read_text()
    pattern=re.search(r"if pgrep -f '([^']+)'",script).group(1)
    python_pattern=pattern.replace('[[:space:]]',r'\s').replace('[^[:space:]]',r'\S')
    assert re.search(python_pattern,'/usr/bin/python3 /repo/.agents/skills/nba/nba_daily_auto/nba_daily_schedule.py --mode postgame')
    assert re.search(python_pattern,'/Framework/Python -u /repo/tennis_daily_schedule.py --mode daily')
    assert not re.search(python_pattern,'/usr/bin/python3 /repo/scoped_release.py --path .agents/skills/nba/nba_daily_auto/nba_daily_schedule.py')
    assert not re.search(python_pattern,'python3 -m pytest tests/test_nba_daily_schedule.py')


def _restore_fixture(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path]:
    agents = tmp_path / "agents"
    agents.mkdir()
    fake, state = _stateful_launchctl(tmp_path)
    state.mkdir()
    env = {**os.environ, "WC_LAUNCH_AGENTS_DIR": str(agents), "WC_LAUNCHCTL_BIN": str(fake),
           "WC_TENNIS_DB_POINTER": str(tmp_path / "pointer"),
           "WC_TENNIS_RUNTIME_ROOT": str(tmp_path / "runtime"), "TEST_LAUNCHD_STATE": str(state),
           "WC_RESTORE_POLL_SECONDS": "0.01", "WC_RESTORE_RETRY_SECONDS": "0.01",
           "WC_RESTORE_UNLOAD_POLLS": "20"}
    return env, agents, state, tmp_path / "snapshot"


def test_restore_waits_for_async_bootout_and_leaves_unchanged_running_jobs(tmp_path):
    """2026-11-10 regression: rollback must not kill an unchanged RunAtLoad job
    and must survive launchd's asynchronous bootout of a changed one."""
    env, agents, state, snapshot = _restore_fixture(tmp_path)
    startup = "com.antigravity.hkjc-wong-choi.startup"
    prerace = "com.antigravity.hkjc-wong-choi.prerace"
    introduced = "com.antigravity.tennis-wong-choi.settle"
    for label in (startup, prerace):
        (agents / f"{label}.plist").write_text(f"old {label}\n")
        (state / f"{label}.loaded").touch()
    subprocess.run(["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
                   env=env, capture_output=True, text=True, check=True)
    # Candidate: startup rewritten byte-identical and running again, prerace
    # changed, settle newly introduced and loaded.
    (agents / f"{prerace}.plist").write_text("candidate prerace\n")
    (agents / f"{introduced}.plist").write_text("new settle\n")
    (state / f"{introduced}.loaded").touch()
    (state / "calls.log").unlink(missing_ok=True)

    result = subprocess.run(["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
                            env=env, capture_output=True, text=True, timeout=60)

    assert result.returncode == 0, result.stderr
    calls = (state / "calls.log").read_text().splitlines()
    assert not any(c.startswith("bootout") and c.endswith(startup) for c in calls)
    assert (state / f"{startup}.loaded").exists()
    assert (agents / f"{prerace}.plist").read_text() == f"old {prerace}\n"
    assert (state / f"{prerace}.loaded").exists()
    assert not (agents / f"{introduced}.plist").exists()
    assert not (state / f"{introduced}.loaded").exists()


def test_restore_reports_the_label_that_never_unloads(tmp_path):
    env, agents, state, snapshot = _restore_fixture(tmp_path)
    stuck = "com.antigravity.nba-wong-choi.health"
    other = "com.antigravity.nba-wong-choi.warmup"
    for label in (stuck, other):
        (agents / f"{label}.plist").write_text(f"old {label}\n")
        (state / f"{label}.loaded").touch()
    subprocess.run(["/bin/zsh", str(INSTALLER), "--snapshot", str(snapshot)],
                   env=env, capture_output=True, text=True, check=True)
    for label in (stuck, other):
        (agents / f"{label}.plist").write_text("candidate\n")

    result = subprocess.run(["/bin/zsh", str(INSTALLER), "--restore", str(snapshot)],
                            env={**env, "TEST_LAUNCHD_STUCK": stuck},
                            capture_output=True, text=True, timeout=60)

    assert result.returncode == 1
    assert f"restore: {stuck} still loaded after bootout" in result.stderr
    # One stuck label must not stop the others from being restored.
    assert (agents / f"{other}.plist").read_text() == f"old {other}\n"
    assert (state / f"{other}.loaded").exists()
