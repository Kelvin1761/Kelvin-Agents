#!/usr/bin/env python3
"""Leakage-safe joint shadow for relative barrier and pace-performance weights.

No result from the meeting being ranked is available to either candidate.  The
barrier statistic uses only raw result rows dated before the meeting; pace tests
only reweight archived pre-race 7D matrix scores.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.extend([str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])
from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
    detect_meeting_track, load_historical_results, normalize_horse_name, normalize_track_name, parse_int,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402

OUT = ARCHIVE_ROOT / "AU_Barrier_Pace_Shadow_Backtest.md"
KEYS = tuple(MATRIX_WEIGHTS)


def as_date(value: str) -> date:
    return date.fromisoformat(value)


def dist_band(value: object) -> str:
    d = int(float(value or 0))
    if d <= 1200:
        return "短途≤1200"
    if d <= 1600:
        return "中程1201-1600"
    return "長途1601+"


def field_band(n: int) -> str:
    return "8-" if n <= 8 else ("9-12" if n <= 12 else "13+")


def relative_draw_bin(barrier: int, field: int) -> str:
    if field <= 1:
        return "中"
    q = (barrier - 1) / (field - 1)
    if q <= .20:
        return "內"
    if q <= .45:
        return "內中"
    if q <= .70:
        return "外中"
    return "外"


def parse_sp(value: object) -> float | None:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    return float(match.group()) if match else None


def normalized_with_pace(pace_weight: float) -> dict[str, float]:
    other = sum(v for k, v in MATRIX_WEIGHTS.items() if k != "pace_perf")
    remaining = 1.0 - pace_weight
    return {key: (pace_weight if key == "pace_perf" else value / other * remaining)
            for key, value in MATRIX_WEIGHTS.items()}


def matrix_score(row: dict, weights: dict[str, float], barrier: float | None = None) -> float:
    matrix = dict(row["matrix"])
    if barrier is not None:
        matrix["race_shape"] = barrier
    return sum(matrix[key] * weights[key] for key in KEYS)


def debut_adjusted_matrix(row: dict, *, trial_proxy: bool = False, low_sample_shrink: bool = False) -> dict[str, float]:
    """Small, auditable initial-career alternatives; not a wholesale new model."""
    matrix = dict(row["matrix"])
    starts = row["starts"]
    if starts == 0:
        # No official race has occurred, so a below-neutral stability proxy must
        # not masquerade as negative evidence.
        matrix["stability"] = 60.0
        if trial_proxy:
            f = row["features"]
            # Trial is supporting evidence only: it cannot become an actual
            # sectional figure, and the 60-neutral pace figure remains largest.
            matrix["pace_perf"] = (
                .65 * float(f.get("pace_figure_score") or 60.0)
                + .20 * float(f.get("sectional_score") or 60.0)
                + .15 * float(f.get("trial_score") or 60.0)
            )
    elif low_sample_shrink and starts <= 3:
        # Shrink a 1-3 run result toward neutral rather than reward/punish a
        # single race as if it were a five-run form cycle.
        matrix["stability"] = 60.0 + (matrix["stability"] - 60.0) * starts / (starts + 2.0)
    return matrix


def custom_matrix_score(matrix: dict[str, float], weights: dict[str, float]) -> float:
    return sum(matrix[key] * weights[key] for key in KEYS)


def has_actual_pace(row: dict) -> bool:
    feature = row["features"]
    provenance = row.get("provenance") or {}
    p = str(provenance.get("pace_figure_score") or "")
    return (float(feature.get("pace_figure_score") or 60.0) != 60.0
            and p not in {"missing_neutral", "no_spread", ""})


def stat_score(stats: dict, prior: float) -> float | None:
    n = int(stats.get("n") or 0)
    if n < 25:
        return None
    # Strong shrinkage protects sparse track/distance cells from becoming a
    # fabricated bias.  Place rate, not win rate, matches a Top-3 ranking task.
    rate = (stats["top3"] + 30 * prior) / (n + 30)
    return max(50.0, min(70.0, 60.0 + (rate - prior) * 100.0))


def metrics(races: list[dict], variant: str) -> dict[str, float | int]:
    win = top3 = winner_top3 = stakes = 0
    flat_return = box_return = value_stakes = value_return = 0.0
    for race in races:
        ranked = sorted(race["horses"], key=lambda h: (-h["scores"][variant], h["num"]))
        picks = ranked[:3]
        first = ranked[0]
        win += int(first["pos"] == 1)
        top3 += sum(h["pos"] <= 3 for h in picks)
        winner_top3 += int(any(h["pos"] == 1 for h in picks))
        stakes += 1
        if first["pos"] == 1 and first["sp"]:
            flat_return += first["sp"]
        # A three-horse win box: three $1 bets, returned price if any selection wins.
        box_return += next((h["sp"] for h in picks if h["pos"] == 1 and h["sp"]), 0.0)
        for h in picks:
            if h["sp"] and h["sp"] >= 4.0:
                value_stakes += 1
                if h["pos"] == 1:
                    value_return += h["sp"]
    n = len(races) or 1
    return {
        "races": len(races), "top1": win / n * 100, "top3": top3 / (3 * n) * 100,
        "winner_top3": winner_top3 / n * 100, "flat_roi": (flat_return / stakes - 1) * 100 if stakes else 0,
        "box_roi": (box_return / (stakes * 3) - 1) * 100 if stakes else 0,
        "value_roi": (value_return / value_stakes - 1) * 100 if value_stakes else 0,
        "value_stakes": int(value_stakes),
    }


def load_races() -> list[dict]:
    labels = load_historical_results(HISTORICAL_RESULTS_CSV)
    # Raw rows grouped by date, for a genuine pre-race barrier history.
    raw_by_day: dict[str, list[dict]] = defaultdict(list)
    with HISTORICAL_RESULTS_CSV.open(encoding="utf-8-sig", newline="") as handle:
        for item in csv.DictReader(handle):
            barrier = parse_int(item.get("Barrier"))
            pos = parse_int(item.get("Pos"))
            race_no = parse_int(item.get("Race"))
            if not barrier or barrier <= 0 or not pos or not race_no or not item.get("Date"):
                continue
            raw_by_day[str(item["Date"])].append({
                "date": str(item["Date"]), "track": str(item.get("Track") or ""), "race": race_no,
                "distance": parse_int(item.get("Distance")) or 0, "barrier": barrier, "pos": pos,
            })
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    archive: list[dict] = []
    for index, meeting in enumerate(meetings, 1):
        if index == 1 or index % 20 == 0:
            print(f"reading pre-race snapshots {index}/{len(meetings)}", flush=True)
        day = detect_meeting_date(meeting)
        paths = sorted(meeting.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not day or not paths:
            continue
        first = json.loads(paths[0].read_text(encoding="utf-8"))
        track = detect_meeting_track(meeting, first)
        for path in paths:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race = parse_int((logic.get("race_analysis") or {}).get("race_number")) or parse_int(path.stem.split("_")[1])
            rows = choose_track_rows(labels.get((day, race), []), track)
            lookup = {r["horse_slug"]: r for r in rows}
            horses = []
            for num, horse in (logic.get("horses") or {}).items():
                outcome = lookup.get(normalize_horse_name(horse.get("horse_name") or ""))
                auto = horse.get("python_auto") or {}
                matrix = auto.get("matrix_scores") or {}
                features = auto.get("feature_scores") or {}
                if not outcome or not matrix or not features:
                    continue
                pace = matrix.get("pace_perf", matrix.get("sectional", 60.0))
                horses.append({
                    "num": parse_int(num, 999), "barrier": int(horse.get("barrier") or 0),
                    "pos": int(outcome["pos"]), "sp": outcome.get("sp"),
                    "starts": int(float(horse.get("career_race_starts") or 0)),
                    "matrix": {**{key: float(matrix.get(key, 60.0) or 60.0) for key in KEYS}, "pace_perf": float(pace or 60.0)},
                    "features": features, "provenance": auto.get("score_provenance") or {},
                })
            if len(horses) >= 4 and sum(h["pos"] <= 3 for h in horses) >= 3:
                archive.append({"date": day, "track": normalize_track_name(track),
                                "distance": int(re.search(r"\d+", str((logic.get("race_analysis") or {}).get("distance") or "0")).group() or 0),
                                "horses": horses})
    archive.sort(key=lambda r: r["date"])

    # Update histories strictly before each date, then score all archive races of date.
    history_global: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "top3": 0})
    history_track: dict[tuple, dict] = defaultdict(lambda: {"n": 0, "top3": 0})
    result: list[dict] = []
    all_days = sorted(set(raw_by_day) | {r["date"] for r in archive})
    archive_by_day: dict[str, list[dict]] = defaultdict(list)
    for race in archive:
        archive_by_day[race["date"]].append(race)
    prior = .30
    for day in all_days:
        for race in archive_by_day.get(day, []):
            field = len(race["horses"])
            band = dist_band(race["distance"])
            fb = field_band(field)
            for horse in race["horses"]:
                rel = relative_draw_bin(horse["barrier"], field)
                gkey = (band, fb, rel)
                tkey = (race["track"], band, fb, rel)
                candidate = stat_score(history_track[tkey], prior) or stat_score(history_global[gkey], prior)
                base = normalized_with_pace(MATRIX_WEIGHTS["pace_perf"])
                moderate = normalized_with_pace(.22)
                strong = normalized_with_pace(.26)
                dynamic_weight = .23 if has_actual_pace(horse) else .15
                dynamic = normalized_with_pace(dynamic_weight)
                horse["scores"] = {
                    "baseline": matrix_score(horse, base),
                    "pace_moderate": matrix_score(horse, moderate),
                    "pace_strong": matrix_score(horse, strong),
                    "pace_dynamic": matrix_score(horse, dynamic),
                    "barrier_relative": matrix_score(horse, base, candidate),
                    "barrier_plus_dynamic_pace": matrix_score(horse, dynamic, candidate),
                    "debut_neutral_stability": custom_matrix_score(debut_adjusted_matrix(horse), base),
                    "debut_trial_proxy": custom_matrix_score(debut_adjusted_matrix(horse, trial_proxy=True), base),
                    "low_sample_stability_shrink": custom_matrix_score(debut_adjusted_matrix(horse, low_sample_shrink=True), base),
                }
            result.append(race)
        # Commit entire date only after all racecards have been scored.
        for row in raw_by_day.get(day, []):
            field_rows = labels.get((row["date"], row["race"]), [])
            size = len(field_rows)
            if size < 2:
                continue
            band = dist_band(row.get("distance"))
            fb = field_band(size)
            rel = relative_draw_bin(int(row["barrier"]), size)
            for store, key in ((history_global, (band, fb, rel)),
                               (history_track, (normalize_track_name(row["track"]), band, fb, rel))):
                store[key]["n"] += 1
                store[key]["top3"] += int(row["pos"] <= 3)
    return result


def render(races: list[dict]) -> str:
    variants = ("baseline", "pace_moderate", "pace_strong", "pace_dynamic", "barrier_relative", "barrier_plus_dynamic_pace", "debut_neutral_stability", "debut_trial_proxy", "low_sample_stability_shrink")
    split = max(1, int(len(races) * .7))
    groups = {"全樣本（描述）": races, "開發窗（較早70%）": races[:split], "時間 holdout（較後30%）": races[split:]}
    lines = ["# AU 檔位×段速×初出 Shadow 回測", "", "- 檔位候選只使用該賽日前 raw results；同日結果不會進入統計。", "- 檔位以相對 field position（非絕對 1／12 檔）×場地×路程帶×field size，並以 place-rate 強收縮。", "- 段速只改 7D 權重；dynamic 僅在實測 pace figure 可用時升至 23%，否則降至 15%。", "- 初出候選不創造實測段速：只把缺正式賽樣本的穩定性調回中性，或把試閘 leaf 由 4.7% 小幅升至 15%。", ""]
    for label, sample in groups.items():
        base = metrics(sample, "baseline")
        lines.extend([f"## {label}", "", "| 版本 | 場數 | Top1 | Top3 | 頭馬在Top3 | 單WIN ROI | 三匹WIN box ROI | ≥$4價值ROI |", "|---|---:|---:|---:|---:|---:|---:|---:|"])
        for variant in variants:
            m = metrics(sample, variant)
            lines.append(f"| {variant} | {m['races']} | {m['top1']:.2f}% | {m['top3']:.2f}% | {m['winner_top3']:.2f}% | {m['flat_roi']:+.1f}% | {m['box_roi']:+.1f}% | {m['value_roi']:+.1f}% |")
        lines.append("")
    lines.extend(["## 接入門檻", "", "候選必須在時間 holdout 不令 Top1、Top3、頭馬在Top3 任何一項倒退，且 ROI 方向不惡化，才可修改 live 公式。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUT)
    args = parser.parse_args()
    races = load_races()
    args.output.write_text(render(races), encoding="utf-8")
    print(f"eligible races: {len(races)} | {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
