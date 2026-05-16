from __future__ import annotations


def should_use_named_jt_ratings(race_context: dict) -> bool:
    field_summary = race_context.get("field_summary") or {}
    field_count = int(field_summary.get("count", 0) or 0)
    return field_count >= 13


def jt_sample_size_rank_cap(
    matrix_scores: dict,
    current_formal_rides: int,
    current_trial_rides: int,
    best_formal_rides: int,
    latest_official_rides: int,
    combo_runs: int,
    trainer_runs: int,
) -> float:
    jt_score = float(matrix_scores.get("jockey_trainer", 60))
    if jt_score < 70:
        return 0.0

    weak_count = 0
    if current_formal_rides == 0:
        weak_count += 1
    if current_trial_rides == 0:
        weak_count += 1
    if combo_runs < 5:
        weak_count += 1
    if trainer_runs < 10:
        weak_count += 1
    if best_formal_rides == 0 and latest_official_rides == 0:
        weak_count += 1

    if jt_score >= 76 and weak_count >= 4:
        return -3.2
    if jt_score >= 72 and weak_count >= 3:
        return -2.0
    if jt_score >= 70 and weak_count >= 2 and combo_runs == 0 and current_formal_rides == 0:
        return -1.0
    return 0.0


def narrow_overrated_rank_shield(matrix_scores: dict, wet_state: str, field_count: int) -> float:
    if wet_state in {"soft56", "soft7plus", "heavy"}:
        return 0.0
    if field_count < 8:
        return 0.0

    stability = float(matrix_scores.get("stability", 60))
    form_line = float(matrix_scores.get("form_line", 60))
    race_shape = float(matrix_scores.get("race_shape", 60))
    track = float(matrix_scores.get("track", 60))
    class_weight = float(matrix_scores.get("class_weight", 60))
    sectional = float(matrix_scores.get("sectional", 60))
    jockey_trainer = float(matrix_scores.get("jockey_trainer", 60))

    low_scores = (race_shape, track, class_weight)
    low_flags = sum(score < 63 for score in low_scores)
    very_low_flags = sum(score < 60 for score in low_scores)

    penalty = 0.0
    if stability >= 78 and form_line >= 76 and low_flags >= 2 and sectional < 67:
        penalty -= 1.4
    elif stability >= 75 and form_line >= 74 and low_flags >= 2 and sectional < 65:
        penalty -= 0.8

    if penalty < 0 and very_low_flags >= 2:
        penalty -= 0.4
    if penalty < 0 and jockey_trainer >= 72:
        penalty += 0.3
    return penalty
