#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[1]
AUTO_SCRIPT_DIR = ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"


LIVE_DIRS = [
    ROOT / "2026-06-06 Randwick Race 1-10",
    ROOT / "2026-06-06 Eagle Farm Race 1-9",
]

LIVE_ACTUAL_TOP3 = {
    "2026-06-06 Randwick Race 1-10": {
        1: [7, 11, 13],
        2: [6, 9, 7],
        3: [14, 8, 4],
        4: [3, 8, 6],
        5: [3, 9, 2],
        6: [6, 3, 10],
        7: [4, 6, 10],
        8: [16, 3, 5],
        9: [5, 6, 21],
        10: [7, 15, 14],
    },
    "2026-06-06 Eagle Farm Race 1-9": {
        1: [17, 13, 4],
        2: [8, 6, 14],
        3: [6, 4, 9],
        4: [13, 6, 3],
        5: [1, 2, 5],
        6: [5, 1, 7],
        7: [3, 4, 14],
        8: [3, 1, 4],
        9: [11, 1, 2],
    },
}

ARCHIVE_DIRS = [
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-05-30 Rosehill Gardens Race 1-10",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-05-30 Caulfield Race 1-9",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-05-30 Eagle Farm Race 1-9",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-05-27 Doomben Race 1-8",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-05-27 Canterbury Race 1-6",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-04-25 Randwick Race 1-8",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-04-18 Randwick",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-04-22 Canterbury Race 1-8",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2026-04-17 Cranbourne Race 1-8",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2025-09-13 Flemington Race 1-10",
    ROOT / "Archive_Race_Analysis" / "AU_Racing" / "2025-09-06 Randwick Race 1-10",
]

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
    "confidence_score",
)

MATRIX_KEYS = (
    "stability",
    "sectional",
    "race_shape",
    "jockey_trainer",
    "class_weight",
    "track",
    "form_line",
)


def as_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_int(value, default: int | None = None) -> int | None:
    if value is None:
        return default
    match = re.search(r"\d+", str(value))
    if not match:
        return default
    return int(match.group(0))


def read_text_retry(path: Path, attempts: int = 3) -> str:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return path.read_text(encoding="utf-8")
        except TimeoutError as exc:
            last_exc = exc
            print(f"Read timeout ({attempt}/{attempts}): {path}", flush=True)
            time.sleep(float(attempt))
    if last_exc:
        raise last_exc
    return path.read_text(encoding="utf-8")


def race_label(ranked: list[dict]) -> str:
    top3 = ranked[:3]
    hits = sum(1 for row in top3 if row["actual_pos"] <= 3)
    top2_hits = sum(1 for row in top3[:2] if row["actual_pos"] <= 3)
    if hits == 3:
        return "Gold"
    if top2_hits == 2:
        return "Good"
    if hits >= 2:
        return "Pass"
    if hits == 1:
        return "1 Hit"
    return "Miss"


def evaluate(races: list[dict], score_fn) -> dict:
    summary = Counter()
    rows = []
    top3_hits = 0
    winner_in_top3 = 0
    top1 = 0
    changed = []

    for race in races:
        ranked = sorted(
            (
                {**horse, "_score": score_fn(horse, race)}
                for horse in race["horses"]
            ),
            key=lambda row: (-row["_score"], -row["ability_score"], row["horse_number"]),
        )
        label = race_label(ranked)
        summary[label] += 1
        hits = sum(1 for row in ranked[:3] if row["actual_pos"] <= 3)
        top3_hits += hits
        if any(row["actual_pos"] == 1 for row in ranked[:3]):
            winner_in_top3 += 1
        if ranked and ranked[0]["actual_pos"] == 1:
            top1 += 1
        rows.append(
            {
                "meeting": race["meeting"],
                "race_no": race["race_no"],
                "label": label,
                "hits": hits,
                "top3": " / ".join(f"#{row['horse_number']} {row['horse_name']}({row['actual_pos']})" for row in ranked[:3]),
            }
        )
        base = race.get("_rank_score_top3")
        now = [row["horse_number"] for row in ranked[:3]]
        if base and base != now:
            changed.append((race, base, now))

    total = len(races)
    return {
        "races": total,
        "summary": dict(summary),
        "top3_precision": top3_hits / (total * 3) if total else 0.0,
        "winner_in_top3": winner_in_top3 / total if total else 0.0,
        "top1": top1 / total if total else 0.0,
        "rows": rows,
        "changed": changed,
    }


def rank_score(horse: dict, _race: dict) -> float:
    return horse["rank_score"]


def ability_score(horse: dict, _race: dict) -> float:
    return horse["ability_score"]


def close_gap_score(horse: dict, race: dict) -> float:
    score = horse["rank_score"]
    base_ranked = race["_rank_score_ranked"]
    rank_map = {row["horse_number"]: idx for idx, row in enumerate(base_ranked, start=1)}
    rank = rank_map.get(horse["horse_number"], 999)
    if 4 <= rank <= 6:
        third_score = base_ranked[2]["rank_score"] if len(base_ranked) >= 3 else score
        gap = third_score - score
        mx = horse["matrix_scores"]
        if gap <= 3.0 and (
            as_float(mx.get("stability"), 60) >= 66
            or as_float(mx.get("form_line"), 60) >= 66
            or as_float(mx.get("class_weight"), 60) >= 66
        ):
            score += 1.15
    return score


def jt_conf_score(horse: dict, _race: dict) -> float:
    score = horse["rank_score"]
    mx = horse["matrix_scores"]
    fs = horse["feature_scores"]
    jt = as_float(mx.get("jockey_trainer"), 60)
    confidence = as_float(fs.get("confidence_score"), 60)
    fit = as_float(fs.get("jockey_horse_fit_score"), 60)
    if jt >= 66 and confidence >= 82:
        score += 1.0
    if fit >= 68 and confidence >= 80:
        score += 0.45
    return score


def pace_track_score(horse: dict, _race: dict) -> float:
    score = horse["rank_score"]
    mx = horse["matrix_scores"]
    fs = horse["feature_scores"]
    race_shape = as_float(mx.get("race_shape"), 60)
    track = as_float(mx.get("track"), 60)
    pace = as_float(fs.get("pace_map_score"), 60)
    sectional = as_float(mx.get("sectional"), 60)
    if race_shape >= 65 and track >= 64:
        score += 0.75
    if pace >= 64 and sectional >= 62:
        score += 0.45
    return score


def combined_score(horse: dict, race: dict) -> float:
    score = horse["rank_score"]
    score += close_gap_score(horse, race) - horse["rank_score"]
    score += (jt_conf_score(horse, race) - horse["rank_score"]) * 0.75
    score += (pace_track_score(horse, race) - horse["rank_score"]) * 0.75
    return score


def load_live_races() -> list[dict]:
    races = []
    for meeting_dir in LIVE_DIRS:
        races.extend(load_scoring_races(meeting_dir, LIVE_ACTUAL_TOP3.get(meeting_dir.name, {})))
    return races


def load_archive_races() -> list[dict]:
    races = []
    for meeting_dir in ARCHIVE_DIRS:
        if not meeting_dir.exists():
            continue
        top3_by_race = parse_reflector_top3(meeting_dir / "Race_Results_Reflector.md")
        if top3_by_race:
            races.extend(load_scoring_races(meeting_dir, top3_by_race))
    return races


def parse_reflector_top3(path: Path) -> dict[int, list[int]]:
    if not path.exists():
        return {}
    try:
        text = read_text_retry(path)
    except TimeoutError:
        return {}
    top3_by_race: dict[int, list[int]] = {}
    current_race = None
    for line in text.splitlines():
        race_match = re.match(r"## Race\s+(\d+)", line.strip())
        if race_match:
            current_race = int(race_match.group(1))
            top3_by_race[current_race] = []
            continue
        if current_race is None:
            continue
        result_match = re.match(r"(?:1st|2nd|3rd):\s+#(\d+)\s+", line.strip())
        if result_match and len(top3_by_race[current_race]) < 3:
            top3_by_race[current_race].append(int(result_match.group(1)))
    return {race_no: nums for race_no, nums in top3_by_race.items() if len(nums) >= 3}


def load_scoring_races(meeting_dir: Path, top3_by_race: dict[int, list[int]]) -> list[dict]:
    csv_paths = [meeting_dir / "Meeting_Auto_Scoring.csv"]
    if not csv_paths[0].exists():
        csv_paths = sorted(meeting_dir.glob("Race_*_Auto_Scoring.csv"))
    rows_by_race: dict[int, list[dict]] = {}
    for csv_path in csv_paths:
        if not csv_path.exists():
            continue
        try:
            text = read_text_retry(csv_path)
        except TimeoutError:
            continue
        reader = csv.DictReader(text.splitlines())
        for row in reader:
            race_no = parse_int(row.get("race_number"))
            horse_number = parse_int(row.get("horse_number"))
            if not race_no or not horse_number:
                continue
            actual_top3 = top3_by_race.get(race_no, [])
            if not actual_top3:
                continue
            try:
                actual_pos = actual_top3.index(horse_number) + 1
            except ValueError:
                actual_pos = 99
            feature_scores = {key: as_float(row.get(key), 60.0) for key in FEATURE_KEYS}
            matrix_scores = {
                "stability": feature_scores["consistency_score"],
                "sectional": feature_scores["sectional_score"],
                "race_shape": feature_scores["pace_map_score"],
                "jockey_trainer": mean([
                    feature_scores["jockey_score"],
                    feature_scores["trainer_score"],
                    feature_scores["jockey_horse_fit_score"],
                ]),
                "class_weight": mean([
                    feature_scores["class_score"],
                    feature_scores["rating_score"],
                    feature_scores["weight_score"],
                ]),
                "track": feature_scores["track_score"],
                "form_line": feature_scores["formline_score"],
            }
            rows_by_race.setdefault(race_no, []).append(
                {
                    "horse_number": horse_number,
                    "horse_name": str(row.get("horse_name") or "").strip(),
                    "actual_pos": actual_pos,
                    "ability_score": as_float(row.get("ability_score")),
                    "rank_score": as_float(row.get("rank_score"), as_float(row.get("ability_score"))),
                    "feature_scores": feature_scores,
                    "matrix_scores": matrix_scores,
                }
            )
    races = []
    for race_no, horses in sorted(rows_by_race.items()):
        if len(horses) < 4:
            continue
        ranked = sorted(horses, key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
        races.append(
            {
                "meeting": meeting_dir.name,
                "race_no": race_no,
                "horses": horses,
                "_rank_score_ranked": ranked,
                "_rank_score_top3": [row["horse_number"] for row in ranked[:3]],
            }
        )
    return races


def load_logic_races(meeting_dir: Path, results_by_race: dict, archive_names: bool = False) -> list[dict]:
    races = []
    for logic_path in sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999)):
        logic = json.loads(read_text_retry(logic_path))
        race_analysis = logic.get("race_analysis") or {}
        race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
        positions = results_by_race.get(race_no) or {}
        horses = []
        for horse_num, horse in (logic.get("horses") or {}).items():
            auto = horse.get("python_auto") or {}
            horse_number = parse_int(horse_num) or parse_int(horse.get("number"), 999)
            if archive_names:
                actual_pos = positions.get(normalize_horse_name(horse.get("horse_name")))
            else:
                actual_pos = positions.get(horse_number)
            if actual_pos is None:
                continue
            horses.append(
                {
                    "horse_number": horse_number,
                    "horse_name": str(horse.get("horse_name") or "").strip(),
                    "actual_pos": int(actual_pos),
                    "ability_score": as_float(auto.get("ability_score")),
                    "rank_score": as_float(auto.get("rank_score"), as_float(auto.get("ability_score"))),
                    "feature_scores": auto.get("feature_scores") if isinstance(auto.get("feature_scores"), dict) else {},
                    "matrix_scores": auto.get("matrix_scores") if isinstance(auto.get("matrix_scores"), dict) else {},
                }
            )
        if len(horses) >= 4:
            ranked = sorted(horses, key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
            races.append(
                {
                    "meeting": meeting_dir.name,
                    "race_no": race_no,
                    "horses": horses,
                    "_rank_score_ranked": ranked,
                    "_rank_score_top3": [row["horse_number"] for row in ranked[:3]],
                }
            )
    return races


def ml_live_test(train_races: list[dict], live_races: list[dict]) -> dict:
    feature_names = list(FEATURE_KEYS) + [f"mx_{key}" for key in MATRIX_KEYS]

    def vector(horse: dict) -> list[float]:
        fs = horse["feature_scores"]
        mx = horse["matrix_scores"]
        return [as_float(fs.get(key), 60.0) for key in FEATURE_KEYS] + [as_float(mx.get(key), 60.0) for key in MATRIX_KEYS]

    X_train = []
    y_train = []
    for race in train_races:
        for horse in race["horses"]:
            X_train.append(vector(horse))
            y_train.append(1 if horse["actual_pos"] <= 3 else 0)

    if len(set(y_train)) < 2 or len(X_train) < 50:
        return {"skipped": "not enough labelled training data"}

    positives = [row for row, label in zip(X_train, y_train) if label == 1]
    negatives = [row for row, label in zip(X_train, y_train) if label == 0]
    all_means = [mean([row[i] for row in X_train]) for i in range(len(feature_names))]
    all_ranges = [
        max([row[i] for row in X_train]) - min([row[i] for row in X_train]) or 1.0
        for i in range(len(feature_names))
    ]
    weights = []
    for i in range(len(feature_names)):
        pos_mean = mean(row[i] for row in positives)
        neg_mean = mean(row[i] for row in negatives)
        weights.append((pos_mean - neg_mean) / all_ranges[i])

    def ml_score(horse: dict) -> float:
        row = vector(horse)
        return sum(((row[i] - all_means[i]) / all_ranges[i]) * weights[i] for i in range(len(feature_names)))

    scored_races = []
    for race in live_races:
        horses = []
        for horse in race["horses"]:
            horses.append({**horse, "ml_score": ml_score(horse)})
        scored_races.append({**race, "horses": horses})

    result = evaluate(scored_races, lambda horse, _race: horse["ml_score"])
    top_features = sorted(zip(feature_names, weights), key=lambda item: abs(item[1]), reverse=True)[:12]
    return {
        "train_races": len(train_races),
        "train_horses": len(X_train),
        "live_result": result,
        "top_features": top_features,
    }


def fmt_pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_section(title: str, result: dict) -> list[str]:
    summary = result["summary"]
    return [
        f"## {title}",
        "",
        f"- Races: **{result['races']}**",
        f"- Labels: Gold {summary.get('Gold', 0)}, Good {summary.get('Good', 0)}, Pass {summary.get('Pass', 0)}, 1 Hit {summary.get('1 Hit', 0)}, Miss {summary.get('Miss', 0)}",
        f"- Top3 precision: **{fmt_pct(result['top3_precision'])}**",
        f"- Winner in Top3: **{fmt_pct(result['winner_in_top3'])}**",
        f"- Top1 winner: **{fmt_pct(result['top1'])}**",
        "",
    ]


def write_outputs(live_races: list[dict], archive_races: list[dict], results: dict, ml_result: dict) -> None:
    md = ROOT / "scratch" / "au_0606_validation_report.md"
    csv_path = ROOT / "scratch" / "au_0606_validation_race_rows.csv"
    lines = [
        "# AU 06-06 Validation Before Implementation",
        "",
        f"- Live races: **{len(live_races)}**",
        f"- Archive subset races: **{len(archive_races)}**",
        "",
    ]
    for title, result in results.items():
        lines.extend(render_section(title, result))

    lines.append("## ML Gate")
    lines.append("")
    if ml_result.get("skipped"):
        lines.append(f"- ML skipped: `{ml_result['skipped']}`")
    else:
        live = ml_result["live_result"]
        lines.append(f"- Train archive subset: **{ml_result['train_races']} races / {ml_result['train_horses']} horses**")
        lines.append(f"- Live labels: Gold {live['summary'].get('Gold', 0)}, Good {live['summary'].get('Good', 0)}, Pass {live['summary'].get('Pass', 0)}, 1 Hit {live['summary'].get('1 Hit', 0)}, Miss {live['summary'].get('Miss', 0)}")
        lines.append(f"- Live Top3 precision: **{fmt_pct(live['top3_precision'])}**")
        lines.append(f"- Live Winner in Top3: **{fmt_pct(live['winner_in_top3'])}**")
        lines.append("- Top linear ML feature weights:")
        for name, value in ml_result["top_features"]:
            lines.append(f"  - `{name}`: {value:.4f}")
    lines.append("")

    md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["variant", "meeting", "race_no", "label", "hits", "top3"])
        writer.writeheader()
        for variant, result in results.items():
            for row in result["rows"]:
                writer.writerow({"variant": variant, **row})

    print(f"Report: {md}")
    print(f"Rows: {csv_path}")


def main() -> int:
    print("Loading live 06-06 races...", flush=True)
    live_races = load_live_races()
    print(f"Loaded live races: {len(live_races)}", flush=True)
    print("Loading JSON-labelled archive subset...", flush=True)
    archive_races = load_archive_races()
    print(f"Loaded archive races: {len(archive_races)}", flush=True)
    variants = {
        "Live ability_score baseline": (live_races, ability_score),
        "Live rank_score baseline": (live_races, rank_score),
        "Live close-gap candidate": (live_races, close_gap_score),
        "Live JT/confidence candidate": (live_races, jt_conf_score),
        "Live pace/track candidate": (live_races, pace_track_score),
        "Live combined candidate": (live_races, combined_score),
        "Archive rank_score baseline": (archive_races, rank_score),
        "Archive combined candidate": (archive_races, combined_score),
    }
    print("Evaluating score variants...", flush=True)
    results = {name: evaluate(races, fn) for name, (races, fn) in variants.items()}
    print("Running pure-Python ML gate...", flush=True)
    ml_result = ml_live_test(archive_races, live_races)
    write_outputs(live_races, archive_races, results, ml_result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
