from __future__ import annotations

import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.release_policy import (
    ReleaseRisk,
    activation_plan,
    classify_release,
)


def test_docs_only_can_auto_merge_after_quick_gate() -> None:
    policy = classify_release(["docs/architecture/adr-003.md", "tests/test_docs.py"])
    assert policy.risk is ReleaseRisk.DOCS_TESTS
    assert policy.check == "quick"
    assert policy.auto_push is True
    assert policy.auto_merge is True
    assert policy.auto_activate is False


@pytest.mark.parametrize(
    ("path", "risk"),
    [
        (
            ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine/scoring.py",
            ReleaseRisk.MODEL,
        ),
        ("docs/model-evaluation-contract.md", ReleaseRisk.EVALUATION),
        (
            ".agents/skills/nba/nba_daily_auto/nba_daily_schedule.py",
            ReleaseRisk.AUTOMATION,
        ),
        ("Horse_Racing_Dashboard/deploy.sh", ReleaseRisk.DEPLOYMENT),
        ("wongchoi_paths.py", ReleaseRisk.CODE),
    ],
)
def test_risky_scope_pushes_but_never_auto_merges(path: str, risk: ReleaseRisk) -> None:
    policy = classify_release([path])
    assert policy.risk is risk
    assert policy.check == "full"
    assert policy.auto_push is True
    assert policy.auto_merge is False
    assert policy.auto_activate is False


def test_highest_risk_wins_for_mixed_scope() -> None:
    policy = classify_release(
        ["docs/readme.md", "tests/test_x.py", "Horse_Racing_Dashboard/deploy.sh"]
    )
    assert policy.risk is ReleaseRisk.DEPLOYMENT


def test_empty_or_parent_scope_is_rejected() -> None:
    with pytest.raises(ValueError):
        classify_release([])
    with pytest.raises(ValueError):
        classify_release(["../outside"])


def test_activation_plan_routes_shared_code_to_four_domains() -> None:
    plan = activation_plan([".agents/skills/shared_wong_choi/central_status.py"])
    assert plan["production_sync_domains"] == ["au", "hkjc", "nba", "tennis"]
    assert plan["dashboard_deploy"] is False


def test_activation_plan_marks_dashboard_and_launchd_installer() -> None:
    plan = activation_plan(
        [
            "Horse_Racing_Dashboard/app.js",
            ".agents/skills/nba/nba_daily_auto/install_macos_launchd.sh",
        ]
    )
    assert plan["dashboard_deploy"] is True
    assert plan["manual_required"] is True
    assert plan["production_sync_domains"] == ["nba"]
