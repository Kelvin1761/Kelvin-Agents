from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.contracts import Domain
from shared_wong_choi.evaluation_rulers import DEFAULT_RULER_ROOT, load_evaluation_ruler
from shared_wong_choi.research_dataset import DatasetSource, SplitPolicy, StorageTier, build_dataset_snapshot
from shared_wong_choi.research_registry import ExperimentRegistry, ExperimentSpec
from shared_wong_choi.research_safety import ResearchSafetyError, audit_research_inputs


def encoded(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode()


def source_record(index, entity, event, value, *, price=False):
    return {
        "record_id": f"{'price' if price else 'feature'}-{index}-{entity}",
        "event_id": f"event-{index}",
        "entity_id": entity,
        "kind": "odds" if price else "prerace",
        "observed_at": (event - timedelta(hours=2)).isoformat(),
        "available_at": (event - timedelta(hours=1)).isoformat(),
        "history_through": None,
        "values": {"decimal_odds" if price else "rating": value},
        "market_id": "moneyline" if price else None,
        "snapshot_id": index * 100 + int(entity) if price else None,
        "in_play": False if price else None,
    }


def fixture_inputs(tmp_path, mutate=None, *, domain=Domain.TENNIS, commits=None):
    ruler = load_evaluation_ruler(domain)
    spec = ExperimentSpec(
        record_id=f"wc:{domain.value}:experiment-spec:safety-inputs",
        domain=domain,
        created_at="2026-08-30T00:00:00+00:00",
        hypothesis="input audit fixture, not a model experiment",
        evaluation_ruler_id=ruler.ruler_id,
        evaluation_ruler_digest=hashlib.sha256(
            (DEFAULT_RULER_ROOT / f"{ruler.ruler_id}.json").read_bytes()
        ).hexdigest(),
        baseline_commit=commits[0] if commits else "a" * 40,
        candidate_commit=commits[1] if commits else "b" * 40,
        preregistered_metrics=tuple(metric["name"] for metric in ruler.metrics),
        seed=ruler.bootstrap["seed"],
        commands=("python3 frozen_harness.py",),
        protocol_artifact_digest="f" * 64,
    )
    protocol = {
        "schema_version": "wong-choi-research-input-protocol/v1",
        "spec_id": spec.record_id,
        "domain": domain.value,
        "baseline_commit": spec.baseline_commit,
        "candidate_commit": spec.candidate_commit,
        "ruler_id": spec.evaluation_ruler_id,
        "ruler_digest": spec.evaluation_ruler_digest,
        "market_methodology": None,
        "postflight_protocol_digest": "e" * 64,
        "sources": {},
        "fields": {
            "rating": {
                "source_id": "prerace-feed",
                "source_field": "rating",
                "kind": "prerace",
                "value_type": "number",
                "min_coverage": 1.0,
                "max_neutral_fraction": 0.5,
                "neutral_values": [60],
                "min_unique": 2,
                "max_age_seconds": 86400,
                "value_min": 0,
                "value_max": 100,
                "max_missing_rate_increase": 0.1,
                "max_mean_shift": 10.0,
            }
        },
        "required_markets": {"moneyline": "prerace-feed"},
    }
    rows, records = [], []
    for index in range(6):
        event = datetime(2026, 8, 10, 12, tzinfo=timezone.utc) + timedelta(days=index)
        entities = []
        for entity in ("1", "2"):
            value = 70 + index + int(entity)
            record = source_record(index, entity, event, value)
            price = source_record(index, entity, event, 2.0 + int(entity) / 10, price=True)
            records.extend([record, price])
            entities.append(
                {
                    "entity_id": entity,
                    "features": {
                        "rating": {"source_id": "prerace-feed", "record_id": record["record_id"], "value": value}
                    },
                    "prices": [
                        {"source_id": "prerace-feed", "record_id": price["record_id"], "market_id": "moneyline"}
                    ],
                }
            )
        rows.append(
            {
                "row_id": f"row-{index}",
                "event_at": event.isoformat(),
                "available_at": (event + timedelta(hours=4)).isoformat(),
                "payload": {
                    "fold": index - 1 if index in (2, 3) else None,
                    "cohorts": {
                        key: "family-a" if key in {"family", "market_family"} else "fixture" for key in ruler.cohorts
                    },
                    "winner": "1",  # Evaluation label is deliberately outside the scoring allowlist.
                    "research_inputs": {
                        "event_id": f"event-{index}",
                        "group_id": f"meeting-{index}",
                        "decision_at": (event - timedelta(minutes=10)).isoformat(),
                        "entities": entities,
                        "fit_row_ids": ["row-0"] if index >= 2 else [],
                    },
                },
            }
        )
    if mutate:
        mutate(protocol, rows, records)
    source_path = tmp_path / "prerace.json"
    source_path.write_bytes(
        encoded(
            {
                "schema_version": "wong-choi-research-input-source/v1",
                "source_id": "prerace-feed",
                "domain": domain.value,
                "records": records,
            }
        )
    )
    protocol["sources"]["prerace-feed"] = hashlib.sha256(source_path.read_bytes()).hexdigest()
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_bytes(encoded(protocol))
    spec = replace(spec, protocol_artifact_digest=hashlib.sha256(protocol_path.read_bytes()).hexdigest())
    raw_root = tmp_path / "raw"
    raw_root.mkdir()
    rows_path = raw_root / "rows.jsonl"
    rows_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    dataset = build_dataset_snapshot(
        spec,
        sources=(
            DatasetSource(
                "settled", StorageTier.HOT, raw_root, rows_path, "2026-08-29T00:00:00+00:00", artifact_digest(raw_root)
            ),
        ),
        split_policy=SplitPolicy("2026-08-11T23:59:00+00:00", "2026-08-13T23:59:00+00:00", "2026-08-29T23:59:00+00:00"),
        snapshot_root=tmp_path / "snapshots",
    )
    registry = ExperimentRegistry(tmp_path / "registry")
    registry.append(spec)
    registry.append(dataset.manifest)
    return spec, {
        "dataset_snapshot": dataset.path,
        "protocol_path": protocol_path,
        "source_paths": {"prerace-feed": source_path},
        "registry": registry,
    }


@pytest.mark.parametrize("domain", list(Domain))
def test_verified_inputs_are_reproducible_but_not_complete_safety_approval(tmp_path, domain):
    spec, arguments = fixture_inputs(tmp_path, domain=domain)
    first = audit_research_inputs(spec, **arguments)
    assert first.input_checks_passed is True
    assert first.proposal_ready is False
    assert first.to_payload() == audit_research_inputs(spec, **arguments).to_payload()
    assert first.checked_cells == 12


@pytest.mark.parametrize(
    "fault",
    [
        "future_feature",
        "result_source",
        "unknown_feature",
        "changed_value",
        "post_start_decision",
        "self_fit",
        "terminal_fit",
        "duplicate_entity",
        "group_overlap",
        "same_event_history",
        "stale",
        "missing",
        "constant",
        "neutral",
        "range",
        "live_odds",
        "late_odds",
        "empty_odds",
        "hidden_market_proxy",
    ],
)
def test_input_faults_cannot_be_called_safe(tmp_path, fault):
    def mutate(protocol, rows, records):
        inputs = rows[2]["payload"]["research_inputs"]
        if fault == "future_feature":
            records[8]["available_at"] = rows[2]["event_at"]
        elif fault == "result_source":
            records[8]["kind"] = "result"
        elif fault == "unknown_feature":
            inputs["entities"][0]["features"]["winner"] = {"value": 1}
        elif fault == "changed_value":
            inputs["entities"][0]["features"]["rating"]["value"] = 99
        elif fault == "post_start_decision":
            inputs["decision_at"] = rows[2]["event_at"]
        elif fault == "self_fit":
            inputs["fit_row_ids"] = ["row-2"]
        elif fault == "terminal_fit":
            inputs["fit_row_ids"] = ["row-4"]
        elif fault == "duplicate_entity":
            inputs["entities"].append(inputs["entities"][0])
        elif fault == "group_overlap":
            inputs["group_id"] = rows[0]["payload"]["research_inputs"]["group_id"]
        elif fault == "same_event_history":
            protocol["fields"]["rating"]["kind"] = "historical"
            for row, event_index in zip(rows, range(6)):
                for record in records[event_index * 4 : event_index * 4 + 4 : 2]:
                    record["kind"] = "historical"
                    record["history_through"] = row["event_at"]
        elif fault == "stale":
            records[8]["observed_at"] = "2020-01-01T00:00:00+00:00"
        elif fault in {"missing", "constant", "neutral", "range"}:
            for row_index, row in enumerate(rows):
                for entity_index, entity in enumerate(row["payload"]["research_inputs"]["entities"]):
                    value = {"missing": None, "constant": 77, "neutral": 60, "range": 101}[fault]
                    entity["features"]["rating"]["value"] = value
                    records[row_index * 4 + entity_index * 2]["values"]["rating"] = value
        elif fault == "live_odds":
            records[9]["in_play"] = True
        elif fault == "late_odds":
            original = records[9]
            later = dict(
                original,
                record_id="later-price",
                snapshot_id=original["snapshot_id"] + 10,
                available_at=inputs["decision_at"],
            )
            records.append(later)
            inputs["entities"][0]["prices"][0]["record_id"] = later["record_id"]
        elif fault == "empty_odds":
            inputs["entities"][0]["prices"] = []
        elif fault == "hidden_market_proxy":
            protocol["fields"]["rating"]["kind"] = "odds"
            protocol["fields"]["rating"]["source_field"] = "decimal_odds"

    spec, arguments = fixture_inputs(tmp_path, mutate)
    report = audit_research_inputs(spec, **arguments)
    assert report.input_checks_passed is False, fault
    assert report.proposal_ready is False
    assert report.findings


@pytest.mark.parametrize("target", ["protocol_path", "source"])
def test_changed_evidence_bytes_fail_closed(tmp_path, target):
    spec, arguments = fixture_inputs(tmp_path)
    path = arguments["protocol_path"] if target == "protocol_path" else arguments["source_paths"]["prerace-feed"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ResearchSafetyError, match="digest"):
        audit_research_inputs(spec, **arguments)


def test_evidence_via_symlink_is_refused(tmp_path):
    spec, arguments = fixture_inputs(tmp_path)
    link = tmp_path / "source-link.json"
    link.symlink_to(arguments["source_paths"]["prerace-feed"])
    arguments["source_paths"]["prerace-feed"] = link
    with pytest.raises(ResearchSafetyError, match="symlink"):
        audit_research_inputs(spec, **arguments)


def test_missing_protocol_source_is_not_best_effort(tmp_path):
    spec, arguments = fixture_inputs(tmp_path)
    arguments["source_paths"] = {}
    with pytest.raises(ResearchSafetyError, match="source"):
        audit_research_inputs(spec, **arguments)


def test_numeric_value_in_category_column_is_a_finding_not_a_crash(tmp_path):
    def mutate(protocol, rows, records):
        rule = protocol["fields"]["rating"]
        rule.update(value_type="category", value_min=None, value_max=None, max_mean_shift=None)

    spec, arguments = fixture_inputs(tmp_path, mutate)
    report = audit_research_inputs(spec, **arguments)
    assert any("invalid_feature_type" in reason for reason in report.findings)


def test_overflow_json_number_is_refused_even_with_matching_hash(tmp_path):
    spec, arguments = fixture_inputs(tmp_path)
    raw = arguments["protocol_path"].read_bytes().replace(b'"max_age_seconds": 86400', b'"max_age_seconds": 1e999')
    arguments["protocol_path"].write_bytes(raw)
    spec = replace(spec, protocol_artifact_digest=hashlib.sha256(raw).hexdigest())
    registry = ExperimentRegistry(tmp_path / "replacement-registry")
    registry.append(spec)
    # Registry need not be weakened to inject malformed protocol bytes.
    from shared_wong_choi.research_dataset import load_dataset_snapshot

    registry.append(load_dataset_snapshot(arguments["dataset_snapshot"]).manifest)
    arguments["registry"] = registry
    with pytest.raises(ResearchSafetyError, match="non-finite"):
        audit_research_inputs(spec, **arguments)


@pytest.mark.parametrize(
    "fault", ["missingness_drift", "unseen_cohort", "fold_order", "duplicate_event", "wrong_price_market"]
)
def test_partition_and_population_faults_are_reported(tmp_path, fault):
    def mutate(protocol, rows, records):
        if fault == "missingness_drift":
            protocol["fields"]["rating"]["min_coverage"] = 0.5
            rows[2]["payload"]["research_inputs"]["entities"][0]["features"]["rating"]["value"] = None
            records[8]["values"]["rating"] = None
        elif fault == "unseen_cohort":
            rows[2]["payload"]["cohorts"]["surface"] = "clay"
        elif fault == "fold_order":
            rows[2]["payload"]["fold"], rows[3]["payload"]["fold"] = 2, 1
        elif fault == "duplicate_event":
            rows[3]["payload"]["research_inputs"]["event_id"] = "event-2"
        else:
            rows[2]["payload"]["research_inputs"]["entities"][0]["prices"][0]["market_id"] = "wrong"

    spec, arguments = fixture_inputs(tmp_path, mutate)
    report = audit_research_inputs(spec, **arguments)
    expected = {
        "fold_order": "fold_chronology",
        "duplicate_event": "duplicate_evaluation_event",
        "wrong_price_market": "price_subject_or_market_mismatch",
        "unseen_cohort": "unseen_training_cohort",
    }.get(fault, fault)
    assert any(expected in reason for reason in report.findings)


def test_missing_evidence_structure_never_defaults_to_safe(tmp_path):
    def mutate(protocol, rows, records):
        del rows[2]["payload"]["research_inputs"]

    spec, arguments = fixture_inputs(tmp_path, mutate)
    with pytest.raises(ResearchSafetyError, match="research_inputs"):
        audit_research_inputs(spec, **arguments)


def test_field_rule_cannot_disable_all_numeric_variation_checks(tmp_path):
    def mutate(protocol, rows, records):
        protocol["fields"]["rating"]["min_unique"] = 1

    spec, arguments = fixture_inputs(tmp_path, mutate)
    with pytest.raises(ResearchSafetyError, match="numeric variation"):
        audit_research_inputs(spec, **arguments)


def test_populated_nonconstant_feature_drift_is_not_missed(tmp_path):
    def mutate(protocol, rows, records):
        for index in (2, 3):
            for entity_index, entity in enumerate(rows[index]["payload"]["research_inputs"]["entities"]):
                value = 95 + index + entity_index
                entity["features"]["rating"]["value"] = value
                records[index * 4 + entity_index * 2]["values"]["rating"] = value

    spec, arguments = fixture_inputs(tmp_path, mutate)
    report = audit_research_inputs(spec, **arguments)
    assert any("mean_shift_above_protocol" in reason for reason in report.findings)
