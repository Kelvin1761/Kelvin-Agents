"""Evidence-backed model release registry with explicit promotion transitions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .contracts import Domain
from .evidence import EvidenceRecord, EvidenceStore, RecordKind, ReleaseStage


PROMOTION_ORDER = (
    ReleaseStage.RESEARCH,
    ReleaseStage.SHADOW,
    ReleaseStage.PAPER,
    ReleaseStage.LIMITED,
    ReleaseStage.PRODUCTION,
)
PROMOTION_VERDICTS = frozenset({"PRIMARY_WIN", "RANKING_WIN"})


class ModelPromotionError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelReleaseRequest:
    domain: Domain
    model_id: str
    code_commit: str
    evaluation_contract_version: str
    target_stage: ReleaseStage
    evaluation_verdict: str
    approval_id: str | None = None
    previous_release_id: str | None = None
    rollback_release_id: str | None = None
    forward_evidence_observed: int = 0
    forward_evidence_required: int = 0
    created_at: str | None = None
    baseline_migration: bool = False


class ModelRegistry:
    def __init__(self, evidence_root: Path) -> None:
        self.store = EvidenceStore(evidence_root)

    def _load_model_release(self, record_id: str) -> dict[str, Any]:
        value = self.store.load(record_id)
        if value["kind"] != RecordKind.MODEL_RELEASE.value:
            raise ModelPromotionError(f"not a model release: {record_id}")
        return value

    def register(self, request: ModelReleaseRequest) -> dict[str, Any]:
        model_id = request.model_id.strip()
        if not model_id:
            raise ModelPromotionError("model_id is required")
        if request.forward_evidence_observed < 0 or request.forward_evidence_required < 0:
            raise ModelPromotionError("forward evidence counts cannot be negative")
        previous = None
        if request.previous_release_id:
            previous = self._load_model_release(request.previous_release_id)
            if previous["domain"] != request.domain.value:
                raise ModelPromotionError("previous release belongs to another domain")
            if (previous.get("body") or {}).get("model_id") != model_id:
                raise ModelPromotionError("previous release belongs to another model")

        if request.baseline_migration:
            if request.evaluation_verdict != "BASELINE_MIGRATION":
                raise ModelPromotionError("baseline migration requires BASELINE_MIGRATION verdict")
            if request.previous_release_id is not None:
                raise ModelPromotionError("baseline migration cannot have previous_release_id")
            if request.target_stage not in {
                ReleaseStage.SHADOW,
                ReleaseStage.PRODUCTION,
            }:
                raise ModelPromotionError("baseline migration must register shadow or production")
            if not request.approval_id:
                raise ModelPromotionError("baseline migration requires human approval")
        elif request.target_stage is ReleaseStage.RESEARCH:
            if previous is not None:
                raise ModelPromotionError("research registration cannot have a previous release")
        elif request.target_stage is ReleaseStage.RETIRED:
            if previous is None:
                raise ModelPromotionError("retirement requires the active release")
        else:
            if previous is None:
                raise ModelPromotionError("promotion requires previous_release_id")
            previous_stage = ReleaseStage(previous["body"]["release_stage"])
            try:
                expected = PROMOTION_ORDER[PROMOTION_ORDER.index(previous_stage) + 1]
            except (ValueError, IndexError) as exc:
                raise ModelPromotionError(
                    f"cannot promote from {previous_stage.value}"
                ) from exc
            if request.target_stage is not expected:
                raise ModelPromotionError(
                    f"stage skip blocked: {previous_stage.value} -> {request.target_stage.value}"
                )

        if (
            not request.baseline_migration
            and request.target_stage is not ReleaseStage.RESEARCH
            and not request.approval_id
        ):
            raise ModelPromotionError("human approval is required for model promotion")
        if not request.baseline_migration and request.target_stage in {
            ReleaseStage.LIMITED,
            ReleaseStage.PRODUCTION,
        } and request.evaluation_verdict not in PROMOTION_VERDICTS:
            raise ModelPromotionError("limited/production requires PRIMARY_WIN or RANKING_WIN")
        if not request.baseline_migration and request.target_stage in {
            ReleaseStage.PAPER,
            ReleaseStage.LIMITED,
            ReleaseStage.PRODUCTION,
        }:
            if request.forward_evidence_required < 1:
                raise ModelPromotionError("forward evidence threshold must be predeclared")
            if request.forward_evidence_observed < request.forward_evidence_required:
                raise ModelPromotionError("forward evidence threshold not met")
        if not request.baseline_migration and request.target_stage is ReleaseStage.PRODUCTION:
            if not request.rollback_release_id:
                raise ModelPromotionError("production promotion requires rollback_release_id")
            rollback = self._load_model_release(request.rollback_release_id)
            if rollback["domain"] != request.domain.value:
                raise ModelPromotionError("rollback release belongs to another domain")

        stamp = request.created_at or datetime.now(timezone.utc).isoformat()
        stage = request.target_stage.value
        record_id = ":".join(
            (
                "wc",
                request.domain.value,
                "model-release",
                quote(model_id.lower(), safe="._-"),
                request.code_commit[:12],
                stage,
            )
        )
        links = {}
        if request.previous_release_id:
            links["previous_release_id"] = request.previous_release_id
        if request.rollback_release_id:
            links["rollback_release_id"] = request.rollback_release_id
        body = {
            "model_id": model_id,
            "release_stage": stage,
            "code_commit": request.code_commit,
            "evaluation_contract_version": request.evaluation_contract_version,
            "evaluation_verdict": request.evaluation_verdict,
            "approval_id": request.approval_id,
            "forward_evidence_observed": request.forward_evidence_observed,
            "forward_evidence_required": request.forward_evidence_required,
            "baseline_migration": request.baseline_migration,
        }
        existing_path = self.store.find(record_id)
        if existing_path is not None:
            existing = self.store.load(record_id)
            if (
                existing.get("kind") == RecordKind.MODEL_RELEASE.value
                and existing.get("domain") == request.domain.value
                and existing.get("body") == body
                and existing.get("links") == links
            ):
                return {
                    "status": "duplicate",
                    "record_id": record_id,
                    "content_hash": existing["content_hash"],
                    "path": str(existing_path),
                    "stage": stage,
                }
            raise ModelPromotionError(f"immutable model release conflict: {record_id}")
        appended = self.store.append(
            EvidenceRecord(
                record_id=record_id,
                kind=RecordKind.MODEL_RELEASE,
                domain=request.domain,
                created_at=stamp,
                body=body,
                links=links,
            )
        )
        return {
            "status": appended.status,
            "record_id": record_id,
            "content_hash": appended.content_hash,
            "path": str(appended.path),
            "stage": stage,
        }


def bootstrap_current_models(
    evidence_root: Path,
    *,
    code_commit: str,
    approval_id: str,
    created_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    """One-time, explicit registration of existing champions before new promotions."""
    registry = ModelRegistry(evidence_root)
    specs = {
        Domain.AU: ("au-matrix", "au-hkjc-v2", ReleaseStage.PRODUCTION),
        Domain.HKJC: ("hkjc-7d", "au-hkjc-v2", ReleaseStage.PRODUCTION),
        Domain.TENNIS: ("tennis-pricing", "tennis-current", ReleaseStage.PRODUCTION),
        Domain.NBA: ("nba-hybrid-v1", "nba-hybrid-v1", ReleaseStage.SHADOW),
    }
    return {
        domain.value: registry.register(
            ModelReleaseRequest(
                domain=domain,
                model_id=model_id,
                code_commit=code_commit,
                evaluation_contract_version=contract,
                target_stage=stage,
                evaluation_verdict="BASELINE_MIGRATION",
                approval_id=approval_id,
                created_at=created_at,
                baseline_migration=True,
            )
        )
        for domain, (model_id, contract, stage) in specs.items()
    }
