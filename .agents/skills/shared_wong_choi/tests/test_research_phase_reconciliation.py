from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared_wong_choi.artifact_archive import artifact_digest
from shared_wong_choi.research_dataset import DatasetSource, SplitPolicy, StorageTier
from shared_wong_choi.research_runner import ResearchDisposition, SubprocessResearchExecutor, create_research_adapter
from shared_wong_choi.research_supervision import (
    ResearchPreparationRunner,
    ResearchScoringRunner,
    PhaseReconciliationRunner,
)
from test_research_supervision import fixture


def crashed_phase(tmp_path, phase, point, *, failed=False):
    spec, job, runtime, registry = fixture(tmp_path, "raise SystemExit(9)\n" if failed else None)

    class Crash(SubprocessResearchExecutor):
        def run(self, invocation, **kwargs):
            code = "import os,sys\nfrom pathlib import Path\nimport shared_wong_choi.research_supervision as s\n"
            if point == "partial_artifact":
                code += (
                    "rename=Path.rename\n"
                    "def crash_rename(self,target):\n"
                    "    if '.partial-' in self.name: os._exit(84)\n"
                    "    return rename(self,target)\n"
                    "Path.rename=crash_rename\n"
                )
            elif point == "before_artifact":
                code += (
                    "s.build_dataset_snapshot=lambda *a,**k: os._exit(81)\n"
                    if phase == "prepare"
                    else "s.ResearchRunner.run=lambda *a,**k: os._exit(81)\n"
                )
            else:
                kind = "dataset_manifest" if phase == "prepare" else "experiment_run"
                code += (
                    "append=s.ExperimentRegistry.append\n"
                    "def crash(self,record):\n"
                    f"    if record.kind.value == {kind!r}:\n"
                    + ("        append(self,record)\n" if point == "after_registry" else "")
                    + f"        os._exit({83 if point == 'after_registry' else 82})\n"
                    "    return append(self,record)\n"
                    "s.ExperimentRegistry.append=crash\n"
                )
            code += "s._worker(Path(sys.argv[1]))"
            return super().run(replace(invocation, argv=(sys.executable, "-c", code, invocation.argv[-1])), **kwargs)

    crashed_runtime = replace(runtime, executor=Crash(poll_seconds=0.02, terminate_grace=0.1))
    if phase == "prepare":
        source = tmp_path / "dataset-source/artifact"
        result = ResearchPreparationRunner(crashed_runtime, registry).run(
            spec,
            sources=(
                DatasetSource(
                    "au-fixture",
                    StorageTier.HOT,
                    source,
                    source / "rows.jsonl",
                    "2026-08-28T00:00:00+00:00",
                    artifact_digest(source),
                ),
            ),
            split_policy=SplitPolicy(
                "2026-08-10T23:59:00+00:00", "2026-08-20T23:59:00+00:00", "2026-08-29T23:59:00+00:00"
            ),
            estimated_bytes=1024,
            timeout_seconds=30,
        )
    else:
        result = ResearchScoringRunner(crashed_runtime, registry).run(job, spec, create_research_adapter("au"))
    assert result.disposition is ResearchDisposition.FAILED
    attempt = next((runtime.warm_root / "research-phases/au").glob(phase + "-*"))
    outcome = json.loads((attempt / "phase-outcome.json").read_text())
    assert (
        outcome["execution"]["returncode"]
        == {"before_artifact": 81, "after_artifact": 82, "after_registry": 83, "partial_artifact": 84}[point]
    )
    assert not (attempt / "completed.json").exists()
    return spec, runtime, registry, attempt


def inspect(spec, runtime, registry, attempt):
    return PhaseReconciliationRunner(runtime, registry).run(
        spec,
        attempt_path=attempt,
        request_sha256=hashlib.sha256((attempt / "request.json").read_bytes()).hexdigest(),
        estimated_bytes=1024,
        timeout_seconds=30,
    )


@pytest.mark.parametrize("phase", ["prepare", "scoring"])
@pytest.mark.parametrize("point", ["before_artifact", "partial_artifact", "after_artifact", "after_registry"])
def test_phase_crash_boundaries_do_not_trigger_rerun_or_registry_repair(tmp_path, phase, point):
    spec, runtime, registry, attempt = crashed_phase(tmp_path, phase, point)
    original, records = artifact_digest(attempt), artifact_digest(registry.root)
    result = inspect(spec, runtime, registry, attempt)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    expected = "no_final_artifact_observed" if point == "before_artifact" else "artifact_without_matching_registration"
    if point == "after_registry":
        expected = "verified_registered_dataset" if phase == "prepare" else "verified_registered_run"
    elif point == "partial_artifact":
        expected = "incomplete_artifact_observed"
    assert result.status == expected
    report = json.loads(result.report_path.read_text())
    assert report["phase"] == phase and report["publication_status"] == expected
    assert all(
        report[key] is False
        for key in ("rerun_scoring_allowed", "retry_publication_allowed", "model_promotion_allowed")
    )
    assert bool(result.record_id) is (point == "after_registry")
    assert result.decision_id is None
    assert artifact_digest(attempt) == original and artifact_digest(registry.root) == records
    assert inspect(spec, runtime, registry, attempt).content_hash == result.content_hash


@pytest.mark.parametrize("phase", ["prepare", "scoring"])
@pytest.mark.parametrize("fault", ["corrupt_artifact", "corrupt_record", "symlink"])
def test_phase_reconciliation_blocks_corrupt_or_redirected_evidence(tmp_path, phase, fault):
    spec, runtime, registry, attempt = crashed_phase(tmp_path, phase, "after_registry")
    filename = "rows.jsonl" if phase == "prepare" else "metrics.json"
    artifact_file = next((attempt / "work").rglob(filename))
    if fault == "corrupt_artifact":
        artifact_file.write_text("corrupt\n")
    elif fault == "symlink":
        moved = tmp_path / "displaced"
        artifact_file.rename(moved)
        artifact_file.symlink_to(moved)
    else:
        kind = "dataset_manifest" if phase == "prepare" else "experiment_run"
        record = next((registry.root / "records" / kind).glob("*.json"))
        record.write_text('{"corrupt":true}')
    result = inspect(spec, runtime, registry, attempt)
    assert result.disposition is ResearchDisposition.FAILED
    assert result.record_id is None and result.report_path is None


def test_registered_scoring_failure_is_retained_not_a_successful_run(tmp_path):
    spec, runtime, registry, attempt = crashed_phase(tmp_path, "scoring", "after_registry", failed=True)
    before = artifact_digest(registry.root)
    result = inspect(spec, runtime, registry, attempt)
    assert result.disposition is ResearchDisposition.SUCCEEDED
    assert result.status == "verified_registered_failure"
    assert registry.load(result.record_id)["state"] == "failed"
    assert artifact_digest(registry.root) == before


@pytest.mark.parametrize("phase", ["prepare", "scoring"])
def test_receipt_cannot_upgrade_dataset_or_failed_run_to_successful_scoring(tmp_path, phase):
    from shared_wong_choi.research_phase_reconciliation import verify_phase_reconciliation_receipt
    from shared_wong_choi.research_reconciliation import _encode

    spec, runtime, registry, attempt = crashed_phase(tmp_path, phase, "after_registry", failed=phase == "scoring")
    result = inspect(spec, runtime, registry, attempt)
    payload = json.loads(result.report_path.read_text())
    payload["publication_status"] = "verified_registered_run"
    payload.pop("content_hash")
    payload["content_hash"] = hashlib.sha256(_encode(payload)).hexdigest()
    copied = tmp_path / "forged-inspection.json"
    copied.write_text(json.dumps(payload))
    receipt = {
        "status": payload["publication_status"],
        "record_id": result.record_id,
        "content_hash": payload["content_hash"],
    }
    with pytest.raises(ValueError):
        verify_phase_reconciliation_receipt(
            spec, registry=registry, report_path=copied, receipt=receipt, request_sha256=payload["request_sha256"]
        )
