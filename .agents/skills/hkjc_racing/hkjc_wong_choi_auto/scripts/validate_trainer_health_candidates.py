#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[5]
SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_DIR = SCRIPT_DIR / "racing_engine"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"))

from engine_core import RacingEngine
from hkjc_results_db import get_combo_priors_csv, get_full_results_csv
from renderer import _draw_micro_bonus

RESULTS_CSV = get_full_results_csv()
OUTER_WEIGHTS = {
    "sectional": 0.20,
    "trainer_signal": 0.18,
    "stability": 0.14,
    "race_shape": 0.26,
    "class_advantage": 0.10,
    "horse_health": 0.07,
    "form_line": 0.05,
}
VENUE_MAP = {
    "HappyValley": "跑馬地",
    "ShaTin": "沙田",
    "Sha_Tin": "沙田",
}


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


def parse_pct(value: str) -> float:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    return float(match.group(0)) if match else 0.0


def table_cols(line: str) -> list[str]:
    return [col.strip() for col in re.split(r"\s*\|\s*", line.strip().strip("|"))]


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
                if normalize_horse_name(horse.get("horse_name", "")) not in actual_pos:
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


def parse_current_jockey_record(block: str) -> dict[str, float] | None:
    for line in str(block or "").splitlines():
        if line.strip().startswith("|") and "← 今場" in line:
            cols = table_cols(line)
            if len(cols) < 8:
                return None
            try:
                return {
                    "starts": float(cols[1]),
                    "wins": float(cols[2]),
                    "places": float(cols[4]),
                    "avg_finish": float(cols[5]),
                    "win_rate": parse_pct(cols[6]),
                    "place_rate": parse_pct(cols[7]),
                }
            except ValueError:
                return None
    return None


def parse_jockey_combo_rows(block: str, current_jockey: str = "") -> list[dict[str, float | str | bool]]:
    rows: list[dict[str, float | str | bool]] = []
    for line in str(block or "").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cols = table_cols(line)
        if len(cols) < 8:
            continue
        if cols[0] in {"騎師", "------", "#", "---"}:
            continue
        if cols[0].startswith("#") or cols[0].isdigit():
            continue
        jockey_name = cols[0].replace("← 今場", "").strip()
        try:
            rows.append(
                {
                    "jockey": jockey_name,
                    "starts": float(cols[1]),
                    "wins": float(cols[2]),
                    "places": float(cols[4]),
                    "avg_finish": float(cols[5]),
                    "win_rate": parse_pct(cols[6]),
                    "place_rate": parse_pct(cols[7]),
                    "is_current": "← 今場" in cols[0] or (current_jockey and jockey_name == current_jockey),
                }
            )
        except ValueError:
            continue
    return rows


def parse_recent_jockey_history(block: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    capture = False
    for raw_line in str(block or "").splitlines():
        line = raw_line.strip()
        if "近6場騎師歷史" in line:
            capture = True
            continue
        if not capture or not line.startswith("|"):
            continue
        cols = table_cols(line)
        if len(cols) < 5:
            continue
        if cols[0] in {"#", "---"} or cols[0].startswith("---"):
            continue
        if not re.fullmatch(r"\d+", cols[0]):
            continue
        rows.append(
            {
                "index": cols[0],
                "date": cols[1],
                "jockey": cols[2],
                "finish": cols[3],
                "note": cols[4],
            }
        )
    rows.sort(key=lambda row: int(row["index"]))
    return rows


def jockey_row_strength(row: dict[str, float | str | bool] | None) -> float:
    if not row:
        return -99.0
    starts = float(row["starts"])
    wins = float(row["wins"])
    places = float(row["places"])
    place_rate = float(row["place_rate"])
    win_rate = float(row["win_rate"])
    avg_finish = float(row["avg_finish"])
    sample = min(1.0, starts / 4.0)
    return (
        wins * 3.0
        + places * 1.4
        + place_rate * 0.08 * sample
        + win_rate * 0.12 * sample
        - avg_finish * 0.9 * sample
    )


def horse_specific_jockey_change_adjustment(horse: dict) -> tuple[float, list[str]]:
    data = horse["data"].get("_data", {}) if isinstance(horse["data"].get("_data"), dict) else {}
    block = str(data.get("jockey_combo_block", ""))
    current_jockey = str(horse["data"].get("jockey", "")).strip()
    if not block or not current_jockey:
        return 0.0, []

    combo_rows = parse_jockey_combo_rows(block, current_jockey=current_jockey)
    if not combo_rows:
        return 0.0, []
    row_by_jockey = {str(row["jockey"]): row for row in combo_rows}
    current_row = row_by_jockey.get(current_jockey)
    history_rows = parse_recent_jockey_history(block)
    previous_jockey = ""
    if history_rows:
        previous_jockey = history_rows[0]["jockey"].strip()
    changed = bool(previous_jockey and previous_jockey != current_jockey)
    if not changed:
        return 0.0, []

    previous_row = row_by_jockey.get(previous_jockey)
    best_other = None
    for row in combo_rows:
        if str(row["jockey"]) == current_jockey:
            continue
        if best_other is None or jockey_row_strength(row) > jockey_row_strength(best_other):
            best_other = row

    notes: list[str] = []
    delta = 0.0
    current_strength = jockey_row_strength(current_row)
    previous_strength = jockey_row_strength(previous_row)
    best_other_strength = jockey_row_strength(best_other)

    if current_row and previous_row:
        if float(current_row["starts"]) >= 2 and current_strength >= previous_strength + 2.5:
            delta += 2.5
            notes.append("換上此馬歷來表現更佳的騎師")
        elif float(previous_row["starts"]) >= 2 and previous_strength >= current_strength + 2.5:
            delta -= 2.5
            notes.append("由此馬較合拍騎師轉走")
    elif current_row and not previous_row:
        if float(current_row["starts"]) >= 2 and float(current_row["place_rate"]) >= 50.0:
            delta += 1.5
            notes.append("換上曾對此馬有直接支持的騎師")
    elif previous_row and not current_row:
        if float(previous_row["starts"]) >= 2 and (
            float(previous_row["wins"]) >= 1 or float(previous_row["place_rate"]) >= 50.0
        ):
            delta -= 1.5
            notes.append("今場改配未證明能複製前任人馬效果")

    if current_row and best_other and str(best_other["jockey"]) != previous_jockey:
        if current_strength >= best_other_strength + 2.5 and float(current_row["starts"]) >= 2:
            delta += 0.5
            notes.append("現任配搭亦優於其他曾策騎者")
        elif best_other_strength >= current_strength + 3.5 and float(best_other["starts"]) >= 2:
            delta -= 0.5
            notes.append("現任配搭未及此馬最合拍騎師")

    return max(-3.0, min(3.0, round(delta, 2))), notes


def load_combo_priors() -> dict[tuple[str, str], dict[str, float]]:
    path = get_combo_priors_csv()
    priors = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            priors[(row["Jockey"], row["Trainer"])] = {
                "starts": float(row["Starts"]),
                "wins": float(row["Wins"]),
                "places": float(row["Places"]),
                "win_rate": float(row["WinRate"]),
                "place_rate": float(row["PlaceRate"]),
            }
    return priors


def trainer_signal_candidate_v2(horse: dict, combo_priors: dict[tuple[str, str], dict[str, float]]) -> tuple[float, list[str]]:
    auto = horse["auto"]
    current = float(auto["matrix_scores"]["trainer_signal"])
    data = horse["data"].get("_data", {}) if isinstance(horse["data"].get("_data"), dict) else {}
    delta = 0.0
    notes: list[str] = []

    combo = parse_current_jockey_record(str(data.get("jockey_combo_block", "")))
    if combo:
        if combo["starts"] >= 3 and (combo["place_rate"] >= 50.0 or combo["win_rate"] >= 20.0):
            delta += 4.0
            notes.append("現任人馬合作歷史偏強")
        elif combo["starts"] >= 3 and combo["place_rate"] <= 15.0:
            delta -= 4.0
            notes.append("現任人馬合作歷史偏弱")
        elif combo["starts"] >= 2 and combo["place_rate"] >= 33.0:
            delta += 2.0
            notes.append("現任人馬合作有基本支持")

    combo_prior = combo_priors.get((horse["data"].get("jockey", ""), horse["data"].get("trainer", "")))
    if combo_prior:
        if combo_prior["starts"] >= 25 and combo_prior["place_rate"] >= 30.0:
            delta += 3.0
            notes.append("騎練組合長期 place rate 偏高")
        elif combo_prior["starts"] >= 12 and combo_prior["place_rate"] >= 25.0:
            delta += 1.5
            notes.append("騎練組合長期數據正面")
        elif combo_prior["starts"] >= 25 and combo_prior["place_rate"] < 18.0 and combo_prior["win_rate"] < 5.0:
            delta -= 3.0
            notes.append("騎練組合長期數據偏弱")
        elif combo_prior["starts"] >= 12 and combo_prior["place_rate"] < 15.0:
            delta -= 1.5
            notes.append("騎練組合樣本下表現一般")

    trainer_block = str(data.get("trackwork_trainer", ""))
    if "賽日騎師有直接參與操練" in trainer_block:
        delta += 1.5
        notes.append("賽日騎師有直接參與操練")

    return round(max(45.0, min(90.0, current + delta)), 2), notes


def trainer_signal_candidate_v3(horse: dict, combo_priors: dict[tuple[str, str], dict[str, float]]) -> tuple[float, list[str]]:
    auto = horse["auto"]
    current = float(auto["matrix_scores"]["trainer_signal"])
    data = horse["data"].get("_data", {}) if isinstance(horse["data"].get("_data"), dict) else {}
    delta = 0.0
    notes: list[str] = []

    combo = parse_current_jockey_record(str(data.get("jockey_combo_block", "")))
    if combo:
        if combo["starts"] >= 3 and combo["places"] >= 2 and (combo["place_rate"] >= 50.0 or combo["win_rate"] >= 20.0 or combo["avg_finish"] <= 3.5):
            delta += 3.0
            notes.append("現任人馬合作歷史偏強")
        elif combo["starts"] >= 2 and combo["place_rate"] >= 50.0 and combo["avg_finish"] <= 4.0:
            delta += 1.5
            notes.append("現任人馬合作有直接支持")

    combo_prior = combo_priors.get((horse["data"].get("jockey", ""), horse["data"].get("trainer", "")))
    if combo_prior:
        if combo_prior["starts"] >= 80 and combo_prior["place_rate"] >= 28.0 and combo_prior["win_rate"] >= 8.0:
            delta += 2.0
            notes.append("騎練組合長期數據穩定偏強")
        elif combo_prior["starts"] >= 40 and combo_prior["place_rate"] >= 32.0:
            delta += 1.5
            notes.append("騎練組合長期 place rate 正面")
        elif combo_prior["starts"] >= 25 and combo_prior["win_rate"] >= 12.0 and combo_prior["place_rate"] >= 25.0:
            delta += 1.0
            notes.append("騎練組合有基本勝率支持")

    trainer_block = str(data.get("trackwork_trainer", ""))
    if "賽日騎師有直接參與操練" in trainer_block:
        delta += 1.0
        notes.append("賽日騎師有直接參與操練")

    return round(max(45.0, min(90.0, current + delta)), 2), notes


def trainer_signal_candidate_v4(horse: dict, combo_priors: dict[tuple[str, str], dict[str, float]]) -> tuple[float, list[str]]:
    base_score, notes = trainer_signal_candidate_v3(horse, combo_priors)
    delta, extra_notes = horse_specific_jockey_change_adjustment(horse)
    return round(max(45.0, min(90.0, base_score + delta)), 2), notes + extra_notes


def parse_weight_trend(text: str) -> dict[str, float | str]:
    raw = str(text or "")
    amplitude_match = re.search(r"波幅(\d+)lb", raw)
    direction_match = re.search(r"(微增|微減|大增|大減|急增|急減)", raw)
    values = [int(x) for x in re.findall(r"\b\d{3,4}\b", raw)]
    return {
        "amplitude": float(amplitude_match.group(1)) if amplitude_match else 0.0,
        "direction": direction_match.group(1) if direction_match else "",
        "count": float(len(values)),
    }


def horse_health_candidate(horse: dict) -> tuple[float, list[str]]:
    auto = horse["auto"]
    current = float(auto["matrix_scores"]["horse_health"])
    data = horse["data"].get("_data", {}) if isinstance(horse["data"].get("_data"), dict) else {}
    trend = parse_weight_trend(str(data.get("weight_trend", "")))
    amplitude = float(trend["amplitude"])
    direction = str(trend["direction"])
    days_raw = horse["data"].get("days_since_last") or data.get("days_since_last")
    days = float(days_raw) if str(days_raw).isdigit() else 0.0
    delta = 0.0
    notes: list[str] = []

    if amplitude:
        if amplitude <= 4:
            delta += 2.0
            notes.append("體重波幅細，體態較穩")
        elif amplitude <= 8:
            delta += 1.0
            notes.append("體重波幅可控")
        elif amplitude <= 20:
            notes.append("體重波幅中性")
        elif amplitude <= 28:
            delta -= 1.0
            notes.append("體重波幅略大")
        else:
            delta -= 2.0
            notes.append("體重波幅偏大")

    if direction in {"微增", "微減"} and amplitude and amplitude <= 8:
        delta += 0.5
    elif direction in {"大增", "大減", "急增", "急減"} and amplitude >= 20:
        delta -= 1.0

    if days:
        if 15 <= days <= 28:
            delta += 1.0
            notes.append("休賽期處於較佳轉身窗口")
        elif days <= 10:
            delta -= 0.5
            notes.append("休賽較短，回氣空間較窄")
        elif days >= 60:
            delta -= 0.5
            notes.append("休賽偏長，實戰感要再驗證")

    return round(max(45.0, min(90.0, current + delta)), 2), notes


def compute_candidate_ability(
    horse: dict,
    combo_priors: dict[tuple[str, str], dict[str, float]],
    mode: str = "both",
    trainer_variant: str = "v2",
) -> tuple[float, dict]:
    auto = horse["auto"]
    matrix_scores = dict(auto["matrix_scores"])
    if trainer_variant == "v4":
        trainer_score, trainer_notes = trainer_signal_candidate_v4(horse, combo_priors)
    elif trainer_variant == "v3":
        trainer_score, trainer_notes = trainer_signal_candidate_v3(horse, combo_priors)
    else:
        trainer_score, trainer_notes = trainer_signal_candidate_v2(horse, combo_priors)
    health_score, health_notes = horse_health_candidate(horse)
    if mode in {"both", "trainer_only"}:
        matrix_scores["trainer_signal"] = trainer_score
    if mode in {"both", "health_only"}:
        matrix_scores["horse_health"] = health_score
    ability = round(sum(float(matrix_scores[key]) * weight for key, weight in OUTER_WEIGHTS.items()), 4)
    return ability, {
        "matrix_scores": matrix_scores,
        "trainer_notes": trainer_notes,
        "health_notes": health_notes,
    }


def apply_live_verdict_ranking(rows: list[dict], race_context: dict) -> list[dict]:
    ranked = sorted(rows, key=lambda item: (-float(item["ability"]), int(item["horse_num"])))
    if len(ranked) >= 4:
        third = ranked[2]
        fourth = ranked[3]
        if abs(float(third["ability"]) - float(fourth["ability"])) <= 0.8:
            third_bonus = _draw_micro_bonus(third["data"], race_context, {"feature_scores": third.get("feature_scores", {})})
            fourth_bonus = _draw_micro_bonus(fourth["data"], race_context, {"feature_scores": fourth.get("feature_scores", {})})
            third["rank_score"] = round(float(third["ability"]) + third_bonus, 4)
            fourth["rank_score"] = round(float(fourth["ability"]) + fourth_bonus, 4)
    for row in ranked:
        row.setdefault("rank_score", round(float(row["ability"]), 4))
    return sorted(
        ranked,
        key=lambda item: (-float(item.get("rank_score", item["ability"])), -float(item["ability"]), int(item["horse_num"])),
    )


def evaluate_race(race: RaceSample, scored_rows: list[dict]) -> dict:
    ranked = apply_live_verdict_ranking(scored_rows, race.race_context)
    picks = [item["horse_num"] for item in ranked[:4]]
    actual_top3 = [horse for horse, _pos in sorted(race.actual_pos.items(), key=lambda item: item[1])[:3]]
    actual_top4 = [horse for horse, _pos in sorted(race.actual_pos.items(), key=lambda item: item[1])[:4]]
    actual_top3_set = set(actual_top3)
    hits = sum(1 for horse_num in picks[:3] if normalize_horse_name(next(row["horse_name"] for row in scored_rows if row["horse_num"] == horse_num)) in actual_top3_set)
    winner = actual_top3[0] if actual_top3 else None
    winner_rank = len(ranked) + 1
    for idx, row in enumerate(ranked, start=1):
        if normalize_horse_name(row["horse_name"]) == winner:
            winner_rank = idx
            break
    pick1_finish = race.actual_pos.get(normalize_horse_name(ranked[0]["horse_name"]), 99) if ranked else 99
    top4_hits = sum(1 for row in ranked[:4] if normalize_horse_name(row["horse_name"]) in set(actual_top4))
    order_issue = False
    if len(ranked) >= 4:
        p1 = race.actual_pos.get(normalize_horse_name(ranked[0]["horse_name"]), 99)
        p2 = race.actual_pos.get(normalize_horse_name(ranked[1]["horse_name"]), 99)
        p3 = race.actual_pos.get(normalize_horse_name(ranked[2]["horse_name"]), 99)
        p4 = race.actual_pos.get(normalize_horse_name(ranked[3]["horse_name"]), 99)
        order_issue = min(p3, p4) < min(p1, p2)
    return {
        "meeting": race.meeting,
        "race_number": race.race_number,
        "distance": race.distance,
        "venue": race.venue,
        "class": race.race_class,
        "picks": picks,
        "gold": hits == 3,
        "good": len(ranked) >= 2 and normalize_horse_name(ranked[0]["horse_name"]) in actual_top3_set and normalize_horse_name(ranked[1]["horse_name"]) in actual_top3_set,
        "min_threshold": hits >= 2,
        "single": hits >= 1,
        "champion": bool(ranked and normalize_horse_name(ranked[0]["horse_name"]) == winner),
        "top3_has_champion": bool(winner in {normalize_horse_name(row["horse_name"]) for row in ranked[:3]}),
        "winner_rank": winner_rank,
        "mrr": 1.0 / winner_rank if winner_rank > 0 else 0.0,
        "pick1_finish": pick1_finish,
        "top4_hits": top4_hits,
        "order_issue": order_issue,
        "ranked": ranked,
    }


def summarize(results: Iterable[dict]) -> dict:
    items = list(results)
    total = len(items)
    if total == 0:
        return {}
    return {
        "races": total,
        "gold": sum(item["gold"] for item in items),
        "good": sum(item["good"] for item in items),
        "min_threshold": sum(item["min_threshold"] for item in items),
        "single": sum(item["single"] for item in items),
        "champion": sum(item["champion"] for item in items),
        "top3_has_champion": sum(item["top3_has_champion"] for item in items),
        "order_issue": sum(item["order_issue"] for item in items),
        "avg_winner_rank": round(sum(item["winner_rank"] for item in items) / total, 3),
        "mrr": round(sum(item["mrr"] for item in items) / total, 4),
        "avg_pick1_finish": round(sum(item["pick1_finish"] for item in items) / total, 3),
        "avg_top4_hits": round(sum(item["top4_hits"] for item in items) / total, 3),
    }


def render_summary_table(rows: list[list[object]]) -> str:
    headers = ["Model", "Races", "Champion", "Top3 Champ", "Order Issue", "Avg Winner Rank", "MRR", "Avg Pick1 Finish", "Avg Top4 Hits"]
    out = ["| " + " | ".join(headers) + " |", "|---" * len(headers) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(col) for col in row) + " |")
    return "\n".join(out)


def slice_races(races: list[RaceSample], predicate) -> list[RaceSample]:
    return [race for race in races if predicate(race)]


def score_models(
    races: list[RaceSample],
    combo_priors: dict[tuple[str, str], dict[str, float]],
    mode: str = "both",
    trainer_variant: str = "v2",
) -> tuple[list[dict], list[dict]]:
    baseline_results = []
    candidate_results = []
    for race in races:
        baseline_rows = []
        candidate_rows = []
        for horse in race.horses:
            baseline_rows.append(
                {
                    "horse_num": horse["horse_num"],
                    "horse_name": horse["horse_name"],
                    "ability": float(horse["auto"]["ability_score"]),
                    "data": horse["data"],
                    "feature_scores": horse["auto"].get("feature_scores", {}),
                }
            )
            ability, payload = compute_candidate_ability(horse, combo_priors, mode=mode, trainer_variant=trainer_variant)
            candidate_rows.append(
                {
                    "horse_num": horse["horse_num"],
                    "horse_name": horse["horse_name"],
                    "ability": ability,
                    "data": horse["data"],
                    "feature_scores": horse["auto"].get("feature_scores", {}),
                    **payload,
                }
            )
        baseline_results.append(evaluate_race(race, baseline_rows))
        candidate_results.append(evaluate_race(race, candidate_rows))
    return baseline_results, candidate_results


def render_report(races: list[RaceSample], baseline_results: list[dict], candidate_results: list[dict]) -> str:
    baseline = summarize(baseline_results)
    candidate = summarize(candidate_results)
    trainer_results = score_models(races, load_combo_priors(), mode="trainer_only")[1]
    trainer_results_v3 = score_models(races, load_combo_priors(), mode="trainer_only", trainer_variant="v3")[1]
    trainer_results_v4 = score_models(races, load_combo_priors(), mode="trainer_only", trainer_variant="v4")[1]
    health_results = score_models(races, load_combo_priors(), mode="health_only")[1]
    candidate_results_v3 = score_models(races, load_combo_priors(), mode="both", trainer_variant="v3")[1]
    candidate_results_v4 = score_models(races, load_combo_priors(), mode="both", trainer_variant="v4")[1]
    trainer_stats = summarize(trainer_results)
    trainer_stats_v3 = summarize(trainer_results_v3)
    trainer_stats_v4 = summarize(trainer_results_v4)
    health_stats = summarize(health_results)
    candidate_v3 = summarize(candidate_results_v3)
    candidate_v4 = summarize(candidate_results_v4)
    lines = [
        "# HKJC Trainer/Health Candidate Validation",
        "",
        f"- Sample races: {len(races)}",
        f"- Meetings: {len({race.meeting for race in races})}",
        "",
        "## Overall",
        "",
        render_summary_table([
            ["current_live", baseline["races"], baseline["champion"], baseline["top3_has_champion"], baseline["order_issue"], baseline["avg_winner_rank"], baseline["mrr"], baseline["avg_pick1_finish"], baseline["avg_top4_hits"]],
            ["trainer_only_v2", trainer_stats["races"], trainer_stats["champion"], trainer_stats["top3_has_champion"], trainer_stats["order_issue"], trainer_stats["avg_winner_rank"], trainer_stats["mrr"], trainer_stats["avg_pick1_finish"], trainer_stats["avg_top4_hits"]],
            ["trainer_only_v3", trainer_stats_v3["races"], trainer_stats_v3["champion"], trainer_stats_v3["top3_has_champion"], trainer_stats_v3["order_issue"], trainer_stats_v3["avg_winner_rank"], trainer_stats_v3["mrr"], trainer_stats_v3["avg_pick1_finish"], trainer_stats_v3["avg_top4_hits"]],
            ["trainer_only_v4_change_quality", trainer_stats_v4["races"], trainer_stats_v4["champion"], trainer_stats_v4["top3_has_champion"], trainer_stats_v4["order_issue"], trainer_stats_v4["avg_winner_rank"], trainer_stats_v4["mrr"], trainer_stats_v4["avg_pick1_finish"], trainer_stats_v4["avg_top4_hits"]],
            ["health_only_v2", health_stats["races"], health_stats["champion"], health_stats["top3_has_champion"], health_stats["order_issue"], health_stats["avg_winner_rank"], health_stats["mrr"], health_stats["avg_pick1_finish"], health_stats["avg_top4_hits"]],
            ["trainer_health_v2", candidate["races"], candidate["champion"], candidate["top3_has_champion"], candidate["order_issue"], candidate["avg_winner_rank"], candidate["mrr"], candidate["avg_pick1_finish"], candidate["avg_top4_hits"]],
            ["trainer_health_v3", candidate_v3["races"], candidate_v3["champion"], candidate_v3["top3_has_champion"], candidate_v3["order_issue"], candidate_v3["avg_winner_rank"], candidate_v3["mrr"], candidate_v3["avg_pick1_finish"], candidate_v3["avg_top4_hits"]],
            ["trainer_health_v4_change_quality", candidate_v4["races"], candidate_v4["champion"], candidate_v4["top3_has_champion"], candidate_v4["order_issue"], candidate_v4["avg_winner_rank"], candidate_v4["mrr"], candidate_v4["avg_pick1_finish"], candidate_v4["avg_top4_hits"]],
        ]),
        "",
    ]

    slices = {
        "Happy Valley": lambda race: race.venue == "跑馬地",
        "Sha Tin": lambda race: race.venue == "沙田",
        "Happy Valley 1650/1800": lambda race: race.venue == "跑馬地" and race.distance in {"1650m", "1800m"},
    }
    for label, predicate in slices.items():
        race_slice = slice_races(races, predicate)
        if not race_slice:
            continue
        base_slice, cand_slice = score_models(race_slice, load_combo_priors())
        trainer_slice = summarize(score_models(race_slice, load_combo_priors(), mode="trainer_only")[1])
        trainer_slice_v3 = summarize(score_models(race_slice, load_combo_priors(), mode="trainer_only", trainer_variant="v3")[1])
        trainer_slice_v4 = summarize(score_models(race_slice, load_combo_priors(), mode="trainer_only", trainer_variant="v4")[1])
        health_slice = summarize(score_models(race_slice, load_combo_priors(), mode="health_only")[1])
        base_stats = summarize(base_slice)
        cand_stats = summarize(cand_slice)
        cand_stats_v3 = summarize(score_models(race_slice, load_combo_priors(), trainer_variant="v3")[1])
        cand_stats_v4 = summarize(score_models(race_slice, load_combo_priors(), trainer_variant="v4")[1])
        lines.extend([
            "## " + label,
            "",
            render_summary_table([
                ["current_live", base_stats["races"], base_stats["champion"], base_stats["top3_has_champion"], base_stats["order_issue"], base_stats["avg_winner_rank"], base_stats["mrr"], base_stats["avg_pick1_finish"], base_stats["avg_top4_hits"]],
                ["trainer_only_v2", trainer_slice["races"], trainer_slice["champion"], trainer_slice["top3_has_champion"], trainer_slice["order_issue"], trainer_slice["avg_winner_rank"], trainer_slice["mrr"], trainer_slice["avg_pick1_finish"], trainer_slice["avg_top4_hits"]],
                ["trainer_only_v3", trainer_slice_v3["races"], trainer_slice_v3["champion"], trainer_slice_v3["top3_has_champion"], trainer_slice_v3["order_issue"], trainer_slice_v3["avg_winner_rank"], trainer_slice_v3["mrr"], trainer_slice_v3["avg_pick1_finish"], trainer_slice_v3["avg_top4_hits"]],
                ["trainer_only_v4_change_quality", trainer_slice_v4["races"], trainer_slice_v4["champion"], trainer_slice_v4["top3_has_champion"], trainer_slice_v4["order_issue"], trainer_slice_v4["avg_winner_rank"], trainer_slice_v4["mrr"], trainer_slice_v4["avg_pick1_finish"], trainer_slice_v4["avg_top4_hits"]],
                ["health_only_v2", health_slice["races"], health_slice["champion"], health_slice["top3_has_champion"], health_slice["order_issue"], health_slice["avg_winner_rank"], health_slice["mrr"], health_slice["avg_pick1_finish"], health_slice["avg_top4_hits"]],
                ["trainer_health_v2", cand_stats["races"], cand_stats["champion"], cand_stats["top3_has_champion"], cand_stats["order_issue"], cand_stats["avg_winner_rank"], cand_stats["mrr"], cand_stats["avg_pick1_finish"], cand_stats["avg_top4_hits"]],
                ["trainer_health_v3", cand_stats_v3["races"], cand_stats_v3["champion"], cand_stats_v3["top3_has_champion"], cand_stats_v3["order_issue"], cand_stats_v3["avg_winner_rank"], cand_stats_v3["mrr"], cand_stats_v3["avg_pick1_finish"], cand_stats_v3["avg_top4_hits"]],
                ["trainer_health_v4_change_quality", cand_stats_v4["races"], cand_stats_v4["champion"], cand_stats_v4["top3_has_champion"], cand_stats_v4["order_issue"], cand_stats_v4["avg_winner_rank"], cand_stats_v4["mrr"], cand_stats_v4["avg_pick1_finish"], cand_stats_v4["avg_top4_hits"]],
            ]),
            "",
        ])

    improved = []
    worsened = []
    for base, cand in zip(baseline_results, candidate_results):
        delta = (cand["champion"] - base["champion"], cand["mrr"] - base["mrr"], cand["top4_hits"] - base["top4_hits"])
        row = f"{base['meeting']} R{base['race_number']}: baseline {base['picks'][:4]} -> candidate {cand['picks'][:4]}"
        if delta > (0, 0, 0):
            improved.append(row)
        elif delta < (0, 0, 0):
            worsened.append(row)

    lines.extend(["## Quick Read", ""])
    if candidate.get("champion", 0) > baseline.get("champion", 0) or candidate.get("mrr", 0) > baseline.get("mrr", 0):
        lines.append("- Candidate 有局部正面跡象，但仍要留意 order issue 同 trade-off。")
    else:
        lines.append("- Candidate 暫未見穩定優於 current_live，不建議直接 embed。")
    lines.append(f"- Improved races tracked: {len(improved)}")
    lines.append(f"- Worsened races tracked: {len(worsened)}")
    lines.append("")
    if improved:
        lines.extend(["### Improved Examples", ""] + [f"- {row}" for row in improved[:8]] + [""])
    if worsened:
        lines.extend(["### Worsened Examples", ""] + [f"- {row}" for row in worsened[:8]] + [""])
    return "\n".join(lines).strip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate candidate-only trainer/health adjustments against archive HKJC meetings.")
    parser.add_argument("--output", type=Path, help="Optional path to write markdown report.")
    args = parser.parse_args()

    result_index = build_actual_results_index()
    races = load_race_samples(result_index)
    combo_priors = load_combo_priors()
    baseline_results, candidate_results = score_models(races, combo_priors)
    report = render_report(races, baseline_results, candidate_results)
    print(report)
    if args.output:
        args.output.write_text(report, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
