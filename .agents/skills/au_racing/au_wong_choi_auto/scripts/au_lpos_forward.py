#!/usr/bin/env python3
"""Forward 測試：末段扣位置（Lpos）—— EXP-20261116-20（預先登記，規格凍結，只追蹤，唔郁發佈排名）。

    baseline  = live 排名分（Logic 儲存特徵 → `exact_score`，同其他 AU forward 一樣）
    candidate = baseline + 0.10 × 場內 pstdev(baseline) × 場內 z(Lpos.avg4)，冇值 = 0

    本駒 L600 = 手機分段 400m＋200m＋Fnsh（由 km/h 反推）；Lr = −(本駒 L600 − Formguide RaceL600)
    p800 = (800m 位置 − 1)/(馬數 − 1)；Lpos = Lr − (A + B × p800)，A／B 係 EXP-22 凍結常數
    Lpos.avg4 = 最近 ≤4 仗有值嘅平均（只用日期 < 今仗）

未夠 TARGET_RACES 只寫場數同覆蓋率（**唔睇賽果指標**）；夠數用 v3 `evaluate_full_record`（fixed_rule）判一次並凍結，
由 forward tracker 推 Telegram。永遠唔會自動改模型。

    python3 au_lpos_forward.py --output STATUS.json [--data-root DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing"))
sys.path.insert(0, str(SCRIPT_DIR.parents[2] / "shared_racing" / "scripts"))

import au_mobile_sectionals as ams  # noqa: E402

EXPERIMENT_ID = "EXP-20261116-20"
START_DATE = ams.FORWARD_START
TARGET_RACES = 2500
WEIGHT = 0.10
LPOS_A, LPOS_B = -1.1008497873571432, -0.10976351609298357   # EXP-22（11-06 前 22,071 行）凍結
LAST_N = 4
SPRINT_MAX = 1200

_HDR = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)


def _norm(name: str) -> str:
    from au_archive_calibrator import normalize_horse_name
    return normalize_horse_name(name or "")


def venue_key(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def formguide_runs(text: str) -> dict:
    """→ {馬名(normalised): {日期: {race_l600, pos800, starters}}}；試閘唔要。"""
    heads = list(_HDR.finditer(text or ""))
    out = {}
    for i, h in enumerate(heads):
        body = text[h.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        runs = {}
        for line in body.splitlines():
            d = re.search(r"\bR\d+\s+(\d{4}-\d{2}-\d{2})\s+\d{3,4}m\s+cond:", line)
            if not d or "(TRIAL)" in line:
                continue
            rl = re.search(r"RaceL600:([\d.]+)", line)
            p8 = re.search(r"(\d+)(?:st|nd|rd|th)@800m", line)
            st = re.search(r"starters:(\d+)", line)
            runs[d.group(1)] = {"race_l600": float(rl.group(1)) if rl else None,
                                "pos800": int(p8.group(1)) if p8 else None,
                                "starters": int(st.group(1)) if st else None}
        out[_norm(h.group(2))] = runs
    return out


def run_lpos(mob_run: dict, fg_run: dict | None) -> float | None:
    if not fg_run or fg_run.get("race_l600") is None:
        return None
    own = ams.own_l600(mob_run)
    if own is None or not fg_run.get("pos800") or not fg_run.get("starters") or fg_run["starters"] < 2:
        return None
    p800 = (fg_run["pos800"] - 1) / (fg_run["starters"] - 1)
    return -(own - fg_run["race_l600"]) - (LPOS_A + LPOS_B * p800)


def lpos_avg4(mob_runs: list[dict], fg: dict, race_day: str) -> float | None:
    vals = []
    for run in sorted((r for r in mob_runs if r.get("date") and r["date"] < race_day),
                      key=lambda r: r["date"], reverse=True):
        v = run_lpos(run, fg.get(run["date"]))
        if v is not None:
            vals.append(v)
        if len(vals) == LAST_N:
            break
    return statistics.mean(vals) if vals else None


def zscores(vals: list) -> list[float]:
    have = [v for v in vals if v is not None]
    if len(have) < 2 or statistics.pstdev(have) == 0:
        return [0.0] * len(vals)
    m, s = statistics.mean(have), statistics.pstdev(have)
    return [0.0 if v is None else (v - m) / s for v in vals]


def candidate_scores(bases: list[float], feats: list) -> list[float]:
    sd = statistics.pstdev(bases) if len(bases) >= 2 else 0.0
    return [b + WEIGHT * sd * z for b, z in zip(bases, zscores(feats))]


def race_rows(logic: dict, result_rows: list, mobile: dict, fg: dict, race_day: str):
    """→ rows（只計對到賽果嘅馬）：{n, pos, base, lpos}。"""
    from au_archive_calibrator import get_true_horse_name
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score

    lookup = {_norm(r["horse_slug"]): r for r in result_rows}
    by_name = {_norm(r.get("name")): r.get("runs") or [] for r in mobile.get("runners") or []}
    rows = []
    for number, horse in (logic.get("horses") or {}).items():
        auto = (horse or {}).get("python_auto") or {}
        features = auto.get("feature_scores") or {}
        if not features:
            continue
        name = _norm(get_true_horse_name(horse))
        result = lookup.get(name)
        if result is None:
            continue
        row = {"features": features, "wet": auto.get("wet_form_feature") or 0.0,
               "proven_class": auto.get("proven_class_feature") or 0.0,
               "full_time": auto.get("full_time_speed_feature") or 0.0,
               "draw": float(auto.get("draw_feature") or 0.0)}
        mob_runs = by_name.get(name)
        rows.append({"n": int(number) if str(number).isdigit() else 999, "pos": int(result["pos"]),
                     "base": exact_score(row, MATRIX_WEIGHTS),
                     "lpos": lpos_avg4(mob_runs, fg.get(name, {}), race_day) if mob_runs else None})
    return rows


def collect(root: Path, start: str = START_DATE, mobile_root: Path | None = None):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_date,
                                       detect_meeting_track, load_historical_results)
    from corpus_paths import meeting_dirs

    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    races, skipped = [], {"no_mobile_page": 0, "no_formguide": 0, "incomplete_result": 0}
    mobile_cache: dict = {}
    for meeting_dir in meeting_dirs(root):
        day = detect_meeting_date(meeting_dir)
        if not day or day < start:
            continue
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"))
        if not logic_files:
            continue
        track = detect_meeting_track(meeting_dir, json.loads(logic_files[0].read_text(encoding="utf-8")))
        if day not in mobile_cache:
            mobile_cache[day] = {(venue_key(r["venue"]), int(r["race"])): r for r in ams.load_day(day, mobile_root)}
        for path in logic_files:
            logic = json.loads(path.read_text(encoding="utf-8"))
            race_no = int(str((logic.get("race_analysis") or {}).get("race_number") or path.stem.split("_")[1]))
            folder_venue = re.sub(r"\s+Race\s+\d+-\d+$", "", re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", meeting_dir.name))
            mobile = (mobile_cache[day].get((venue_key(track), race_no))
                      or mobile_cache[day].get((venue_key(folder_venue), race_no)))
            if mobile is None:
                skipped["no_mobile_page"] += 1
                continue
            fg_files = list(meeting_dir.glob(f"* Race {race_no} Formguide.md"))
            if not fg_files:
                skipped["no_formguide"] += 1
                continue
            res = choose_track_rows(results.get((day, race_no), []), track)
            rows = race_rows(logic, res, mobile, formguide_runs(fg_files[0].read_text(encoding="utf-8")), day) if res else []
            if sum(r["pos"] <= 3 for r in rows) < 3 or not any(r["pos"] == 1 for r in rows):
                skipped["incomplete_result"] += 1
                continue
            cand = candidate_scores([r["base"] for r in rows], [r["lpos"] for r in rows])
            for r, c in zip(rows, cand):
                r["cand"] = c
            dist = (logic.get("race_analysis") or {}).get("distance")
            post = sum(1 for r in mobile.get("runners") or [] for run in r.get("runs") or []
                       if run.get("date") and run["date"] >= day)   # 描述用（EXP-20261120-87 會剔走 > 0 嘅場）
            races.append({"date": day, "meeting": meeting_dir.name, "race": race_no, "rows": rows,
                          "distance": dist, "mobile_post_race_rows": post})
    races.sort(key=lambda r: (r["date"], r["meeting"], r["race"]))
    return races, skipped


def order(race, key):
    return [r["n"] for r in sorted(race["rows"], key=lambda r: (-r[key], r["n"]))]


def coverage(races) -> dict:
    horses = sum(len(r["rows"]) for r in races)
    with_lpos = sum(1 for r in races for x in r["rows"] if x["lpos"] is not None)
    moved = sum(1 for r in races if order(r, "base")[:3] != order(r, "cand")[:3])
    return {"horses": horses, "horses_with_lpos": with_lpos,
            "lpos_share": round(with_lpos / horses, 4) if horses else None, "races_top3_order_changed": moved}


def evaluate(races):
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record

    base = lambda race: race["base"]  # noqa: E731
    cand = lambda race: race["cand"]  # noqa: E731
    verdict = evaluate_full_record(
        domain="au", mode="fixed_rule", dates=[r["date"] for r in races],
        baseline_rows=_stage4_metric_rows(races, base), candidate_rows=_stage4_metric_rows(races, cand),
        leakage_audit_passed=True, ranking_metrics=("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc"))
    detail = verdict["detail"]
    pick = lambda group: {k: {f: e[f] for f in ("delta", "ci_low", "ci_high", "p_value")}  # noqa: E731
                          for k, e in detail[group].items()}

    def split(sel):
        sub = [r for r in races if sel(r)]
        return {"races": len(sub), "baseline": _counts(sub, base), "candidate": _counts(sub, cand)}

    def dist(r):
        try:
            return int(str(r.get("distance") or "").rstrip("m"))
        except ValueError:
            return None

    return {"win": verdict["verdict"] in ("PRIMARY_WIN", "RANKING_WIN"), "verdict": verdict["verdict"],
            "reason": verdict["reason"], "primary": pick("primary"), "ranking": pick("ranking"),
            "sprint_le_1200": split(lambda r: (dist(r) or 0) and dist(r) <= SPRINT_MAX),
            "over_1200": split(lambda r: (dist(r) or 0) > SPRINT_MAX)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", default=None)
    ap.add_argument("--start", default=START_DATE, help="只供自檢；正式 forward 一律用 START_DATE")
    ap.add_argument("--mobile-root", default=None, help="只供自檢；預設 = 資料根")
    ap.add_argument("--output", required=True)
    args = ap.parse_args(argv)
    from au_archive_calibrator import ARCHIVE_ROOT

    out_path = Path(args.output)
    previous = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    if previous.get("evaluation"):
        print(f"{EXPERIMENT_ID} forward 已判（凍結）：{previous['evaluation']['verdict']}")
        return 0
    root = Path(args.data_root) if args.data_root else ARCHIVE_ROOT
    races, skipped = collect(root, start=args.start, mobile_root=Path(args.mobile_root) if args.mobile_root else root)
    ready = len(races) >= TARGET_RACES
    status = {"experiment": EXPERIMENT_ID, "start_date": args.start, "target_races": TARGET_RACES,
              "weight": WEIGHT, "races_collected": len(races), "race_days": len({r["date"] for r in races}),
              "skipped": skipped, "coverage": coverage(races), "outcomes_visible": ready,
              "state": "evaluated" if ready else "collecting",
              "generated_at": datetime.now(timezone.utc).isoformat()}
    if ready:
        status["evaluation"] = evaluate(races[:TARGET_RACES])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(status, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in status.items() if k != "evaluation"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
