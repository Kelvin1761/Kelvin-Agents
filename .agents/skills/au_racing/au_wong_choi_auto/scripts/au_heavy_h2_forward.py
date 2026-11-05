#!/usr/bin/env python3
"""Forward 測試：今場大爛地，近績質素分用返 C2 之前嘅舊公式（EXP-20261105-06 H2，用戶 2026-11-05 揀 forward）。

背景：C2（EXP-20261105-05，跑得好先攞獎金分）喺大爛地 Good 變差。H2 = 今場場地家族係 Heavy 時，全場近績質素 raw
用舊公式（獎金分唔打折），場內均值／SD 亦由舊 raw 計；其他場地照 C2。v3 PRIMARY_WIN（大爛地 Good +2.59pp），
但 §8 得 70 場大爛地，功效唔夠 → 冇上線，改為 forward。

只計 C2 上線之後（START_DATE 起、往績紀錄有 `z_prize_raw`）、今場大爛地、已完賽嘅賽事：

    live（baseline）  = 儲存特徵 + overlay，`exact_score` 重算
    H2（candidate）   = 同一樣，但近績質素分由 `stability_detail.form_quality.runs` 用 `stability.legacy_raw`
                        重砌舊 raw，再用舊 raw 嘅場內均值／SD 計（連 fallback、增程縮程 −5；海外代理馬唔郁）

每晚寫 `interim`（描述，唔係判決）；夠 TARGET_RACES 場用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結，
夠數由 forward tracker 推 Telegram。永遠唔會自動改模型。

    python3 au_heavy_h2_forward.py --output STATUS.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

from au_racing_engine.stability import is_heavy_going, legacy_raw, score_without_proxy  # noqa: E402

EXPERIMENT_ID = "EXP-20261105-06"
START_DATE = "2026-11-06"      # C2 喺 2026-11-05 18:50 上線（f8c1271a）；之前嘅分析係舊公式
TARGET_RACES = 200             # ≈ 預先登記 v3 大爛地樣本（193 場）；冬季多、夏季少
PROXY_SOURCE = "form_quality_overseas_rating_proxy"
TOLERANCE = 0.05               # 重砌 live 分數同儲存值嘅容差（分）


def today_going(logic: dict) -> str:
    race = logic.get("race_analysis") or {}
    mi = race.get("meeting_intelligence") if isinstance(race.get("meeting_intelligence"), dict) else {}
    sm = race.get("speed_map") if isinstance(race.get("speed_map"), dict) else {}
    return str(mi.get("going") or sm.get("going") or sm.get("track_condition") or race.get("going") or "")


def h2_scores(horses: dict) -> tuple[dict, str]:
    """→ ({馬號: H2 近績質素分}, 問題)。問題非空 = 呢場唔用（重砌對唔上 live）。"""
    details, old = {}, {}
    for number, horse in horses.items():
        auto = (horse or {}).get("python_auto") or {}
        detail = (auto.get("stability_detail") or {}).get("form_quality")
        if not isinstance(detail, dict):
            continue
        details[number] = (auto, detail)
        if detail.get("raw") is not None:
            old[number] = legacy_raw(detail.get("runs"))
    if not details:
        # ⚠️ 2026-11-02 之前嘅 Logic 冇儲 stability_detail.form_quality —— 唔可以當「冇變」，否則靜靜拉向零。
        return {}, "no_stored_detail"
    live_raw = [float(d["raw"]) for _a, d in details.values() if d.get("raw") is not None]
    if not live_raw:
        return {}, ""          # 有 detail 但全場冇 raw（例如全部初出）：H2 同 live 一樣，照計入（同 v3 分層一致）
    if not any(r.get("z_prize_raw") is not None for _a, d in details.values() for r in d.get("runs") or []):
        return {}, "pre_c2_record"
    stored_mean = next((d.get("field_mean") for _a, d in details.values() if d.get("field_mean") is not None), None)
    if stored_mean is not None and abs(statistics.fmean(live_raw) - float(stored_mean)) > 1e-3:
        return {}, "field_mismatch"
    if any(v is None for v in old.values()):
        return {}, "legacy_raw_missing"
    values = list(old.values())
    mean = statistics.fmean(values) if values else None
    stdev = statistics.pstdev(values) if len(values) > 1 else 0.0
    out = {}
    for number, (auto, detail) in details.items():
        features = auto.get("feature_scores") or {}
        live = float(features.get("form_quality_score", 60.0))
        if (auto.get("score_provenance") or {}).get("form_quality_score") == PROXY_SOURCE:
            out[number] = live
            continue
        if abs(score_without_proxy(features, detail) - live) > TOLERANCE:
            return {}, "live_rebuild_mismatch"
        new = dict(detail, raw=old.get(number), field_mean=mean, field_stdev=stdev)
        out[number] = score_without_proxy(features, new)
    return out, ""


def race_rows(logic, result_rows):
    """→ (rows_live, rows_h2, 問題)；只計對到賽果嘅馬。"""
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    horses = logic.get("horses") or {}
    h2, problem = h2_scores(horses)
    if problem:
        return [], [], problem
    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    live, cand = [], []
    for number, horse in horses.items():
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
        cand_features = dict(features)
        if number in h2:
            cand_features["form_quality_score"] = h2[number]
        live_row = {**row, "features": dict(features)}
        cand_row = {**row, "features": cand_features}
        live_row["ability"] = exact_score(live_row, MATRIX_WEIGHTS)
        cand_row["ability"] = exact_score(cand_row, MATRIX_WEIGHTS)
        live.append(live_row)
        cand.append(cand_row)
    return live, cand, ""


def collect(root, start=START_DATE):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    live_races, cand_races = [], []
    skipped = {"not_heavy": 0, "incomplete_result": 0}
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
            if not is_heavy_going(today_going(logic)):
                skipped["not_heavy"] += 1
                continue
            race_no = int(str((logic.get("race_analysis") or {}).get("race_number") or path.stem.split("_")[1]))
            rows = choose_track_rows(results.get((date, race_no), []), track)
            if not rows:
                continue
            live, cand, problem = race_rows(logic, rows)
            if problem:
                skipped[problem] = skipped.get(problem, 0) + 1
                continue
            if sum(r["pos"] <= 3 for r in live) < 3 or not any(r["pos"] == 1 for r in live):
                skipped["incomplete_result"] += 1
                continue
            meta = {"meeting": meeting_dir.name, "date": date, "race": race_no}
            live_races.append({**meta, "rows": live})
            cand_races.append({**meta, "rows": cand})
    order = sorted(range(len(live_races)), key=lambda i: (live_races[i]["date"], live_races[i]["meeting"],
                                                          live_races[i]["race"]))
    return [live_races[i] for i in order], [cand_races[i] for i in order], skipped


def top2_changed(live_races, cand_races) -> int:
    pick = lambda race: {r["n"] for r in sorted(race["rows"], key=lambda r: (-r["ability"], r["n"]))[:2]}  # noqa: E731
    return sum(pick(a) != pick(b) for a, b in zip(live_races, cand_races))


def interim(live_races, cand_races):
    """未夠數嘅累計描述：唔係判決，冇 CI。"""
    from au_eval import _counts

    score = lambda race: race["ability"]  # noqa: E731
    live, cand = _counts(live_races, score), _counts(cand_races, score)
    keys = ("gold", "good_positional", "pass")
    moved = sum(abs(a["features"]["form_quality_score"] - b["features"]["form_quality_score"]) > 0.01
                for ra, rb in zip(live_races, cand_races) for a, b in zip(ra["rows"], rb["rows"]))
    return {"races": len(live_races), "top2_changed": top2_changed(live_races, cand_races),
            "horses_form_quality_moved": moved,
            "live_c2": {k: round(live[k], 2) for k in keys}, "h2": {k: round(cand[k], 2) for k in keys},
            "note": "累計描述，唔係判決；夠數先用 v3 判"}


def evaluate(live_races, cand_races):
    """baseline = live（C2），candidate = H2。"""
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record

    score = lambda race: race["ability"]  # noqa: E731
    verdict = evaluate_full_record(
        domain="au", mode="fixed_rule", dates=[r["date"] for r in live_races],
        baseline_rows=_stage4_metric_rows(live_races, score),
        candidate_rows=_stage4_metric_rows(cand_races, score),
        leakage_audit_passed=True,
        ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    detail = verdict["detail"]
    pick = lambda group: {k: {f: e[f] for f in ("delta", "ci_low", "ci_high", "p_value")}  # noqa: E731
                          for k, e in detail[group].items()}
    return {"adopt_h2": verdict["verdict"] in ("PRIMARY_WIN", "RANKING_WIN"), "verdict": verdict["verdict"],
            "reason": verdict["reason"], "primary": pick("primary"), "ranking": pick("ranking"),
            "top2_changed": top2_changed(live_races, cand_races),
            "counts_live_c2": _counts(live_races, score), "counts_h2": _counts(cand_races, score)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--start", default=START_DATE, help="只供自檢；正式 forward 一律用 START_DATE")
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    from au_archive_calibrator import ARCHIVE_ROOT

    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} forward 已判（凍結）：adopt_h2={previous['evaluation']['adopt_h2']}")
        return
    live, cand, skipped = collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT, start=args.start)
    status = {"experiment": EXPERIMENT_ID, "start_date": args.start, "target_races": TARGET_RACES,
              "races_collected": len(live), "race_days": len({r["date"] for r in live}),
              "skipped": skipped, "outcomes_visible": len(live) >= TARGET_RACES,
              "state": "evaluated" if len(live) >= TARGET_RACES else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if status["outcomes_visible"]:
        status["evaluation"] = evaluate(live[:TARGET_RACES], cand[:TARGET_RACES])
    elif live:
        status["interim"] = interim(live, cand)
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))
    if status.get("evaluation"):
        print("evaluation:", status["evaluation"]["verdict"], status["evaluation"]["reason"])


if __name__ == "__main__":
    main()
