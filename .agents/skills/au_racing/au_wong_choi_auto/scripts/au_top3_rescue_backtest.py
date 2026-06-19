#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path

from au_archive_calibrator import (
    ARCHIVE_ROOT,
    FEATURE_SCORE_KEYS,
    HISTORICAL_RESULTS_CSV,
    MATRIX_KEYS,
    iter_logic_rows,
    load_historical_results,
    parse_float,
    parse_int,
)
from au_zero_hit_race_audit import field_size_bucket, race_class_bucket


OUTPUT_MD = ARCHIVE_ROOT / "AU_Top3_Rescue_Backtest.md"
KENSINGTON_DIR = ARCHIVE_ROOT / "2026-06-10 Kensington Race 1-7"


def pct(n: int | float, d: int | float) -> str:
    return f"{(n / d * 100):.1f}%" if d else "0.0%"


def metric_bucket() -> dict:
    return {
        "races": 0,
        "champion": 0,
        "gold": 0,
        "good": 0,
        "pass": 0,
        "winner_in_top3": 0,
        "winner_in_top5": 0,
        "top3_places": 0,
        "top3_slots": 0,
        "hit_distribution": Counter(),
    }


def row_score(row: dict) -> float:
    return float(row.get("model_score") or row.get("rank_score") or row.get("ability_score") or 0.0)


def rank_race(rows: list[dict], score_key: str = "shadow_score") -> list[dict]:
    return sorted(rows, key=lambda row: (-float(row.get(score_key, row_score(row))), int(row["horse_number"])))


def safe_matrix(row: dict, key: str, default: float = 60.0) -> float:
    return float((row.get("matrix_scores") or {}).get(key, default) or default)


def safe_feature(row: dict, key: str, default: float = 60.0) -> float:
    return float((row.get("feature_scores") or {}).get(key, default) or default)


def structural_weak_count(row: dict) -> int:
    checks = (
        safe_matrix(row, "sectional") < 58.0,
        safe_matrix(row, "race_shape") < 58.0,
        safe_matrix(row, "track") < 60.0,
        safe_matrix(row, "class_weight") < 60.0,
    )
    return sum(1 for flag in checks if flag)


def stable_profile_count(row: dict) -> int:
    checks = (
        safe_matrix(row, "stability") >= 66.0,
        safe_matrix(row, "class_weight") >= 61.5,
        safe_matrix(row, "form_line") >= 64.0,
        safe_matrix(row, "jockey_trainer") >= 64.0,
        safe_matrix(row, "track") >= 64.0,
        safe_feature(row, "distance_score") >= 60.0,
        safe_feature(row, "trial_score") >= 66.0,
        safe_feature(row, "consistency_score") >= 78.0,
        safe_feature(row, "rating_score") >= 64.0,
    )
    return sum(1 for flag in checks if flag)


def rescue_reasons(row: dict, top3_cutoff: float) -> list[str]:
    gap = max(0.0, top3_cutoff - row_score(row))
    reasons = []
    if 4 <= int(row["model_rank"]) <= 6:
        reasons.append("rank4_6")
    if gap <= 2.0:
        reasons.append("score_gap_le_2")
    if safe_matrix(row, "stability") >= 66.0:
        reasons.append("stable_enough")
    if safe_feature(row, "distance_score") >= 60.0:
        reasons.append("distance_ok")
    if safe_matrix(row, "class_weight") >= 61.5:
        reasons.append("class_weight_ok")
    if safe_matrix(row, "jockey_trainer") >= 64.0 or safe_feature(row, "trial_score") >= 66.0:
        reasons.append("jt_or_trial_support")
    if safe_matrix(row, "track") >= 64.0:
        reasons.append("track_ok")
    sp = row.get("sp")
    if sp is not None and sp <= 15.0:
        reasons.append("market_live")
    return reasons


def is_rescue_candidate(row: dict, top3_cutoff: float, *, market_aware: bool = False) -> tuple[bool, list[str], float]:
    rank = int(row["model_rank"])
    gap = max(0.0, top3_cutoff - row_score(row))
    profile_count = stable_profile_count(row)
    reasons = rescue_reasons(row, top3_cutoff)
    risk_flags = set(row.get("risk_flags") or [])
    severe_risk = "high_consumption_load" in risk_flags and safe_matrix(row, "sectional") < 58.0

    passes_core = 4 <= rank <= 6 and gap <= 2.25 and profile_count >= 4 and not severe_risk
    passes_near = 4 <= rank <= 5 and gap <= 3.0 and profile_count >= 5 and not severe_risk
    rescue_score = profile_count * 0.55 + max(0.0, 2.5 - gap) * 0.75
    if safe_matrix(row, "stability") >= 68.0:
        rescue_score += 0.35
    if safe_matrix(row, "class_weight") >= 62.0:
        rescue_score += 0.25
    if safe_matrix(row, "track") >= 66.0:
        rescue_score += 0.20
    if safe_matrix(row, "sectional") >= 62.0:
        rescue_score += 0.15

    sp = row.get("sp")
    if market_aware and sp is not None:
        if sp <= 15.0:
            rescue_score += 0.45
        elif sp >= 41.0 and profile_count < 6:
            rescue_score -= 0.35

    return passes_core or passes_near, reasons, rescue_score


def overrating_reasons(row: dict, *, market_aware: bool = False) -> tuple[list[str], float]:
    reasons = []
    risk_score = 0.0
    stability = safe_matrix(row, "stability")
    form_line = safe_matrix(row, "form_line")
    sectional = safe_matrix(row, "sectional")
    race_shape = safe_matrix(row, "race_shape")
    track = safe_matrix(row, "track")
    class_weight = safe_matrix(row, "class_weight")
    weak_count = structural_weak_count(row)
    risk_flags = set(row.get("risk_flags") or [])

    if stability >= 72.0 and form_line >= 70.0 and weak_count >= 2:
        reasons.append("stability_formline_overtrust")
        risk_score += 1.6
    if weak_count >= 3:
        reasons.append("multi_structural_weakness")
        risk_score += 1.2
    if sectional < 56.0 and race_shape < 58.0:
        reasons.append("weak_engine_and_shape")
        risk_score += 1.1
    if track < 58.0 and class_weight < 60.0:
        reasons.append("track_class_pressure")
        risk_score += 0.8
    if "high_consumption_load" in risk_flags:
        reasons.append("high_consumption_load")
        risk_score += 0.6
    if safe_feature(row, "confidence_score") < 62.0 and safe_feature(row, "trial_score") < 60.0:
        reasons.append("thin_current_support")
        risk_score += 0.5

    sp = row.get("sp")
    profile_count = stable_profile_count(row)
    if market_aware and sp is not None and sp >= 26.0 and profile_count < 6:
        reasons.append("market_cold_sanity")
        risk_score += 0.75 if sp < 51.0 else 1.0

    return reasons, risk_score


def add_rank_metadata(race_rows: list[dict]) -> list[dict]:
    ranked = sorted(deepcopy(race_rows), key=lambda row: (-row_score(row), int(row["horse_number"])))
    for idx, row in enumerate(ranked, start=1):
        row["model_rank"] = idx
        row["shadow_score"] = row_score(row)
    return ranked


def conservative_flags(ranked: list[dict], *, market_aware: bool = False) -> dict:
    top3_cutoff = row_score(ranked[2]) if len(ranked) >= 3 else 0.0
    candidates = []
    risks = []
    for row in ranked:
        if int(row["model_rank"]) > 3:
            ok, reasons, score = is_rescue_candidate(row, top3_cutoff, market_aware=market_aware)
            if ok:
                candidates.append({**row, "rescue_reasons": reasons, "rescue_score": score})
        elif int(row["model_rank"]) <= 3:
            reasons, score = overrating_reasons(row, market_aware=market_aware)
            if reasons:
                risks.append({**row, "risk_reasons": reasons, "risk_score": score})
    candidates.sort(key=lambda row: (-row["rescue_score"], int(row["model_rank"]), int(row["horse_number"])))
    risks.sort(key=lambda row: (-row["risk_score"], int(row["model_rank"]), int(row["horse_number"])))
    return {"candidates": candidates, "risks": risks}


def apply_controlled_rerank(ranked: list[dict], *, market_aware: bool = False) -> tuple[list[dict], dict]:
    flags = conservative_flags(ranked, market_aware=market_aware)
    candidates = flags["candidates"]
    risks = []
    for row in flags["risks"]:
        sp = row.get("sp")
        top1_protected = int(row["model_rank"]) == 1 and row["risk_score"] < 2.4
        market_protected = market_aware and sp is not None and sp <= 8.0 and row["risk_score"] < 2.4
        if top1_protected or market_protected:
            continue
        risks.append(row)
    if not candidates or not risks:
        return ranked, {**flags, "swapped": False, "swap_reason": "missing_candidate_or_risk"}

    rescue = candidates[0]
    risk = risks[0]
    score_gap = row_score(risk) - row_score(rescue)
    threshold = 2.35 if market_aware else 2.0
    min_risk = 1.0
    if score_gap > threshold:
        return ranked, {**flags, "swapped": False, "swap_reason": "score_gap_too_wide"}
    if risk["risk_score"] < min_risk:
        return ranked, {**flags, "swapped": False, "swap_reason": "risk_not_strong_enough"}
    if rescue["rescue_score"] < risk["risk_score"] + 0.65:
        return ranked, {**flags, "swapped": False, "swap_reason": "rescue_not_strong_enough"}

    adjusted = deepcopy(ranked)
    rescue_no = rescue["horse_number"]
    risk_no = risk["horse_number"]
    risk_shadow = next(row["shadow_score"] for row in adjusted if row["horse_number"] == risk_no)
    for row in adjusted:
        if row["horse_number"] == rescue_no:
            row["shadow_score"] = risk_shadow + 0.01
            row["rescue_swap_in"] = True
            row["rescue_reasons"] = rescue["rescue_reasons"]
        elif row["horse_number"] == risk_no:
            row["shadow_score"] = risk_shadow - 0.01
            row["rescue_swap_out"] = True
            row["risk_reasons"] = risk["risk_reasons"]

    return rank_race(adjusted), {
        **flags,
        "swapped": True,
        "swap_reason": "controlled_gate_pass",
        "swap_in": rescue,
        "swap_out": risk,
    }


def evaluate_ranked(ranked: list[dict], bucket: dict) -> None:
    top3 = ranked[:3]
    top5 = ranked[:5]
    top2 = ranked[:2]
    hits_top3 = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
    hits_top2 = sum(1 for row in top2 if int(row["actual_pos"]) <= 3)
    bucket["races"] += 1
    bucket["top3_places"] += hits_top3
    bucket["top3_slots"] += len(top3)
    bucket["hit_distribution"][hits_top3] += 1
    if top3 and int(top3[0]["actual_pos"]) == 1:
        bucket["champion"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top3):
        bucket["winner_in_top3"] += 1
    if any(int(row["actual_pos"]) == 1 for row in top5):
        bucket["winner_in_top5"] += 1
    if hits_top3 == 3:
        bucket["gold"] += 1
    if hits_top2 == 2:
        bucket["good"] += 1
    if hits_top3 >= 2:
        bucket["pass"] += 1


def summary(bucket: dict) -> dict:
    races = bucket["races"]
    slots = bucket["top3_slots"]
    return {
        "races": races,
        "champion": pct(bucket["champion"], races),
        "gold": pct(bucket["gold"], races),
        "good": pct(bucket["good"], races),
        "pass": pct(bucket["pass"], races),
        "winner_top3": pct(bucket["winner_in_top3"], races),
        "winner_top5": pct(bucket["winner_in_top5"], races),
        "top3_place": pct(bucket["top3_places"], slots),
        "0hit": bucket["hit_distribution"][0],
        "1hit": bucket["hit_distribution"][1],
        "2hit": bucket["hit_distribution"][2],
        "3hit": bucket["hit_distribution"][3],
    }


def delta(before: dict, after: dict) -> dict:
    return {
        "gold": after["gold"] - before["gold"],
        "good": after["good"] - before["good"],
        "pass": after["pass"] - before["pass"],
        "0hit": after["hit_distribution"][0] - before["hit_distribution"][0],
        "1hit": after["hit_distribution"][1] - before["hit_distribution"][1],
        "top3_places": after["top3_places"] - before["top3_places"],
        "winner_top5": after["winner_in_top5"] - before["winner_in_top5"],
    }


def row_label(row: dict) -> str:
    sp = row.get("sp")
    sp_text = f", SP {sp:.1f}" if sp is not None else ""
    return (
        f"#{row['horse_number']} {row['horse_name']} "
        f"(rank {row['model_rank']}, score {row_score(row):.2f}, pos {row['actual_pos']}{sp_text})"
    )


def md_summary_table(results: dict[str, dict]) -> list[str]:
    lines = [
        "| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, bucket in results.items():
        s = summary(bucket)
        lines.append(
            f"| {label} | {s['races']} | {s['champion']} | {s['gold']} | {s['good']} | {s['pass']} | "
            f"{s['winner_top3']} | {s['winner_top5']} | {s['top3_place']} | "
            f"{s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
        )
    return lines


def md_delta_table(baseline: dict, results: dict[str, dict]) -> list[str]:
    lines = [
        "| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for label, bucket in results.items():
        if label == "Baseline":
            continue
        d = delta(baseline, bucket)
        lines.append(
            f"| {label} | {d['gold']:+d} | {d['good']:+d} | {d['pass']:+d} | {d['0hit']:+d} | "
            f"{d['1hit']:+d} | {d['top3_places']:+d} | {d['winner_top5']:+d} |"
        )
    return lines


def kensington_r7_check(race_checks: list[dict]) -> str:
    for item in race_checks:
        if item["meeting"] == "2026-06-10 Kensington Race 1-7" and item["race"] == 7:
            candidates = item["market_free_flags"]["candidates"]
            found = next((row for row in candidates if int(row["horse_number"]) == 4), None)
            if found:
                return "PASS - #4 Existential Bob is flagged as a market-free rescue candidate."
            return "FAIL - #4 Existential Bob was not flagged as a market-free rescue candidate."
    special = kensington_r7_special_check()
    if special:
        return special
    return "WARN - Kensington 2026-06-10 R7 not found in the historical scan or standalone result files."


def kensington_r7_special_check() -> str | None:
    scoring_path = KENSINGTON_DIR / "Race_7_Auto_Scoring.csv"
    logic_path = KENSINGTON_DIR / "Race_7_Logic.json"
    results_path = KENSINGTON_DIR / "Race_Results_Kensington_2026-06-10.json"
    if not (scoring_path.exists() and logic_path.exists() and results_path.exists()):
        return None

    scoring_rows = {}
    with scoring_path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            horse_no = parse_int(row.get("horse_number"))
            if horse_no is None:
                continue
            scoring_rows[horse_no] = row

    logic = json.loads(logic_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    race_results = results.get("results", {}).get("7", [])
    starters = {}
    for item in race_results:
        horse_no = parse_int(item.get("competitor_number"))
        finish = parse_int(item.get("finish_position"), 99)
        if horse_no is None or item.get("is_scratched") or not finish or finish >= 99:
            continue
        starters[horse_no] = finish

    rows = []
    for horse_no, finish in starters.items():
        horse = (logic.get("horses") or {}).get(str(horse_no), {})
        auto = horse.get("python_auto") or {}
        scoring = scoring_rows.get(horse_no, {})
        feature_scores = {
            key: parse_float(scoring.get(key), None)
            if scoring.get(key) not in (None, "")
            else parse_float((auto.get("feature_scores") or {}).get(key), 60.0)
            for key in FEATURE_SCORE_KEYS
        }
        matrix_scores = {
            key: parse_float((auto.get("matrix_scores") or {}).get(key), 60.0) or 60.0
            for key in MATRIX_KEYS
        }
        rows.append({
            "meeting": KENSINGTON_DIR.name,
            "race": 7,
            "race_class": str((logic.get("race_analysis") or {}).get("race_class") or ""),
            "condition_bucket": "Soft",
            "horse_number": horse_no,
            "horse_name": horse.get("horse_name") or scoring.get("horse_name") or "",
            "model_score": parse_float(scoring.get("ability_score"), None)
            or parse_float(auto.get("ability_score"), 0.0)
            or 0.0,
            "actual_pos": finish,
            "sp": None,
            "feature_scores": {key: float(value or 60.0) for key, value in feature_scores.items()},
            "matrix_scores": matrix_scores,
            "risk_flags": list(auto.get("risk_flags") or []),
        })

    ranked = add_rank_metadata(rows)
    flags = conservative_flags(ranked, market_aware=False)
    found = next((row for row in flags["candidates"] if int(row["horse_number"]) == 4), None)
    if not found:
        return "FAIL - Kensington standalone check: #4 Existential Bob was not flagged."
    return (
        "PASS - Kensington standalone check: #4 Existential Bob is flagged "
        f"(rank {found['model_rank']}, score {row_score(found):.2f}, reasons={','.join(found['rescue_reasons'])})."
    )


def main() -> None:
    historical_results = load_historical_results(HISTORICAL_RESULTS_CSV)
    all_races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical_results):
        ranked = add_rank_metadata(race_rows)
        actual_top3 = [row for row in ranked if int(row["actual_pos"]) <= 3]
        if len(actual_top3) < 3:
            continue
        all_races.append(ranked)

    results = {
        "Baseline": metric_bucket(),
        "Conservative Flags": metric_bucket(),
        "Controlled Market-Free": metric_bucket(),
        "Controlled Market-Aware": metric_bucket(),
    }
    by_condition = defaultdict(lambda: {key: metric_bucket() for key in results})
    by_class = defaultdict(lambda: {key: metric_bucket() for key in results})
    by_field = defaultdict(lambda: {key: metric_bucket() for key in results})
    flag_stats = {
        "market_free_flags": Counter(),
        "market_aware_flags": Counter(),
    }
    rescue_reason_counts = Counter()
    risk_reason_counts = Counter()
    swap_examples = []
    swap_stats = {
        "market_free": Counter(),
        "market_aware": Counter(),
    }
    focus_examples = []
    race_checks = []

    for ranked in all_races:
        baseline = ranked
        free_flags = conservative_flags(ranked, market_aware=False)
        aware_flags = conservative_flags(ranked, market_aware=True)
        market_free, free_decision = apply_controlled_rerank(ranked, market_aware=False)
        market_aware, aware_decision = apply_controlled_rerank(ranked, market_aware=True)
        versions = {
            "Baseline": baseline,
            "Conservative Flags": baseline,
            "Controlled Market-Free": market_free,
            "Controlled Market-Aware": market_aware,
        }
        condition = ranked[0]["condition_bucket"]
        race_class = race_class_bucket(ranked[0].get("race_class"))
        field_bucket = field_size_bucket(len(ranked))
        baseline_hits = sum(1 for row in baseline[:3] if int(row["actual_pos"]) <= 3)

        flag_stats["market_free_flags"]["races_with_candidate"] += int(bool(free_flags["candidates"]))
        flag_stats["market_free_flags"]["races_with_risk"] += int(bool(free_flags["risks"]))
        flag_stats["market_aware_flags"]["races_with_candidate"] += int(bool(aware_flags["candidates"]))
        flag_stats["market_aware_flags"]["races_with_risk"] += int(bool(aware_flags["risks"]))
        for row in aware_flags["candidates"]:
            flag_stats["market_aware_flags"]["candidate_count"] += 1
            if int(row["actual_pos"]) <= 3:
                flag_stats["market_aware_flags"]["candidate_actual_top3"] += 1
        for row in aware_flags["risks"]:
            flag_stats["market_aware_flags"]["risk_count"] += 1
            if int(row["actual_pos"]) > 3:
                flag_stats["market_aware_flags"]["risk_failed_top3"] += 1
        for row in free_flags["candidates"]:
            flag_stats["market_free_flags"]["candidate_count"] += 1
            if int(row["actual_pos"]) <= 3:
                flag_stats["market_free_flags"]["candidate_actual_top3"] += 1
            for reason in row["rescue_reasons"]:
                rescue_reason_counts[reason] += 1
        for row in free_flags["risks"]:
            flag_stats["market_free_flags"]["risk_count"] += 1
            if int(row["actual_pos"]) > 3:
                flag_stats["market_free_flags"]["risk_failed_top3"] += 1
            for reason in row["risk_reasons"]:
                risk_reason_counts[reason] += 1

        race_checks.append({
            "meeting": ranked[0]["meeting"],
            "race": ranked[0]["race"],
            "market_free_flags": free_flags,
            "market_aware_flags": aware_flags,
        })

        if baseline_hits <= 1 and len(focus_examples) < 30:
            focus_examples.append({
                "meeting": ranked[0]["meeting"],
                "race": ranked[0]["race"],
                "condition": condition,
                "class": race_class,
                "field": field_bucket,
                "baseline_hits": baseline_hits,
                "baseline": baseline,
                "market_free_flags": free_flags,
                "market_aware_flags": aware_flags,
                "market_free_decision": free_decision,
                "market_aware_decision": aware_decision,
            })

        if (free_decision.get("swapped") or aware_decision.get("swapped")) and len(swap_examples) < 25:
            swap_examples.append({
                "meeting": ranked[0]["meeting"],
                "race": ranked[0]["race"],
                "baseline_hits": baseline_hits,
                "free_decision": free_decision,
                "aware_decision": aware_decision,
                "free_hits": sum(1 for row in market_free[:3] if int(row["actual_pos"]) <= 3),
                "aware_hits": sum(1 for row in market_aware[:3] if int(row["actual_pos"]) <= 3),
            })

        for key, decision, before_ranked, after_ranked in (
            ("market_free", free_decision, baseline, market_free),
            ("market_aware", aware_decision, baseline, market_aware),
        ):
            if not decision.get("swapped"):
                continue
            before_hits = sum(1 for row in before_ranked[:3] if int(row["actual_pos"]) <= 3)
            after_hits = sum(1 for row in after_ranked[:3] if int(row["actual_pos"]) <= 3)
            swap_stats[key]["swaps"] += 1
            if after_hits > before_hits:
                swap_stats[key]["improved"] += 1
            elif after_hits == before_hits:
                swap_stats[key]["same"] += 1
            else:
                swap_stats[key]["worse"] += 1
            swap_in = decision.get("swap_in") or {}
            swap_out = decision.get("swap_out") or {}
            if swap_in.get("sp") is not None and swap_in["sp"] >= 20.0:
                swap_stats[key]["high_odds_swap_in"] += 1
                if int(swap_in.get("actual_pos") or 99) <= 3:
                    swap_stats[key]["high_odds_swap_in_actual_top3"] += 1
            if swap_out.get("sp") is not None and swap_out["sp"] <= 8.0:
                swap_stats[key]["short_odds_swap_out"] += 1
                if int(swap_out.get("actual_pos") or 99) <= 3:
                    swap_stats[key]["short_odds_swap_out_actual_top3"] += 1

        for label, version_ranked in versions.items():
            evaluate_ranked(version_ranked, results[label])
            evaluate_ranked(version_ranked, by_condition[condition][label])
            evaluate_ranked(version_ranked, by_class[race_class][label])
            evaluate_ranked(version_ranked, by_field[field_bucket][label])

    lines = [
        "# AU Top3 Rescue Backtest",
        "",
        "Analysis-first shadow test. The 7D matrix scores and live ranking engine are unchanged.",
        "",
        "## Overall Metrics",
        "",
        *md_summary_table(results),
        "",
        "## Delta vs Baseline",
        "",
        *md_delta_table(results["Baseline"], results),
        "",
        "## Rescue/Risk Flag Quality",
        "",
    ]
    free = flag_stats["market_free_flags"]
    aware = flag_stats["market_aware_flags"]
    lines.extend([
        "| Flag Set | Races With Candidate | Candidates | Candidate Actual Top3 | Races With Risk | Risks | Risk Failed Top3 |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| Market-Free | {free['races_with_candidate']} | {free['candidate_count']} | "
            f"{free['candidate_actual_top3']} ({pct(free['candidate_actual_top3'], free['candidate_count'])}) | "
            f"{free['races_with_risk']} | {free['risk_count']} | "
            f"{free['risk_failed_top3']} ({pct(free['risk_failed_top3'], free['risk_count'])}) |"
        ),
        (
            f"| Market-Aware | {aware['races_with_candidate']} | {aware['candidate_count']} | "
            f"{aware['candidate_actual_top3']} ({pct(aware['candidate_actual_top3'], aware['candidate_count'])}) | "
            f"{aware['races_with_risk']} | {aware['risk_count']} | "
            f"{aware['risk_failed_top3']} ({pct(aware['risk_failed_top3'], aware['risk_count'])}) |"
        ),
        "",
        "Top market-free rescue reasons:",
    ])
    for reason, count in rescue_reason_counts.most_common(10):
        lines.append(f"- {reason}: **{count}**")
    lines.append("")
    lines.append("Top market-free overrating risk reasons:")
    for reason, count in risk_reason_counts.most_common(10):
        lines.append(f"- {reason}: **{count}**")

    lines.extend(["", "## Controlled Swap Quality", ""])
    lines.append("| Version | Swaps | Improved | Same | Worse | High-Odds Swap-In | High-Odds Swap-In Actual Top3 | Short-Odds Swap-Out | Short-Odds Swap-Out Actual Top3 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for key, label in (("market_free", "Controlled Market-Free"), ("market_aware", "Controlled Market-Aware")):
        stats = swap_stats[key]
        lines.append(
            f"| {label} | {stats['swaps']} | {stats['improved']} | {stats['same']} | {stats['worse']} | "
            f"{stats['high_odds_swap_in']} | {stats['high_odds_swap_in_actual_top3']} | "
            f"{stats['short_odds_swap_out']} | {stats['short_odds_swap_out_actual_top3']} |"
        )

    lines.extend(["", "## Segment Deltas", ""])
    for title, buckets in (("Condition", by_condition), ("Class", by_class), ("Field Size", by_field)):
        lines.extend([f"### {title}", ""])
        lines.append("| Segment | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |")
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
        for segment, version_buckets in sorted(buckets.items(), key=lambda item: (-item[1]["Baseline"]["races"], item[0])):
            for label in ("Baseline", "Controlled Market-Free", "Controlled Market-Aware"):
                s = summary(version_buckets[label])
                lines.append(
                    f"| {segment} | {label} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | "
                    f"{s['0hit']} | {s['1hit']} | {s['top3_place']} |"
                )
        lines.append("")

    lines.extend([
        "## Kensington Gate",
        "",
        f"- {kensington_r7_check(race_checks)}",
        "",
        "## 0/1-Hit Focus Examples",
        "",
    ])
    for item in focus_examples[:18]:
        lines.extend([
            f"### {item['meeting']} R{item['race']} ({item['baseline_hits']}-hit)",
            f"- Context: {item['condition']} / {item['class']} / {item['field']}",
            "- Baseline Top3:",
        ])
        for row in item["baseline"][:3]:
            lines.append(f"  - {row_label(row)}")
        lines.append("- Market-free rescue candidates:")
        if item["market_free_flags"]["candidates"]:
            for row in item["market_free_flags"]["candidates"][:3]:
                lines.append(f"  - {row_label(row)}; reasons={','.join(row['rescue_reasons'])}; rescue_score={row['rescue_score']:.2f}")
        else:
            lines.append("  - None")
        lines.append("- Market-free Top3 risks:")
        if item["market_free_flags"]["risks"]:
            for row in item["market_free_flags"]["risks"][:3]:
                lines.append(f"  - {row_label(row)}; reasons={','.join(row['risk_reasons'])}; risk_score={row['risk_score']:.2f}")
        else:
            lines.append("  - None")
        lines.append("")

    lines.extend(["## Controlled Swap Examples", ""])
    for item in swap_examples:
        lines.append(f"### {item['meeting']} R{item['race']}")
        lines.append(f"- Baseline hits: {item['baseline_hits']}; market-free hits: {item['free_hits']}; market-aware hits: {item['aware_hits']}")
        if item["free_decision"].get("swapped"):
            lines.append(f"- Market-free swap in: {row_label(item['free_decision']['swap_in'])}")
            lines.append(f"- Market-free swap out: {row_label(item['free_decision']['swap_out'])}")
        if item["aware_decision"].get("swapped"):
            lines.append(f"- Market-aware swap in: {row_label(item['aware_decision']['swap_in'])}")
            lines.append(f"- Market-aware swap out: {row_label(item['aware_decision']['swap_out'])}")
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")
    for label, bucket in results.items():
        print(label, summary(bucket))
    print("Kensington:", kensington_r7_check(race_checks))


if __name__ == "__main__":
    main()
