"""Run-bound Stage 5 safety checks; no promotion, tuning, or model execution.

Sidecars are evidence from an audited harness inside a registered run artifact,
not signed execution attestations. The harness/exporter must itself be reviewed
and exercised by domain pilots; hashing arbitrary self-authored tables cannot
prove correct execution. The verifier recomputes every supported check and does
not accept a caller's `passed` field.
"""

from __future__ import annotations

import math
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from statistics import fmean, stdev
from typing import Any, Mapping

from .artifact_archive import artifact_digest
from .evaluation_rulers import load_evaluation_ruler
from .research_evaluation import load_run_observations
from .research_registry import ExperimentRegistry, ExperimentSpec
from .research_safety import (
    ResearchSafetyError,
    _encoded,
    _json,
    _number,
    _object,
    _read,
    _sha,
    _text,
    _time,
    _source,
    audit_research_inputs,
    prepare_scoring_inputs,
)


PROTOCOL_VERSION = "wong-choi-research-postflight-protocol/v1"
EXECUTION_VERSION = "wong-choi-research-safety-execution/v1"
REPORT_VERSION = "wong-choi-research-safety-report/v1"


@dataclass(frozen=True)
class SafetyEvidence:
    input_protocol: Path
    postflight_protocol: Path
    source_paths: Mapping[str, Path]


@dataclass(frozen=True)
class ResearchSafetyReport:
    run_id: str
    run_artifact_digest: str
    spec_id: str
    dataset_manifest_id: str
    input_audit_hash: str
    postflight_digest: str
    findings: tuple[str, ...]
    power: tuple[dict, ...]
    ablation: tuple[dict, ...]
    controls: tuple[dict, ...]

    @property
    def passed(self) -> bool:
        return not self.findings

    def to_payload(self) -> dict:
        payload = {
            "schema_version": REPORT_VERSION,
            "run_id": self.run_id,
            "run_artifact_digest": self.run_artifact_digest,
            "spec_id": self.spec_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "input_audit_hash": self.input_audit_hash,
            "postflight_digest": self.postflight_digest,
            "findings": list(self.findings),
            "power": list(self.power),
            "ablation": list(self.ablation),
            "controls": list(self.controls),
            "passed": self.passed,
        }
        payload["content_hash"] = _sha(_encoded(payload))
        return payload


def load_postflight_protocol(spec: ExperimentSpec, evidence: SafetyEvidence) -> tuple[dict, str]:
    input_protocol = _json(_read(evidence.input_protocol, spec.protocol_artifact_digest))
    digest = input_protocol.get("postflight_protocol_digest")
    value = _object(
        _json(_read(evidence.postflight_protocol, digest)),
        {
            "schema_version",
            "spec_id",
            "domain",
            "label_field",
            "harness_digest",
            "components",
            "variants",
            "negative_control",
            "power",
        },
        "postflight protocol",
    )
    if (
        value["schema_version"] != PROTOCOL_VERSION
        or value["spec_id"] != spec.record_id
        or value["domain"] != spec.domain.value
    ):
        raise ResearchSafetyError("postflight protocol identity mismatch")
    _text(value["label_field"], "evaluation label field")
    if value["label_field"] in {"cohorts", "fold", "research_inputs"}:
        raise ResearchSafetyError("label field must be separate from model inputs")
    _read(Path(__file__).with_name("research_harness.py"), value["harness_digest"])
    components = value["components"]
    if (
        not isinstance(components, list)
        or not components
        or any(not isinstance(item, str) or not item.strip() for item in components)
        or len(set(components)) != len(components)
    ):
        raise ResearchSafetyError("changed components must be explicitly enumerated")
    variants = value["variants"]
    if not isinstance(variants, dict) or not variants:
        raise ResearchSafetyError("finite ablation variants required")
    combinations = set()
    for name, combination in variants.items():
        _text(name, "variant")
        if (
            not isinstance(combination, list)
            or any(not isinstance(item, str) for item in combination)
            or len(set(combination)) != len(combination)
            or not set(combination) <= set(components)
        ):
            raise ResearchSafetyError("invalid ablation component set")
        frozen = frozenset(combination)
        if frozen in combinations:
            raise ResearchSafetyError("duplicate ablation combination")
        combinations.add(frozen)
    all_components = frozenset(components)
    required = {frozenset(), all_components}
    if len(components) > 1:
        required.update(frozenset([name]) for name in components)
        required.update(all_components - {name} for name in components)
    if not required <= combinations:
        raise ResearchSafetyError("missing mandatory single/leave-one-out ablation")
    ruler = load_evaluation_ruler(spec.domain)
    eligible = ruler.metric_names("primary") | ruler.metric_names("ranking")
    control = _object(value["negative_control"], {"kind", "max_gain"}, "negative control")
    if control["kind"] != "development_label_rotation":
        raise ResearchSafetyError("unsupported negative control")
    _object(control["max_gain"], eligible, "control metric set")
    if any(not _number(item) or item < 0 for item in control["max_gain"].values()):
        raise ResearchSafetyError("invalid negative control gain bounds")
    power = _object(
        value["power"], {"method", "target", "min_dev_units", "unit", "minimum_effects", "sd_floor"}, "power protocol"
    )
    if power["method"] != "paired_t_design" or power["unit"] != ruler.bootstrap["unit"]:
        raise ResearchSafetyError("power methodology/unit not supported")
    if not _number(power["target"]) or not 0.5 < power["target"] < 1:
        raise ResearchSafetyError("power target must be preregistered in (0.5, 1)")
    if type(power["min_dev_units"]) is not int or power["min_dev_units"] < 2:
        raise ResearchSafetyError("power requires at least two dev units")
    for key in ("minimum_effects", "sd_floor"):
        _object(power[key], eligible, f"power {key}")
        if any(not _number(item) or item <= 0 for item in power[key].values()):
            raise ResearchSafetyError("positive preregistered effects and SD floors required")
    if any(control["max_gain"][name] >= power["minimum_effects"][name] for name in eligible):
        raise ResearchSafetyError("negative control bound cannot admit the target effect")
    return value, digest


def development_label_rotation(rows: list[dict], seed: int) -> dict[str, str]:
    """Deterministic no-fixed-point control within family, never terminal."""
    groups = defaultdict(list)
    for row in rows:
        if row["split"] == "dev":
            cohorts = row["payload"]["cohorts"]
            scope = cohorts.get("family", cohorts.get("market_family", "all"))
            groups[scope].append(row["row_id"])
    mapping = {}
    for group in groups.values():
        ids = sorted(group)
        if len(ids) < 2:
            raise ResearchSafetyError("negative control needs at least two development events per family")
        offset = seed % (len(ids) - 1) + 1
        mapping.update({row_id: ids[(index + offset) % len(ids)] for index, row_id in enumerate(ids)})
    return mapping


def _metric_rows(value: Any, expected_ids: set[str], names: set[str]) -> dict[str, dict]:
    if not isinstance(value, list):
        raise ResearchSafetyError("control/ablation observations must be list")
    rows = {}
    for row in value:
        _object(row, {"row_id", "metrics"}, "control/ablation row")
        row_id = _text(row["row_id"], "control row_id")
        if row_id in rows:
            raise ResearchSafetyError("duplicate control/ablation row")
        _object(row["metrics"], names, "control metric schema")
        if any(not (_number(item) or type(item) is bool) for item in row["metrics"].values()):
            raise ResearchSafetyError("non-finite or nonnumeric control metric")
        rows[row_id] = row["metrics"]
    if set(rows) != expected_ids:
        raise ResearchSafetyError("control/ablation must cover exact dev rows, never terminal")
    return rows


def ineffective_label_controls(rows: list[dict], *, seed: int, label_field: str) -> tuple[str, ...]:
    by_id = {row["row_id"]: row for row in rows}
    if any(label_field not in row["payload"] for row in rows):
        raise ResearchSafetyError("frozen evaluation labels missing")
    changed = defaultdict(list)
    for target, source in development_label_rotation(rows, seed).items():
        cohorts = by_id[target]["payload"]["cohorts"]
        scope = cohorts.get("family", cohorts.get("market_family", "all"))
        changed[scope].append(
            _encoded(by_id[target]["payload"][label_field]) != _encoded(by_id[source]["payload"][label_field])
        )
    return tuple(
        f"{scope}:negative_control_does_not_change_labels"
        for scope, changes in sorted(changed.items())
        if not any(changes)
    )


def _execution_evidence(spec, verified, root, protocol, postflight_digest, input_hash, rows, projected, findings):
    raw_metrics = _json((root / "metrics.json").read_bytes())
    permutation = development_label_rotation(rows, spec.seed)
    findings.update(ineffective_label_controls(rows, seed=spec.seed, label_field=protocol["label_field"]))
    controls = {"baseline": {}, "candidate": {}}
    ablations = {name: {} for name in protocol["variants"]}
    for role in ("baseline", "candidate"):
        for index, chunk in enumerate(raw_metrics[role]):
            path = root / role / f"command-{index:02d}" / "safety.json"
            try:
                payload = _json(path.read_bytes())
            except OSError as exc:
                raise ResearchSafetyError("registered run missing safety execution sidecar") from exc
            _object(
                payload,
                {
                    "schema_version",
                    "spec_id",
                    "role",
                    "commit",
                    "command_index",
                    "input_audit_hash",
                    "postflight_digest",
                    "trace",
                    "control",
                    "ablations",
                },
                "safety execution",
            )
            expected = {
                "schema_version": EXECUTION_VERSION,
                "spec_id": spec.record_id,
                "role": role,
                "commit": spec.baseline_commit if role == "baseline" else spec.candidate_commit,
                "command_index": index,
                "input_audit_hash": input_hash,
                "postflight_digest": postflight_digest,
            }
            if any(payload[key] != expected[key] for key in expected):
                raise ResearchSafetyError("safety execution provenance mismatch")
            ids = {row["row_id"] for row in chunk["observations"]}
            traces = payload["trace"]
            if not isinstance(traces, list):
                raise ResearchSafetyError("input trace required")
            traced = set()
            for trace in traces:
                _object(trace, {"row_id", "input_digest"}, "input trace")
                row_id = _text(trace["row_id"], "trace row_id")
                if row_id not in ids or row_id in traced:
                    raise ResearchSafetyError("trace does not match command row partition")
                traced.add(row_id)
                if trace["input_digest"] != _sha(_encoded(projected[row_id])):
                    findings.add(f"{role}:{row_id}:actual_input_trace_mismatch")
            if traced != ids:
                raise ResearchSafetyError("input trace has missing rows")
            dev_ids = ids & set(permutation)
            control = _object(payload["control"], {"label_sources", "observations"}, "control execution")
            if control["label_sources"] != {row_id: permutation[row_id] for row_id in sorted(dev_ids)}:
                raise ResearchSafetyError("negative control label mapping is not the preregistered dev-only rotation")
            controls[role].update(_metric_rows(control["observations"], dev_ids, set(spec.preregistered_metrics)))
            expected_variants = set(protocol["variants"]) if role == "candidate" else set()
            _object(payload["ablations"], expected_variants, "executed ablation variants")
            for name, values in payload["ablations"].items():
                ablations[name].update(_metric_rows(values, dev_ids, set(spec.preregistered_metrics)))
    return controls, ablations


def paired_design_power(*, effect: float, sd: float, n: int, confidence: float) -> float:
    """Positive-tail paired-t design power, not observed/bootstrap power.

    Uses scipy.stats.nct, with critical t at the upper endpoint of a two-sided
    ruler CI. Assumes independent normal paired differences. Its SD comes from
    dev only with a preregistered positive floor, never terminal outcomes.
    """
    if (
        not all(_number(value) for value in (effect, sd, confidence))
        or effect <= 0
        or sd <= 0
        or not 0.5 < confidence < 1
        or type(n) is not int
        or n < 2
    ):
        raise ResearchSafetyError("invalid power inputs")
    from scipy.stats import nct, t

    critical = t.ppf((1 + confidence) / 2, n - 1)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", RuntimeWarning)
            result = float(nct.sf(critical, n - 1, (effect / sd) * math.sqrt(n)))
    except RuntimeWarning as exc:
        raise ResearchSafetyError("power numerical instability") from exc
    if not math.isfinite(result) or not 0 <= result <= 1:
        raise ResearchSafetyError("non-finite design power")
    return result


def _measured_checks(verified, protocol, controls, ablations, findings):
    ruler = load_evaluation_ruler(verified.baseline.domain)
    directions = {item["name"]: 1 if item["direction"] == "maximize" else -1 for item in ruler.metrics}
    eligible = sorted(ruler.metric_names("primary") | ruler.metric_names("ranking"))
    groups = defaultdict(lambda: {"dev": [], "terminal": []})
    baseline = {row.row_id: row for row in verified.baseline.observations}
    candidate = {row.row_id: row for row in verified.candidate.observations}
    for row in verified.baseline.observations:
        if row.split != "train":
            scope = row.cohorts.get("family", row.cohorts.get("market_family", "all"))
            groups[scope][row.split].append(row.row_id)
    variants = {frozenset(parts): name for name, parts in protocol["variants"].items()}
    all_components = frozenset(protocol["components"])
    full, empty = variants[all_components], variants[frozenset()]
    power_rows, ablation_rows, control_rows = [], [], []
    for scope, partitions in sorted(groups.items()):
        dev, terminal = partitions["dev"], partitions["terminal"]
        if not dev or not terminal:
            raise ResearchSafetyError("each research family requires dev and terminal evidence")
        for row_id in dev:
            if ablations[full][row_id] != dict(candidate[row_id].metrics) or ablations[empty][row_id] != dict(
                baseline[row_id].metrics
            ):
                raise ResearchSafetyError("full/empty ablation does not reproduce actual candidate/baseline")
        for name in eligible:
            gain = fmean(
                directions[name] * (controls["candidate"][row_id][name] - controls["baseline"][row_id][name])
                for row_id in dev
            )
            bound = protocol["negative_control"]["max_gain"][name]
            if gain > bound:
                findings.add(f"{scope}:{name}:negative_control_retains_gain")
            control_rows.append({"scope": scope, "metric": name, "dev_units": len(dev), "gain": gain, "bound": bound})
            power = protocol["power"]
            if len(dev) < power["min_dev_units"] or len(terminal) < 2:
                findings.add(f"{scope}:{name}:insufficient_power_units")
                continue
            differences = [
                directions[name] * (candidate[row_id].metrics[name] - baseline[row_id].metrics[name]) for row_id in dev
            ]
            sd = max(stdev(differences), power["sd_floor"][name])
            try:
                estimate = paired_design_power(
                    effect=power["minimum_effects"][name],
                    sd=sd,
                    n=len(terminal),
                    confidence=float(ruler.bootstrap["confidence"]),
                )
            except ResearchSafetyError:
                findings.add(f"{scope}:{name}:power_numerically_unverified")
                continue
            if estimate < power["target"]:
                findings.add(f"{scope}:{name}:design_power_below_target")
            power_rows.append(
                {
                    "scope": scope,
                    "metric": name,
                    "method": power["method"],
                    "dev_units": len(dev),
                    "terminal_units": len(terminal),
                    "sd": sd,
                    "minimum_effect": power["minimum_effects"][name],
                    "target": power["target"],
                    "estimated_power": estimate,
                }
            )
        if len(all_components) > 1:
            folds = sorted({baseline[row_id].fold for row_id in dev})
            for component in sorted(all_components):
                without = variants[all_components - {component}]
                supported = []
                for name in eligible:
                    deltas = {
                        row_id: directions[name] * (ablations[full][row_id][name] - ablations[without][row_id][name])
                        for row_id in dev
                    }
                    gain = fmean(deltas.values())
                    fold_gains = {
                        str(fold): fmean(deltas[row_id] for row_id in dev if baseline[row_id].fold == fold)
                        for fold in folds
                    }
                    if gain > 0 and all(value >= 0 for value in fold_gains.values()):
                        supported.append(name)
                    if name in ruler.metric_names("primary") and (
                        gain < 0 or any(value < 0 for value in fold_gains.values())
                    ):
                        findings.add(f"{scope}:{component}:{name}:ablation_primary_harm")
                    ablation_rows.append(
                        {
                            "scope": scope,
                            "component": component,
                            "metric": name,
                            "dev_marginal_gain": gain,
                            "fold_gains": fold_gains,
                        }
                    )
                if not supported:
                    findings.add(f"{scope}:{component}:no_supported_marginal_contribution")
    return tuple(power_rows), tuple(ablation_rows), tuple(control_rows)


def verify_research_safety(
    spec: ExperimentSpec,
    *,
    dataset_snapshot: Path,
    run_artifact: Path,
    run_id: str,
    registry: ExperimentRegistry,
    evidence: SafetyEvidence,
) -> ResearchSafetyReport:
    if not isinstance(evidence, SafetyEvidence):
        raise ResearchSafetyError("safety artifact references required, not a passed flag")
    verified = load_run_observations(
        spec, dataset_snapshot=dataset_snapshot, run_artifact=run_artifact, run_id=run_id, registry=registry
    )
    if _time(spec.created_at) > _time(verified.run["started_at"]):
        raise ResearchSafetyError("protocol was not preregistered before execution")
    input_report = audit_research_inputs(
        spec,
        dataset_snapshot=dataset_snapshot,
        protocol_path=evidence.input_protocol,
        source_paths=evidence.source_paths,
        registry=registry,
    )
    protocol, digest = load_postflight_protocol(spec, evidence)
    input_hash = input_report.to_payload()["content_hash"]
    findings = set(input_report.findings)
    power_rows, ablation_rows, control_rows = (), (), ()
    if input_report.input_checks_passed:
        rows = [
            _json(line)
            for line in _read(Path(dataset_snapshot) / "rows.jsonl", verified.dataset.artifact_digest).splitlines()
        ]
        input_protocol = _json(_read(evidence.input_protocol, spec.protocol_artifact_digest))
        sources = {
            name: _source(_read(evidence.source_paths[name], source_digest), name, spec.domain.value)
            for name, source_digest in input_protocol["sources"].items()
        }
        projected = prepare_scoring_inputs(rows, input_protocol, sources, protocol["label_field"])
        controls, ablations = _execution_evidence(
            spec, verified, Path(run_artifact), protocol, digest, input_hash, rows, projected, findings
        )
        power_rows, ablation_rows, control_rows = _measured_checks(verified, protocol, controls, ablations, findings)
    if artifact_digest(run_artifact)["sha256"] != verified.run["artifact_digest"]:
        raise ResearchSafetyError("run artifact changed during safety verification")
    _read(evidence.postflight_protocol, digest)
    repeated = audit_research_inputs(
        spec,
        dataset_snapshot=dataset_snapshot,
        protocol_path=evidence.input_protocol,
        source_paths=evidence.source_paths,
        registry=registry,
    )
    if repeated.to_payload() != input_report.to_payload():
        raise ResearchSafetyError("input evidence changed during postflight")
    return ResearchSafetyReport(
        run_id,
        verified.run["artifact_digest"],
        spec.record_id,
        verified.dataset.record_id,
        input_hash,
        digest,
        tuple(sorted(findings)),
        power_rows,
        ablation_rows,
        control_rows,
    )
