from __future__ import annotations

import os
import plistlib
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[4]
INSTALLER = (
    REPO_ROOT
    / ".agents/skills/central_wong_choi/install_production_runtime.sh"
)


def test_runtime_installer_snapshot_restore_is_exact_and_idempotent(
    tmp_path: Path,
) -> None:
    agents = tmp_path / "LaunchAgents"
    agents.mkdir()
    snapshot = tmp_path / "snapshot"
    fake_launchctl = tmp_path / "launchctl"
    fake_launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_launchctl.chmod(0o755)
    existing = agents / "com.antigravity.hkjc-wong-choi.prerace.plist"
    introduced = agents / "com.antigravity.nba-wong-choi.health.plist"
    existing.write_text("old plist\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "WC_LAUNCH_AGENTS_DIR": str(agents),
            "WC_LAUNCHCTL_BIN": str(fake_launchctl),
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


@pytest.mark.parametrize("active_run,acceptance", [(False, True), (True, True), (False, False)])
def test_runtime_installer_full_cutover_in_isolated_home(tmp_path: Path, active_run: bool, acceptance: bool) -> None:
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
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
    fake_launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
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

    if active_run:
        assert result.returncode != 0
        assert "automation run is active; cutover deferred" in result.stderr
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        return
    if not acceptance:
        assert result.returncode != 0
        assert "runtime cutover failed" in result.stderr
        assert not (agents / "com.antigravity.central-wong-choi.research-review.plist").exists()
        assert {p.stem for p in agents.glob("*.plist")} == set(au_labels)
        receipt = tmp_path / "control/runs/central/test/research-review/acceptance.json"
        assert '"status": "failed"' in receipt.read_text()
        return
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production runtime cutover verified" in result.stdout
    assert (home / ".wongchoi_tennis_db").read_text(encoding="utf-8").strip() == str(
        runtime / "tennis_wc.db"
    )


@pytest.mark.parametrize("fault", ["interrupt", "copyfail", "bootstrapfail", "concurrent", "none"])
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
