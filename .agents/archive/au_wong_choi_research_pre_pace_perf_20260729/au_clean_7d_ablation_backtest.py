#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    iter_logic_rows,
    load_historical_results,
    parse_float,
    parse_int,
)
from au_zero_hit_race_audit import field_size_bucket, race_class_bucket  # noqa: E402
from scoring import MATRIX_WEIGHTS, get_dynamic_matrix_weights, soft_race_shape_modifier  # noqa: E402


OUTPUT_MD = ARCHIVE_ROOT / "AU_Clean_7D_Ablation_Backtest.md"
KENSINGTON_DIR = ARCHIVE_ROOT / "2026-06-10 Kensington Race 1-7"


def pct(n: int | float, d: int | float) -> str:
    return f"{(n / d * 100):.1f}%" if d else "0.0%"


def bucket() -> dict:
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "pass": 0,
        "winner_top3": 0,
        "winner_top5": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": Counter(),
    }


def base_score(row: dict) -> float:
    return float(row.get("model_score") or row.get("rank_score") or row.get("ability_score") or 0.0)


def matrix_score(row: dict, weights: dict) -> float:
    matrix = row.get("matrix_scores") or {}
    return round(sum(float(matrix.get(key, 60.0) or 60.0) * float(weights.get(key, 0.0)) for key in MATRIX_KEYS), 4)


def race_context(rows: list[dict]) -> dict:
    first = rows[0]
    going = str(first.get("condition") or first.get("condition_bucket") or "")
    auto = (first.get("horse") or {}).get("python_auto") or {}
    auto_context = auto.get("race_context") or {}
    return {
        "field_summary": {"count": len(rows)},
        "going": auto_context.get("going") or going,
        "condition": going,
        "race_class": first.get("race_class") or "",
    }


def dynamic_score(row: dict, context: dict) -> float:
    return matrix_score(row, get_dynamic_matrix_weights(context))


def diversity_bonus(row: dict) -> float:
    values = [float((row.get("matrix_scores") or {}).get(key, 60.0) or 60.0) for key in MATRIX_KEYS]
    return 2.0 if values and min(values) >= 56.0 else 0.0


def auto_value(row: dict, key: str, default: float = 0.0) -> float:
    auto = (row.get("horse") or {}).get("python_auto") or {}
    return float(auto.get(key) or default)


def soft_wetproof_cap(matrix: dict, ability_score: float, going: str, going_stats_line: str) -> float:
    if "soft" not in str(going or "").lower():
        return 0.0
    if ability_score < 66.0:
        return 0.0
    track = float(matrix.get("track", 60.0) or 60.0)
    sectional = float(matrix.get("sectional", 60.0) or 60.0)
    stability = float(matrix.get("stability", 60.0) or 60.0)
    race_shape = float(matrix.get("race_shape", 60.0) or 60.0)
    soft_match = None
    for token in str(going_stats_line or "").split("|"):
        if "軟地" in token or "Soft" in token:
            soft_match = token
            break
    exposed_no_wet_place = False
    if soft_match:
        stats = [int(x) for x in __import__("re").findall(r"\d+", soft_match)]
        if len(stats) >= 3:
            starts, wins, seconds = stats[0], stats[1], stats[2]
            thirds = stats[3] if len(stats) > 3 else 0
            exposed_no_wet_place = starts >= 1 and wins + seconds + thirds == 0
    speed_stability_only = (sectional >= 66.0 or stability >= 70.0) and track < 66.0 and race_shape < 66.0
    delta = 0.0
    if exposed_no_wet_place:
        delta -= 0.7
    if track < 66.0:
        delta -= 0.4
    if speed_stability_only:
        delta -= 0.5
    return round(max(-1.4, delta), 4)


def wet_condition_adjustment(matrix: dict, going: str) -> float:
    text = str(going or "").lower()
    stability = float(matrix.get("stability", 60.0) or 60.0)
    sectional = float(matrix.get("sectional", 60.0) or 60.0)
    track = float(matrix.get("track", 60.0) or 60.0)
    delta = 0.0
    if "soft" in text:
        if stability >= 75.0:
            delta -= (stability - 75.0) * 0.10
        if track >= 68.0:
            delta += (track - 62.0) * 0.08
    elif "heavy" in text:
        if stability >= 75.0:
            delta -= (stability - 75.0) * 0.10
        if sectional >= 75.0:
            delta -= (sectional - 75.0) * 0.08
        if track >= 68.0:
            delta += (track - 62.0) * 0.10
    return round(delta, 4)


def safety_score(row: dict, context: dict) -> float:
    score = dynamic_score(row, context)
    matrix = row.get("matrix_scores") or {}
    going = str(context.get("going") or context.get("condition") or "")
    score += soft_race_shape_modifier(context, matrix)
    score += soft_wetproof_cap(matrix, score, going, (row.get("data") or {}).get("going_stats_line", ""))
    score += wet_condition_adjustment(matrix, going)
    return round(score, 4)


def current_without_noisy(row: dict) -> float:
    score = base_score(row)
    score -= diversity_bonus(row)
    score -= auto_value(row, "barrier_bias_modifier")
    score -= auto_value(row, "place_tightening_bonus")
    score -= auto_value(row, "micro_rank_bonus")
    return round(score, 4)


def watchlist(row: dict, top3_cutoff: float) -> tuple[str, list[str]]:
    rank = int(row["model_rank"])
    if rank < 4 or rank > 6:
        return "", []
    gap = max(0.0, top3_cutoff - base_score(row))
    reasons = []
    matrix = row.get("matrix_scores") or {}
    features = row.get("feature_scores") or {}
    data = row.get("data") or {}
    if gap <= 2.5:
        reasons.append("near_top3_score")
    if float(matrix.get("stability", 60.0) or 60.0) >= 66.0:
        reasons.append("stable_enough")
    if float(matrix.get("class_weight", 60.0) or 60.0) >= 61.5:
        reasons.append("class_weight_ok")
    if float(matrix.get("jockey_trainer", 60.0) or 60.0) >= 64.0 or float(features.get("trial_score", 60.0) or 60.0) >= 66.0:
        reasons.append("jt_or_trial_support")
    if float(features.get("distance_score", 60.0) or 60.0) >= 60.0:
        reasons.append("distance_ok")
    market_low = parse_float(data.get("current_market_low"), None)
    if market_low is not None and market_low <= 15.0:
        reasons.append("market_context_live")
    timing_recent = parse_float(data.get("timing_600m_recent_speed"), None)
    if timing_recent is not None and timing_recent >= 17.0:
        reasons.append("timing_context")
    if parse_float(data.get("recent_shape_wide_no_cover_count"), 0) or parse_float(data.get("recent_shape_early_work_count"), 0):
        reasons.append("excuse_shape_context")
    if data.get("gear_changes") and str(data.get("gear_changes")).lower() != "none":
        reasons.append("gear_context")
    score = len(reasons)
    level = "High" if score >= 5 else "Medium" if score >= 3 else "Low" if score >= 1 else ""
    return level, reasons


def ranked(rows: list[dict], score_key: str) -> list[dict]:
    return sorted(rows, key=lambda row: (-float(row[score_key]), int(row["horse_number"])))


def eval_ranked(rows: list[dict], out: dict) -> None:
    top3 = rows[:3]
    top5 = rows[:5]
    hits = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
    top2_hits = sum(1 for row in rows[:2] if int(row["actual_pos"]) <= 3)
    out["races"] += 1
    out["top3_places"] += hits
    out["top3_slots"] += len(top3)
    out["hit_distribution"][hits] += 1
    if top3 and int(top3[0]["actual_pos"]) == 1:
        out["champion"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top3):
        out["winner_top3"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top5):
        out["winner_top5"] += 1
    if hits == 3:
        out["gold"] += 1
    if top2_hits == 2:
        out["good"] += 1
    if hits >= 2:
        out["pass"] += 1


def summary(out: dict) -> dict:
    races = out["races"]
    slots = out["top3_slots"]
    return {
        "races": races,
        "champion": pct(out["champion"], races),
        "gold": pct(out["gold"], races),
        "good": pct(out["good"], races),
        "pass": pct(out["pass"], races),
        "winner_top3": pct(out["winner_top3"], races),
        "winner_top5": pct(out["winner_top5"], races),
        "top3_place": pct(out["top3_places"], slots),
        "0hit": out["hit_distribution"][0],
        "1hit": out["hit_distribution"][1],
        "2hit": out["hit_distribution"][2],
        "3hit": out["hit_distribution"][3],
    }


def delta(before: dict, after: dict) -> dict:
    return {
        "gold": after["gold"] - before["gold"],
        "good": after["good"] - before["good"],
        "pass": after["pass"] - before["pass"],
        "0hit": after["hit_distribution"][0] - before["hit_distribution"][0],
        "1hit": after["hit_distribution"][1] - before["hit_distribution"][1],
        "top3_places": after["top3_places"] - before["top3_places"],
        "winner_top5": after["winner_top5"] - before["winner_top5"],
    }


def passes_acceptance(baseline: dict, candidate: dict) -> bool:
    return (
        candidate["gold"] >= baseline["gold"]
        and candidate["good"] >= baseline["good"] - 1
        and candidate["pass"] >= baseline["pass"] - 1
        and candidate["hit_distribution"][0] <= baseline["hit_distribution"][0]
        and candidate["top3_places"] >= baseline["top3_places"] - 2
        and candidate["winner_top5"] >= baseline["winner_top5"]
    )


def passes_directional_clean_acceptance(baseline: dict, candidate: dict) -> bool:
    """User-approved clean gate: allow small Gold sacrifice for broader coverage."""
    return (
        candidate["gold"] >= baseline["gold"] - 3
        and candidate["good"] >= baseline["good"]
        and candidate["pass"] >= baseline["pass"]
        and candidate["hit_distribution"][0] <= baseline["hit_distribution"][0] - 1
        and candidate["top3_places"] >= baseline["top3_places"] - 1
        and candidate["winner_top5"] >= baseline["winner_top5"]
    )


def table(results: dict[str, dict]) -> list[str]:
    lines = [
        "| Variant | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, out in results.items():
        s = summary(out)
        lines.append(
            f"| {name} | {s['races']} | {s['champion']} | {s['gold']} | {s['good']} | {s['pass']} | "
            f"{s['winner_top3']} | {s['winner_top5']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
        )
    return lines


def delta_table(baseline: dict, results: dict[str, dict]) -> list[str]:
    lines = [
        "| Variant | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ | Strict | Directional Clean |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for name, out in results.items():
        if name == "Current Live":
            continue
        d = delta(baseline, out)
        strict = "PASS" if passes_acceptance(baseline, out) else "FAIL"
        directional = "PASS" if passes_directional_clean_acceptance(baseline, out) else "FAIL"
        lines.append(
            f"| {name} | {d['gold']:+d} | {d['good']:+d} | {d['pass']:+d} | {d['0hit']:+d} | "
            f"{d['1hit']:+d} | {d['top3_places']:+d} | {d['winner_top5']:+d} | {strict} | {directional} |"
        )
    return lines


def row_label(row: dict, score_key: str = "current_score") -> str:
    return f"#{row['horse_number']} {row['horse_name']} ({row[score_key]:.2f}, pos {row['actual_pos']})"


def kensington_special_watchlist() -> str:
    scoring_path = KENSINGTON_DIR / "Race_7_Auto_Scoring.csv"
    logic_path = KENSINGTON_DIR / "Race_7_Logic.json"
    results_path = KENSINGTON_DIR / "Race_Results_Kensington_2026-06-10.json"
    if not (scoring_path.exists() and logic_path.exists() and results_path.exists()):
        return "WARN - Kensington standalone files not available."
    scoring_rows = {}
    with scoring_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            horse_no = parse_int(row.get("horse_number"))
            if horse_no is not None:
                scoring_rows[horse_no] = row
    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    finish = {}
    for item in results.get("results", {}).get("7", []):
        horse_no = parse_int(item.get("competitor_number"))
        pos = parse_int(item.get("finish_position"), 99)
        if horse_no is not None and not item.get("is_scratched") and pos and pos < 99:
            finish[horse_no] = pos
    rows = []
    for horse_no, pos in finish.items():
        horse = (logic.get("horses") or {}).get(str(horse_no), {})
        auto = horse.get("python_auto") or {}
        scoring = scoring_rows.get(horse_no, {})
        rows.append({
            "horse_number": horse_no,
            "horse_name": horse.get("horse_name") or scoring.get("horse_name") or "",
            "model_score": parse_float(scoring.get("ability_score"), auto.get("ability_score") or 0.0) or 0.0,
            "actual_pos": pos,
            "matrix_scores": auto.get("matrix_scores") or {},
            "feature_scores": auto.get("feature_scores") or {},
            "data": horse.get("_data") or {},
        })
    rows = sorted(rows, key=lambda row: (-base_score(row), row["horse_number"]))
    for idx, row in enumerate(rows, start=1):
        row["model_rank"] = idx
    top3_cutoff = base_score(rows[2]) if len(rows) >= 3 else 0.0
    target = next((row for row in rows if row["horse_number"] == 4), None)
    if not target:
        return "FAIL - #4 Existential Bob not found."
    level, reasons = watchlist(target, top3_cutoff)
    if level:
        return f"PASS - #4 Existential Bob watchlist level {level}; reasons={','.join(reasons)}."
    return "FAIL - #4 Existential Bob not flagged by broad watchlist."


def main() -> None:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    raw_races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical):
        if sum(1 for row in race_rows if int(row["actual_pos"]) <= 3) >= 3:
            raw_races.append(race_rows)

    variants = {
        "Current Live": "current_score",
        "Pure Static 7D": "pure_static_7d_score",
        "Dynamic 7D Only": "dynamic_7d_score",
        "Dynamic 7D + Safety Caps": "safety_7d_score",
        "Current Minus Noisy Modifiers": "current_no_noisy_score",
    }
    results = {name: bucket() for name in variants}
    by_condition = defaultdict(lambda: {name: bucket() for name in variants})
    watch_stats = Counter()
    watch_examples = []
    clean_examples = []

    for race_rows in raw_races:
        context = race_context(race_rows)
        rows = []
        for source in race_rows:
            row = deepcopy(source)
            row["current_score"] = base_score(row)
            row["pure_static_7d_score"] = matrix_score(row, MATRIX_WEIGHTS)
            row["dynamic_7d_score"] = dynamic_score(row, context)
            row["safety_7d_score"] = safety_score(row, context)
            row["current_no_noisy_score"] = current_without_noisy(row)
            rows.append(row)
        current_ranked = ranked(rows, "current_score")
        for idx, row in enumerate(current_ranked, start=1):
            row["model_rank"] = idx
        top3_cutoff = current_ranked[2]["current_score"] if len(current_ranked) >= 3 else 0.0
        baseline_hits = sum(1 for row in current_ranked[:3] if int(row["actual_pos"]) <= 3)

        for row in current_ranked[3:6]:
            level, reasons = watchlist(row, top3_cutoff)
            if level:
                watch_stats["flagged"] += 1
                watch_stats[f"level_{level.lower()}"] += 1
                if int(row["actual_pos"]) <= 3:
                    watch_stats["actual_top3"] += 1
                if len(watch_examples) < 30:
                    watch_examples.append((current_ranked[0]["meeting"], current_ranked[0]["race"], row, level, reasons))

        for name, key in variants.items():
            rr = ranked(rows, key)
            eval_ranked(rr, results[name])
            eval_ranked(rr, by_condition[rows[0]["condition_bucket"]][name])
            hits = sum(1 for row in rr[:3] if int(row["actual_pos"]) <= 3)
            if name != "Current Minus Noisy Modifiers" and baseline_hits <= 1 and hits > baseline_hits and len(clean_examples) < 24:
                clean_examples.append((name, rows[0]["meeting"], rows[0]["race"], current_ranked, rr, baseline_hits, hits, key))

    baseline = results["Current Live"]
    passing = [name for name, out in results.items() if name != "Current Live" and passes_acceptance(baseline, out)]
    directional_passing = [
        name for name, out in results.items()
        if name != "Current Live" and passes_directional_clean_acceptance(baseline, out)
    ]
    if passing:
        recommendation = f"Candidate clean variant(s) passed: {', '.join(passing)}. Implement only the simplest passing variant after code review."
    elif "Pure Static 7D" in directional_passing:
        recommendation = (
            "Pure Static 7D passes the directional clean gate: accept small Gold sacrifice "
            "for lower 0-hit, better Good/Pass, better Winner Top5, and cleaner future upgrade path."
        )
    elif directional_passing:
        recommendation = f"Directional clean candidate(s) passed: {', '.join(directional_passing)}. Prefer the simplest matrix-only variant."
    else:
        recommendation = "No clean variant passed the no-regression gate. Keep live ranking unchanged; move rescue/formguide evidence to report-only watchlist."

    lines = [
        "# AU Clean 7D Ablation Backtest",
        "",
        "Shadow test only. This report does not change the live AU ranking engine.",
        "",
        "## Recommendation",
        "",
        f"- {recommendation}",
        f"- Kensington gate: {kensington_special_watchlist()}",
        "- HKJC lesson applied: keep final ranking as one official matrix score; use rich data as sourced feature evidence or report-only watchlist, not post-score rerank noise.",
        "",
        "## Overall Metrics",
        "",
        *table(results),
        "",
        "## Delta vs Current Live",
        "",
        *delta_table(baseline, results),
        "",
        "## Broad Rank 4-6 Watchlist Quality",
        "",
        f"- Flagged rank 4-6 horses: **{watch_stats['flagged']}**",
        f"- Actual Top3 among flagged: **{watch_stats['actual_top3']}** ({pct(watch_stats['actual_top3'], watch_stats['flagged'])})",
        f"- Levels: High **{watch_stats['level_high']}**, Medium **{watch_stats['level_medium']}**, Low **{watch_stats['level_low']}**",
        "",
        "## Condition Breakdown",
        "",
        "| Condition | Variant | Races | Gold | Good | Pass | Winner Top5 | Top3 Place | 0-hit | 1-hit |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for condition, version_buckets in sorted(by_condition.items(), key=lambda item: (-item[1]["Current Live"]["races"], item[0])):
        for name in variants:
            s = summary(version_buckets[name])
            lines.append(
                f"| {condition} | {name} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | "
                f"{s['winner_top5']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} |"
            )

    lines.extend(["", "## Watchlist Examples", ""])
    for meeting, race_no, row, level, reasons in watch_examples[:18]:
        lines.append(f"- {meeting} R{race_no}: {level} danger {row_label(row)}; reasons={','.join(reasons)}")

    lines.extend(["", "## Clean Variant Improved 0/1-Hit Examples", ""])
    for name, meeting, race_no, before, after, before_hits, after_hits, key in clean_examples:
        lines.append(f"### {name} - {meeting} R{race_no}")
        lines.append(f"- Hits: {before_hits} -> {after_hits}")
        lines.append("- Current Top3: " + " / ".join(row_label(row, "current_score") for row in before[:3]))
        lines.append("- Variant Top3: " + " / ".join(row_label(row, key) for row in after[:3]))
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")
    for name, out in results.items():
        print(name, summary(out))
    print("Passing variants:", passing or "None")
    print("Directional clean variants:", directional_passing or "None")
    print("Kensington:", kensington_special_watchlist())


if __name__ == "__main__":
    main()
