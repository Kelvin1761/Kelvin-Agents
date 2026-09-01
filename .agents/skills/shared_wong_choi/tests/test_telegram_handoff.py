from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
HANDOFF = (
    REPO_ROOT
    / ".agents/skills/central_wong_choi/bootstrap_telegram_approval.sh"
)


def test_handoff_accepts_dedicated_worktree_git_file(tmp_path: Path) -> None:
    production = tmp_path / "production"
    production.mkdir()
    (production / ".git").write_text(
        "gitdir: /tmp/example-worktree\n", encoding="utf-8"
    )
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.antigravity.au-wong-choi.bot.plist").write_text(
        "placeholder\n", encoding="utf-8"
    )
    env = os.environ.copy()
    env.update({"HOME": str(tmp_path), "WC_PRODUCTION_ROOT": str(production)})
    env.pop("WC_NOTIFY_TELEGRAM_TOKEN", None)
    env.pop("WC_NOTIFY_TELEGRAM_CHAT", None)

    result = subprocess.run(
        ["/bin/zsh", str(HANDOFF), "a" * 12],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Telegram credentials are not configured" in result.stderr
    assert "production checkout missing" not in result.stderr


def test_handoff_polling_loop_and_cleanup_execute_without_zsh_runtime_error(
    tmp_path: Path,
) -> None:
    production = tmp_path / "production"
    production.mkdir()
    (production / ".git").write_text(
        "gitdir: /tmp/example-worktree\n", encoding="utf-8"
    )
    agents = tmp_path / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    (agents / "com.antigravity.au-wong-choi.bot.plist").write_text(
        "placeholder\n", encoding="utf-8"
    )
    fake_launchctl = tmp_path / "launchctl"
    fake_launchctl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fake_launchctl.chmod(0o755)
    fake_bot = tmp_path / "bot.py"
    fake_bot.write_text("print('processed test poll')\n", encoding="utf-8")
    fake_notifier = tmp_path / "notifier.py"
    fake_notifier.write_text("raise SystemExit(0)\n", encoding="utf-8")
    fake_status = tmp_path / "status.py"
    fake_status.write_text("print('no activation yet')\n", encoding="utf-8")
    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path),
            "WC_PRODUCTION_ROOT": str(production),
            "WC_NOTIFY_TELEGRAM_TOKEN": "test-token",
            "WC_NOTIFY_TELEGRAM_CHAT": "123",
            "WC_LAUNCHCTL_BIN": str(fake_launchctl),
            "WC_BOOTSTRAP_BOT": str(fake_bot),
            "WC_BOOTSTRAP_NOTIFIER": str(fake_notifier),
            "WC_BOOTSTRAP_STATUS_CLI": str(fake_status),
            "WC_BOOTSTRAP_MAX_ATTEMPTS": "1",
            "WC_BOOTSTRAP_SLEEP_SECONDS": "0",
        }
    )

    result = subprocess.run(
        ["/bin/zsh", str(HANDOFF), "b" * 12],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "processed test poll" in result.stdout
    assert "approval window timed out" in result.stderr
    assert "read-only variable" not in result.stderr
