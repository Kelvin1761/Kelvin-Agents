#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts" / "review_auto_weighting.py"

OUTER_WEIGHTS = {
    "sectional": 0.20,
    "trainer_signal": 0.18,
    "stability": 0.14,
    "race_shape": 0.26,
    "class_advantage": 0.10,
    "horse_health": 0.07,
    "form_line": 0.05,
}

BASE_FORMULAS = {
    "stability": (("form_score", 0.50), ("consistency_score", 0.40), ("confidence_score", 0.10)),
    "sectional": (("speed_score", 0.75), ("track_going_score", 0.25)),
    "race_shape": (("draw_score", 1.00),),
    "trainer_signal": (("jockey_score", 0.55), ("trainer_score", 0.45)),
    "horse_health": (("risk_score", 0.55), ("weight_score", 0.35), ("confidence_score", 0.10)),
    "form_line": (("formline_strength_score", 0.70), ("margin_trend_score", 0.30)),
    "class_advantage": (("class_score", 0.75), ("weight_score", 0.25)),
}


def load_review_module():
    spec = importlib.util.spec_from_file_location("review_auto_weighting", REVIEW_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def summarize(model_races):
    total = len(model_races)
    return {
        "races": total,
        "gold": sum(item["gold"] for item in model_races),
        "good": sum(item["good"] for item in model_races),
        "min_threshold": sum(item["min_threshold"] for item in model_races),
        "single": sum(item["single"] for item in model_races),
        "champion": sum(item["champion"] for item in model_races),
        "top3_has_champion": sum(item["top3_has_champion"] for item in model_races),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in model_races) / total, 3),
        "mrr": round(sum(item["mrr"] for item in model_races) / total, 4),
        "avg_pick1_finish": round(sum(item["pick1_finish"] for item in model_races) / total, 3),
        "avg_top4_hits": round(sum(item["top4_hits"] for item in model_races) / total, 3),
    }


def objective(stats):
    return (
        stats["gold"] * 8.0
        + stats["good"] * 4.0
        + stats["min_threshold"] * 3.0
        + stats["champion"] * 2.0
        + stats["top3_has_champion"] * 2.0
        + stats["single"] * 0.5
        + stats["mrr"] * 30.0
        + stats["avg_top4_hits"] * 8.0
        - stats["avg_pick1_finish"] * 0.6
        - stats["avg_winner_rank"] * 0.4
    )


def main() -> int:
    review = load_review_module()
    races = collect_races(review)
    formulas = deepcopy(BASE_FORMULAS)
    base_stats = evaluate(review, races, formulas, OUTER_WEIGHTS)
    print("BASE", round(objective(base_stats), 4), base_stats, compact(formulas))

    for iteration in range(4):
        improved = False
        print("ITER", iteration + 1)
        for section, candidates in section_candidates().items():
            best_formula = formulas[section]
            best_stats = evaluate(review, races, formulas, OUTER_WEIGHTS)
            best_score = objective(best_stats)
            ranked = []
            for candidate in candidates:
                trial = deepcopy(formulas)
                trial[section] = candidate
                stats = evaluate(review, races, trial, OUTER_WEIGHTS)
                ranked.append((objective(stats), candidate, stats))
            ranked.sort(key=lambda item: item[0], reverse=True)
            top_score, top_candidate, top_stats = ranked[0]
            print(section, round(best_score, 4), "=>", round(top_score, 4), top_candidate, top_stats)
            if top_score > best_score + 0.01:
                formulas[section] = top_candidate
                improved = True
        stats = evaluate(review, races, formulas, OUTER_WEIGHTS)
        print("AFTER", round(objective(stats), 4), stats, compact(formulas))
        if not improved:
            break

    print("OUTER RETUNE")
    outer_ranked = []
    for weights in outer_weight_candidates():
        stats = evaluate(review, races, formulas, weights)
        outer_ranked.append((objective(stats), weights, stats))
    outer_ranked.sort(key=lambda item: item[0], reverse=True)
    for score, weights, stats in outer_ranked[:12]:
        print(round(score, 4), weights, stats)

    best_weights = outer_ranked[0][1]
    print("BEST VENUE SPLIT")
    for venue, stats in evaluate_split(review, races, formulas, best_weights, "venue").items():
        print(venue, stats)
    print("BEST FORMULAS", compact(formulas))
    print("BEST WEIGHTS", best_weights)
    return 0


def section_candidates():
    return {
        "stability": tuple(
            (("form_score", f / 100), ("consistency_score", c / 100), ("confidence_score", (100 - f - c) / 100))
            for f in range(40, 66, 5)
            for c in range(25, 56, 5)
            if 0 <= 100 - f - c <= 20
        ),
        "sectional": two_part("speed_score", "track_going_score", range(55, 96, 5)),
        "trainer_signal": two_part("jockey_score", "trainer_score", range(40, 71, 5)),
        "horse_health": tuple(
            (("risk_score", r / 100), ("weight_score", w / 100), ("confidence_score", (100 - r - w) / 100))
            for r in range(40, 76, 5)
            for w in range(15, 51, 5)
            if 0 <= 100 - r - w <= 25
        ),
        "form_line": two_part("formline_strength_score", "margin_trend_score", range(45, 96, 5)),
        "class_advantage": two_part("class_score", "weight_score", range(50, 96, 5)),
    }


def two_part(left, right, values):
    return tuple(((left, v / 100), (right, (100 - v) / 100)) for v in values)


def outer_weight_candidates():
    ranges = {
        "sectional": range(16, 25, 2),
        "trainer_signal": range(14, 23, 2),
        "stability": range(10, 19, 2),
        "race_shape": range(20, 31, 2),
        "class_advantage": range(6, 15, 2),
        "horse_health": range(3, 12, 2),
    }
    for sectional in ranges["sectional"]:
        for trainer in ranges["trainer_signal"]:
            for stability in ranges["stability"]:
                for race_shape in ranges["race_shape"]:
                    for class_advantage in ranges["class_advantage"]:
                        for horse_health in ranges["horse_health"]:
                            used = sectional + trainer + stability + race_shape + class_advantage + horse_health
                            form_line = 100 - used
                            if 3 <= form_line <= 12:
                                yield {
                                    "sectional": sectional / 100,
                                    "trainer_signal": trainer / 100,
                                    "stability": stability / 100,
                                    "race_shape": race_shape / 100,
                                    "class_advantage": class_advantage / 100,
                                    "horse_health": horse_health / 100,
                                    "form_line": form_line / 100,
                                }


def collect_races(review):
    results_index = review.build_results_index(review.default_results_roots())
    rows = []
    for meeting_dir in review.hk_meeting_dirs(review.default_meeting_roots()):
        date = review.meeting_date(meeting_dir)
        result_path = results_index.get(date or "")
        if not result_path:
            continue
        actual_results = review.load_results(result_path)
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=review.race_num_from_path):
            race_num = review.race_num_from_path(logic_path)
            actual_pos = actual_results.get(race_num)
            if not actual_pos:
                continue
            logic = review.json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue
                horses.append({"horse_num": horse_num, "features": review.compute_full_feature_scores(horse, race_context)})
            if horses:
                rows.append({
                    "venue": "HappyValley" if "HappyValley" in meeting_dir.name else "ShaTin",
                    "actual_pos": actual_pos,
                    "horses": horses,
                })
    return rows


def evaluate(review, races, formulas, weights):
    evaluated = []
    for race in races:
        scored = []
        for horse in race["horses"]:
            matrix_scores = review.compute_matrix_scores(horse["features"], formulas)
            ability = review.compute_ability(matrix_scores, weights)
            scored.append({"horse_num": horse["horse_num"], "models": {"candidate": {"ability": ability}}})
        evaluated.append(review.evaluate_model(scored, race["actual_pos"], "candidate"))
    return summarize(evaluated)


def evaluate_split(review, races, formulas, weights, split_key):
    groups = {}
    for race in races:
        groups.setdefault(race[split_key], []).append(race)
    return {name: evaluate(review, subset, formulas, weights) for name, subset in sorted(groups.items())}


def compact(formulas):
    return {
        key: tuple((name, round(weight, 2)) for name, weight in formulas[key])
        for key in ("stability", "sectional", "trainer_signal", "horse_health", "form_line", "class_advantage")
    }


if __name__ == "__main__":
    raise SystemExit(main())
