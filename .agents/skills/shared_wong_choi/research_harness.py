"""Deterministic, label-separated scoring/control/ablation harness.

Run this inside a Task 4 command so its capacity, timeout, checkout and production
preemption controls apply. Callbacks must be reviewed domain adapters. This is
an API data boundary, NOT an OS sandbox for arbitrary/malicious Python code.
"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Callable, Mapping, Any

from .research_dataset import load_dataset_snapshot
from .research_evaluation import OBSERVATION_SCHEMA_VERSION, _write_report
from .research_postflight import SafetyEvidence, EXECUTION_VERSION, development_label_rotation, load_postflight_protocol
from .research_registry import ExperimentRegistry, ExperimentSpec
from .research_safety import (
    ResearchSafetyError,
    _encoded,
    _json,
    _number,
    _read,
    _sha,
    _source,
    audit_research_inputs,
    prepare_scoring_inputs,
)


def run_research_harness(
    spec: ExperimentSpec,
    *,
    dataset_snapshot: Path,
    registry: ExperimentRegistry,
    evidence: SafetyEvidence,
    role: str,
    scorer: Callable[[dict, tuple[str, ...]], Any],
    measure: Callable[[Any, Any, dict], Mapping[str, float]],
    output_dir: Path,
    command_index: int = 0,
    row_ids: tuple[str, ...] | None = None,
) -> dict:
    """Actually execute callbacks; emit metrics plus trace/control/ablation data.

    The scorer receives projected features and declared prior train labels only.
    Current labels and evaluation prices go exclusively to the measurement
    callback after prediction. Ablation and label controls operate on dev only.
    The full candidate is fixed before execution; no winner search occurs.
    """
    if (
        role not in {"baseline", "candidate"}
        or type(command_index) is not int
        or not 0 <= command_index < len(spec.commands)
    ):
        raise ResearchSafetyError("invalid harness role/command index")
    audit = audit_research_inputs(
        spec,
        dataset_snapshot=dataset_snapshot,
        protocol_path=evidence.input_protocol,
        source_paths=evidence.source_paths,
        registry=registry,
    )
    if not audit.input_checks_passed:
        raise ResearchSafetyError("input audit failed before model execution")
    postflight, postflight_digest = load_postflight_protocol(spec, evidence)
    dataset = load_dataset_snapshot(dataset_snapshot)
    rows = [_json(line) for line in _read(dataset.path / "rows.jsonl", dataset.manifest.artifact_digest).splitlines()]
    by_id = {row["row_id"]: row for row in rows}
    selected = list(by_id) if row_ids is None else list(row_ids)
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= set(by_id):
        raise ResearchSafetyError("invalid command row partition")
    input_protocol = _json(_read(evidence.input_protocol, spec.protocol_artifact_digest))
    sources = {
        name: _source(_read(evidence.source_paths[name], digest), name, spec.domain.value)
        for name, digest in input_protocol["sources"].items()
    }
    label_field = postflight["label_field"]
    if any(label_field not in row["payload"] for row in rows):
        raise ResearchSafetyError("frozen evaluation label missing")
    projected = prepare_scoring_inputs(rows, input_protocol, sources, label_field)
    permutation = development_label_rotation(rows, spec.seed)

    def predict(row_id, components):
        case = deepcopy(projected[row_id])
        before = _sha(_encoded(case))
        prediction = scorer(case, components)
        if _sha(_encoded(case)) != before:
            raise ResearchSafetyError("scorer mutated frozen input")
        _encoded(prediction)  # Non-finite/unserializable predictions cannot become evidence.
        return deepcopy(prediction)

    def measured(row_id, prediction, label_id):
        row = by_id[row_id]
        prices = {}
        for entity in row["payload"]["research_inputs"]["entities"]:
            prices[entity["entity_id"]] = {
                ref["market_id"]: sources[ref["source_id"]][ref["record_id"]]["values"]["decimal_odds"]
                for ref in entity["prices"]
            }
        context = {"cohorts": deepcopy(row["payload"]["cohorts"]), "prices": prices}
        values = measure(deepcopy(prediction), deepcopy(by_id[label_id]["payload"][label_field]), context)
        if (
            not isinstance(values, Mapping)
            or set(values) != set(spec.preregistered_metrics)
            or any(not (_number(value) or type(value) is bool) for value in values.values())
        ):
            raise ResearchSafetyError("measurement differs from frozen metric contract")
        return dict(values)

    components = tuple(postflight["components"]) if role == "candidate" else ()
    predictions = {row_id: predict(row_id, components) for row_id in selected}
    metrics = {row_id: measured(row_id, predictions[row_id], row_id) for row_id in selected}
    observations = [
        {
            "row_id": row_id,
            "event_at": by_id[row_id]["event_at"],
            "split": by_id[row_id]["split"],
            "fold": by_id[row_id]["payload"]["fold"],
            "cohorts": by_id[row_id]["payload"]["cohorts"],
            "metrics": metrics[row_id],
        }
        for row_id in selected
    ]
    dev_ids = [row_id for row_id in selected if row_id in permutation]
    ablations = {}
    if role == "candidate":
        for variant, parts in postflight["variants"].items():
            ablations[variant] = [
                {
                    "row_id": row_id,
                    "metrics": metrics[row_id]
                    if set(parts) == set(components)
                    else measured(row_id, predict(row_id, tuple(parts)), row_id),
                }
                for row_id in dev_ids
            ]
    sidecar = {
        "schema_version": EXECUTION_VERSION,
        "spec_id": spec.record_id,
        "role": role,
        "commit": spec.baseline_commit if role == "baseline" else spec.candidate_commit,
        "command_index": command_index,
        "input_audit_hash": audit.to_payload()["content_hash"],
        "postflight_digest": postflight_digest,
        "trace": [{"row_id": row_id, "input_digest": _sha(_encoded(projected[row_id]))} for row_id in selected],
        "control": {
            "label_sources": {row_id: permutation[row_id] for row_id in dev_ids},
            "observations": [
                {"row_id": row_id, "metrics": measured(row_id, predictions[row_id], permutation[row_id])}
                for row_id in dev_ids
            ],
        },
        "ablations": ablations,
    }
    repeated = audit_research_inputs(
        spec,
        dataset_snapshot=dataset_snapshot,
        protocol_path=evidence.input_protocol,
        source_paths=evidence.source_paths,
        registry=registry,
    )
    if repeated.to_payload() != audit.to_payload():
        raise ResearchSafetyError("input evidence changed during harness execution")
    _read(evidence.postflight_protocol, postflight_digest)
    output = Path(output_dir).absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ResearchSafetyError("symlinked harness output forbidden")
    output.mkdir(parents=True, exist_ok=True)
    _write_report(
        output / "metrics.json",
        {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "domain": spec.domain.value,
            "sample_hash": dataset.manifest.sample_hash,
            "dataset_manifest_id": dataset.manifest.record_id,
            "dataset_artifact_digest": dataset.manifest.artifact_digest,
            "observations": observations,
        },
    )
    _write_report(output / "safety.json", sidecar)
    return sidecar
