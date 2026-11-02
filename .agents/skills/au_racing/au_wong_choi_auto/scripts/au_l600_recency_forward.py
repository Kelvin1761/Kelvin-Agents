#!/usr/bin/env python3
"""Forward 監察：L600 環境分近期加權（EXP-20261101-30 R，用戶 2026-11-01 決定上線）。

上線之後嘅每場已完賽賽事，用**已儲存**嘅 live Logic（`python_auto` 特徵、overlay、
`_data.pf_metrics` 往績）重算：

  live           = 上線版（近期加權 0.8^k），必須同儲存嘅 `pace_figure_score` 一致
  counterfactual = 舊版（每仗一樣重），其餘特徵、overlay 原封不動

儲存分數同近期加權重算對唔上嘅場次（即係舊引擎評分）唔計，另外報數。
夠 TARGET_RACES 場完整賽果之前**只報場數**，唔出任何結果指標（預先登記：唔准提早判）。
夠數之後用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結：Gold、Good 點估計
都唔負 = 保留；否則提請 Kelvin 還原。永遠唔會自動改模型。

    python3 au_l600_recency_forward.py --output STATUS.json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

EXPERIMENT_ID = "EXP-20261101-30"
START_DATE = "2026-11-02"      # 第一個用上線版引擎分析嘅賽日
TARGET_RACES = 600
SEC_PER_LENGTH = 0.17
DECAY = 0.8


def _num(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def horse_values(runs, decay):
    """→ (own_x, race_x)。同 engine `_pf_aggregates`：k 按 run_date 新到舊，捨入 3dp。"""
    ordered = sorted(runs, key=lambda run: str(run.get("run_date") or ""), reverse=True)
    own, race = [], []
    for k, run in enumerate(ordered):
        weight = decay ** k
        if run.get("l600_delta") is not None:
            race.append((weight, float(run["l600_delta"])))
        if run.get("own_l600_delta") is not None:
            own.append((weight, float(run["own_l600_delta"])))

    def agg(pairs):
        return round(sum(w * v for w, v in pairs) / sum(w for w, _ in pairs), 3) if pairs else None
    return agg(own), agg(race)


def pace_figure_field(horses, decay):
    """{horse_number: L600 環境分}，同 engine `_pace_figure_score` 同一條路（母體 = Logic 全部馬）。"""
    from au_racing_engine.engine_core import performance_pf_metrics
    from au_racing_engine.scoring import clip_score

    values = {str(n): horse_values(performance_pf_metrics(h).get("pf_runs") or [], decay)
              for n, h in horses.items() if isinstance(h, dict)}
    own_field = [o for o, _ in values.values() if o is not None]
    race_field = [r for _, r in values.values() if r is not None]

    def stats(field):
        mean = sum(field) / len(field) if field else 0.0
        sd = (sum((v - mean) ** 2 for v in field) / len(field)) ** 0.5 if len(field) > 1 else 0.0
        return mean, sd
    (own_mean, own_sd), (race_mean, race_sd) = stats(own_field), stats(race_field)
    out = {}
    for number, (own, race) in values.items():
        if own is not None and len(own_field) >= 3:
            value, mean, sd = own, own_mean, own_sd
        elif race is not None and len(race_field) >= 3:
            value, mean, sd = race, race_mean, race_sd
        else:
            out[number] = 60.0
            continue
        out[number] = 60.0 if sd <= 0 else clip_score(60 - (value - mean) / sd * 20.0)
    return out


def race_rows(logic, result_rows):
    """→ (rows_live, rows_counterfactual, shipped)；對唔到賽果嘅馬唔入 rows，但入場內母體。"""
    from au_archive_calibrator import get_true_horse_name, normalize_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    horses = logic.get("horses") or {}
    live_pf, base_pf = pace_figure_field(horses, DECAY), pace_figure_field(horses, 1.0)
    lookup = {normalize_horse_name(r["horse_slug"]): r for r in result_rows}
    live, base, shipped = [], [], True
    for number, horse in horses.items():
        auto = (horse or {}).get("python_auto") or {}
        features = dict(auto.get("feature_scores") or {})
        result = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
        if not features or result is None:
            continue
        stored = _num(features.get("pace_figure_score"))
        if stored is None or abs(stored - live_pf.get(str(number), 60.0)) > 1e-3:
            shipped = False
        row = {"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
               "sp": result.get("sp"), "wet": auto.get("wet_form_feature") or 0.0,
               "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0,
               "draw": auto.get("draw_feature") or 0.0}
        live_row = {**row, "features": {**features, "pace_figure_score": live_pf.get(str(number), 60.0)}}
        base_row = {**row, "features": {**features, "pace_figure_score": base_pf.get(str(number), 60.0)}}
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
    live_races, base_races, skipped = [], [], {"old_engine": 0, "incomplete_result": 0}
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
            meta = {"meeting": meeting_dir.name, "date": date, "race": race_no}
            live_races.append({**meta, "rows": live})
            base_races.append({**meta, "rows": base})
    order = sorted(range(len(live_races)), key=lambda i: (live_races[i]["date"], live_races[i]["meeting"],
                                                          live_races[i]["race"]))
    return [live_races[i] for i in order], [base_races[i] for i in order], skipped


def evaluate(live_races, base_races):
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record

    score = lambda race: race["ability"]  # noqa: E731
    verdict = evaluate_full_record(
        domain="au", mode="fixed_rule", dates=[r["date"] for r in live_races],
        baseline_rows=_stage4_metric_rows(base_races, score),
        candidate_rows=_stage4_metric_rows(live_races, score),
        leakage_audit_passed=True,
        ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    primary = verdict["detail"]["primary"]
    keep = all(primary[k]["delta"] >= 0 for k in ("gold", "good_positional"))
    return {"keep": keep, "verdict": verdict["verdict"], "reason": verdict["reason"],
            "primary": {k: {f: e[f] for f in ("delta", "ci_low", "ci_high", "p_value")} for k, e in primary.items()},
            "counts_live": _counts(live_races, score), "counts_counterfactual": _counts(base_races, score)}


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
        status["evaluation"] = evaluate(live[:TARGET_RACES], base[:TARGET_RACES])
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))
    if status.get("evaluation"):
        print("evaluation:", json.dumps(status["evaluation"]["primary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
