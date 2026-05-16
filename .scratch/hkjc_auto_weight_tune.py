#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts" / "review_auto_weighting.py"


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


def score_summary(stats):
    # Balanced objective: reward coverage and ranking quality while keeping first pick useful.
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
    model_review = review.run_review(
        review.default_meeting_roots(),
        review.default_results_roots(),
        review.default_season_csvs(),
    )

    races = []
    for race in collect_races(review):
        races.append(race)

    current = {
        "sectional": 0.22,
        "trainer_signal": 0.16,
        "stability": 0.18,
        "race_shape": 0.20,
        "class_advantage": 0.06,
        "horse_health": 0.09,
        "form_line": 0.09,
    }
    candidates = []
    keys = list(current)
    ranges = {
        "sectional": range(12, 25, 2),
        "trainer_signal": range(12, 23, 2),
        "stability": range(14, 27, 2),
        "race_shape": range(12, 27, 2),
        "class_advantage": range(4, 13, 2),
        "horse_health": range(5, 15, 2),
    }
    for sectional in ranges["sectional"]:
        for trainer in ranges["trainer_signal"]:
            for stability in ranges["stability"]:
                for race_shape in ranges["race_shape"]:
                    for class_advantage in ranges["class_advantage"]:
                        for horse_health in ranges["horse_health"]:
                            used = sectional + trainer + stability + race_shape + class_advantage + horse_health
                            form_line = 100 - used
                            if form_line < 4 or form_line > 16:
                                continue
                            weights = {
                                "sectional": sectional / 100,
                                "trainer_signal": trainer / 100,
                                "stability": stability / 100,
                                "race_shape": race_shape / 100,
                                "class_advantage": class_advantage / 100,
                                "horse_health": horse_health / 100,
                                "form_line": form_line / 100,
                            }
                            stats = evaluate_weights(review, races, weights)
                            candidates.append((score_summary(stats), weights, stats))

    candidates.sort(key=lambda item: item[0], reverse=True)
    current_stats = model_review["model_summary"]["current_live"]
    previous_stats = model_review["model_summary"]["previous_calibrated"]
    print("BASE previous_calibrated", previous_stats)
    print("BASE current_live", current_stats)
    print("TOP CANDIDATES")
    for score, weights, stats in candidates[:20]:
        print(round(score, 4), weights, stats)
    best_weights = candidates[0][1]
    print("BEST VENUE SPLIT")
    for name, stats in evaluate_split(review, races, best_weights, "venue").items():
        print(name, stats)
    print("CURRENT VENUE SPLIT")
    for name, stats in evaluate_split(review, races, current, "venue").items():
        print(name, stats)
    return 0


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
                matrix_scores = review.compute_matrix_scores(features, review.CURRENT_MATRIX_FORMULAS)
                horses.append({"horse_num": horse_num, "matrix_scores": matrix_scores})
            if horses:
                rows.append({
                    "meeting": str(meeting_dir),
                    "venue": "HappyValley" if "HappyValley" in meeting_dir.name else "ShaTin",
                    "actual_pos": actual_pos,
                    "horses": horses,
                })
    return rows


def evaluate_weights(review, races, weights):
    evaluated = []
    for race in races:
        scored = []
        for horse in race["horses"]:
            ability = review.compute_ability(horse["matrix_scores"], weights)
            scored.append({
                "horse_num": horse["horse_num"],
                "models": {"candidate": {"ability": ability}},
            })
        evaluated.append(review.evaluate_model(scored, race["actual_pos"], "candidate"))
    return summarize(evaluated)


def evaluate_split(review, races, weights, split_key):
    groups = {}
    for race in races:
        groups.setdefault(race[split_key], []).append(race)
    return {name: evaluate_weights(review, subset, weights) for name, subset in sorted(groups.items())}


if __name__ == "__main__":
    raise SystemExit(main())
