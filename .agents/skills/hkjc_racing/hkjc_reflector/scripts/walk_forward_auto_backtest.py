#!/usr/bin/env python3
"""
walk_forward_auto_backtest.py — HKJC Auto old/new formula backtest.

Compares the previous Auto 7D weighting against the current calibrated
weighting using existing Race_*_Logic.json feature scores and HKJC extractor
result JSON files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


OLD_MATRIX_WEIGHTS = {
    "sectional": 0.23,
    "trainer_signal": 0.21,
    "stability": 0.17,
    "race_shape": 0.15,
    "class_advantage": 0.10,
    "horse_health": 0.07,
    "form_line": 0.07,
}

OLD_MATRIX_FORMULAS = {
    "stability": (("form_score", 0.45), ("consistency_score", 0.35), ("confidence_score", 0.20)),
    "sectional": (("speed_score", 0.75), ("track_going_score", 0.25)),
    "race_shape": (("draw_score", 0.60), ("distance_score", 0.25), ("weight_score", 0.15)),
    "trainer_signal": (("jockey_score", 0.50), ("trainer_score", 0.35), ("confidence_score", 0.15)),
    "horse_health": (("risk_score", 0.45), ("weight_score", 0.30), ("confidence_score", 0.25)),
    "form_line": (("form_score", 0.70), ("consistency_score", 0.30)),
    "class_advantage": (("class_score", 0.70), ("distance_score", 0.30)),
}

# The "new" model mirrors live PRODUCTION. To prevent the weights drifting out of
# sync with the engine (the original bug — they were stale and never-deployed),
# import them straight from the engine's single source of truth. Falls back to a
# pinned copy only if the engine package can't be located.
#
# WARNING: the recompute path below can only use the 12 persisted feature_scores.
# Production's form_line uses formline_strength_score / margin_trend_score and
# stability uses trackwork_trend_score — these sub-features are NOT persisted, so
# the recompute CANNOT reproduce production form_line/stability exactly. For a
# faithful production backtest, trust the "prod" column, which ranks by the
# persisted python_auto.ability_score directly.
_ENGINE = Path(__file__).resolve().parents[2] / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
try:
    sys.path.insert(0, str(_ENGINE))
    from scoring import MATRIX_WEIGHTS as NEW_MATRIX_WEIGHTS  # type: ignore
    from matrix_mapper import MATRIX_FORMULAS as NEW_MATRIX_FORMULAS  # type: ignore
except Exception:  # pragma: no cover - fallback to pinned production snapshot
    NEW_MATRIX_WEIGHTS = {
        "sectional": 0.1922, "trainer_signal": 0.2296, "stability": 0.0955,
        "race_shape": 0.2661, "class_advantage": 0.1387, "horse_health": 0.0,
        "form_line": 0.0778,
    }
    NEW_MATRIX_FORMULAS = {
        "stability": (("form_score", 0.50), ("consistency_score", 0.40), ("trackwork_trend_score", 0.10)),
        "sectional": (("speed_score", 0.65), ("track_going_score", 0.35)),
        "race_shape": (("draw_score", 1.00),),
        "trainer_signal": (("jockey_score", 0.55), ("trainer_score", 0.45)),
        "horse_health": (("risk_score", 0.55), ("weight_score", 0.35), ("confidence_score", 0.10)),
        "form_line": (("formline_strength_score", 0.70), ("margin_trend_score", 0.30)),
        "class_advantage": (("class_score", 0.75), ("weight_score", 0.25)),
    }


def clip_score(value: object, default: float = 60.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(100.0, score))


def compute_ability(features: dict, formulas: dict, weights: dict) -> float:
    matrix_scores = {}
    for key, components in formulas.items():
        matrix_scores[key] = sum(clip_score(features.get(name, 60)) * weight for name, weight in components)
    return sum(matrix_scores[key] * weight for key, weight in weights.items())


def find_results_json(meeting_dir: Path) -> Path | None:
    files = sorted(meeting_dir.glob("*全日賽果.json"))
    return files[0] if files else None


def load_results(path: Path) -> dict[int, dict[int, int]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    results = {}
    for race_key, race_data in data.items():
        try:
            race_num = int(race_key)
        except (TypeError, ValueError):
            continue
        race_results = {}
        for row in race_data.get("results", []):
            try:
                race_results[int(row["horse_no"])] = int(row["pos"])
            except (KeyError, TypeError, ValueError):
                continue
        if race_results:
            results[race_num] = race_results
    return results


def race_num_from_path(path: Path) -> int:
    match = re.search(r"Race_(\d+)_Logic\.json$", path.name)
    return int(match.group(1)) if match else 0


def score_meeting(meeting_dir: Path) -> dict:
    result_path = find_results_json(meeting_dir)
    if result_path is None:
        raise FileNotFoundError(f"No *全日賽果.json found in {meeting_dir}")

    actual = load_results(result_path)
    races = []
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=race_num_from_path):
        race_num = race_num_from_path(logic_path)
        if race_num not in actual:
            continue
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        scored = []
        for horse_num_text, horse in logic.get("horses", {}).items():
            try:
                horse_num = int(horse_num_text)
            except ValueError:
                continue
            auto = horse.get("python_auto", {})
            features = auto.get("feature_scores", {})
            if not features:
                continue
            scored.append({
                "horse_num": horse_num,
                "old": compute_ability(features, OLD_MATRIX_FORMULAS, OLD_MATRIX_WEIGHTS),
                "new": compute_ability(features, NEW_MATRIX_FORMULAS, NEW_MATRIX_WEIGHTS),
                # faithful production ranking — what the engine actually produced
                "prod": clip_score(auto.get("ability_score", 60.0)),
            })
        if scored:
            races.append(evaluate_race(race_num, scored, actual[race_num]))

    return {
        "meeting": str(meeting_dir),
        "results_file": str(result_path),
        "summary": summarize(races),
        "races": races,
    }


def evaluate_race(race_num: int, scored: list[dict], actual_pos: dict[int, int]) -> dict:
    # Dead-heat safe: include every horse finishing in pos <= 3 (not a hard [:3] slice).
    actual_top3 = [horse for horse, pos in actual_pos.items() if pos <= 3]
    return {
        "race": race_num,
        "actual_top3": actual_top3,
        "old": evaluate_model(scored, actual_pos, actual_top3, "old"),
        "new": evaluate_model(scored, actual_pos, actual_top3, "new"),
        "prod": evaluate_model(scored, actual_pos, actual_top3, "prod"),
    }


def evaluate_model(scored: list[dict], actual_pos: dict[int, int], actual_top3: list[int], key: str) -> dict:
    # Deterministic tie-break: higher score first, then lower horse number.
    picks = [item["horse_num"] for item in sorted(scored, key=lambda item: (-item[key], item["horse_num"]))[:4]]
    actual_set = set(actual_top3)
    hits = sum(1 for horse in picks[:3] if horse in actual_set)
    winner = actual_top3[0] if actual_top3 else None
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )
    return {
        "picks": picks,
        "hits": hits,
        "gold": hits == 3,
        "good": len(picks) >= 2 and picks[0] in actual_set and picks[1] in actual_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(picks and picks[0] == winner),
        "top3_has_champion": winner in set(picks[:3]),
        "order_issue": order_issue,
    }


def summarize(races: list[dict]) -> dict:
    summary = {}
    for key in ("old", "new", "prod"):
        total = len(races)
        summary[key] = {
            "races": total,
            "gold": sum(r[key]["gold"] for r in races),
            "good": sum(r[key]["good"] for r in races),
            "min_threshold": sum(r[key]["min_threshold"] for r in races),
            "single": sum(r[key]["single"] for r in races),
            "champion": sum(r[key]["champion"] for r in races),
            "top3_has_champion": sum(r[key]["top3_has_champion"] for r in races),
            "order_issue": sum(r[key]["order_issue"] for r in races),
        }
    return summary


def aggregate(meetings: list[dict]) -> dict:
    races = []
    for meeting in meetings:
        races.extend(meeting["races"])
    return summarize(races)


def print_table(meetings: list[dict]) -> None:
    print("meeting,races,model,gold,good,min,single,champion,top3_champ,order_issue")
    for meeting in meetings:
        name = Path(meeting["meeting"]).name
        for model in ("old", "new", "prod"):
            s = meeting["summary"][model]
            print(
                f"{name},{s['races']},{model},{s['gold']},{s['good']},"
                f"{s['min_threshold']},{s['single']},{s['champion']},"
                f"{s['top3_has_champion']},{s['order_issue']}"
            )
    overall = aggregate(meetings)
    for model in ("old", "new", "prod"):
        s = overall[model]
        print(
            f"OVERALL,{s['races']},{model},{s['gold']},{s['good']},"
            f"{s['min_threshold']},{s['single']},{s['champion']},"
            f"{s['top3_has_champion']},{s['order_issue']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="HKJC Auto old/new formula walk-forward backtest")
    parser.add_argument("meeting_dirs", nargs="+", help="Meeting folders containing Race_*_Logic.json and *全日賽果.json")
    parser.add_argument("--json", action="store_true", help="Output JSON instead of CSV table")
    args = parser.parse_args()

    meetings = [score_meeting(Path(item)) for item in args.meeting_dirs]
    if args.json:
        print(json.dumps({"meetings": meetings, "overall": aggregate(meetings)}, ensure_ascii=False, indent=2))
    else:
        print_table(meetings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
