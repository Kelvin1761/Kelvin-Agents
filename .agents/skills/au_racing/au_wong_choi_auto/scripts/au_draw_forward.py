#!/usr/bin/env python3
"""Forward 監察：大場次檔位分（EXP-20261102-08，USER-ACCEPTED EXPERIMENTAL LIVE，`draw.py`）。

每場已完賽、由有檔位分嘅引擎評分（Logic 有 `draw_feature`）嘅 ≥8 匹賽事：

    live           = 儲存特徵 + overlay（連 `draw_feature`），`exact_score` 重算
    counterfactual = 同一樣，但檔位分 = 0（即係上線前）

Kelvin 要「keep monitoring if we can already see signal」：未夠數之前每晚寫 `interim`（累計 Gold／Good／前三
場數，只係描述，唔係判決）；夠 TARGET_RACES 場用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結。
上線版輸（primary_regression／ranking_metric_harm）→ 建議回退（`WC_AU_DRAW_LIVE=0`）。永遠唔會自動改模型。

    python3 au_draw_forward.py --output STATUS.json
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

from au_racing_engine.draw import BETA, MIN_FIELD  # noqa: E402

EXPERIMENT_ID = "EXP-20261102-08"
START_DATE = "2026-11-02"      # EXP-20261102-07 語料最後一日係 11-01；之前嘅場次冇 draw_feature，會被跳過
TARGET_RACES = 1000


def race_rows(logic, result_rows):
    """→ (rows_live, rows_without_draw, shipped)；只計對到賽果嘅馬。"""
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    live, base, shipped = [], [], True
    for number, horse in (logic.get("horses") or {}).items():
        auto = (horse or {}).get("python_auto") or {}
        features = auto.get("feature_scores") or {}
        result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
        if not features or result is None:
            continue
        row = {"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
               "sp": result.get("sp"), "features": dict(features), "wet": auto.get("wet_form_feature") or 0.0,
               "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0}
        if "draw_feature" not in auto:
            shipped = False
        live_row = {**row, "draw": float(auto.get("draw_feature") or 0.0)}
        base_row = {**row, "draw": 0.0}
        live_row["ability"] = exact_score(live_row, MATRIX_WEIGHTS)
        base_row["ability"] = exact_score(base_row, MATRIX_WEIGHTS)
        live.append(live_row)
        base.append(base_row)
    return live, base, shipped


def collect(root, start=START_DATE):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    live_races, base_races, skipped = [], [], {"small_field": 0, "incomplete_result": 0, "old_engine": 0}
    for meeting_dir in meeting_dirs(root):
        date = detect_meeting_date(meeting_dir)
        if not date or date < start:
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
            live, base, shipped = race_rows(logic, rows)
            if sum(r["pos"] <= 3 for r in live) < 3 or not any(r["pos"] == 1 for r in live):
                skipped["incomplete_result"] += 1
                continue
            if not shipped:
                skipped["old_engine"] += 1
                continue
            if len(live) < MIN_FIELD:
                skipped["small_field"] += 1
                continue
            meta = {"meeting": meeting_dir.name, "date": date, "race": race_no}
            live_races.append({**meta, "rows": live})
            base_races.append({**meta, "rows": base})
    order = sorted(range(len(live_races)), key=lambda i: (live_races[i]["date"], live_races[i]["meeting"],
                                                          live_races[i]["race"]))
    return [live_races[i] for i in order], [base_races[i] for i in order], skipped


def interim(live_races, base_races):
    """未夠數嘅累計描述（Kelvin 要求）：唔係判決，冇 CI。"""
    from au_eval import _counts

    score = lambda race: race["ability"]  # noqa: E731
    live, base = _counts(live_races, score), _counts(base_races, score)
    keys = ("gold", "good_positional", "pass")
    return {"races": len(live_races), "with_draw": {k: round(live[k], 2) for k in keys},
            "without_draw": {k: round(base[k], 2) for k in keys},
            "note": "累計描述，唔係判決；夠數先用 v3 判"}


def evaluate(base_races, live_races):
    """candidate = 上線版（有檔位分），baseline = 冇檔位分。"""
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record

    score = lambda race: race["ability"]  # noqa: E731
    verdict = evaluate_full_record(
        domain="au", mode="fixed_rule", dates=[r["date"] for r in base_races],
        baseline_rows=_stage4_metric_rows(base_races, score),
        candidate_rows=_stage4_metric_rows(live_races, score),
        leakage_audit_passed=True,
        ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    detail = verdict["detail"]
    pick = lambda group: {k: {f: e[f] for f in ("delta", "ci_low", "ci_high", "p_value")}  # noqa: E731
                          for k, e in detail[group].items()}
    return {"keep": verdict["reason"] not in ("primary_regression", "ranking_metric_harm"),
            "win": verdict["verdict"] in ("PRIMARY_WIN", "RANKING_WIN"), "verdict": verdict["verdict"],
            "reason": verdict["reason"], "primary": pick("primary"), "ranking": pick("ranking"),
            "counts_with_draw": _counts(live_races, score), "counts_without_draw": _counts(base_races, score)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    from au_archive_calibrator import ARCHIVE_ROOT

    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} forward 已判（凍結）：keep={previous['evaluation']['keep']}")
        return
    live, base, skipped = collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT)
    status = {"experiment": EXPERIMENT_ID, "start_date": START_DATE, "target_races": TARGET_RACES,
              "beta": BETA, "min_field": MIN_FIELD,
              "races_collected": len(live), "race_days": len({r["date"] for r in live}),
              "skipped": skipped, "outcomes_visible": len(live) >= TARGET_RACES,
              "state": "evaluated" if len(live) >= TARGET_RACES else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if status["outcomes_visible"]:
        status["evaluation"] = evaluate(base[:TARGET_RACES], live[:TARGET_RACES])
    elif live:
        status["interim"] = interim(live, base)
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))
    if status.get("evaluation"):
        print("evaluation:", status["evaluation"]["verdict"], status["evaluation"]["reason"])


if __name__ == "__main__":
    main()
