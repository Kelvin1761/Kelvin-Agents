"""Ruler-locked paired evaluation for Stage 5 research observations."""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from shared_racing.model_evaluation_decision import (
    CandidateVerdict,
    EvaluationInput,
    MetricEvidence,
    evaluate_candidate,
)

from .contracts import Domain
from .artifact_archive import artifact_digest
from .research_dataset import load_dataset_snapshot
from .evaluation_rulers import (
    DEFAULT_RULER_ROOT,
    EvaluationRuler,
    load_evaluation_ruler,
)
from .research_registry import (
    DatasetManifest,
    ExperimentDecision,
    ExperimentDecisionState,
    ExperimentRegistry,
    ExperimentSpec,
    ResearchConflictError,
)


OBSERVATION_SCHEMA_VERSION = "wong-choi-evaluation-observations/v1"
REPORT_SCHEMA_VERSION = "wong-choi-research-evaluation/v1"


class EvaluationError(RuntimeError):
    """Raised when frozen evaluation evidence is incomplete or inconsistent."""


class EvaluationVerdict(str, Enum):
    PRIMARY_WIN = "PRIMARY_WIN"
    RANKING_WIN = "RANKING_WIN"
    SHADOW_CANDIDATE = "SHADOW_CANDIDATE"
    REJECT = "REJECT"
    INCONCLUSIVE = "INCONCLUSIVE"
    DESCRIPTIVE_ONLY = "DESCRIPTIVE_ONLY"
    BLOCKED = "BLOCKED"


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _aware(value: str, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvaluationError(f"{field_name} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvaluationError(f"{field_name} must include a timezone")
    return parsed


@dataclass(frozen=True)
class EvaluationObservation:
    row_id: str
    event_at: str
    split: str
    fold: int | None
    cohorts: Mapping[str, str]
    metrics: Mapping[str, float | bool]

    def to_payload(self) -> dict[str, Any]:
        return {
            "row_id": self.row_id,
            "event_at": self.event_at,
            "split": self.split,
            "fold": self.fold,
            "cohorts": dict(sorted(self.cohorts.items())),
            "metrics": dict(sorted(self.metrics.items())),
        }


@dataclass(frozen=True)
class ObservationSeries:
    domain: Domain
    sample_hash: str
    observations: tuple[EvaluationObservation, ...]
    dataset_manifest_id: str = ""
    dataset_artifact_digest: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": OBSERVATION_SCHEMA_VERSION,
            "domain": self.domain.value,
            "sample_hash": self.sample_hash,
            "dataset_manifest_id": self.dataset_manifest_id,
            "dataset_artifact_digest": self.dataset_artifact_digest,
            "observations": [item.to_payload() for item in self.observations],
        }


@dataclass(frozen=True)
class MetricComparison:
    development_delta: float
    terminal_delta: float
    terminal_ci_low: float
    terminal_ci_high: float
    higher_is_better: bool
    development_rows: int
    terminal_rows: int
    fold_deltas: tuple[tuple[int, float], ...]
    baseline_development_mean: float
    baseline_terminal_mean: float
    candidate_development_mean: float
    candidate_terminal_mean: float
    candidate_terminal_ci_low: float
    candidate_terminal_ci_high: float

    def favourable(self) -> tuple[float, float, float, float]:
        if self.higher_is_better:
            return (
                self.development_delta,
                self.terminal_delta,
                self.terminal_ci_low,
                self.terminal_ci_high,
            )
        return (
            -self.development_delta,
            -self.terminal_delta,
            -self.terminal_ci_high,
            -self.terminal_ci_low,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "development_delta": self.development_delta,
            "terminal_delta": self.terminal_delta,
            "terminal_ci_low": self.terminal_ci_low,
            "terminal_ci_high": self.terminal_ci_high,
            "higher_is_better": self.higher_is_better,
            "development_rows": self.development_rows,
            "terminal_rows": self.terminal_rows,
            "fold_deltas": [{"fold": fold, "delta": delta} for fold, delta in self.fold_deltas],
            "baseline_development_mean": self.baseline_development_mean,
            "baseline_terminal_mean": self.baseline_terminal_mean,
            "candidate_development_mean": self.candidate_development_mean,
            "candidate_terminal_mean": self.candidate_terminal_mean,
            "candidate_terminal_ci_low": self.candidate_terminal_ci_low,
            "candidate_terminal_ci_high": self.candidate_terminal_ci_high,
        }


@dataclass(frozen=True)
class ScopeEvaluation:
    scope: str
    verdict: EvaluationVerdict
    reason: str
    row_count: int
    metrics: Mapping[str, MetricComparison]
    cohort_regressions: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "scope": self.scope,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "row_count": self.row_count,
            "metrics": {name: comparison.to_payload() for name, comparison in sorted(self.metrics.items())},
            "cohort_regressions": list(self.cohort_regressions),
        }


@dataclass(frozen=True)
class EvaluationReport:
    domain: Domain
    spec_id: str
    dataset_manifest_id: str
    ruler_id: str
    ruler_digest: str
    input_metrics_digest: str
    verdict: EvaluationVerdict
    reason: str
    promotion_proposal_allowed: bool
    safety_passed: bool
    scopes: tuple[ScopeEvaluation, ...]

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "schema_version": REPORT_SCHEMA_VERSION,
            "append_only": True,
            "domain": self.domain.value,
            "spec_id": self.spec_id,
            "dataset_manifest_id": self.dataset_manifest_id,
            "ruler_id": self.ruler_id,
            "ruler_digest": self.ruler_digest,
            "input_metrics_digest": self.input_metrics_digest,
            "verdict": self.verdict.value,
            "reason": self.reason,
            "promotion_proposal_allowed": self.promotion_proposal_allowed,
            "safety_passed": self.safety_passed,
            "scopes": [scope.to_payload() for scope in self.scopes],
        }
        payload["content_hash"] = _digest(payload)
        return payload


@dataclass(frozen=True)
class PublishedEvaluationDecision:
    status: str
    decision_id: str
    report_path: Path


def _ruler_and_digest(domain: Domain, *, ruler_root: Path | None) -> tuple[EvaluationRuler, str]:
    root = Path(ruler_root) if ruler_root is not None else DEFAULT_RULER_ROOT
    ruler = load_evaluation_ruler(domain, root=root)
    path = root / f"{ruler.ruler_id}.json"
    try:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise EvaluationError(f"cannot hash frozen ruler: {path}") from exc
    return ruler, digest


def _metric_contract(ruler: EvaluationRuler) -> dict[str, dict[str, str]]:
    return {
        str(item["name"]): {
            "role": str(item["role"]),
            "direction": str(item["direction"]),
        }
        for item in ruler.metrics
    }


def _validate_inputs(
    spec: ExperimentSpec,
    dataset: DatasetManifest,
    baseline: ObservationSeries,
    candidate: ObservationSeries,
    ruler: EvaluationRuler,
    ruler_digest: str,
) -> None:
    spec.validate()
    dataset.validate()
    if spec.domain is not ruler.domain or dataset.domain is not ruler.domain:
        raise EvaluationError("ruler domain does not match experiment lineage")
    if dataset.spec_id != spec.record_id:
        raise EvaluationError("dataset does not belong to experiment spec")
    if spec.evaluation_ruler_id != ruler.ruler_id:
        raise EvaluationError("frozen ruler id mismatch")
    if spec.evaluation_ruler_digest != ruler_digest:
        raise EvaluationError("frozen ruler digest mismatch")
    if spec.seed != int(ruler.bootstrap["seed"]):
        raise EvaluationError("experiment seed conflicts with frozen ruler")
    metric_contract = _metric_contract(ruler)
    if set(spec.preregistered_metrics) != set(metric_contract) or len(spec.preregistered_metrics) != len(
        metric_contract
    ):
        raise EvaluationError("pre-registered metrics must exactly match frozen ruler")
    if baseline.domain is not ruler.domain or candidate.domain is not ruler.domain:
        raise EvaluationError("observation series domain mismatch")
    if baseline.sample_hash != dataset.sample_hash or candidate.sample_hash != dataset.sample_hash:
        raise EvaluationError("observation sample hash mismatch")
    for series in (baseline, candidate):
        if series.dataset_manifest_id != dataset.record_id:
            raise EvaluationError("observation dataset manifest id mismatch")
        if series.dataset_artifact_digest != dataset.artifact_digest:
            raise EvaluationError("observation dataset artifact digest mismatch")
    if len(baseline.observations) != dataset.row_count or len(candidate.observations) != dataset.row_count:
        raise EvaluationError("observation row count does not match dataset")
    split_counts = {item.name: item.row_count for item in dataset.splits}
    actual_counts = {
        name: sum(item.split == name for item in baseline.observations) for name in ("train", "dev", "terminal")
    }
    if actual_counts != split_counts:
        raise EvaluationError("observation split counts do not match dataset")

    row_ids: set[str] = set()
    dev_folds: set[int] = set()
    dates_by_split: dict[str, list[datetime]] = {key: [] for key in actual_counts}
    dates_by_fold: dict[int, list[datetime]] = {}
    cutoff = _aware(dataset.point_in_time_cutoff, "dataset.point_in_time_cutoff")
    for baseline_row, candidate_row in zip(baseline.observations, candidate.observations):
        if baseline_row.row_id in row_ids or not baseline_row.row_id.strip():
            raise EvaluationError("duplicate or empty evaluation row_id")
        row_ids.add(baseline_row.row_id)
        paired_fields = (
            baseline_row.row_id == candidate_row.row_id
            and baseline_row.event_at == candidate_row.event_at
            and baseline_row.split == candidate_row.split
            and baseline_row.fold == candidate_row.fold
            and dict(baseline_row.cohorts) == dict(candidate_row.cohorts)
        )
        if not paired_fields:
            raise EvaluationError("paired row identity or provenance mismatch")
        event = _aware(baseline_row.event_at, "observation.event_at").astimezone(timezone.utc)
        if event > cutoff:
            raise EvaluationError("observation event exceeds dataset cutoff")
        if baseline_row.split not in {"train", "dev", "terminal"}:
            raise EvaluationError("unsupported observation split")
        dates_by_split[baseline_row.split].append(event)
        if baseline_row.split == "dev":
            if isinstance(baseline_row.fold, bool) or not isinstance(baseline_row.fold, int) or baseline_row.fold < 1:
                raise EvaluationError("development rows require a positive fold")
            dev_folds.add(baseline_row.fold)
            dates_by_fold.setdefault(baseline_row.fold, []).append(event)
        elif baseline_row.fold is not None:
            raise EvaluationError("only development rows may declare a fold")
        if set(baseline_row.cohorts) != set(ruler.cohorts) or any(
            not str(value).strip() for value in baseline_row.cohorts.values()
        ):
            raise EvaluationError("observation cohorts do not match frozen ruler")
        for row in (baseline_row, candidate_row):
            if set(row.metrics) != set(metric_contract):
                raise EvaluationError("observation metrics do not match frozen ruler")
            for value in row.metrics.values():
                if isinstance(value, bool):
                    continue
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    raise EvaluationError("observation metric must be finite numeric")
    if len(dev_folds) < 2:
        raise EvaluationError("walk-forward evaluation requires multiple development folds")
    for earlier, later in (("train", "dev"), ("dev", "terminal")):
        if not dates_by_split[earlier] or not dates_by_split[later]:
            raise EvaluationError("chronological evaluation requires all three splits")
        if max(dates_by_split[earlier]).date() >= min(dates_by_split[later]).date():
            raise EvaluationError("observation splits are not chronological whole-date partitions")
    ordered_folds = sorted(dev_folds)
    if ordered_folds != list(range(1, len(ordered_folds) + 1)):
        raise EvaluationError("development fold IDs must be contiguous from 1")
    for earlier, later in zip(ordered_folds, ordered_folds[1:]):
        if max(dates_by_fold[earlier]).date() >= min(dates_by_fold[later]).date():
            raise EvaluationError("development folds must be chronological and non-overlapping")


def _mean(values: list[float]) -> float:
    if not values:
        raise EvaluationError("metric comparison has no paired rows")
    return math.fsum(values) / len(values)


def _bootstrap_ci(deltas: list[float], *, trials: int, confidence: float, seed: int) -> tuple[float, float]:
    if not deltas:
        raise EvaluationError("terminal metric has no paired rows")
    if all(value == deltas[0] for value in deltas):
        return deltas[0], deltas[0]
    rng = random.Random(seed)
    size = len(deltas)
    estimates = sorted(sum(deltas[rng.randrange(size)] for _ in range(size)) / size for _ in range(trials))
    tail = (1.0 - confidence) / 2.0
    low_index = max(0, math.floor(trials * tail))
    high_index = min(trials - 1, math.ceil(trials * (1.0 - tail)) - 1)
    return estimates[low_index], estimates[high_index]


def _comparison(
    metric: str,
    indices: list[int],
    baseline: ObservationSeries,
    candidate: ObservationSeries,
    *,
    higher_is_better: bool,
    trials: int,
    confidence: float,
    seed: int,
) -> MetricComparison:
    development = [index for index in indices if baseline.observations[index].split == "dev"]
    terminal = [index for index in indices if baseline.observations[index].split == "terminal"]

    def deltas(selected: list[int]) -> list[float]:
        return [
            float(candidate.observations[index].metrics[metric]) - float(baseline.observations[index].metrics[metric])
            for index in selected
        ]

    development_deltas = deltas(development)
    terminal_deltas = deltas(terminal)
    ci_low, ci_high = _bootstrap_ci(terminal_deltas, trials=trials, confidence=confidence, seed=seed)
    folds = sorted(
        {
            int(baseline.observations[index].fold)
            for index in development
            if baseline.observations[index].fold is not None
        }
    )
    fold_deltas = tuple(
        (
            fold,
            _mean(deltas([index for index in development if baseline.observations[index].fold == fold])),
        )
        for fold in folds
    )
    candidate_terminal = [float(candidate.observations[i].metrics[metric]) for i in terminal]
    candidate_low, candidate_high = _bootstrap_ci(candidate_terminal, trials=trials, confidence=confidence, seed=seed)
    return MetricComparison(
        development_delta=_mean(development_deltas),
        terminal_delta=_mean(terminal_deltas),
        terminal_ci_low=ci_low,
        terminal_ci_high=ci_high,
        higher_is_better=higher_is_better,
        development_rows=len(development),
        terminal_rows=len(terminal),
        fold_deltas=fold_deltas,
        baseline_development_mean=_mean([float(baseline.observations[i].metrics[metric]) for i in development]),
        baseline_terminal_mean=_mean([float(baseline.observations[i].metrics[metric]) for i in terminal]),
        candidate_development_mean=_mean([float(candidate.observations[i].metrics[metric]) for i in development]),
        candidate_terminal_mean=_mean(candidate_terminal),
        candidate_terminal_ci_low=candidate_low,
        candidate_terminal_ci_high=candidate_high,
    )


def _cohort_regressions(
    indices: list[int],
    baseline: ObservationSeries,
    candidate: ObservationSeries,
    ruler: EvaluationRuler,
    metrics: Mapping[str, MetricComparison],
) -> tuple[str, ...]:
    metric_contract = _metric_contract(ruler)
    guarded_roles = {"primary", "ranking", "guardrail"}
    regressions: list[str] = []
    for cohort in ruler.cohorts:
        values = sorted({str(baseline.observations[index].cohorts[cohort]) for index in indices})
        for value in values:
            selected = [
                index
                for index in indices
                if baseline.observations[index].cohorts[cohort] == value
                and baseline.observations[index].split in {"dev", "terminal"}
            ]
            if not any(baseline.observations[index].split == "dev" for index in selected) or not any(
                baseline.observations[index].split == "terminal" for index in selected
            ):
                continue
            for metric, contract in metric_contract.items():
                if contract["role"] not in guarded_roles:
                    continue
                aggregate_dev, aggregate_terminal, _low, _high = metrics[metric].favourable()
                if aggregate_dev < 0 or aggregate_terminal < 0:
                    # The main decision contract owns aggregate regression.
                    # Cohort regression is reserved for additional subgroup harm.
                    continue
                comparison = _comparison(
                    metric,
                    selected,
                    baseline,
                    candidate,
                    higher_is_better=contract["direction"] == "maximize",
                    trials=int(ruler.bootstrap["trials"]),
                    confidence=float(ruler.bootstrap["confidence"]),
                    seed=int(ruler.bootstrap["seed"]),
                )
                _dev, _terminal, _low, high = comparison.favourable()
                if high < 0:
                    regressions.append(f"{cohort}={value}:{metric}")
    return tuple(sorted(regressions))


def _horse_scope(
    domain: Domain,
    indices: list[int],
    baseline: ObservationSeries,
    candidate: ObservationSeries,
    ruler: EvaluationRuler,
    metrics: Mapping[str, MetricComparison],
    cohort_regressions: tuple[str, ...],
    *,
    safety_passed: bool,
) -> ScopeEvaluation:
    contract = _metric_contract(ruler)
    primary = {
        name: MetricEvidence(
            comparison.development_delta,
            comparison.terminal_delta,
            comparison.terminal_ci_low,
            comparison.terminal_ci_high,
            comparison.higher_is_better,
        )
        for name, comparison in metrics.items()
        if contract[name]["role"] == "primary"
    }
    ranking = {
        name: MetricEvidence(
            comparison.development_delta,
            comparison.terminal_delta,
            comparison.terminal_ci_low,
            comparison.terminal_ci_high,
            comparison.higher_is_better,
        )
        for name, comparison in metrics.items()
        if contract[name]["role"] == "ranking"
    }
    nontrain = sum(baseline.observations[index].split in {"dev", "terminal"} for index in indices)
    result = evaluate_candidate(
        EvaluationInput(
            domain=domain.value,
            baseline_sample_hash=baseline.sample_hash,
            candidate_sample_hash=candidate.sample_hash,
            baseline_races=nontrain,
            candidate_races=nontrain,
            holdout_locked=True,
            leakage_audit_passed=safety_passed,
            primary=primary,
            ranking=ranking,
            cohort_regressions=cohort_regressions,
        )
    )
    verdict = {
        CandidateVerdict.PRIMARY_WIN.value: EvaluationVerdict.PRIMARY_WIN,
        CandidateVerdict.RANKING_WIN.value: EvaluationVerdict.RANKING_WIN,
        CandidateVerdict.REJECT.value: EvaluationVerdict.REJECT,
    }[str(result["verdict"])]
    return ScopeEvaluation(
        scope="all",
        verdict=verdict,
        reason=str(result["reason"]),
        row_count=nontrain,
        metrics=metrics,
        cohort_regressions=cohort_regressions,
    )


def _family_scope(
    domain: Domain,
    scope_name: str,
    indices: list[int],
    baseline: ObservationSeries,
    ruler: EvaluationRuler,
    metrics: Mapping[str, MetricComparison],
    cohort_regressions: tuple[str, ...],
) -> ScopeEvaluation:
    contract = _metric_contract(ruler)
    row_count = sum(baseline.observations[index].split in {"dev", "terminal"} for index in indices)
    primary = {
        name: comparison.favourable() for name, comparison in metrics.items() if contract[name]["role"] == "primary"
    }
    guardrails = {
        name: comparison.favourable() for name, comparison in metrics.items() if contract[name]["role"] == "guardrail"
    }
    primary_regressions = [name for name, (dev, terminal, _low, _high) in primary.items() if dev < 0 or terminal < 0]
    if primary_regressions:
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.REJECT,
            "primary_regression",
            row_count,
            metrics,
            cohort_regressions,
        )
    guardrail_regressions = [
        name for name, (dev, terminal, _low, _high) in guardrails.items() if dev < 0 or terminal < 0
    ]
    if guardrail_regressions:
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.REJECT,
            "guardrail_regression",
            row_count,
            metrics,
            cohort_regressions,
        )
    if cohort_regressions:
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.REJECT,
            "cohort_regression",
            row_count,
            metrics,
            cohort_regressions,
        )
    if domain is Domain.NBA and ruler.decision_mode == "descriptive_only":
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.DESCRIPTIVE_ONLY,
            "ruler_descriptive_only",
            row_count,
            metrics,
            cohort_regressions,
        )
    floor = ruler.sample_policy.get("promotion_floor")
    if floor is not None and row_count < int(floor):
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.INCONCLUSIVE,
            "family_below_sample_floor",
            row_count,
            metrics,
            cohort_regressions,
        )
    if domain is Domain.TENNIS:
        market_metrics = [metrics[name] for name in ("brier_gain_vs_market", "log_loss_gain_vs_market")]
        if any(item.candidate_development_mean < 0 or item.candidate_terminal_mean < 0 for item in market_metrics):
            return ScopeEvaluation(
                scope_name, EvaluationVerdict.REJECT, "market_not_beaten", row_count, metrics, cohort_regressions
            )
        roi = metrics["roi"]
        if roi.candidate_development_mean < 0 or roi.candidate_terminal_mean < 0:
            return ScopeEvaluation(
                scope_name, EvaluationVerdict.REJECT, "negative_absolute_roi", row_count, metrics, cohort_regressions
            )
        if any(item.candidate_development_mean <= 0 or item.candidate_terminal_ci_low <= 0 for item in market_metrics):
            return ScopeEvaluation(
                scope_name,
                EvaluationVerdict.INCONCLUSIVE,
                "primary_evidence_too_weak",
                row_count,
                metrics,
                cohort_regressions,
            )
        if roi.candidate_terminal_ci_low < 0:
            return ScopeEvaluation(
                scope_name,
                EvaluationVerdict.INCONCLUSIVE,
                "roi_downside_uncertain",
                row_count,
                metrics,
                cohort_regressions,
            )
    primary_supported = [
        name for name, (dev, terminal, low, _high) in primary.items() if dev > 0 and terminal > 0 and low > 0
    ]
    if primary_supported and all(dev > 0 and terminal > 0 for dev, terminal, _low, _high in primary.values()):
        return ScopeEvaluation(
            scope_name,
            EvaluationVerdict.SHADOW_CANDIDATE,
            "market_relative_supported_gain",
            row_count,
            metrics,
            cohort_regressions,
        )
    return ScopeEvaluation(
        scope_name,
        EvaluationVerdict.INCONCLUSIVE,
        "primary_evidence_too_weak",
        row_count,
        metrics,
        cohort_regressions,
    )


def evaluate_research_candidate(
    spec: ExperimentSpec,
    dataset: DatasetManifest,
    baseline: ObservationSeries,
    candidate: ObservationSeries,
    *,
    safety_passed: bool,
    ruler_root: Path | None = None,
) -> EvaluationReport:
    ruler, digest = _ruler_and_digest(spec.domain, ruler_root=ruler_root)
    _validate_inputs(spec, dataset, baseline, candidate, ruler, digest)
    input_metrics_digest = _digest(
        {
            "baseline": [baseline.to_payload()],
            "candidate": [candidate.to_payload()],
        }
    )
    if safety_passed is not True:
        return EvaluationReport(
            domain=spec.domain,
            spec_id=spec.record_id,
            dataset_manifest_id=dataset.record_id,
            ruler_id=ruler.ruler_id,
            ruler_digest=digest,
            input_metrics_digest=input_metrics_digest,
            verdict=EvaluationVerdict.BLOCKED,
            reason="research_safety_gate_failed",
            promotion_proposal_allowed=False,
            safety_passed=False,
            scopes=(),
        )

    metric_contract = _metric_contract(ruler)
    if ruler.family_specific:
        family_key = "family" if spec.domain is Domain.TENNIS else "market_family"
        scope_names = sorted({str(row.cohorts[family_key]) for row in baseline.observations})
    else:
        family_key = None
        scope_names = ["all"]
    scopes: list[ScopeEvaluation] = []
    for scope_name in scope_names:
        indices = [
            index
            for index, row in enumerate(baseline.observations)
            if family_key is None or row.cohorts[family_key] == scope_name
        ]
        comparisons = {
            name: _comparison(
                name,
                indices,
                baseline,
                candidate,
                higher_is_better=contract["direction"] == "maximize",
                trials=int(ruler.bootstrap["trials"]),
                confidence=float(ruler.bootstrap["confidence"]),
                seed=int(ruler.bootstrap["seed"]),
            )
            for name, contract in metric_contract.items()
        }
        regressions = _cohort_regressions(indices, baseline, candidate, ruler, comparisons)
        if spec.domain in {Domain.AU, Domain.HKJC}:
            scope = _horse_scope(
                spec.domain,
                indices,
                baseline,
                candidate,
                ruler,
                comparisons,
                regressions,
                safety_passed=safety_passed,
            )
        else:
            scope = _family_scope(
                spec.domain,
                scope_name,
                indices,
                baseline,
                ruler,
                comparisons,
                regressions,
            )
        scopes.append(scope)

    verdicts = {scope.verdict for scope in scopes}
    if spec.domain is Domain.NBA and EvaluationVerdict.REJECT not in verdicts:
        verdict = EvaluationVerdict.DESCRIPTIVE_ONLY
        reason = "ruler_descriptive_only"
    elif EvaluationVerdict.REJECT in verdicts:
        verdict = EvaluationVerdict.REJECT
        reason = next(scope.reason for scope in scopes if scope.verdict is EvaluationVerdict.REJECT)
    elif verdicts == {EvaluationVerdict.PRIMARY_WIN}:
        verdict = EvaluationVerdict.PRIMARY_WIN
        reason = scopes[0].reason
    elif verdicts == {EvaluationVerdict.RANKING_WIN}:
        verdict = EvaluationVerdict.RANKING_WIN
        reason = scopes[0].reason
    elif verdicts == {EvaluationVerdict.SHADOW_CANDIDATE}:
        verdict = EvaluationVerdict.SHADOW_CANDIDATE
        reason = scopes[0].reason
    else:
        verdict = EvaluationVerdict.INCONCLUSIVE
        reason = next(
            (scope.reason for scope in scopes if scope.verdict is EvaluationVerdict.INCONCLUSIVE),
            "mixed_family_evidence",
        )
    return EvaluationReport(
        domain=spec.domain,
        spec_id=spec.record_id,
        dataset_manifest_id=dataset.record_id,
        ruler_id=ruler.ruler_id,
        ruler_digest=digest,
        input_metrics_digest=input_metrics_digest,
        verdict=verdict,
        reason=reason,
        promotion_proposal_allowed=(
            ruler.promotion_allowed
            and verdict
            in {
                EvaluationVerdict.PRIMARY_WIN,
                EvaluationVerdict.RANKING_WIN,
                EvaluationVerdict.SHADOW_CANDIDATE,
            }
        ),
        safety_passed=True,
        scopes=tuple(scopes),
    )


def _observation_series(payload: Any) -> ObservationSeries:
    fields = {
        "schema_version",
        "domain",
        "sample_hash",
        "dataset_manifest_id",
        "dataset_artifact_digest",
        "observations",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise EvaluationError("invalid observation series schema")
    if payload["schema_version"] != OBSERVATION_SCHEMA_VERSION or not isinstance(payload["observations"], list):
        raise EvaluationError("unsupported observation series schema")
    rows = []
    for item in payload["observations"]:
        if not isinstance(item, dict) or set(item) != {"row_id", "event_at", "split", "fold", "cohorts", "metrics"}:
            raise EvaluationError("invalid observation row schema")
        if any(not isinstance(item[key], str) for key in ("row_id", "event_at", "split")):
            raise EvaluationError("observation identity fields must be strings")
        if not isinstance(item["cohorts"], dict) or not isinstance(item["metrics"], dict):
            raise EvaluationError("observation cohorts and metrics must be objects")
        if any(not isinstance(value, str) for value in item["cohorts"].values()):
            raise EvaluationError("observation cohort values must be strings")
        rows.append(EvaluationObservation(**item))
    try:
        domain = Domain(payload["domain"])
    except (ValueError, TypeError) as exc:
        raise EvaluationError("invalid observation domain") from exc
    return ObservationSeries(
        domain, payload["sample_hash"], tuple(rows), payload["dataset_manifest_id"], payload["dataset_artifact_digest"]
    )


def _strict_json(raw: str) -> Any:
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise EvaluationError(f"duplicate JSON key: {key}")
            value[key] = item
        return value

    def invalid_constant(value):
        raise EvaluationError(f"non-finite JSON constant: {value}")

    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except ValueError as exc:
        raise EvaluationError("invalid evaluation JSON") from exc


def evaluate_run_artifact(
    spec: ExperimentSpec,
    *,
    dataset_snapshot: Path,
    run_artifact: Path,
    run_id: str,
    registry: ExperimentRegistry,
    safety_passed: bool,
) -> EvaluationReport:
    """Verify Task 4 output bytes and Task 3 row identity before evaluation.

    Multi-command specs may partition observations, but no command output can
    be silently selected or discarded. Frozen rows must contain cohort/fold
    annotations in their payload, so both scorers cannot jointly relabel data.
    """
    snapshot = load_dataset_snapshot(dataset_snapshot)
    dataset = snapshot.manifest
    run = registry.load(run_id)
    if registry.load(spec.record_id) != spec.to_payload() or registry.load(dataset.record_id) != dataset.to_payload():
        raise EvaluationError("evaluation inputs differ from registered lineage")
    if (
        run.get("kind") != "experiment_run"
        or run.get("state") != "succeeded"
        or run.get("links", {}).get("spec_id") != spec.record_id
        or run.get("links", {}).get("dataset_manifest_id") != dataset.record_id
        or run.get("evaluation_ruler_id") != spec.evaluation_ruler_id
        or run.get("evaluation_ruler_digest") != spec.evaluation_ruler_digest
        or run.get("baseline_commit") != spec.baseline_commit
        or run.get("candidate_commit") != spec.candidate_commit
        or run.get("seed") != spec.seed
        or run.get("commands") != list(spec.commands)
    ):
        raise EvaluationError("run artifact provenance conflicts with registered spec")
    if (
        run_artifact.is_symlink()
        or not run_artifact.is_dir()
        or any(path.is_symlink() for path in run_artifact.rglob("*"))
    ):
        raise EvaluationError("unsafe run artifact path")
    if artifact_digest(run_artifact)["sha256"] != run["artifact_digest"]:
        raise EvaluationError("run artifact digest mismatch")
    metrics = _strict_json((run_artifact / "metrics.json").read_text(encoding="utf-8"))
    if (
        not isinstance(metrics, dict)
        or set(metrics) != {"baseline", "candidate"}
        or _digest(metrics) != run["metrics_digest"]
    ):
        raise EvaluationError("run artifact metrics digest or roles mismatch")
    rows_bytes = (snapshot.path / "rows.jsonl").read_bytes()
    if hashlib.sha256(rows_bytes).hexdigest() != dataset.artifact_digest:
        raise EvaluationError("frozen dataset rows digest mismatch")
    frozen_rows = [_strict_json(line) for line in rows_bytes.decode("utf-8").splitlines()]
    identities = {row["row_id"]: row for row in frozen_rows}
    series = {}
    for role in ("baseline", "candidate"):
        chunks = metrics[role]
        if not isinstance(chunks, list) or len(chunks) != len(spec.commands):
            raise EvaluationError("every registered command must supply observations")
        combined = []
        for chunk in chunks:
            current = _observation_series(chunk)
            if (
                current.domain is not spec.domain
                or current.sample_hash != dataset.sample_hash
                or current.dataset_manifest_id != dataset.record_id
                or current.dataset_artifact_digest != dataset.artifact_digest
            ):
                raise EvaluationError("run observations differ from frozen dataset lineage")
            combined.extend(current.observations)
        ids = [row.row_id for row in combined]
        if len(set(ids)) != len(ids) or set(ids) != set(identities):
            raise EvaluationError("observations do not match frozen dataset row identities")
        for row in combined:
            frozen = identities[row.row_id]
            if (
                row.event_at != frozen["event_at"]
                or row.split != frozen["split"]
                or "fold" not in frozen["payload"]
                or row.fold != frozen["payload"]["fold"]
                or dict(row.cohorts) != frozen["payload"].get("cohorts")
            ):
                raise EvaluationError("observations relabel a frozen dataset row")
        by_id = {row.row_id: row for row in combined}
        series[role] = ObservationSeries(
            spec.domain,
            dataset.sample_hash,
            tuple(by_id[row["row_id"]] for row in frozen_rows),
            dataset.record_id,
            dataset.artifact_digest,
        )
    report = evaluate_research_candidate(
        spec, dataset, series["baseline"], series["candidate"], safety_passed=safety_passed
    )
    if (
        artifact_digest(run_artifact)["sha256"] != run["artifact_digest"]
        or load_dataset_snapshot(snapshot.path).manifest.to_payload() != dataset.to_payload()
    ):
        raise EvaluationError("evaluation artifact changed during analysis")
    return replace(report, input_metrics_digest=run["metrics_digest"])


def _write_report(path: Path, payload: Mapping[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != encoded:
                raise EvaluationError("immutable evaluation report conflict")
            return "duplicate"
    finally:
        temporary.unlink(missing_ok=True)
    return "created"


def publish_evaluation_decision(
    report: EvaluationReport,
    *,
    registry: ExperimentRegistry,
    run_id: str,
    report_root: Path,
    decided_at: str,
) -> PublishedEvaluationDecision:
    _aware(decided_at, "decided_at")
    try:
        run = registry.load(run_id)
    except (FileNotFoundError, ResearchConflictError) as exc:
        raise EvaluationError(f"experiment run unavailable: {run_id}") from exc
    if (
        run.get("kind") != "experiment_run"
        or run.get("domain") != report.domain.value
        or run.get("links", {}).get("spec_id") != report.spec_id
        or run.get("links", {}).get("dataset_manifest_id") != report.dataset_manifest_id
        or run.get("metrics_digest") != report.input_metrics_digest
        or run.get("evaluation_ruler_id") != report.ruler_id
        or run.get("evaluation_ruler_digest") != report.ruler_digest
        or run.get("state") != "succeeded"
    ):
        raise EvaluationError("evaluation report conflicts with frozen experiment run")
    payload = report.to_payload()
    report_path = (
        report_root.expanduser().resolve() / report.domain.value / str(payload["content_hash"]) / "report.json"
    )
    report_status = _write_report(report_path, payload)
    artifact_digest = hashlib.sha256(report_path.read_bytes()).hexdigest()
    state = {
        EvaluationVerdict.PRIMARY_WIN: ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL,
        EvaluationVerdict.RANKING_WIN: ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL,
        EvaluationVerdict.SHADOW_CANDIDATE: ExperimentDecisionState.SHADOW_REVIEW_PROPOSAL,
        EvaluationVerdict.REJECT: ExperimentDecisionState.REJECT,
        EvaluationVerdict.INCONCLUSIVE: ExperimentDecisionState.INCONCLUSIVE,
        EvaluationVerdict.DESCRIPTIVE_ONLY: ExperimentDecisionState.INCONCLUSIVE,
        EvaluationVerdict.BLOCKED: ExperimentDecisionState.BLOCKED,
    }[report.verdict]
    identity = _digest({"run_id": run_id, "report_hash": payload["content_hash"], "state": state.value})[:24]
    decision_id = f"wc:{report.domain.value}:experiment-decision:{identity}"
    if registry.find(decision_id) is not None:
        prior = registry.load(decision_id)
        decided_at = prior["decided_at"]
    decision = ExperimentDecision(
        record_id=decision_id,
        domain=report.domain,
        created_at=decided_at,
        run_id=run_id,
        decided_at=decided_at,
        state=state,
        rationale=f"{report.verdict.value}: {report.reason}",
        metrics_digest=report.input_metrics_digest,
        artifact_digest=artifact_digest,
    )
    appended = registry.append(decision)
    status = "created" if report_status == "created" and appended.status == "created" else "duplicate"
    return PublishedEvaluationDecision(status, decision.record_id, report_path)
