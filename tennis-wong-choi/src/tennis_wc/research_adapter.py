"""Create-only research captures; no model, ledger or provider operations."""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence
from urllib.parse import quote, unquote

from tennis_wc.research_evidence import SETTLEMENT_INPUT_FIELDS

# Match the existing frozen prediction consumer's file/bundle budgets.
CAPTURE_MAX_FILES = 5000
CAPTURE_MAX_FILE_BYTES = 32 * 1024 * 1024
CAPTURE_MAX_TOTAL_BYTES = 512 * 1024 * 1024
CAPTURE_MAX_MANIFEST_BYTES = 1024 * 1024


def _capture_bytes(path: Path, limit: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("capture file type or size limit")
        chunks, length = [], 0
        while True:
            raw = os.read(descriptor, min(1024 * 1024, limit - length + 1))
            if not raw:
                break
            length += len(raw)
            if length > limit:
                raise ValueError("capture file size limit")
            chunks.append(raw)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def research_retry_batch(*, evidence_root: Path, before_date: str, max_dates: int = 10) -> dict:
    """Bounded rotating research-only catch-up, independent of ledger PENDING.

    Inventory is not dataset qualification. Deferred history remains explicit;
    no archived/missing source is silently removed to obtain a usable sample.
    """
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.evidence import RecordKind
    from shared_wong_choi.research_index import _Reader, _safe
    from shared_wong_choi.research_prediction_artifacts import _record

    before = date.fromisoformat(before_date)
    if before.isoformat() != before_date or type(max_dates) is not int or not 0 <= max_dates <= 30:
        raise ValueError("canonical retry date and budget 0..30 required")
    reader, days = _Reader(lambda: None), set()
    root = _safe(evidence_root.expanduser().absolute())
    for path in reader.listing(root / "records" / RecordKind.PREDICTION.value):
        if not unquote(path.stem).startswith("wc:tennis:"):
            continue
        raw, _ = reader.read(path)
        prediction = _record(raw, RecordKind.PREDICTION, Domain.TENNIS, path)
        event = prediction.body["event_id"]
        parsed = date.fromisoformat(event)
        if parsed.isoformat() != event:
            raise ValueError("noncanonical retry event")
        if parsed < before:
            days.add(event)
    reader.recheck()
    ordered = sorted(days)
    limit = min(max_dates, len(ordered))
    start = (before.toordinal() * max_dates) % len(ordered) if ordered else 0
    selected = [ordered[(start + index) % len(ordered)] for index in range(limit)]
    return {"dates": selected, "eligible_dates": len(ordered),
            "deferred_dates": len(ordered) - limit, "budget": max_dates,
            "selection": "calendar_rotating", "corpus_qualified": False}


def record_research_settlement(
    connection: sqlite3.Connection, *, evidence_root: Path, capture_root: Path,
    event_id: str, at: datetime,
) -> dict:
    """Observe native results and append guarded evidence, never settle bets."""
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.domain_evidence import record_settlement_for_event
    from shared_wong_choi.evidence import SettlementState
    from tennis_wc.research_evidence import build_settlement_artifacts

    try:
        context = load_forecast_context(evidence_root=evidence_root, event_id=event_id, at=at)
    except ValueError as exc:
        return {"status": "blocked", "reason": str(exc), "live_acceptance": "pending"}
    if context is None:
        return {"status": "migration_pending", "reason": "decision_not_found"}
    identity = {"event_id": event_id, "decision_id": context["decision_id"],
                "prediction_id": context["prediction_id"],
                "source_cutoff_at": context["source_cutoff_at"].isoformat()}
    try:
        outcomes, raw = read_settlement_sources(connection, event_id=event_id,
                                               forecast_rows=context["forecast_rows"])
        def build(clock):
            return build_settlement_artifacts(event_id=event_id, source_cutoff_at=context["source_cutoff_at"],
                                             settled_at=clock, outcomes=outcomes, raw_responses=raw)
        # Validate sources before creating directories. Capture/storage failures
        # below remain failures rather than being mislabeled missing provenance.
        build(at)
    except ValueError as exc:
        status, reason, count = "unverified", str(exc), 0
        identity.update(status=status, reason=reason)
        def build(clock):
            return {f"Tennis_Research_Status_{event_id}.json": _encoded({
                "event_id": event_id, "generated_at": clock.isoformat(),
                "status": status, "reason": reason, "live_acceptance": "pending",
            }) + b"\n"}
        state = SettlementState.UNVERIFIED
    else:
        status, reason, count = "result_provenance_captured", None, len(outcomes)
        identity.update(forecast_rows=context["forecast_rows"], outcomes=outcomes, raw_responses=raw)
        state = SettlementState.SETTLED
    paths, captured, signature = freeze_settlement(root=capture_root, identity=identity, at=at, build=build, event_id=event_id)
    expected_files = build(captured)
    expected_hashes = {str(path.resolve()): hashlib.sha256(expected_files[path.name]).hexdigest()
                       for path in paths}
    summary = {"research_status": status, "input_signature": signature,
               "verified_outcomes": count, "live_acceptance": "pending"}
    if reason is not None:
        summary["reason"] = reason
    result = record_settlement_for_event(
        domain=Domain.TENNIS, event_id=event_id, evidence_root=evidence_root,
        summary=summary, artifacts=paths, settled_at=captured, settlement_state=state,
        expected_decision_id=context["decision_id"], required=True,
        expected_artifact_hashes=expected_hashes,
    )
    return {**result, **summary}


def load_forecast_context(*, evidence_root: Path, event_id: str, at: datetime) -> dict | None:
    """Load the unambiguous latest parent and verify its complete frozen bundle.

    No DB access, repair, relocated basename search or evidence writes. Missing
    decisions return None; corrupt/ambiguous evidence fails closed.
    """
    from shared_wong_choi.contracts import Domain
    from shared_wong_choi.evidence import RecordKind
    from shared_wong_choi.research_index import _Reader, _safe
    from shared_wong_choi.research_prediction_artifacts import (
        _Blobs, _manifest_consistent, _record, _resolve_bundle,
    )
    from shared_wong_choi.research_tennis_feature_provenance import _projection

    if not isinstance(event_id, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id) is None:
        raise ValueError("canonical Tennis event date required")
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("research context clock must be aware")
    root = _safe(evidence_root.expanduser().absolute())
    reader, blobs = _Reader(lambda: None), _Blobs(lambda: None)
    candidates = []
    for path in reader.listing(root / "records" / RecordKind.DECISION.value):
        if not unquote(path.stem).startswith("wc:tennis:"):
            continue
        raw, _ = reader.read(path)
        decision = _record(raw, RecordKind.DECISION, Domain.TENNIS, path)
        prediction_id = decision.links["prediction_id"]
        parent_path = root / "records" / RecordKind.PREDICTION.value / (quote(prediction_id, safe="._-") + ".json")
        parent_raw, _ = reader.read(parent_path)
        prediction = _record(parent_raw, RecordKind.PREDICTION, Domain.TENNIS, parent_path)
        if prediction.body["event_id"] == event_id:
            candidates.append((decision, prediction))
    if not candidates:
        reader.recheck()
        return None
    latest = max(_aware(item[0].created_at) for item in candidates)
    selected = [item for item in candidates if _aware(item[0].created_at) == latest]
    if len(selected) != 1 or latest > at:
        raise ValueError("ambiguous or future Tennis decision parent")
    decision, prediction = selected[0]
    cutoff = _aware(prediction.body["source_cutoff_at"])
    if cutoff > at or _aware(prediction.created_at) > at:
        raise ValueError("future Tennis prediction parent")
    release_id = prediction.links["model_release_id"]
    release_path = root / "records" / RecordKind.MODEL_RELEASE.value / (quote(release_id, safe="._-") + ".json")
    release_raw, _ = reader.read(release_path)
    _record(release_raw, RecordKind.MODEL_RELEASE, Domain.TENNIS, release_path)
    if not prediction.artifacts or any(
        _aware(ref.captured_at) != cutoff or ref.source != "tennis_prediction_snapshot"
        for ref in prediction.artifacts
    ):
        raise ValueError("Tennis prediction artifact provenance differs")
    resolved, invalid = _resolve_bundle(prediction.artifacts, event_id, (), blobs)
    manifest_ok, _ = _manifest_consistent(prediction, resolved)
    if invalid or not manifest_ok or any(item[3] is None for item in resolved) or len({item[2].parent for item in resolved if item[2] is not None}) != 1:
        raise ValueError("Tennis frozen prediction bundle unverified")
    files = {Path(item[0].path).name: item[3] for item in resolved}
    feature_name = f"Tennis_Feature_Evidence_{event_id}.json"
    if feature_name not in files:
        raise ValueError("Tennis frozen feature evidence missing")
    recommendations = {}
    for item in prediction.body["recommendations"]:
        identity = item.get("id")
        if type(identity) is not int or identity <= 0 or identity in recommendations:
            raise ValueError("invalid Tennis frozen recommendation identity")
        recommendations[identity] = item
    _projected, blockers = _projection(
        files[feature_name], event_id=event_id, cutoff=cutoff,
        recommendations=recommendations,
        raw_artifacts={name: raw for name, raw in files.items() if name.startswith(f"Tennis_Raw_Evidence_{event_id}_")},
    )
    if blockers:
        raise ValueError("Tennis frozen feature provenance blocked: " + ",".join(sorted(blockers)))
    reader.recheck()
    blobs.recheck()
    return {"decision_id": decision.record_id, "prediction_id": prediction.record_id,
            "source_cutoff_at": cutoff, "forecast_rows": json.loads(files[feature_name])["rows"]}


def _aware(value: object) -> datetime:
    clock = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise ValueError("forecast timestamp must be aware")
    return clock.astimezone(timezone.utc)


def read_settlement_sources(
    connection: sqlite3.Connection, *, event_id: str,
    forecast_rows: Sequence[Mapping[str, object]],
) -> tuple[list[dict], dict[int, dict]]:
    """SELECT exact frozen forecasts and the native ledger's canonical result.

    Never selects a replacement forecast or updates predictions/results/ledger.
    The pure settlement producer must still validate raw pair/winner/chronology.
    """
    if not isinstance(event_id, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id) is None:
        raise ValueError("canonical Tennis event date required")
    if not forecast_rows:
        raise ValueError("frozen forecasts required")
    forecasts = {}
    for forecast in forecast_rows:
        identity = forecast.get("prediction_id")
        if type(identity) is not int or identity <= 0 or identity in forecasts:
            raise ValueError("invalid or duplicate frozen prediction identity")
        forecasts[identity] = forecast
    outcomes, raw_responses = [], {}
    identities = sorted(forecasts)
    raw_fields = ("id", "provider_name", "endpoint", "response_json", "fetched_at", "created_at")
    for start in range(0, len(identities), 500):
        batch = identities[start:start + 500]
        placeholders = ",".join("?" for _ in batch)
        cursor = connection.execute(f"""
            SELECT p.id AS prediction_id, p.match_id, m.match_date,
                   p.created_at AS prediction_created_at,
                   m.player_a_id, m.player_b_id,
                   pa.name AS player_a_name, pb.name AS player_b_name,
                   p.selection_player_id, p.model_probability, p.no_vig_market_probability,
                   r.winner_player_id, r.source_provider AS result_source_provider,
                   r.raw_response_id AS result_raw_response_id,
                   r.created_at AS result_created_at,
                   raw.id AS raw_id, raw.provider_name AS raw_provider_name,
                   raw.endpoint AS raw_endpoint, raw.response_json AS raw_response_json,
                   raw.fetched_at AS raw_fetched_at, raw.created_at AS raw_created_at
            FROM predictions p
            JOIN matches m ON m.id = p.match_id
            JOIN players pa ON pa.id = m.player_a_id
            JOIN players pb ON pb.id = m.player_b_id
            LEFT JOIN match_results r ON r.id = (
                SELECT r2.id FROM match_results r2 WHERE r2.match_id = p.match_id
                ORDER BY
                    CASE WHEN json_extract(r2.score_json, '$.player_a_aces') IS NOT NULL
                           AND json_extract(r2.score_json, '$.player_b_aces') IS NOT NULL
                         THEN 0 ELSE 1 END,
                    CASE WHEN r2.source_provider = 'tennismylife' THEN 0 ELSE 1 END,
                    r2.id DESC LIMIT 1
            )
            LEFT JOIN raw_api_responses raw ON raw.id = r.raw_response_id
            WHERE p.id IN ({placeholders}) AND m.match_date = ?
            ORDER BY p.id
        """, (*batch, event_id))
        columns = [item[0] for item in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
        if [row["prediction_id"] for row in rows] != batch:
            raise ValueError("frozen prediction coverage missing")
        for row in rows:
            forecast = forecasts[row["prediction_id"]]
            fields = ("match_id", "selection_player_id", "model_probability", "no_vig_market_probability")
            try:
                changed = any(row[field] != forecast[field] for field in fields)
                changed |= _aware(row["prediction_created_at"]) != _aware(forecast["prediction_created_at"])
                snapshot = forecast["feature_snapshot"]
                changed |= any(row[f"{side}_id"] != snapshot[side]["id"]["value"]
                               for side in ("player_a", "player_b"))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("invalid frozen forecast comparison") from exc
            if changed:
                raise ValueError("stored prediction differs from frozen forecast")
            if row["winner_player_id"] is None or row["raw_id"] is None:
                raise ValueError("canonical result or raw provenance missing")
            raw_id = row["raw_id"]
            raw = {field: row[f"raw_{field}"] for field in raw_fields}
            if raw_id in raw_responses and raw_responses[raw_id] != raw:
                raise ValueError("raw result changed during capture")
            raw_responses[raw_id] = raw
            outcomes.append({field: row[field] for field in SETTLEMENT_INPUT_FIELDS})
    return outcomes, raw_responses


def _encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def freeze_settlement(
    *, root: Path, identity: dict, at: datetime,
    build: Callable[[datetime], Mapping[str, bytes]],
    event_id: str | None = None,
) -> tuple[tuple[Path, ...], datetime, str]:
    """Reuse a verified first capture, or publish a new one without overwrite."""
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("research capture clock must be aware")
    if event_id is not None and (not isinstance(event_id, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", event_id) is None):
        raise ValueError("canonical capture event date required")
    signature = hashlib.sha256(_encoded(identity)).hexdigest()
    root = root.expanduser().absolute()
    if ".." in root.parts or any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("research capture root symlink refused")
    root.mkdir(parents=True, exist_ok=True)
    final = root / (f"{event_id}_{signature}" if event_id is not None else signature)
    if not final.exists() and not final.is_symlink():
        files = dict(build(at))
        if not files or any(
            not isinstance(name, str) or Path(name).name != name
            or name in {"", ".", "..", "manifest.json"}
            or not isinstance(raw, bytes) or not raw
            for name, raw in files.items()
        ):
            raise ValueError("invalid research capture artifact")
        if (len(files) > CAPTURE_MAX_FILES
                or any(len(raw) > CAPTURE_MAX_FILE_BYTES for raw in files.values())
                or sum(map(len, files.values())) > CAPTURE_MAX_TOTAL_BYTES):
            raise ValueError("research capture artifact budget exceeded")
        manifest = {
            "schema_version": "wong-choi-tennis-research-capture/v1",
            "input_signature": signature, "captured_at": at.isoformat(),
            "files": [
                {"name": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
                for name, raw in sorted(files.items())
            ],
        }
        manifest_bytes = _encoded(manifest) + b"\n"
        if len(manifest_bytes) > CAPTURE_MAX_MANIFEST_BYTES:
            raise ValueError("research capture manifest budget exceeded")
        with tempfile.TemporaryDirectory(prefix=".capture-", dir=root) as temporary:
            staging = Path(temporary)
            for name, raw in files.items():
                with (staging / name).open("xb") as handle:
                    handle.write(raw)
            with (staging / "manifest.json").open("xb") as handle:
                handle.write(manifest_bytes)
            try:
                staging.rename(final)
            except OSError:
                if not final.is_dir():
                    raise
    if final.is_symlink() or not final.is_dir():
        raise ValueError("invalid immutable research capture directory")
    manifest_path = final / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("invalid immutable research capture manifest")
    manifest = json.loads(_capture_bytes(manifest_path, CAPTURE_MAX_MANIFEST_BYTES))
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema_version", "input_signature", "captured_at", "files"}
        or manifest["schema_version"] != "wong-choi-tennis-research-capture/v1"
        or manifest["input_signature"] != signature
        or not isinstance(manifest["files"], list) or not manifest["files"]
        or len(manifest["files"]) > CAPTURE_MAX_FILES
    ):
        raise ValueError("immutable research capture identity differs")
    captured = datetime.fromisoformat(str(manifest["captured_at"]))
    if captured.tzinfo is None or captured.utcoffset() is None or captured > at:
        raise ValueError("invalid immutable research capture clock")
    paths, names, total = [], set(), 0
    for item in manifest["files"]:
        if (
            not isinstance(item, dict) or set(item) != {"name", "bytes", "sha256"}
            or not isinstance(item["name"], str) or Path(item["name"]).name != item["name"]
            or item["name"] in {"", ".", "..", "manifest.json"} or item["name"] in names
            or type(item["bytes"]) is not int or item["bytes"] <= 0
        ):
            raise ValueError("invalid immutable research capture entry")
        path = final / item["name"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("immutable research capture file missing or symlink")
        raw = _capture_bytes(path, min(CAPTURE_MAX_FILE_BYTES, CAPTURE_MAX_TOTAL_BYTES - total))
        total += len(raw)
        if len(raw) != item["bytes"] or hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("immutable research capture bytes differ")
        names.add(item["name"])
        paths.append(path)
    if {path.name for path in final.iterdir()} != names | {"manifest.json"}:
        raise ValueError("immutable research capture file set differs")
    # A mutable manifest's hashes alone cannot prove the input binding. Rebuild
    # from the same memory inputs at the captured clock and compare exact bytes.
    expected = dict(build(captured))
    if set(expected) != names or any(_capture_bytes(path, CAPTURE_MAX_FILE_BYTES) != expected[path.name] for path in paths):
        raise ValueError("immutable research capture differs from source inputs")
    return tuple(paths), captured.astimezone(timezone.utc), signature
