#!/usr/bin/env python3
"""Leakage-safe shadow tests for trainer and jockey/horse context signals.

Every candidate only sees labelled archive results strictly before the meeting
date being ranked.  Meetings on the same day are scored before any of that
day's results enter the rolling histories.  The archived pre-race rank score
is always the baseline, so this is an overlay test rather than a re-fit.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
import json
from collections import defaultdict
from datetime import date
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.extend([str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
    detect_meeting_track, load_historical_results, normalize_horse_name, parse_int,
)
from au_official_trial_shadow_test import metrics  # noqa: E402
from scoring import clip_score  # noqa: E402


OUTPUT_PATH = ARCHIVE_ROOT / "AU_JT_Context_Shadow_Backtest.md"
TRAINER_RANK_WEIGHT = 0.19408 * 0.20
FIT_RANK_WEIGHT = 0.19408 * 0.52
PLACE_PRIOR = 0.365


def clean(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def meeting_day(value: str) -> date:
    return date.fromisoformat(value)


def distance_bucket(row: dict) -> str:
    text = str((row.get("data") or {}).get("distance_profile_line") or "")
    match = re.search(r"今仗\s*(\d{3,4})\s*m", text)
    metres = int(match.group(1)) if match else 0
    if metres <= 1200:
        return "sprint"
    if metres <= 1600:
        return "mile"
    return "staying" if metres else "unknown"


def posterior_score(entries: list[dict], shrink: float) -> float | None:
    runs = len(entries)
    if not runs:
        return None
    places = sum(entry["top3"] for entry in entries)
    rate = (places + shrink * PLACE_PRIOR) / (runs + shrink)
    return clip_score(60.0 + (rate - PLACE_PRIOR) * 100.0)


def trainer_overlay(base: float, candidate: float | None) -> float:
    # Existing curated/non-neutral trainer reads are deliberately untouched.
    if abs(base - 60.0) > 0.01 or candidate is None:
        return 0.0
    return TRAINER_RANK_WEIGHT * (candidate - base)


def fit_overlay(row: dict) -> float:
    """A deliberately small *new* rider/horse confirmation overlay.

    It is only tested where the historic snapshot still had a neutral fit
    score, so it cannot double count a fit already credited by the engine.
    """
    features = row.get("feature_scores") or {}
    if abs(float(features.get("jockey_horse_fit_score") or 60.0) - 60.0) > 0.01:
        return 0.0
    data = row.get("data") or {}
    rides = int(float(data.get("current_jockey_formal_rides") or 0))
    places = int(float(data.get("current_jockey_formal_places") or 0))
    wins = int(float(data.get("current_jockey_formal_wins") or 0))
    if rides >= 2 and places / rides >= 0.50:
        return FIT_RANK_WEIGHT * (3.0 + (1.0 if wins else 0.0))
    signal = str(data.get("jockey_change_signal") or "")
    if "試閘手接手" in signal or "沿用上仗騎師" in signal:
        return FIT_RANK_WEIGHT * 2.0
    return 0.0


def load_races() -> tuple[list[dict], dict]:
    labels = load_historical_results(HISTORICAL_RESULTS_CSV)
    raw: list[list[dict]] = []
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    for index, meeting_dir in enumerate(meetings, 1):
        if index == 1 or index % 100 == 0:
            print(f"reading Logic snapshots {index}/{len(meetings)}", flush=True)
        day = detect_meeting_date(meeting_dir)
        logic_paths = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not day or not logic_paths:
            continue
        first = json.loads(logic_paths[0].read_text(encoding="utf-8"))
        track = detect_meeting_track(meeting_dir, first)
        for logic_path in logic_paths:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
            race_no = parse_int((logic.get("race_analysis") or {}).get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            lookup = {item["horse_slug"]: item for item in choose_track_rows(labels.get((day, race_no), []), track)}
            rows: list[dict] = []
            for number, horse in (logic.get("horses") or {}).items():
                actual = lookup.get(normalize_horse_name(horse.get("horse_name") or ""))
                auto = horse.get("python_auto") or {}
                features = auto.get("feature_scores") or {}
                if not actual or not features:
                    continue
                rows.append({
                    "date": day, "meeting": meeting_dir.name, "track": track, "race": race_no,
                    "horse_number": parse_int(number, 999), "actual_pos": int(actual["pos"]),
                    "model_score": float(auto.get("rank_score") or auto.get("ability_score") or 0.0),
                    "feature_scores": features, "data": horse.get("_data") or {}, "horse": horse,
                })
            if len(rows) >= 4 and any(row["actual_pos"] == 1 for row in rows) and sum(row["actual_pos"] <= 3 for row in rows) >= 3:
                raw.append(rows)
    raw.sort(key=lambda rows: (rows[0]["date"], rows[0]["meeting"], rows[0]["race"]))
    history: dict[str, list[dict]] = defaultdict(list)
    races: list[dict] = []
    coverage = defaultdict(int)
    by_day: dict[str, list[list[dict]]] = defaultdict(list)
    for rows in raw:
        by_day[rows[0]["date"]].append(rows)

    for day_text in sorted(by_day):
        today = meeting_day(day_text)
        pending: list[dict] = []
        for rows in by_day[day_text]:
            horses = []
            for row in rows:
                trainer = clean((row.get("horse") or {}).get("trainer"))
                previous = history.get(trainer, [])
                recent90 = [entry for entry in previous if 0 < (today - entry["day"]).days <= 90]
                recent365 = [entry for entry in previous if 0 < (today - entry["day"]).days <= 365]
                td = [entry for entry in previous if entry["track"] == clean(row.get("track")) and entry["distance"] == distance_bucket(row)]
                td365 = [entry for entry in td if 0 < (today - entry["day"]).days <= 365]
                baseline = float(row.get("model_score") or row.get("rank_score") or 0.0)
                tscore = float((row.get("feature_scores") or {}).get("trainer_score") or 60.0)
                roll90 = posterior_score(recent90, 10.0) if len(recent90) >= 5 else None
                roll365 = posterior_score(recent365, 20.0) if len(recent365) >= 10 else None
                # Point 1: 90d state where possible; otherwise a larger 365d sample.
                rolling = roll90 if roll90 is not None else roll365
                # Point 2: same trainer + venue + distance band; deliberately
                # requires four prior starters and stronger shrinkage.
                track_distance = posterior_score(td365, 12.0) if len(td365) >= 4 else None
                if roll90 is not None:
                    coverage["rolling90"] += 1
                if roll365 is not None:
                    coverage["rolling365"] += 1
                if track_distance is not None:
                    coverage["track_distance"] += 1
                fit_delta = fit_overlay(row)
                if fit_delta:
                    coverage["horse_jockey_fit"] += 1
                scores = {"baseline": baseline}
                scores["p1_trainer_rolling"] = baseline + trainer_overlay(tscore, rolling)
                scores["p2_trainer_track_distance"] = baseline + trainer_overlay(tscore, track_distance)
                scores["p1_p2_combined"] = baseline + trainer_overlay(tscore, rolling) + trainer_overlay(tscore, track_distance)
                scores["p3_horse_jockey_confirm"] = baseline + fit_delta
                scores["p1_p2_p3_combined"] = scores["p1_p2_combined"] + fit_delta
                horses.append({
                    "horse_number": int(row.get("horse_number") or 999),
                    "actual_pos": int(row["actual_pos"]),
                    "scores": scores,
                })
                pending.append({
                    "trainer": trainer,
                    "day": today,
                    "track": clean(row.get("track")),
                    "distance": distance_bucket(row),
                    "top3": int(row["actual_pos"] <= 3),
                })
            races.append({"date": day_text, "meeting": rows[0]["meeting"], "race": rows[0]["race"], "horses": horses})
        # Atomic same-day update: nothing from a morning race informs the
        # afternoon racecard, and no duplicate same-day result leaks in.
        for entry in pending:
            if entry["trainer"]:
                history[entry["trainer"]].append(entry)
    return races, dict(coverage)


def report(races: list[dict], coverage: dict) -> str:
    variants = (
        "baseline", "p1_trainer_rolling", "p2_trainer_track_distance",
        "p1_p2_combined", "p3_horse_jockey_confirm", "p1_p2_p3_combined",
    )
    split = max(1, math.floor(len(races) * 0.7))
    groups = {
        "全樣本（描述）": races,
        "開發窗（較早 70%）": races[:split],
        "時間 holdout（較後 30%）": races[split:],
    }
    lines = [
        "# AU 騎練 Context Shadow 回測", "",
        "- 所有 trainer 歷史只累積至該日之前；同日賽事採原子更新，沒有賽後 leakage。",
        "- P1 只改原本 60 分的練馬師分；P2 為同場館×路程帶；P3 只測原本 60 分的人馬配搭確認。",
        "- 固定先驗、最少樣本及幅度，沒有按賽果調參。", "",
        "## 覆蓋", "",
        f"- 可用完整賽果：{len(races)} 場。",
        f"- P1 近90日：{coverage.get('rolling90', 0)} 馬；近365日 fallback：{coverage.get('rolling365', 0)} 馬。",
        f"- P2 同場館×路程帶：{coverage.get('track_distance', 0)} 馬。",
        f"- P3 原本中性而有明確人馬確認：{coverage.get('horse_jockey_fit', 0)} 馬。", "",
    ]
    for label, sample in groups.items():
        base = metrics(sample, "baseline")
        lines.extend([f"## {label}", "", "| 變體 | 場數 | 頭馬命中率 | Top-3 命中率 | 相對 baseline |", "|---|---:|---:|---:|---:|"])
        for variant in variants:
            value = metrics(sample, variant)
            lines.append(f"| {variant} | {value['races']} | {value['winner_rate']:.2f}% | {value['top3_precision']:.2f}% | {value['top3_precision'] - base['top3_precision']:+.2f}pp |")
        lines.append("")
    # A single 70/30 split can be moved by one race.  Show four consecutive
    # out-of-sample-style chronological blocks before considering promotion.
    lines.extend(["## P1 連續時間窗穩健性", "", "| 時間窗 | 場數 | baseline 頭馬 | P1 頭馬 | baseline Top-3 | P1 Top-3 | Top-3 差異 |", "|---|---:|---:|---:|---:|---:|---:|"])
    width = max(1, math.ceil(len(races) / 4))
    for index in range(4):
        sample = races[index * width:(index + 1) * width]
        if not sample:
            continue
        base = metrics(sample, "baseline")
        p1 = metrics(sample, "p1_trainer_rolling")
        lines.append(f"| 第 {index + 1} 窗 | {len(sample)} | {base['winner_rate']:.2f}% | {p1['winner_rate']:.2f}% | {base['top3_precision']:.2f}% | {p1['top3_precision']:.2f}% | {p1['top3_precision'] - base['top3_precision']:+.2f}pp |")
    lines.append("")
    lines.extend([
        "## 接入門檻", "",
        "單項只有在時間 holdout 的 Top-3 不低於 baseline、頭馬命中不倒退，且開發窗方向一致，才可進入正式分數。P4（官方試閘騎師＝今場騎師）由 `au_official_trial_shadow_test.py` 獨立回測，避免把有限官方試閘樣本混入此 archive。", "",
    ])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Leakage-safe trainer/JT context shadow tests")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args()
    races, coverage = load_races()
    args.output.write_text(report(races, coverage), encoding="utf-8")
    print(f"eligible races: {len(races)} | {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
