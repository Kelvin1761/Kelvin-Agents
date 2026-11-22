#!/usr/bin/env python3
"""重建練馬師剩餘表現表（EXP-20261122-02，實驗性上線 2026-11-22）。排程每晚賽果摺入之後、分析下一日之前跑。

同研究（`docs/experiments/patches/au_people_residual/run.py`）一樣嘅計法：
  * 2026-08-05 起乾淨語料、有頭馬兼 ≥3 匹入三甲嘅場次（`au_logloss_ruler.eligible`）；
  * 綜合分 = 儲存 `ability_score` 減走 `old_horse_feature` 同 `trainer_residual_feature`（唔畀 overlay 自己餵自己）；
  * p = σ(a + α·(綜合分 − 場均))，(a, α) = `au_logloss_ruler.calibrations`（只用之前賽日；warm-up 日唔累積）；
  * 練馬師（Logic 賽前名，正規化）逐日累積 Σ(入三甲 − p) 同出賽數。

輸出 `<資料根>/AU_Trainer_Residual.json`：{"trainers": {名: [[日期, 累積剩餘, 出賽數], ...]}}；
引擎只用**早過賽日**嘅最後一筆（`people_overlays.trainer_raw`），所以重評分舊場次唔會前視。

    python3 au_trainer_residual_table.py [--data-root DIR] [--output PATH]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

from au_racing_engine.people_overlays import TRAINER_BETA, TRAINER_K, default_table_path, norm  # noqa: E402


def collect(root):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, get_true_horse_name, load_historical_results,
                                       normalize_horse_name)
    from au_logloss_ruler import CLEAN_SINCE
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for meeting_dir in meeting_dirs(root):
        date = detect_meeting_date(meeting_dir)
        if not date or date < CLEAN_SINCE:
            continue
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue
        track = detect_meeting_track(meeting_dir, json.loads(logic_files[0].read_text(encoding="utf-8")))
        for path in logic_files:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race_no = int(str((logic.get("race_analysis") or {}).get("race_number") or path.stem.split("_")[1]))
            res = choose_track_rows(results.get((date, race_no), []), track)
            if not res:
                continue
            lookup = {normalize_horse_name(r["horse_slug"]): r for r in res}
            rows = []
            for horse in (logic.get("horses") or {}).values():
                auto = (horse or {}).get("python_auto") or {}
                result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
                if auto.get("ability_score") is None or result is None:
                    continue
                ability = (float(auto["ability_score"]) - float(auto.get("old_horse_feature") or 0.0)
                           - float(auto.get("trainer_residual_feature") or 0.0)
                           - float(auto.get("people_prize_feature") or 0.0)
                           - float(auto.get("people_prize_leaf_delta") or 0.0))
                rows.append({"ability": ability, "pos": int(result["pos"]), "trainer": norm(horse.get("trainer"))})
            if rows:
                races.append({"meeting": meeting_dir.name, "date": date, "race": race_no, "rows": rows})
    return races


def build(races):
    from au_logloss_ruler import calibrations, eligible

    races = eligible(races)
    cal = calibrations(races)
    by_day = defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    cum_r, cum_n, table = defaultdict(float), defaultdict(int), defaultdict(list)
    for day in sorted(by_day):
        if day not in cal:
            continue
        a, alpha = cal[day]
        touched = set()
        for r in by_day[day]:
            mean = sum(x["ability"] for x in r["rows"]) / len(r["rows"])
            for x in r["rows"]:
                if not x["trainer"]:
                    continue
                p = 1 / (1 + math.exp(-(a + alpha * (x["ability"] - mean))))
                cum_r[x["trainer"]] += (1 if x["pos"] <= 3 else 0) - p
                cum_n[x["trainer"]] += 1
                touched.add(x["trainer"])
        for t in touched:
            table[t].append([day, round(cum_r[t], 6), cum_n[t]])
    return dict(table), (max(by_day) if by_day else None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    from au_archive_calibrator import ARCHIVE_ROOT

    races = collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT)
    table, as_of = build(races)
    out = Path(args.output) if args.output else default_table_path()
    payload = {"experiment": "EXP-20261122-02", "built_at": datetime.now(timezone.utc).isoformat(), "as_of": as_of,
               "k": TRAINER_K, "beta": TRAINER_BETA, "races": len(races), "trainers": table}
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(out)
    print(json.dumps({"as_of": as_of, "races": len(races), "trainers": len(table), "output": str(out)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
