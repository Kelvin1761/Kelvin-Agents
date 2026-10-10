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


# ═══════════════════════════════════════════════════════════════════════════
# Stage 4 v3 (2026-10-10): judge on the full record, not on a 15% tail.
#
# v2 judged every candidate on one locked terminal tail (~50–60 HKJC races).
# That wasted 85% of the evidence, the tail had been opened many times, and a
# chronological tail is also a season/condition split. v3 separates two kinds of
# candidate:
#
#   fixed_rule        nothing was learned from the data (correctness fixes,
#                     pre-registered constants, restoring a documented design).
#                     There is no in-sample optimism, so every race counts.
#   walk_forward_oos  values were fitted from data; the producer MUST supply
#                     predictions where each meeting was scored by a fit that
#                     only saw earlier meetings. Then every race is out of sample.
#
# Anything fitted without walk-forward predictions is refused outright — judging
# a fitted change on the data it was fitted to is the bias v3 exists to prevent.
# Inference resamples whole meeting days (races on one day share going, bias and
# the same scheduled run), and every primary metric must hold in most of K
# contiguous time blocks so one hot season cannot carry a verdict.
# ═══════════════════════════════════════════════════════════════════════════

V3_MODES = ("fixed_rule", "walk_forward_oos")


@dataclass(frozen=True)
class FullRecordEvidence:
    delta: float
    ci_low: float
    ci_high: float
    p_value: float
    block_deltas: tuple[float, ...]
    higher_is_better: bool = True

    def favourable(self) -> "FullRecordEvidence":
        if self.higher_is_better:
            return self
        return FullRecordEvidence(
            delta=-self.delta,
            ci_low=-self.ci_high,
            ci_high=-self.ci_low,
            p_value=self.p_value,
            block_deltas=tuple(-value for value in self.block_deltas),
            higher_is_better=True,
        )

    def blocks_nonnegative(self) -> int:
        return sum(1 for value in self.favourable().block_deltas if value >= 0)


def _full_record_metric(
    baseline: list[float | None],
    candidate: list[float | None],
    dates: list[str],
    *,
    higher_is_better: bool,
    blocks: int,
    bootstrap: int,
    seed: int,
) -> FullRecordEvidence:
    by_day: dict[str, list[float]] = {}
    for base, cand, day in zip(baseline, candidate, dates):
        if base is None or cand is None:
            continue
        by_day.setdefault(day, []).append(float(cand) - float(base))
    days = sorted(by_day)
    all_deltas = [value for day in days for value in by_day[day]]
    delta = _mean(all_deltas)
    if not all_deltas or all(value == 0 for value in all_deltas):
        ci_low = ci_high = delta
        p_value = 1.0
    else:
        rng = random.Random(seed)
        samples = []
        for _ in range(bootstrap):
            picked = [by_day[days[rng.randrange(len(days))]] for _ in days]
            flat = [value for day in picked for value in day]
            samples.append(_mean(flat))
        samples.sort()
        ci_low = samples[max(0, math.floor(bootstrap * 0.025))]
        ci_high = samples[min(bootstrap - 1, math.ceil(bootstrap * 0.975) - 1)]
        below = sum(1 for value in samples if value <= 0) / bootstrap
        above = sum(1 for value in samples if value >= 0) / bootstrap
        p_value = min(1.0, 2 * min(below, above))
    size = max(1, math.ceil(len(days) / blocks))
    block_deltas = tuple(
        _mean([value for day in days[start:start + size] for value in by_day[day]])
        for start in range(0, len(days), size)
    )
    return FullRecordEvidence(delta, ci_low, ci_high, p_value, block_deltas, higher_is_better)


def evaluate_full_record(
    *,
    domain: str,
    mode: str,
    dates: list[str],
    baseline_rows: list[Mapping[str, float | bool | None]],
    candidate_rows: list[Mapping[str, float | bool | None]],
    leakage_audit_passed: bool,
    ranking_metrics: tuple[str, ...] = (
        "top3_capture_at5",
        "ndcg_at5",
        "competitive_recall_at5",
        "mean_top3_model_rank",
    ),
    blocks: int = 6,
    min_blocks_fraction: float = 2 / 3,
    bootstrap: int = 2000,
    seed: int = 7,
) -> dict:
    """Stage 4 v3 verdict on the full paired record (see module note above)."""
    domain = domain.strip().lower()
    if domain not in PRIMARY_KEYS:
        return _fail("unsupported_domain", detail={"domain": domain})
    if mode not in V3_MODES:
        return _fail("fitted_candidate_needs_walk_forward_predictions", detail={"mode": mode})
    if not (len(dates) == len(baseline_rows) == len(candidate_rows)):
        return _fail("race_count_changed")
    if not leakage_audit_passed:
        return _fail("leakage_audit_failed")
    unknown = sorted(set(ranking_metrics).difference(RANKING_KEYS))
    if unknown:
        return _fail("unregistered_ranking_metric", detail={"metrics": unknown})

    def evidence(name: str) -> FullRecordEvidence:
        return _full_record_metric(
            [row.get(name) for row in baseline_rows],
            [row.get(name) for row in candidate_rows],
            dates,
            higher_is_better=METRIC_DIRECTIONS[name],
            blocks=blocks,
            bootstrap=bootstrap,
            seed=seed,
        )

    primary = {name: evidence(name) for name in PRIMARY_KEYS[domain]}
    ranking = {name: evidence(name) for name in ranking_metrics}
    need = math.ceil(len(next(iter(primary.values())).block_deltas) * min_blocks_fraction)
    detail = {
        "mode": mode,
        "races": len(dates),
        "meeting_days": len(set(dates)),
        "blocks_required_nonnegative": need,
        "primary": {k: vars(v) for k, v in primary.items()},
        "ranking": {k: vars(v) for k, v in ranking.items()},
    }
    fav_primary = {k: v.favourable() for k, v in primary.items()}
    regressions = [
        key for key, item in fav_primary.items()
        if item.delta < 0 or item.blocks_nonnegative() < need
    ]
    if regressions:
        return {"verdict": CandidateVerdict.REJECT.value, "reason": "primary_regression",
                "detail": {**detail, "metrics": regressions}}
    winners = [key for key, item in fav_primary.items() if item.ci_low > 0]
    if winners:
        return {"verdict": CandidateVerdict.PRIMARY_WIN.value, "reason": "gold_or_good_supported_gain",
                "detail": {**detail, "winning_metrics": winners}}
    fav_ranking = {k: v.favourable() for k, v in ranking.items()}
    harmful = [key for key, item in fav_ranking.items() if item.ci_high < 0]
    if harmful:
        return {"verdict": CandidateVerdict.REJECT.value, "reason": "ranking_metric_harm",
                "detail": {**detail, "metrics": harmful}}
    positive = [key for key, item in fav_ranking.items()
                if item.delta > 0 and item.blocks_nonnegative() >= need]
    supported = [key for key in positive if fav_ranking[key].ci_low > 0]
    if len(positive) >= 2 and supported:
        return {"verdict": CandidateVerdict.RANKING_WIN.value,
                "reason": "primary_neutral_ranking_supported_gain",
                "detail": {**detail, "positive_metrics": positive, "ci_supported_metrics": supported}}
    return {"verdict": CandidateVerdict.REJECT.value, "reason": "ranking_evidence_too_weak",
            "detail": {**detail, "positive_metrics": positive, "ci_supported_metrics": supported}}


def holm_adjust(p_values: Mapping[str, float]) -> dict[str, float]:
    """Holm step-down adjusted p-values for one registered candidate family."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    m = len(ordered)
    adjusted: dict[str, float] = {}
    running = 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[name] = running
    return adjusted
