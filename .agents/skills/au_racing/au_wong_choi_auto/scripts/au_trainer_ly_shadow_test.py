#!/usr/bin/env python3
"""Test official prior-season trainer stats as a replacement for neutral 60s."""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from statistics import mean, pstdev


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.extend([str(SCRIPT_DIR), str(SCRIPT_DIR / "racing_engine")])

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
    detect_meeting_track, load_historical_results, normalize_horse_name, parse_int,
)
from au_official_trial_shadow_test import field_summary, metrics, rank_score  # noqa: E402
from scoring import clip_score  # noqa: E402


OUTPUT_PATH = ARCHIVE_ROOT / "AU_Trainer_LY_Shadow_Backtest.md"
PRIOR = 0.365  # same all-AU place-rate prior as the already validated jockey fallback
TRAINER_RANK_WEIGHT = 0.19408 * 0.20  # jockey_trainer matrix × trainer leaf


def trainer_ly_score(stats: dict, shrinkage: float) -> float | None:
    try:
        rides = float(stats.get("rides") or 0)
        places = float(stats.get("places") or 0)
    except (TypeError, ValueError):
        return None
    if rides <= 0:
        return None
    rate = (places + shrinkage * PRIOR) / (rides + shrinkage)
    return clip_score(60.0 + (rate - PRIOR) * 100.0)


def load_races(start_index: int = 1, end_index: int | None = None) -> tuple[list[dict], dict]:
    labels = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    coverage = {"labelled_horses": 0, "neutral_trainer": 0, "neutral_with_ly": 0}
    meetings = sorted(path for path in ARCHIVE_ROOT.iterdir() if path.is_dir() and path.name != "Official_Free_Data")
    for index, meeting_dir in enumerate(meetings, 1):
        if index < start_index or (end_index is not None and index > end_index):
            continue
        if index == start_index or index % 5 == 0:
            print(f"scanning {index}/{len(meetings)}: {meeting_dir.name}", flush=True)
        day = detect_meeting_date(meeting_dir)
        if not day:
            continue
        logic_paths = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
        if not logic_paths:
            continue
        track = detect_meeting_track(meeting_dir, json.loads(logic_paths[0].read_text(encoding="utf-8")))
        for path in logic_paths:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race_no = parse_int((logic.get("race_analysis") or {}).get("race_number")) or parse_int(path.stem.split("_")[1])
            results = choose_track_rows(labels.get((day, race_no), []), track)
            lookup = {row["horse_slug"]: row for row in results}
            horses = []
            for number, horse in (logic.get("horses") or {}).items():
                result = lookup.get(normalize_horse_name(horse.get("horse_name") or ""))
                if not result:
                    continue
                # Use the archived pre-race Auto snapshot as baseline.  This
                # avoids recomputing an old race with later code/data changes.
                features = dict((horse.get("python_auto") or {}).get("feature_scores") or {})
                if not features:
                    continue
                trainer_score = float(features.get("trainer_score") or 60.0)
                ly = (horse.get("_data") or {}).get("trainer_ly") or {}
                coverage["labelled_horses"] += 1
                if abs(trainer_score - 60.0) < 0.01:
                    coverage["neutral_trainer"] += 1
                    if ly.get("rides"):
                        coverage["neutral_with_ly"] += 1
                row = {
                    "horse_number": parse_int(number, 999),
                    "actual_pos": int(result["pos"]),
                    "base": features,
                    "trainer_score": trainer_score,
                    "ly": ly,
                    "scores": {"baseline": rank_score(features)},
                }
                # Do not overwrite a curated/non-neutral trainer assessment.
                for name, k in (("trainer_ly_k20", 20.0), ("trainer_ly_k40", 40.0), ("trainer_ly_k80", 80.0)):
                    score = trainer_ly_score(ly, k)
                    if abs(trainer_score - 60.0) < 0.01 and score is not None:
                        row["scores"][name] = row["scores"]["baseline"] + TRAINER_RANK_WEIGHT * (score - trainer_score)
                    else:
                        row["scores"][name] = row["scores"]["baseline"]
                horses.append(row)
            if len(horses) < 4 or sum(1 for horse in horses if horse["actual_pos"] <= 3) < 3:
                continue
            races.append({"date": day, "meeting": meeting_dir.name, "race": race_no, "horses": horses})
    return races, coverage


def report(races: list[dict], coverage: dict) -> str:
    variants = ("baseline", "trainer_ly_k20", "trainer_ly_k40", "trainer_ly_k80")
    split = max(1, math.floor(len(races) * 0.7))
    groups = {"全樣本（描述）": races, "開發窗（較早 70%）": races[:split], "時間 holdout（較後 30%）": races[split:]}
    flat = [horse for race in races for horse in race["horses"]]
    scores = [trainer_ly_score(horse["ly"], 40.0) for horse in flat]
    scores = [score for score in scores if score is not None]
    lines = [
        "# AU Trainer LY Shadow 回測", "",
        "- 只以當時 Logic 已保存的官方往季 trainer 統計作候選，沒有使用賽後資料。",
        "- 只取代原本剛好 60 的 trainer score；既有資料庫的非中性評估不會被覆蓋。", "",
        f"- 有賽果標籤馬匹：{coverage['labelled_horses']}；trainer=60：{coverage['neutral_trainer']}；其中有官方 LY：{coverage['neutral_with_ly']}。",
        f"- K40 候選分佈：平均 {mean(scores):.1f}、標準差 {pstdev(scores):.1f}。" if scores else "- 沒有可用 trainer LY 分數。", "",
    ]
    for label, sample in groups.items():
        base = metrics(sample, "baseline")
        lines.extend([f"## {label}", "", "| 變體 | 場數 | 頭馬命中率 | Top-3 命中率 | 相對 baseline |", "|---|---:|---:|---:|---:|"])
        for variant in variants:
            value = metrics(sample, variant)
            lines.append(f"| {variant} | {value['races']} | {value['winner_rate']:.2f}% | {value['top3_precision']:.2f}% | {value['top3_precision'] - base['top3_precision']:+.2f}pp |")
        lines.append("")
    lines.extend(["## 判定", "", "只有一個 K 值在時間 holdout 的 Top-3 不低於 baseline、頭馬命中不倒退，並且開發窗方向一致，才考慮接入 trainer score。", ""])
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest official trainer prior-season stats as a neutral-score replacement.")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--start-index", type=int, default=1, help="One-based archive meeting index (for bounded replay batches)")
    parser.add_argument("--end-index", type=int, help="Inclusive archive meeting index")
    args = parser.parse_args()
    races, coverage = load_races(args.start_index, args.end_index)
    args.output.write_text(report(races, coverage), encoding="utf-8")
    print(f"eligible races: {len(races)} | {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
