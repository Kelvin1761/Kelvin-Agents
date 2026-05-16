#!/usr/bin/env python3
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".scratch" / "hkjc_auto_feature_cache.json"

BASE_WEIGHTS = {
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


def clip(value, default=60.0):
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def matrix_scores(features, formulas):
    return {
        key: sum(clip(features.get(name, 60)) * weight for name, weight in components)
        for key, components in formulas.items()
    }


def ability(mscores, weights):
    return sum(mscores[key] * weight for key, weight in weights.items())


def evaluate_model(scored, actual_pos):
    ranked = sorted(scored, key=lambda item: (-item["ability"], item["horse_num"]))
    picks = [item["horse_num"] for item in ranked[:4]]
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    hits = sum(1 for horse in picks[:3] if horse in actual_top3_set)
    winner = actual_top3[0] if actual_top3 else None
    winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_num"] == winner), len(ranked) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse in picks if horse in set(actual_top4))
    return {
        "gold": hits == 3,
        "good": len(picks) >= 2 and picks[0] in actual_top3_set and picks[1] in actual_top3_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(picks and picks[0] == winner),
        "top3_has_champion": bool(winner in set(picks[:3])),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
        "pick1_finish": pick1_finish,
        "top4_hits": top4_hits,
    }


def summarize(items):
    total = len(items)
    return {
        "races": total,
        "gold": sum(item["gold"] for item in items),
        "good": sum(item["good"] for item in items),
        "min_threshold": sum(item["min_threshold"] for item in items),
        "single": sum(item["single"] for item in items),
        "champion": sum(item["champion"] for item in items),
        "top3_has_champion": sum(item["top3_has_champion"] for item in items),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in items) / total, 3),
        "mrr": round(sum(item["mrr"] for item in items) / total, 4),
        "avg_pick1_finish": round(sum(item["pick1_finish"] for item in items) / total, 3),
        "avg_top4_hits": round(sum(item["top4_hits"] for item in items) / total, 3),
    }


def score(stats):
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


def evaluate(races, formulas, weights):
    results = []
    for race in races:
        scored = []
        actual_pos = {int(k): int(v) for k, v in race["actual_pos"].items()}
        for horse in race["horses"]:
            mscores = matrix_scores(horse["features"], formulas)
            scored.append({"horse_num": int(horse["horse_num"]), "ability": ability(mscores, weights)})
        results.append(evaluate_model(scored, actual_pos))
    return summarize(results)


def split_eval(races, formulas, weights):
    groups = {}
    for race in races:
        groups.setdefault(race["venue"], []).append(race)
    return {name: evaluate(group, formulas, weights) for name, group in sorted(groups.items())}


def main():
    races = json.loads(CACHE.read_text(encoding="utf-8"))
    formulas = deepcopy(BASE_FORMULAS)
    weights = deepcopy(BASE_WEIGHTS)
    base = evaluate(races, formulas, weights)
    print("BASE", round(score(base), 4), base, compact(formulas), weights, flush=True)

    for iteration in range(6):
        print("ITER", iteration + 1, flush=True)
        changed = False
        for section, candidates in section_candidates().items():
            current = evaluate(races, formulas, weights)
            current_score = score(current)
            ranked = []
            for candidate in candidates:
                trial = deepcopy(formulas)
                trial[section] = candidate
                stats = evaluate(races, trial, weights)
                ranked.append((score(stats), candidate, stats))
            ranked.sort(key=lambda item: item[0], reverse=True)
            top_score, top_candidate, top_stats = ranked[0]
            print(section, round(current_score, 4), "=>", round(top_score, 4), top_candidate, top_stats, flush=True)
            if top_score > current_score + 0.01:
                formulas[section] = top_candidate
                changed = True
        print("AFTER", round(score(evaluate(races, formulas, weights)), 4), evaluate(races, formulas, weights), compact(formulas), weights, flush=True)
        if not changed:
            break

    outer_ranked = []
    for candidate_weights in outer_weight_candidates():
        stats = evaluate(races, formulas, candidate_weights)
        outer_ranked.append((score(stats), candidate_weights, stats))
    outer_ranked.sort(key=lambda item: item[0], reverse=True)
    if outer_ranked[0][0] > score(evaluate(races, formulas, weights)) + 0.01:
        weights = outer_ranked[0][1]

    final = evaluate(races, formulas, weights)
    print("OUTER TOP", flush=True)
    for item_score, item_weights, item_stats in outer_ranked[:12]:
        print(round(item_score, 4), item_weights, item_stats, flush=True)
    print("FINAL", round(score(final), 4), final, flush=True)
    print("SPLIT", split_eval(races, formulas, weights), flush=True)
    print("FORMULAS", compact(formulas), flush=True)
    print("WEIGHTS", weights, flush=True)


def section_candidates():
    return {
        "stability": tuple(
            (("form_score", f / 100), ("consistency_score", c / 100), ("confidence_score", (100 - f - c) / 100))
            for f in range(35, 71, 5)
            for c in range(20, 61, 5)
            if 0 <= 100 - f - c <= 25
        ),
        "sectional": two_part("speed_score", "track_going_score", range(45, 96, 5)),
        "trainer_signal": two_part("jockey_score", "trainer_score", range(35, 76, 5)),
        "horse_health": tuple(
            (("risk_score", r / 100), ("weight_score", w / 100), ("confidence_score", (100 - r - w) / 100))
            for r in range(35, 81, 5)
            for w in range(10, 56, 5)
            if 0 <= 100 - r - w <= 30
        ),
        "form_line": two_part("formline_strength_score", "margin_trend_score", range(35, 96, 5)),
        "class_advantage": two_part("class_score", "weight_score", range(40, 96, 5)),
    }


def two_part(left, right, values):
    return tuple(((left, value / 100), (right, (100 - value) / 100)) for value in values)


def outer_weight_candidates():
    ranges = {
        "sectional": range(18, 23, 2),
        "trainer_signal": range(16, 21, 2),
        "stability": range(12, 17, 2),
        "race_shape": range(24, 29, 2),
        "class_advantage": range(8, 13, 2),
        "horse_health": range(5, 10, 2),
    }
    for sectional in ranges["sectional"]:
        for trainer in ranges["trainer_signal"]:
            for stability in ranges["stability"]:
                for race_shape in ranges["race_shape"]:
                    for class_advantage in ranges["class_advantage"]:
                        for horse_health in ranges["horse_health"]:
                            used = sectional + trainer + stability + race_shape + class_advantage + horse_health
                            form_line = 100 - used
                            if 1 <= form_line <= 14:
                                yield {
                                    "sectional": sectional / 100,
                                    "trainer_signal": trainer / 100,
                                    "stability": stability / 100,
                                    "race_shape": race_shape / 100,
                                    "class_advantage": class_advantage / 100,
                                    "horse_health": horse_health / 100,
                                    "form_line": form_line / 100,
                                }


def compact(formulas):
    return {
        key: tuple((name, round(weight, 2)) for name, weight in formulas[key])
        for key in ("stability", "sectional", "trainer_signal", "horse_health", "form_line", "class_advantage")
    }


if __name__ == "__main__":
    main()
