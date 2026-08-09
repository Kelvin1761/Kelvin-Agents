from __future__ import annotations

import sys
from pathlib import Path


NBA_SKILL_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NBA_SKILL_DIR))

from nba_orchestrator import _pipeline_release_action


def test_failed_auto_run_never_releases_dashboard() -> None:
    assert (
        _pipeline_release_action(
            passed=True,
            failed=True,
            fill_count=0,
            sgm_exists=True,
        )
        == "blocked"
    )


def test_release_requires_at_least_one_passed_game() -> None:
    assert (
        _pipeline_release_action(
            passed=False,
            failed=False,
            fill_count=0,
            sgm_exists=True,
        )
        == "blocked"
    )


def test_release_waits_for_fill_and_compile_stages() -> None:
    assert (
        _pipeline_release_action(
            passed=True,
            failed=False,
            fill_count=2,
            sgm_exists=False,
        )
        == "fill"
    )
    assert (
        _pipeline_release_action(
            passed=True,
            failed=False,
            fill_count=0,
            sgm_exists=False,
        )
        == "compile"
    )


def test_release_deploys_only_complete_pipeline() -> None:
    assert (
        _pipeline_release_action(
            passed=True,
            failed=False,
            fill_count=0,
            sgm_exists=True,
        )
        == "deploy"
    )
