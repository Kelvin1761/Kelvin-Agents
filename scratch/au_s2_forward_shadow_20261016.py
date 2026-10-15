#!/usr/bin/env python3
"""EXP-20261016-03：S2 forward shadow（凍結設計 + 凍結權重，一個 family 只開一次）。

S2 = pace_perf 入面 pace_figure 同 Sportsbet 全程速度各佔一半（EXP-20261016-02）。

    freeze    寫凍結設定（權重、code hash、評估規則），已存在就拒絕覆蓋。
    status    只數 forward 窗有幾多個有賽果嘅賽日／場次 —— **唔計任何指標**。
    evaluate  一次過：未夠樣本、code hash 唔夾、或者已經評估過 → 拒絕。

輸入一律係**賽前不可改快照**（`<meeting>/_prediction_snapshots/<id>/`，揀 11:00 悉尼時間
之前最後一個，同 `au_window_review.pick_snapshot` 一樣），簽名同逐檔 sha256 要對得上。
引擎用凍結 code 重新評分快照入面嘅 Logic；A_sb 只用快照日或之前已經出現過嘅往績事件。

三個 arm（全部凍結權重、production 算術）：
    A0  現行 leaf + 凍結時 live 權重
    B0  現行 leaf + 凍結 pooled refit 權重（同一 refit 程序）
    B1  S2 leaf  + 凍結 pooled refit 權重
判決（預先登記）：B1 vs B0 `walk_forward_oos` WIN，而且 B1 vs A0 唔係
primary_regression／ranking_metric_harm。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for path in (SCRIPTS, SHARED, SHARED / "scripts", HERE):
    sys.path.insert(0, str(path))

EXP_DIR = REPO / "docs/experiments/EXP-20261016-03-forward"
FREEZE = EXP_DIR / "freeze.json"
RESULT = EXP_DIR / "forward_result.json"
VALID_FROM = "2026-10-17"
MIN_MEETING_DAYS = 41          # 同 EXP-20261016-02 嘅 OOS 一樣多
RANKING_METRICS = ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")
FROZEN_SOURCES = (
    "scratch/au_s2_forward_shadow_20261016.py",
    "scratch/au_sb_total_speed_20261016.py",
    "scratch/au_sb_total_speed_arms_20261016.py",
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


def forward_meetings(root: Path):
    """[(date, meeting_dir)] for meetings dated ≥ VALID_FROM (top level and Archive)."""
    from corpus_paths import meeting_dirs
    out = []
    for meeting in meeting_dirs(root):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", meeting.name)
        if m and m[1] >= VALID_FROM:
            out.append((m[1], meeting))
    return sorted(out)


# ── 重新評分（同 au_dump_engine_leaves 同一條路）────────────────────────
def score_snapshot(snap: Path, meeting_name: str, date: str, created_at: str, results):
    from au_archive_calibrator import (choose_track_rows, detect_meeting_track, get_true_horse_name,
                                       normalize_horse_name, parse_int)
    from au_auto_orchestrator import _build_field_summary
    from au_racing_engine.engine_core import (RacingEngine, backfill_prize_column,
                                              refresh_pf_own_l600)
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
        full_time_speed.prepare_field(logic, facts_path, prediction_at=prediction_at)
        ctx = dict(ra)
        horses = logic.get("horses", {})
        ctx["field_summary"] = _build_field_summary(horses)
        ctx["field_horse_names"] = [h.get("horse_name") for h in horses.values()
                                    if isinstance(h, dict) and h.get("horse_name")]
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
            fs = res.get("feature_scores") or {}
            out_rows.append({
                "n": parse_int(hnum) or 999, "name": get_true_horse_name(horse), "pos": int(row["pos"]),
                "features": {k: round(float(60 if v is None else v), 6) for k, v in fs.items()},
                "wet": float(res.get("wet_form_feature") or 0.0),
                "proven_class": float(res.get("proven_class_feature") or 0.0),
                "full_time": float(res.get("full_time_speed_feature") or 0.0),
                "ability": float(res.get("ability_score") or 0.0),
                "distance": ra.get("distance"), "going": (res.get("race_context") or {}).get("going"),
            })
        if len(out_rows) >= 4:
            races.append({"meeting": meeting_name, "date": date, "race": race_no,
                          "field": len(out_rows), "rows": out_rows})
    return races


def add_s2(races, events, histories):
    """Copy of each race with S2 pace_figure (EXP-20261016-02 arm, unchanged formula)."""
    import au_sb_total_speed_20261016 as sb
    from au_racing_engine import full_time_speed as fts
    by_date = defaultdict(list)
    for race in races:
        by_date[race["date"]].append(race)
    out = []
    for date in sorted(by_date):
        visible = sorted((e for e in events.values() if e["first_seen"] <= date), key=lambda e: e["date"])
        lookup, _n = sb.context_lookup(visible, date)
        for race in by_date[date]:
            dm = re.search(r"\d{3,5}", str(race["rows"][0].get("distance") or ""))
            distance = int(dm[0]) if dm else 1400
            going = fts.condition_key(re.sub(r"\s*\d+$", "", str(race["rows"][0].get("going") or "")))
            raws = []
            for row in race["rows"]:
                runs = histories.get((date, "snapshot:" + race["meeting"], race["race"], fts.norm(row["name"])), [])
                values, _k, _rel = fts.aggregate(runs, fts.norm(row["name"]), date, distance, going, lookup)
                raws.append(values["A"])
            zs = fts.zscores(raws)
            rows = []
            for row, raw, z in zip(race["rows"], raws, zs):
                feats = dict(row["features"])
                zz = z if raw is not None else 0.0
                feats["pace_figure_score"] = round(0.5 * feats["pace_figure_score"] + 0.5 * (60 + 10 * zz), 6)
                rows.append({**row, "features": feats, "asb_observed": raw is not None})
            out.append({**race, "rows": rows})
    return out


def collect(root: Path):
    """→ (base_races, s2_races, audit). Pure replay of frozen code over snapshots."""
    import au_sb_total_speed_20261016 as sb
    from au_archive_calibrator import HISTORICAL_RESULTS_CSV, load_historical_results
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    audit = defaultdict(int)
    snaps = []
    for date, meeting in forward_meetings(root):
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            audit[info] += 1
            continue
        snaps.append((date, meeting, snap, info))
    base = []
    for date, meeting, snap, created in snaps:
        races = score_snapshot(snap, meeting.name, date, created, results)
        audit["meetings_scored" if races else "meetings_without_results"] += 1
        base.extend(races)
    sources = sb.corpus_sources(root) + [(d, "snapshot:" + m.name, s) for d, m, s, _c in snaps]
    events, histories, sb_audit = sb.parse_corpus(root, sources)
    s2 = add_s2(base, events, histories)
    audit.update({f"sb_{k}": v for k, v in sb_audit.items()})
    return base, s2, dict(audit)


# ── 判決 ──────────────────────────────────────────────────────────────────
def arms(base, s2, freeze):
    from au_walkforward_refit import exact_score
    def with_ability(races, weights):
        return [{**race, "rows": [{**r, "ability": exact_score(r, weights)} for r in race["rows"]]}
                for race in races]
    w = freeze["weights"]
    return {"A0": with_ability(base, w["A0_live"]), "B0": with_ability(base, w["B0_pooled"]),
            "B1": with_ability(s2, w["B1_pooled"])}


def judge(arm_races):
    from au_eval import _counts, _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record
    score = lambda r: r["ability"]  # noqa: E731
    dates = [r["date"] for r in arm_races["A0"]]
    rows = {k: _stage4_metric_rows(v, score) for k, v in arm_races.items()}

    def full(base, cand):
        return evaluate_full_record(domain="au", mode="walk_forward_oos", dates=dates,
                                    baseline_rows=rows[base], candidate_rows=rows[cand],
                                    leakage_audit_passed=True, ranking_metrics=RANKING_METRICS)
    primary, guard = full("B0", "B1"), full("A0", "B1")
    ship = (primary["verdict"] in ("PRIMARY_WIN", "RANKING_WIN")
            and guard["reason"] not in ("primary_regression", "ranking_metric_harm"))
    return {"ship_eligible": ship, "primary_B1_vs_B0": primary, "guard_B1_vs_A0": guard,
            "stale_B0_vs_A0": full("A0", "B0"),
            "counts": {k: _counts(v, score) for k, v in arm_races.items()},
            "races": len(dates), "meeting_days": len(set(dates))}


# ── CLI ───────────────────────────────────────────────────────────────────
def data_root() -> Path:
    return Path((REPO / ".wongchoi_au_data_root").read_text().strip())


def cmd_freeze(args):
    if FREEZE.exists():
        raise SystemExit(f"{FREEZE} already exists — a frozen design is never rewritten")
    from au_racing_engine.scoring import MATRIX_WEIGHTS
    pooled = json.loads(Path(args.pooled).read_text(encoding="utf-8"))
    freeze = {
        "experiment": "EXP-20261016-03", "candidate": "S2 (EXP-20261016-02)",
        "valid_from": VALID_FROM, "min_meeting_days": MIN_MEETING_DAYS, "one_look": True,
        "weights": {"A0_live": dict(MATRIX_WEIGHTS),
                    "B0_pooled": pooled["prod_f6a"]["weights"],
                    "B1_pooled": pooled["arm_S2"]["weights"]},
        "pooled_fit": {k: {kk: vv for kk, vv in v.items() if kk != "weights"}
                       for k, v in pooled.items() if isinstance(v, dict)},
        "refit_procedure_hash": pooled["procedure_hash"],
        "rule": "B1 vs B0 walk_forward_oos PRIMARY_WIN/RANKING_WIN AND B1 vs A0 not "
                "primary_regression/ranking_metric_harm; ranking metrics " + ",".join(RANKING_METRICS),
        "inputs": "pre-race immutable snapshots (pick_snapshot pre_cutoff), signature + per-file sha256 verified",
        "code_sha256": code_hashes(),
        "frozen_at": datetime.now().astimezone().isoformat(),
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
    root = data_root()
    days, reasons = set(), defaultdict(int)
    from au_archive_calibrator import HISTORICAL_RESULTS_CSV, load_historical_results
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    result_dates = {d for d, _r in results}
    for date, meeting in forward_meetings(root):
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            reasons[info] += 1
        elif date in result_dates:
            days.add(date)
    print(f"forward days with snapshot + results: {len(days)} / {freeze['min_meeting_days']} needed")
    print(f"meetings skipped: {dict(reasons)}")
    print(f"code drift vs freeze: {drift or 'none'}")
    print(f"already evaluated: {RESULT.exists()}")


def cmd_evaluate(args):
    if RESULT.exists():
        raise SystemExit("forward family already opened once — refusing a second look")
    freeze, drift = load_freeze()
    if drift:
        raise SystemExit(f"code differs from the frozen design: {drift}")
    base, s2, audit = collect(data_root())
    days = len({r["date"] for r in base})
    if days < freeze["min_meeting_days"] and not args.dry_run_counts:
        raise SystemExit(f"only {days} forward meeting days; need {freeze['min_meeting_days']}")
    if args.dry_run_counts:
        print(json.dumps({"forward_days": days, "races": len(base), "audit": audit}, indent=1))
        return
    verdict = judge(arms(base, s2, freeze))
    verdict.update({"audit": audit, "evaluated_at": datetime.now().astimezone().isoformat()})
    RESULT.write_text(json.dumps(verdict, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(f"ship_eligible={verdict['ship_eligible']}  primary={verdict['primary_B1_vs_B0']['verdict']}"
          f"/{verdict['primary_B1_vs_B0']['reason']}  guard={verdict['guard_B1_vs_A0']['reason']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--pooled", required=True)
    sub.add_parser("status")
    e = sub.add_parser("evaluate")
    e.add_argument("--dry-run-counts", action="store_true",
                   help="only count replayable forward races; never computes metrics")
    args = ap.parse_args(argv)
    {"freeze": cmd_freeze, "status": cmd_status, "evaluate": cmd_evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()
