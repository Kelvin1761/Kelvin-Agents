#!/usr/bin/env python3
"""EXP-20261016-74：今日改動合併 forward 確認 + walk-forward refit 權重（B1）+ GBM 對照（G）。

    freeze    --corpus A1_corpus.json   凍結 A0／A1 commit、B1 權重（refit 程序一次 fit）、GBM 模型；已存在就拒絕
    status                              只數 forward 窗有快照兼有賽果嘅賽日 —— 唔計任何指標
    evaluate                            一次：樣本未夠、code 唔夾、已評過 → 拒絕
    replay-check --date D               窗外一日：A1 重播 ability vs production 存檔差幾多（唔計指標）

規格見 docs/experiments/EXP-20261016-74-au-bundle-forward-protocol.md —— 唔准喺度改。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import random
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for p in (SCRIPTS, SHARED, SHARED / "scripts"):
    sys.path.insert(0, str(p))

EXP_DIR = REPO / "docs/experiments/EXP-20261016-74-forward"
FREEZE = EXP_DIR / "freeze.json"
RESULT = EXP_DIR / "forward_result.json"
GBM_FILE = EXP_DIR / "gbm.pkl"
A0_SHA = "d51796e1"
VALID_FROM = "2026-10-17"
TRAIN_FROM, TRAIN_TO = "2026-08-05", "2026-10-16"
MIN_MEETING_DAYS = 41
RANKING_METRICS = ("top3_capture_at5", "ndcg_at5", "top5_pairwise_auc")
WORKER = HERE / "au_bundle_replay_worker_20261016.py"
FROZEN_SOURCES = ("scratch/au_bundle_forward_20261016.py", "scratch/au_bundle_replay_worker_20261016.py")
GBM_PARAMS = dict(max_iter=200, learning_rate=0.05, max_leaf_nodes=15, min_samples_leaf=50,
                  l2_regularization=1.0, random_state=7)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout.strip()


def data_root() -> Path:
    return Path((REPO / ".wongchoi_au_data_root").read_text().strip())


def paid(n):
    return 3 if n >= 8 else 2


# ── GBM ───────────────────────────────────────────────────────────────────
def gbm_matrix(races):
    from au_racing_engine.scoring import FEATURE_KEYS
    keys = list(FEATURE_KEYS) + ["wet", "proven_class", "full_time"]
    X, y, index = [], [], []
    for ri, race in enumerate(races):
        rows = race["rows"]
        vals = [[(r["features"][k] if k in r["features"] else float(r.get(k) or 0.0)) for k in keys] for r in rows]
        means = [sum(col) / len(col) for col in zip(*vals)]
        n = len(rows)
        for r, v in zip(rows, vals):
            X.append([a - m for a, m in zip(v, means)])
            y.append(int(r["pos"] <= paid(n)) if "pos" in r else 0)
            index.append((ri, r["n"]))
    return X, y, index, keys


def clean(races, lo=None, hi=None):
    return sorted([r for r in races if (lo is None or r["date"] >= lo) and (hi is None or r["date"] <= hi)
                   and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])],
                  key=lambda r: (r["date"], r["meeting"], r["race"]))


# ── snapshots ─────────────────────────────────────────────────────────────
def verified_snapshot(meeting: Path, day: str):
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


def meetings_between(lo, hi=None, only=None):
    from corpus_paths import meeting_dirs
    out = []
    for meeting in meeting_dirs(data_root()):
        m = re.search(r"(\d{4}-\d{2}-\d{2})", meeting.name)
        if not m:
            continue
        d = m[1]
        if (only and d == only) or (not only and d >= lo and (hi is None or d <= hi)):
            out.append((d, meeting))
    return sorted(out)


def stage_snapshots(stage: Path, meetings):
    manifest, audit = [], {}
    for date, meeting in meetings:
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            audit[info] = audit.get(info, 0) + 1
            continue
        shutil.copytree(snap, stage / meeting.name)
        manifest.append({"dir": meeting.name, "date": date, "created_at": info})
        audit["staged"] = audit.get("staged", 0) + 1
    (stage / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    return audit


def replay(sha: str, stage: Path, out: Path, tmp: Path):
    tree = tmp / f"tree-{sha[:8]}"
    git("worktree", "add", "--detach", str(tree), sha)
    try:
        for marker in REPO.glob(".wongchoi_*root"):
            shutil.copy(marker, tree / marker.name)
        subprocess.run([sys.executable, str(WORKER), "--repo", str(tree), "--stage", str(stage), "--out", str(out)],
                       check=True, env={**__import__("os").environ, "PYTHONDONTWRITEBYTECODE": "1"})
    finally:
        git("worktree", "remove", "--force", str(tree))
    return json.loads(out.read_text(encoding="utf-8"))["races"]


def join_results(races):
    from au_archive_calibrator import (HISTORICAL_RESULTS_CSV, choose_track_rows, detect_meeting_track,
                                       load_historical_results, normalize_horse_name)
    results = load_historical_results(HISTORICAL_RESULTS_CSV)
    joined = []
    for race in races:
        venue = detect_meeting_track(Path(race["meeting"]), {})
        rows = choose_track_rows(results.get((race["date"], race["race"]), []), venue)
        if not rows:
            continue
        lookup = {normalize_horse_name(r["horse_slug"]): r for r in rows}
        out_rows = []
        for x in race["rows"]:
            row = lookup.get(normalize_horse_name(x["name"]))
            if row:
                out_rows.append({**x, "pos": int(row["pos"]), "sp": row.get("sp")})
        if len(out_rows) >= 4:
            joined.append({**race, "rows": out_rows})
    return joined


# ── judge ─────────────────────────────────────────────────────────────────
def v3(base, cand):
    from au_eval import _stage4_metric_rows
    from model_evaluation_decision import evaluate_full_record
    score = lambda r: r["ability"]  # noqa: E731
    v = evaluate_full_record(domain="au", mode="fixed_rule", dates=[r["date"] for r in base],
                             baseline_rows=_stage4_metric_rows(base, score), candidate_rows=_stage4_metric_rows(cand, score),
                             leakage_audit_passed=True, ranking_metrics=RANKING_METRICS)
    pick = lambda d: {k: {kk: e[kk] for kk in ("delta", "ci_low", "ci_high", "p_value")} for k, e in d.items()}  # noqa: E731
    return {"verdict": v["verdict"], "reason": v["reason"],
            "primary": pick(v["detail"]["primary"]), "ranking": pick(v["detail"]["ranking"])}


def flops(races):
    total = 0
    for race in races:
        n = len(race["rows"])
        for x in sorted(race["rows"], key=lambda x: (-x["ability"], x["n"]))[:2]:
            try:
                sp = float(str(x.get("sp")).replace("$", ""))
            except (TypeError, ValueError):
                sp = 0.0
            total += sp >= 15 and x["pos"] > n - n // 3
    return total


def align(*arms):
    keys = set.intersection(*[{(r["meeting"], r["race"]) for r in a} for a in arms])
    out = []
    for a in arms:
        by = {(r["meeting"], r["race"]): r for r in a if (r["meeting"], r["race"]) in keys}
        out.append([by[k] for k in sorted(keys, key=lambda k: (by[k]["date"], k))])
    return out


def judge(a0, a1, freeze):
    from au_walkforward_refit import exact_score
    weights = freeze["b1_weights"]
    b1 = [{**r, "rows": [{**x, "ability": exact_score(x, weights)} for x in r["rows"]]} for r in a1]
    model = pickle.loads(GBM_FILE.read_bytes())
    X, _y, index, _ = gbm_matrix(a1)
    prob = dict(zip(index, model.predict_proba(X)[:, 1])) if X else {}
    g = [{**r, "rows": [{**x, "ability": float(prob[(i, x["n"])])} for x in r["rows"]]} for i, r in enumerate(a1)]
    out = {"bundle_A1_vs_A0": v3(a0, a1), "ml_weights_B1_vs_A1": v3(a1, b1), "ml_weights_B1_vs_A0": v3(a0, b1),
           "ml_formula_G_vs_A1": v3(a1, g),
           "flops_top2_15plus": {"A0": flops(a0), "A1": flops(a1), "B1": flops(b1), "G": flops(g)},
           "races": len(a1), "meeting_days": len({r["date"] for r in a1})}
    p_b1 = min(e["p_value"] for e in {**out["ml_weights_B1_vs_A1"]["primary"], **out["ml_weights_B1_vs_A1"]["ranking"]}.values())
    p_g = min(e["p_value"] for e in {**out["ml_formula_G_vs_A1"]["primary"], **out["ml_formula_G_vs_A1"]["ranking"]}.values())
    lo, hi = sorted([p_b1, p_g])
    out["ml_holm"] = {"B1_min_p": p_b1, "G_min_p": p_g, "holm_first": min(1.0, 2 * lo), "holm_second": min(1.0, max(2 * lo, hi))}
    return out


# ── commands ──────────────────────────────────────────────────────────────
def code_hashes():
    return {rel: sha256_file(REPO / rel) for rel in FROZEN_SOURCES}


def cmd_freeze(args):
    if FREEZE.exists():
        raise SystemExit(f"{FREEZE} already exists — a frozen design is never rewritten")
    from au_walkforward_refit import Matrix, PROCEDURE, fit_window, load_clean, procedure_hash
    from sklearn.ensemble import HistGradientBoostingClassifier
    import sklearn
    a1_sha = git("rev-parse", "origin/main")
    engine = ".agents/skills/au_racing/au_wong_choi_auto/scripts"
    if git("diff", "--name-only", a1_sha, "HEAD", "--", engine) and not args.allow_non_main:
        raise SystemExit("this checkout's engine differs from origin/main — A1 must be exactly origin/main")
    corpus = [r for r in load_clean(args.corpus) if TRAIN_FROM <= r["date"] <= TRAIN_TO]
    weights, meta = fit_window(corpus, Matrix(corpus), PROCEDURE)
    X, y, _idx, keys = gbm_matrix(corpus)
    model = HistGradientBoostingClassifier(**GBM_PARAMS).fit(X, y)
    EXP_DIR.mkdir(parents=True, exist_ok=True)
    GBM_FILE.write_bytes(pickle.dumps(model))
    freeze = {
        "experiment": "EXP-20261016-74", "a0_sha": git("rev-parse", A0_SHA), "a1_sha": a1_sha,
        "valid_from": VALID_FROM, "min_meeting_days": MIN_MEETING_DAYS, "one_look": True,
        "b1_weights": weights, "b1_meta": meta, "refit_procedure_hash": procedure_hash(),
        "train_window": [TRAIN_FROM, TRAIN_TO], "train_races": len(corpus), "corpus_file_sha256": sha256_file(Path(args.corpus)),
        "gbm": {"params": GBM_PARAMS, "features": keys, "sklearn": sklearn.__version__,
                "model_sha256": sha256_file(GBM_FILE), "train_rows": len(X)},
        "code_sha256": code_hashes(), "frozen_at": datetime.now().astimezone().isoformat(),
    }
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"frozen → {FREEZE}\nB1 weights {weights}\nmeta {meta}")


def load_freeze():
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    drift = [k for k, v in freeze["code_sha256"].items() if sha256_file(REPO / k) != v]
    if sha256_file(GBM_FILE) != freeze["gbm"]["model_sha256"]:
        drift.append(GBM_FILE.name)
    return freeze, drift


def cmd_status(_args):
    freeze, drift = load_freeze()
    from au_archive_calibrator import HISTORICAL_RESULTS_CSV, load_historical_results
    result_dates = {d for d, _r in load_historical_results(HISTORICAL_RESULTS_CSV)}
    days, skipped = set(), {}
    for date, meeting in meetings_between(freeze["valid_from"]):
        snap, info = verified_snapshot(meeting, date)
        if snap is None:
            skipped[info] = skipped.get(info, 0) + 1
        elif date in result_dates:
            days.add(date)
    print(f"forward days with snapshot + results: {len(days)} / {freeze['min_meeting_days']} needed")
    print(f"meetings skipped: {skipped}")
    print(f"code drift vs freeze: {drift or 'none'}")
    print(f"already evaluated: {RESULT.exists()}")


def run_arms(freeze, meetings):
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp); stage = tmp / "stage"; stage.mkdir()
        audit = stage_snapshots(stage, meetings)
        a0 = join_results(replay(freeze["a0_sha"], stage, tmp / "a0.json", tmp))
        a1 = join_results(replay(freeze["a1_sha"], stage, tmp / "a1.json", tmp))
    return a0, a1, audit


def cmd_evaluate(args):
    if RESULT.exists():
        raise SystemExit("forward family already opened once — refusing a second look")
    freeze, drift = load_freeze()
    if drift:
        raise SystemExit(f"code differs from the frozen design: {drift}")
    a0, a1, audit = run_arms(freeze, meetings_between(freeze["valid_from"]))
    a0, a1 = align(clean(a0), clean(a1))
    days = len({r["date"] for r in a1})
    if days < freeze["min_meeting_days"]:
        raise SystemExit(f"only {days} forward meeting days; need {freeze['min_meeting_days']}")
    verdict = judge(a0, a1, freeze)
    verdict.update({"audit": audit, "evaluated_at": datetime.now().astimezone().isoformat()})
    RESULT.write_text(json.dumps(verdict, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps({k: verdict[k] for k in ("races", "meeting_days", "flops_top2_15plus", "ml_holm")}, indent=1))


def cmd_replay_check(args):
    """窗外一日：A0、A1 都能重播，A1 ability 同 production 存檔 CSV 對得上（唔計指標）。"""
    if args.date >= VALID_FROM:
        raise SystemExit("replay-check only runs on a date before the forward window")
    freeze = {"a0_sha": git("rev-parse", A0_SHA), "a1_sha": git("rev-parse", "HEAD")}
    a0, a1, audit = run_arms(freeze, meetings_between(None, only=args.date))
    print(json.dumps({"date": args.date, "audit": audit, "a0_races": len(a0), "a1_races": len(a1),
                      "a0_runners": sum(len(r["rows"]) for r in a0), "a1_runners": sum(len(r["rows"]) for r in a1)}, indent=1))
    if not a0 or not a1:
        raise SystemExit("replay produced no races — do not freeze")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze"); f.add_argument("--corpus", required=True)
    f.add_argument("--allow-non-main", action="store_true", help="tests only")
    sub.add_parser("status")
    sub.add_parser("evaluate")
    rc = sub.add_parser("replay-check"); rc.add_argument("--date", required=True)
    args = ap.parse_args(argv)
    {"freeze": cmd_freeze, "status": cmd_status, "evaluate": cmd_evaluate, "replay-check": cmd_replay_check}[args.cmd](args)


if __name__ == "__main__":
    main()
