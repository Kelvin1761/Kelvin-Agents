#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
ENGINE_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts" / "racing_engine"
REFLECTOR_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"
AUTO_DIR = ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_wong_choi_auto" / "scripts"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(REFLECTOR_DIR))
sys.path.insert(0, str(AUTO_DIR))

from engine_core import RacingEngine  # noqa: E402
from review_auto_weighting import (  # noqa: E402
    build_results_index,
    default_meeting_roots,
    default_results_roots,
    hk_meeting_dirs,
    load_results,
    meeting_date,
    race_num_from_path,
    summarize_model_races,
    venue_from_meeting_dir,
)
from scoring import MATRIX_WEIGHTS, clip_score  # noqa: E402
from validate_trainer_health_candidates import (  # noqa: E402
    horse_specific_jockey_change_adjustment,
    load_combo_priors,
    parse_current_jockey_record,
    trainer_signal_candidate_v3,
    trainer_signal_candidate_v4,
)


@dataclass
class RaceSample:
    meeting: str
    date: str
    venue: str
    race_number: int
    distance: str
    race_class: str
    race_context: dict
    actual_pos: dict[int, int]
    horses: list[dict]


def _ability(matrix_scores: dict[str, float]) -> float:
    return round(sum(float(matrix_scores[key]) * weight for key, weight in MATRIX_WEIGHTS.items()), 4)


def _distance_token(value: object) -> str:
    match = re.search(r"(\d{3,4})", str(value or ""))
    return match.group(1) if match else str(value or "").strip()


def _row_value(row: dict | None, key: str) -> float:
    if not row:
        return 0.0
    try:
        return float(row.get(key, 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


class NoJockeyChangePenaltyEngine(RacingEngine):
    def _jockey_change_adjustment(self, jockey_change_rows):  # noqa: D401
        return 0.0


class RelaxedContextEngine(RacingEngine):
    def _trainer_combo_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 80 and (win_rate >= 14.0 or place_rate >= 36.0):
            return 4.0
        if starts >= 55 and (win_rate >= 11.0 or place_rate >= 32.0):
            return 2.0
        if starts >= 30 and win_rate >= 10.0 and place_rate >= 28.0:
            return 1.0
        if starts >= 55 and win_rate <= 6.0 and place_rate <= 21.0:
            return -1.5
        return 0.0

    def _jockey_distance_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 80 and (win_rate >= 15.0 or place_rate >= 40.0):
            return 3.0
        if starts >= 50 and (win_rate >= 11.0 or place_rate >= 33.0):
            return 1.5
        if starts >= 35 and win_rate >= 10.0 and place_rate >= 28.0:
            return 0.8
        if starts >= 55 and win_rate <= 5.5 and place_rate <= 20.0:
            return -1.5
        return 0.0

    def _trainer_distance_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 80 and (win_rate >= 12.0 or place_rate >= 34.0):
            return 2.0
        if starts >= 50 and (win_rate >= 9.0 or place_rate >= 30.0):
            return 1.0
        if starts >= 35 and win_rate >= 8.0 and place_rate >= 27.0:
            return 0.6
        if starts >= 55 and win_rate <= 4.5 and place_rate <= 19.0:
            return -1.0
        return 0.0


class RelaxedNoChangePenaltyEngine(RelaxedContextEngine):
    def _jockey_change_adjustment(self, jockey_change_rows):  # noqa: D401
        return 0.0


class PlaceContextEngine(RacingEngine):
    def _trainer_combo_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 70 and place_rate >= 35.0:
            return 3.0
        if starts >= 40 and place_rate >= 32.0:
            return 1.5
        if starts >= 25 and win_rate >= 12.0 and place_rate >= 26.0:
            return 1.0
        if starts >= 60 and place_rate <= 20.0 and win_rate <= 6.0:
            return -1.5
        return 0.0

    def _jockey_distance_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 70 and place_rate >= 38.0:
            return 2.5
        if starts >= 40 and place_rate >= 33.0:
            return 1.2
        if starts >= 25 and win_rate >= 12.0 and place_rate >= 27.0:
            return 0.8
        if starts >= 60 and place_rate <= 20.0 and win_rate <= 5.5:
            return -1.5
        return 0.0

    def _trainer_distance_adjustment(self, row):
        starts = _row_value(row, "starts")
        win_rate = _row_value(row, "win_rate")
        place_rate = _row_value(row, "place_rate")
        if starts >= 70 and place_rate >= 33.0:
            return 1.8
        if starts >= 40 and place_rate >= 30.0:
            return 0.9
        if starts >= 25 and win_rate >= 10.0 and place_rate >= 26.0:
            return 0.6
        if starts >= 60 and place_rate <= 19.0 and win_rate <= 5.0:
            return -1.0
        return 0.0


class PlaceNoChangePenaltyEngine(PlaceContextEngine):
    def _jockey_change_adjustment(self, jockey_change_rows):  # noqa: D401
        return 0.0


ENGINE_MODELS: dict[str, type[RacingEngine]] = {
    "no_jockey_change_penalty": NoJockeyChangePenaltyEngine,
    "relaxed_context_replace": RelaxedContextEngine,
    "relaxed_no_change_penalty": RelaxedNoChangePenaltyEngine,
    "place_context_replace": PlaceContextEngine,
    "place_no_change_penalty": PlaceNoChangePenaltyEngine,
}


def load_samples() -> tuple[list[RaceSample], dict[str, object]]:
    results_index = build_results_index(default_results_roots())
    skipped: defaultdict[str, int] = defaultdict(int)
    seen: set[tuple[str, str, int]] = set()
    races: list[RaceSample] = []
    for meeting_dir in hk_meeting_dirs(default_meeting_roots()):
        date = meeting_date(meeting_dir)
        if not date:
            skipped["no_date"] += 1
            continue
        results_path = results_index.get(date)
        if not results_path:
            skipped["no_results_file"] += 1
            continue
        venue = venue_from_meeting_dir(meeting_dir)
        all_results = load_results(results_path)
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
            race_number = race_num_from_path(logic_path)
            actual_pos = all_results.get(race_number)
            if not actual_pos:
                skipped["no_race_results"] += 1
                continue
            key = (date, venue, race_number)
            if key in seen:
                skipped["duplicate_race"] += 1
                continue
            seen.add(key)
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            horses = []
            for horse_num_text, horse in logic.get("horses", {}).items():
                try:
                    horse_num = int(horse_num_text)
                except (TypeError, ValueError):
                    continue
                if horse_num not in actual_pos:
                    continue
                auto = RacingEngine(horse, race_context).analyze_horse()
                horses.append(
                    {
                        "horse_num": horse_num,
                        "horse_name": horse.get("horse_name", ""),
                        "data": horse,
                        "auto": auto,
                    }
                )
            if len(horses) < 4:
                skipped["too_few_horses"] += 1
                continue
            races.append(
                RaceSample(
                    meeting=meeting_dir.name,
                    date=date,
                    venue=venue,
                    race_number=race_number,
                    distance=str(race_context.get("distance") or ""),
                    race_class=str(race_context.get("race_class") or ""),
                    race_context=race_context,
                    actual_pos=actual_pos,
                    horses=horses,
                )
            )
    meta = {
        "meetings": len({race.meeting for race in races}),
        "races": len(races),
        "horses": sum(len(race.horses) for race in races),
        "skipped": dict(skipped),
    }
    return races, meta


def current_score(horse: dict, _race: RaceSample) -> tuple[float, dict[str, float]]:
    matrix_scores = dict(horse["auto"]["matrix_scores"])
    return float(horse["auto"]["ability_score"]), matrix_scores


def engine_score(engine_cls: type[RacingEngine], horse: dict, race: RaceSample) -> tuple[float, dict[str, float]]:
    auto = engine_cls(horse["data"], race.race_context).analyze_horse()
    return float(auto["ability_score"]), dict(auto["matrix_scores"])


def additive_trainer_score(fn: Callable, combo_priors: dict) -> Callable[[dict, RaceSample], tuple[float, dict[str, float]]]:
    def _score(horse: dict, _race: RaceSample) -> tuple[float, dict[str, float]]:
        trainer_signal, _notes = fn(horse, combo_priors)
        matrix_scores = dict(horse["auto"]["matrix_scores"])
        matrix_scores["trainer_signal"] = float(trainer_signal)
        return _ability(matrix_scores), matrix_scores

    return _score


def change_quality_only_score(horse: dict, _race: RaceSample) -> tuple[float, dict[str, float]]:
    delta, _notes = horse_specific_jockey_change_adjustment(horse)
    matrix_scores = dict(horse["auto"]["matrix_scores"])
    matrix_scores["trainer_signal"] = clip_score(float(matrix_scores["trainer_signal"]) + delta)
    return _ability(matrix_scores), matrix_scores


def direct_pair_damped_score(horse: dict, _race: RaceSample) -> tuple[float, dict[str, float]]:
    data = horse["data"].get("_data", {}) if isinstance(horse["data"].get("_data"), dict) else {}
    combo = parse_current_jockey_record(str(data.get("jockey_combo_block", "")))
    delta = 0.0
    if combo:
        if combo["starts"] >= 3 and combo["places"] >= 2 and (
            combo["place_rate"] >= 50.0 or combo["win_rate"] >= 20.0 or combo["avg_finish"] <= 3.5
        ):
            delta += 1.2
        elif combo["starts"] >= 2 and combo["place_rate"] >= 50.0 and combo["avg_finish"] <= 4.0:
            delta += 0.7
        elif combo["starts"] >= 3 and combo["place_rate"] == 0.0 and combo["avg_finish"] >= 7.0:
            delta -= 1.2
        elif combo["starts"] >= 5 and combo["place_rate"] <= 20.0 and combo["avg_finish"] >= 6.5:
            delta -= 0.7
    matrix_scores = dict(horse["auto"]["matrix_scores"])
    matrix_scores["trainer_signal"] = clip_score(float(matrix_scores["trainer_signal"]) + delta)
    return _ability(matrix_scores), matrix_scores


def direct_pair_damped_change_quality_score(horse: dict, race: RaceSample) -> tuple[float, dict[str, float]]:
    _ability_value, matrix_scores = direct_pair_damped_score(horse, race)
    change_delta, _notes = horse_specific_jockey_change_adjustment(horse)
    matrix_scores["trainer_signal"] = clip_score(float(matrix_scores["trainer_signal"]) + change_delta * 0.5)
    return _ability(matrix_scores), matrix_scores


def evaluate_pick_order(picks: list[int], actual_pos: dict[int, int]) -> dict:
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    winner = actual_top3[0] if actual_top3 else None
    hits = sum(1 for horse in picks[:3] if horse in actual_top3_set)
    winner_rank = next((idx for idx, horse in enumerate(picks, start=1) if horse == winner), len(actual_pos) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse in picks[:4] if horse in set(actual_top4))
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )
    return {
        "picks": picks[:4],
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
        "order_issue": order_issue,
    }


def evaluate_model(races: list[RaceSample], score_fn: Callable[[dict, RaceSample], tuple[float, dict[str, float]]]) -> tuple[list[dict], dict]:
    results = []
    changed_horses = 0
    deltas = []
    for race in races:
        rows = []
        for horse in race.horses:
            ability, matrix_scores = score_fn(horse, race)
            base_trainer = float(horse["auto"]["matrix_scores"].get("trainer_signal", 0.0))
            cand_trainer = float(matrix_scores.get("trainer_signal", base_trainer))
            delta = cand_trainer - base_trainer
            if abs(delta) > 1e-9:
                changed_horses += 1
                deltas.append(delta)
            rows.append((horse["horse_num"], ability))
        ranked = sorted(rows, key=lambda item: (-item[1], item[0]))
        picks = [horse_num for horse_num, _ability_value in ranked]
        result = evaluate_pick_order(picks, race.actual_pos)
        result.update(
            {
                "meeting": race.meeting,
                "date": race.date,
                "venue": race.venue,
                "race_number": race.race_number,
                "distance": race.distance,
            }
        )
        results.append(result)
    trigger_meta = {
        "changed_horses": changed_horses,
        "avg_trainer_signal_delta": round(sum(deltas) / len(deltas), 4) if deltas else 0.0,
        "positive_deltas": sum(1 for value in deltas if value > 0),
        "negative_deltas": sum(1 for value in deltas if value < 0),
    }
    return results, trigger_meta


def slice_races(races: list[RaceSample], label: str) -> list[RaceSample]:
    if label == "all":
        return races
    if label == "happy_valley":
        return [race for race in races if race.venue == "跑馬地"]
    if label == "sha_tin":
        return [race for race in races if race.venue == "沙田"]
    if label == "target_2026_06_10":
        return [race for race in races if race.date == "2026-06-10" and race.venue == "跑馬地"]
    if label.startswith("happy_valley_"):
        distance = label.rsplit("_", 1)[-1]
        return [race for race in races if race.venue == "跑馬地" and _distance_token(race.distance) == distance]
    return []


def metric_delta(candidate: dict, baseline: dict) -> dict:
    keys = ("gold", "good", "min_threshold", "champion", "top3_has_champion", "order_issue")
    out = {key: candidate.get(key, 0) - baseline.get(key, 0) for key in keys}
    for key in ("avg_winner_rank", "mrr", "avg_pick1_finish", "avg_top4_hits"):
        out[key] = round(candidate.get(key, 0) - baseline.get(key, 0), 4)
    return out


def run() -> dict:
    races, meta = load_samples()
    combo_priors = load_combo_priors()
    score_fns: dict[str, Callable[[dict, RaceSample], tuple[float, dict[str, float]]]] = {
        "current_live": current_score,
        "trainer_v3_additive": additive_trainer_score(trainer_signal_candidate_v3, combo_priors),
        "trainer_v4_change_quality_additive": additive_trainer_score(trainer_signal_candidate_v4, combo_priors),
        "change_quality_only_additive": change_quality_only_score,
        "direct_pair_damped": direct_pair_damped_score,
        "direct_pair_damped_change_quality": direct_pair_damped_change_quality_score,
    }
    for name, engine_cls in ENGINE_MODELS.items():
        score_fns[name] = lambda horse, race, cls=engine_cls: engine_score(cls, horse, race)

    scopes = [
        "all",
        "happy_valley",
        "sha_tin",
        "happy_valley_1200",
        "happy_valley_1650",
        "happy_valley_1800",
        "target_2026_06_10",
    ]
    payload = {
        "meta": meta,
        "matrix_weights": MATRIX_WEIGHTS,
        "contract": "ability-only ranking; no draw micro tiebreak; only trainer_signal feature context is varied",
        "scopes": {},
    }
    for scope in scopes:
        subset = slice_races(races, scope)
        if not subset:
            continue
        scope_payload = {}
        baseline_summary = None
        for model_name, score_fn in score_fns.items():
            model_results, trigger_meta = evaluate_model(subset, score_fn)
            summary = summarize_model_races(model_results)
            if model_name == "current_live":
                baseline_summary = summary
            scope_payload[model_name] = {
                "summary": summary,
                "trainer_signal_change": trigger_meta,
            }
            if baseline_summary is not None and model_name != "current_live":
                scope_payload[model_name]["delta_vs_current"] = metric_delta(summary, baseline_summary)
        payload["scopes"][scope] = scope_payload
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Shadow-test HKJC trainer/jockey context feature candidates.")
    parser.add_argument("--output", type=Path, default=Path("scratch/hkjc_trainer_context_feature_test.json"))
    args = parser.parse_args()
    payload = run()
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
