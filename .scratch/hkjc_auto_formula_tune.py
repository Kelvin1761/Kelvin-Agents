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
    base_stats = evaluate(review, races, BASE_FORMULAS, OUTER_WEIGHTS)
    print("BASE", objective(base_stats), base_stats)

    formula_candidates = build_formula_candidates()
    best = []
    for formulas in formula_candidates:
        stats = evaluate(review, races, formulas, OUTER_WEIGHTS)
        best.append((objective(stats), formulas, stats))
    best.sort(key=lambda item: item[0], reverse=True)

    print("TOP FORMULA-ONLY CANDIDATES")
    for score, formulas, stats in best[:20]:
        print(round(score, 4), compact_formulas(formulas), stats)

    # Re-tune outer weights for the best few inner formula sets.
    combo_best = []
    for _score, formulas, _stats in best[:8]:
        for weights in outer_weight_candidates():
            stats = evaluate(review, races, formulas, weights)
            combo_best.append((objective(stats), formulas, weights, stats))
    combo_best.sort(key=lambda item: item[0], reverse=True)

    print("TOP FORMULA+OUTER CANDIDATES")
    for score, formulas, weights, stats in combo_best[:20]:
        print(round(score, 4), compact_formulas(formulas), weights, stats)

    top_score, top_formulas, top_weights, top_stats = combo_best[0]
    print("BEST VENUE SPLIT")
    for venue, stats in evaluate_split(review, races, top_formulas, top_weights, "venue").items():
        print(venue, stats)
    print("BASE VENUE SPLIT")
    for venue, stats in evaluate_split(review, races, BASE_FORMULAS, OUTER_WEIGHTS, "venue").items():
        print(venue, stats)
    return 0


def build_formula_candidates():
    candidates = []
    for stability in stability_candidates():
        for sectional in two_part_candidates("speed_score", "track_going_score", range(60, 91, 5)):
            for trainer in two_part_candidates("jockey_score", "trainer_score", range(45, 66, 5)):
                for health in health_candidates():
                    for form_line in two_part_candidates("formline_strength_score", "margin_trend_score", range(55, 86, 5)):
                        for class_advantage in two_part_candidates("class_score", "weight_score", range(60, 91, 5)):
                            formulas = deepcopy(BASE_FORMULAS)
                            formulas["stability"] = stability
                            formulas["sectional"] = sectional
                            formulas["trainer_signal"] = trainer
                            formulas["horse_health"] = health
                            formulas["form_line"] = form_line
                            formulas["class_advantage"] = class_advantage
                            candidates.append(formulas)
    return candidates


def stability_candidates():
    out = []
    for form in range(40, 66, 5):
        for consistency in range(25, 56, 5):
            confidence = 100 - form - consistency
            if 0 <= confidence <= 20:
                out.append((
                    ("form_score", form / 100),
                    ("consistency_score", consistency / 100),
                    ("confidence_score", confidence / 100),
                ))
    return out


def health_candidates():
    out = []
    for risk in range(45, 71, 5):
        for weight in range(20, 46, 5):
            confidence = 100 - risk - weight
            if 0 <= confidence <= 20:
                out.append((
                    ("risk_score", risk / 100),
                    ("weight_score", weight / 100),
                    ("confidence_score", confidence / 100),
                ))
    return out


def two_part_candidates(left_key, right_key, left_range):
    return tuple(((left_key, left / 100), (right_key, (100 - left) / 100)) for left in left_range)


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
                features = review.compute_full_feature_scores(horse, race_context)
                horses.append({"horse_num": horse_num, "features": features})
            if horses:
                rows.append({
                    "meeting": str(meeting_dir),
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


def compact_formulas(formulas):
    return {
        key: tuple((name, round(weight, 2)) for name, weight in formulas[key])
        for key in ("stability", "sectional", "trainer_signal", "horse_health", "form_line", "class_advantage")
    }


if __name__ == "__main__":
    raise SystemExit(main())
