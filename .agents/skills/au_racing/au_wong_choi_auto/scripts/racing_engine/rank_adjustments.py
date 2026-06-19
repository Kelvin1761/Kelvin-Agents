from __future__ import annotations

import re


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


def market_free_rank_adjustment(
    matrix_scores: dict,
    field_count: int,
    going: str,
    race_class_raw: str,
) -> float:
    def centered(v):
        try:
            return (float(v) - 60.0) / 10.0
        except (TypeError, ValueError):
            return 0.0

    stability = centered(matrix_scores.get("stability", 60.0))
    race_shape = centered(matrix_scores.get("race_shape", 60.0))
    jockey_trainer = centered(matrix_scores.get("jockey_trainer", 60.0))
    class_weight = centered(matrix_scores.get("class_weight", 60.0))
    track = centered(matrix_scores.get("track", 60.0))
    form_line = centered(matrix_scores.get("form_line", 60.0))
    sectional = centered(matrix_scores.get("sectional", 60.0))

    # Field size bucket
    field = "Field <=8"
    if field_count >= 13:
        field = "Field 13+"
    elif field_count >= 9:
        field = "Field 9-12"

    # Going bucket
    going_val = str(going or "").strip().lower()
    condition = "Other"
    if going_val.startswith(("good", "firm")):
        condition = "Good/Firm"
    elif going_val.startswith("soft"):
        condition = "Soft"
    elif going_val.startswith("heavy"):
        condition = "Heavy"

    # Race Class bucket
    class_val = str(race_class_raw or "").lower()
    race_class = "Other"
    if "group 1" in class_val:
        race_class = "Group 1"
    elif "group 2" in class_val or "group 3" in class_val:
        race_class = "Group 2/3"
    elif "listed" in class_val:
        race_class = "Listed"
    elif "maiden" in class_val:
        race_class = "Maiden"
    elif "bm" in class_val:
        match = re.search(r"-?\d+", class_val)
        rating = int(match.group(0)) if match else 0
        if rating >= 88:
            race_class = "BM88+"
        elif rating >= 72:
            race_class = "BM72-84"
        else:
            race_class = "BM58-70"

    # Interaction terms
    field13_race_shape = race_shape if field == "Field 13+" else 0.0
    field13_sectional = sectional if field == "Field 13+" else 0.0
    field13_form_line = form_line if field == "Field 13+" else 0.0
    field912_form_line = form_line if field == "Field 9-12" else 0.0
    field912_stability = stability if field == "Field 9-12" else 0.0
    bm_class_weight = class_weight if race_class in {"BM58-70", "BM72-84", "BM88+"} else 0.0
    wet_track = track if condition in {"Soft", "Heavy"} else 0.0
    wet_stability = stability if condition in {"Soft", "Heavy"} else 0.0
    # False Positive Traps (Empty Form & Class Exposed)
    # Using centered values: 70 -> 1.0, 65 -> 0.5, 60 -> 0.0
    empty_form_trap = stability if (stability >= 1.0 and class_weight < 0.5 and race_shape < 0.5) else 0.0
    class_exposed = class_weight if (stability >= 1.0 and class_weight < 0.0) else 0.0

    # Calculate adjustment delta.
    delta_v1 = (
        - 0.35 * stability
        - 0.33 * sectional
        - 0.19 * race_shape
        + 0.31 * jockey_trainer
        + 0.06 * class_weight
        - 0.64 * track
        - 0.77 * form_line
        + 0.06 * field13_race_shape
        + 0.48 * field13_sectional
        + 1.01 * field13_form_line
        - 0.03 * field912_form_line
        - 0.74 * field912_stability
        - 0.97 * bm_class_weight
        - 1.12 * wet_track
        + 0.01 * wet_stability
        + 0.54 * empty_form_trap
        + 0.49 * class_exposed
    )

    delta_v2 = (
        - 0.36 * stability
        - 0.30 * sectional
        + 0.42 * race_shape
        - 0.12 * jockey_trainer
        + 0.20 * class_weight
        + 0.21 * track
        - 0.15 * form_line
        + 0.29 * field13_race_shape
        - 0.58 * field13_form_line
        - 0.49 * field912_form_line
        - 0.52 * field912_stability
        + 0.32 * bm_class_weight
        + 0.29 * wet_track
        - 0.36 * wet_stability
    )

    return max(-3.5, min(3.5, delta_v1)) + max(-3.5, min(3.5, delta_v2))

