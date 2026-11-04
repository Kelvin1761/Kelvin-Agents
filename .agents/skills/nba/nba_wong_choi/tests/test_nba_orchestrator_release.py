from __future__ import annotations

import sys
from pathlib import Path


NBA_SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_SKILL_DIR))

from nba_orchestrator import _release_action


def test_failed_auto_run_never_releases_dashboard() -> None:
    assert _release_action(passed=True, failed=True, sgm_ok=True) == "blocked"


def test_release_requires_at_least_one_passed_game() -> None:
    assert _release_action(passed=False, failed=False, sgm_ok=True) == "blocked"


def test_release_requires_the_sgm_summary() -> None:
    assert _release_action(passed=True, failed=False, sgm_ok=False) == "blocked"


def test_release_deploys_only_complete_pipeline() -> None:
    assert _release_action(passed=True, failed=False, sgm_ok=True) == "deploy"
