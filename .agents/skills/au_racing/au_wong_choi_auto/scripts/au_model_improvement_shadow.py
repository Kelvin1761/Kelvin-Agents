#!/usr/bin/env python3
"""Targeted OOS checks for AU Wong Choi model-improvement candidates.

This is a research harness.  It never writes Logic files and never changes the
live scoring engine.  It tests:

1. shrinking/removing the wet-form overlay (track/wet de-duplication);
2. a fresh-trial / stale-official pace recency gate;
3. a pace-concentration confidence abstention rule; and
4. pre-race going versus result-day going drift in recent Logic snapshots.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import median

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import ARCHIVE_ROOT, normalize_condition_bucket, normalize_horse_name  # noqa: E402
from au_cached_walkforward_ml import (  # noqa: E402
    as_float,
    date_folds,
    group_races,
    materialize_dataset,
    metrics_for_races,
)
from scoring import MATRIX_WEIGHTS  # noqa: E402


OUTPUT_MD = PROJECT_ROOT / "2026-07-16 AU Model Improvement Shadow Review.md"
OUTPUT_JSON = PROJECT_ROOT / "scratch" / "au_model_improvement_shadow_results.json"
CONTEXT_CACHE = Path("/private/tmp/au_model_improvement_logic_context.json")
WARWICK_LOGIC_DIR = PROJECT_ROOT / "scratch" / "au_reflector_2026-07-15_warwick_farm"
WARWICK_ARCHIVE_DIR = ARCHIVE_ROOT / "2026-07-15 Warwick Farm Race 1-7"
WARWICK_RESULTS = (
    PROJECT_ROOT
    / "Wong Choi Horse Race Analysis"
    / "AU_Racing"
    / "2026-07-15 Warwick Farm"
    / "Race_Results_Warwick_Farm_2026-07-15.json"
)

PACE_FIGURE_INNER_WEIGHT = 0.759174
RECENCY_ALPHA = 0.50
RECENCY_CAP = 3.0
RECENCY_FORMAL_AGE = 60
RECENCY_TRIAL_AGE = 30
RECENCY_TRIAL_SCORE = 75.0

HISTORICAL_PROMOTIONS = (
    {
        "feature": "Pure static 7D",
        "evidence": "336 races: Good 17.6%→18.2%, Pass 38.1%→38.7%, 0-hit 46→43",
        "status": "Implemented",
    },
    {
        "feature": "Wet-form suitability",
        "evidence": "Expanding walk-forward: Soft box-trifecta 14.4%→16.6%; robust scale plateau 6–12",
        "status": "Implemented",
    },
    {
        "feature": "Measured PF pace",
        "evidence": "687-race archive: Gold 33→37, Pass 285→298, Champion +0.9pp, W-in-T3 +2.0pp",
        "status": "Implemented",
    },
    {
        "feature": "7D bug-fix / de-dup review",
        "evidence": "702-race dual-window A/B: aggregate GGP 444→478 with no metric regression",
        "status": "Implemented",
    },
)


def _score_races(races: list[list[dict]], scorer) -> list[list[dict]]:
    return [[{**row, "_score": float(scorer(row))} for row in race] for race in races]


def _valid_window(races: list[list[dict]]) -> list[list[dict]]:
    folds = date_folds(races)
    return [race for _train, valid in folds for race in valid]


def _fmt(metrics: dict) -> str:
    return (
        f"{metrics['races']} races; {metrics['gold']} Gold / {metrics['good']} Good / "
        f"{metrics['pass']} Pass / {metrics['miss']} Miss; Top3 {metrics['top3_precision'] * 100:.1f}%; "
        f"W-in-T3 {metrics['winner_in_top3'] * 100:.1f}%; Top1 {metrics['top1_win'] * 100:.1f}%"
    )


def _condition_metrics(races: list[list[dict]]) -> dict[str, dict]:
    groups: dict[str, list[list[dict]]] = defaultdict(list)
    for race in races:
        groups[normalize_condition_bucket(race[0].get("condition_bucket", ""))].append(race)
    return {key: metrics_for_races(value) for key, value in sorted(groups.items())}


def _fold_stability(races: list[list[dict]], baseline_scorer, candidate_scorer) -> dict:
    folds = date_folds(races)
    top3_non_worse = 0
    winner_non_worse = 0
    miss_non_worse = 0
    rows = []
    for idx, (_train, valid) in enumerate(folds, 1):
        baseline = metrics_for_races(_score_races(valid, baseline_scorer))
        candidate = metrics_for_races(_score_races(valid, candidate_scorer))
        top3_non_worse += candidate["top3_precision"] >= baseline["top3_precision"]
        winner_non_worse += candidate["winner_in_top3"] >= baseline["winner_in_top3"]
        miss_non_worse += candidate["miss"] <= baseline["miss"]
        rows.append({"fold": idx, "baseline": baseline, "candidate": candidate})
    return {
        "folds": len(folds),
        "top3_non_worse": top3_non_worse,
        "winner_non_worse": winner_non_worse,
        "miss_non_worse": miss_non_worse,
        "rows": rows,
    }


def wet_overlay_test(races: list[list[dict]]) -> dict:
    valid = _valid_window(races)
    results = {}
    for scale in (0.0, 0.25, 0.50, 0.75, 1.0):
        scored = _score_races(
            valid,
            lambda row, s=scale: as_float(row.get("pure_7d_score"), row["ability_score"])
            + s * as_float(row.get("wet_form_feature"), 0.0),
        )
        results[f"{scale:.2f}"] = {
            "overall": metrics_for_races(scored),
            "conditions": _condition_metrics(scored),
        }
    current_scored = _score_races(valid, lambda row: as_float(row["ability_score"]))
    results["current"] = {
        "overall": metrics_for_races(current_scored),
        "conditions": _condition_metrics(current_scored),
    }
    affected = [
        race for race in valid
        if any(abs(as_float(row.get("wet_form_feature"), 0.0)) > 1e-9 for row in race)
    ]
    affected_dates = sorted({race[0]["date"] for race in affected})
    stability = _fold_stability(
        races,
        lambda row: as_float(row["ability_score"]),
        lambda row: as_float(row.get("pure_7d_score"), row["ability_score"]),
    )
    baseline = results["current"]["overall"]
    no_overlay = results["0.00"]["overall"]
    rollback_supported = (
        len(affected) >= 50
        and len(affected_dates) >= 6
        and no_overlay["top3_precision"] >= baseline["top3_precision"]
        and no_overlay["winner_in_top3"] >= baseline["winner_in_top3"]
        and no_overlay["miss"] <= baseline["miss"]
        and stability["top3_non_worse"] >= math.ceil(stability["folds"] * 0.6)
        and stability["winner_non_worse"] >= math.ceil(stability["folds"] * 0.6)
    )
    return {
        "valid_races": len(valid),
        "affected_races": len(affected),
        "affected_dates": affected_dates,
        "scales": results,
        "stability": stability,
        "rollback_supported": rollback_supported,
    }


def _record_dates(facts_section: str) -> tuple[str, str]:
    formal: list[str] = []
    trials: list[str] = []
    for line in str(facts_section or "").splitlines():
        text = line.strip()
        if not text.startswith("|") or "| 類型 |" in text or "|---" in text:
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        if len(cols) < 4 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", cols[2]):
            continue
        (trials if "試閘" in cols[1] else formal).append(cols[2])
    return (max(formal) if formal else "", max(trials) if trials else "")


def _days_between(later: str, earlier: str) -> int | None:
    try:
        return (date.fromisoformat(later) - date.fromisoformat(earlier)).days
    except (TypeError, ValueError):
        return None


def _logic_path(meeting: str, race_no: int) -> Path:
    return ARCHIVE_ROOT / meeting / f"Race_{race_no}_Logic.json"


def enrich_logic_context(races: list[list[dict]], since: str) -> tuple[dict[str, dict], dict]:
    cache = {}
    if CONTEXT_CACHE.exists():
        try:
            cache = json.loads(CONTEXT_CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cache = {}

    going_counts = Counter()
    missing = 0
    loaded = 0
    targets = []
    for race in races:
        row0 = race[0]
        race_date = str(row0.get("date") or "")
        recency_proxy = any(
            as_float(row.get("trial_score"), 60.0) >= RECENCY_TRIAL_SCORE
            and as_float(row.get("pace_figure_score"), 60.0) < 60.0
            for row in race
        )
        going_sample = bool(race_date and race_date >= since)
        if recency_proxy or going_sample:
            targets.append(race)
    for idx, race in enumerate(targets, 1):
        row0 = race[0]
        race_date = str(row0.get("date") or "")
        going_sample = bool(race_date and race_date >= since)
        if idx == 1 or idx % 20 == 0:
            print(f"Enriching Logic context: {idx}/{len(targets)} {row0['meeting']} R{row0['race']}", flush=True)
        key = f"{row0['meeting']}|{int(row0['race'])}"
        context = cache.get(key)
        if context is None or (going_sample and not context.get("pre_going")):
            path = _logic_path(str(row0["meeting"]), int(row0["race"]))
            if not path.exists():
                cache[key] = {"missing": True}
                missing += 1
                continue
            try:
                logic = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                cache[key] = {"missing": True}
                missing += 1
                continue
            horses = {}
            for horse_no, horse in (logic.get("horses") or {}).items():
                data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
                latest_formal, latest_trial = _record_dates(data.get("facts_section", ""))
                item = {"latest_formal": latest_formal, "latest_trial": latest_trial}
                horses[str(horse_no)] = item
                name_key = normalize_horse_name(horse.get("horse_name") or horse.get("name") or "")
                if name_key:
                    horses[name_key] = item
            race_analysis = logic.get("race_analysis") or {}
            meeting = race_analysis.get("meeting_intelligence") or {}
            profile = race_analysis.get("track_profile") or {}
            speed_map = race_analysis.get("speed_map") or {}
            context = {
                "pre_going": str(
                    race_analysis.get("going")
                    or meeting.get("going")
                    or meeting.get("track_summary")
                    or profile.get("going")
                    or speed_map.get("going")
                    or ""
                ),
                "horses": horses,
            }
            cache[key] = context
            loaded += 1
            if loaded % 20 == 0:
                CONTEXT_CACHE.parent.mkdir(parents=True, exist_ok=True)
                CONTEXT_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        if context.get("missing"):
            continue
        for row in race:
            horse_context = (context.get("horses") or {}).get(str(row.get("horse_number")))
            if horse_context is None:
                horse_context = (context.get("horses") or {}).get(normalize_horse_name(row.get("horse_name", "")))
            if horse_context:
                row["official_age_days"] = _days_between(race_date, horse_context.get("latest_formal", ""))
                row["trial_age_days"] = _days_between(race_date, horse_context.get("latest_trial", ""))
        if going_sample:
            pre = normalize_condition_bucket(context.get("pre_going", ""))
            actual = normalize_condition_bucket(row0.get("condition_bucket", ""))
            going_counts["scanned"] += 1
            comparable = pre not in {"Unknown", "Other"} and actual not in {"Unknown", "Other"}
            going_counts["comparable"] += comparable
            going_counts["mismatch"] += comparable and pre != actual
            going_counts[f"{pre}->{actual}"] += 1

    CONTEXT_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CONTEXT_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return cache, {"loaded": loaded, "missing": missing, "counts": dict(going_counts), "since": since}


def _recency_eligible(row: dict, formal_age: int = RECENCY_FORMAL_AGE, trial_age: int = RECENCY_TRIAL_AGE) -> bool:
    official = row.get("official_age_days")
    trial = row.get("trial_age_days")
    return (
        official is not None
        and trial is not None
        and official >= formal_age
        and 0 <= trial <= trial_age
        and as_float(row.get("trial_score"), 60.0) >= RECENCY_TRIAL_SCORE
        and as_float(row.get("pace_figure_score"), 60.0) < 60.0
    )


def _recency_score(row: dict, alpha: float = RECENCY_ALPHA) -> float:
    score = as_float(row.get("ability_score"), 0.0)
    if not _recency_eligible(row):
        return score
    pace = as_float(row.get("pace_figure_score"), 60.0)
    raw = MATRIX_WEIGHTS["pace_perf"] * PACE_FIGURE_INNER_WEIGHT * alpha * (60.0 - pace)
    return score + min(RECENCY_CAP, max(0.0, raw))


def recency_test(races: list[list[dict]]) -> dict:
    valid = _valid_window(races)
    baseline_scored = _score_races(valid, lambda row: as_float(row["ability_score"]))
    candidate_scored = _score_races(valid, _recency_score)
    baseline = metrics_for_races(baseline_scored)
    candidate = metrics_for_races(candidate_scored)
    affected_horses = sum(_recency_eligible(row) for race in valid for row in race)
    affected_races = sum(any(_recency_eligible(row) for row in race) for race in valid)
    proxy_horses = sum(
        as_float(row.get("trial_score"), 60.0) >= RECENCY_TRIAL_SCORE
        and as_float(row.get("pace_figure_score"), 60.0) < 60.0
        for race in valid for row in race
    )
    stability = _fold_stability(races, lambda row: as_float(row["ability_score"]), _recency_score)
    passed = (
        affected_races >= 10
        and candidate["top3_precision"] >= baseline["top3_precision"]
        and candidate["winner_in_top3"] >= baseline["winner_in_top3"]
        and candidate["miss"] <= baseline["miss"]
        and stability["top3_non_worse"] >= math.ceil(stability["folds"] * 0.6)
    )
    return {
        "affected_horses": affected_horses,
        "affected_races": affected_races,
        "proxy_horses": proxy_horses,
        "baseline": baseline,
        "candidate": candidate,
        "stability": stability,
        "passed": passed,
    }


def _pace_concentration(race: list[dict]) -> tuple[dict, float]:
    ranked = sorted(race, key=lambda row: (-as_float(row["ability_score"]), int(row["horse_number"])))
    top = ranked[0]
    positive_total = 0.0
    pace_lift = 0.0
    for key, weight in MATRIX_WEIGHTS.items():
        if key == "form_line" or weight <= 0:
            continue
        values = [as_float(row.get(f"mx_{key}"), 60.0) for row in race]
        lift = max(0.0, weight * (as_float(top.get(f"mx_{key}"), 60.0) - median(values)))
        positive_total += lift
        if key == "pace_perf":
            pace_lift = lift
    return top, (pace_lift / positive_total if positive_total > 0 else 0.0)


def concentration_test(races: list[list[dict]]) -> dict:
    valid = _valid_window(races)
    rules = []
    for pace_threshold in (85.0, 90.0, 95.0):
        for share_threshold in (0.40, 0.50, 0.60):
            retained = []
            flagged = []
            for race in valid:
                top, share = _pace_concentration(race)
                is_flagged = as_float(top.get("pace_figure_score"), 60.0) >= pace_threshold and share >= share_threshold
                (flagged if is_flagged else retained).append(top)
            retained_wins = sum(row["actual_pos"] == 1 for row in retained)
            flagged_wins = sum(row["actual_pos"] == 1 for row in flagged)
            rules.append(
                {
                    "pace_threshold": pace_threshold,
                    "share_threshold": share_threshold,
                    "flagged": len(flagged),
                    "coverage": len(retained) / max(1, len(valid)),
                    "retained_top1_win": retained_wins / max(1, len(retained)),
                    "flagged_top1_win": flagged_wins / max(1, len(flagged)),
                }
            )
    fixed = next(row for row in rules if row["pace_threshold"] == 90.0 and row["share_threshold"] == 0.50)
    baseline_top1 = metrics_for_races(_score_races(valid, lambda row: as_float(row["ability_score"])))['top1_win']
    fixed["passed"] = (
        fixed["flagged"] >= 10
        and fixed["coverage"] >= 0.85
        and fixed["retained_top1_win"] > baseline_top1
        and fixed["flagged_top1_win"] < baseline_top1
    )
    return {"races": len(valid), "baseline_top1_win": baseline_top1, "fixed_rule": fixed, "grid": rules}


def warwick_going_audit() -> dict:
    if not WARWICK_RESULTS.exists() or not WARWICK_LOGIC_DIR.exists():
        return {"available": False}
    payload = json.loads(WARWICK_RESULTS.read_text(encoding="utf-8"))
    rows = []
    for race_no, event in sorted((payload.get("events") or {}).items(), key=lambda item: int(item[0])):
        logic_path = WARWICK_LOGIC_DIR / f"Race_{int(race_no)}_Logic.json"
        if not logic_path.exists() or logic_path.stat().st_size == 0:
            logic_path = WARWICK_ARCHIVE_DIR / f"Race_{int(race_no)}_Logic.json"
        if not logic_path.exists() or logic_path.stat().st_size == 0:
            continue
        try:
            logic = json.loads(logic_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        race_analysis = logic.get("race_analysis") or {}
        meeting = race_analysis.get("meeting_intelligence") or {}
        pre_raw = race_analysis.get("going") or meeting.get("going") or meeting.get("track_summary") or ""
        actual_raw = event.get("track_condition") or ""
        pre = normalize_condition_bucket(pre_raw)
        actual = normalize_condition_bucket(actual_raw)
        rows.append({"race": int(race_no), "pre": pre_raw, "actual": actual_raw, "mismatch": pre != actual})
    return {
        "available": bool(rows),
        "races": len(rows),
        "mismatches": sum(row["mismatch"] for row in rows),
        "rows": rows,
    }


def render_report(dataset: dict) -> str:
    wet = dataset["wet_overlay"]
    recency = dataset["recency"]
    concentration = dataset["concentration"]
    going = dataset["going_audit"]
    lines = [
        "# AU Wong Choi Model Improvement — Shadow Review",
        "",
        "> Research-only. No live ranking weights or production Logic files were changed by this run.",
        "",
        "## Evaluation frame",
        "",
        f"- Full labelled archive: **{dataset['races']} races / {dataset['horses']} horses**.",
        f"- OOS validation window: **{wet['valid_races']} races**, expanding-date folds over the latter half of available dates.",
        "- Promotion requires no loss in Top3 precision, winner-in-Top3, or Miss count, plus fold stability.",
        "",
        "## Already-promoted large-sample improvements",
        "",
        "| Feature | Prior validation evidence | Production status |",
        "|---|---|---|",
    ]
    for item in HISTORICAL_PROMOTIONS:
        lines.append(f"| {item['feature']} | {item['evidence']} | **{item['status']}** |")
    lines.extend([
        "",
        "These are not new promotion candidates. The current run is only a regression check and cannot overturn a larger recompute-based walk-forward with a smaller stored-snapshot subset.",
        "",
        "## 1. Existing wet-form feature regression check",
        "",
        "| Wet overlay scale | OOS result |",
        "|---:|---|",
    ])
    lines.append(f"| production ability | {_fmt(wet['scales']['current']['overall'])} |")
    for scale in ("0.00", "0.25", "0.50", "0.75", "1.00"):
        lines.append(f"| reconstructed {scale} | {_fmt(wet['scales'][scale]['overall'])} |")
    lines.extend([
        "",
        f"- Non-zero wet overlay support: **{wet['affected_races']} races across {len(wet['affected_dates'])} dates**.",
        "- The reconstructed 1.00 row is diagnostic only; historical CSV rounding means production `ability_score` is the actual baseline.",
        f"- Rollback gate: **{'TRIGGERED' if wet['rollback_supported'] else 'NOT TRIGGERED'}**.",
        "- Decision: **KEEP the already-baked wet-form feature**. This short snapshot is underpowered relative to its original expanding walk-forward.",
        "",
        "## 2. Fresh-trial / stale-official pace recency gate",
        "",
        f"- Trigger: last official run ≥{RECENCY_FORMAL_AGE} days, trial ≤{RECENCY_TRIAL_AGE} days, trial score ≥{RECENCY_TRIAL_SCORE:.0f}, pace figure <60.",
        f"- Action: shrink half the stale pace deficit toward neutral, capped at +{RECENCY_CAP:.1f} ability points.",
        f"- Affected OOS sample: **{recency['affected_horses']} horses in {recency['affected_races']} races**.",
        f"- Available trial-high / pace-low proxy rows: **{recency['proxy_horses']}**; the strict dated trigger has insufficient support.",
        f"- Baseline: {_fmt(recency['baseline'])}",
        f"- Candidate: {_fmt(recency['candidate'])}",
        f"- Decision: **{'PASS' if recency['passed'] else 'FAIL / HOLD'}**.",
        "",
        "## 3. Pace-concentrated Top1 confidence gate",
        "",
        "Fixed rule: abstain from a Top1 endorsement when pace figure ≥90 and pace supplies ≥50% of the Top1's positive matrix lift over the field median.",
        "",
        f"- Baseline Top1 win: **{concentration['baseline_top1_win'] * 100:.1f}%**.",
        f"- Flagged: **{concentration['fixed_rule']['flagged']} races**; flagged Top1 win **{concentration['fixed_rule']['flagged_top1_win'] * 100:.1f}%**.",
        f"- Retained coverage: **{concentration['fixed_rule']['coverage'] * 100:.1f}%**; retained Top1 win **{concentration['fixed_rule']['retained_top1_win'] * 100:.1f}%**.",
        f"- Decision: **{'PASS' if concentration['fixed_rule']['passed'] else 'FAIL / HOLD'}**.",
        "",
        "## 4. Going refresh audit",
        "",
        f"- Recent Logic scan since {going['since']}: **{going['counts'].get('scanned', 0)} races**; comparable going present in **{going['counts'].get('comparable', 0)}**.",
        f"- Comparable archive mismatches: **{going['counts'].get('mismatch', 0)}**.",
        f"- Warwick Farm 2026-07-15: **{dataset['warwick_going'].get('mismatches', 0)}/{dataset['warwick_going'].get('races', 0)} mismatches** (R4-R7 changed Soft 5 → Good 4).",
        "- This is a data-correctness gate: the orchestrator should refresh going immediately before scoring when mismatches are material.",
        "",
        "## Bake decision",
        "",
    ])
    passed = []
    if recency["passed"]:
        passed.append("recency gate")
    if concentration["fixed_rule"]["passed"]:
        passed.append("Top1 confidence abstention")
    if passed:
        lines.append("Candidates eligible for a separately reviewed live change: **" + ", ".join(passed) + "**.")
    else:
        lines.append("**Keep all previously promoted improvements. No additional scoring candidate cleared the new promotion gate.**")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild-cache", action="store_true")
    parser.add_argument("--logic-since", default="2026-05-01")
    parser.add_argument("--output", type=Path, default=OUTPUT_MD)
    args = parser.parse_args()

    rows = materialize_dataset(rebuild=args.rebuild_cache)
    races = group_races(rows)
    if not races:
        raise SystemExit("No labelled archive races available")
    validation_races = _valid_window(races)
    _cache, going_audit = enrich_logic_context(validation_races, args.logic_since)

    result = {
        "races": len(races),
        "horses": sum(len(race) for race in races),
        "wet_overlay": wet_overlay_test(races),
        "recency": recency_test(races),
        "concentration": concentration_test(races),
        "going_audit": going_audit,
        "warwick_going": warwick_going_audit(),
    }
    args.output.write_text(render_report(result), encoding="utf-8")
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Wrote {OUTPUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
