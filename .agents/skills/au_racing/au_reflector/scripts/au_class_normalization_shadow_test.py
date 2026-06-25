#!/usr/bin/env python3
"""
Shadow test for AU class/venue normalization ideas.

This does not modify production engine behavior. It reuses the same recomputed
395-race iterator as au_review_auto_weighting.py, then applies small post-hoc
rank deltas to test whether finer class ladders and venue-depth normalization
can improve archive performance before any implementation work.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from dataclasses import asdict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"))

from reflector_auto_stats import compute_race_stats  # noqa: E402
from au_review_auto_weighting import (  # noqa: E402
    _build_field_summary,
    _facts_path_for_logic,
    _load_results_map,
    _logic_sort_key,
    find_au_meetings,
    meeting_results_file,
    summarize_race_stats,
)
from engine_core import RacingEngine, enrich_logic_from_facts  # noqa: E402
from scoring import parse_float  # noqa: E402


ARCHIVE_ROOT = AU_RACING
OUTPUT_MD = ARCHIVE_ROOT / "AU_Class_Normalization_Shadow_Test.md"
OUTPUT_JSON = ARCHIVE_ROOT / "AU_Class_Normalization_Shadow_Test.json"

CORE_METRO_TOKENS = (
    "randwick",
    "rosehill",
    "flemington",
    "caulfield",
    "moonee valley",
    "eagle farm",
    "doomben",
    "ascot",
)

SECONDARY_METRO_TOKENS = (
    "warwick farm",
    "kensington",
    "canterbury",
    "sandown",
    "morphettville",
)

VARIANTS = {
    "baseline": {"scale": 0.0, "use_venue": False, "use_weight": False},
    "class_ladder_soft": {"scale": 0.65, "use_venue": False, "use_weight": False},
    "class_venue_soft": {"scale": 0.75, "use_venue": True, "use_weight": False},
    "class_venue_weight_soft": {"scale": 0.75, "use_venue": True, "use_weight": True},
    "class_venue_weight_med": {"scale": 1.0, "use_venue": True, "use_weight": True},
}


def _normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_venue(value) -> str:
    return _normalize_text(value).lower()


def _venue_depth_tier(value) -> int:
    venue = _normalize_venue(value)
    if any(token in venue for token in CORE_METRO_TOKENS):
        return 3
    if any(token in venue for token in SECONDARY_METRO_TOKENS):
        return 2
    return 1 if venue else 0


def _parse_race_class_value(race_class_raw: str) -> int:
    text = _normalize_text(race_class_raw).lower()
    if "group 1" in text:
        return 110
    if "group 2" in text:
        return 106
    if "group 3" in text:
        return 103
    if "listed" in text:
        return 98
    if "maiden" in text:
        return 56
    match = re.search(r"bm\s*(\d+)", text)
    if match:
        return int(match.group(1))
    return 70


def _target_rt_threshold(class_value: int) -> float:
    if class_value >= 108:
        return 72.0
    if class_value >= 100:
        return 69.0
    if class_value >= 88:
        return 67.0
    if class_value >= 78:
        return 65.0
    if class_value >= 72:
        return 64.0
    if class_value >= 64:
        return 62.0
    return 60.0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _shadow_delta(engine: RacingEngine, horse: dict, race: dict, variant: dict) -> tuple[float, dict]:
    scale = float(variant.get("scale") or 0.0)
    if scale <= 0:
        return 0.0, {}

    race_class = engine._race_class_text()
    class_value = _parse_race_class_value(race_class)
    target_rt = _target_rt_threshold(class_value)
    current_venue = engine._meeting_intelligence().get("venue") or engine._track_profile().get("venue") or ""
    current_tier = _venue_depth_tier(current_venue)

    official_entries = engine._official_entries()
    latest = official_entries[0] if official_entries else {}
    latest_venue = latest.get("venue") or ""
    latest_tier = _venue_depth_tier(latest_venue)
    latest_place = parse_float(latest.get("placing"))
    latest_rt = engine._latest_l600_rt_metrics().get("rt")
    class_move = engine._class_move_display()
    weight = parse_float(horse.get("weight"))

    raw = 0.0
    reasons: list[str] = []

    if "降班" in class_move:
        raw += 1.0
        reasons.append("drop")
    elif "大幅升班" in class_move:
        raw -= 1.5
        reasons.append("big_rise")
    elif "升班" in class_move:
        raw -= 1.0
        reasons.append("rise")

    if latest_rt is not None:
        rt_gap = latest_rt - target_rt
        if rt_gap >= 4:
            raw += 1.0
            reasons.append("rt_strong")
        elif rt_gap >= 2:
            raw += 0.6
            reasons.append("rt_ok")
        elif rt_gap <= -4:
            raw -= 1.0
            reasons.append("rt_weak")
        elif rt_gap <= -2:
            raw -= 0.6
            reasons.append("rt_below")

    if latest_place is not None:
        if latest_place <= 3 and class_move == "=":
            raw += 0.5
            reasons.append("same_class_place")
        elif latest_place >= 6 and "升班" in class_move:
            raw -= 0.5
            reasons.append("rise_off_poor_place")

    if variant.get("use_venue"):
        tier_gap = current_tier - latest_tier
        if tier_gap >= 2:
            raw -= 0.9
            reasons.append("big_venue_step")
        elif tier_gap == 1:
            raw -= 0.5
            reasons.append("venue_step")
        elif tier_gap <= -1 and latest_place is not None and latest_place <= 4:
            raw += 0.4
            reasons.append("venue_relief")

        if tier_gap > 0 and latest_rt is not None and latest_rt < target_rt:
            raw -= 0.5
            reasons.append("venue_step_rt_short")

    if variant.get("use_weight") and weight is not None:
        if class_value >= 72 and weight >= 58.5 and ("升班" in class_move or current_tier > latest_tier):
            raw -= 0.5
            reasons.append("deep_class_high_weight")
        elif class_value >= 72 and weight <= 54.5 and latest_rt is not None and latest_rt >= target_rt:
            raw += 0.4
            reasons.append("deep_class_light_weight")

    field_count = int(race.get("field_count") or 0)
    if field_count >= 9:
        raw *= 1.1
        reasons.append("field9plus")

    delta = round(_clip(raw * scale, -2.5, 2.5), 4)
    return delta, {
        "race_class": race_class,
        "class_value": class_value,
        "target_rt": target_rt,
        "current_venue": current_venue,
        "current_tier": current_tier,
        "latest_venue": latest_venue,
        "latest_tier": latest_tier,
        "latest_place": latest_place,
        "latest_rt": latest_rt,
        "class_move": class_move,
        "weight": weight,
        "raw": round(raw, 4),
        "delta": delta,
        "reasons": reasons,
    }


def _ranked_picks_from_logic(logic_path: pathlib.Path, variant_name: str, variant: dict) -> tuple[list[tuple[int, int, str]], list[dict]]:
    logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
    race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race_number = race.get("race_number")
    facts_path = _facts_path_for_logic(logic_path, int(race_number) if str(race_number).isdigit() else None)
    if facts_path and facts_path.exists():
        logic_data = enrich_logic_from_facts(logic_data, facts_path)
        race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
    race["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
    race["field_count"] = int(race.get("field_summary", {}).get("count") or len(logic_data.get("horses", {})))

    ranked = []
    diagnostics = []
    for horse_num, horse in logic_data.get("horses", {}).items():
        data = horse.get("_data", {}) if isinstance(horse.get("_data"), dict) else {}
        engine = RacingEngine(
            horse,
            race,
            facts_section=data.get("facts_section", ""),
            facts_path=facts_path,
        )
        auto = engine.analyze_horse()
        delta, detail = _shadow_delta(engine, horse, race, variant)
        try:
            horse_number = int(horse_num)
        except (TypeError, ValueError):
            horse_number = 999
        rank_score = float(auto.get("rank_score", auto.get("ability_score", 0)) or 0.0) + delta
        ranked.append(
            {
                "horse_number": horse_number,
                "horse_name": str(horse.get("horse_name") or "").strip(),
                "rank_score": rank_score,
                "ability_score": float(auto.get("ability_score", 0) or 0.0),
            }
        )
        diagnostics.append(
            {
                "variant": variant_name,
                "meeting": logic_path.parent.name,
                "race_num": _logic_sort_key(logic_path),
                "horse_number": horse_number,
                "horse_name": str(horse.get("horse_name") or "").strip(),
                "base_rank_score": float(auto.get("rank_score", auto.get("ability_score", 0)) or 0.0),
                **detail,
            }
        )

    ranked.sort(key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
    picks = [(idx, row["horse_number"], row["horse_name"]) for idx, row in enumerate(ranked[:4], start=1)]
    return picks, diagnostics


def run_variant(base_dir: pathlib.Path, variant_name: str, variant: dict) -> dict:
    meetings = find_au_meetings(base_dir)
    started = time.perf_counter()
    aggregate = {
        "meetings": len(meetings),
        "races": 0,
        "Champion": 0,
        "Gold": 0,
        "Good": 0,
        "Minimum": 0,
        "MRR": 0.0,
        "Order Issue": 0,
        "Avg Top4 Hits": 0.0,
    }
    mrr_weighted = 0.0
    top4_weighted = 0.0
    total_races = 0
    details = []
    diagnostics = []

    for index, meeting in enumerate(meetings, start=1):
        meeting_started = time.perf_counter()
        print(f"🔍 AU class shadow [{variant_name}]: {index}/{len(meetings)} {meeting.name}", flush=True)
        results_file = meeting_results_file(meeting)
        if not results_file:
            continue
        results_map = _load_results_map(results_file)
        race_stats = []
        for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key):
            race_num = _logic_sort_key(logic_path)
            results = results_map.get(race_num, [])
            if not results:
                continue
            picks, race_diag = _ranked_picks_from_logic(logic_path, variant_name, variant)
            diagnostics.extend(race_diag)
            if not picks:
                continue
            stats = compute_race_stats(picks, results, {})
            stats.race_num = race_num
            race_stats.append(stats)
        summary = summarize_race_stats(race_stats)
        races = summary["races"]
        if not races:
            continue
        total_races += races
        aggregate["Champion"] += summary["Champion"]
        aggregate["Gold"] += summary["Gold"]
        aggregate["Good"] += summary["Good"]
        aggregate["Minimum"] += summary["Minimum"]
        aggregate["Order Issue"] += summary["Order Issue"]
        mrr_weighted += summary["MRR"] * races
        top4_weighted += summary["Avg Top4 Hits"] * races
        details.append(
            {
                "meeting": meeting.name,
                **summary,
                "races_detail": [asdict(item) for item in race_stats],
            }
        )
        print(
            f"✅ AU class shadow [{variant_name}]: {meeting.name} "
            f"({races} races, {time.perf_counter() - meeting_started:.2f}s, total {time.perf_counter() - started:.2f}s)",
            flush=True,
        )

    aggregate["races"] = total_races
    aggregate["MRR"] = round(mrr_weighted / total_races, 4) if total_races else 0.0
    aggregate["Avg Top4 Hits"] = round(top4_weighted / total_races, 3) if total_races else 0.0
    return {"variant": variant_name, "current_live": aggregate, "details": details, "diagnostics": diagnostics}


def _delta_summary(baseline: dict, candidate: dict) -> dict:
    return {
        "Champion": candidate["Champion"] - baseline["Champion"],
        "Gold": candidate["Gold"] - baseline["Gold"],
        "Good": candidate["Good"] - baseline["Good"],
        "Minimum": candidate["Minimum"] - baseline["Minimum"],
        "MRR": round(candidate["MRR"] - baseline["MRR"], 4),
        "Order Issue": candidate["Order Issue"] - baseline["Order Issue"],
        "Avg Top4 Hits": round(candidate["Avg Top4 Hits"] - baseline["Avg Top4 Hits"], 3),
    }


def _pct(count: int, total: int) -> str:
    return f"{(count / total * 100.0):.1f}%" if total else "0.0%"


def build_report(results: list[dict]) -> str:
    baseline = results[0]["current_live"]
    lines = [
        "# AU Class Normalization Shadow Test",
        "",
        "- Iterator: same `recomputed` mainline benchmark path as `au_review_auto_weighting.py`.",
        "- Scope: shadow-only rerank deltas; production engine is unchanged.",
        "",
        "## Baseline",
        "",
        f"- Meetings: **{baseline['meetings']}**",
        f"- Races: **{baseline['races']}**",
        f"- Champion: **{baseline['Champion']} / {baseline['races']} = {_pct(baseline['Champion'], baseline['races'])}**",
        f"- Good: **{baseline['Good']} / {baseline['races']} = {_pct(baseline['Good'], baseline['races'])}**",
        f"- Pass: **{baseline['Minimum']} / {baseline['races']} = {_pct(baseline['Minimum'], baseline['races'])}**",
        f"- Order Issue: **{baseline['Order Issue']}**",
        "",
        "## Variants",
        "",
        "| Variant | Champion | Gold | Good | Pass | MRR | Order | Avg Top4 Hits | Delta |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in results:
        current = row["current_live"]
        delta = _delta_summary(baseline, current)
        lines.append(
            "| {variant} | {champ} ({champ_pct}) | {gold} | {good} ({good_pct}) | {pass_count} ({pass_pct}) | {mrr:.4f} | {order} | {hits:.3f} | "
            "C {dc:+d} / G {dg:+d} / Good {dgood:+d} / Pass {dp:+d} / Order {do:+d} |".format(
                variant=row["variant"],
                champ=current["Champion"],
                champ_pct=_pct(current["Champion"], current["races"]),
                gold=current["Gold"],
                good=current["Good"],
                good_pct=_pct(current["Good"], current["races"]),
                pass_count=current["Minimum"],
                pass_pct=_pct(current["Minimum"], current["races"]),
                mrr=current["MRR"],
                order=current["Order Issue"],
                hits=current["Avg Top4 Hits"],
                dc=delta["Champion"],
                dg=delta["Gold"],
                dgood=delta["Good"],
                dp=delta["Minimum"],
                do=delta["Order Issue"],
            )
        )

    best = max(
        results[1:],
        key=lambda row: (
            row["current_live"]["Minimum"],
            row["current_live"]["Good"],
            -row["current_live"]["Order Issue"],
            row["current_live"]["Champion"],
        ),
        default=None,
    )
    if best:
        current = best["current_live"]
        delta = _delta_summary(baseline, current)
        lines.extend(
            [
                "",
                "## Best Shadow Candidate",
                "",
                f"- Variant: **{best['variant']}**",
                f"- Champion: **{current['Champion']}** (`{delta['Champion']:+d}`)",
                f"- Good: **{current['Good']}** (`{delta['Good']:+d}`)",
                f"- Pass: **{current['Minimum']}** (`{delta['Minimum']:+d}`)",
                f"- Order Issue: **{current['Order Issue']}** (`{delta['Order Issue']:+d}`)",
                "",
                "## Promotion Gate",
                "",
                "- Promote only if Pass improves, Good does not drop materially, and Order Issue does not worsen.",
            ]
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Shadow test AU class/venue normalization ideas")
    parser.add_argument("--base-dir", default=str(AU_RACING))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    base_dir = pathlib.Path(args.base_dir)
    results = [run_variant(base_dir, name, config) for name, config in VARIANTS.items()]
    report = {
        "baseline_variant": "baseline",
        "variants": [
            {"variant": row["variant"], "current_live": row["current_live"]}
            for row in results
        ],
    }

    OUTPUT_MD.write_text(build_report(results), encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for row in results:
        current = row["current_live"]
        print(
            row["variant"],
            "races",
            current["races"],
            "Champion",
            current["Champion"],
            "Good",
            current["Good"],
            "Pass",
            current["Minimum"],
            "Order",
            current["Order Issue"],
        )
    print(f"Report: {OUTPUT_MD}")
    print(f"JSON: {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
