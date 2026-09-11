from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from shared_wong_choi.contracts import Domain
from shared_wong_choi.evaluation_rulers import load_evaluation_ruler
from shared_wong_choi.research_dataset import load_dataset_snapshot
from shared_wong_choi.research_evaluation import OBSERVATION_SCHEMA_VERSION
from shared_wong_choi.research_postflight import SafetyEvidence, verify_research_safety
from shared_wong_choi.research_runner import (
    CommandExecution,
    CommandState,
    ResearchJob,
    ResearchRunner,
    ResearchRuntime,
    SubprocessResearchExecutor,
    create_research_adapter,
)
from shared_wong_choi.research_safety import ResearchSafetyError, audit_research_inputs, prepare_scoring_inputs
from test_research_safety import encoded, fixture_inputs


def canonical_hash(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def evidence_fixture(tmp_path, fault=None, *, domain=Domain.AU, use_harness=False, use_subprocess=False, commits=None):
    ruler = load_evaluation_ruler(domain)
    names = [metric["name"] for metric in ruler.metrics]
    eligible = [metric["name"] for metric in ruler.metrics if metric["role"] in {"primary", "ranking"}]
    postflight = {
        "schema_version": "wong-choi-research-postflight-protocol/v1",
        "spec_id": f"wc:{domain.value}:experiment-spec:safety-inputs",
        "domain": domain.value,
        "label_field": "winner",
        "harness_digest": hashlib.sha256(
            (Path(__file__).resolve().parents[1] / "research_harness.py").read_bytes()
        ).hexdigest(),
        "components": ["a", "b"],
        "variants": {"empty": [], "a": ["a"], "b": ["b"], "full": ["a", "b"]},
        "negative_control": {"kind": "development_label_rotation", "max_gain": {name: 0.001 for name in eligible}},
        "power": {
            "method": "paired_t_design",
            "target": 0.8,
            "min_dev_units": 2,
            "unit": ruler.bootstrap["unit"],
            "minimum_effects": {name: 0.1 for name in eligible},
            "sd_floor": {name: 0.001 for name in eligible},
        },
    }
    if fault == "missing_ablation":
        del postflight["variants"]["a"]
    if fault == "weak_power":
        postflight["power"]["minimum_effects"] = {name: 0.000001 for name in eligible}
        postflight["negative_control"]["max_gain"] = {name: 0 for name in eligible}
    if fault == "missing_power":
        del postflight["power"]
    if fault == "wrong_harness":
        postflight["harness_digest"] = "f" * 64
    postflight_path = tmp_path / "postflight.json"
    postflight_path.write_bytes(encoded(postflight))

    def amend(protocol, rows, records):
        protocol["postflight_protocol_digest"] = hashlib.sha256(postflight_path.read_bytes()).hexdigest()
        for index, row in enumerate(rows):
            row["payload"]["winner"] = 0 if fault == "ineffective_rotation" else index % 2
        if fault == "future_feature":
            records[8]["available_at"] = rows[2]["event_at"]

    spec, inputs = fixture_inputs(tmp_path, amend, domain=domain, commits=commits)
    snapshot = load_dataset_snapshot(inputs["dataset_snapshot"])
    rows = [json.loads(line) for line in (snapshot.path / "rows.jsonl").read_text().splitlines()]
    input_audit = audit_research_inputs(spec, **inputs)
    input_protocol = json.loads(inputs["protocol_path"].read_bytes())
    sources = {
        name: {record["record_id"]: record for record in json.loads(path.read_bytes())["records"]}
        for name, path in inputs["source_paths"].items()
    }
    projected = prepare_scoring_inputs(rows, input_protocol, sources, "winner")
    safety_evidence = SafetyEvidence(inputs["protocol_path"], postflight_path, inputs["source_paths"])
    metric = eligible[0]
    controls = {rows[2]["row_id"]: rows[3]["row_id"], rows[3]["row_id"]: rows[2]["row_id"]}

    def metrics(gain):
        return {name: gain if name == metric else 0.0 for name in names}

    class Executor:
        def run(self, invocation, **kwargs):
            if use_harness:
                from shared_wong_choi.research_harness import run_research_harness

                def scorer(case, components):
                    assert "winner" not in case and "split" not in case
                    assert all(entity["prices"] == {} for entity in case["entities"])
                    if fault == "mutating_scorer":
                        case["entities"][0]["features"]["rating"] = -999
                    label_signal = (case["entities"][0]["features"]["rating"] - 71) % 2
                    return 0.5 + (2 * label_signal - 1) * 0.05 * len(components)

                def measure(prediction, label, context):
                    return metrics(1 - (prediction - label) ** 2)

                run_research_harness(
                    spec,
                    dataset_snapshot=snapshot.path,
                    registry=inputs["registry"],
                    evidence=safety_evidence,
                    role=invocation.role,
                    scorer=scorer,
                    measure=measure,
                    output_dir=invocation.output_dir,
                    command_index=invocation.index,
                )
                return CommandExecution(CommandState.SUCCEEDED, 0, "harness executed", "", 0.01, 0.01, 0, 1024)
            main_gain = 0.2 if invocation.role == "candidate" else 0.0
            observations = [
                {
                    "row_id": row["row_id"],
                    "event_at": row["event_at"],
                    "split": row["split"],
                    "fold": row["payload"]["fold"],
                    "cohorts": row["payload"]["cohorts"],
                    "metrics": metrics(main_gain),
                }
                for row in rows
            ]
            invocation.metrics_path.write_text(
                json.dumps(
                    {
                        "schema_version": OBSERVATION_SCHEMA_VERSION,
                        "domain": domain.value,
                        "sample_hash": snapshot.manifest.sample_hash,
                        "dataset_manifest_id": snapshot.manifest.record_id,
                        "dataset_artifact_digest": snapshot.manifest.artifact_digest,
                        "observations": observations,
                    }
                )
            )
            traces = [
                {"row_id": row["row_id"], "input_digest": canonical_hash(projected[row["row_id"]])} for row in rows
            ]
            if fault == "wrong_trace" and invocation.role == "candidate":
                traces[2]["input_digest"] = "f" * 64
            sidecar = {
                "schema_version": "wong-choi-research-safety-execution/v1",
                "spec_id": spec.record_id,
                "role": invocation.role,
                "commit": spec.baseline_commit if invocation.role == "baseline" else spec.candidate_commit,
                "command_index": invocation.index,
                "input_audit_hash": input_audit.to_payload()["content_hash"],
                "postflight_digest": hashlib.sha256(postflight_path.read_bytes()).hexdigest(),
                "trace": traces,
                "control": {
                    "label_sources": controls,
                    "observations": [
                        {
                            "row_id": row["row_id"],
                            "metrics": metrics(
                                0.2 if fault == "control_gain" and invocation.role == "candidate" else 0.0
                            ),
                        }
                        for row in rows
                        if row["split"] == "dev"
                    ],
                },
                "ablations": {
                    variant: [
                        {"row_id": row["row_id"], "metrics": metrics(0.1 * len(components))}
                        for row in rows
                        if row["split"] == "dev"
                    ]
                    for variant, components in postflight["variants"].items()
                }
                if invocation.role == "candidate"
                else {},
            }
            if fault == "terminal_control":
                sidecar["control"]["observations"].append({"row_id": rows[-1]["row_id"], "metrics": metrics(0)})
            if fault == "wrong_postflight":
                sidecar["postflight_digest"] = "f" * 64
            if fault == "wrong_permutation":
                sidecar["control"]["label_sources"] = {row_id: row_id for row_id in controls}
            if fault == "missing_trace":
                sidecar["trace"] = sidecar["trace"][:-1]
            if fault == "extra_ablation" and invocation.role == "candidate":
                sidecar["ablations"]["new-after-results"] = sidecar["ablations"]["full"]
            if fault == "unhelpful_component" and invocation.role == "candidate":
                for row in sidecar["ablations"]["a"]:
                    row["metrics"] = metrics(0.2)
            if fault != "missing_sidecar":
                (invocation.output_dir / "safety.json").write_bytes(encoded(sidecar))
            return CommandExecution(CommandState.SUCCEEDED, 0, "fixture executed", "", 0.01, 0.01, 0, 1024)

    for name in ("baseline", "candidate", "warm"):
        (tmp_path / name).mkdir(exist_ok=True)
    if use_subprocess and commits is None:
        # A real interpreter executes the reviewed harness, not the fake
        # executor above. Toy callbacks still make no model-performance claim.
        script = f'''
import os, sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})
from shared_wong_choi.research_registry import ExperimentRegistry, _record_from_payload
from shared_wong_choi.research_postflight import SafetyEvidence
from shared_wong_choi.research_harness import run_research_harness
registry = ExperimentRegistry(Path({str(inputs["registry"].root)!r}))
spec = _record_from_payload(registry.load(os.environ["WC_RESEARCH_SPEC_ID"]))
evidence = SafetyEvidence(Path({str(inputs["protocol_path"])!r}), Path({str(postflight_path)!r}),
    {{name: Path(path) for name, path in { {name: str(path) for name, path in inputs["source_paths"].items()}!r}.items()}})
def scorer(case, components):
    signal = (case["entities"][0]["features"]["rating"] - 71) % 2
    return 0.5 + (2 * signal - 1) * 0.05 * len(components)
def measure(prediction, label, context):
    return {{name: 1 - (prediction-label)**2 if name == {metric!r} else 0.0 for name in spec.preregistered_metrics}}
run_research_harness(spec, dataset_snapshot=Path(os.environ["WC_RESEARCH_DATASET"]).parent,
    registry=registry, evidence=evidence, role=os.environ["WC_RESEARCH_ROLE"],
    scorer=scorer, measure=measure, output_dir=Path(os.environ["WC_RESEARCH_OUTPUT_DIR"]))
'''
        for name in ("baseline", "candidate"):
            (tmp_path / name / "frozen_harness.py").write_text(script)
    runtime = ResearchRuntime(
        state_root=tmp_path / "state",
        warm_root=tmp_path / "warm",
        executor=SubprocessResearchExecutor(poll_seconds=0.05, terminate_grace=0.1) if use_subprocess else Executor(),
        checkout_probe=lambda path: spec.baseline_commit if path.name == "baseline" else spec.candidate_commit,
        free_space_probe=lambda path: 10**9,
        clock=lambda: datetime(2026, 8, 31, tzinfo=timezone.utc),
    )
    job = ResearchJob(
        f"wc:{domain.value}:research-job:postflight",
        domain,
        spec.record_id,
        snapshot.path,
        tmp_path / "baseline",
        tmp_path / "candidate",
        1024,
        30,
    )
    from research_test_support import pin_review
    pin_review(runtime, inputs["registry"], spec)
    run = ResearchRunner(runtime, inputs["registry"]).run(job, spec, create_research_adapter(domain))
    if fault == "mutating_scorer":
        return run
    assert run.status == "succeeded"
    evidence = SafetyEvidence(inputs["protocol_path"], postflight_path, inputs["source_paths"])
    arguments = {
        "dataset_snapshot": snapshot.path,
        "run_artifact": run.artifact_path,
        "run_id": run.experiment_run_id,
        "registry": inputs["registry"],
        "evidence": evidence,
    }
    return spec, arguments


def real_checkout_fixture(tmp_path, domain=Domain.AU):
    import subprocess
    script = f'''
import os, sys
from pathlib import Path
sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})
from shared_wong_choi.research_registry import ExperimentRegistry, _record_from_payload
from shared_wong_choi.research_postflight import SafetyEvidence
from shared_wong_choi.research_harness import run_research_harness
from shared_wong_choi.evaluation_rulers import load_evaluation_ruler
root = Path(__file__).resolve().parents[1]
registry = ExperimentRegistry(root / "registry")
spec = _record_from_payload(registry.load(os.environ["WC_RESEARCH_SPEC_ID"]))
evidence = SafetyEvidence(root / "protocol.json", root / "postflight.json", {{"prerace-feed": root / "prerace.json"}})
metric = next(m["name"] for m in load_evaluation_ruler(spec.domain).metrics if m["role"] in {{"primary", "ranking"}})
def scorer(case, components):
    signal = (case["entities"][0]["features"]["rating"] - 71) % 2
    return 0.5 + (2 * signal - 1) * .05 * len(components)
def measure(prediction, label, context):
    return {{name: 1 - (prediction-label)**2 if name == metric else 0.0 for name in spec.preregistered_metrics}}
run_research_harness(spec, dataset_snapshot=Path(os.environ["WC_RESEARCH_DATASET"]).parent,
    registry=registry, evidence=evidence, role=os.environ["WC_RESEARCH_ROLE"], scorer=scorer,
    measure=measure, output_dir=Path(os.environ["WC_RESEARCH_OUTPUT_DIR"]))
'''
    commits = []
    for name in ("baseline", "candidate"):
        folder = tmp_path / name
        folder.mkdir()
        (folder / "frozen_harness.py").write_text(script)
        for command in (["init", "-q"], ["add", "frozen_harness.py"], ["-c", "user.name=Research Test", "-c", "user.email=research@example.invalid", "commit", "-qm", name]):
            subprocess.run(["git", "-C", str(folder), *command], check=True, capture_output=True)
        commits.append(subprocess.check_output(["git", "-C", str(folder), "rev-parse", "HEAD"], text=True).strip())
    return evidence_fixture(tmp_path, domain=domain, use_subprocess=True, commits=tuple(commits))


def test_verified_postflight_recomputes_controls_ablation_and_power(tmp_path):
    spec, arguments = evidence_fixture(tmp_path)
    report = verify_research_safety(spec, **arguments)
    assert report.passed
    assert report.to_payload() == verify_research_safety(spec, **arguments).to_payload()
    assert report.power and report.ablation
    assert report.run_id == arguments["run_id"]


@pytest.mark.parametrize(
    "fault",
    ["future_feature", "wrong_trace", "control_gain", "weak_power", "unhelpful_component", "ineffective_rotation"],
)
def test_measured_safety_failure_is_blocked(tmp_path, fault):
    spec, arguments = evidence_fixture(tmp_path, fault)
    report = verify_research_safety(spec, **arguments)
    assert report.passed is False
    assert report.findings


@pytest.mark.parametrize(
    "fault",
    [
        "missing_power",
        "missing_ablation",
        "terminal_control",
        "missing_sidecar",
        "wrong_postflight",
        "wrong_permutation",
        "missing_trace",
        "extra_ablation",
        "wrong_harness",
    ],
)
def test_missing_or_holdout_tuned_evidence_is_not_safety(tmp_path, fault):
    spec, arguments = evidence_fixture(tmp_path, fault)
    with pytest.raises(ResearchSafetyError):
        verify_research_safety(spec, **arguments)


def test_safety_refuses_artifact_tampering(tmp_path):
    spec, arguments = evidence_fixture(tmp_path)
    sidecar = arguments["run_artifact"] / "candidate" / "command-00" / "safety.json"
    sidecar.write_bytes(sidecar.read_bytes() + b" ")
    with pytest.raises((ResearchSafetyError, RuntimeError), match="digest"):
        verify_research_safety(spec, **arguments)


def test_evaluation_and_publisher_require_current_evidence_not_boolean(tmp_path):
    from dataclasses import replace
    from shared_wong_choi.research_evaluation import (
        EvaluationError,
        EvaluationVerification,
        evaluate_run_artifact,
        publish_evaluation_decision,
    )

    spec, arguments = evidence_fixture(tmp_path)
    report = evaluate_run_artifact(spec, **arguments)
    assert report.safety_passed and report.promotion_proposal_allowed
    assert report.safety_report["run_id"] == arguments["run_id"]
    publication = {
        "registry": arguments["registry"],
        "run_id": arguments["run_id"],
        "report_root": tmp_path / "reports",
        "decided_at": "2026-08-31T01:00:00+00:00",
    }
    with pytest.raises(EvaluationError, match="verification"):
        publish_evaluation_decision(report, **publication)
    proof = EvaluationVerification(
        spec, arguments["dataset_snapshot"], arguments["run_artifact"], arguments["evidence"]
    )
    first = publish_evaluation_decision(report, verification=proof, **publication)
    second = publish_evaluation_decision(
        report, verification=proof, **{**publication, "decided_at": "2026-08-31T02:00:00+00:00"}
    )
    assert first.status == "created" and second.status == "duplicate"
    with pytest.raises(EvaluationError, match="recomputed"):
        publish_evaluation_decision(
            replace(report, reason="invented better verdict"), verification=proof, **publication
        )
    sidecar = arguments["run_artifact"] / "candidate" / "command-00" / "safety.json"
    sidecar.write_bytes(sidecar.read_bytes() + b" ")
    with pytest.raises(EvaluationError, match="digest"):
        publish_evaluation_decision(report, verification=proof, **publication)


def test_old_boolean_is_not_an_evaluation_authorization(tmp_path):
    from shared_wong_choi.research_evaluation import evaluate_run_artifact

    spec, arguments = evidence_fixture(tmp_path)
    no_evidence = {key: value for key, value in arguments.items() if key != "evidence"}
    report = evaluate_run_artifact(spec, **no_evidence)
    assert not report.safety_passed and not report.promotion_proposal_allowed
    with pytest.raises(TypeError):
        evaluate_run_artifact(spec, **no_evidence, safety_passed=True)


def test_power_math_agrees_with_standard_paired_t_reference():
    from scipy.stats import nct, t
    from shared_wong_choi.research_postflight import paired_design_power

    # Positive side of a two-sided 95% CI, not retrospective observed power.
    expected = float(nct.sf(t.ppf(0.975, 99), 99, 0.3 * 10))
    assert paired_design_power(effect=0.3, sd=1.0, n=100, confidence=0.95) == pytest.approx(expected)


@pytest.mark.parametrize("domain", list(Domain))
def test_real_harness_executes_scorer_controls_and_ablations(tmp_path, domain):
    spec, arguments = evidence_fixture(tmp_path, use_harness=True, domain=domain)
    report = verify_research_safety(spec, **arguments)
    assert report.passed
    assert all(row["gain"] <= 0 for row in report.controls)
    assert any(row["dev_marginal_gain"] > 0 for row in report.ablation)


def test_harness_input_mutation_is_a_failed_registered_run(tmp_path):
    result = evidence_fixture(tmp_path, "mutating_scorer", use_harness=True)
    assert result.status == "executor_exception"
    assert result.experiment_run_id is not None


def test_ineffective_control_in_one_family_cannot_hide_behind_another():
    from shared_wong_choi.research_postflight import ineffective_label_controls

    rows = [
        {"row_id": f"{family}-{index}", "split": "dev", "payload": {"cohorts": {"family": family}, "winner": label}}
        for family, labels in (("a", (0, 0)), ("b", (0, 1)))
        for index, label in enumerate(labels)
    ]
    assert ineffective_label_controls(rows, seed=7, label_field="winner") == (
        "a:negative_control_does_not_change_labels",
    )
