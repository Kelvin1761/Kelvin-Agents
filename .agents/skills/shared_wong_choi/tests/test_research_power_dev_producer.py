from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_dataset import load_dataset_snapshot
from shared_wong_choi.research_power_dev_producer import (
    produce_power_dev_observation,
    verify_power_dev_observation,
)
from shared_wong_choi.research_power_projection import build_power_variance_projection
from shared_wong_choi.research_power_variance import inspect_power_variance
from test_research_safety import fixture_inputs


RULER_ROOT = Path(__file__).resolve().parents[1] / "resources" / "evaluation_rulers"
AS_OF = datetime(2026, 9, 2, 4, 0, tzinfo=timezone.utc)
METRICS = {
    "gold": 0.0,
    "good_positional": 1.0,
    "top3_capture_at5": 0.6,
    "mean_top3_model_rank": 3.0,
    "competitive_recall_at5": 0.5,
    "ndcg_at5": 0.7,
    "top5_pairwise_auc": 0.65,
}


def setup_inputs(tmp_path, domain=Domain.AU, role="baseline"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    spec, inputs = fixture_inputs(tmp_path, domain=domain)
    snapshot = load_dataset_snapshot(inputs["dataset_snapshot"])
    rows = [json.loads(line) for line in (snapshot.path / "rows.jsonl").read_text().splitlines()]
    selected = [row for row in rows if row["split"] == "dev"]
    metrics = {
        "schema_version": "wong-choi-evaluation-observations/v1",
        "domain": domain.value,
        "sample_hash": snapshot.manifest.sample_hash,
        "dataset_manifest_id": snapshot.manifest.record_id,
        "dataset_artifact_digest": snapshot.manifest.artifact_digest,
        "observations": [
            {
                "row_id": row["row_id"],
                "event_at": row["event_at"],
                "split": "dev",
                "fold": row["payload"]["fold"],
                "cohorts": row["payload"]["cohorts"],
                "metrics": dict(METRICS),
            }
            for row in selected
        ],
    }
    metrics_path = tmp_path / f"{role}-metrics.json"
    metrics_path.write_text(json.dumps(metrics, sort_keys=True) + "\n")
    variant_id = "known-good" if role == "baseline" else "neutral-jitter-v1"
    variant = {
        "schema_version": "wong-choi-power-variant-manifest/v1",
        "domain": domain.value,
        "role": role,
        "variant_id": variant_id,
        "engine_commit": "a" * 40,
        "purpose": "known_good" if role == "baseline" else "neutral_variance_probe",
        "registered_at": "2026-09-02T02:00:00+00:00",
        "selected_by_outcome": False,
        "terminal_accessed": False,
        "model_change": False,
        "configuration": {"mode": variant_id},
    }
    variant_path = tmp_path / f"{role}-variant.json"
    variant_path.write_text(json.dumps(variant, sort_keys=True) + "\n")
    protocol = {
        "schema_version": "wong-choi-power-neutral-protocol/v1",
        "domain": domain.value,
        "protocol_id": "neutral-jitter-v1",
        "comparison_kind": "neutral_perturbation",
        "preregistered_at": "2026-09-02T01:00:00+00:00",
        "selected_by_outcome": False,
        "baseline_variant_id": "known-good",
        "comparator_variant_id": "neutral-jitter-v1",
    }
    protocol_path = tmp_path / "power-neutral-protocol.json"
    protocol_path.write_text(json.dumps(protocol, sort_keys=True) + "\n")
    return spec, snapshot, metrics, metrics_path, variant, variant_path, protocol_path


def produce(tmp_path, *, domain=Domain.AU, role="baseline", mutate=None):
    _spec, snapshot, metrics, metrics_path, variant, variant_path, protocol_path = setup_inputs(
        tmp_path, domain, role
    )
    if mutate:
        mutate(metrics, variant)
        metrics_path.write_text(json.dumps(metrics, sort_keys=True) + "\n")
        variant_path.write_text(json.dumps(variant, sort_keys=True) + "\n")
    output = tmp_path / f"{role}-dev-observations.json"
    payload = produce_power_dev_observation(
        metrics_path=metrics_path,
        dataset_snapshot=snapshot.path,
        variant_manifest_path=variant_path,
        protocol_path=protocol_path,
        output_path=output,
        domain=domain,
        role=role,
        engine_commit="a" * 40,
        command_argv=("python3", "reviewed-domain-adapter.py"),
        generated_at=AS_OF,
        ruler_root=RULER_ROOT,
    )
    return snapshot, payload, output, variant_path


@pytest.mark.parametrize("domain", [Domain.AU, Domain.HKJC])
def test_producer_emits_all_and_only_frozen_dev_rows_for_each_racing_domain(tmp_path, domain):
    snapshot, payload, output, variant_path = produce(tmp_path, domain=domain)
    rows = [json.loads(line) for line in (snapshot.path / "rows.jsonl").read_text().splitlines()]
    expected = {row["row_id"] for row in rows if row["split"] == "dev"}
    assert {row["row_id"] for row in payload["observations"]} == expected
    assert payload["source_split"] == "dev"
    assert payload["terminal_metrics_emitted"] is False
    assert payload["variant_manifest_sha256"] == hashlib.sha256(variant_path.read_bytes()).hexdigest()
    assert json.loads(output.read_text()) == payload


def test_baseline_and_comparator_keep_separate_pre_registered_variant_identity(tmp_path):
    snapshot, baseline, baseline_path, _manifest = produce(tmp_path, role="baseline")
    baseline_metrics = json.loads((tmp_path / "baseline-metrics.json").read_text())
    comparator_metrics = tmp_path / "neutral_comparator-metrics.json"
    comparator_metrics.write_text(json.dumps(baseline_metrics, sort_keys=True) + "\n")
    comparator_variant = {
        "schema_version": "wong-choi-power-variant-manifest/v1",
        "domain": "au",
        "role": "neutral_comparator",
        "variant_id": "neutral-jitter-v1",
        "engine_commit": "a" * 40,
        "purpose": "neutral_variance_probe",
        "registered_at": "2026-09-02T02:00:00+00:00",
        "selected_by_outcome": False,
        "terminal_accessed": False,
        "model_change": False,
        "configuration": {"mode": "neutral-jitter-v1"},
    }
    comparator_manifest = tmp_path / "neutral_comparator-variant.json"
    comparator_manifest.write_text(json.dumps(comparator_variant, sort_keys=True) + "\n")
    comparator_path = tmp_path / "neutral_comparator-dev-observations.json"
    comparator = produce_power_dev_observation(
        metrics_path=comparator_metrics,
        dataset_snapshot=snapshot.path,
        variant_manifest_path=comparator_manifest,
        protocol_path=tmp_path / "power-neutral-protocol.json",
        output_path=comparator_path,
        domain=Domain.AU,
        role="neutral_comparator",
        engine_commit="a" * 40,
        command_argv=("python3", "reviewed-domain-adapter.py"),
        generated_at=AS_OF,
        ruler_root=RULER_ROOT,
    )
    assert baseline["variant_id"] == "known-good"
    assert comparator["variant_id"] == "neutral-jitter-v1"
    assert baseline["protocol"] == comparator["protocol"]
    projection = tmp_path / "variance-input.json"
    build_power_variance_projection(
        baseline_path=baseline_path,
        comparator_path=comparator_path,
        output_path=projection,
        domain=Domain.AU,
        as_of=AS_OF,
        ruler_root=RULER_ROOT,
    )
    report = inspect_power_variance(
        input_path=projection,
        domain=Domain.AU,
        as_of=AS_OF,
        ruler_root=RULER_ROOT,
    )
    assert report["units"] == 2
    assert report["power_profile_write_allowed"] is False


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("terminal_row", "dev rows"),
        ("missing_dev", "dev rows"),
        ("wrong_fold", "provenance"),
        ("wrong_metric", "metric"),
        ("selected", "outcome"),
        ("terminal_access", "terminal"),
        ("model_change", "model change"),
        ("wrong_commit", "commit"),
    ],
)
def test_unsafe_or_unbound_engine_metrics_fail_closed(tmp_path, fault, message):
    def mutate(metrics, variant):
        if fault == "terminal_row":
            row = dict(metrics["observations"][0])
            row["row_id"] = "row-4"
            row["split"] = "terminal"
            metrics["observations"].append(row)
        elif fault == "missing_dev":
            metrics["observations"] = metrics["observations"][:1]
        elif fault == "wrong_fold":
            metrics["observations"][0]["fold"] = 99
        elif fault == "wrong_metric":
            del metrics["observations"][0]["metrics"]["gold"]
        elif fault == "selected":
            variant["selected_by_outcome"] = True
        elif fault == "terminal_access":
            variant["terminal_accessed"] = True
        elif fault == "model_change":
            variant["model_change"] = True
        elif fault == "wrong_commit":
            variant["engine_commit"] = "b" * 40

    with pytest.raises((ValueError, RuntimeError), match=message):
        produce(tmp_path, mutate=mutate)


def test_producer_is_create_only(tmp_path):
    _spec, snapshot, _metrics, metrics_path, _variant, variant_path, protocol_path = setup_inputs(
        tmp_path
    )
    output = tmp_path / "existing.json"
    output.write_text("owner data\n")
    with pytest.raises((FileExistsError, ValueError, RuntimeError)):
        produce_power_dev_observation(
            metrics_path=metrics_path,
            dataset_snapshot=snapshot.path,
            variant_manifest_path=variant_path,
            protocol_path=protocol_path,
            output_path=output,
            domain=Domain.AU,
            role="baseline",
            engine_commit="a" * 40,
            command_argv=("python3", "reviewed-domain-adapter.py"),
            generated_at=AS_OF,
            ruler_root=RULER_ROOT,
        )
    assert output.read_text() == "owner data\n"


def test_parent_verifier_rejects_mutated_producer_output(tmp_path):
    snapshot, payload, output, variant_path = produce(tmp_path)
    payload["observations"][0]["metrics"]["ndcg_at5"] += 0.01
    output.write_text(json.dumps(payload, sort_keys=True) + "\n")
    with pytest.raises((ValueError, RuntimeError), match="differs from frozen"):
        verify_power_dev_observation(
            output_path=output,
            metrics_path=tmp_path / "baseline-metrics.json",
            dataset_snapshot=snapshot.path,
            variant_manifest_path=variant_path,
            protocol_path=tmp_path / "power-neutral-protocol.json",
            domain=Domain.AU,
            role="baseline",
            engine_commit="a" * 40,
            command_argv=("python3", "reviewed-domain-adapter.py"),
            generated_at=AS_OF,
            ruler_root=RULER_ROOT,
        )
