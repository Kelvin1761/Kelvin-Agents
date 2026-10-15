#!/usr/bin/env python3
"""EXP-20261016-11：pg33_N6 forward shadow（凍結設計，一個 family 只開一次）。

pg33_N6（EXP-20261016-10）：近績質素分每場 = (z名次 + G) / 2，
G = z獎金（該場名次喺前三分一）否則 min(0, z獎金) —— 高班加分只俾跑得入前列嘅往績。
baseline = production eq2_N6（G 一律 = z獎金）。兩邊都用 live 權重（冇 refit）。

    freeze    寫凍結設定（code hash、規則），已存在就拒絕覆蓋。
    status    只數 forward 窗有幾多個有快照兼有賽果嘅賽日 —— **唔計任何指標**。
    evaluate  一次過：樣本未夠、code 唔夾、或者已經評過 → 拒絕。

輸入一律係賽前不可改快照（同 EXP-20261016-03：pick_snapshot pre_cutoff、簽名 + 逐檔 sha256）。
引擎用凍結 code 重評快照 Logic；pg33 嘅場內標準化同 production 一樣用全場報名馬。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for path in (SCRIPTS, SHARED, SHARED / "scripts", HERE):
    sys.path.insert(0, str(path))

EXP_DIR = REPO / "docs/experiments/EXP-20261016-11-forward"
FREEZE = EXP_DIR / "freeze.json"
RESULT = EXP_DIR / "forward_result.json"
VALID_FROM = "2026-10-17"
MIN_MEETING_DAYS = 41
RANKING_METRICS = ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")
FROZEN_SOURCES = (
    "scratch/au_pg33_forward_shadow_20261016.py",
    ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_walkforward_refit.py",
    ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_window_review.py",
    ".agents/skills/au_racing/au_wong_choi_auto/scripts/au_auto_orchestrator.py",
    ".agents/skills/shared_racing/model_evaluation_decision.py",
)
FROZEN_DIRS = (".agents/skills/au_racing/au_wong_choi_auto/scripts/au_racing_engine",)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict:
    out = {rel: sha256_file(REPO / rel) for rel in FROZEN_SOURCES}
    for rel in FROZEN_DIRS:
        for path in sorted((REPO / rel).glob("*.py")):
            out[str(path.relative_to(REPO))] = sha256_file(path)
    return out


# ── 快照 ──────────────────────────────────────────────────────────────────
def verified_snapshot(meeting: Path, day: str):
    """→ (snapshot_dir, created_at) or (None, reason)."""
    from au_window_review import pick_snapshot
    snap, rule, _local = pick_snapshot(meeting, day)
    if snap is None or rule != "pre_cutoff":
        return None, f"no_pre_cutoff_snapshot:{rule}"
    manifest = json.loads((snap / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = snap / item["name"]
        if not path.is_file() or sha256_file(path) != item["sha256"]:
            return None, "file_hash_mismatch"
    body = json.dumps({"files": manifest["files"], "recommendations": manifest.get("recommendations", [])},
                      ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(body).hexdigest() != manifest.get("signature"):
        return None, "signature_mismatch"
    return snap, manifest["created_at"]


def forward_meetings(root: Path, only_date: str | None = None):
    from corpus_paths import meeting_dirs
    out = []
    for meeting in meeting_dirs(root):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", meeting.name)
        if m and (m[1] == only_date if only_date else m[1] >= VALID_FROM):
            out.append((m[1], meeting))
    return sorted(out)


# ── pg33 ──────────────────────────────────────────────────────────────────
def pg33_raw(runs, gate=1 / 3):
    """Raw pg33 from the engine's own `form_quality_runs` (same selection as eq2_N6).

    `gate=1.0` reproduces production eq2_N6 exactly —— 用嚟做重播自檢。"""
    from au_racing_engine import engine_core as ec
    values = []
    for run in runs or []:
        finish, starters = int(run.get("finish_pos") or 0), int(run.get("starters") or 0)
        if not (starters >= 2 and 1 <= finish <= starters) or not run.get("prize"):
            continue
        p = (finish - 1) / (starters - 1)
        z_place = (0.5 - p) / ec.FORM_QUALITY_SD_PCT
        z_prize = (math.log10(float(run["prize"])) - ec.FORM_QUALITY_MU_LOG_PRIZE) / ec.FORM_QUALITY_SD_LOG_PRIZE
        values.append((z_place + (z_prize if p <= gate else min(0.0, z_prize))) / 2)
    if len(values) < 2:
        return None
    weights = ec.FORM_QUALITY_RECENCY_WEIGHTS[: len(values)]
    return round(sum(v * w for v, w in zip(values, weights)) / sum(weights), 6)  # 同引擎一樣捨入


def pg33_leaves(horses: dict, gate=1 / 3) -> dict:
    """{horse_number: leaf or None} with production's field population (all Logic horses)."""
    raws = {str(n): pg33_raw((h.get("_data") or {}).get("form_quality_runs"), gate)
            for n, h in horses.items() if isinstance(h, dict)}
    obs = [v for v in raws.values() if v is not None]
    if len(obs) < 3:
        return {n: None for n in raws}
    mu = sum(obs) / len(obs)
    sd = (sum((v - mu) ** 2 for v in obs) / len(obs)) ** 0.5
    if sd <= 0:
        return {n: None for n in raws}
    return {n: (None if v is None else max(0.0, min(100.0, 60 + 20 * (v - mu) / sd))) for n, v in raws.items()}


# ── 重新評分 ─────────────────────────────────────────────────────────────
def score_snapshot(snap: Path, meeting_name: str, date: str, created_at: str, results):
    from au_archive_calibrator import (choose_track_rows, detect_meeting_track, get_true_horse_name,
                                       normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_racing_engine.engine_core import (RacingEngine, backfill_prize_column,
                                              refresh_form_quality, refresh_pf_own_l600)
    from au_racing_engine import full_time_speed
    races = []
    logic_files = sorted(snap.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 999))
    if not logic_files:
        return races
    sample = json.loads(logic_files[0].read_text(encoding="utf-8"))
    track = detect_meeting_track(snap.parent.parent, sample)
    prediction_at = datetime.fromisoformat(created_at)
    for logic_path in logic_files:
        logic = json.loads(logic_path.read_text(encoding="utf-8"))
        ra = logic.get("race_analysis", {})
        race_no = parse_int(ra.get("race_number")) or parse_int(logic_path.stem.split("_")[1])
        rows = choose_track_rows(results.get((date, race_no), []), track)
        if not rows:
            continue
        lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}
        facts_path = snap / f"{date[5:]} Race {race_no} Facts.md"
        refresh_pf_own_l600(logic, facts_path)
        backfill_prize_column(logic, snap, race_no, date)
        refresh_form_quality(logic, facts_path)
        full_time_speed.prepare_field(logic, facts_path, prediction_at=prediction_at)
        ctx = dict(ra)
        horses = logic.get("horses", {})
        ctx["field_summary"] = _build_field_summary(horses)
        ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                    if isinstance(h, dict) and h.get("horse_name")]
        cand = pg33_leaves(horses)
        eq2 = pg33_leaves(horses, gate=1.0)
        out_rows = []
        for hnum, horse in horses.items():
            row = lookup.get(normalize_horse_name(get_true_horse_name(horse)))
            if not row:
                continue
            hd = dict(horse)
            hd.setdefault("horse_number", hnum)
            facts = (hd.get("_data") or {}).get("facts_section", "")
            res = RacingEngine(hd, ctx, facts_section=facts,
                               facts_path=str(snap / f"{date}_dummy.md")).analyze_horse()
            fs = {k: round(float(60 if v is None else v), 6) for k, v in (res.get("feature_scores") or {}).items()}
            composite = max(0.0, min(100.0, 60 + 0.6 * (fs["form_score"] - 60) + 0.4 * (fs["performance_quality_score"] - 60)))
            leaf = cand.get(str(hnum))
            out_rows.append({
                "n": parse_int(hnum) or 999, "name": get_true_horse_name(horse), "pos": int(row["pos"]),
                "sp": row.get("sp"), "features": fs,
                "cand_form_quality": round(composite if leaf is None else leaf, 6),
                "eq2_form_quality": round(composite if eq2.get(str(hnum)) is None else eq2[str(hnum)], 6),
                "wet": float(res.get("wet_form_feature") or 0.0),
                "proven_class": float(res.get("proven_class_feature") or 0.0),
                "full_time": float(res.get("full_time_speed_feature") or 0.0),
                "ability": float(res.get("ability_score") or 0.0),
            })
        if len(out_rows) >= 4:
            races.append({"meeting": meeting_name, "date": date, "race": race_no,
                          "field": len(out_rows), "rows": out_rows})
    return races


def collect(root: Path, only_date: str | None = None):
    from au_archive_calibrator import HISTORICAL_RESULTS_CSV, load_historical_results
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    audit, races = {}, []
    for date, meeting in forward_meetings(root, only_date):
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            audit[info] = audit.get(info, 0) + 1
            continue
        # 快照目錄名（20261014T…）冇 YYYY-MM-DD：引擎由 Facts 嘅 parent 名攞賽日，原地重播會令
        # 近績質素分篩走全部往績、靜靜跌落 fallback。抄去以場次命名嘅目錄先評（同 live 一樣）。
        with tempfile.TemporaryDirectory() as tmp:
            dated = Path(tmp) / meeting.name
            shutil.copytree(snap, dated)
            got = score_snapshot(dated, meeting.name, date, info, results)
        audit["meetings_scored" if got else "meetings_without_results"] = audit.get(
            "meetings_scored" if got else "meetings_without_results", 0) + 1
        races.extend(got)
    return races, audit


# ── 判決 ──────────────────────────────────────────────────────────────────
def arms(races):
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    base, cand = [], []
    for race in races:
        b = [{**r, "ability": exact_score(r, MATRIX_WEIGHTS)} for r in race["rows"]]
        c = []
        for r in race["rows"]:
            feats = {**r["features"], "form_quality_score": r["cand_form_quality"]}
            c.append({**r, "features": feats, "ability": exact_score({**r, "features": feats}, MATRIX_WEIGHTS)})
        base.append({**race, "rows": b})
        cand.append({**race, "rows": c})
    return base, cand


def longshot_flops(races):
    by_day = {}
    for race in races:
        n = len(race["rows"])
        top2 = sorted(race["rows"], key=lambda x: (-x["ability"], x["n"]))[:2]
        count = 0
        for x in top2:
            try:
                sp = float(str(x.get("sp")).replace("$", ""))
            except (TypeError, ValueError):
                sp = 0.0
            count += sp >= 15 and x["pos"] > n - n // 3
        by_day.setdefault(race["date"], []).append(count)
    return by_day


def judge(base, cand):
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in base]
    v3 = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates,
                              baseline_rows=_stage4_metric_rows(base, score),
                              candidate_rows=_stage4_metric_rows(cand, score),
                              leakage_audit_passed=True, ranking_metrics=RANKING_METRICS)
    fb, fc = longshot_flops(base), longshot_flops(cand)
    days = sorted(fb)
    stat = lambda f, pick: sum(c for d in pick for c in f[d])  # noqa: E731
    delta = stat(fc, days) - stat(fb, days)
    rng = random.Random(7)
    samples = sorted(stat(fc, p) - stat(fb, p) for p in
                     ([days[rng.randrange(len(days))] for _ in days] for _ in range(2000)))
    flops = {"base": stat(fb, days), "cand": stat(fc, days), "delta": delta, "ci": [samples[50], samples[1949]]}
    primary = v3["detail"]["primary"]
    no_regression = all(primary[k]["delta"] >= 0 for k in ("gold", "good_positional"))
    eligible = v3["verdict"] in ("PRIMARY_WIN", "RANKING_WIN") or (no_regression and flops["ci"][1] < 0)
    return {"ship_eligible": eligible, "v3": v3, "longshot_top2_bottom": flops,
            "counts": {"base": _counts(base, score), "cand": _counts(cand, score)},
            "races": len(dates), "meeting_days": len(set(dates))}


# ── CLI ───────────────────────────────────────────────────────────────────
def data_root() -> Path:
    return Path((REPO / ".wongchoi_au_data_root").read_text().strip())


def cmd_replay_check(args):
    """窗外一日重播自檢：eq2 門檻重算 = 引擎 form_quality_score；exact_score = 引擎 ability。唔計指標。"""
    if args.date >= VALID_FROM:
        raise SystemExit("replay-check only runs on a date before the forward window")
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    from au_walkforward_refit import exact_score
    races, audit = collect(data_root(), args.date)
    rows = [r for race in races for r in race["rows"]]
    leaf_gap = max((abs(r["eq2_form_quality"] - r["features"]["form_quality_score"]) for r in rows), default=None)
    ability_gap = max((abs(exact_score(r, MATRIX_WEIGHTS) - r["ability"]) for r in rows), default=None)
    moved = sum(abs(r["cand_form_quality"] - r["features"]["form_quality_score"]) > 1e-6 for r in rows)
    print(json.dumps({"date": args.date, "races": len(races), "runners": len(rows), "audit": audit,
                      "max_leaf_gap_eq2_vs_engine": leaf_gap, "max_ability_gap_exact_vs_engine": ability_gap,
                      "runners_where_pg33_differs": moved}, indent=1))
    if rows and (leaf_gap > 1e-4 or ability_gap > 1e-4):
        raise SystemExit("replay does not reproduce the engine — do not freeze")


def cmd_freeze(_args):
    if FREEZE.exists():
        raise SystemExit(f"{FREEZE} already exists — a frozen design is never rewritten")
    freeze = {
        "experiment": "EXP-20261016-11", "candidate": "pg33_N6 (EXP-20261016-10)", "baseline": "eq2_N6 (production)",
        "valid_from": VALID_FROM, "min_meeting_days": MIN_MEETING_DAYS, "one_look": True, "weights": "live MATRIX_WEIGHTS",
        "rule": "v3 fixed_rule PRIMARY_WIN/RANKING_WIN, OR fixed Gold & Good delta >= 0 AND top-2 $15+ "
                "bottom-third count delta 95% day-bootstrap CI upper < 0",
        "inputs": "pre-race immutable snapshots (pick_snapshot pre_cutoff), signature + per-file sha256 verified",
        "code_sha256": code_hashes(), "frozen_at": datetime.now().astimezone().isoformat(),
    }
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"frozen → {FREEZE}")


def load_freeze():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    drift = {k for k, v in freeze["code_sha256"].items()
             if not (REPO / k).exists() or sha256_file(REPO / k) != v}
    drift |= set(code_hashes()) - set(freeze["code_sha256"])
    return freeze, sorted(drift)


def cmd_status(_args):
    freeze, drift = load_freeze()
    from au_archive_calibrator import HISTORICAL_RESULTS_CSV, load_historical_results
    result_dates = {d for d, _r in load_historical_results(HISTORICAL_RESULTS_CSV)}
    days, skipped = set(), {}
    for date, meeting in forward_meetings(data_root()):
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            skipped[info] = skipped.get(info, 0) + 1
        elif date in result_dates:
            days.add(date)
    print(f"forward days with snapshot + results: {len(days)} / {freeze['min_meeting_days']} needed")
    print(f"meetings skipped: {skipped}")
    print(f"code drift vs freeze: {drift or 'none'}")
    print(f"already evaluated: {RESULT.exists()}")


def cmd_evaluate(args):
    if RESULT.exists():
        raise SystemExit("forward family already opened once — refusing a second look")
    freeze, drift = load_freeze()
    if drift:
        raise SystemExit(f"code differs from the frozen design: {drift}")
    races, audit = collect(data_root())
    days = len({r["date"] for r in races})
    if args.dry_run_counts:
        print(json.dumps({"forward_days": days, "races": len(races), "audit": audit}, indent=1))
        return
    if days < freeze["min_meeting_days"]:
        raise SystemExit(f"only {days} forward meeting days; need {freeze['min_meeting_days']}")
    verdict = judge(*arms(races))
    verdict.update({"audit": audit, "evaluated_at": datetime.now().astimezone().isoformat()})
    RESULT.write_text(json.dumps(verdict, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"ship_eligible={verdict['ship_eligible']}  v3={verdict['v3']['verdict']}/{verdict['v3']['reason']}  "
          f"longshot flops {verdict['longshot_top2_bottom']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    rc = sub.add_parser("replay-check")
    rc.add_argument("--date", required=True)
    sub.add_parser("status")
    e = sub.add_parser("evaluate")
    e.add_argument("--dry-run-counts", action="store_true",
                   help="only count replayable forward races; never computes metrics")
    args = ap.parse_args(argv)
    {"freeze": cmd_freeze, "replay-check": cmd_replay_check, "status": cmd_status,
     "evaluate": cmd_evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()
