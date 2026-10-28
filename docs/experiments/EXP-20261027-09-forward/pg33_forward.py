"""EXP-20261027-09: frozen forward test of pg33_N6 (EXP-20261016-10) against live eq2_N6.

    freeze    write freeze.json (commit + sha256 of every file the verdict depends on); once
    selftest  wiring check on one already-seen meeting: no outcome is read
    status    count eligible race days / races since valid_from; no metric is computed
    evaluate  one look, after >= min_race_days; writes result.json and refuses to run again

Arm A = the frozen engine as is (live eq2_N6). Arm B = the same engine with only the per-run
近績質素 value replaced by pg33 (prize credit only when the run finished in the top third of
the field; prize debit always counts). Both arms rescore the same immutable pre-race snapshot
with the same live weights, so the verdict is the fixed arm of §8 (mode fixed_rule).
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import runpy
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
SCRIPTS = REPO / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
ORCH = SCRIPTS / "au_auto_orchestrator.py"
SHARED = REPO / ".agents/skills/shared_racing"
FREEZE = HERE / "freeze.json"
RESULT = HERE / "result.json"
DISK = Path("/Volumes/Kelvin Hardisk 1")
WORK = DISK / "WongChoi-Archive/scratch/EXP-20261027-09-pg33-forward"

VALID_FROM = "2026-10-28"   # 10-17..10-27 were read by the divergence diagnostic that motivated this
MIN_RACE_DAYS = 30
KEEP = re.compile(r"(Racecard|Formguide|Facts|Formguide_Index)\.md$|^Race_\d+_Logic\.json$|^Odds\.json$|^odds_history\.json$")
PRIMARY = ("gold", "good_positional")
RANKING = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5", "mean_top3_model_rank")

sys.path.insert(0, str(SHARED))
sys.path.insert(0, str(SHARED / "race_reflector/scripts"))


def frozen_files() -> list[Path]:
    engine = sorted((SCRIPTS / "au_racing_engine").glob("*.py"))
    return engine + [ORCH, SHARED / "model_evaluation_decision.py", SHARED / "eval_metrics.py",
                     SHARED / "race_reflector/scripts/unified_reflector_core.py", Path(__file__).resolve()]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def au_root() -> Path:
    return Path((REPO / ".wongchoi_au_data_root").read_text(encoding="utf-8").strip())


# ── arm B: pg33 per-run value, everything else identical to engine_core._form_quality_digest ──

def install_pg33() -> None:
    from au_racing_engine import engine_core as ec

    def _form_quality_digest_pg33(official_entries, *, meeting_date=""):
        runs = ec._performance_quality_digest(
            official_entries, meeting_date=meeting_date,
            max_runs=len(ec.FORM_QUALITY_RECENCY_WEIGHTS)).get("runs", [])
        values = []
        for run in runs:
            finish, starters = int(run.get("finish_pos") or 0), int(run.get("starters") or 0)
            if not (starters >= 2 and 1 <= finish <= starters):
                continue
            p = (finish - 1) / (starters - 1)
            z_place = (0.5 - p) / ec.FORM_QUALITY_SD_PCT
            z_prize = (math.log10(float(run["prize"])) - ec.FORM_QUALITY_MU_LOG_PRIZE) / ec.FORM_QUALITY_SD_LOG_PRIZE
            credit = z_prize if p <= 1 / 3 else min(0.0, z_prize)
            values.append((run, (z_place + credit) / 2))
        if len(values) < 2:
            return {}
        weights = ec.FORM_QUALITY_RECENCY_WEIGHTS[: len(values)]
        raw = sum(v * w for (_r, v), w in zip(values, weights)) / sum(weights)
        return {"raw": round(raw, 6), "run_count": len(values),
                "runs": [{"date": r.get("date"), "finish_pos": r.get("finish_pos"),
                          "starters": r.get("starters"), "prize": r.get("prize"),
                          "distance": r.get("distance"), "value": round(v, 6)} for r, v in values]}

    ec._form_quality_digest = _form_quality_digest_pg33


def run_arm_b(target: str) -> None:
    sys.path.insert(0, str(SCRIPTS))
    install_pg33()
    sys.argv = [str(ORCH), target]
    runpy.run_path(str(ORCH), run_name="__main__")


# ── replay ──

def meetings(since: str, until: str = "9999") -> list[tuple[Path, Path]]:
    from unified_reflector_core import select_prerace_snapshot
    root = au_root()
    found = {}
    for parent in (root, root / "Archive"):
        for d in parent.iterdir() if parent.is_dir() else ():
            if d.is_dir() and re.match(r"\d{4}-\d\d-\d\d ", d.name) and since <= d.name[:10] <= until:
                found.setdefault(d.name, d)
    out = []
    for name in sorted(found):
        d = found[name]
        if not (d / "Race_Results_Reflector.md").exists():
            continue
        snap = select_prerace_snapshot(d, platform="au")[0]
        if snap is not None:
            out.append((d, snap))
    return out


def replay(arm: str, meeting: Path, snap: Path) -> tuple[str, str, int]:
    dst = WORK / arm / meeting.name
    if (dst / ".done").exists():
        return arm, meeting.name, 0
    if dst.exists():
        shutil.rmtree(dst)
    dst.mkdir(parents=True)
    for f in snap.iterdir():
        if f.is_file() and KEEP.search(f.name):
            shutil.copy2(f, dst / f.name)
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", TMPDIR=str(WORK / "tmp"), WC_DISABLE_POST_SUCCESS_DEPLOY="1")
    cmd = [sys.executable, str(ORCH), str(dst)] if arm == "A" else [sys.executable, __file__, "_arm-b", str(dst)]
    p = subprocess.run(cmd, cwd=REPO, env=env, capture_output=True, text=True, timeout=3600)
    (dst / "orchestrator.log").write_text(p.stdout[-20000:] + "\n--- stderr ---\n" + p.stderr[-20000:])
    if p.returncode == 0:
        (dst / ".done").write_text("ok")
    return arm, meeting.name, p.returncode


def ranked(logic_path: Path, drop: set[int]) -> list[int]:
    horses = json.loads(logic_path.read_text(encoding="utf-8")).get("horses") or {}
    rows = sorted((h["python_auto"]["rank"], int(n)) for n, h in horses.items()
                  if str(n).isdigit() and (h.get("python_auto") or {}).get("rank") and int(n) not in drop)
    return [n for _r, n in rows]


def need_disk() -> None:
    if not DISK.is_dir() or not os.path.ismount(DISK):
        sys.exit(f"{DISK} is not mounted — refusing to write scratch onto the internal disk")
    WORK.mkdir(parents=True, exist_ok=True)
    (WORK / "tmp").mkdir(exist_ok=True)


def verify_freeze() -> dict:
    if not FREEZE.exists():
        sys.exit("not frozen")
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    bad = [rel for rel, digest in freeze["code_sha256"].items()
           if not (REPO / rel).exists() or sha256(REPO / rel) != digest]
    if bad:
        sys.exit(f"code differs from freeze (check out {freeze['commit']}): {bad}")
    return freeze


# ── commands ──

def cmd_freeze(_args) -> None:
    if FREEZE.exists():
        sys.exit("freeze.json already exists; it is never rewritten")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    freeze = {
        "experiment": "EXP-20261027-09",
        "candidate": "pg33_N6 (EXP-20261016-10)",
        "baseline": "eq2_N6 live 近績質素分 (EXP-20261016-06)",
        "engine_commit": commit,
        "valid_from": VALID_FROM,
        "min_race_days": MIN_RACE_DAYS,
        "one_look": True,
        "mode": "fixed_rule",
        "primary": list(PRIMARY),
        "ranking_metrics": list(RANKING),
        "bootstrap": {"draws": 2000, "seed": 7, "blocks": 6, "unit": "race day"},
        "rule": "B vs A evaluate_full_record(mode=fixed_rule) verdict PRIMARY_WIN or RANKING_WIN; anything else closes pg33_N6 as REJECT",
        "inputs": "select_prerace_snapshot(platform=au) per meeting; results from Race_Results_Reflector.md",
        "code_sha256": {str(p.relative_to(REPO)): sha256(p) for p in frozen_files()},
        "frozen_at": dt.datetime.now().astimezone().isoformat(),
    }
    freeze["commit_note"] = "engine_commit is the parent of the commit that adds this file; code_sha256 is what is enforced"
    FREEZE.write_text(json.dumps(freeze, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"frozen {len(freeze['code_sha256'])} files at {commit[:8]}")


def cmd_selftest(args) -> None:
    """Wiring only: A must reproduce the production ranks; B must move 近績質素 somewhere. No results read."""
    need_disk()
    picked = [(m, s) for m, s in meetings(args.date, args.date)][:1]
    if not picked:
        sys.exit(f"no meeting with a pre-race snapshot on {args.date}")
    meeting, snap = picked[0]
    for arm in ("A", "B"):
        print(replay(arm, meeting, snap))
    same_prod = moved_fq = top4_changed = races = 0
    for logic in sorted((WORK / "A" / meeting.name).glob("Race_*_Logic.json")):
        prod, a, b = snap / logic.name, logic, WORK / "B" / meeting.name / logic.name
        races += 1
        same_prod += ranked(prod, set()) == ranked(a, set())
        top4_changed += ranked(a, set())[:4] != ranked(b, set())[:4]
        ha = json.loads(a.read_text())["horses"]
        hb = json.loads(b.read_text())["horses"]
        moved_fq += sum(1 for n in ha if (ha[n].get("_data") or {}).get("form_quality_raw")
                        != (hb.get(n, {}).get("_data") or {}).get("form_quality_raw"))
    print(json.dumps({"meeting": meeting.name, "races": races, "A_matches_production_ranks": same_prod,
                      "runners_with_changed_form_quality": moved_fq, "races_top4_changed": top4_changed},
                     ensure_ascii=False))
    for arm in ("A", "B"):
        shutil.rmtree(WORK / arm / meeting.name, ignore_errors=True)


def cmd_status(_args) -> None:
    from unified_reflector_core import load_structured_results
    days, races = set(), 0
    for meeting, _snap in meetings(VALID_FROM):
        try:
            res = load_structured_results("au", meeting / "Race_Results_Reflector.md")
        except Exception:  # noqa: BLE001 — an unreadable results file is counted as not eligible
            continue
        n = sum(1 for info in res.values() if len(info.get("results") or []) >= 3)
        if n:
            days.add(meeting.name[:10])
            races += n
    print(f"valid_from {VALID_FROM}: {len(days)} race days / {races} races eligible "
          f"(evaluate opens at {MIN_RACE_DAYS} days){' — READY' if len(days) >= MIN_RACE_DAYS else ''}")


def cmd_evaluate(args) -> None:
    from eval_metrics import race_metrics
    from model_evaluation_decision import evaluate_full_record
    from unified_reflector_core import load_structured_results

    freeze = verify_freeze()
    if RESULT.exists():
        sys.exit("result.json exists: this family has already been opened once")
    need_disk()
    plan = meetings(freeze["valid_from"])
    days = sorted({m.name[:10] for m, _s in plan})
    if len(days) < freeze["min_race_days"]:
        sys.exit(f"only {len(days)} race days; evaluate opens at {freeze['min_race_days']}")
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        runs = list(ex.map(lambda j: replay(*j), [(arm, m, s) for m, s in plan for arm in ("A", "B")]))
    failed = {name for _arm, name, rc in runs if rc}

    dates, base, cand, flops = [], [], [], {"A": 0, "B": 0}
    for meeting, _snap in plan:
        if meeting.name in failed:
            continue
        results = load_structured_results("au", meeting / "Race_Results_Reflector.md")
        for race, info in sorted(results.items()):
            rows = info.get("results") or []
            a_path = WORK / "A" / meeting.name / f"Race_{race}_Logic.json"
            b_path = WORK / "B" / meeting.name / f"Race_{race}_Logic.json"
            if len(rows) < 3 or not (a_path.exists() and b_path.exists()):
                continue
            drop = set(info.get("scratched_horse_numbers") or [])
            pos = {r["horse_no"]: int(r["placing"]) for r in rows if str(r.get("placing", "")).isdigit()}
            sp = {}
            for r in rows:
                try:
                    sp[r["horse_no"]] = float(str(r.get("odds") or "").replace("$", ""))
                except ValueError:
                    pass
            top3 = {h for h, p in pos.items() if p <= 3}
            pair = []
            for arm, path in (("A", a_path), ("B", b_path)):
                picks = [n for n in ranked(path, drop) if n in pos]
                m = race_metrics(picks, top3, actual_pos=pos)
                row = {k: m[k] for k in PRIMARY + RANKING[:3]}
                row["mean_top3_model_rank"] = m["top3_mean_model_rank"]
                pair.append(row)
                # secondary, report only: a top-2 pick at SP $15+ finishing in the last third
                flops[arm] += sum(1 for n in picks[:2]
                                  if sp.get(n, 0) >= 15 and pos[n] > len(pos) - len(pos) // 3)
            dates.append(meeting.name[:10])
            base.append(pair[0])
            cand.append(pair[1])

    verdict = evaluate_full_record(domain="au", mode="fixed_rule", dates=dates, baseline_rows=base,
                                   candidate_rows=cand, leakage_audit_passed=True, ranking_metrics=RANKING)
    out = {"experiment": freeze["experiment"], "opened_at": dt.datetime.now().astimezone().isoformat(),
           "race_days": len(set(dates)), "races": len(dates), "failed_meetings": sorted(failed),
           "window": [min(dates), max(dates)] if dates else None,
           "secondary_top2_longshot_flops": flops, "verdict": verdict,
           "pass": verdict.get("verdict") in ("PRIMARY_WIN", "RANKING_WIN")}
    RESULT.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str)[:6000])


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "_arm-b":
        run_arm_b(sys.argv[2])
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    st = sub.add_parser("selftest")
    st.add_argument("--date", required=True, help="an already-seen date before valid_from")
    sub.add_parser("status")
    ev = sub.add_parser("evaluate")
    ev.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    {"freeze": cmd_freeze, "selftest": cmd_selftest, "status": cmd_status, "evaluate": cmd_evaluate}[args.cmd](args)


if __name__ == "__main__":
    main()
