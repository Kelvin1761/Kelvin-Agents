"""Canonical seven-metric measurement after prediction, with labels held apart.

This accepts completed score rows, not raw model resources or caller metrics.
It grants no input/PIT, power, model or promotion authority.
"""
from __future__ import annotations

from collections import Counter
import math
from typing import Mapping

from shared_racing.eval_metrics import race_metrics, top3_pairwise_counts

from .contracts import Domain
from .research_registry import ExperimentSpec
from .research_safety import ResearchSafetyError


RACING_METRICS = frozenset({
    "gold", "good_positional", "top3_capture_at5", "mean_top3_model_rank",
    "competitive_recall_at5", "ndcg_at5", "top5_pairwise_auc",
})
RACING_RULERS = {Domain.AU: "au-v2", Domain.HKJC: "hkjc-v2"}


def racing_measurement_for(spec: ExperimentSpec):
    """Select only the existing frozen racing ruler and its complete metric set."""
    if (spec.domain not in RACING_RULERS
            or spec.evaluation_ruler_id != RACING_RULERS[spec.domain]
            or len(spec.preregistered_metrics) != len(RACING_METRICS)
            or set(spec.preregistered_metrics) != RACING_METRICS):
        raise ResearchSafetyError("canonical racing measurement requires the complete frozen v2 ruler")
    return measure_racing_prediction


def _entity_id(value):
    return isinstance(value, str) and bool(value.strip())


def validate_racing_outcome(label, entities: set[str]):
    """Validate an original or rotated complete outcome before model execution.

    Rotation stays exactly as registered. Cross-race identity or field mismatch
    is an incompatibility, never permission to remap, omit or invent runners.
    """
    if not isinstance(label, dict) or set(label) != {"positions", "withdrawn"}:
        raise ResearchSafetyError("complete racing outcome required")
    positions, withdrawn = label["positions"], label["withdrawn"]
    if (not isinstance(positions, dict) or not positions
            or not all(_entity_id(k) and type(v) is int and v > 0 for k, v in positions.items())
            or not isinstance(withdrawn, list) or not all(_entity_id(k) for k in withdrawn)
            or len(withdrawn) != len(set(withdrawn))):
        raise ResearchSafetyError("invalid finish positions or withdrawals")
    withdrawn = set(withdrawn)
    if (set(positions) & withdrawn) or (set(positions) | withdrawn) != entities:
        raise ResearchSafetyError("racing outcome identity or finish coverage mismatch")
    expected_place = 1
    for place, count in sorted(Counter(positions.values()).items()):
        if place != expected_place:
            raise ResearchSafetyError("incomplete or inconsistent official finish positions")
        expected_place += count
    if not any(v <= 3 for v in positions.values()) or not any(v > 3 for v in positions.values()):
        raise ResearchSafetyError("top-five pairwise metric has no comparable pairs")
    return positions, withdrawn


def measure_racing_prediction(prediction, label, context) -> dict:
    """Measure ordered score rows against complete, separately held outcomes.

    prediction: [{entity_id, score}, ...] in native ranking tie order.
    A domain adapter must preserve its native secondary tie breakers (including
    HKJC raw ability and horse number), not just raw input order. This kernel
    does not establish native HKJC scoring/ranking adapter parity.
    label: {positions: {entity_id: positive integer}, withdrawn: [entity_id, ...]}.
    The harness's existing context.prices keys bind the audited decision field;
    price values are unused. Explicit post-decision withdrawals are removed only
    here. Missing finishers, omitted runners and unmeasurable AUC block output.
    """
    if (not isinstance(context, Mapping) or not isinstance(context.get("prices"), Mapping)
            or not context["prices"] or not all(_entity_id(k) for k in context["prices"])):
        raise ResearchSafetyError("audited racing entity identities unavailable")
    entities = set(context["prices"])
    if not isinstance(prediction, list) or not prediction:
        raise ResearchSafetyError("completed racing score rows required")
    scores = {}
    for row in prediction:
        if not isinstance(row, dict) or set(row) != {"entity_id", "score"}:
            raise ResearchSafetyError("invalid completed racing prediction")
        identity, score = row["entity_id"], row["score"]
        if not _entity_id(identity) or identity in scores:
            raise ResearchSafetyError("duplicate or invalid predicted entity")
        try:
            finite = type(score) in {int, float} and math.isfinite(score)
        except OverflowError:
            finite = False
        if not finite:
            raise ResearchSafetyError("finite numeric racing score required")
        scores[identity] = score
    if set(scores) != entities:
        raise ResearchSafetyError("prediction differs from the audited racing field")
    positions, withdrawn = validate_racing_outcome(label, entities)
    rows = [(identity, score) for identity, score in scores.items() if identity not in withdrawn]
    picks = [identity for identity, score in sorted(rows, key=lambda r: -r[1])]
    pairs = top3_pairwise_counts([(score, positions[identity]) for identity, score in rows])
    if not pairs[1]:
        raise ResearchSafetyError("top-five pairwise metric has no comparable pairs")
    canonical = race_metrics(picks, {k for k, v in positions.items() if v <= 3},
                             actual_pos=positions, field_size=len(positions))
    metrics = {"gold": canonical["gold"], "good_positional": canonical["good_positional"],
        "top3_capture_at5": canonical["top3_capture_at5"],
        "mean_top3_model_rank": canonical["top3_mean_model_rank"],
        "competitive_recall_at5": canonical["competitive_recall_at5"],
        "ndcg_at5": canonical["ndcg_at5"], "top5_pairwise_auc": pairs[0] / pairs[1]}
    if any(value is None or not math.isfinite(value) for value in metrics.values()):
        raise ResearchSafetyError("canonical racing measurement unavailable")
    return metrics
