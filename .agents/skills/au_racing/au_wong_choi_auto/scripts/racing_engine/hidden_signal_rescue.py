from __future__ import annotations

from copy import deepcopy
from typing import Any


VARIANT_LABELS = {
    "v1_formline_merit": "V1 Formline Merit Rescue",
    "v2_trial_jt_comeback": "V2 Trial/JT Comeback Rescue",
    "v3_sectional_hardness_relief": "V3 Sectional Hardness Relief",
    "v4_combined_conservative": "V4 Combined Conservative Overlay",
}


def score_row(row: dict[str, Any]) -> float:
    return float(row.get("rank_score") or row.get("ability_score") or row.get("model_score") or 0.0)


def feature(row: dict[str, Any], key: str, default: float = 60.0) -> float:
    return _as_float((row.get("feature_scores") or {}).get(key), default)


def matrix(row: dict[str, Any], key: str, default: float = 60.0) -> float:
    return _as_float((row.get("matrix_scores") or {}).get(key), default)


def add_rank_metadata(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(deepcopy(rows), key=lambda row: (-score_row(row), int(row.get("horse_number") or 999)))
    for idx, row in enumerate(ranked, start=1):
        row["model_rank"] = idx
        row["shadow_score"] = score_row(row)
        row["hidden_signal_rescue_modifier"] = 0.0
        row["hidden_signal_reasons"] = []
        row["hidden_signal_variant"] = ""
    return ranked


def apply_hidden_signal_variant(
    race_rows: list[dict[str, Any]],
    variant: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    ranked = add_rank_metadata(race_rows)
    if len(ranked) < 4:
        return ranked, []
    top3_cutoff = score_row(ranked[2])
    candidates: list[dict[str, Any]] = []

    if variant == "v4_combined_conservative":
        for row in ranked:
            best = _best_component(row, top3_cutoff)
            if best:
                candidates.append(best)
        if candidates:
            chosen = sorted(
                candidates,
                key=lambda item: (
                    -float(item["modifier"]),
                    int(item["model_rank"]),
                    int(item["horse_number"]),
                ),
            )[0]
            _apply_modifier(ranked, chosen, "v4_combined_conservative")
            return _rank_shadow(ranked), [chosen]
        return ranked, []

    for row in ranked:
        item = _component_candidate(row, top3_cutoff, variant)
        if item:
            _apply_modifier(ranked, item, variant)
            candidates.append(item)
    return _rank_shadow(ranked), candidates


def apply_report_only_hidden_signal(race_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked, _candidates = apply_hidden_signal_variant(race_rows, "v4_combined_conservative")
    return ranked


def _best_component(row: dict[str, Any], top3_cutoff: float) -> dict[str, Any] | None:
    items = [
        _component_candidate(row, top3_cutoff, "v1_formline_merit"),
        _component_candidate(row, top3_cutoff, "v2_trial_jt_comeback"),
        _component_candidate(row, top3_cutoff, "v3_sectional_hardness_relief"),
    ]
    items = [item for item in items if item]
    if not items:
        return None
    best = sorted(items, key=lambda item: (-float(item["modifier"]), str(item["variant"])))[0]
    best["modifier"] = min(1.8, float(best["modifier"]))
    return best


def _component_candidate(row: dict[str, Any], top3_cutoff: float, variant: str) -> dict[str, Any] | None:
    rank = int(row.get("model_rank") or 999)
    gap = max(0.0, top3_cutoff - score_row(row))
    if rank <= 3:
        return None
    if _severe_sanity_risk(row):
        return None
    if variant == "v1_formline_merit":
        return _formline_merit_candidate(row, rank, gap)
    if variant == "v2_trial_jt_comeback":
        return _trial_jt_candidate(row, rank, gap)
    if variant == "v3_sectional_hardness_relief":
        return _sectional_relief_candidate(row, rank, gap)
    raise ValueError(f"Unknown hidden-signal rescue variant: {variant}")


def _formline_merit_candidate(row: dict[str, Any], rank: int, gap: float) -> dict[str, Any] | None:
    if not (4 <= rank <= 8 and gap <= 3.5):
        return None
    formline = feature(row, "formline_score")
    class_weight = matrix(row, "class_weight")
    rating = feature(row, "rating_score")
    confidence = feature(row, "confidence_score")
    form = feature(row, "form_score")
    strong_line = formline >= 75.0
    class_rating = class_weight >= 64.0 and rating >= 65.0
    balanced_hidden = formline >= 68.0 and class_weight >= 64.0 and confidence >= 80.0
    if not (strong_line or class_rating or balanced_hidden):
        return None

    modifier = 0.45
    modifier += max(0.0, formline - 70.0) * 0.035
    modifier += max(0.0, class_weight - 62.0) * 0.030
    modifier += max(0.0, rating - 64.0) * 0.020
    modifier += max(0.0, confidence - 80.0) * 0.012
    if form < 45.0 and formline >= 75.0:
        modifier += 0.18
    reasons = []
    if strong_line:
        reasons.append("strong_formline_hidden_merit")
    if class_rating:
        reasons.append("class_rating_support")
    if balanced_hidden:
        reasons.append("balanced_formline_class_confidence")
    if form < 50.0:
        reasons.append("recent_form_not_hard_block")
    return _candidate(row, "v1_formline_merit", min(1.55, modifier), reasons, gap)


def _trial_jt_candidate(row: dict[str, Any], rank: int, gap: float) -> dict[str, Any] | None:
    if not (4 <= rank <= 12 and gap <= 5.0):
        return None
    trial = feature(row, "trial_score")
    jt = matrix(row, "jockey_trainer")
    jockey = feature(row, "jockey_score")
    trainer = feature(row, "trainer_score")
    fit = feature(row, "jockey_horse_fit_score")
    confidence = feature(row, "confidence_score")
    if trial < 75.0:
        return None
    support_count = sum(
        (
            jt >= 64.0,
            jockey >= 66.0,
            trainer >= 66.0,
            fit >= 64.0,
            confidence >= 80.0,
        )
    )
    if support_count < 1:
        return None
    modifier = 0.50 + max(0.0, trial - 75.0) * 0.035 + support_count * 0.16
    modifier += max(0.0, jt - 64.0) * 0.018
    reasons = ["strong_trial_signal"]
    if jt >= 64.0:
        reasons.append("jt_matrix_support")
    if jockey >= 66.0:
        reasons.append("jockey_support")
    if trainer >= 66.0:
        reasons.append("trainer_support")
    if fit >= 64.0:
        reasons.append("jockey_horse_fit_support")
    if feature(row, "form_score") < 50.0:
        reasons.append("recent_form_not_hard_block")
    return _candidate(row, "v2_trial_jt_comeback", min(1.50, modifier), reasons, gap)


def _sectional_relief_candidate(row: dict[str, Any], rank: int, gap: float) -> dict[str, Any] | None:
    if not (4 <= rank <= 12 and gap <= 5.0):
        return None
    sectional_feature = feature(row, "sectional_score")
    sectional_matrix = matrix(row, "sectional")
    if not (sectional_feature < 45.0 or sectional_matrix < 55.0):
        return None
    support_checks = {
        "trial_support": feature(row, "trial_score") >= 72.0,
        "formline_support": feature(row, "formline_score") >= 70.0,
        "class_support": matrix(row, "class_weight") >= 63.0,
        "track_support": matrix(row, "track") >= 66.0,
        "confidence_support": feature(row, "confidence_score") >= 82.0,
        "rating_support": feature(row, "rating_score") >= 64.0,
        "distance_ok": feature(row, "distance_score") >= 60.0,
        "jt_support": matrix(row, "jockey_trainer") >= 64.0,
    }
    reasons = [name for name, ok in support_checks.items() if ok]
    if len(reasons) < 3:
        return None
    modifier = 0.42 + min(4, len(reasons)) * 0.20
    if sectional_feature < 40.0:
        modifier += 0.10
    reasons.insert(0, "sectional_low_score_relief")
    return _candidate(row, "v3_sectional_hardness_relief", min(1.25, modifier), reasons, gap)


def _candidate(
    row: dict[str, Any],
    variant: str,
    modifier: float,
    reasons: list[str],
    gap: float,
) -> dict[str, Any]:
    return {
        "variant": variant,
        "horse_number": int(row.get("horse_number") or 0),
        "horse_name": str(row.get("horse_name") or ""),
        "model_rank": int(row.get("model_rank") or 999),
        "base_score": round(score_row(row), 4),
        "modifier": round(max(0.0, modifier), 4),
        "shadow_score": round(score_row(row) + max(0.0, modifier), 4),
        "gap_to_top3": round(gap, 4),
        "reasons": reasons,
    }


def _apply_modifier(ranked: list[dict[str, Any]], item: dict[str, Any], variant: str) -> None:
    horse_no = int(item["horse_number"])
    for row in ranked:
        if int(row.get("horse_number") or 0) != horse_no:
            continue
        modifier = float(item["modifier"])
        row["hidden_signal_rescue_modifier"] = round(modifier, 4)
        row["hidden_signal_reasons"] = list(item["reasons"])
        row["hidden_signal_variant"] = variant
        row["shadow_score"] = round(score_row(row) + modifier, 4)
        break


def _rank_shadow(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=lambda row: (-float(row.get("shadow_score", score_row(row))), int(row.get("horse_number") or 999)))
    for idx, row in enumerate(ranked, start=1):
        row["shadow_rank"] = idx
    return ranked


def _severe_sanity_risk(row: dict[str, Any]) -> bool:
    confidence = feature(row, "confidence_score")
    health = feature(row, "health_score")
    if confidence < 55.0 or health < 48.0:
        return True
    risk_flags = set(row.get("risk_flags") or [])
    if "high_consumption_load" in risk_flags and matrix(row, "race_shape") < 56.0:
        return True
    return False


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default
