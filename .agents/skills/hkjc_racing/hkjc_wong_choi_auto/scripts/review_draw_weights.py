#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SCRIPT_DIR / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"))

from engine_core import RacingEngine
from scoring import clip_score
from hkjc_results_db import get_full_results_csv, get_comprehensive_stats_root

RESULTS_CSV = get_full_results_csv()
STATS_ROOT = get_comprehensive_stats_root()
CURRENT_WEIGHTS = {
    "sectional": 0.20,
    "trainer_signal": 0.18,
    "stability": 0.12,
    "race_shape": 0.28,
    "class_advantage": 0.08,
    "horse_health": 0.09,
    "form_line": 0.05,
}
OUTER_WEIGHT_GRID = {
    "sectional": [0.18, 0.20, 0.22],
    "trainer_signal": [0.16, 0.18, 0.20],
    "stability": [0.12, 0.14, 0.16],
    "race_shape": [0.24, 0.26, 0.28],
    "class_advantage": [0.08, 0.10, 0.12],
    "horse_health": [0.05, 0.07, 0.09],
    "form_line": [0.03, 0.05, 0.07],
}
VENUE_MAP = {
    "HappyValley": "跑馬地",
    "ShaTin": "沙田",
    "Sha_Tin": "沙田",
}
JOCKEY_DRAW_PRIORS = STATS_ROOT / "Full" / "jockey_draw_performance.csv"


@dataclass
class RaceSample:
    meeting: str
    date: str
    venue: str
    race_number: int
    distance: str
    race_class: str
    race_context: dict
    horses: list[dict]
    actual_pos: dict[str, int]


def normalize_horse_name(name: str) -> str:
    text = re.sub(r"\([A-Z0-9]+\)", "", str(name or ""))
    return re.sub(r"\s+", "", text).strip()


def build_actual_results_index() -> dict[tuple[str, str, int], dict[str, int]]:
    index: dict[tuple[str, str, int], dict[str, int]] = {}
    with RESULTS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                key = (row["Date"], row["Venue"], int(row["RaceNo"]))
                index.setdefault(key, {})[normalize_horse_name(row["Horse"])] = int(row["Rank"])
            except (KeyError, TypeError, ValueError):
                continue
    return index


def discover_hkjc_meetings() -> list[Path]:
    candidates = []
    for csv_path in ROOT.glob("**/HKJC_Auto_Scoring.csv"):
        parent = csv_path.parent
        if "ShaTin" not in parent.name and "HappyValley" not in parent.name and "Sha_Tin" not in parent.name:
            continue
        if not list(parent.glob("Race_*_Logic.json")):
            continue
        candidates.append(parent)
    return sorted(set(candidates))


def parse_meeting_identity(path: Path) -> tuple[str, str]:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name)
    date = match.group(1) if match else ""
    venue = next((mapped for token, mapped in VENUE_MAP.items() if token in path.name), "")
    return date, venue


def load_race_samples(result_index: dict[tuple[str, str, int], dict[str, int]]) -> list[RaceSample]:
    samples: list[RaceSample] = []
    for meeting_dir in discover_hkjc_meetings():
        date, venue = parse_meeting_identity(meeting_dir)
        if not date or not venue:
            continue
        for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json")):
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_context = logic.get("race_analysis", {})
            race_number = int(race_context.get("race_number") or 0)
            actual_pos = result_index.get((date, venue, race_number), {})
            if not actual_pos:
                continue
            horses = []
            for horse_num, horse in logic.get("horses", {}).items():
                name = normalize_horse_name(horse.get("horse_name", ""))
                if name not in actual_pos:
                    continue
                live_auto = RacingEngine(horse, race_context).analyze_horse()
                horses.append(
                    {
                        "horse_num": str(horse_num),
                        "horse_name": horse.get("horse_name", ""),
                        "data": horse,
                        "auto": live_auto,
                    }
                )
            if len(horses) < 4:
                continue
            samples.append(
                RaceSample(
                    meeting=meeting_dir.name,
                    date=date,
                    venue=venue,
                    race_number=race_number,
                    distance=str(race_context.get("distance") or ""),
                    race_class=str(race_context.get("race_class") or ""),
                    race_context=race_context,
                    horses=horses,
                    actual_pos=actual_pos,
                )
            )
    return samples


def _ability(matrix_scores: dict[str, float], weights: dict[str, float]) -> float:
    return round(sum(float(matrix_scores[key]) * weights[key] for key in weights), 4)


def _draw_candidate_score(horse: dict) -> float | None:
    draw = horse.get("barrier") or horse.get("draw")
    try:
        draw = int(draw)
    except (TypeError, ValueError):
        return None
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    if draw <= 4:
        score = 75.0
    elif draw <= 8:
        score = 65.0
    else:
        score = 50.0

    fit = str(data.get("draw_position_fit") or "")
    verdict = str(data.get("draw_verdict") or "")
    trend = str(data.get("position_pi") or "")

    if "✅匹配" in fit:
        score += 5.0
    elif "❌錯配" in fit:
        score -= 9.0
    elif "偏好走外但起步在內" in fit or "偏好走內但被迫走外" in fit:
        score -= 6.0
    elif "需主動切入內疊" in fit:
        score -= 4.0

    if "✅有利" in verdict:
        score += 3.0
    elif "❌不利" in verdict:
        score -= 5.0

    if "上升軌" in trend:
        score += 2.0
    elif "微升" in trend:
        score += 1.0
    elif "微跌" in trend:
        score -= 1.0
    elif "衰退中" in trend:
        score -= 3.0

    return clip_score(score)


def _draw_signal_v3a_score(horse: dict, base_score: float) -> float:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    score = float(base_score)
    fit = str(data.get("draw_position_fit") or "")
    verdict = str(data.get("draw_verdict") or "")
    trend = str(data.get("position_pi") or "")

    if "❌錯配" in fit:
        score -= 5.0
    elif "偏好走內但被迫走外" in fit or "偏好走外但起步在內" in fit:
        score -= 3.0
    elif "需主動切入內疊" in fit:
        score -= 2.0
    elif "偏好:" in fit and ("走內有利" in fit or "走外有利" in fit):
        score += 1.5

    if "✅有利" in verdict:
        score += 2.0
    elif "❌不利" in verdict:
        score -= 2.0

    if "上升軌" in trend:
        score += 1.0
    elif "衰退中" in trend:
        score -= 1.5

    return clip_score(score)


def _load_jockey_draw_priors() -> dict[tuple[str, str], dict[str, float]]:
    priors = {}
    with JOCKEY_DRAW_PRIORS.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            priors[(row["Jockey"], row["Draw"])] = {
                "starts": float(row["Starts"]),
                "wins": float(row["Wins"]),
                "places": float(row["Places"]),
                "win_rate": float(row["WinRate"]),
                "place_rate": float(row["PlaceRate"]),
            }
    return priors


def _horse_draw_history_adjustment(horse: dict, draw_num: int) -> float:
    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    fit = str(data.get("draw_position_fit") or "")
    match = re.search(r"內檔\(1-4\)上名率(\d+)%.*?中檔\(5-8\)上名率(\d+)%.*?外檔\(9\+\)上名率(\d+)%", fit)
    if not match:
        return 0.0
    inner, middle, outer = (float(match.group(i)) for i in range(1, 4))
    if draw_num <= 4:
        current = inner
        best_other = max(middle, outer)
    elif draw_num <= 8:
        current = middle
        best_other = max(inner, outer)
    else:
        current = outer
        best_other = max(inner, middle)
    edge = current - best_other
    if edge >= 10.0:
        return 1.5
    if edge <= -10.0:
        return -1.5
    return 0.0


def _draw_signal_v3b_score(horse: dict, base_score: float, jockey_draw_priors: dict[tuple[str, str], dict[str, float]]) -> float:
    score = _draw_signal_v3a_score(horse, base_score)
    draw = horse.get("barrier") or horse.get("draw")
    jockey = str(horse.get("jockey") or "").strip()
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return score

    prior = jockey_draw_priors.get((jockey, str(draw_num)))
    if prior and prior["starts"] >= 35:
        if prior["win_rate"] >= 12.0 or prior["place_rate"] >= 30.0:
            score += 1.0
        elif prior["win_rate"] <= 4.0 and prior["place_rate"] <= 18.0:
            score -= 1.0

    score += _horse_draw_history_adjustment(horse, draw_num)
    return clip_score(score)


def _normalize_venue(value) -> str:
    text = str(value or "").strip()
    if text in {"HV", "跑馬地"}:
        return "跑馬地"
    if text in {"ST", "沙田"}:
        return "沙田"
    return text


def _normalize_distance(value) -> str:
    return str(value or "").replace("m", "").strip()


def _tie_break_draw_bonus(horse: dict, race_context: dict, features: dict[str, float]) -> float:
    bonus = 0.0
    draw = horse.get("barrier") or horse.get("draw")
    try:
        draw_num = int(draw)
    except (TypeError, ValueError):
        return 0.0

    data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
    fit = str(data.get("draw_position_fit") or "")
    trend = str(data.get("position_pi") or "")
    verdict = str(data.get("draw_verdict") or "")

    if "✅匹配" in fit:
        bonus += 1.5
    elif "❌錯配" in fit:
        bonus -= 2.0
    elif "偏好走外但起步在內" in fit or "偏好走內但被迫走外" in fit:
        bonus -= 1.5
    elif "需主動切入內疊" in fit:
        bonus -= 1.0

    if "上升軌" in trend:
        bonus += 0.8
    elif "衰退中" in trend:
        bonus -= 0.8

    if "✅有利" in verdict:
        bonus += 0.7
    elif "❌不利" in verdict:
        bonus -= 0.7

    bonus += _horse_draw_history_adjustment(horse, draw_num) * 0.5

    venue = _normalize_venue(race_context.get("venue"))
    distance = _normalize_distance(race_context.get("distance"))
    if venue == "跑馬地" and distance == "1650":
        if draw_num in {1, 2, 3, 7, 8}:
            bonus += 0.5
        if draw_num in {11, 12}:
            bonus -= 0.5

    if clip_score(features.get("draw_score", 60.0)) <= 55.0:
        bonus *= 1.15
    return bonus


def _race_shape_score(matrix_scores: dict[str, float]) -> float:
    return float(matrix_scores.get("race_shape", 0.0))


def _is_hv_middle_distance(race_context: dict) -> bool:
    return _normalize_venue(race_context.get("venue")) == "跑馬地" and _normalize_distance(race_context.get("distance")) in {"1650", "1800"}


def _score_micro_tiebreak_race(
    race: RaceSample,
    *,
    hv_only: bool = False,
    min_race_shape: float | None = None,
    max_gap: float = 0.8,
    min_bonus_edge: float = 0.0,
) -> dict:
    ranked = sorted(
        [
            {
                "horse_num": horse["horse_num"],
                "horse_name": normalize_horse_name(horse["horse_name"]),
                "ability": float(horse["auto"]["ability_score"]),
                "matrix_scores": dict(horse["auto"]["matrix_scores"]),
                "features": dict(horse["auto"]["feature_scores"]),
                "horse": horse["data"],
            }
            for horse in race.horses
        ],
        key=lambda item: item["ability"],
        reverse=True,
    )

    boosts: dict[str, float] = {}
    trigger = False
    swapped = False
    before_top4 = [row["horse_name"] for row in ranked[:4]]
    trigger_info = ""
    if len(ranked) >= 4:
        third = ranked[2]
        fourth = ranked[3]
        race_shape_ok = True
        if min_race_shape is not None:
            race_shape_ok = min(_race_shape_score(third["matrix_scores"]), _race_shape_score(fourth["matrix_scores"])) >= min_race_shape
        venue_ok = True
        if hv_only:
            venue_ok = _is_hv_middle_distance(race.race_context)
        if abs(third["ability"] - fourth["ability"]) <= max_gap and race_shape_ok and venue_ok:
            third_bonus = _tie_break_draw_bonus(third["horse"], race.race_context, third["features"])
            fourth_bonus = _tie_break_draw_bonus(fourth["horse"], race.race_context, fourth["features"])
            if abs(third_bonus - fourth_bonus) >= min_bonus_edge:
                trigger = True
                boosts[third["horse_num"]] = third_bonus
                boosts[fourth["horse_num"]] = fourth_bonus
                trigger_info = (
                    f"{third['horse_name']}({third['ability']:.2f},{third_bonus:+.2f}) vs "
                    f"{fourth['horse_name']}({fourth['ability']:.2f},{fourth_bonus:+.2f})"
                )

    rescored = [
        {
            "horse_num": row["horse_num"],
            "horse_name": row["horse_name"],
            "ability": row["ability"] + boosts.get(row["horse_num"], 0.0),
        }
        for row in ranked
    ]
    after_ranked = sorted(rescored, key=lambda item: item["ability"], reverse=True)
    after_top4 = [row["horse_name"] for row in after_ranked[:4]]
    if before_top4 != after_top4:
        swapped = True
    result = _evaluate_race(race.actual_pos, rescored)
    result["triggered"] = trigger
    result["swapped"] = swapped
    result["before_top4"] = before_top4
    result["after_top4"] = after_top4
    result["trigger_info"] = trigger_info
    result["meeting"] = race.meeting
    result["race_number"] = race.race_number
    return result


def _candidate_outer_weight_sets() -> list[dict[str, float]]:
    keys = list(OUTER_WEIGHT_GRID.keys())
    candidates: list[dict[str, float]] = []
    for values in product(*(OUTER_WEIGHT_GRID[key] for key in keys)):
        weights = {key: round(value, 2) for key, value in zip(keys, values)}
        if abs(sum(weights.values()) - 1.0) > 1e-9:
            continue
        if not (weights["race_shape"] >= weights["trainer_signal"] >= weights["class_advantage"]):
            continue
        if weights["race_shape"] < weights["sectional"]:
            continue
        if weights["form_line"] > weights["horse_health"]:
            continue
        if weights["stability"] < 0.12 or weights["trainer_signal"] < 0.16:
            continue
        candidates.append(weights)
    return candidates


def _evaluate_race(actual_pos: dict[str, int], scored_rows: list[dict]) -> dict:
    ranked = sorted(scored_rows, key=lambda item: item["ability"], reverse=True)
    picks = [item["horse_name"] for item in ranked[:4]]
    actual_top3 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    hits = sum(1 for horse_name in picks[:3] if horse_name in actual_top3_set)
    winner = actual_top3[0] if actual_top3 else None
    winner_rank = next((idx for idx, row in enumerate(ranked, start=1) if row["horse_name"] == winner), len(ranked) + 1)
    pick1_finish = actual_pos.get(picks[0], 99) if picks else 99
    top4_hits = sum(1 for horse_name in picks if horse_name in set(actual_top4))
    order_issue = False
    if len(picks) >= 4:
        order_issue = min(actual_pos.get(picks[2], 99), actual_pos.get(picks[3], 99)) < min(
            actual_pos.get(picks[0], 99), actual_pos.get(picks[1], 99)
        )
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
        "order_issue": order_issue,
    }


def _summarize(rows: list[dict]) -> dict:
    total = len(rows)
    return {
        "races": total,
        "gold": sum(item["gold"] for item in rows),
        "good": sum(item["good"] for item in rows),
        "min_threshold": sum(item["min_threshold"] for item in rows),
        "single": sum(item["single"] for item in rows),
        "champion": sum(item["champion"] for item in rows),
        "top3_has_champion": sum(item["top3_has_champion"] for item in rows),
        "order_issue": sum(item["order_issue"] for item in rows),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in rows) / total, 3),
        "mrr": round(sum(item["mrr"] for item in rows) / total, 4),
        "avg_pick1_finish": round(sum(item["pick1_finish"] for item in rows) / total, 3),
        "avg_top4_hits": round(sum(item["top4_hits"] for item in rows) / total, 3),
    }


def _micro_report(baseline_rows: list[dict], candidate_rows: list[dict]) -> dict:
    triggered = [row for row in candidate_rows if row.get("triggered")]
    swapped = [row for row in candidate_rows if row.get("swapped")]
    improved = []
    worsened = []
    for base, cand in zip(baseline_rows, candidate_rows):
        base_tuple = (base["champion"], base["gold"], base["good"], base["mrr"], -base["order_issue"])
        cand_tuple = (cand["champion"], cand["gold"], cand["good"], cand["mrr"], -cand["order_issue"])
        row = {
            "meeting": cand["meeting"],
            "race_number": cand["race_number"],
            "before_top4": cand["before_top4"],
            "after_top4": cand["after_top4"],
            "trigger_info": cand["trigger_info"],
        }
        if cand_tuple > base_tuple:
            improved.append(row)
        elif cand_tuple < base_tuple:
            worsened.append(row)
    return {
        "triggered_count": len(triggered),
        "swapped_count": len(swapped),
        "improved": improved,
        "worsened": worsened,
        "sample_triggers": [
            {
                "meeting": row["meeting"],
                "race_number": row["race_number"],
                "before_top4": row["before_top4"],
                "after_top4": row["after_top4"],
                "trigger_info": row["trigger_info"],
            }
            for row in triggered[:8]
        ],
    }


def score_models(
    races: list[RaceSample],
    weights: dict[str, float],
    draw_mode: str = "live",
    jockey_draw_priors: dict[tuple[str, str], dict[str, float]] | None = None,
) -> list[dict]:
    model_races = []
    for race in races:
        scored = []
        for horse in race.horses:
            matrix_scores = dict(horse["auto"]["matrix_scores"])
            if draw_mode == "v2":
                score = _draw_candidate_score(horse["data"])
                if score is not None:
                    matrix_scores["race_shape"] = score
            elif draw_mode == "v3a":
                matrix_scores["race_shape"] = _draw_signal_v3a_score(horse["data"], matrix_scores["race_shape"])
            elif draw_mode == "v3b":
                matrix_scores["race_shape"] = _draw_signal_v3b_score(
                    horse["data"],
                    matrix_scores["race_shape"],
                    jockey_draw_priors or {},
                )
            scored.append(
                {
                    "horse_num": horse["horse_num"],
                    "horse_name": normalize_horse_name(horse["horse_name"]),
                    "ability": _ability(matrix_scores, weights),
                }
            )
        model_races.append(_evaluate_race(race.actual_pos, scored))
    return model_races


def pick_best_weight_candidate(
    races: list[RaceSample],
    draw_mode: str = "live",
    jockey_draw_priors: dict[tuple[str, str], dict[str, float]] | None = None,
) -> tuple[dict[str, float] | None, dict | None]:
    best_weights = None
    best_stats = None
    for weights in _candidate_outer_weight_sets():
        stats = _summarize(score_models(races, weights, draw_mode=draw_mode, jockey_draw_priors=jockey_draw_priors))
        if best_stats is None:
            best_weights, best_stats = weights, stats
            continue
        current_tuple = (
            stats["champion"],
            stats["gold"],
            stats["good"],
            stats["mrr"],
            -stats["order_issue"],
            -stats["avg_pick1_finish"],
        )
        best_tuple = (
            best_stats["champion"],
            best_stats["gold"],
            best_stats["good"],
            best_stats["mrr"],
            -best_stats["order_issue"],
            -best_stats["avg_pick1_finish"],
        )
        if current_tuple > best_tuple:
            best_weights, best_stats = weights, stats
    return best_weights, best_stats


def render_table(rows: list[list[object]]) -> str:
    headers = ["Model", "Races", "Gold", "Good", "Champion", "Top3 Champ", "Order Issue", "MRR", "Avg Pick1 Finish", "Avg Top4 Hits"]
    out = ["| " + " | ".join(headers) + " |", "|---" * len(headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(col) for col in row) + " |")
    return "\n".join(out)


def main() -> int:
    result_index = build_actual_results_index()
    races = load_race_samples(result_index)
    jockey_draw_priors = _load_jockey_draw_priors()

    baseline = _summarize(score_models(races, CURRENT_WEIGHTS, draw_mode="live", jockey_draw_priors=jockey_draw_priors))
    draw_v2 = _summarize(score_models(races, CURRENT_WEIGHTS, draw_mode="v2", jockey_draw_priors=jockey_draw_priors))
    draw_v3a = _summarize(score_models(races, CURRENT_WEIGHTS, draw_mode="v3a", jockey_draw_priors=jockey_draw_priors))
    draw_v3b = _summarize(score_models(races, CURRENT_WEIGHTS, draw_mode="v3b", jockey_draw_priors=jockey_draw_priors))
    baseline_micro_rows = [_score_micro_tiebreak_race(race, max_gap=0.0, min_bonus_edge=999.0) for race in races]
    micro_rows = [_score_micro_tiebreak_race(race) for race in races]
    micro_tiebreak = _summarize(micro_rows)
    micro_tiebreak_hv_mid = _summarize([_score_micro_tiebreak_race(race, hv_only=True) for race in races])
    micro_tiebreak_hv_mid_shape60 = _summarize([_score_micro_tiebreak_race(race, hv_only=True, min_race_shape=60.0) for race in races])
    micro_tiebreak_hv_mid_shape60_gap06 = _summarize([_score_micro_tiebreak_race(race, hv_only=True, min_race_shape=60.0, max_gap=0.6) for race in races])
    micro_tiebreak_hv_mid_shape60_gap08_edge05 = _summarize([_score_micro_tiebreak_race(race, hv_only=True, min_race_shape=60.0, max_gap=0.8, min_bonus_edge=0.5) for race in races])
    best_weights, best_weight_stats = pick_best_weight_candidate(races, draw_mode="live", jockey_draw_priors=jockey_draw_priors)
    best_draw_weights, best_draw_weight_stats = pick_best_weight_candidate(races, draw_mode="v3a", jockey_draw_priors=jockey_draw_priors)
    micro_report = _micro_report(baseline_micro_rows, micro_rows)

    print("# HKJC Auto Draw/Weight Review\n")
    print(render_table([
        ["current_live", baseline["races"], baseline["gold"], baseline["good"], baseline["champion"], baseline["top3_has_champion"], baseline["order_issue"], baseline["mrr"], baseline["avg_pick1_finish"], baseline["avg_top4_hits"]],
        ["draw_signal_v2", draw_v2["races"], draw_v2["gold"], draw_v2["good"], draw_v2["champion"], draw_v2["top3_has_champion"], draw_v2["order_issue"], draw_v2["mrr"], draw_v2["avg_pick1_finish"], draw_v2["avg_top4_hits"]],
        ["draw_signal_v3a", draw_v3a["races"], draw_v3a["gold"], draw_v3a["good"], draw_v3a["champion"], draw_v3a["top3_has_champion"], draw_v3a["order_issue"], draw_v3a["mrr"], draw_v3a["avg_pick1_finish"], draw_v3a["avg_top4_hits"]],
        ["draw_signal_v3b", draw_v3b["races"], draw_v3b["gold"], draw_v3b["good"], draw_v3b["champion"], draw_v3b["top3_has_champion"], draw_v3b["order_issue"], draw_v3b["mrr"], draw_v3b["avg_pick1_finish"], draw_v3b["avg_top4_hits"]],
        ["draw_micro_tiebreak", micro_tiebreak["races"], micro_tiebreak["gold"], micro_tiebreak["good"], micro_tiebreak["champion"], micro_tiebreak["top3_has_champion"], micro_tiebreak["order_issue"], micro_tiebreak["mrr"], micro_tiebreak["avg_pick1_finish"], micro_tiebreak["avg_top4_hits"]],
        ["draw_micro_tiebreak_hv_mid", micro_tiebreak_hv_mid["races"], micro_tiebreak_hv_mid["gold"], micro_tiebreak_hv_mid["good"], micro_tiebreak_hv_mid["champion"], micro_tiebreak_hv_mid["top3_has_champion"], micro_tiebreak_hv_mid["order_issue"], micro_tiebreak_hv_mid["mrr"], micro_tiebreak_hv_mid["avg_pick1_finish"], micro_tiebreak_hv_mid["avg_top4_hits"]],
        ["draw_micro_tiebreak_hv_mid_shape60", micro_tiebreak_hv_mid_shape60["races"], micro_tiebreak_hv_mid_shape60["gold"], micro_tiebreak_hv_mid_shape60["good"], micro_tiebreak_hv_mid_shape60["champion"], micro_tiebreak_hv_mid_shape60["top3_has_champion"], micro_tiebreak_hv_mid_shape60["order_issue"], micro_tiebreak_hv_mid_shape60["mrr"], micro_tiebreak_hv_mid_shape60["avg_pick1_finish"], micro_tiebreak_hv_mid_shape60["avg_top4_hits"]],
        ["draw_micro_tiebreak_hv_mid_shape60_gap06", micro_tiebreak_hv_mid_shape60_gap06["races"], micro_tiebreak_hv_mid_shape60_gap06["gold"], micro_tiebreak_hv_mid_shape60_gap06["good"], micro_tiebreak_hv_mid_shape60_gap06["champion"], micro_tiebreak_hv_mid_shape60_gap06["top3_has_champion"], micro_tiebreak_hv_mid_shape60_gap06["order_issue"], micro_tiebreak_hv_mid_shape60_gap06["mrr"], micro_tiebreak_hv_mid_shape60_gap06["avg_pick1_finish"], micro_tiebreak_hv_mid_shape60_gap06["avg_top4_hits"]],
        ["draw_micro_tiebreak_hv_mid_shape60_gap08_edge05", micro_tiebreak_hv_mid_shape60_gap08_edge05["races"], micro_tiebreak_hv_mid_shape60_gap08_edge05["gold"], micro_tiebreak_hv_mid_shape60_gap08_edge05["good"], micro_tiebreak_hv_mid_shape60_gap08_edge05["champion"], micro_tiebreak_hv_mid_shape60_gap08_edge05["top3_has_champion"], micro_tiebreak_hv_mid_shape60_gap08_edge05["order_issue"], micro_tiebreak_hv_mid_shape60_gap08_edge05["mrr"], micro_tiebreak_hv_mid_shape60_gap08_edge05["avg_pick1_finish"], micro_tiebreak_hv_mid_shape60_gap08_edge05["avg_top4_hits"]],
        ["best_7d_retune", best_weight_stats["races"], best_weight_stats["gold"], best_weight_stats["good"], best_weight_stats["champion"], best_weight_stats["top3_has_champion"], best_weight_stats["order_issue"], best_weight_stats["mrr"], best_weight_stats["avg_pick1_finish"], best_weight_stats["avg_top4_hits"]],
        ["draw_v3a_plus_7d_retune", best_draw_weight_stats["races"], best_draw_weight_stats["gold"], best_draw_weight_stats["good"], best_draw_weight_stats["champion"], best_draw_weight_stats["top3_has_champion"], best_draw_weight_stats["order_issue"], best_draw_weight_stats["mrr"], best_draw_weight_stats["avg_pick1_finish"], best_draw_weight_stats["avg_top4_hits"]],
    ]))
    print()
    print("## Best 7D Retune")
    print(best_weights)
    print()
    print("## Best Draw+7D Retune")
    print(best_draw_weights)
    print()
    print("## Draw Micro Tiebreak Review")
    print({
        "triggered_count": micro_report["triggered_count"],
        "swapped_count": micro_report["swapped_count"],
        "improved_count": len(micro_report["improved"]),
        "worsened_count": len(micro_report["worsened"]),
    })
    print()
    print("### Sample Triggers")
    for row in micro_report["sample_triggers"]:
        print(f"- {row['meeting']} R{row['race_number']}: {row['trigger_info']} | {row['before_top4']} -> {row['after_top4']}")
    print()
    print("### Improved Examples")
    for row in micro_report["improved"][:8]:
        print(f"- {row['meeting']} R{row['race_number']}: {row['trigger_info']} | {row['before_top4']} -> {row['after_top4']}")
    print()
    print("### Worsened Examples")
    for row in micro_report["worsened"][:8]:
        print(f"- {row['meeting']} R{row['race_number']}: {row['trigger_info']} | {row['before_top4']} -> {row['after_top4']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
