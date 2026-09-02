from __future__ import annotations

import os
import plistlib
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


@pytest.mark.parametrize("active_run", [False, True])
def test_runtime_installer_full_cutover_in_isolated_home(tmp_path: Path, active_run: bool) -> None:
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
    assert result.returncode == 0, result.stdout + result.stderr
    assert "production runtime cutover verified" in result.stdout
    assert (home / ".wongchoi_tennis_db").read_text(encoding="utf-8").strip() == str(
        runtime / "tennis_wc.db"
    )
