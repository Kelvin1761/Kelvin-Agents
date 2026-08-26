"""Domain-neutral writer from immutable prediction artifacts into evidence records."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import Domain
from .evidence import (
    ArtifactRef,
    DecisionState,
    EvidenceRecord,
    EvidenceStore,
    RecordKind,
    ReleaseStage,
    SettlementState,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso(value: str | None, fallback: datetime) -> str:
    if value:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
        if parsed is not None and parsed.tzinfo is not None:
            return parsed.isoformat()
    return fallback.isoformat()


def latest_model_release(store: EvidenceStore, domain: Domain) -> str:
    folder = store.root / "records" / RecordKind.MODEL_RELEASE.value
    values: list[dict[str, Any]] = []
    if folder.exists():
        for path in folder.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if payload.get("domain") == domain.value:
                values.append(payload)
    if not values:
        raise RuntimeError(f"no model release registered for {domain.value}")
    stage_order = {
        "research": 0,
        "shadow": 1,
        "paper": 2,
        "limited": 3,
        "production": 4,
        "retired": -1,
    }
    latest_by_model: dict[str, dict[str, Any]] = {}
    for item in values:
        model_id = str((item.get("body") or {}).get("model_id") or item["record_id"])
        current = latest_by_model.get(model_id)
        if current is None or str(item.get("created_at") or "") > str(
            current.get("created_at") or ""
        ):
            latest_by_model[model_id] = item
    active = [
        item
        for item in latest_by_model.values()
        if str((item.get("body") or {}).get("release_stage")) != "retired"
    ]
    if not active:
        raise RuntimeError(f"no active model release registered for {domain.value}")
    latest = max(
        active,
        key=lambda item: (
            stage_order.get(str((item.get("body") or {}).get("release_stage")), -2),
            str(item.get("created_at") or ""),
        ),
    )
    return str(latest["record_id"])


def _manifest(snapshot: Path) -> tuple[Path, dict[str, Any]]:
    manifest = snapshot / "manifest.json" if snapshot.is_dir() else snapshot
    if not manifest.is_file():
        raise FileNotFoundError(f"prediction manifest missing: {manifest}")
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("prediction manifest must be a JSON object")
    return manifest, payload


def scoring_recommendations(snapshot: Path, *, limit: int = 5) -> list[dict[str, Any]]:
    candidates = sorted(
        {
            path
            for pattern in ("*Auto_Scoring.csv", "*Scoring.csv")
            for path in snapshot.glob(pattern)
            if path.is_file()
        }
    )
    recommendations: list[dict[str, Any]] = []
    for path in candidates:
        try:
            with path.open(encoding="utf-8-sig", newline="") as handle:
                rows = list(csv.DictReader(handle))
        except (OSError, UnicodeError, csv.Error):
            continue
        for row in rows:
            rank_raw = row.get("rank") or row.get("Rank") or row.get("derived_rank")
            try:
                rank = int(float(str(rank_raw)))
            except (TypeError, ValueError):
                continue
            if rank > limit:
                continue
            recommendations.append(
                {
                    "race": row.get("race_number") or row.get("race") or row.get("Race"),
                    "rank": rank,
                    "selection_id": row.get("horse_number") or row.get("horse_no"),
                    "selection": row.get("horse_name") or row.get("name"),
                    "grade": row.get("grade") or row.get("Grade"),
                    "source": path.name,
                }
            )
    return recommendations


def infer_recommendations(
    domain: Domain,
    snapshot: Path,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if domain in {Domain.AU, Domain.HKJC}:
        return scoring_recommendations(snapshot)
    if domain is Domain.NBA:
        return [
            {"event_id": tag, "status": "analysis_snapshot_available"}
            for tag in manifest.get("game_tags") or []
        ]
    raw = manifest.get("recommendations") or []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def record_prediction_decision(
    *,
    domain: Domain,
    event_id: str,
    snapshot: Path,
    evidence_root: Path,
    decision_state: DecisionState,
    recommendations: Iterable[Mapping[str, Any]] | None = None,
    model_release_id: str | None = None,
    source_cutoff_at: str | None = None,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    store = EvidenceStore(evidence_root)
    manifest_path, manifest = _manifest(snapshot)
    snapshot_root = manifest_path.parent
    ingestion_clock = created_at or datetime.now(timezone.utc)
    if ingestion_clock.tzinfo is None or ingestion_clock.utcoffset() is None:
        raise ValueError("prediction evidence clock must be timezone-aware")
    cutoff = _iso(
        source_cutoff_at
        or str(manifest.get("created_at") or manifest.get("generated_at") or ""),
        ingestion_clock,
    )
    record_clock = (
        ingestion_clock
        if created_at is not None
        else datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    )
    release_id = model_release_id or latest_model_release(store, domain)
    release = store.load(release_id)
    release_stage = ReleaseStage(str((release.get("body") or {}).get("release_stage")))
    requested_decision_state = decision_state
    if release_stage in {
        ReleaseStage.RESEARCH,
        ReleaseStage.SHADOW,
        ReleaseStage.PAPER,
    } and decision_state is not DecisionState.BLOCKED:
        decision_state = DecisionState.SHADOW
    elif release_stage is ReleaseStage.RETIRED:
        decision_state = DecisionState.BLOCKED
    selected = (
        [dict(item) for item in recommendations]
        if recommendations is not None
        else infer_recommendations(domain, snapshot_root, manifest)
    )
    files = [manifest_path]
    if snapshot_root.is_dir():
        files.extend(
            path
            for path in sorted(snapshot_root.iterdir())
            if path.is_file() and path != manifest_path
        )
    artifact_refs = tuple(
        ArtifactRef(
            path=str(path.resolve()),
            sha256=_sha256(path),
            captured_at=cutoff,
            source=f"{domain.value}_prediction_snapshot",
        )
        for path in files
    )
    signature = _sha256(manifest_path)
    prediction_id = f"wc:{domain.value}:prediction:{signature[:24]}"
    prediction = store.append(
        EvidenceRecord(
            record_id=prediction_id,
            kind=RecordKind.PREDICTION,
            domain=domain,
            created_at=record_clock.isoformat(),
            body={
                "event_id": event_id,
                "source_cutoff_at": cutoff,
                "recommendations": selected,
                "snapshot_manifest_sha256": signature,
            },
            links={"model_release_id": release_id},
            artifacts=artifact_refs,
        )
    )
    decision_id = f"wc:{domain.value}:decision:{signature[:24]}:{decision_state.value}"
    decision = store.append(
        EvidenceRecord(
            record_id=decision_id,
            kind=RecordKind.DECISION,
            domain=domain,
            created_at=record_clock.isoformat(),
            body={
                "decision_state": decision_state.value,
                "recommendation_count": len(selected),
            },
            links={"prediction_id": prediction_id},
        )
    )
    return {
        "status": "created"
        if "created" in {prediction.status, decision.status}
        else "duplicate",
        "model_release_id": release_id,
        "prediction_id": prediction_id,
        "decision_id": decision_id,
        "release_stage": release_stage.value,
        "requested_decision_state": requested_decision_state.value,
        "decision_state": decision_state.value,
        "recommendation_count": len(selected),
    }


def record_prediction_decision_if_configured(
    *,
    required: bool | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Migration guard: production fails closed once WC_REQUIRE_EVIDENCE=1."""
    evidence_root = Path(kwargs["evidence_root"]).expanduser().resolve()
    model_folder = evidence_root / "records" / RecordKind.MODEL_RELEASE.value
    must_write = (
        required
        if required is not None
        else os.environ.get("WC_REQUIRE_EVIDENCE", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    if not model_folder.exists() or not any(model_folder.glob("*.json")):
        if must_write:
            raise RuntimeError("model registry is not bootstrapped; evidence is required")
        return {"status": "migration_pending", "reason": "model_registry_empty"}
    return record_prediction_decision(**kwargs)


def _latest_decision_for_event(
    store: EvidenceStore, domain: Domain, event_id: str
) -> str | None:
    prediction_folder = store.root / "records" / RecordKind.PREDICTION.value
    matching_predictions: set[str] = set()
    for path in prediction_folder.glob("*.json") if prediction_folder.exists() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (
            payload.get("domain") == domain.value
            and str((payload.get("body") or {}).get("event_id")) == event_id
        ):
            matching_predictions.add(str(payload.get("record_id")))
    if not matching_predictions:
        return None
    decision_folder = store.root / "records" / RecordKind.DECISION.value
    decisions: list[dict[str, Any]] = []
    for path in decision_folder.glob("*.json") if decision_folder.exists() else ():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if str((payload.get("links") or {}).get("prediction_id")) in matching_predictions:
            decisions.append(payload)
    if not decisions:
        return None
    latest = max(decisions, key=lambda item: str(item.get("created_at") or ""))
    return str(latest["record_id"])


def record_settlement_for_event(
    *,
    domain: Domain,
    event_id: str,
    evidence_root: Path,
    summary: Mapping[str, Any],
    artifacts: Iterable[Path] = (),
    settled_at: datetime | None = None,
    required: bool | None = None,
) -> dict[str, Any]:
    """Append an aggregate event settlement linked to its latest decision."""
    store = EvidenceStore(evidence_root)
    must_write = (
        required
        if required is not None
        else os.environ.get("WC_REQUIRE_EVIDENCE", "").strip().lower()
        in {"1", "true", "yes", "on"}
    )
    decision_id = _latest_decision_for_event(store, domain, event_id)
    if decision_id is None:
        if must_write:
            raise RuntimeError(f"no decision evidence for {domain.value}:{event_id}")
        return {"status": "migration_pending", "reason": "decision_not_found"}
    clock = settled_at or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("settlement clock must be timezone-aware")
    selected_artifacts = [Path(path).expanduser().resolve() for path in artifacts]
    for path in selected_artifacts:
        if not path.is_file():
            raise FileNotFoundError(f"settlement artifact missing: {path}")
    stable = {
        "decision_id": decision_id,
        "event_id": event_id,
        "summary": dict(summary),
        "artifacts": [
            {"path": str(path), "sha256": _sha256(path)}
            for path in selected_artifacts
        ],
    }
    signature = hashlib.sha256(
        json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    record_id = f"wc:{domain.value}:settlement:{signature[:24]}"
    if store.find(record_id) is not None:
        return {
            "status": "duplicate",
            "settlement_id": record_id,
            "decision_id": decision_id,
        }
    refs = tuple(
        ArtifactRef(
            path=str(path),
            sha256=_sha256(path),
            captured_at=clock.isoformat(),
            source=f"{domain.value}_settlement",
        )
        for path in selected_artifacts
    )
    appended = store.append(
        EvidenceRecord(
            record_id=record_id,
            kind=RecordKind.SETTLEMENT,
            domain=domain,
            created_at=clock.isoformat(),
            body={
                "event_id": event_id,
                "settlement_state": SettlementState.SETTLED.value,
                "settled_at": clock.isoformat(),
                "summary": dict(summary),
            },
            links={"decision_id": decision_id},
            artifacts=refs,
        )
    )
    return {
        "status": appended.status,
        "settlement_id": record_id,
        "decision_id": decision_id,
    }
