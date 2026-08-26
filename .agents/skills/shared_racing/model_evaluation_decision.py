"""Stage 4 AU/HKJC candidate verdict: primary KPI first, ranking squeeze second."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import math
import random
from typing import Mapping


class CandidateVerdict(str, Enum):
    PRIMARY_WIN = "PRIMARY_WIN"
    RANKING_WIN = "RANKING_WIN"
    REJECT = "REJECT"


@dataclass(frozen=True)
class MetricEvidence:
    """Paired candidate-minus-baseline evidence on locked development/terminal data."""

    development_delta: float
    terminal_delta: float
    terminal_ci_low: float
    terminal_ci_high: float
    higher_is_better: bool = True

    def favourable(self) -> "MetricEvidence":
        if self.higher_is_better:
            return self
        return MetricEvidence(
            development_delta=-self.development_delta,
            terminal_delta=-self.terminal_delta,
            terminal_ci_low=-self.terminal_ci_high,
            terminal_ci_high=-self.terminal_ci_low,
            higher_is_better=True,
        )


@dataclass(frozen=True)
class EvaluationInput:
    domain: str
    baseline_sample_hash: str
    candidate_sample_hash: str
    baseline_races: int
    candidate_races: int
    holdout_locked: bool
    leakage_audit_passed: bool
    primary: Mapping[str, MetricEvidence]
    ranking: Mapping[str, MetricEvidence]
    cohort_regressions: tuple[str, ...] = ()


PRIMARY_KEYS = {
    "au": ("gold", "good_positional"),
    "hkjc": ("gold", "good_positional"),
}

RANKING_KEYS = frozenset(
    {
        "top3_capture_at5",
        "mean_top3_model_rank",
        "competitive_recall_at5",
        "ndcg_at5",
        "top5_pairwise_auc",
    }
)

METRIC_DIRECTIONS = {
    "gold": True,
    "good_positional": True,
    "top3_capture_at5": True,
    "mean_top3_model_rank": False,
    "competitive_recall_at5": True,
    "ndcg_at5": True,
    "top5_pairwise_auc": True,
}


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _paired_metric_evidence(
    baseline: list[float | None],
    candidate: list[float | None],
    development: list[int],
    terminal: list[int],
    *,
    higher_is_better: bool,
    bootstrap: int = 2000,
    seed: int = 7,
) -> MetricEvidence:
    def deltas(indices: list[int]) -> list[float]:
        return [
            float(candidate[index]) - float(baseline[index])
            for index in indices
            if baseline[index] is not None and candidate[index] is not None
        ]

    dev_delta = _mean(deltas(development))
    terminal_deltas = deltas(terminal)
    terminal_delta = _mean(terminal_deltas)
    if not terminal_deltas:
        ci_low = ci_high = 0.0
    elif all(value == terminal_deltas[0] for value in terminal_deltas):
        ci_low = ci_high = terminal_deltas[0]
    else:
        rng = random.Random(seed)
        size = len(terminal_deltas)
        samples = sorted(
            _mean([terminal_deltas[rng.randrange(size)] for _ in range(size)])
            for _ in range(bootstrap)
        )
        ci_low = samples[max(0, math.floor(bootstrap * 0.025))]
        ci_high = samples[min(bootstrap - 1, math.ceil(bootstrap * 0.975) - 1)]
    return MetricEvidence(
        development_delta=dev_delta,
        terminal_delta=terminal_delta,
        terminal_ci_low=ci_low,
        terminal_ci_high=ci_high,
        higher_is_better=higher_is_better,
    )


def build_evaluation_input(
    *,
    domain: str,
    dates: list[str],
    baseline_rows: list[Mapping[str, float | bool | None]],
    candidate_rows: list[Mapping[str, float | bool | None]],
    leakage_audit_passed: bool,
    holdout_fraction: float = 0.15,
    locked_holdout_fraction: float = 0.15,
    ranking_metrics: tuple[str, ...] = (
        "top3_capture_at5",
        "ndcg_at5",
        "competitive_recall_at5",
    ),
    cohort_regressions: tuple[str, ...] = (),
) -> EvaluationInput:
    """Build paired evidence on one immutable whole-date terminal split."""
    if not (len(dates) == len(baseline_rows) == len(candidate_rows)):
        raise ValueError("dates/baseline/candidate race counts must match")
    unique_dates = sorted(set(dates))
    holdout_count = max(1, math.ceil(len(unique_dates) * holdout_fraction))
    holdout_dates = set(unique_dates[-holdout_count:])
    development = [index for index, day in enumerate(dates) if day not in holdout_dates]
    terminal = [index for index, day in enumerate(dates) if day in holdout_dates]
    sample_hash = hashlib.sha256(
        json.dumps(
            {"dates": dates, "development": development, "terminal": terminal},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    def metric(name: str) -> MetricEvidence:
        return _paired_metric_evidence(
            [row.get(name) for row in baseline_rows],
            [row.get(name) for row in candidate_rows],
            development,
            terminal,
            higher_is_better=METRIC_DIRECTIONS[name],
        )

    primary = {name: metric(name) for name in PRIMARY_KEYS[domain]}
    ranking = {name: metric(name) for name in ranking_metrics}
    return EvaluationInput(
        domain=domain,
        baseline_sample_hash=sample_hash,
        candidate_sample_hash=sample_hash,
        baseline_races=len(baseline_rows),
        candidate_races=len(candidate_rows),
        holdout_locked=math.isclose(holdout_fraction, locked_holdout_fraction),
        leakage_audit_passed=leakage_audit_passed,
        primary=primary,
        ranking=ranking,
        cohort_regressions=cohort_regressions,
    )


def _fail(reason: str, *, detail: Mapping[str, object] | None = None) -> dict:
    return {
        "verdict": CandidateVerdict.REJECT.value,
        "reason": reason,
        "detail": dict(detail or {}),
    }


def evaluate_candidate(candidate: EvaluationInput) -> dict:
    """Apply the immutable Stage 4 decision order without touching model code.

    PRIMARY_WIN requires statistically supported Gold or positional-Good gain.
    RANKING_WIN keeps both primary KPIs non-negative and needs two independent,
    predeclared ranking signals, at least one with a positive terminal paired CI.
    """
    domain = candidate.domain.strip().lower()
    if domain not in PRIMARY_KEYS:
        return _fail("unsupported_domain", detail={"domain": candidate.domain})
    if candidate.baseline_sample_hash != candidate.candidate_sample_hash:
        return _fail("sample_hash_changed")
    if candidate.baseline_races != candidate.candidate_races:
        return _fail("race_count_changed")
    if not candidate.holdout_locked:
        return _fail("holdout_not_locked")
    if not candidate.leakage_audit_passed:
        return _fail("leakage_audit_failed")
    if candidate.cohort_regressions:
        return _fail(
            "cohort_regression",
            detail={"cohorts": list(candidate.cohort_regressions)},
        )

    primary_keys = PRIMARY_KEYS[domain]
    missing_primary = [key for key in primary_keys if key not in candidate.primary]
    if missing_primary:
        return _fail("missing_primary_evidence", detail={"metrics": missing_primary})
    primary = {key: candidate.primary[key].favourable() for key in primary_keys}
    regressions = [
        key
        for key, item in primary.items()
        if item.development_delta < 0 or item.terminal_delta < 0
    ]
    if regressions:
        return _fail("primary_regression", detail={"metrics": regressions})

    primary_winners = [
        key
        for key, item in primary.items()
        if item.development_delta > 0
        and item.terminal_delta > 0
        and item.terminal_ci_low > 0
    ]
    if primary_winners:
        return {
            "verdict": CandidateVerdict.PRIMARY_WIN.value,
            "reason": "gold_or_good_supported_gain",
            "detail": {"winning_metrics": primary_winners},
        }

    unknown_ranking = sorted(set(candidate.ranking).difference(RANKING_KEYS))
    if unknown_ranking:
        return _fail(
            "unregistered_ranking_metric",
            detail={"metrics": unknown_ranking},
        )
    if len(candidate.ranking) < 2:
        return _fail("insufficient_ranking_metrics")

    ranking = {key: item.favourable() for key, item in candidate.ranking.items()}
    strongly_harmful = [
        key for key, item in ranking.items() if item.terminal_ci_high < 0
    ]
    if strongly_harmful:
        return _fail(
            "ranking_metric_harm",
            detail={"metrics": strongly_harmful},
        )
    positive = [
        key
        for key, item in ranking.items()
        if item.development_delta > 0 and item.terminal_delta > 0
    ]
    supported = [key for key in positive if ranking[key].terminal_ci_low > 0]
    nonnegative = [
        key
        for key, item in ranking.items()
        if item.development_delta >= 0 and item.terminal_delta >= 0
    ]
    if len(positive) >= 2 and supported and len(nonnegative) >= 2:
        return {
            "verdict": CandidateVerdict.RANKING_WIN.value,
            "reason": "primary_neutral_ranking_supported_gain",
            "detail": {
                "positive_metrics": positive,
                "ci_supported_metrics": supported,
            },
        }
    return _fail(
        "ranking_evidence_too_weak",
        detail={
            "positive_metrics": positive,
            "ci_supported_metrics": supported,
            "nonnegative_metrics": nonnegative,
        },
    )
