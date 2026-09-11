"""Replayable Stage 5 monitoring clock, with no execution or publication authority.

Inputs must be supplied by evidence-verifying adapters. A digest here is a pinned
reference, not proof of PIT eligibility, settlement, production completion or
absence of an incident. In particular dataset row_count is not a sample clock.
This module does not read files, schedule jobs, send messages, evaluate models,
advance sample watermarks, or clear a freeze. Completed request IDs suppress a
duplicate notification request only; they cannot approve a ruler or model.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .contracts import Domain


SYDNEY = ZoneInfo("Australia/Sydney")
UTC = timezone.utc
_SHA = re.compile(r"[0-9a-f]{64}")
_BASIS = {
    Domain.AU: "settled_races",
    Domain.HKJC: "settled_races",
    Domain.TENNIS: "verified_pit_outcomes",
    Domain.NBA: "forward_settled_recommendations",
}
_EVENTS = {"run_preflight", "run_postflight", "production_day_closed", "incident"}


class ReviewClockError(ValueError):
    pass


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _at(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReviewClockError("review clock requires timezone-aware datetime")
    return value.astimezone(UTC)


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise ReviewClockError("non-empty identity required")
    return value


def _digest(value):
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        raise ReviewClockError("full sha256 evidence identity required")
    return value


@dataclass(frozen=True)
class SampleSnapshot:
    domain: Domain
    scope: str
    basis: str
    observed_at: datetime
    evidence_digest: str
    unit_ids: frozenset[str]


@dataclass(frozen=True)
class ReviewEvent:
    kind: str
    event_id: str
    occurred_at: datetime
    evidence_digest: str
    production_day: date | None = None


def _sample_map(items, domain, now):
    mapped = {}
    for item in items:
        if not isinstance(item, SampleSnapshot) or item.domain != domain or item.basis != _BASIS[domain]:
            raise ReviewClockError("sample domain or eligibility basis mismatch")
        _text(item.scope)
        if domain is not Domain.TENNIS and item.scope != "all":
            raise ReviewClockError("non-Tennis sample clock requires all scope")
        if domain is Domain.TENNIS and item.scope == "all":
            raise ReviewClockError("Tennis sample clock must be family-specific")
        if item.scope in mapped:
            raise ReviewClockError("duplicate sample scope")
        if _at(item.observed_at) > now:
            raise ReviewClockError("sample observed in the future")
        _digest(item.evidence_digest)
        if not isinstance(item.unit_ids, frozenset):
            raise ReviewClockError("immutable deduplicated sample identities required")
        for identity in item.unit_ids:
            _text(identity)
        mapped[item.scope] = item
    return mapped


def _sample_payload(item):
    return {"domain": item.domain.value, "scope": item.scope, "basis": item.basis,
            "observed_at": _at(item.observed_at).isoformat(), "evidence_digest": item.evidence_digest,
            "unit_ids": sorted(item.unit_ids)}


def plan_reviews(
    *, domain: Domain, window_start: datetime, now: datetime,
    ruler_digest: str, ruler_released_at: datetime,
    samples: tuple[SampleSnapshot, ...] = (), previous_samples: tuple[SampleSnapshot, ...] = (),
    events: tuple[ReviewEvent, ...] = (), completed_request_ids: frozenset[str] = frozenset(),
) -> dict:
    """Plan due checks in (window_start, now], including unacknowledged event debt.

    Calendar history is bounded to 366 days per call; longer recovery must use
    explicit adjacent windows. Unresolved incidents and a ruler older than 90
    days remain freeze reasons even after acknowledging their digest. The caller
    must keep the last accepted sample snapshot: this result never resets it.
    """
    if not isinstance(domain, Domain):
        raise ReviewClockError("known research domain required")
    start, end, release = _at(window_start), _at(now), _at(ruler_released_at)
    _digest(ruler_digest)
    if start > end or end - start > timedelta(days=366):
        raise ReviewClockError("invalid or unbounded review window")
    if release > end:
        raise ReviewClockError("ruler release cannot be in the future")
    acknowledged = frozenset(completed_request_ids)
    for identity in acknowledged:
        _digest(identity)
    current = _sample_map(samples, domain, end)
    previous = _sample_map(previous_samples, domain, end)
    requests, findings, freeze_reasons = {}, set(), set()

    def request(kind, slot, due, *, action="monitor_only", **detail):
        identity = _hash({"schema": "wong-choi-review-request/v1", "domain": domain.value,
                          "ruler_digest": ruler_digest, "kind": kind, "slot": slot})
        if identity not in acknowledged:
            if len(requests) >= 10000 and identity not in requests:
                raise ReviewClockError("review backlog exceeds bounded request limit")
            requests[identity] = {"request_id": identity, "kind": kind, "slot": slot,
                                  "due_at": _at(due).isoformat(), "action": action, **detail}

    day, last = start.astimezone(SYDNEY).date(), end.astimezone(SYDNEY).date()
    while day <= last:
        due = datetime.combine(day, time(9), SYDNEY).astimezone(UTC)
        if day.weekday() == 0 and start < due <= end and due >= release:
            request("weekly", day.isoformat(), due)
            if day.day <= 7:
                request("monthly", day.strftime("%Y-%m"), due)
        day += timedelta(days=1)

    ruler_due = release + timedelta(days=90)
    if end >= ruler_due:
        freeze_reasons.add("ruler_90_day_review_due")
        request("ruler_90_day", release.isoformat(), ruler_due, action="human_ruler_review")

    unique_events = {}
    for event in events:
        if not isinstance(event, ReviewEvent) or event.kind not in _EVENTS:
            raise ReviewClockError("unsupported review event")
        _text(event.event_id)
        _digest(event.evidence_digest)
        occurred = _at(event.occurred_at)
        if occurred > end:
            raise ReviewClockError("review event cannot occur in the future")
        payload = {"kind": event.kind, "event_id": event.event_id,
                   "occurred_at": occurred.isoformat(), "evidence_digest": event.evidence_digest}
        if event.production_day is not None:
            if (event.kind != "production_day_closed" or type(event.production_day) is not date
                    or event.production_day > occurred.astimezone(SYDNEY).date()):
                raise ReviewClockError("production day must identify a non-future closure day")
            payload["production_day"] = event.production_day.isoformat()
        key = (event.kind, event.event_id)
        if key in unique_events and unique_events[key] != payload:
            raise ReviewClockError("conflicting review event identity")
        unique_events[key] = payload
    for payload in sorted(unique_events.values(), key=lambda item: (item["occurred_at"], item["kind"], item["event_id"])):
        occurred = datetime.fromisoformat(payload["occurred_at"])
        kind, slot = payload["kind"], payload["event_id"]
        action = "check_only"
        if kind == "production_day_closed":
            # Legacy events without this optional field preserve their old key.
            # Verified adapters must provide the logical day for late completion.
            kind, slot = "daily", payload.get("production_day", occurred.astimezone(SYDNEY).date().isoformat())
        elif kind == "incident":
            freeze_reasons.add(f"incident:{slot}")
            action = "human_incident_review"
        request(kind, slot, occurred, action=action, evidence_digest=payload["evidence_digest"])

    sample_growth = False
    for scope in sorted(set(previous) | set(current)):
        old, new = previous.get(scope), current.get(scope)
        if new is None:
            freeze_reasons.add(f"{scope}:sample_scope_missing")
            continue
        if old is None:
            findings.add(f"{scope}:sample_baseline_missing")
            continue
        if _at(new.observed_at) < _at(old.observed_at):
            raise ReviewClockError("sample clock moved backwards")
        if not old.unit_ids.issubset(new.unit_ids):
            freeze_reasons.add(f"{scope}:sample_identity_loss")
            continue
        low, high = len(old.unit_ids), len(new.unit_ids)
        sample_growth |= high > low
        increment, first = (200, 200) if domain is Domain.TENNIS else (50, 50)
        if domain is Domain.NBA:
            increment, first = 100, 30
        threshold = first if low < first else first + ((low - first) // increment + 1) * increment
        for value in range(threshold, high + 1, increment):
            request("sample", f"{scope}:{new.basis}:{value}", new.observed_at, scope=scope,
                    threshold=value, sample_count=high, basis=new.basis,
                    evidence_digest=new.evidence_digest, previous_evidence_digest=old.evidence_digest)

    findings.update(freeze_reasons)
    inputs = {"samples": [_sample_payload(current[key]) for key in sorted(current)],
              "previous_samples": [_sample_payload(previous[key]) for key in sorted(previous)],
              "events": [unique_events[key] for key in sorted(unique_events)]}
    payload = {
        "schema_version": "wong-choi-research-review-plan/v1", "domain": domain.value,
        "window_start": start.isoformat(), "as_of": end.isoformat(), "timezone": "Australia/Sydney",
        "ruler_digest": ruler_digest, "ruler_released_at": release.isoformat(),
        "inputs_digest": _hash(inputs), "completed_request_ids": sorted(acknowledged),
        "requests": sorted(requests.values(), key=lambda item: (item["due_at"], item["kind"],
                            item.get("scope", ""), item.get("threshold", 0), item["request_id"])),
        "findings": sorted(findings), "freeze_reasons": sorted(freeze_reasons),
        "sample_growth_observed": sample_growth, "progress_only": not sample_growth,
        "freeze_research_required": bool(freeze_reasons), "human_review_required": bool(findings),
        "rerun_scoring_allowed": False, "reevaluate_promotion_allowed": False, "model_promotion_allowed": False,
    }
    payload["content_hash"] = _hash(payload)
    return payload
