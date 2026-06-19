#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict
from copy import deepcopy

from au_archive_calibrator import ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, iter_logic_rows, load_historical_results, parse_float
from au_zero_hit_race_audit import field_size_bucket, race_class_bucket


OUTPUT_MD = ARCHIVE_ROOT / "AU_Formguide_Signal_Backtest.md"


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


def model_score(row: dict) -> float:
    return float(row.get("model_score") or row.get("rank_score") or row.get("ability_score") or 0.0)


def data_float(row: dict, key: str) -> float | None:
    return parse_float((row.get("data") or {}).get(key), None)


def data_text(row: dict, key: str) -> str:
    return str((row.get("data") or {}).get(key) or "").strip()


def matrix(row: dict, key: str, default: float = 60.0) -> float:
    return float((row.get("matrix_scores") or {}).get(key, default) or default)


def feature(row: dict, key: str, default: float = 60.0) -> float:
    return float((row.get("feature_scores") or {}).get(key, default) or default)


def rank_rows(rows: list[dict], key: str = "shadow_score") -> list[dict]:
    ranked = sorted(rows, key=lambda row: (-float(row.get(key, model_score(row))), int(row["horse_number"])))
    for idx, row in enumerate(ranked, start=1):
        row["shadow_rank"] = idx
    return ranked


def annotate_base(rows: list[dict]) -> list[dict]:
    ranked = sorted(deepcopy(rows), key=lambda row: (-model_score(row), int(row["horse_number"])))
    for idx, row in enumerate(ranked, start=1):
        row["model_rank"] = idx
        row["shadow_score"] = model_score(row)
        row["fg_reasons"] = []
    return ranked


def eval_ranked(ranked: list[dict], out: dict) -> None:
    top3 = ranked[:3]
    top5 = ranked[:5]
    hits = sum(1 for row in top3 if int(row["actual_pos"]) <= 3)
    top2_hits = sum(1 for row in ranked[:2] if int(row["actual_pos"]) <= 3)
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


def summary(item: dict) -> dict:
    races = item["races"]
    slots = item["top3_slots"]
    return {
        "races": races,
        "champion": pct(item["champion"], races),
        "gold": pct(item["gold"], races),
        "good": pct(item["good"], races),
        "pass": pct(item["pass"], races),
        "winner_top3": pct(item["winner_top3"], races),
        "winner_top5": pct(item["winner_top5"], races),
        "top3_place": pct(item["top3_places"], slots),
        "0hit": item["hit_distribution"][0],
        "1hit": item["hit_distribution"][1],
        "2hit": item["hit_distribution"][2],
        "3hit": item["hit_distribution"][3],
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


def market_score(row: dict) -> tuple[float, list[str]]:
    low = data_float(row, "current_market_low")
    last = data_float(row, "current_market_last")
    first = data_float(row, "current_market_first")
    trend = data_text(row, "current_market_trend").lower()
    reasons = []
    score = 0.0
    live_price = low if low is not None else last
    if live_price is not None and live_price <= 15.0:
        score += 1.0
        reasons.append("market_live_le_15")
    if live_price is not None and live_price <= 8.0:
        score += 0.35
        reasons.append("market_live_le_8")
    if first and last and last < first * 0.82:
        score += 0.35
        reasons.append("firming_market")
    elif "firm" in trend or "short" in trend:
        score += 0.2
        reasons.append("market_trend_positive")
    if last is not None and last >= 31.0:
        score -= 0.75
        reasons.append("market_cold_31plus")
    if last is not None and last >= 51.0:
        score -= 0.4
        reasons.append("market_very_cold_51plus")
    return score, reasons


def excuse_shape_score(row: dict) -> tuple[float, list[str]]:
    data = row.get("data") or {}
    reasons = []
    score = 0.0
    wide = int(parse_float(data.get("recent_shape_wide_no_cover_count"), 0) or 0)
    early = int(parse_float(data.get("recent_shape_early_work_count"), 0) or 0)
    entropy = parse_float(data.get("recent_shape_entropy"), 0.0) or 0.0
    consensus = data_text(row, "recent_shape_consensus").lower()
    latest_text = " ".join(str(data.get(k) or "") for k in ("warning_line", "latest_official_text", "recent_shape_summary_line")).lower()

    if wide >= 1:
        score += 0.45
        reasons.append("recent_wide_no_cover")
    if early >= 1:
        score += 0.35
        reasons.append("recent_early_work")
    if entropy >= 0.85:
        score -= 0.25
        reasons.append("shape_inconsistent")
    if consensus in {"front", "on_pace"} and matrix(row, "race_shape") >= 62.0:
        score += 0.25
        reasons.append("shape_consensus_supported")
    excuse_tokens = ("wide", "without cover", "hampered", "held up", "blocked", "restricted room", "awkward", "checked")
    negative_tokens = ("lame", "bled", "cardiac", "eased down", "poor recovery", "respiratory")
    if any(token in latest_text for token in excuse_tokens):
        score += 0.35
        reasons.append("text_excuse")
    if any(token in latest_text for token in negative_tokens):
        score -= 0.65
        reasons.append("health_negative_text")
    return score, reasons


def timing_score(row: dict, race_rows: list[dict]) -> tuple[float, list[str]]:
    recent = data_float(row, "timing_600m_recent_speed")
    best = data_float(row, "timing_600m_best_speed")
    trend = data_text(row, "timing_600m_trend")
    variance = data_float(row, "timing_speed_variance")
    reasons = []
    score = 0.0
    recent_values = [data_float(peer, "timing_600m_recent_speed") for peer in race_rows]
    recent_values = [value for value in recent_values if value is not None]
    best_values = [data_float(peer, "timing_600m_best_speed") for peer in race_rows]
    best_values = [value for value in best_values if value is not None]
    if recent is not None and recent_values:
        threshold = sorted(recent_values, reverse=True)[max(0, min(2, len(recent_values) - 1))]
        if recent >= threshold:
            score += 0.45
            reasons.append("recent_l600_top3_field")
    if best is not None and best_values:
        threshold = sorted(best_values, reverse=True)[max(0, min(2, len(best_values) - 1))]
        if best >= threshold:
            score += 0.25
            reasons.append("best_l600_top3_field")
    if trend in {"improving", "sharp_improving"}:
        score += 0.35
        reasons.append(f"timing_{trend}")
    elif trend in {"declining", "sharp_declining"}:
        score -= 0.35
        reasons.append(f"timing_{trend}")
    if variance is not None and variance <= 0.12 and recent is not None:
        score += 0.2
        reasons.append("timing_consistent")
    return score, reasons


def gear_score(row: dict) -> tuple[float, list[str]]:
    changes = data_text(row, "gear_changes")
    has_blinkers = bool((row.get("data") or {}).get("has_blinkers"))
    reasons = []
    score = 0.0
    if changes and changes.lower() != "none":
        score += 0.35
        reasons.append("gear_change")
    if has_blinkers and feature(row, "confidence_score") >= 70.0:
        score += 0.15
        reasons.append("blinkers_with_confidence")
    return score, reasons


def top3_risk(row: dict, *, use_market: bool) -> tuple[float, list[str]]:
    reasons = []
    score = 0.0
    weak_engine = matrix(row, "sectional") < 58.0 and matrix(row, "race_shape") < 58.0
    weak_support = matrix(row, "track") < 60.0 and matrix(row, "class_weight") < 60.0
    if weak_engine:
        score += 0.9
        reasons.append("weak_engine_shape")
    if weak_support:
        score += 0.6
        reasons.append("weak_track_class")
    if matrix(row, "stability") >= 72.0 and weak_engine:
        score += 0.4
        reasons.append("stability_overtrust")
    if use_market:
        market, market_reasons = market_score(row)
        if market < -0.7:
            score += min(1.1, abs(market))
            reasons.extend(reason for reason in market_reasons if "cold" in reason)
    return score, reasons


def apply_variant(base_ranked: list[dict], variant: str) -> tuple[list[dict], Counter]:
    rows = deepcopy(base_ranked)
    top3_cutoff = model_score(base_ranked[2]) if len(base_ranked) >= 3 else 0.0
    stats = Counter()
    use_market = variant in {"market", "market_strict", "combined", "combined_strict"}

    for row in rows:
        rank = int(row["model_rank"])
        gap = max(0.0, top3_cutoff - model_score(row))
        parts: list[tuple[float, list[str]]] = []
        if variant in {"market", "market_strict", "combined", "combined_strict"}:
            parts.append(market_score(row))
        if variant in {"excuse_shape", "combined", "combined_strict"}:
            parts.append(excuse_shape_score(row))
        if variant in {"timing", "timing_rescue", "combined", "combined_strict"}:
            parts.append(timing_score(row, base_ranked))
        if variant in {"gear", "combined", "combined_strict"}:
            parts.append(gear_score(row))

        signal = sum(score for score, _ in parts)
        reasons = [reason for _, item_reasons in parts for reason in item_reasons]
        risk, risk_reasons = top3_risk(row, use_market=use_market)

        candidate_gate = rank > 3 and rank <= 6 and gap <= 2.6 and signal >= 1.0
        if variant == "market_strict":
            live_price = data_float(row, "current_market_low") or data_float(row, "current_market_last")
            candidate_gate = (
                rank in {4, 5}
                and gap <= 1.6
                and live_price is not None
                and live_price <= 12.0
                and signal >= 1.2
            )
        elif variant == "timing_rescue":
            candidate_gate = rank > 3 and rank <= 6 and gap <= 2.0 and signal >= 0.65
        elif variant == "combined_strict":
            has_market_live = any(reason in reasons for reason in ("market_live_le_15", "market_live_le_8"))
            has_non_market_support = any(
                reason.startswith("recent_")
                or reason.startswith("timing_")
                or reason in {"best_l600_top3_field", "gear_change", "text_excuse", "shape_consensus_supported"}
                for reason in reasons
            )
            candidate_gate = rank in {4, 5, 6} and gap <= 2.0 and signal >= 1.35 and (has_market_live or has_non_market_support)

        if candidate_gate:
            boost = min(1.35, 0.25 + signal * 0.45 + max(0.0, 2.6 - gap) * 0.15)
            row["shadow_score"] += boost
            row["fg_reasons"].extend(reasons)
            stats["candidate_boosts"] += 1
            if int(row["actual_pos"]) <= 3:
                stats["candidate_actual_top3"] += 1
        elif rank <= 3 and risk >= 1.2 and variant not in {"market_strict", "timing_rescue"}:
            if variant == "combined_strict" and rank == 1:
                continue
            protect_short_price = use_market and (data_float(row, "current_market_low") or 99.0) <= 8.0 and risk < 2.2
            if not protect_short_price:
                penalty = min(0.85, 0.20 + risk * 0.30)
                row["shadow_score"] -= penalty
                row["fg_reasons"].extend(risk_reasons)
                stats["risk_penalties"] += 1
                if int(row["actual_pos"]) > 3:
                    stats["risk_failed"] += 1

    ranked = rank_rows(rows)
    before_hits = sum(1 for row in base_ranked[:3] if int(row["actual_pos"]) <= 3)
    after_hits = sum(1 for row in ranked[:3] if int(row["actual_pos"]) <= 3)
    if after_hits > before_hits:
        stats["race_improved"] += 1
    elif after_hits == before_hits:
        stats["race_same"] += 1
    else:
        stats["race_worse"] += 1
    return ranked, stats


def label(row: dict) -> str:
    data = row.get("data") or {}
    price = data.get("current_market_low") or data.get("current_market_last") or ""
    price_text = f", fluc {price}" if price not in ("", None) else ""
    reasons = ",".join(row.get("fg_reasons") or [])
    reason_text = f"; {reasons}" if reasons else ""
    return f"#{row['horse_number']} {row['horse_name']} (rank {row['model_rank']}, pos {row['actual_pos']}{price_text}{reason_text})"


def table(results: dict[str, dict]) -> list[str]:
    lines = [
        "| Version | Races | Champion | Gold | Good | Pass | Winner Top3 | Winner Top5 | Top3 Place | 0-hit | 1-hit | 2-hit | 3-hit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in results.items():
        s = summary(value)
        lines.append(
            f"| {name} | {s['races']} | {s['champion']} | {s['gold']} | {s['good']} | {s['pass']} | "
            f"{s['winner_top3']} | {s['winner_top5']} | {s['top3_place']} | {s['0hit']} | {s['1hit']} | {s['2hit']} | {s['3hit']} |"
        )
    return lines


def delta_table(baseline: dict, results: dict[str, dict]) -> list[str]:
    lines = [
        "| Version | Gold Δ | Good Δ | Pass Δ | 0-hit Δ | 1-hit Δ | Top3 places Δ | Winner Top5 Δ |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, value in results.items():
        if name == "Baseline":
            continue
        d = delta(baseline, value)
        lines.append(
            f"| {name} | {d['gold']:+d} | {d['good']:+d} | {d['pass']:+d} | {d['0hit']:+d} | "
            f"{d['1hit']:+d} | {d['top3_places']:+d} | {d['winner_top5']:+d} |"
        )
    return lines


def main() -> None:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV)
    races = []
    for race_rows in iter_logic_rows(ARCHIVE_ROOT, historical):
        actual_top3 = [row for row in race_rows if int(row["actual_pos"]) <= 3]
        if len(actual_top3) >= 3:
            races.append(annotate_base(race_rows))

    variants = {
        "Baseline": None,
        "Market Flucs": "market",
        "Market Strict Rescue": "market_strict",
        "Excuse/Run-Shape": "excuse_shape",
        "Timing Consistency": "timing",
        "Timing Rescue Only": "timing_rescue",
        "Gear Change": "gear",
        "Combined Formguide": "combined",
        "Combined Strict": "combined_strict",
    }
    results = {name: bucket() for name in variants}
    by_condition = defaultdict(lambda: {name: bucket() for name in variants})
    signal_stats = {name: Counter() for name in variants if name != "Baseline"}
    examples = []

    for race in races:
        condition = race[0]["condition_bucket"]
        baseline_hits = sum(1 for row in race[:3] if int(row["actual_pos"]) <= 3)
        eval_ranked(race, results["Baseline"])
        eval_ranked(race, by_condition[condition]["Baseline"])
        for name, variant in variants.items():
            if name == "Baseline":
                continue
            ranked, stats = apply_variant(race, variant)
            signal_stats[name].update(stats)
            eval_ranked(ranked, results[name])
            eval_ranked(ranked, by_condition[condition][name])
            after_hits = sum(1 for row in ranked[:3] if int(row["actual_pos"]) <= 3)
            if baseline_hits <= 1 and after_hits > baseline_hits and len(examples) < 25:
                examples.append({
                    "variant": name,
                    "meeting": race[0]["meeting"],
                    "race": race[0]["race"],
                    "condition": condition,
                    "class": race_class_bucket(race[0].get("race_class")),
                    "field": field_size_bucket(len(race)),
                    "baseline": race,
                    "ranked": ranked,
                    "baseline_hits": baseline_hits,
                    "after_hits": after_hits,
                })

    lines = [
        "# AU Formguide Signal Backtest",
        "",
        "Shadow test using pre-race Formguide/Facts data. No live ranking or 7D matrix weights are changed.",
        "",
        "## Overall Metrics",
        "",
        *table(results),
        "",
        "## Delta vs Baseline",
        "",
        *delta_table(results["Baseline"], results),
        "",
        "## Signal Quality",
        "",
        "| Version | Candidate Boosts | Candidate Actual Top3 | Risk Penalties | Risk Failed | Improved Races | Same | Worse |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, stats in signal_stats.items():
        lines.append(
            f"| {name} | {stats['candidate_boosts']} | {stats['candidate_actual_top3']} ({pct(stats['candidate_actual_top3'], stats['candidate_boosts'])}) | "
            f"{stats['risk_penalties']} | {stats['risk_failed']} ({pct(stats['risk_failed'], stats['risk_penalties'])}) | "
            f"{stats['race_improved']} | {stats['race_same']} | {stats['race_worse']} |"
        )

    lines.extend(["", "## Condition Breakdown", ""])
    lines.append("| Condition | Version | Races | Gold | Good | Pass | 0-hit | 1-hit | Top3 Place |")
    lines.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for condition, version_buckets in sorted(by_condition.items(), key=lambda item: (-item[1]["Baseline"]["races"], item[0])):
        for name in variants:
            s = summary(version_buckets[name])
            lines.append(f"| {condition} | {name} | {s['races']} | {s['gold']} | {s['good']} | {s['pass']} | {s['0hit']} | {s['1hit']} | {s['top3_place']} |")

    lines.extend(["", "## Improved 0/1-Hit Examples", ""])
    for item in examples:
        lines.extend([
            f"### {item['variant']} - {item['meeting']} R{item['race']}",
            f"- Context: {item['condition']} / {item['class']} / {item['field']}",
            f"- Hits: {item['baseline_hits']} -> {item['after_hits']}",
            "- Baseline Top3:",
        ])
        for row in item["baseline"][:3]:
            lines.append(f"  - {label(row)}")
        lines.append("- Shadow Top3:")
        for row in item["ranked"][:3]:
            lines.append(f"  - {label(row)}")
        lines.append("")

    OUTPUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report written: {OUTPUT_MD}")
    for name, value in results.items():
        print(name, summary(value))
    print("Signal quality:")
    for name, stats in signal_stats.items():
        print(name, dict(stats))


if __name__ == "__main__":
    main()
