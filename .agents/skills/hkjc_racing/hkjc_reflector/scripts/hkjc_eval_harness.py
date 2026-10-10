#!/usr/bin/env python3
"""HKJC unified evaluation harness — one replay path, one split, one verdict.

Why this exists (2026-10-10 audit):
  * `rescore_backtest.rescore_logic` applies SIP but **not** the whole-field
    race_shape cap that went live on 2026-10-08, and ranks on the display score
    — so every replay measured a model that is not production.
  * `pit_backtest` only prints aggregate percentages, so no candidate could get
    a paired Stage 4 v2 verdict.
  * ~20 patch harnesses each re-implemented the split slightly differently.

This harness scores every archived race through the **real** orchestrator
`score_race` (writes disabled, profile network enrichment disabled) after
injecting point-in-time jockey/trainer priors (`pit_backtest.inject_as_of`).

Two sub-commands:

  run      replay one arm, write one JSON line per race
  compare  pair two run files → Stage 4 v2 verdict + cohort / meeting tables

An *arm* is an optional Python file exposing ``apply()``; it monkeypatches the
engine before scoring.  Running each arm in its own process keeps arms isolated.

    PYTHONDONTWRITEBYTECODE=1 python3 hkjc_eval_harness.py run --out base.jsonl
    PYTHONDONTWRITEBYTECODE=1 python3 hkjc_eval_harness.py run --arm my_arm.py --out cand.jsonl
    python3 hkjc_eval_harness.py compare base.jsonl cand.jsonl --leakage-audit-passed
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import math
import os
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
REPO = SCRIPTS.parents[4]
AUTO_SCRIPTS = REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"
SHARED = REPO / ".agents/skills/shared_racing"
for path in (SCRIPTS, AUTO_SCRIPTS, REPO, SHARED):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

MEETING_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(ShaTin|HappyValley)$")
RANKING_METRICS = ("top3_capture_at5", "ndcg_at5", "competitive_recall_at5", "mean_top3_model_rank")


def _default_root() -> Path:
    import wongchoi_paths

    return Path(wongchoi_paths.HK_RACING)


def discover_meetings(root: Path, since: str | None = None, until: str | None = None) -> list[Path]:
    out = []
    for path in sorted(root.iterdir()):
        match = MEETING_RE.match(path.name)
        if not match or not path.is_dir():
            continue
        day = match.group(1)
        if since and day < since or until and day > until:
            continue
        if not list(path.glob("Race_*_Logic.json")) or not list(path.glob("*全日賽果.json")):
            continue
        out.append(path)
    return out


def _load_arm(path: str | None):
    if not path:
        return "baseline"
    spec = importlib.util.spec_from_file_location("hkjc_eval_arm", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.apply()
    return getattr(module, "ARM_NAME", Path(path).stem)


def _race_context(logic: dict) -> dict:
    ctx = logic.get("race_analysis") or {}
    track = str(ctx.get("track") or ctx.get("surface") or "")
    distance = re.search(r"\d{3,4}", str(ctx.get("distance") or ""))
    return {
        "venue": str(ctx.get("venue") or ""),
        "awt": "全天候" in track or "AWT" in track.upper(),
        "distance": int(distance.group()) if distance else None,
    }


def _ranking(logic: dict) -> list[int]:
    rows = []
    for number, horse in (logic.get("horses") or {}).items():
        auto = horse.get("python_auto") if isinstance(horse, dict) else None
        if not isinstance(auto, dict):
            continue
        try:
            rows.append((-float(auto.get("ability_score_raw", auto.get("ability_score"))), int(number)))
        except (TypeError, ValueError):
            continue
    return [number for _score, number in sorted(rows)]


def _meeting_dead_fields(rows: list[dict]) -> list[str]:
    """Leaves whose within-race spread is 0 in every race of the meeting."""
    spreads = defaultdict(list)
    for row in rows:
        for key, values in row.get("_leaf_values", {}).items():
            if len(values) > 1:
                spreads[key].append(statistics.pstdev(values))
    return sorted(key for key, values in spreads.items() if values and max(values) == 0.0)


def run(args) -> int:
    os.environ.setdefault("WC_DISABLE_HKJC_PROFILE_ENRICH", "1")
    os.environ.setdefault("WC_DISABLE_POST_SUCCESS_DEPLOY", "1")
    arm_name = _load_arm(args.arm)

    import hkjc_auto_orchestrator as orch
    import pit_backtest
    import rescore_backtest
    from eval_metrics import race_metrics

    orch._atomic_write_json = lambda *a, **k: None
    orch.write_prepared_race_outputs = lambda *a, **k: (Path("replay.md"), Path("replay.csv"))
    orch.HKJCAutoOrchestrator._emit_event = lambda *a, **k: None

    root = Path(args.meeting_root) if args.meeting_root else _default_root()
    meetings = discover_meetings(root, args.since, args.until)
    all_rows = None if args.no_pit else pit_backtest.load_all_rows()
    out = open(args.out, "w", encoding="utf-8")
    written = 0
    for md in meetings:
        day = MEETING_RE.match(md.name).group(1)
        if all_rows is not None:
            pit_backtest.inject_as_of(all_rows, day)
        actual = rescore_backtest.load_results(rescore_backtest.find_results_json(md))
        orchestrator = orch.HKJCAutoOrchestrator(md)
        meeting_rows = []
        for race_file in sorted(md.glob("Race_*_Logic.json"), key=rescore_backtest.race_num_from_path):
            race_no = rescore_backtest.race_num_from_path(race_file)
            if race_no not in actual:
                continue
            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    logic = orchestrator.score_race(race_file)
            except Exception as exc:  # recorded per race; both arms drop the same race
                meeting_rows.append({"meeting": md.name, "race": race_no,
                                     "error": f"{type(exc).__name__}: {exc}"[:300]})
                continue
            if not logic:
                meeting_rows.append({"meeting": md.name, "race": race_no, "error": "score_race_failed"})
                continue
            positions = actual[race_no]
            picks = _ranking(logic)
            metrics = race_metrics(
                picks,
                [h for h, p in positions.items() if p <= 3],
                actual_pos=positions,
            )
            metrics["mean_top3_model_rank"] = metrics.get("top3_mean_model_rank")
            leaf_values = defaultdict(list)
            for horse in (logic.get("horses") or {}).values():
                auto = horse.get("python_auto") or {}
                for block in ("feature_scores", "derived_feature_scores"):
                    for key, value in (auto.get(block) or {}).items():
                        if isinstance(value, (int, float)):
                            leaf_values[key].append(float(value))
            dump = None
            if args.dump_matrix:
                dump = []
                for number, horse in (logic.get("horses") or {}).items():
                    auto = horse.get("python_auto") if isinstance(horse, dict) else None
                    if not isinstance(auto, dict) or not isinstance(auto.get("matrix_scores"), dict):
                        continue
                    try:
                        dump.append({
                            "n": int(number),
                            "pos": positions.get(int(number)),
                            "raw": float(auto.get("ability_score_raw")),
                            "debut": any("debut" in str(c).lower() for c in auto.get("reason_codes") or []),
                            "m": {k: float(v) for k, v in auto["matrix_scores"].items()},
                        })
                    except (TypeError, ValueError):
                        continue
            row = {
                "arm": arm_name,
                "date": day,
                "meeting": md.name,
                "race": race_no,
                **_race_context(logic),
                "field": len(positions),
                "picks": picks,
                **{k: metrics.get(k) for k in ("gold", "gold_strict", "good_positional", "champion", *RANKING_METRICS)},
                "_leaf_values": leaf_values,
            }
            if dump is not None:
                row["horses"] = dump
            meeting_rows.append(row)
        dead = _meeting_dead_fields([r for r in meeting_rows if "error" not in r])
        for row in meeting_rows:
            row.pop("_leaf_values", None)
            row["meeting_dead_fields"] = dead
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            written += 1
        print(f"{md.name}: {len(meeting_rows)} races  dead={dead or '-'}", file=sys.stderr)
    out.close()
    print(f"wrote {written} rows → {args.out}", file=sys.stderr)
    return 0


def _read(path: str) -> dict:
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if "error" in row:
            continue
        rows[(row["meeting"], row["race"])] = row
    return rows


def _excluded(row: dict, exclude_dead: set[str]) -> bool:
    return bool(exclude_dead.intersection(row.get("meeting_dead_fields") or []))


def compare(args) -> int:
    from model_evaluation_decision import build_evaluation_input, evaluate_candidate, evaluate_full_record

    base, cand = _read(args.baseline), _read(args.candidate)
    exclude = set(args.exclude_dead or ())
    keys = sorted(
        k for k in base.keys() & cand.keys()
        if not _excluded(base[k], exclude) and not _excluded(cand[k], exclude)
    )
    dropped = len(base.keys() ^ cand.keys())
    dates = [base[k]["date"] for k in keys]
    b_rows = [base[k] for k in keys]
    c_rows = [cand[k] for k in keys]
    evaluation = build_evaluation_input(
        domain="hkjc",
        dates=dates,
        baseline_rows=b_rows,
        candidate_rows=c_rows,
        leakage_audit_passed=args.leakage_audit_passed,
        ranking_metrics=RANKING_METRICS,
    )
    if args.stage4 == "v2":
        verdict = evaluate_candidate(evaluation)
    else:
        # Stage 4 v3 (docs/model-evaluation-contract.md): full record.
        verdict = evaluate_full_record(
            domain="hkjc", mode=args.stage4, dates=dates,
            baseline_rows=b_rows, candidate_rows=c_rows,
            leakage_audit_passed=args.leakage_audit_passed,
            ranking_metrics=RANKING_METRICS,
        )

    def rate(rows, key):
        values = [bool(r[key]) for r in rows if r.get(key) is not None]
        return 100.0 * sum(values) / len(values) if values else float("nan")

    def meeting_sd(rows):
        by = defaultdict(list)
        for r in rows:
            by[r["meeting"]].append(bool(r["good_positional"]))
        per = [sum(v) / len(v) for v in by.values() if v]
        return statistics.pstdev(per) if len(per) > 1 else float("nan")

    cohorts = {
        "all": lambda r: True,
        "沙田草地": lambda r: r["venue"].startswith("沙田") and not r["awt"],
        "沙田泥地": lambda r: r["awt"],
        "跑馬地": lambda r: r["venue"].startswith("跑馬地"),
        "直路1000": lambda r: r["venue"].startswith("沙田") and not r["awt"] and r["distance"] == 1000,
        "今季(26/27)": lambda r: r["date"] >= "2026-08-01",
    }
    changed = sum(1 for b, c in zip(b_rows, c_rows) if b["picks"] != c["picks"])
    report = {
        "races": len(keys),
        "excluded_dead_or_unpaired": dropped + (len(base) - len(keys) - dropped if exclude else 0),
        "races_with_ranking_change": changed,
        "sample_hash": evaluation.baseline_sample_hash,
        "verdict": verdict,
        "primary": {k: vars(v) for k, v in evaluation.primary.items()},
        "ranking": {k: vars(v) for k, v in evaluation.ranking.items()},
        "meeting_good_sd": {"baseline": meeting_sd(b_rows), "candidate": meeting_sd(c_rows)},
        "cohorts": {},
    }
    for name, pred in cohorts.items():
        idx = [i for i, r in enumerate(b_rows) if pred(r)]
        if not idx:
            continue
        sub_b = [b_rows[i] for i in idx]
        sub_c = [c_rows[i] for i in idx]
        report["cohorts"][name] = {
            "races": len(idx),
            **{f"{m}_delta_pp": round(rate(sub_c, m) - rate(sub_b, m), 2) for m in ("gold", "good_positional", "champion")},
        }
    text = json.dumps(report, ensure_ascii=False, indent=2, default=lambda o: None if isinstance(o, float) and math.isnan(o) else o)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arm", help="Python file with apply(); omit for production baseline")
    r.add_argument("--meeting-root")
    r.add_argument("--since")
    r.add_argument("--until")
    r.add_argument("--out", required=True)
    r.add_argument("--dump-matrix", action="store_true",
                   help="Also write every horse's raw matrix scores (for offline weight studies)")
    r.add_argument("--no-pit", action="store_true",
                   help="Use live priors (faithfulness check only — has lookahead)")
    c = sub.add_parser("compare")
    c.add_argument("baseline")
    c.add_argument("candidate")
    c.add_argument("--leakage-audit-passed", action="store_true")
    c.add_argument("--stage4", choices=("fixed_rule", "walk_forward_oos", "v2"), required=True,
                   help="v3 fixed_rule = nothing learned from this data (full record); "
                        "walk_forward_oos = fitted candidate scored from walk-forward predictions; "
                        "v2 = legacy 15%% terminal tail")
    c.add_argument("--exclude-dead", action="append", default=["speed_score"],
                   help="Drop meetings where this leaf is dead (default: speed_score)")
    c.add_argument("--out")
    args = parser.parse_args(argv)
    return run(args) if args.command == "run" else compare(args)


if __name__ == "__main__":
    raise SystemExit(main())
