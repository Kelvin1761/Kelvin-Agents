#!/usr/bin/env python3
"""Forward 監察：英愛法往績馬嘅近績質素分改由官方讓磅分推算（EXP-20261102-12，USER-ACCEPTED，`overseas.py`）。

只計有馬用咗代理分（`score_provenance.form_quality_score == form_quality_overseas_rating_proxy`）嘅已完賽賽事：

    live           = 儲存特徵 + overlay，`exact_score` 重算
    counterfactual = 同一樣，但代理馬嘅近績質素分換返冇代理時嘅值（由 `stability_detail.form_quality`
                     入面賽前已記低嘅 raw／場內均值／SD 重算，連增程縮程 −5）

一年只有幾十匹英愛法往績馬，所以每晚寫 `interim`（代理馬平均名次差距 + Gold／Good 場數，只係描述）；
夠 TARGET_RACES 場用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結，夠數由 forward tracker 推 Telegram。
上線版輸 → 建議回退（`WC_AU_OVERSEAS_RATING_PROXY=0`）。永遠唔會自動改模型。

    python3 au_overseas_proxy_forward.py --output STATUS.json
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

from au_racing_engine.engine_core import FORM_QUALITY_TRIP_CHANGE_PEN  # noqa: E402
from au_racing_engine.scoring import clip_score  # noqa: E402

EXPERIMENT_ID = "EXP-20261102-12"
START_DATE = "2026-11-02"      # 98ed99c5 上線日；之前嘅 Logic 冇 stability_detail.form_quality，重算唔到
TARGET_RACES = 100
PROXY_SOURCE = "form_quality_overseas_rating_proxy"


def without_proxy_score(features: dict, detail: dict) -> float:
    """冇代理時嘅近績質素分，同 `engine_core._merged_form_quality` + `_trip_change_adjustment` 一樣。"""
    raw, mean = detail.get("raw"), detail.get("field_mean")
    stdev = detail.get("field_stdev") or 0.0
    if raw is None or int(detail.get("run_count") or 0) < 2 or int(detail.get("field_count") or 0) < 3 \
            or mean is None or stdev <= 0:
        form = clip_score(features.get("form_score", 60))
        quality = clip_score(features.get("performance_quality_score", 60))
        score = clip_score(60.0 + 0.6 * (form - 60.0) + 0.4 * (quality - 60.0))
    else:
        score = clip_score(60.0 + 20.0 * (raw - mean) / stdev)
    if detail.get("trip_change"):
        score = clip_score(score + FORM_QUALITY_TRIP_CHANGE_PEN)
    return round(score, 6)


def race_rows(logic, result_rows):
    """→ (rows_live, rows_without_proxy, proxied_count)；只計對到賽果嘅馬。"""
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    live, base, proxied = [], [], 0
    for number, horse in (logic.get("horses") or {}).items():
        auto = (horse or {}).get("python_auto") or {}
        features = auto.get("feature_scores") or {}
        result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
        if not features or result is None:
            continue
        row = {"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
               "sp": result.get("sp"), "wet": auto.get("wet_form_feature") or 0.0,
               "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0,
               "draw": float(auto.get("draw_feature") or 0.0)}
        base_features = dict(features)
        is_proxy = (auto.get("score_provenance") or {}).get("form_quality_score") == PROXY_SOURCE
        if is_proxy:
            detail = (auto.get("stability_detail") or {}).get("form_quality") or {}
            base_features["form_quality_score"] = without_proxy_score(features, detail)
            proxied += 1
        live_row = {**row, "features": dict(features), "proxy": is_proxy}
        base_row = {**row, "features": base_features, "proxy": is_proxy}
        live_row["ability"] = exact_score(live_row, MATRIX_WEIGHTS)
        base_row["ability"] = exact_score(base_row, MATRIX_WEIGHTS)
        live.append(live_row)
        base.append(base_row)
    return live, base, proxied


def collect(root, start=START_DATE):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    live_races, base_races, skipped = [], [], {"no_proxy_horse": 0, "incomplete_result": 0}
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
            live, base, proxied = race_rows(logic, rows)
            if not proxied:
                skipped["no_proxy_horse"] += 1
                continue
            if sum(r["pos"] <= 3 for r in live) < 3 or not any(r["pos"] == 1 for r in live):
                skipped["incomplete_result"] += 1
                continue
            meta = {"meeting": meeting_dir.name, "date": date, "race": race_no}
            live_races.append({**meta, "rows": live})
            base_races.append({**meta, "rows": base})
    order = sorted(range(len(live_races)), key=lambda i: (live_races[i]["date"], live_races[i]["meeting"],
                                                          live_races[i]["race"]))
    return [live_races[i] for i in order], [base_races[i] for i in order], skipped


def proxy_rank_error(races):
    """代理馬嘅 |模型名次 − 實際名次| 平均。"""
    errors = []
    for race in races:
        ranked = sorted(race["rows"], key=lambda r: (-r["ability"], r["n"]))
        errors += [abs(i + 1 - r["pos"]) for i, r in enumerate(ranked) if r["proxy"]]
    return (round(sum(errors) / len(errors), 3) if errors else None), len(errors)


def interim(live_races, base_races):
    """未夠數嘅累計描述：唔係判決，冇 CI。"""
    from au_eval import _counts

    score = lambda race: race["ability"]  # noqa: E731
    live, base = _counts(live_races, score), _counts(base_races, score)
    keys = ("gold", "good_positional", "pass")
    live_err, horses = proxy_rank_error(live_races)
    base_err, _ = proxy_rank_error(base_races)
    return {"races": len(live_races), "proxy_horses": horses,
            "with_proxy": {**{k: round(live[k], 2) for k in keys}, "proxy_rank_error": live_err},
            "without_proxy": {**{k: round(base[k], 2) for k in keys}, "proxy_rank_error": base_err},
            "note": "累計描述，唔係判決；夠數先用 v3 判"}


def evaluate(base_races, live_races):
    """candidate = 上線版（有代理），baseline = 冇代理。"""
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
            "proxy_rank_error": {"with_proxy": proxy_rank_error(live_races)[0],
                                 "without_proxy": proxy_rank_error(base_races)[0]},
            "counts_with_proxy": _counts(live_races, score), "counts_without_proxy": _counts(base_races, score)}


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
