from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_DIR / "scripts" / "install_macos_launchd.sh"


def test_rendered_launchd_uses_versioned_code_and_existing_runtime(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "tennis_wc.db").write_bytes(b"not opened during render")
    destination = tmp_path / "LaunchAgents"
    mirror = tmp_path / "mirror"
    env = os.environ.copy()
    env.update(
        {
            "WC_TENNIS_RUNTIME_ROOT": str(runtime),
            "TENNIS_LOG_DIR": str(runtime / "data" / "logs"),
            "TENNIS_ANALYSIS_OUTPUT_ROOT": str(mirror),
        }
    )

    subprocess.run(
        ["/bin/zsh", str(INSTALLER), "--render-only", str(destination)],
        cwd=PROJECT_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    card = plistlib.load(
        (destination / "com.antigravity.tennis-wong-choi.card.plist").open("rb")
    )
    daily = plistlib.load(
        (destination / "com.antigravity.tennis-wong-choi.daily.plist").open("rb")
    )
    recovery = plistlib.load(
        (destination / "com.antigravity.tennis-wong-choi.recovery.plist").open("rb")
    )
    runner = str(PROJECT_DIR / "scripts" / "run_tennis_daily_schedule.sh")
    database_url = f"sqlite:///{runtime / 'tennis_wc.db'}"
    for payload in (card, daily, recovery):
        assert payload["WorkingDirectory"] == str(PROJECT_DIR)
        assert payload["EnvironmentVariables"]["DATABASE_URL"] == database_url
        assert payload["EnvironmentVariables"]["TENNIS_LOG_DIR"] == str(
            runtime / "data" / "logs"
        )
        assert payload["EnvironmentVariables"]["TENNIS_ANALYSIS_OUTPUT_ROOT"] == str(
            mirror
        )
    assert card["ProgramArguments"][:3] == ["/bin/zsh", runner, "card"]
    assert daily["ProgramArguments"][:2] == ["/bin/zsh", runner]
    assert recovery["ProgramArguments"] == [
        "/usr/bin/python3",
        str(PROJECT_DIR / "scripts" / "tennis_card_recovery.py"),
    ]
