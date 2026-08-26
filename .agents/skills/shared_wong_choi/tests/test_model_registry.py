from __future__ import annotations

import sys
from pathlib import Path

import pytest


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE_ROOT.parent))

from shared_wong_choi.contracts import Domain  # noqa: E402
from shared_wong_choi.evidence import ReleaseStage  # noqa: E402
from shared_wong_choi.model_registry import (  # noqa: E402
    ModelPromotionError,
    ModelRegistry,
    ModelReleaseRequest,
    bootstrap_current_models,
)


SHA = "a" * 40


def request(stage: ReleaseStage, **changes) -> ModelReleaseRequest:
    values = {
        "domain": Domain.AU,
        "model_id": "au-matrix",
        "code_commit": SHA,
        "evaluation_contract_version": "v2",
        "target_stage": stage,
        "evaluation_verdict": "RANKING_WIN",
        "created_at": "2026-08-26T10:00:00+00:00",
    }
    values.update(changes)
    return ModelReleaseRequest(**values)


def test_research_to_shadow_requires_approval_and_no_stage_skip(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    research = registry.register(request(ReleaseStage.RESEARCH))
    with pytest.raises(ModelPromotionError, match="stage skip"):
        registry.register(
            request(
                ReleaseStage.PAPER,
                previous_release_id=research["record_id"],
                approval_id="telegram:one",
                forward_evidence_required=1,
                forward_evidence_observed=1,
            )
        )
    with pytest.raises(ModelPromotionError, match="human approval"):
        registry.register(
            request(
                ReleaseStage.SHADOW,
                previous_release_id=research["record_id"],
            )
        )
    shadow = registry.register(
        request(
            ReleaseStage.SHADOW,
            previous_release_id=research["record_id"],
            approval_id="telegram:one",
        )
    )
    assert shadow["stage"] == "shadow"


def test_paper_and_later_require_predeclared_forward_evidence(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    research = registry.register(request(ReleaseStage.RESEARCH))
    shadow = registry.register(
        request(
            ReleaseStage.SHADOW,
            previous_release_id=research["record_id"],
            approval_id="telegram:one",
        )
    )
    with pytest.raises(ModelPromotionError, match="threshold must be predeclared"):
        registry.register(
            request(
                ReleaseStage.PAPER,
                previous_release_id=shadow["record_id"],
                approval_id="telegram:two",
            )
        )
    with pytest.raises(ModelPromotionError, match="threshold not met"):
        registry.register(
            request(
                ReleaseStage.PAPER,
                previous_release_id=shadow["record_id"],
                approval_id="telegram:two",
                forward_evidence_required=20,
                forward_evidence_observed=19,
            )
        )


def test_production_requires_supported_verdict_and_rollback(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    research = registry.register(request(ReleaseStage.RESEARCH))
    shadow = registry.register(
        request(
            ReleaseStage.SHADOW,
            previous_release_id=research["record_id"],
            approval_id="a1",
        )
    )
    paper = registry.register(
        request(
            ReleaseStage.PAPER,
            previous_release_id=shadow["record_id"],
            approval_id="a2",
            forward_evidence_required=1,
            forward_evidence_observed=1,
        )
    )
    limited = registry.register(
        request(
            ReleaseStage.LIMITED,
            previous_release_id=paper["record_id"],
            approval_id="a3",
            forward_evidence_required=2,
            forward_evidence_observed=2,
        )
    )
    with pytest.raises(ModelPromotionError, match="rollback"):
        registry.register(
            request(
                ReleaseStage.PRODUCTION,
                previous_release_id=limited["record_id"],
                approval_id="a4",
                forward_evidence_required=3,
                forward_evidence_observed=3,
            )
        )
    production = registry.register(
        request(
            ReleaseStage.PRODUCTION,
            previous_release_id=limited["record_id"],
            rollback_release_id=limited["record_id"],
            approval_id="a4",
            forward_evidence_required=3,
            forward_evidence_observed=3,
        )
    )
    assert production["stage"] == "production"


def test_registry_is_append_only_and_idempotent(tmp_path: Path) -> None:
    registry = ModelRegistry(tmp_path)
    first = registry.register(request(ReleaseStage.RESEARCH))
    second = registry.register(request(ReleaseStage.RESEARCH))
    assert first["status"] == "created"
    assert second["status"] == "duplicate"


def test_explicit_baseline_migration_keeps_unproven_domains_in_shadow(
    tmp_path: Path,
) -> None:
    releases = bootstrap_current_models(
        tmp_path,
        code_commit=SHA,
        approval_id="telegram:kelvin",
        created_at="2026-08-26T10:00:00+00:00",
    )
    assert {name: item["stage"] for name, item in releases.items()} == {
        "au": "production",
        "hkjc": "production",
        "tennis": "shadow",
        "nba": "shadow",
    }
    retry = bootstrap_current_models(
        tmp_path,
        code_commit=SHA,
        approval_id="telegram:kelvin",
        created_at="2026-08-27T10:00:00+00:00",
    )
    assert {name: item["status"] for name, item in retry.items()} == {
        "au": "duplicate",
        "hkjc": "duplicate",
        "tennis": "duplicate",
        "nba": "duplicate",
    }
