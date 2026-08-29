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
