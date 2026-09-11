import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.research_index import _hash
from shared_wong_choi.research_power_variance import (
    inspect_power_variance,
    verify_power_variance_report,
)


RULER_ROOT = Path(__file__).resolve().parents[1] / "resources" / "evaluation_rulers"
AS_OF = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)
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


def _metric_row(offset=0.0):
    return {
        "gold": 1.0 if offset > 0 else 0.0,
        "good_positional": 0.0,
        "top3_capture_at5": 0.6 + offset,
        "mean_top3_model_rank": 3.0 - offset,
        "competitive_recall_at5": 0.5 + offset,
        "ndcg_at5": 0.7 + offset,
        "top5_pairwise_auc": 0.65 + offset,
    }


def _payload(domain="au", *, rows=3):
    data = {
        "schema_version": "wong-choi-power-variance-input/v1",
        "evidence_id": f"wc:{domain}:power-variance-input:neutral-v1",
        "domain": domain,
        "ruler_id": f"{domain}-v2",
        "ruler_sha256": _ruler_digest(domain),
        "generated_at": "2026-09-01T12:00:00+00:00",
        "source_role": "development_only",
        "engine_evidence": {
            "baseline_artifact_sha256": "3" * 64,
            "comparator_artifact_sha256": "4" * 64,
            "baseline_variant_id": "known-good",
            "comparator_variant_id": "neutral-jitter-v1",
            "baseline_variant_manifest_sha256": "5" * 64,
            "comparator_variant_manifest_sha256": "6" * 64,
            "baseline_command_sha256": "7" * 64,
            "comparator_command_sha256": "8" * 64,
        },
        "protocol": {
            "protocol_id": "neutral-rotation-v1",
            "comparison_kind": "neutral_perturbation",
            "preregistered_at": "2026-09-01T11:00:00+00:00",
            "terminal_accessed": False,
            "selected_by_outcome": False,
        },
        "corpus": {
            "manifest_sha256": "a" * 64,
            "code_commit": "b" * 40,
            "unit": "race",
            "split": "dev",
        },
        "rows": [],
    }
    for index in range(rows):
        data["rows"].append(
            {
                "unit_id": f"{domain}:race:{index + 1}",
                "observed_at": f"2026-08-{20 + index:02d}T05:00:00+00:00",
                "fold": index % 2,
                "cohorts": {
                    "field_size": "9-10",
                    "venue": "test-venue",
                    "going": "good",
                },
                "baseline": _metric_row(0.0),
                "comparator": _metric_row((index - 1) * 0.01),
            }
        )
    return data


def _write(tmp_path, payload):
    path = tmp_path / "variance-input.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_au_dev_only_variance_is_descriptive_and_direction_normalized(tmp_path):
    path = _write(tmp_path, _payload())
    report = inspect_power_variance(
        input_path=path, domain=Domain.AU, as_of=AS_OF, ruler_root=RULER_ROOT
    )
    metrics = {item["name"]: item for item in report["metrics"]}
    assert report["units"] == 3
    assert set(metrics) == set(METRICS)
    assert math.isclose(metrics["ndcg_at5"]["delta_sd"], 0.01)
    assert math.isclose(metrics["mean_top3_model_rank"]["delta_sd"], 0.01)
    assert metrics["mean_top3_model_rank"]["direction"] == "minimize"
    assert report["variance_input_contract_verified"] is True
    assert report["engine_evidence"]["baseline_command_sha256"] == "7" * 64
    assert report["power_profile_write_allowed"] is False
    assert report["verified_monitoring_samples"] is None
    assert report["model_promotion_allowed"] is False


def test_hkjc_uses_its_own_ruler_binding(tmp_path):
    path = _write(tmp_path, _payload("hkjc"))
    report = inspect_power_variance(
        input_path=path, domain=Domain.HKJC, as_of=AS_OF, ruler_root=RULER_ROOT
    )
    assert report["domain"] == "hkjc"
    assert report["ruler_id"] == "hkjc-v2"
    assert report["ruler_sha256"] == _ruler_digest("hkjc")


@pytest.mark.parametrize("domain", [Domain.TENNIS, Domain.NBA])
def test_non_racing_domains_cannot_use_racing_variance_contract(tmp_path, domain):
    path = _write(tmp_path, _payload())
    with pytest.raises((ValueError, RuntimeError), match="AU or HKJC"):
        inspect_power_variance(
            input_path=path, domain=domain, as_of=AS_OF, ruler_root=RULER_ROOT
        )


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ("terminal", "development-only"),
        ("selected", "pre-registered"),
        ("ruler", "ruler"),
        ("metrics", "metric"),
        ("cohorts", "cohort"),
        ("duplicate", "duplicate"),
        ("too_few", "two"),
        ("future", "future"),
        ("engine_digest", "engine evidence digest"),
        ("same_variant", "distinct engine variant"),
    ],
)
def test_unsafe_or_noncanonical_variance_inputs_fail_closed(tmp_path, fault, message):
    payload = _payload()
    if fault == "terminal":
        payload["protocol"]["terminal_accessed"] = True
    elif fault == "selected":
        payload["protocol"]["selected_by_outcome"] = True
    elif fault == "ruler":
        payload["ruler_sha256"] = "f" * 64
    elif fault == "metrics":
        del payload["rows"][0]["baseline"]["gold"]
    elif fault == "cohorts":
        del payload["rows"][0]["cohorts"]["going"]
    elif fault == "duplicate":
        payload["rows"][1]["unit_id"] = payload["rows"][0]["unit_id"]
    elif fault == "too_few":
        payload["rows"] = payload["rows"][:1]
    elif fault == "future":
        payload["rows"][0]["observed_at"] = "2026-09-02T00:00:00+00:00"
    elif fault == "engine_digest":
        payload["engine_evidence"]["baseline_command_sha256"] = "not-a-digest"
    elif fault == "same_variant":
        payload["engine_evidence"]["comparator_variant_id"] = "known-good"
    path = _write(tmp_path, payload)
    with pytest.raises((ValueError, RuntimeError), match=message):
        inspect_power_variance(
            input_path=path, domain=Domain.AU, as_of=AS_OF, ruler_root=RULER_ROOT
        )


def test_report_verifier_recomputes_source_and_rejects_mutation(tmp_path):
    path = _write(tmp_path, _payload())
    report = inspect_power_variance(
        input_path=path, domain=Domain.AU, as_of=AS_OF, ruler_root=RULER_ROOT
    )
    payload = _payload()
    payload["rows"][0]["comparator"]["ndcg_at5"] += 0.01
    _write(tmp_path, payload)
    with pytest.raises((ValueError, RuntimeError)):
        verify_power_variance_report(
            report,
            input_path=path,
            domain=Domain.AU,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
        )


def test_report_verifier_rejects_forged_profile_or_sample_authority(tmp_path):
    path = _write(tmp_path, _payload())
    report = inspect_power_variance(
        input_path=path, domain=Domain.AU, as_of=AS_OF, ruler_root=RULER_ROOT
    )
    report["power_profile_write_allowed"] = True
    report["content_hash"] = _hash(
        {key: value for key, value in report.items() if key != "content_hash"}
    )
    with pytest.raises((ValueError, RuntimeError)):
        verify_power_variance_report(
            report,
            input_path=path,
            domain=Domain.AU,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
        )


def test_checkpoint_can_preempt_during_variance_parsing(tmp_path):
    path = _write(tmp_path, _payload())
    calls = 0

    def checkpoint():
        nonlocal calls
        calls += 1
        if calls == 5:
            raise RuntimeError("production_preempted")

    with pytest.raises(RuntimeError, match="production_preempted"):
        inspect_power_variance(
            input_path=path,
            domain=Domain.AU,
            as_of=AS_OF,
            ruler_root=RULER_ROOT,
            checkpoint=checkpoint,
        )
    assert calls == 5
