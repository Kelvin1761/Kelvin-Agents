#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
AUTO_SCRIPT_DIR = PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"
sys.path.append(str(AUTO_SCRIPT_DIR))
sys.path.append(str(AUTO_SCRIPT_DIR / "racing_engine"))

from matrix_mapper import MATRIX_FORMULAS  # noqa: E402
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402


ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
RESULTS_CSV = ARCHIVE_ROOT / "AU_Historical_Raw_Race_Results.csv"
OUTPUT_MD = ARCHIVE_ROOT / "AU_ML_Matrix_Diagnostics.md"

MATRIX_KEYS = tuple(MATRIX_FORMULAS.keys())
FEATURE_KEYS = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "rating_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "health_score",
    "confidence_score",
)
BM_BUCKETS = {"BM58-70", "BM72-84", "BM88+"}
RACECARD_HORSE_RE = re.compile(r"^\d+\.\s+(.+?)\s+\((\d+)\)$")
RACECARD_META_RE = re.compile(
    r"^Trainer:\s.*?\|\sJockey:\s.*?\|\sWeight:\s*([0-9.]+)\s*\|\sAge:\s.*?\|\sRating:\s*([0-9.]+)"
)


def parse_int(value, default=None):
    match = re.search(r"-?\d+", str(value or ""))
    return int(match.group(0)) if match else default


def parse_float(value, default=None):
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else default


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def normalize_horse_name(name: str) -> str:
    clean = re.sub(r"\s*\([^)]*\)", "", str(name or ""))
    return slug(clean)


def normalize_track_name(name: str) -> str:
    clean = str(name or "").strip().lower()
    clean = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", clean)
    clean = re.sub(r"\s+race\s+\d+(?:-\d+)?$", "", clean)
    clean = clean.replace(" gardens", "")
    clean = clean.replace(" heath", "")
    clean = clean.replace(" lakeside", "")
    clean = clean.replace(" hillside", "")
    return slug(clean)


def choose_track_rows(rows: list[dict], meeting_track: str) -> list[dict]:
    target_slug = normalize_track_name(meeting_track)
    exact = [row for row in rows if row["track_slug"] == target_slug]
    if exact:
        return exact
    loose = [row for row in rows if row["track_slug"] in target_slug or target_slug in row["track_slug"]]
    return loose or rows


def field_bucket(field_count: int) -> str:
    if field_count >= 13:
        return "Field 13+"
    if field_count >= 9:
        return "Field 9-12"
    return "Field 1-8"


def condition_bucket(going: str) -> str:
    text = str(going or "").strip().lower()
    if text.startswith(("good", "firm")):
        return "Good/Firm"
    if text.startswith("soft"):
        return "Soft"
    if text.startswith("heavy"):
        return "Heavy"
    if any(token in text for token in ("synthetic", "poly", "all weather", "all-weather")):
        return "Synthetic"
    return "Other"


def race_class_bucket(race_class: str) -> str:
    text = str(race_class or "").strip().upper()
    if not text:
        return "Unknown"
    if "BM" in text:
        digits = parse_int(text, 0) or 0
        if digits <= 70:
            return "BM58-70"
        if digits <= 84:
            return "BM72-84"
        return "BM88+"
    if any(token in text for token in ("MDN", "MAIDEN")):
        return "Maiden"
    if any(token in text for token in ("2YO", "2 Y O", "2-Y-O")):
        return "2YO"
    if any(token in text for token in ("GROUP", "G1", "G2", "G3", "LISTED", "LR")):
        return "Black-Type"
    return "Open/Other"


def load_historical_results() -> dict[tuple[str, int], list[dict]]:
    by_date_race: dict[tuple[str, int], list[dict]] = defaultdict(list)
    with RESULTS_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            race_no = parse_int(row.get("Race"))
            pos = parse_int(row.get("Pos"))
            if not race_no or not pos:
                continue
            record = {
                "date": str(row.get("Date") or "").strip(),
                "race": race_no,
                "track_slug": normalize_track_name(row.get("Track") or ""),
                "horse_slug": normalize_horse_name(row.get("Horse") or ""),
                "pos": pos,
                "condition": str(row.get("Condition") or "").strip(),
            }
            by_date_race[(record["date"], race_no)].append(record)
    return by_date_race


def map_matrix_scores(features: dict[str, float]) -> dict[str, float]:
    matrix_scores = {}
    for key, components in MATRIX_FORMULAS.items():
        score = sum(clip_score(features.get(name, 60.0)) * weight for name, weight in components)
        matrix_scores[key] = round(clip_score(score), 4)
    return matrix_scores


def load_racecard_profiles(meeting_dir: Path, race_no: int) -> dict[str, dict]:
    candidates = sorted(meeting_dir.glob(f"*Race {race_no} Racecard.md"))
    if not candidates:
        return {}
    lines = candidates[0].read_text(encoding="utf-8").splitlines()
    profiles = {}
    index = 0
    while index < len(lines):
        horse_match = RACECARD_HORSE_RE.match(lines[index].strip())
        if not horse_match or index + 1 >= len(lines):
            index += 1
            continue
        meta_match = RACECARD_META_RE.match(lines[index + 1].strip())
        if meta_match:
            horse_name = horse_match.group(1).strip()
            profiles[normalize_horse_name(horse_name)] = {
                "horse_rating": parse_float(meta_match.group(2)),
                "declared_weight": parse_float(meta_match.group(1)),
            }
        index += 2
    return profiles


def annotate_rating_context(horses: list[dict]) -> None:
    ratings = [float(horse["horse_rating"]) for horse in horses if horse.get("horse_rating") is not None]
    if not ratings:
        for horse in horses:
            horse["rating_z"] = 0.0
            horse["rating_rank_pct"] = 0.5
        return

    avg_rating = sum(ratings) / len(ratings)
    variance = sum((value - avg_rating) ** 2 for value in ratings) / len(ratings)
    stdev = variance ** 0.5
    denom = max(1, len(ratings) - 1)
    for horse in horses:
        rating = horse.get("horse_rating")
        if rating is None:
            horse["rating_z"] = 0.0
            horse["rating_rank_pct"] = 0.5
            continue
        rating = float(rating)
        higher = sum(1 for value in ratings if value > rating)
        equal = sum(1 for value in ratings if value == rating)
        average_rank = higher + max(0.0, (equal - 1) / 2.0)
        horse["rating_z"] = (rating - avg_rating) / stdev if stdev else 0.0
        horse["rating_rank_pct"] = 1.0 - (average_rank / denom)


def detect_meeting_track(meeting_dir: Path, sample_logic: dict) -> str:
    race_analysis = sample_logic.get("race_analysis", {})
    meeting = race_analysis.get("meeting_intelligence") or {}
    track_profile = race_analysis.get("track_profile") or {}
    for value in (
        meeting.get("venue"),
        track_profile.get("venue"),
        race_analysis.get("venue"),
    ):
        if value:
            return str(value).strip()
    name = re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting_dir.name)
    name = re.sub(r"\s+Race\s+\d+-\d+$", "", name)
    return name.strip()


def load_scoring_rows(scoring_path: Path) -> list[dict]:
    rows = []
    with scoring_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            horse_number = parse_int(row.get("horse_number"))
            if horse_number is None:
                continue
            feature_scores = {}
            for key in FEATURE_KEYS:
                value = parse_float(row.get(key), 60.0)
                feature_scores[key] = float(value if value is not None else 60.0)
            rows.append(
                {
                    "horse_number": horse_number,
                    "horse_name": str(row.get("horse_name") or "").strip(),
                    "horse_slug": normalize_horse_name(row.get("horse_name") or ""),
                    "ability_score": float(parse_float(row.get("ability_score"), 0.0) or 0.0),
                    "rank_score": float(parse_float(row.get("rank_score"), 0.0) or 0.0),
                    "feature_scores": feature_scores,
                    "matrix_scores": map_matrix_scores(feature_scores),
                }
            )
    return rows


def load_races() -> list[dict]:
    historical_results = load_historical_results()
    races = []
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        scoring_files = sorted(
            meeting_dir.glob("Race_*_Auto_Scoring.csv"),
            key=lambda path: parse_int(path.stem.split("_")[1], 999),
        )
        if not scoring_files:
            continue
        sample_logic_path = meeting_dir / "Race_1_Logic.json"
        logic_paths = sorted(meeting_dir.glob("Race_*_Logic.json"))
        sample_logic = {}
        if sample_logic_path.exists():
            sample_logic = json.loads(sample_logic_path.read_text(encoding="utf-8"))
        elif logic_paths:
            sample_logic = json.loads(logic_paths[0].read_text(encoding="utf-8"))
        meeting_date = meeting_dir.name[:10]
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        for scoring_path in scoring_files:
            race_no = parse_int(scoring_path.stem.split("_")[1])
            if race_no is None:
                continue
            racecard_profiles = load_racecard_profiles(meeting_dir, race_no)
            results_rows = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not results_rows:
                continue
            result_lookup = {row["horse_slug"]: row for row in results_rows}
            logic_path = meeting_dir / f"Race_{race_no}_Logic.json"
            race_class = ""
            going = ""
            if logic_path.exists():
                logic = json.loads(logic_path.read_text(encoding="utf-8"))
                race_analysis = logic.get("race_analysis", {})
                race_class = str(race_analysis.get("race_class") or "").strip()
                going = str(race_analysis.get("going") or "").strip()
            horses = []
            for row in load_scoring_rows(scoring_path):
                result_row = result_lookup.get(row["horse_slug"])
                if not result_row:
                    continue
                racecard_profile = racecard_profiles.get(row["horse_slug"], {})
                row["actual_pos"] = int(result_row["pos"])
                row["horse_rating"] = parse_float(racecard_profile.get("horse_rating"))
                row["declared_weight"] = parse_float(racecard_profile.get("declared_weight"))
                horses.append(row)
            if len(horses) < 4:
                continue
            annotate_rating_context(horses)
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "date": meeting_date,
                    "race_no": race_no,
                    "track": meeting_track,
                    "race_class": race_class,
                    "race_class_bucket": race_class_bucket(race_class),
                    "going": going or (results_rows[0]["condition"] if results_rows else ""),
                    "condition_bucket": condition_bucket(going or (results_rows[0]["condition"] if results_rows else "")),
                    "field_count": len(horses),
                    "field_bucket": field_bucket(len(horses)),
                    "horses": horses,
                }
            )
    return races


def new_bucket() -> dict:
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "minimum": 0,
        "winner_in_top3": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": {0: 0, 1: 0, 2: 0, 3: 0},
    }


def summarize_bucket(bucket: dict) -> dict:
    races = bucket["races"] or 1
    slots = bucket["top3_slots"] or 1
    return {
        "races": bucket["races"],
        "champion_rate": bucket["champion"] / races,
        "gold_rate": bucket["gold"] / races,
        "good_rate": bucket["good"] / races,
        "pass_rate": bucket["minimum"] / races,
        "winner_in_top3_rate": bucket["winner_in_top3"] / races,
        "top3_place_precision": bucket["top3_places"] / slots,
        "zero_hit_rate": bucket["hit_distribution"][0] / races,
        "one_hit_rate": bucket["hit_distribution"][1] / races,
    }


def evaluate_races(races: list[dict], score_builder) -> dict:
    bucket = new_bucket()
    for race in races:
        scored = []
        for horse in race["horses"]:
            scored.append(
                {
                    "horse_number": horse["horse_number"],
                    "actual_pos": horse["actual_pos"],
                    "score": float(score_builder(race, horse)),
                }
            )
        ranked = sorted(scored, key=lambda row: (-row["score"], row["horse_number"]))
        top3 = ranked[:3]
        top2 = ranked[:2]
        hits_top3 = sum(1 for horse in top3 if horse["actual_pos"] <= 3)
        hits_top2 = sum(1 for horse in top2 if horse["actual_pos"] <= 3)
        bucket["races"] += 1
        bucket["top3_places"] += hits_top3
        bucket["top3_slots"] += 3
        bucket["hit_distribution"][hits_top3] += 1
        if ranked[0]["actual_pos"] == 1:
            bucket["champion"] += 1
        if any(horse["actual_pos"] == 1 for horse in top3):
            bucket["winner_in_top3"] += 1
        if hits_top3 == 3:
            bucket["gold"] += 1
        if hits_top2 == 2:
            bucket["good"] += 1
        if hits_top3 >= 2:
            bucket["minimum"] += 1
    return bucket


def objective(bucket: dict) -> float:
    summary = summarize_bucket(bucket)
    return (
        summary["pass_rate"] * 3.0
        + summary["good_rate"] * 1.5
        + summary["gold_rate"] * 0.9
        + summary["top3_place_precision"] * 1.4
        + summary["winner_in_top3_rate"] * 0.7
        - summary["zero_hit_rate"] * 2.2
    )


def random_weight_vector(keys: tuple[str, ...], rng: random.Random) -> dict[str, float]:
    raw = {key: rng.uniform(0.01, 1.0) for key in keys}
    total = sum(raw.values()) or 1.0
    return {key: raw[key] / total for key in keys}


def build_weighted_score(weights: dict[str, float]):
    def score_builder(_race: dict, horse: dict) -> float:
        candidate_ability = sum(horse["matrix_scores"][key] * weights[key] for key in MATRIX_KEYS)
        return horse["rank_score"] + (candidate_ability - horse["ability_score"])

    return score_builder


def build_section_override_score(section: str, component_weights: dict[str, float]):
    live_weight = float(MATRIX_WEIGHTS.get(section, 0.0))
    components = tuple(component_weights.items())

    def score_builder(_race: dict, horse: dict) -> float:
        features = horse["feature_scores"]
        replacement = sum(clip_score(features.get(name, 60.0)) * weight for name, weight in components)
        replacement = clip_score(replacement)
        live_section = horse["matrix_scores"][section]
        return horse["rank_score"] + (replacement - live_section) * live_weight

    return score_builder


def search_global_weights(train_races: list[dict], valid_races: list[dict], iterations: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    rows = []
    for _ in range(iterations):
        weights = random_weight_vector(MATRIX_KEYS, rng)
        train_bucket = evaluate_races(train_races, build_weighted_score(weights))
        valid_bucket = evaluate_races(valid_races, build_weighted_score(weights))
        rows.append(
            {
                "weights": weights,
                "train": summarize_bucket(train_bucket),
                "valid": summarize_bucket(valid_bucket),
                "train_score": objective(train_bucket),
                "valid_score": objective(valid_bucket),
            }
        )
    rows.sort(
        key=lambda row: (
            row["valid"]["pass_rate"],
            row["valid"]["good_rate"],
            row["valid"]["top3_place_precision"],
            -row["valid"]["zero_hit_rate"],
            row["valid_score"],
        ),
        reverse=True,
    )
    return rows[:10]


def random_simplex(components: tuple[str, ...], rng: random.Random) -> dict[str, float]:
    raw = {name: rng.uniform(0.01, 1.0) for name in components}
    total = sum(raw.values()) or 1.0
    return {name: raw[name] / total for name in components}


def search_section_formulas(train_races: list[dict], valid_races: list[dict], iterations: int, seed: int) -> dict[str, dict]:
    rng = random.Random(seed)
    best_rows = {}
    for section, formula in MATRIX_FORMULAS.items():
        component_names = tuple(name for name, _ in formula)
        live_weights = {name: weight for name, weight in formula}
        live_valid = summarize_bucket(evaluate_races(valid_races, build_section_override_score(section, live_weights)))
        best = {
            "component_weights": live_weights,
            "train": summarize_bucket(evaluate_races(train_races, build_section_override_score(section, live_weights))),
            "valid": live_valid,
            "train_score": objective(evaluate_races(train_races, build_section_override_score(section, live_weights))),
            "valid_score": objective(evaluate_races(valid_races, build_section_override_score(section, live_weights))),
            "is_live": True,
        }
        for _ in range(iterations):
            candidate = random_simplex(component_names, rng)
            train_bucket = evaluate_races(train_races, build_section_override_score(section, candidate))
            valid_bucket = evaluate_races(valid_races, build_section_override_score(section, candidate))
            candidate_row = {
                "component_weights": candidate,
                "train": summarize_bucket(train_bucket),
                "valid": summarize_bucket(valid_bucket),
                "train_score": objective(train_bucket),
                "valid_score": objective(valid_bucket),
                "is_live": False,
            }
            if (
                candidate_row["valid"]["pass_rate"],
                candidate_row["valid"]["good_rate"],
                candidate_row["valid"]["top3_place_precision"],
                -candidate_row["valid"]["zero_hit_rate"],
                candidate_row["valid_score"],
            ) > (
                best["valid"]["pass_rate"],
                best["valid"]["good_rate"],
                best["valid"]["top3_place_precision"],
                -best["valid"]["zero_hit_rate"],
                best["valid_score"],
            ):
                best = candidate_row
        best_rows[section] = best
    return best_rows


def section_univariate_report(races: list[dict]) -> list[dict]:
    rows = []
    for section, formula in MATRIX_FORMULAS.items():
        combo_bucket = evaluate_races(races, lambda _race, horse, key=section: horse["matrix_scores"][key])
        rows.append(
            {
                "section": section,
                "variant": "matrix_combo",
                "summary": summarize_bucket(combo_bucket),
            }
        )
        for feature_name, _weight in formula:
            feature_bucket = evaluate_races(
                races,
                lambda _race, horse, key=feature_name: horse["feature_scores"][key],
            )
            rows.append(
                {
                    "section": section,
                    "variant": feature_name,
                    "summary": summarize_bucket(feature_bucket),
                }
            )
    rows.sort(
        key=lambda row: (
            row["summary"]["pass_rate"],
            row["summary"]["good_rate"],
            row["summary"]["top3_place_precision"],
        ),
        reverse=True,
    )
    return rows


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def fmt_weights(weights: dict[str, float]) -> str:
    return ", ".join(f"{key} {value:.3f}" for key, value in weights.items())


def chron_split(races: list[dict], ratio: float) -> tuple[list[dict], list[dict]]:
    ordered = sorted(races, key=lambda row: (row["date"], row["meeting"], row["race_no"]))
    split_at = max(1, int(len(ordered) * ratio))
    split_at = min(split_at, len(ordered) - 1)
    return ordered[:split_at], ordered[split_at:]


def rating_signal_score(horse: dict, z_scale: float, rank_scale: float) -> float:
    rating = horse.get("horse_rating")
    if rating is None:
        return 60.0
    z_value = max(-2.5, min(2.5, float(horse.get("rating_z", 0.0))))
    rank_pct = max(0.0, min(1.0, float(horse.get("rating_rank_pct", 0.5))))
    return clip_score(60.0 + z_value * z_scale + ((rank_pct - 0.5) * 2.0 * rank_scale))


def build_rating_shadow_score(variant: dict):
    live_weight = float(MATRIX_WEIGHTS.get("class_weight", 0.0))
    class_share = float(variant["class_share"])
    rating_share = float(variant["rating_share"])
    weight_share = float(variant["weight_share"])
    z_scale = float(variant["z_scale"])
    rank_scale = float(variant["rank_scale"])
    section_scale = float(variant["section_scale"])
    bm_scale = float(variant["bm_scale"])

    def score_builder(race: dict, horse: dict) -> float:
        rating_score = rating_signal_score(horse, z_scale, rank_scale)
        replacement = (
            clip_score(horse["feature_scores"].get("class_score", 60.0)) * class_share
            + rating_score * rating_share
            + clip_score(horse["feature_scores"].get("weight_score", 60.0)) * weight_share
        )
        live_section = float(horse["matrix_scores"].get("class_weight", 60.0))
        race_scale = section_scale * (bm_scale if race.get("race_class_bucket") in BM_BUCKETS else 1.0)
        return float(horse["rank_score"]) + (clip_score(replacement) - live_section) * live_weight * race_scale

    return score_builder


def summarize_rating_variant(races: list[dict], variant: dict) -> dict:
    return summarize_bucket(evaluate_races(races, build_rating_shadow_score(variant)))


def search_rating_shadow_variants(train_races: list[dict], valid_races: list[dict], full_races: list[dict]) -> list[dict]:
    rows = []
    for class_share in (0.40, 0.45, 0.55):
        for rating_share in (0.15, 0.25, 0.35):
            weight_share = round(1.0 - class_share - rating_share, 4)
            if weight_share < 0.05 or weight_share > 0.40:
                continue
            for z_scale in (6.0, 9.0):
                for rank_scale in (0.0, 3.0):
                    for section_scale in (0.75, 1.0, 1.25, 1.5):
                        for bm_scale in (0.90, 1.10):
                            variant = {
                                "class_share": class_share,
                                "rating_share": rating_share,
                                "weight_share": weight_share,
                                "z_scale": z_scale,
                                "rank_scale": rank_scale,
                                "section_scale": section_scale,
                                "bm_scale": bm_scale,
                            }
                            rows.append(
                                {
                                    "variant": variant,
                                    "train": summarize_rating_variant(train_races, variant),
                                    "valid": summarize_rating_variant(valid_races, variant),
                                    "full": summarize_rating_variant(full_races, variant),
                                }
                            )
    rows.sort(
        key=lambda row: (
            row["valid"]["pass_rate"],
            row["valid"]["good_rate"],
            -row["valid"]["zero_hit_rate"],
            row["valid"]["top3_place_precision"],
            row["full"]["pass_rate"],
            row["full"]["good_rate"],
        ),
        reverse=True,
    )
    return rows[:12]


def promote_rating_variant(baseline_valid: dict, baseline_full: dict, row: dict) -> bool:
    valid = row["valid"]
    full = row["full"]
    return (
        valid["pass_rate"] > baseline_valid["pass_rate"]
        and valid["good_rate"] >= baseline_valid["good_rate"]
        and valid["top3_place_precision"] >= baseline_valid["top3_place_precision"]
        and valid["zero_hit_rate"] <= baseline_valid["zero_hit_rate"]
        and full["pass_rate"] > baseline_full["pass_rate"]
        and full["good_rate"] >= baseline_full["good_rate"]
        and full["zero_hit_rate"] <= baseline_full["zero_hit_rate"]
    )


def render_report(
    races: list[dict],
    baseline: dict,
    baseline_train: dict,
    baseline_valid: dict,
    univariate_rows: list[dict],
    weight_rows: list[dict],
    section_rows: dict[str, dict],
    rating_rows: list[dict],
    train_count: int,
    valid_count: int,
) -> str:
    rating_loaded = sum(1 for race in races for horse in race["horses"] if horse.get("horse_rating") is not None)
    promote_rows = [row for row in rating_rows if promote_rating_variant(baseline_valid, baseline, row)]
    lines = [
        "# AU ML Matrix Diagnostics",
        "",
        f"- Races: `{len(races)}`",
        f"- Meetings: `{len({race['meeting'] for race in races})}`",
        f"- Horses: `{sum(len(race['horses']) for race in races)}`",
        f"- Racecard ratings loaded: `{rating_loaded}` / `{sum(len(race['horses']) for race in races)}`",
        f"- Split: train `{train_count}` races / validation `{valid_count}` races",
        "",
        "## Baseline",
        "",
        f"- Champion: {fmt_pct(baseline['champion_rate'])}",
        f"- Winner in Top3: {fmt_pct(baseline['winner_in_top3_rate'])}",
        f"- Gold: {fmt_pct(baseline['gold_rate'])}",
        f"- Good: {fmt_pct(baseline['good_rate'])}",
        f"- Pass (Top3 hit >= 2): {fmt_pct(baseline['pass_rate'])}",
        f"- Top3 Place Precision: {fmt_pct(baseline['top3_place_precision'])}",
        f"- Zero-hit: {fmt_pct(baseline['zero_hit_rate'])}",
        "",
        "### Walk-Forward Baseline",
        "",
        f"- Train Pass/Good/Place/Zero-hit: {fmt_pct(baseline_train['pass_rate'])} / {fmt_pct(baseline_train['good_rate'])} / {fmt_pct(baseline_train['top3_place_precision'])} / {fmt_pct(baseline_train['zero_hit_rate'])}",
        f"- Validation Pass/Good/Place/Zero-hit: {fmt_pct(baseline_valid['pass_rate'])} / {fmt_pct(baseline_valid['good_rate'])} / {fmt_pct(baseline_valid['top3_place_precision'])} / {fmt_pct(baseline_valid['zero_hit_rate'])}",
        "",
        "## Section Power",
        "",
        "| Section | Variant | Pass | Good | Place | Zero-hit |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in univariate_rows[:28]:
        summary = row["summary"]
        lines.append(
            f"| {row['section']} | {row['variant']} | {fmt_pct(summary['pass_rate'])} | "
            f"{fmt_pct(summary['good_rate'])} | {fmt_pct(summary['top3_place_precision'])} | "
            f"{fmt_pct(summary['zero_hit_rate'])} |"
        )

    lines.extend(["", "## Weight Search", "", "| Rank | Validation Pass | Validation Good | Validation Place | Validation Zero-hit | Weights |", "|---:|---:|---:|---:|---:|---|"])
    for index, row in enumerate(weight_rows, start=1):
        valid = row["valid"]
        lines.append(
            f"| {index} | {fmt_pct(valid['pass_rate'])} | {fmt_pct(valid['good_rate'])} | "
            f"{fmt_pct(valid['top3_place_precision'])} | {fmt_pct(valid['zero_hit_rate'])} | "
            f"{fmt_weights(row['weights'])} |"
        )

    lines.extend(["", "## Section Formula Search", "", "| Section | Validation Pass | Validation Good | Validation Place | Validation Zero-hit | Candidate | Live? |", "|---|---:|---:|---:|---:|---|---|"])
    for section in MATRIX_KEYS:
        row = section_rows[section]
        valid = row["valid"]
        lines.append(
            f"| {section} | {fmt_pct(valid['pass_rate'])} | {fmt_pct(valid['good_rate'])} | "
            f"{fmt_pct(valid['top3_place_precision'])} | {fmt_pct(valid['zero_hit_rate'])} | "
            f"{fmt_weights(row['component_weights'])} | {'yes' if row['is_live'] else 'no'} |"
        )

    lines.extend(
        [
            "",
            "## Rating Shadow Search",
            "",
            "| Rank | Validation Pass | Validation Good | Validation Place | Validation Zero-hit | Full Pass | Full Good | Full Place | Mix |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for index, row in enumerate(rating_rows, start=1):
        valid = row["valid"]
        full = row["full"]
        variant = row["variant"]
        mix_text = (
            f"class {variant['class_share']:.2f}, rating {variant['rating_share']:.2f}, weight {variant['weight_share']:.2f}; "
            f"z {variant['z_scale']:.1f}, rank {variant['rank_scale']:.1f}, "
            f"section x{variant['section_scale']:.2f}, bm x{variant['bm_scale']:.2f}"
        )
        lines.append(
            f"| {index} | {fmt_pct(valid['pass_rate'])} | {fmt_pct(valid['good_rate'])} | "
            f"{fmt_pct(valid['top3_place_precision'])} | {fmt_pct(valid['zero_hit_rate'])} | "
            f"{fmt_pct(full['pass_rate'])} | {fmt_pct(full['good_rate'])} | {fmt_pct(full['top3_place_precision'])} | {mix_text} |"
        )

    lines.extend(["", "## Rating Promotion Gate", ""])
    if promote_rows:
        best = promote_rows[0]
        variant = best["variant"]
        lines.append("PASSED")
        lines.append("")
        lines.append(
            "- Best promotable mix: "
            f"class {variant['class_share']:.2f}, rating {variant['rating_share']:.2f}, weight {variant['weight_share']:.2f}, "
            f"z {variant['z_scale']:.1f}, rank {variant['rank_scale']:.1f}, "
            f"section x{variant['section_scale']:.2f}, bm x{variant['bm_scale']:.2f}"
        )
        lines.append(
            f"- Validation Pass/Good/Place/Zero-hit: {fmt_pct(best['valid']['pass_rate'])} / {fmt_pct(best['valid']['good_rate'])} / "
            f"{fmt_pct(best['valid']['top3_place_precision'])} / {fmt_pct(best['valid']['zero_hit_rate'])}"
        )
        lines.append(
            f"- Full Pass/Good/Place/Zero-hit: {fmt_pct(best['full']['pass_rate'])} / {fmt_pct(best['full']['good_rate'])} / "
            f"{fmt_pct(best['full']['top3_place_precision'])} / {fmt_pct(best['full']['zero_hit_rate'])}"
        )
    else:
        lines.append("FAILED")
        lines.append("")
        lines.append(
            "No rating-aware class/weight variant improved validation Pass while keeping validation Good/Place up and zero-hit flat or lower."
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AU matrix diagnostics with simple ML-style weight search.")
    parser.add_argument("--weight-iters", type=int, default=3000)
    parser.add_argument("--section-iters", type=int, default=1200)
    parser.add_argument("--train-ratio", type=float, default=0.7)
    parser.add_argument("--seed", type=int, default=20260525)
    parser.add_argument("--stdout", action="store_true")
    args = parser.parse_args()

    races = load_races()
    if len(races) < 10:
        raise SystemExit("Not enough AU races loaded for diagnostics.")

    train_races, valid_races = chron_split(races, args.train_ratio)
    baseline_train = summarize_bucket(evaluate_races(train_races, lambda _race, horse: horse["rank_score"]))
    baseline_valid = summarize_bucket(evaluate_races(valid_races, lambda _race, horse: horse["rank_score"]))
    baseline = summarize_bucket(evaluate_races(races, lambda _race, horse: horse["rank_score"]))
    univariate_rows = section_univariate_report(races)
    weight_rows = search_global_weights(train_races, valid_races, args.weight_iters, args.seed)
    section_rows = search_section_formulas(train_races, valid_races, args.section_iters, args.seed + 17)
    rating_rows = search_rating_shadow_variants(train_races, valid_races, races)

    report = render_report(
        races=races,
        baseline=baseline,
        baseline_train=baseline_train,
        baseline_valid=baseline_valid,
        univariate_rows=univariate_rows,
        weight_rows=weight_rows,
        section_rows=section_rows,
        rating_rows=rating_rows,
        train_count=len(train_races),
        valid_count=len(valid_races),
    )
    OUTPUT_MD.write_text(report, encoding="utf-8")

    if args.stdout:
        print(report)
    else:
        print(f"Wrote {OUTPUT_MD}")
        print(f"Loaded races: {len(races)} | train={len(train_races)} | valid={len(valid_races)}")
        print(
            "Baseline:",
            {
                "champion": round(baseline["champion_rate"], 4),
                "good": round(baseline["good_rate"], 4),
                "pass": round(baseline["pass_rate"], 4),
                "place": round(baseline["top3_place_precision"], 4),
                "zero_hit": round(baseline["zero_hit_rate"], 4),
            },
        )
        print("Best weight candidate:", weight_rows[0]["weights"])
        if rating_rows:
            print("Best rating shadow candidate:", rating_rows[0]["variant"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
