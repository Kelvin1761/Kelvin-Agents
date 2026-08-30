from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parents[1]
INSTALLER = PROJECT_DIR / "scripts" / "install_macos_launchd.sh"


def test_rendered_launchd_uses_versioned_code_and_existing_runtime(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    (runtime / "tennis_wc.db").write_bytes(b"not opened during render")
    (runtime / ".env").write_text(
        "TENNIS_PROVIDER=composite\nODDS_PROVIDER=sportsbet\n",
        encoding="utf-8",
    )
    destination = tmp_path / "LaunchAgents"
    mirror = tmp_path / "mirror"
    python_bin = runtime / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    python_bin.chmod(0o755)
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
        assert payload["EnvironmentVariables"]["TENNIS_ENV_FILE"] == str(
            runtime / ".env"
        )
        assert payload["EnvironmentVariables"]["TENNIS_PYTHON_BIN"] == str(
            python_bin
        )
        assert payload["EnvironmentVariables"]["TENNIS_LOG_DIR"] == str(
            runtime / "data" / "logs"
        )
        assert payload["EnvironmentVariables"]["TENNIS_ANALYSIS_OUTPUT_ROOT"] == str(
            mirror
        )
    assert card["ProgramArguments"][:3] == ["/bin/zsh", runner, "card"]
    assert daily["ProgramArguments"][:2] == ["/bin/zsh", runner]
    assert recovery["ProgramArguments"] == [
        str(python_bin),
        str(PROJECT_DIR / "scripts" / "tennis_card_recovery.py"),
    ]

    cli_env = os.environ.copy()
    cli_env.pop("TENNIS_PROVIDER", None)
    cli_env.pop("ODDS_PROVIDER", None)
    cli_env.update(
        {
            "DATABASE_URL": database_url,
            "PYTHONPATH": str(PROJECT_DIR / "src"),
            "TENNIS_ENV_FILE": str(runtime / ".env"),
        }
    )
    config = subprocess.run(
        [sys.executable, "-m", "tennis_wc.cli", "config-check"],
        cwd=PROJECT_DIR,
        env=cli_env,
        text=True,
        capture_output=True,
        check=True,
    )
    config_payload = json.loads(config.stdout)
    assert config_payload["tennis_provider"] == "composite"
    assert config_payload["odds_provider"] == "sportsbet"
