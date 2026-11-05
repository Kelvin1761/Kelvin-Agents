#!/usr/bin/env python3
"""Forward 監察：初出馬「冇證據」穩定性分 52.4 → 60（EXP-20261105-09 D1，USER-ACCEPTED 上線，`scoring.DEBUT_NO_EVIDENCE`）。

只影響行「初出 → 表現質素 consistency_fallback → 近績質素後備組合」嘅馬：近績質素 = 0.6 × 近績分 + 0.4 × 穩定性分。
只計上線之後（START_DATE 起）、有最少一匹呢類馬、已完賽嘅賽事：

    live（candidate）       = 儲存特徵 + overlay，`exact_score` 重算（D1：穩定性分 60）
    counterfactual（baseline）= 同一樣，但呢類馬嘅近績質素用舊值 52.4 重砌（`stability.composite`，連增程縮程 −5）

每晚寫 `interim`（描述，唔係判決）；夠 TARGET_RACES 場用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結，
夠數由 forward tracker 推 Telegram。上線版輸（primary_regression／ranking_metric_harm）→ 建議回退
`WC_AU_DEBUT_NEUTRAL=0`。永遠唔會自動改模型。

    python3 au_debut_neutral_forward.py --output STATUS.json
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

from au_racing_engine.scoring import DEBUT_NO_EVIDENCE_LEGACY  # noqa: E402
from au_racing_engine.stability import TRIP_CHANGE_PEN, composite  # noqa: E402
from au_racing_engine.scoring import clip_score  # noqa: E402

EXPERIMENT_ID = "EXP-20261105-09"
START_DATE = "2026-11-06"      # D1 喺 2026-11-05 晚上線；之前嘅分析係 52.4
TARGET_RACES = 700             # ≈ v3 判決改咗嘅場數（706）
TOLERANCE = 0.05
PATH = {"consistency_score": "career_tag", "performance_quality_score": "consistency_fallback",
        "form_quality_score": "form_quality_fallback_composite"}


def affected(auto: dict) -> bool:
    """呢匹馬嘅近績質素係咪由初出穩定性分經後備組合嚟。"""
    prov = auto.get("score_provenance") or {}
    return all(prov.get(k) == v for k, v in PATH.items())


def legacy_form_quality(auto: dict) -> tuple[float | None, str]:
    """→ (舊 52.4 下嘅近績質素, 問題)。live 重砌對唔上就回問題。"""
    features = auto.get("feature_scores") or {}
    detail = (auto.get("stability_detail") or {}).get("form_quality") or {}
    trip = TRIP_CHANGE_PEN if detail.get("trip_change") else 0.0
    form = features.get("form_score", 60.0)
    live = float(features.get("form_quality_score", 60.0))
    rebuilt = clip_score(composite(form, features.get("performance_quality_score", 60.0)) + trip)
    if abs(rebuilt - live) > TOLERANCE:
        return None, "live_rebuild_mismatch"
    return clip_score(composite(form, DEBUT_NO_EVIDENCE_LEGACY) + trip), ""


def race_rows(logic, result_rows):
    """→ (rows_live, rows_legacy, 受影響馬數, 問題)；只計對到賽果嘅馬。"""
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    live, base, hit = [], [], 0
    for number, horse in (logic.get("horses") or {}).items():
        auto = (horse or {}).get("python_auto") or {}
        features = auto.get("feature_scores") or {}
        if not features:
            continue
        base_features = dict(features)
        is_debut = affected(auto)
        if is_debut:
            legacy, problem = legacy_form_quality(auto)
            if problem:
                return [], [], 0, problem
            base_features["form_quality_score"] = legacy
            hit += 1
        result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
        if result is None:
            continue
        row = {"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
               "sp": result.get("sp"), "wet": auto.get("wet_form_feature") or 0.0,
               "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0,
               "draw": float(auto.get("draw_feature") or 0.0), "debut": is_debut}
        live_row = {**row, "features": dict(features)}
        base_row = {**row, "features": base_features}
        live_row["ability"] = exact_score(live_row, MATRIX_WEIGHTS)
        base_row["ability"] = exact_score(base_row, MATRIX_WEIGHTS)
        live.append(live_row)
        base.append(base_row)
    return live, base, hit, ""


def collect(root, start=START_DATE):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    live_races, base_races = [], []
    skipped = {"no_debut_horse": 0, "incomplete_result": 0}
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
            live, base, hit, problem = race_rows(logic, rows)
            if problem:
                skipped[problem] = skipped.get(problem, 0) + 1
                continue
            if not hit:
                skipped["no_debut_horse"] += 1
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


def debut_top3(races) -> tuple[int, int]:
    """模型頭三入面初出馬數、佢哋入三數。"""
    picks = [r for race in races for r in sorted(race["rows"], key=lambda r: (-r["ability"], r["n"]))[:3]]
    debut = [r for r in picks if r["debut"]]
    return len(debut), sum(r["pos"] <= 3 for r in debut)


def interim(live_races, base_races):
    """未夠數嘅累計描述：唔係判決，冇 CI。"""
    from au_eval import _counts

    score = lambda race: race["ability"]  # noqa: E731
    live, base = _counts(live_races, score), _counts(base_races, score)
    keys = ("gold", "good_positional", "pass")
    moved = sum(abs(a["ability"] - b["ability"]) > 1e-6 for ra, rb in zip(live_races, base_races)
                for a, b in zip(ra["rows"], rb["rows"]))
    return {"races": len(live_races), "horses_ability_moved": moved,
            "live_d1": {**{k: round(live[k], 2) for k in keys}, "debut_top3_picks_placed": debut_top3(live_races)},
            "legacy_52_4": {**{k: round(base[k], 2) for k in keys}, "debut_top3_picks_placed": debut_top3(base_races)},
            "note": "累計描述，唔係判決；夠數先用 v3 判"}


def evaluate(base_races, live_races):
    """candidate = 上線版（D1），baseline = 舊 52.4。"""
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
            "debut_top3_picks_placed": {"live_d1": debut_top3(live_races), "legacy_52_4": debut_top3(base_races)},
            "counts_live_d1": _counts(live_races, score), "counts_legacy": _counts(base_races, score)}


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
        print(f"{EXPERIMENT_ID} forward 已判（凍結）：keep={previous['evaluation']['keep']}")
        return
    live, base, skipped = collect(Path(args.data_root) if args.data_root else ARCHIVE_ROOT, start=args.start)
    status = {"experiment": EXPERIMENT_ID, "start_date": args.start, "target_races": TARGET_RACES,
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
