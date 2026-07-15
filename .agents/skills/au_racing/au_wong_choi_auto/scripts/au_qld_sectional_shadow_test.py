#!/usr/bin/env python3
"""Leakage-safe test of prior QLD runner-level 200m sectional history."""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from statistics import mean


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.extend([str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
    detect_meeting_track, load_historical_results, normalize_horse_name, parse_int,
)
from au_official_trial_feature_enrich import normalise_name  # noqa: E402
from au_official_trial_shadow_test import field_summary, metrics, rank_score  # noqa: E402
from engine_core import RacingEngine  # noqa: E402
from scoring import clip_score  # noqa: E402


RUNNERS_PATH = ARCHIVE_ROOT / "Official_Free_Data" / "qld_race_sectional_runners.jsonl"
OUTPUT_PATH = ARCHIVE_ROOT / "AU_QLD_Runner_Sectional_Shadow_Backtest.md"


def _last_n_seconds(row: dict, n: int) -> float | None:
    values = [segment.get("segment_time_seconds") for segment in row.get("segments_200m") or []]
    values = [float(value) for value in values if value is not None and float(value) > 0]
    return sum(values[-n:]) if len(values) >= n else None


def load_history() -> dict[str, list[dict]]:
    raw = [json.loads(line) for line in RUNNERS_PATH.read_text(encoding="utf-8").splitlines()]
    by_race: dict[tuple[str, str, int], list[dict]] = defaultdict(list)
    for row in raw:
        by_race[(row["date"], row["track_token"], int(row["race_number"]))].append(row)
    history: dict[str, list[dict]] = defaultdict(list)
    for (day, track, race), runners in by_race.items():
        scored = [(row, _last_n_seconds(row, 3), _last_n_seconds(row, 2)) for row in runners]
        valid = [(row, last600, last400) for row, last600, last400 in scored if last600 is not None]
        ranked600 = sorted(valid, key=lambda item: item[1])
        rank_by_name = {normalise_name(row["horse_name"]): rank for rank, (row, _, _) in enumerate(ranked600, 1)}
        count = len(ranked600)
        for row, last600, last400 in valid:
            rank = rank_by_name[normalise_name(row["horse_name"])]
            # 1.0 = fastest last 600 in that actual race; 0.0 = slowest.
            close_score = (count - rank) / (count - 1) if count > 1 else 0.5
            history[normalise_name(row["horse_name"])].append({
                "date": day, "track": track, "race": race,
                "last600_seconds": round(last600, 3), "last400_seconds": round(last400, 3) if last400 else None,
                "last600_rank": rank, "field_with_sectionals": count,
                "close_score": round(close_score, 4), "finish_position": row.get("finish_position"),
            })
    for rows in history.values():
        rows.sort(key=lambda row: row["date"], reverse=True)
    return history


def prior_feature(history: list[dict], as_of: str) -> dict | None:
    rows = [row for row in history if row["date"] < as_of]
    if not rows:
        return None
    rows = rows[:3]
    weights = [1.0, 0.6, 0.35][:len(rows)]
    score = sum(row["close_score"] * weight for row, weight in zip(rows, weights)) / sum(weights)
    return {"count": len(rows), "close_score": score, "latest_date": rows[0]["date"], "latest_rank": rows[0]["last600_rank"], "latest_field": rows[0]["field_with_sectionals"]}


def load_races() -> list[dict]:
    history = load_history()
    labels = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    print(f"QLD runner histories: {len(history)} horses | scanning {len(meetings)} meetings", flush=True)
    for index, meeting_dir in enumerate(meetings, 1):
        if index == 1 or index % 10 == 0:
            print(f"  meeting {index}/{len(meetings)}: {meeting_dir.name}", flush=True)
        day = detect_meeting_date(meeting_dir)
        if not day:
            continue
        files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda path: parse_int(path.stem.split("_")[1], 999))
        if not files:
            continue
        track = detect_meeting_track(meeting_dir, json.loads(files[0].read_text(encoding="utf-8")))
        for path in files:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race_no = parse_int((logic.get("race_analysis") or {}).get("race_number")) or parse_int(path.stem.split("_")[1])
            result_rows = choose_track_rows(labels.get((day, race_no), []), track)
            lookup = {row["horse_slug"]: row for row in result_rows}
            context = dict(logic.get("race_analysis") or {})
            context["field_summary"] = field_summary(logic.get("horses") or {})
            horses = []
            for number, horse in (logic.get("horses") or {}).items():
                actual = lookup.get(normalize_horse_name(horse.get("horse_name") or ""))
                feature = prior_feature(history.get(normalise_name(horse.get("horse_name") or ""), []), day)
                if not actual or not feature:
                    continue
                auto = RacingEngine(horse, context, str((horse.get("_data") or {}).get("facts_section") or "")).analyze_horse()
                base = dict(auto.get("feature_scores") or {})
                baseline = rank_score(base)
                horses.append({"horse_number": parse_int(number, 999), "actual_pos": int(actual["pos"]), "feature": feature, "base": base, "scores": {"baseline": baseline}})
            if len(horses) < 4 or sum(1 for horse in horses if horse["actual_pos"] <= 3) < 3:
                continue
            for horse in horses:
                centered = horse["feature"]["close_score"] - 0.5
                soft = dict(horse["base"]); soft["sectional_score"] = clip_score(soft.get("sectional_score", 60) + centered * 6.0)
                medium = dict(horse["base"]); medium["sectional_score"] = clip_score(medium.get("sectional_score", 60) + centered * 12.0)
                horse["scores"]["prior_qld_close_soft"] = rank_score(soft)
                horse["scores"]["prior_qld_close_medium"] = rank_score(medium)
            races.append({"date": day, "meeting": meeting_dir.name, "race": race_no, "horses": horses})
    return races


def report(races: list[dict]) -> str:
    variants = ("baseline", "prior_qld_close_soft", "prior_qld_close_medium")
    split = max(1, math.floor(len(races) * 0.7))
    groups = {"全樣本（描述）": races, "開發窗（較早 70%）": races[:split], "時間 holdout（較後 30%）": races[split:]}
    lines = ["# AU QLD Runner Sectional Shadow 回測", "", "- 僅使用日期早於今場的 QLD 逐馬 200m sectionals。", "- 特徵是過往賽事末段 600m 的同場相對排名，並非同場賽後資料。", ""]
    for label, sample in groups.items():
        base = metrics(sample, "baseline")
        lines.extend([f"## {label}", "", "| 變體 | 場數 | 頭馬命中率 | Top-3 命中率 | 相對 baseline |", "|---|---:|---:|---:|---:|"])
        for variant in variants:
            value = metrics(sample, variant)
            lines.append(f"| {variant} | {value['races']} | {value['winner_rate']:.2f}% | {value['top3_precision']:.2f}% | {value['top3_precision'] - base['top3_precision']:+.2f}pp |")
        lines.append("")
    lines.extend(["## 判定", "", "樣本不足或時間 holdout 未改善時，絕不接入正式段速分。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Test prior QLD runner sectionals without leakage.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    races = load_races()
    args.output.write_text(report(races), encoding="utf-8")
    print(f"eligible races: {len(races)} | {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
