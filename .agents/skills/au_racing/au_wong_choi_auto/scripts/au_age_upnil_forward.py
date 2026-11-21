#!/usr/bin/env python3
"""Forward shadow：老馬（8 歲以上）同休後第二仗 0 上名扣分（EXP-20261121-37，Kelvin 2026-11-21「go ahead」）。

EXP-20261121-37 喺新 log-loss 尺下 PASS（Holm），但特徵係睇咗同一份語料先揀 —— 所以要 forward 先信。

  baseline = live（儲存特徵 + overlay，`exact_score` 重算）
  OLD      = baseline − 3.46 分（引擎標籤 `old_horse`：8 歲以上）
  SUNIL    = baseline − 1.93 分（引擎標籤 `second_up_nil`：休後第二仗、二出 ≥3 戰 0 上名）
  幅度 = EXP-37 walk-forward β 中位，凍結唔再 fit。特徵讀 `python_auto.tags`（同 dashboard 標籤同一份定義）。

只有 START_DATE 起（標籤上線之後）嘅賽事會被扣分；之前場次 baseline = candidate，只係俾 log-loss 尺做校準。
夠 TARGET_RACES 場 forward 賽事，用 `au_logloss_ruler.evaluate` 逐個 arm 判一次（Holm 2）並凍結；未夠數只報數量（盲測）。
永遠唔會自動改模型 —— 上唔上線係 Kelvin 決定。

    python3 au_age_upnil_forward.py --output STATUS.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

EXPERIMENT_ID = "EXP-20261121-37"
CALIBRATION_SINCE = "2026-08-05"
START_DATE = "2026-11-22"
TARGET_RACES = 1000
ARMS = {"OLD": ("old_horse", -3.46), "SUNIL": ("second_up_nil", -1.93)}


def tag_keys(auto: dict) -> set:
    tags = auto.get("tags") or {}
    return {t.get("key") for tone in ("good", "bad", "note") for t in (tags.get(tone) or []) if isinstance(t, dict)}


def race_rows(logic, result_rows):
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    rows = []
    for number, horse in (logic.get("horses") or {}).items():
        auto = (horse or {}).get("python_auto") or {}
        features = auto.get("feature_scores") or {}
        result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
        if not features or result is None:
            continue
        row = {"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
               "wet": auto.get("wet_form_feature") or 0.0, "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0, "draw": float(auto.get("draw_feature") or 0.0),
               "features": dict(features), "keys": sorted(k for k in tag_keys(auto) if k)}
        row["ability"] = exact_score(row, MATRIX_WEIGHTS)
        rows.append(row)
    return rows


def collect(root):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for meeting_dir in meeting_dirs(root):
        date = detect_meeting_date(meeting_dir)
        if not date or date < CALIBRATION_SINCE:
            continue
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue
        track = detect_meeting_track(meeting_dir, json.loads(logic_files[0].read_text(encoding="utf-8")))
        for path in logic_files:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race_no = int(str((logic.get("race_analysis") or {}).get("race_number") or path.stem.split("_")[1]))
            rows = choose_track_rows(results.get((date, race_no), []), track)
            if not rows:
                continue
            got = race_rows(logic, rows)
            if sum(r["pos"] <= 3 for r in got) >= 3 and any(r["pos"] == 1 for r in got):
                races.append({"meeting": meeting_dir.name, "date": date, "race": race_no, "rows": got})
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def candidate(races, key, beta):
    out = []
    for r in races:
        if r["date"] < START_DATE:
            out.append(r)
            continue
        out.append(dict(r, rows=[dict(x, ability=x["ability"] + (beta if key in x["keys"] else 0.0)) for x in r["rows"]]))
    return out


def evaluate(races):
    from au_logloss_ruler import eligible, evaluate as ll_evaluate
    base = eligible(races)
    out = {}
    for name, (key, beta) in ARMS.items():
        v = ll_evaluate(base, eligible(candidate(races, key, beta)), nnull=200)
        out[name] = {k: v[k] for k in ("verdict", "reason", "checks", "dlogloss", "beats_null_share", "gold_pp", "good_pp",
                                         "capture5_pp", "top2_any_hit_pp")}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    from au_archive_calibrator import ARCHIVE_ROOT

    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} forward 已判（凍結）")
        return
    races = collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT)
    forward = [r for r in races if r["date"] >= START_DATE]
    flagged = {name: sum(1 for r in forward for x in r["rows"] if key in x["keys"]) for name, (key, _b) in ARMS.items()}
    status = {"experiment": EXPERIMENT_ID, "start_date": START_DATE, "target_races": TARGET_RACES,
              "races_collected": len(forward), "race_days": len({r["date"] for r in forward}),
              "arms": {k: {"tag": t, "beta": b} for k, (t, b) in ARMS.items()},
              "interim": {"horses_flagged": flagged, "note": "盲測：未夠數只報數量"},
              "outcomes_visible": len(forward) >= TARGET_RACES,
              "state": "evaluated" if len(forward) >= TARGET_RACES else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if status["outcomes_visible"]:
        cutoff = sorted(r["date"] for r in forward)[TARGET_RACES - 1]
        status["evaluation"] = evaluate([r for r in races if r["date"] <= cutoff])
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
