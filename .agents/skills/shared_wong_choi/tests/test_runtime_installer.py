from __future__ import annotations

import os
import subprocess
from pathlib import Path


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
