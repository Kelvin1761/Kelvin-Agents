#!/usr/bin/env python3
"""Forward 退回監察：近績質素分場內 SD 下限（F1，EXP-20261123-06，Kelvin 2026-11-24 批准上線）。

上線版：`stability.field_z` 除數 = max(場內 SD, 0.3065)。呢度判「上線版 vs 冇下限」：
  baseline  = 上線版 feature，但 `form_quality_score` 用 `stability.score_without_floor` 重砌（除數 = 場內 SD）
  candidate = 上線版（儲存 feature，`exact_score` 重算）
兩邊都經 `exact_score` 由 feature 重算，所以只差 F1 一樣嘢。

只計 START_DATE 起、而且 detail 有 `sd_floor` 欄（即係新 code 評分）嘅場次；之前場次 baseline = candidate，
只做 log-loss 尺校準。夠 TARGET_RACES 場用 `au_logloss_ruler.evaluate`（v2，登記時嘅尺）判一次並凍結：
上線版明顯差（Δlog-loss CI 下界 > 0）或者 AUC 護欄唔過 → `rollback_recommended`（建議 `WC_AU_FQ_SD_FLOOR_LIVE=0`，
要 Kelvin 決定）。未夠數只報數量（盲測）。永遠唔會自動改模型。

    python3 au_fq_floor_forward.py --output STATUS.json
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

EXPERIMENT_ID = "EXP-20261124-20"
SOURCE_EXPERIMENT = "EXP-20261123-06"
CALIBRATION_SINCE = "2026-08-05"
START_DATE = "2026-11-25"   # 上線後第一個新分析賽日（11-24 22:00 嗰程分析 11-25）
TARGET_RACES = 1000


def race_rows(logic, result_rows, forward):
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine import stability
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
               "old_horse": float(auto.get("old_horse_feature") or 0.0),
               "trainer_residual": float(auto.get("trainer_residual_feature") or 0.0),
               "people_prize": float(auto.get("people_prize_feature") or 0.0),
               "speed": float(auto.get("winning_time_speed_feature") or 0.0),   # EXP-20261124-40
               "features": dict(features)}
        row["ability"] = exact_score(row, MATRIX_WEIGHTS)
        if forward:
            detail = ((auto.get("stability_detail") or {}).get("form_quality")) or {}
            base_features = {**features, "form_quality_score": stability.score_without_floor(features, detail)}
            row["ability_no_floor"] = exact_score({**row, "features": base_features}, MATRIX_WEIGHTS)
        else:
            row["ability_no_floor"] = row["ability"]
        rows.append(row)
    return rows


def _new_code(logic) -> bool:
    for h in (logic.get("horses") or {}).values():
        fq = (((h or {}).get("python_auto") or {}).get("stability_detail") or {}).get("form_quality") or {}
        if "sd_floor" in fq:
            return True
    return False


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
            forward = date >= START_DATE
            if forward and not _new_code(logic):
                continue   # 舊 code 評分（冇 sd_floor 記錄）唔計，免得靜靜稀釋 forward
            got = race_rows(logic, rows, forward)
            if sum(r["pos"] <= 3 for r in got) >= 3 and any(r["pos"] == 1 for r in got):
                races.append({"meeting": meeting_dir.name, "date": date, "race": race_no, "rows": got})
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def baseline(races):
    return [dict(r, rows=[dict(x, ability=x["ability_no_floor"]) for x in r["rows"]]) for r in races]


def evaluate(races):
    """START_DATE 之前嘅場次只做 walk-forward 校準、唔計分 —— 佢哋 baseline = candidate（Δ = 0），
    計入就會稀釋 Δ 同令 AUC／Gold／Good 護欄更易過，即係更難建議回退（Sol 覆核 2026-11-24）。"""
    import au_logloss_ruler as L
    keep = ("verdict", "reason", "checks", "dlogloss", "beats_null_share", "gold_pp", "good_pp", "capture5_pp", "top2_any_hit_pp")
    full = L.calibrations

    def forward_only(rs, version="v1"):
        return {d: v for d, v in full(rs, version).items() if d >= START_DATE}

    L.calibrations = forward_only
    try:
        v = L.evaluate(L.eligible(baseline(races)), L.eligible(races), nnull=200, version="v2")   # 登記時嘅尺
    finally:
        L.calibrations = full
    worse = v["dlogloss"][1] > 0 or not v["checks"]["auc_guardrail"]
    return {"F1": {**{k: v.get(k) for k in keep}, "mode": "rollback", "rollback_recommended": bool(worse)}}


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
    moved = sum(1 for r in forward for x in r["rows"] if abs(x["ability"] - x["ability_no_floor"]) >= 0.005)
    status = {"experiment": EXPERIMENT_ID, "source": SOURCE_EXPERIMENT, "start_date": START_DATE,
              "target_races": TARGET_RACES, "races_collected": len(forward),
              "race_days": len({r["date"] for r in forward}),
              "arms": {"F1": {"mode": "rollback", "switch": "WC_AU_FQ_SD_FLOOR_LIVE", "sd_floor": 0.3065}},
              "interim": {"horses_moved": moved, "note": "盲測：未夠數只報數量"},
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
