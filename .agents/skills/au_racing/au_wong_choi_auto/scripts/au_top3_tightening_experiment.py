#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from pathlib import Path

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    has_complete_result,
    load_historical_results,
    normalize_condition_bucket,
    normalize_horse_name,
    parse_int,
)
from racing_engine.scoring import PLACE_TIGHTENING_FEATURE_WEIGHTS, PLACE_TIGHTENING_SCALE

OUTPUT_MD = ARCHIVE_ROOT / "AU_Auto_Top3_Tightening_Experiment.md"
OUTPUT_CSV = ARCHIVE_ROOT / "AU_Auto_Top3_Tightening_Changes.csv"


def race_class_bucket(text: str) -> str:
    value = str(text or "").lower()
    if "group 1" in value:
        return "Group 1"
    if "group 2" in value or "group 3" in value:
        return "Group 2/3"
    if "listed" in value:
        return "Listed"
    if "maiden" in value:
        return "Maiden"
    if "bm" in value:
        rating = parse_int(value, 0) or 0
        if rating >= 88:
            return "BM88+"
        if rating >= 72:
            return "BM72-84"
        return "BM58-70"
    return "Other"


def field_size_bucket(size: int) -> str:
    if size <= 8:
        return "Field <=8"
    if size <= 12:
        return "Field 9-12"
    return "Field 13+"


def pct(numerator: int, denominator: int) -> str:
    if not denominator:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def build_races():
    races = []
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    for meeting_dir in sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir()):
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_files:
            continue
        sample_logic = json.loads(logic_files[0].read_text(encoding="utf-8"))
        meeting_date = detect_meeting_date(meeting_dir)
        meeting_track = detect_meeting_track(meeting_dir, sample_logic)
        if not meeting_date or not meeting_track:
            continue

        for logic_path in logic_files:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_analysis = logic.get("race_analysis", {})
            race_no = parse_int(race_analysis.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            rows_for_race = choose_track_rows(historical_results.get((meeting_date, race_no), []), meeting_track)
            if not rows_for_race:
                continue
            race_lookup = {row["horse_slug"]: row for row in rows_for_race}
            race_rows = []
            for horse_num, horse in logic.get("horses", {}).items():
                python_auto = horse.get("python_auto") or {}
                matrix_scores = python_auto.get("matrix_scores") or {}
                if not matrix_scores:
                    continue
                result_row = race_lookup.get(normalize_horse_name(horse.get("horse_name")))
                if not result_row:
                    continue
                race_rows.append(
                    {
                        "horse_number": parse_int(horse_num) or 999,
                        "horse_name": str(horse.get("horse_name") or "").strip(),
                        "ability_score": float(python_auto.get("ability_score") or 0.0),
                        "place_tightening_bonus": float(python_auto.get("place_tightening_bonus") or 0.0),
                        "rank_score": float(python_auto.get("rank_score") or 0.0),
                        "legacy_rank_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0)
                        - float(python_auto.get("place_tightening_bonus") or 0.0),
                        "model_score": float(python_auto.get("rank_score") or python_auto.get("ability_score") or 0.0),
                        "actual_pos": int(result_row["pos"]),
                    }
                )
            if len(race_rows) < 4 or not has_complete_result(race_rows):
                continue
            races.append(
                {
                    "meta": {
                        "meeting": meeting_dir.name,
                        "race_no": race_no,
                        "condition_bucket": normalize_condition_bucket(rows_for_race[0].get("condition") or ""),
                        "race_class_bucket": race_class_bucket(race_analysis.get("race_class")),
                        "field_size_bucket": field_size_bucket(len(race_rows)),
                    },
                    "rows": race_rows,
                }
            )
    return races


def hit_count(rows: list[dict], top_n: int = 3) -> int:
    return sum(1 for row in rows[:top_n] if row["actual_pos"] <= 3)


def evaluate(races: list[dict], use_model_score: bool = False, bucket_only: bool = False) -> dict:
    counts = {
        "races": 0,
        "top1": 0,
        "winner_in_top3": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "gold": 0,
        "good": 0,
        "minimum": 0,
        "zero_hit": 0,
        "one_hit": 0,
        "four_to_six_rescues": 0,
    }
    changed_races = []

    for race in races:
        meta = race["meta"]
        if bucket_only and not (
            meta["condition_bucket"] == "Good/Firm"
            and meta["race_class_bucket"] == "BM58-70"
            and meta["field_size_bucket"] == "Field 9-12"
        ):
            continue

        base_ranked = sorted(race["rows"], key=lambda row: (-row["legacy_rank_score"], row["horse_number"]))
        ranked = sorted(
            race["rows"],
            key=lambda row: (-(row["model_score"] if use_model_score else row["legacy_rank_score"]), row["horse_number"]),
        )
        counts["races"] += 1
        hits3 = hit_count(ranked, 3)
        hits2 = hit_count(ranked, 2)

        if ranked[0]["actual_pos"] == 1:
            counts["top1"] += 1
        if any(row["actual_pos"] == 1 for row in ranked[:3]):
            counts["winner_in_top3"] += 1
        counts["top3_places"] += hits3
        counts["top3_slots"] += 3
        if hits3 == 3:
            counts["gold"] += 1
        if hits2 == 2:
            counts["good"] += 1
        if hits3 >= 2:
            counts["minimum"] += 1
        if hits3 == 0:
            counts["zero_hit"] += 1
        if hits3 == 1:
            counts["one_hit"] += 1

        if use_model_score:
            base_hits3 = hit_count(base_ranked, 3)
            if base_hits3 == 0 and hits3 >= 1:
                counts["four_to_six_rescues"] += 1
            base_top3_names = [row["horse_name"] for row in base_ranked[:3]]
            new_top3_names = [row["horse_name"] for row in ranked[:3]]
            if base_top3_names != new_top3_names:
                changed_races.append(
                    {
                        "meeting": meta["meeting"],
                        "race_no": meta["race_no"],
                        "condition_bucket": meta["condition_bucket"],
                        "race_class_bucket": meta["race_class_bucket"],
                        "field_size_bucket": meta["field_size_bucket"],
                        "base_top3": " / ".join(f"{row['horse_name']}({row['actual_pos']})" for row in base_ranked[:3]),
                        "new_top3": " / ".join(f"{row['horse_name']}({row['actual_pos']})" for row in ranked[:3]),
                        "base_hits3": base_hits3,
                        "new_hits3": hits3,
                    }
                )

    return {"counts": counts, "changed_races": changed_races}


def render_comparison(label: str, base: dict, trial: dict) -> list[str]:
    b = base["counts"]
    t = trial["counts"]
    lines = [
        f"## {label}",
        "",
        f"- Races: **{b['races']}**",
        f"- Top 1: **{pct(b['top1'], b['races'])}** -> **{pct(t['top1'], t['races'])}**",
        f"- Top 3 包頭馬: **{pct(b['winner_in_top3'], b['races'])}** -> **{pct(t['winner_in_top3'], t['races'])}**",
        f"- Top 3 Place Precision: **{pct(b['top3_places'], b['top3_slots'])}** -> **{pct(t['top3_places'], t['top3_slots'])}**",
        f"- Gold: **{pct(b['gold'], b['races'])}** -> **{pct(t['gold'], t['races'])}**",
        f"- Good: **{pct(b['good'], b['races'])}** -> **{pct(t['good'], t['races'])}**",
        f"- Minimum: **{pct(b['minimum'], b['races'])}** -> **{pct(t['minimum'], t['races'])}**",
        f"- 0-hit races: **{b['zero_hit']}** -> **{t['zero_hit']}**",
        f"- 1-hit races: **{b['one_hit']}** -> **{t['one_hit']}**",
        f"- 由 rank 4-6 拉返入 top3 並脫離 0-hit: **{t['four_to_six_rescues']}** 場",
        "",
    ]
    return lines


def write_csv(rows: list[dict]) -> None:
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "meeting",
                "race_no",
                "condition_bucket",
                "race_class_bucket",
                "field_size_bucket",
                "base_hits3",
                "new_hits3",
                "base_top3",
                "new_top3",
            ],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main():
    races = build_races()
    base_all = evaluate(races, use_model_score=False, bucket_only=False)
    trial_all = evaluate(races, use_model_score=True, bucket_only=False)
    base_bucket = evaluate(races, use_model_score=False, bucket_only=True)
    trial_bucket = evaluate(races, use_model_score=True, bucket_only=True)

    changed = sorted(
        trial_all["changed_races"],
        key=lambda row: (row["new_hits3"] - row["base_hits3"], row["meeting"], row["race_no"]),
        reverse=True,
    )
    write_csv(changed)

    lines = [
        "# AU Auto Top3 Tightening Experiment",
        "",
        "Comparison: 用 clean archive 比較舊 live `rank_score`（未計 place tightening），對上現行 `rank_score`（已加入 archive-derived place tightening layer）之後，前三收窄有冇改善。",
        "",
        "## Live Tightening Formula",
        "",
        f"- Scale: **{PLACE_TIGHTENING_SCALE:.2f}**",
    ]
    for key, weight in PLACE_TIGHTENING_FEATURE_WEIGHTS.items():
        lines.append(f"- `{key}`: **{weight:+.3f}**")
    lines.extend(
        [
            "",
            *render_comparison("Clean Sample Overall", base_all, trial_all),
            *render_comparison("Core Bucket: Good/Firm + BM58-70 + Field 9-12", base_bucket, trial_bucket),
            "## Changed Races",
            "",
            f"- Top3 組合有變動嘅 clean races: **{len(changed)}**",
            "",
        ]
    )
    for row in changed[:20]:
        lines.append(
            f"- {row['meeting']} Race {row['race_no']}: hits **{row['base_hits3']} -> {row['new_hits3']}**, "
            f"`{row['base_top3']}` -> `{row['new_top3']}`"
        )
    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")
    print(f"Change log written: {OUTPUT_CSV}")
    print(f"Clean races: {base_all['counts']['races']}")


if __name__ == "__main__":
    main()
