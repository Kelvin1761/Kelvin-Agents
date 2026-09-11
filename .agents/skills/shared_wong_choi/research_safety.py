"""Task 6A: reproducible input evidence audit, NOT a model safety approval.

The source files are immutable, normalized exports of audited domain sources.
Hashes prove identity, not that an export's availability assertions are true.
An audited exporter and a run-bound input-use trace are still required before
this evidence can support a complete Task 6 safety decision. No source is
fetched, data repaired, model run, or promotion decision published here.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import fmean
from typing import Any, Mapping

from .evaluation_rulers import DEFAULT_RULER_ROOT, load_evaluation_ruler
from .research_dataset import load_dataset_snapshot
from .research_registry import ExperimentRegistry, ExperimentSpec


PROTOCOL_VERSION = "wong-choi-research-input-protocol/v1"
SOURCE_VERSION = "wong-choi-research-input-source/v1"
REPORT_VERSION = "wong-choi-research-input-audit/v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResearchSafetyError(RuntimeError):
    """Incomplete, mutated, or structurally unverifiable safety evidence."""


def _encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _object(value: Any, keys: set[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ResearchSafetyError(f"{name}: invalid schema")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchSafetyError(f"{name}: non-empty string required")
    return value


def _time(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, "time").replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchSafetyError("invalid ISO-8601 time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchSafetyError("time must include timezone")
    return parsed.astimezone(timezone.utc)


def _number(value: Any) -> bool:
    return type(value) is int or (type(value) is float and math.isfinite(value))


def _json(raw: bytes) -> Any:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ResearchSafetyError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def constant(value):
        raise ResearchSafetyError(f"non-finite JSON: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            constant(value)
        return number

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=finite_float)
    except (ValueError, UnicodeError) as exc:
        raise ResearchSafetyError("invalid evidence JSON") from exc


def _read(path: Path, digest: str) -> bytes:
    path = Path(path).expanduser().absolute()
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ResearchSafetyError("symlinked evidence is not accepted")
    if not path.is_file():
        raise ResearchSafetyError("evidence must be a regular file")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ResearchSafetyError("cannot read safety evidence") from exc
    if _sha(raw) != digest:
        raise ResearchSafetyError("evidence digest mismatch")
    return raw


def _protocol(raw: bytes, spec: ExperimentSpec) -> dict:
    value = _object(
        _json(raw),
        {
            "schema_version",
            "spec_id",
            "domain",
            "baseline_commit",
            "candidate_commit",
            "ruler_id",
            "ruler_digest",
            "sources",
            "fields",
            "required_markets",
            "market_methodology",
            "postflight_protocol_digest",
        },
        "protocol",
    )
    expected = {
        "schema_version": PROTOCOL_VERSION,
        "spec_id": spec.record_id,
        "domain": spec.domain.value,
        "baseline_commit": spec.baseline_commit,
        "candidate_commit": spec.candidate_commit,
        "ruler_id": spec.evaluation_ruler_id,
        "ruler_digest": spec.evaluation_ruler_digest,
    }
    if any(value[key] != expected[key] for key in expected):
        raise ResearchSafetyError("protocol conflicts with registered spec/ruler")
    if not isinstance(value["postflight_protocol_digest"], str) or not _SHA256.fullmatch(
        value["postflight_protocol_digest"]
    ):
        raise ResearchSafetyError("postflight protocol digest must be SHA256")
    if not isinstance(value["sources"], dict) or not value["sources"]:
        raise ResearchSafetyError("protocol sources required")
    for source_id, digest in value["sources"].items():
        _text(source_id, "source_id")
        if not isinstance(digest, str) or not _SHA256.fullmatch(digest):
            raise ResearchSafetyError("source digest must be SHA256")
    fields = value["fields"]
    if not isinstance(fields, dict) or not fields:
        raise ResearchSafetyError("protocol field allowlist required")
    for name, rule in fields.items():
        _text(name, "field")
        _object(
            rule,
            {
                "source_id",
                "source_field",
                "kind",
                "value_type",
                "min_coverage",
                "max_neutral_fraction",
                "neutral_values",
                "min_unique",
                "max_age_seconds",
                "value_min",
                "value_max",
                "max_missing_rate_increase",
                "max_mean_shift",
            },
            "field rule",
        )
        _text(rule["source_field"], "source_field")
        if rule["source_id"] not in value["sources"] or rule["kind"] not in {"prerace", "historical", "odds"}:
            raise ResearchSafetyError("field source/kind not allowed")
        if rule["value_type"] not in {"number", "category"}:
            raise ResearchSafetyError("unsupported feature value type")
        for key in ("min_coverage", "max_neutral_fraction", "max_missing_rate_increase"):
            if not _number(rule[key]) or not 0 <= rule[key] <= 1:
                raise ResearchSafetyError(f"invalid field threshold: {key}")
        if rule["min_coverage"] <= 0 or rule["max_neutral_fraction"] >= 1:
            raise ResearchSafetyError("empty or entirely neutral fields cannot be allowed")
        if type(rule["min_unique"]) is not int or rule["min_unique"] < 1:
            raise ResearchSafetyError("min_unique must be positive integer")
        if rule["value_type"] == "number" and rule["min_unique"] < 2:
            raise ResearchSafetyError("numeric variation checks cannot be disabled")
        if not _number(rule["max_age_seconds"]) or rule["max_age_seconds"] <= 0:
            raise ResearchSafetyError("feature TTL must be positive")
        if not isinstance(rule["neutral_values"], list) or any(
            not (_number(item) or isinstance(item, str)) for item in rule["neutral_values"]
        ):
            raise ResearchSafetyError("neutral_values must contain scalar values")
        if rule["value_type"] == "number":
            if not _number(rule["max_mean_shift"]) or rule["max_mean_shift"] <= 0:
                raise ResearchSafetyError("numeric mean-shift bound must be preregistered and positive")
            if (
                not all(_number(rule[key]) for key in ("value_min", "value_max"))
                or rule["value_min"] >= rule["value_max"]
            ):
                raise ResearchSafetyError("numeric feature bounds invalid")
        elif rule["value_min"] is not None or rule["value_max"] is not None or rule["max_mean_shift"] is not None:
            raise ResearchSafetyError("category feature bounds must be null")
    markets = value["required_markets"]
    if (
        not isinstance(markets, dict)
        or any(not isinstance(item, str) or not item.strip() for item in markets)
        or any(not isinstance(source, str) or source not in value["sources"] for source in markets.values())
    ):
        raise ResearchSafetyError("required_markets must map each market to a frozen source")
    if value["market_methodology"] is not None:
        _text(value["market_methodology"], "market_methodology")
    return value


def _source(raw: bytes, source_id: str, domain: str) -> dict[str, dict]:
    value = _object(_json(raw), {"schema_version", "source_id", "domain", "records"}, "source")
    if value["schema_version"] != SOURCE_VERSION or value["source_id"] != source_id or value["domain"] != domain:
        raise ResearchSafetyError("source identity conflicts with protocol")
    if not isinstance(value["records"], list) or not value["records"]:
        raise ResearchSafetyError("source records required")
    result = {}
    price_ids = set()
    for record in value["records"]:
        _object(
            record,
            {
                "record_id",
                "event_id",
                "entity_id",
                "kind",
                "observed_at",
                "available_at",
                "history_through",
                "values",
                "market_id",
                "snapshot_id",
                "in_play",
            },
            "source record",
        )
        for key in ("record_id", "event_id", "entity_id"):
            _text(record[key], key)
        if record["record_id"] in result:
            raise ResearchSafetyError("duplicate source record identity")
        if record["kind"] not in {"prerace", "historical", "odds", "result"}:
            raise ResearchSafetyError("unrecognized source record kind")
        observed, available = _time(record["observed_at"]), _time(record["available_at"])
        if observed > available:
            raise ResearchSafetyError("source observation after availability")
        if not isinstance(record["values"], dict) or not record["values"]:
            raise ResearchSafetyError("source record values required")
        if record["kind"] == "historical":
            _time(record["history_through"])
        elif record["history_through"] is not None:
            raise ResearchSafetyError("nonhistorical source has history cutoff")
        if record["kind"] == "odds":
            _text(record["market_id"], "market_id")
            if (
                type(record["snapshot_id"]) is not int
                or record["snapshot_id"] < 0
                or type(record["in_play"]) is not bool
            ):
                raise ResearchSafetyError("invalid odds snapshot identity/state")
            price_id = (record["event_id"], record["entity_id"], record["market_id"], record["snapshot_id"])
            if price_id in price_ids:
                raise ResearchSafetyError("duplicate price snapshot id")
            price_ids.add(price_id)
        elif any(record[key] is not None for key in ("market_id", "snapshot_id", "in_play")):
            raise ResearchSafetyError("nonodds record contains price metadata")
        result[record["record_id"]] = record
    return result


@dataclass(frozen=True)
class InputSafetyReport:
    spec_id: str
    dataset_manifest_id: str
    dataset_artifact_digest: str
    sample_hash: str
    protocol_digest: str
    sources: tuple[tuple[str, str], ...]
    checked_cells: int
    findings: tuple[str, ...]
    field_health: tuple[dict, ...]

    @property
    def input_checks_passed(self) -> bool:
        return not self.findings

    @property
    def proposal_ready(self) -> bool:
        # Input evidence cannot stand in for executed controls/ablation/power.
        return False

    def to_payload(self) -> dict:
        value = {
            "schema_version": REPORT_VERSION,
            "spec_id": self.spec_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "dataset_artifact_digest": self.dataset_artifact_digest,
            "sample_hash": self.sample_hash,
            "protocol_digest": self.protocol_digest,
            "sources": dict(self.sources),
            "checked_cells": self.checked_cells,
            "findings": list(self.findings),
            "field_health": list(self.field_health),
            "input_checks_passed": self.input_checks_passed,
            "proposal_ready": self.proposal_ready,
        }
        value["content_hash"] = _sha(_encoded(value))
        return value


def _reference(reference: Any, sources: Mapping, *, keys: set[str]) -> dict:
    _object(reference, keys, "input reference")
    source_id = _text(reference["source_id"], "reference source_id")
    record_id = _text(reference["record_id"], "reference record_id")
    if source_id not in sources or record_id not in sources[source_id]:
        raise ResearchSafetyError("input reference not in frozen sources")
    return sources[source_id][record_id]


def _price_order_index(records: Mapping[str, dict]) -> dict[str, tuple[str, ...]]:
    # One scan per source, not one full-corpus scan per entity/feature.
    groups = defaultdict(list)
    for record in records.values():
        if record["kind"] == "odds":
            groups[(record["event_id"], record["entity_id"], record["market_id"])].append(record)
    index = {}
    for group in groups.values():
        earliest = min(group, key=lambda item: item["snapshot_id"])
        first_time = _time(earliest["observed_at"])
        conflict = any(_time(item["observed_at"]) < first_time for item in group)
        for record in group:
            findings = []
            if record["record_id"] != earliest["record_id"]:
                findings.append("price_not_earliest_snapshot")
            if conflict:
                findings.append("price_id_time_order_conflict")
            index[record["record_id"]] = tuple(findings)
    return index


def _price_findings(record: dict, order_index: Mapping, decision: datetime, event: datetime) -> list[str]:
    if record["kind"] != "odds":
        return ["price_not_odds_source"]
    findings = list(order_index[record["record_id"]])
    if record["in_play"] or _time(record["available_at"]) > decision or _time(record["observed_at"]) >= event:
        findings.append("price_not_verifiable_prematch")
    price = record["values"].get("decimal_odds")
    if not _number(price) or price <= 1:
        findings.append("invalid_decimal_odds")
    return findings


def _row_audit(
    row, rows_by_id, protocol, sources, price_indexes, ruler, seen_units, groups, event_groups, buckets, findings
):
    prefix = row["row_id"]

    def flag(reason):
        findings.add(f"{prefix}:{reason}")

    payload = row["payload"]
    inputs = _object(
        payload.get("research_inputs"),
        {"event_id", "group_id", "decision_at", "entities", "fit_row_ids"},
        "research_inputs",
    )
    event_id, group_id = _text(inputs["event_id"], "event_id"), _text(inputs["group_id"], "group_id")
    decision, event = _time(inputs["decision_at"]), _time(row["event_at"])
    if decision >= event:
        flag("decision_not_before_event")
    cohorts = _object(payload.get("cohorts"), set(ruler.cohorts), "row cohorts")
    for key, value in cohorts.items():
        _text(value, f"cohort {key}")
    fold = payload.get("fold")
    if (
        "fold" not in payload
        or (row["split"] == "dev" and (type(fold) is not int or fold < 1))
        or (row["split"] != "dev" and fold is not None)
    ):
        flag("invalid_fold")
    scope = cohorts.get("family", cohorts.get("market_family", "all"))
    unit = (event_id, scope)
    if unit in seen_units:
        flag("duplicate_evaluation_event")
    seen_units.add(unit)
    partition = (row["split"], fold)
    if group_id in groups and groups[group_id] != partition:
        flag("group_crosses_split_or_fold")
    groups[group_id] = partition
    if event_id in event_groups and event_groups[event_id] != (group_id, partition):
        flag("event_group_or_partition_conflict")
    event_groups[event_id] = (group_id, partition)
    fit_ids = inputs["fit_row_ids"]
    if (
        not isinstance(fit_ids, list)
        or any(not isinstance(item, str) for item in fit_ids)
        or len(set(fit_ids)) != len(fit_ids)
    ):
        raise ResearchSafetyError("fit_row_ids must be unique string list")
    for fit_id in fit_ids:
        fitted = rows_by_id.get(fit_id)
        if (
            not fitted
            or fitted["split"] != "train"
            or fit_id == prefix
            or _time(fitted["available_at"]) > decision
            or _time(fitted["event_at"]).date() >= event.date()
        ):
            flag("preprocessor_fit_not_prior_train_only")
    if not isinstance(inputs["entities"], list) or not inputs["entities"]:
        raise ResearchSafetyError("non-empty entity inputs required")
    seen_entities = set()
    checked = 0
    for entity in inputs["entities"]:
        _object(entity, {"entity_id", "features", "prices"}, "entity")
        entity_id = _text(entity["entity_id"], "entity_id")
        if entity_id in seen_entities:
            flag("duplicate_entity")
        seen_entities.add(entity_id)
        features = entity["features"]
        if not isinstance(features, dict) or set(features) != set(protocol["fields"]):
            flag("feature_allowlist_mismatch")
            continue
        for name, rule in protocol["fields"].items():
            reference = features[name]
            record = _reference(reference, sources, keys={"source_id", "record_id", "value"})
            checked += 1
            value = reference["value"]
            if (
                reference["source_id"] != rule["source_id"]
                or record["kind"] != rule["kind"]
                or record["kind"] == "result"
            ):
                flag(f"{name}:source_kind_mismatch")
            if record["event_id"] != event_id or record["entity_id"] != entity_id:
                flag(f"{name}:source_subject_mismatch")
            if rule["source_field"] not in record["values"] or _encoded(value) != _encoded(
                record["values"].get(rule["source_field"])
            ):
                flag(f"{name}:source_value_mismatch")
            if _time(record["available_at"]) > decision:
                flag(f"{name}:not_available_at_decision")
            if (decision - _time(record["observed_at"])).total_seconds() > rule["max_age_seconds"]:
                flag(f"{name}:stale_feature")
            if record["kind"] == "historical" and (
                _time(record["history_through"]).date() >= event.date()
                or _time(record["history_through"]) > _time(record["observed_at"])
            ):
                flag(f"{name}:history_contains_current_or_future_event")
            if record["kind"] == "odds":
                for reason in _price_findings(record, price_indexes[reference["source_id"]], decision, event):
                    flag(f"{name}:{reason}")
            missing = value is None or (isinstance(value, str) and not value.strip())
            neutral = not missing and any(
                _encoded(value) == _encoded(item) or (_number(value) and _number(item) and value == item)
                for item in rule["neutral_values"]
            )
            if not missing and (
                (rule["value_type"] == "number" and not _number(value))
                or (rule["value_type"] == "category" and not isinstance(value, str))
            ):
                flag(f"{name}:invalid_feature_type")
            if (
                not missing
                and rule["value_type"] == "number"
                and _number(value)
                and not rule["value_min"] <= value <= rule["value_max"]
            ):
                flag(f"{name}:out_of_range")
            for cohort_key, cohort_value in [("__all__", "all"), *sorted(cohorts.items())]:
                buckets[(row["split"], scope, cohort_key, cohort_value, name)].append((missing, neutral, value))
        prices = entity["prices"]
        if not isinstance(prices, list):
            raise ResearchSafetyError("prices must be a list")
        markets = []
        for reference in prices:
            record = _reference(reference, sources, keys={"source_id", "record_id", "market_id"})
            markets.append(_text(reference["market_id"], "price market_id"))
            if (
                record["event_id"] != event_id
                or record["entity_id"] != entity_id
                or record["market_id"] != reference["market_id"]
            ):
                flag("price_subject_or_market_mismatch")
            if protocol["required_markets"].get(reference["market_id"]) != reference["source_id"]:
                flag("price_source_not_preregistered_for_market")
            for reason in _price_findings(record, price_indexes[reference["source_id"]], decision, event):
                flag(reason)
        if sorted(markets) != sorted(protocol["required_markets"]):
            flag("required_price_markets_mismatch")
    return checked


def _partition_findings(rows: list[dict], findings: set[str]) -> None:
    split_dates, fold_dates = defaultdict(set), defaultdict(set)
    for row in rows:
        day = _time(row["event_at"]).date()
        split_dates[row["split"]].add(day)
        fold = row["payload"].get("fold")
        if row["split"] == "dev" and type(fold) is int and fold > 0:
            fold_dates[fold].add(day)
    if any(
        max(split_dates[left]) >= min(split_dates[right]) for left, right in (("train", "dev"), ("dev", "terminal"))
    ):
        findings.add("whole_date_split_chronology_conflict")
    folds = sorted(fold_dates)
    if (
        len(folds) < 2
        or folds != list(range(1, len(folds) + 1))
        or any(max(fold_dates[left]) >= min(fold_dates[right]) for left, right in zip(folds, folds[1:]))
    ):
        findings.add("development_fold_chronology_conflict")


def _health(buckets: Mapping, protocol: dict, findings: set[str]) -> tuple[dict, ...]:
    health = []
    for key, cells in sorted(buckets.items()):
        split, scope, cohort_key, cohort_value, name = key
        rule = protocol["fields"][name]
        missing = sum(item[0] for item in cells) / len(cells)
        neutral = sum(item[1] for item in cells) / len(cells)
        distinct = len({_encoded(value) for absent, is_neutral, value in cells if not absent and not is_neutral})
        prefix = f"{split}:{scope}:{cohort_key}={cohort_value}:{name}"
        if 1 - missing < rule["min_coverage"]:
            findings.add(f"{prefix}:coverage_below_protocol")
        if neutral > rule["max_neutral_fraction"]:
            findings.add(f"{prefix}:neutral_fraction_above_protocol")
        if distinct < rule["min_unique"]:
            findings.add(f"{prefix}:insufficient_non_neutral_variation")
        prior = buckets.get(("train", *key[1:]))
        numeric = (
            [value for absent, is_neutral, value in cells if not absent and not is_neutral and _number(value)]
            if rule["value_type"] == "number"
            else []
        )
        reference_numeric = (
            [value for absent, is_neutral, value in (prior or []) if not absent and not is_neutral and _number(value)]
            if rule["value_type"] == "number"
            else []
        )
        mean_shift = fmean(numeric) - fmean(reference_numeric) if numeric and reference_numeric else None
        if split != "train":
            if not prior:
                findings.add(f"{prefix}:unseen_training_cohort")
            elif missing - sum(item[0] for item in prior) / len(prior) > rule["max_missing_rate_increase"]:
                findings.add(f"{prefix}:missingness_drift")
            if mean_shift is not None and abs(mean_shift) > rule["max_mean_shift"]:
                findings.add(f"{prefix}:mean_shift_above_protocol")
        health.append(
            {
                "split": split,
                "scope": scope,
                "cohort_key": cohort_key,
                "cohort_value": cohort_value,
                "field": name,
                "cells": len(cells),
                "missing_fraction": missing,
                "neutral_fraction": neutral,
                "non_neutral_unique": distinct,
                "numeric_min": min(numeric) if numeric else None,
                "numeric_max": max(numeric) if numeric else None,
                "numeric_mean": fmean(numeric) if numeric else None,
                "mean_shift_from_train": mean_shift,
            }
        )
    return tuple(health)


def audit_research_inputs(
    spec: ExperimentSpec,
    *,
    dataset_snapshot: Path,
    protocol_path: Path,
    source_paths: Mapping[str, Path],
    registry: ExperimentRegistry,
) -> InputSafetyReport:
    """Audit frozen exports; a successful input audit never authorizes a proposal.

    Values are checked per entity, split, family, and frozen ruler cohort. Fit
    lineage is conservative train-only. Historical features must exclude the
    event's UTC day, matching the evaluation layer's whole-date partitions.
    Domain exporters must use existing data_contract/racing_data_health checks,
    not treat this normalized audit as a replacement for their source audits.
    """
    spec.validate()
    snapshot = load_dataset_snapshot(dataset_snapshot)
    dataset = snapshot.manifest
    if (
        registry.load(spec.record_id) != spec.to_payload()
        or registry.load(dataset.record_id) != dataset.to_payload()
        or dataset.spec_id != spec.record_id
        or dataset.domain is not spec.domain
    ):
        raise ResearchSafetyError("input audit differs from registered lineage")
    protocol = _protocol(_read(protocol_path, spec.protocol_artifact_digest), spec)
    ruler = load_evaluation_ruler(spec.domain)
    ruler_path = DEFAULT_RULER_ROOT / f"{ruler.ruler_id}.json"
    _read(ruler_path, spec.evaluation_ruler_digest)
    if ruler.ruler_id != spec.evaluation_ruler_id:
        raise ResearchSafetyError("input audit ruler mismatch")
    if set(source_paths) != set(protocol["sources"]):
        raise ResearchSafetyError("exact preregistered source set required")
    sources = {
        name: _source(_read(source_paths[name], digest), name, spec.domain.value)
        for name, digest in protocol["sources"].items()
    }
    price_indexes = {name: _price_order_index(records) for name, records in sources.items()}
    rows_raw = _read(snapshot.path / "rows.jsonl", dataset.artifact_digest)
    rows = [_json(line) for line in rows_raw.splitlines()]
    rows_by_id = {row["row_id"]: row for row in rows}
    findings = set()
    _partition_findings(rows, findings)
    if any(rule["kind"] == "odds" for rule in protocol["fields"].values()) and not protocol["market_methodology"]:
        findings.add("market_feature_without_explicit_methodology")
    if ruler.price_snapshot_policy and not protocol["required_markets"]:
        findings.add("ruler_price_evidence_missing")
    buckets = defaultdict(list)
    seen_units, groups, event_groups = set(), {}, {}
    checked = 0
    for row in rows:
        checked += _row_audit(
            row,
            rows_by_id,
            protocol,
            sources,
            price_indexes,
            ruler,
            seen_units,
            groups,
            event_groups,
            buckets,
            findings,
        )
    health = _health(buckets, protocol, findings)
    # Detect concurrent replacement of any evidence read during this audit.
    _read(protocol_path, spec.protocol_artifact_digest)
    _read(ruler_path, spec.evaluation_ruler_digest)
    for name, digest in protocol["sources"].items():
        _read(source_paths[name], digest)
    if load_dataset_snapshot(snapshot.path).manifest.to_payload() != dataset.to_payload():
        raise ResearchSafetyError("dataset changed during input audit")
    return InputSafetyReport(
        spec.record_id,
        dataset.record_id,
        dataset.artifact_digest,
        dataset.sample_hash,
        spec.protocol_artifact_digest,
        tuple(sorted(protocol["sources"].items())),
        checked,
        tuple(sorted(findings)),
        health,
    )


def prepare_scoring_inputs(rows: list[dict], protocol: dict, sources: Mapping, label_field: str) -> dict[str, dict]:
    """Project audited rows into the only data passed to a harness scorer.

    Current-event labels, split/fold annotations and raw source paths are not
    present. Prior training labels are explicit and were checked by the input
    audit. Market prices enter scoring only with an explicit methodology.
    Caller must audit these exact bytes before using this projection.
    """
    by_id = {row["row_id"]: row for row in rows}

    def case(row):
        declared = row["payload"]["research_inputs"]
        entities = []
        for entity in declared["entities"]:
            prices = {}
            if protocol["market_methodology"]:
                for reference in entity["prices"]:
                    prices[reference["market_id"]] = sources[reference["source_id"]][reference["record_id"]]["values"][
                        "decimal_odds"
                    ]
            entities.append(
                {
                    "entity_id": entity["entity_id"],
                    "features": {name: reference["value"] for name, reference in sorted(entity["features"].items())},
                    "prices": prices,
                }
            )
        return {"event_id": declared["event_id"], "decision_at": declared["decision_at"], "entities": entities}

    projected = {}
    for row in rows:
        value = case(row)
        value["training_rows"] = []
        for fit_id in row["payload"]["research_inputs"]["fit_row_ids"]:
            fit = by_id[fit_id]
            if label_field not in fit["payload"]:
                raise ResearchSafetyError("training label missing from frozen row")
            value["training_rows"].append({"inputs": case(fit), "label": fit["payload"][label_field]})
        projected[row["row_id"]] = value
    return projected
