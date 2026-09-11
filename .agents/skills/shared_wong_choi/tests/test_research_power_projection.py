import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_power_projection import (
    build_power_variance_projection,
    verify_power_variance_projection,
)
from shared_wong_choi.research_power_variance import inspect_power_variance


RULER_ROOT = Path(__file__).resolve().parents[1] / "resources" / "evaluation_rulers"
AS_OF = datetime(2026, 9, 2, 1, 0, tzinfo=timezone.utc)
METRICS = (
    "gold",
    "good_positional",
    "top3_capture_at5",
    "mean_top3_model_rank",
    "competitive_recall_at5",
    "ndcg_at5",
    "top5_pairwise_auc",
)


def _ruler_digest(domain="au"):
    return hashlib.sha256((RULER_ROOT / f"{domain}-v2.json").read_bytes()).hexdigest()


def _metrics(offset=0.0):
    return {
        "gold": 0.0,
        "good_positional": 1.0,
        "top3_capture_at5": 0.6 + offset,
        "mean_top3_model_rank": 3.0 - offset,
        "competitive_recall_at5": 0.5 + offset,
        "ndcg_at5": 0.7 + offset,
        "top5_pairwise_auc": 0.65 + offset,
    }


def artifact(domain="au", *, role="baseline", fault=None):
    payload = {
        "schema_version": "wong-choi-power-dev-observations/v1",
        "domain": domain,
        "role": role,
        "engine_commit": "a" * 40,
        "variant_id": "known-good" if role == "baseline" else "neutral-jitter-v1",
        "variant_manifest_sha256": ("b" if role == "baseline" else "c") * 64,
        "command_sha256": ("d" if role == "baseline" else "e") * 64,
        "ruler_id": f"{domain}-v2",
        "ruler_sha256": _ruler_digest(domain),
        "dataset_manifest_id": f"wc:{domain}:dataset-manifest:test-dev",
        "dataset_manifest_sha256": "f" * 64,
        "dataset_artifact_digest": "1" * 64,
        "sample_hash": "2" * 64,
        "generated_at": "2026-09-02T00:00:00+00:00",
        "source_split": "dev",
        "terminal_metrics_emitted": False,
        "protocol": {
            "protocol_id": "neutral-jitter-v1",
            "comparison_kind": "neutral_perturbation",
            "preregistered_at": "2026-09-01T23:00:00+00:00",
            "selected_by_outcome": False,
        },
        "observations": [],
    }
    for index in range(3):
        payload["observations"].append(
            {
                "row_id": f"{domain}:race:{index + 1}",
                "event_at": f"2026-08-{20 + index:02d}T05:00:00+00:00",
                "fold": index + 1,
                "cohorts": {
                    "field_size": "9-10",
                    "venue": "test-venue",
                    "going": "good",
                },
                "metrics": _metrics(0.0 if role == "baseline" else (index - 1) * 0.01),
            }
        )
    if fault == "terminal":
        payload["terminal_metrics_emitted"] = True
    elif fault == "outcome_selected":
        payload["protocol"]["selected_by_outcome"] = True
    elif fault == "future":
        payload["generated_at"] = "2026-09-03T00:00:00+00:00"
    elif fault == "metrics":
        del payload["observations"][0]["metrics"]["gold"]
    elif fault == "cohorts":
        del payload["observations"][0]["cohorts"]["going"]
    return payload


def write_artifacts(tmp_path, baseline=None, comparator=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    baseline_path = tmp_path / "baseline-dev.json"
    comparator_path = tmp_path / "comparator-dev.json"
    baseline_path.write_text(json.dumps(baseline or artifact(), sort_keys=True) + "\n")
    comparator_path.write_text(
        json.dumps(comparator or artifact(role="neutral_comparator"), sort_keys=True) + "\n"
    )
    return baseline_path, comparator_path


def build(tmp_path, *, domain=Domain.AU, baseline=None, comparator=None, name="variance.json"):
    baseline_path, comparator_path = write_artifacts(tmp_path, baseline, comparator)
    output = tmp_path / name
    payload = build_power_variance_projection(
        baseline_path=baseline_path,
        comparator_path=comparator_path,
        output_path=output,
        domain=domain,
        as_of=AS_OF,
        ruler_root=RULER_ROOT,
    )
    return payload, output


def test_dev_engine_outputs_create_valid_variance_input_without_terminal_metrics(tmp_path):
    payload, output = build(tmp_path)
    report = inspect_power_variance(
        input_path=output, domain=Domain.AU, as_of=AS_OF, ruler_root=RULER_ROOT
    )
    assert json.loads(output.read_text()) == payload
    assert payload["source_role"] == "development_only"
    assert payload["protocol"]["terminal_accessed"] is False
    assert "terminal_metrics_emitted" not in output.read_text()
    assert payload["engine_evidence"]["baseline_command_sha256"] == "d" * 64
    assert payload["engine_evidence"]["comparator_command_sha256"] == "e" * 64
    assert report["units"] == 3
    assert report["power_profile_write_allowed"] is False


def test_projection_is_deterministic_and_hkjc_remains_separate(tmp_path):
    first, _ = build(
        tmp_path / "one",
        domain=Domain.HKJC,
        baseline=artifact("hkjc"),
        comparator=artifact("hkjc", role="neutral_comparator"),
    )
    second, _ = build(
        tmp_path / "two",
        domain=Domain.HKJC,
        baseline=artifact("hkjc"),
        comparator=artifact("hkjc", role="neutral_comparator"),
    )
    assert first == second
    assert first["domain"] == "hkjc"
    assert first["ruler_sha256"] == _ruler_digest("hkjc")


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("terminal", "terminal"),
        ("outcome_selected", "outcome"),
        ("future", "future"),
        ("metrics", "metric"),
        ("cohorts", "cohort"),
    ],
)
def test_unsafe_dev_observation_artifacts_fail_closed(tmp_path, fault, message):
    comparator = artifact(role="neutral_comparator", fault=fault)
    with pytest.raises((ValueError, RuntimeError), match=message):
        build(tmp_path, comparator=comparator)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("sample_hash", "lineage"),
        ("engine_commit", "engine"),
        ("protocol", "protocol"),
        ("rows", "row"),
        ("role", "role"),
    ],
)
def test_mismatched_engine_outputs_cannot_be_paired(tmp_path, mutation, message):
    comparator = artifact(role="neutral_comparator")
    if mutation == "sample_hash":
        comparator["sample_hash"] = "9" * 64
    elif mutation == "engine_commit":
        comparator["engine_commit"] = "9" * 40
    elif mutation == "protocol":
        comparator["protocol"]["protocol_id"] = "selected-after-run"
    elif mutation == "rows":
        comparator["observations"][0]["row_id"] = "au:race:other"
    elif mutation == "role":
        comparator["role"] = "baseline"
    with pytest.raises((ValueError, RuntimeError), match=message):
        build(tmp_path, comparator=comparator)


def test_projection_is_create_only_and_never_overwrites_existing_output(tmp_path):
    baseline, comparator = write_artifacts(tmp_path)
    output = tmp_path / "variance.json"
    output.write_text("owner data\n")
    with pytest.raises((FileExistsError, ValueError, RuntimeError)):
        build_power_variance_projection(
            baseline_path=baseline,
            comparator_path=comparator,
            output_path=output,
            domain=Domain.AU,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
        )
    assert output.read_text() == "owner data\n"


def test_projection_verifier_rejects_rows_not_backed_by_engine_artifacts(tmp_path):
    baseline, comparator = write_artifacts(tmp_path)
    output = tmp_path / "variance.json"
    build_power_variance_projection(
        baseline_path=baseline,
        comparator_path=comparator,
        output_path=output,
        domain=Domain.AU,
        as_of=AS_OF,
        ruler_root=RULER_ROOT,
    )
    payload = json.loads(output.read_text())
    payload["rows"][0]["comparator"]["ndcg_at5"] += 0.01
    output.write_text(json.dumps(payload, sort_keys=True) + "\n")
    with pytest.raises((ValueError, RuntimeError), match="rows differ"):
        verify_power_variance_projection(
            output_path=output,
            baseline_path=baseline,
            comparator_path=comparator,
            domain=Domain.AU,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
        )


@pytest.mark.parametrize("domain", [Domain.TENNIS, Domain.NBA])
def test_non_racing_domain_cannot_use_racing_projection(tmp_path, domain):
    baseline, comparator = write_artifacts(tmp_path)
    with pytest.raises((ValueError, RuntimeError), match="AU or HKJC"):
        build_power_variance_projection(
            baseline_path=baseline,
            comparator_path=comparator,
            output_path=tmp_path / "variance.json",
            domain=domain,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
        )
