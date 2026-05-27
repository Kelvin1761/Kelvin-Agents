#!/usr/bin/env python3
"""
Shadow test for constrained class-depth / prize-depth tie-break ideas.

This reuses the recomputed archive benchmark path, but keeps all changes in a
shadow-only post-hoc rerank layer. Production scoring remains unchanged.
"""

from __future__ import annotations

import json
import pathlib
import re
import statistics
import sys
from dataclasses import asdict

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
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


ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Class_Depth_Shadow_Test.md"
OUTPUT_JSON = ARCHIVE_ROOT / "AU_Class_Depth_Shadow_Test.json"

SECTION_HEADER_RE = re.compile(r"^\[(\d+)\]\s+(.+?) \((\d+)\)\s*$", re.M)
RUN_LINE_RE = re.compile(
    r"^(\S.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+m)\s+cond:(\S+)\s+\$([0-9,]+).*?$",
    re.M,
)

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
    "baseline": {
        "scale": 0.0,
        "close_gap": 0.0,
        "bm_focus": False,
        "top_weight_guard": False,
        "positive_only": True,
    },
    "prize_positive_soft": {
        "scale": 0.85,
        "close_gap": 99.0,
        "bm_focus": False,
        "top_weight_guard": False,
        "positive_only": True,
    },
    "prize_tiebreak_small": {
        "scale": 0.70,
        "close_gap": 1.20,
        "bm_focus": False,
        "top_weight_guard": True,
        "positive_only": True,
    },
    "prize_tiebreak_bm_focus": {
        "scale": 0.80,
        "close_gap": 1.35,
        "bm_focus": True,
        "top_weight_guard": True,
        "positive_only": True,
    },
    "prize_tiebreak_bm_strict": {
        "scale": 0.65,
        "close_gap": 1.00,
        "bm_focus": True,
        "top_weight_guard": True,
        "positive_only": True,
    },
    "prize_rank36_bm_micro": {
        "scale": 0.45,
        "close_gap": 1.00,
        "bm_focus": True,
        "top_weight_guard": True,
        "positive_only": True,
        "rank_window": (3, 6),
    },
    "prize_rank46_bm_micro": {
        "scale": 0.55,
        "close_gap": 1.15,
        "bm_focus": True,
        "top_weight_guard": True,
        "positive_only": True,
        "rank_window": (4, 6),
    },
}


def _normalize_text(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _normalize_name(value) -> str:
    return re.sub(r"[^a-z0-9]+", "", _normalize_text(value).lower())


def _parse_money(value) -> int:
    text = str(value or "").replace(",", "")
    match = re.search(r"\d+", text)
    return int(match.group(0)) if match else 0


def _clip(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _venue_depth_tier(value: str) -> int:
    venue = _normalize_text(value).lower()
    if any(token in venue for token in CORE_METRO_TOKENS):
        return 3
    if any(token in venue for token in SECONDARY_METRO_TOKENS):
        return 2
    return 1 if venue else 0


def _extract_current_race_prize(formguide_text: str) -> int:
    match = re.search(r"RACE\s+\d+\s+—.*?\|\s*\$([0-9,]+)", formguide_text)
    return _parse_money(match.group(1)) if match else 0


def _extract_formguide_sections(formguide_text: str) -> dict[str, str]:
    matches = list(SECTION_HEADER_RE.finditer(formguide_text))
    output: dict[str, str] = {}
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(formguide_text)
        output[match.group(1)] = formguide_text[start:end]
    return output


def _parse_section_runs(section: str) -> list[dict]:
    runs = []
    for match in RUN_LINE_RE.finditer(section):
        venue = _normalize_text(match.group(1))
        prize = _parse_money(match.group(6))
        is_trial = "**(TRIAL)**" in match.group(0) or prize == 0
        if is_trial:
            continue
        runs.append(
            {
                "venue": venue,
                "venue_tier": _venue_depth_tier(venue),
                "prize": prize,
            }
        )
    return runs


def _formguide_path_for_logic(logic_path: pathlib.Path, race_num: int) -> pathlib.Path | None:
    matches = sorted(logic_path.parent.glob(f"*Race {race_num} Formguide.md"))
    return matches[0] if matches else None


def _load_formguide_context(logic_path: pathlib.Path, race_num: int) -> tuple[int, dict[str, list[dict]]]:
    formguide_path = _formguide_path_for_logic(logic_path, race_num)
    if not formguide_path or not formguide_path.exists():
        return 0, {}
    text = formguide_path.read_text(encoding="utf-8", errors="ignore")
    current_prize = _extract_current_race_prize(text)
    sections = _extract_formguide_sections(text)
    runs_by_horse_num = {horse_num: _parse_section_runs(section) for horse_num, section in sections.items()}
    return current_prize, runs_by_horse_num


def _class_depth_raw(
    *,
    current_prize: int,
    current_venue_tier: int,
    runs: list[dict],
    class_move: str,
) -> tuple[float, dict]:
    if not current_prize or not runs:
        return 0.0, {"reason": "missing_runs_or_prize"}

    latest = runs[0]
    recent_prizes = [run["prize"] for run in runs[:3] if run.get("prize")]
    if not recent_prizes:
        return 0.0, {"reason": "no_recent_prize"}
    median_prize = statistics.median(recent_prizes)
    latest_prize = latest.get("prize") or 0
    latest_tier = int(latest.get("venue_tier") or 0)

    raw = 0.0
    reasons: list[str] = []
    if latest_prize >= current_prize * 1.45:
        raw += 1.2
        reasons.append("latest_prize_clear_drop")
    elif latest_prize >= current_prize * 1.15:
        raw += 0.8
        reasons.append("latest_prize_drop")
    elif latest_prize <= current_prize * 0.62:
        raw -= 1.0
        reasons.append("latest_prize_big_step")
    elif latest_prize <= current_prize * 0.80:
        raw -= 0.6
        reasons.append("latest_prize_step")

    if median_prize >= current_prize * 1.30:
        raw += 0.7
        reasons.append("median_prize_support")
    elif median_prize <= current_prize * 0.72:
        raw -= 0.6
        reasons.append("median_prize_short")

    tier_gap = current_venue_tier - latest_tier
    if tier_gap >= 2:
        raw -= 0.7
        reasons.append("venue_big_step")
    elif tier_gap == 1:
        raw -= 0.4
        reasons.append("venue_step")
    elif tier_gap <= -1 and latest_prize >= current_prize * 0.95:
        raw += 0.2
        reasons.append("venue_relief")

    class_move_text = str(class_move or "")
    if "降班" in class_move_text and latest_prize >= current_prize * 1.10:
        raw += 0.5
        reasons.append("drop_class_confirms")
    if "升班" in class_move_text and latest_prize <= current_prize * 0.80:
        raw -= 0.5
        reasons.append("rise_class_penalty")

    return raw, {
        "latest_prize": latest_prize,
        "median_prize3": median_prize,
        "current_prize": current_prize,
        "latest_tier": latest_tier,
        "current_tier": current_venue_tier,
        "reasons": reasons,
    }


def _candidate_bonus(
    *,
    raw: float,
    row: dict,
    variant: dict,
    race: dict,
) -> tuple[float, dict]:
    if raw == 0.0:
        return 0.0, {"gate": "raw_zero"}

    if variant.get("positive_only") and raw < 0:
        return 0.0, {"gate": "positive_only"}

    matrix_scores = row["matrix_scores"]
    if min(
        float(matrix_scores.get("stability", 60)),
        float(matrix_scores.get("form_line", 60)),
        float(matrix_scores.get("class_weight", 60)),
    ) < 55:
        return 0.0, {"gate": "section_floor"}

    weight = float(row.get("weight") or 0.0)
    if variant.get("top_weight_guard") and weight >= 59.5 and raw > 0:
        return 0.0, {"gate": "top_weight_guard"}

    if variant.get("bm_focus"):
        is_focus = race.get("race_class_bucket") == "BM58-70" and race.get("condition_bucket") == "Good/Firm"
        if not is_focus:
            raw *= 0.55

    bonus = _clip(raw * float(variant.get("scale") or 0.0), -1.5, 1.5)
    return round(bonus, 4), {"gate": "passed"}


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
    race_num = int(race_number) if str(race_number).isdigit() else _logic_sort_key(logic_path)

    current_prize, runs_by_horse_num = _load_formguide_context(logic_path, race_num)
    current_venue = (race.get("meeting_intelligence", {}) or {}).get("venue") or (race.get("track_profile", {}) or {}).get("venue") or race.get("venue") or ""
    current_venue_tier = _venue_depth_tier(current_venue)

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
        try:
            horse_number = int(horse_num)
        except (TypeError, ValueError):
            horse_number = 999
        row = {
            "horse_number": horse_number,
            "horse_name": str(horse.get("horse_name") or "").strip(),
            "base_rank_score": float(auto.get("rank_score", auto.get("ability_score", 0)) or 0.0),
            "ability_score": float(auto.get("ability_score", 0.0) or 0.0),
            "matrix_scores": auto.get("matrix_scores") or {},
            "weight": horse.get("weight"),
            "class_move": horse.get("class_move") or data.get("class_move") or "",
        }
        runs = runs_by_horse_num.get(str(horse_number), [])
        raw, raw_detail = _class_depth_raw(
            current_prize=current_prize,
            current_venue_tier=current_venue_tier,
            runs=runs,
            class_move=row["class_move"],
        )
        bonus, gate_detail = _candidate_bonus(raw=raw, row=row, variant=variant, race=race)
        ranked.append(
            {
                "horse_number": horse_number,
                "horse_name": row["horse_name"],
                "rank_score": row["base_rank_score"],
                "ability_score": row["ability_score"],
                "class_depth_bonus": bonus,
                "class_depth_raw": raw,
            }
        )
        diagnostics.append(
            {
                "variant": variant_name,
                "meeting": logic_path.parent.name,
                "race_num": race_num,
                "horse_number": horse_number,
                "horse_name": row["horse_name"],
                "base_rank_score": row["base_rank_score"],
                "ability_score": row["ability_score"],
                "class_move": row["class_move"],
                "current_prize": current_prize,
                "current_venue_tier": current_venue_tier,
                "run_count": len(runs),
                "class_depth_raw": round(raw, 4),
                "class_depth_bonus": bonus,
                **raw_detail,
                **gate_detail,
            }
        )

    ranked.sort(key=lambda item: (-item["rank_score"], -item["ability_score"], item["horse_number"]))
    close_gap = float(variant.get("close_gap") or 0.0)
    rank_window = variant.get("rank_window")
    if close_gap > 0:
        adjusted = []
        for idx, item in enumerate(ranked):
            gap_up = 999.0 if idx == 0 else ranked[idx - 1]["rank_score"] - item["rank_score"]
            gap_down = 999.0 if idx == len(ranked) - 1 else item["rank_score"] - ranked[idx + 1]["rank_score"]
            nearest_gap = min(abs(gap_up), abs(gap_down))
            rank_position = idx + 1
            in_rank_window = True
            if rank_window:
                lo, hi = rank_window
                in_rank_window = lo <= rank_position <= hi
            bonus = item["class_depth_bonus"] if nearest_gap <= close_gap and in_rank_window else 0.0
            item["rank_score"] = round(item["rank_score"] + bonus, 4)
            adjusted.append(
                {
                    "horse_number": item["horse_number"],
                    "baseline_rank": rank_position,
                    "nearest_gap": round(nearest_gap, 4) if nearest_gap < 999 else None,
                    "applied_bonus": bonus,
                }
            )
        diagnostics_map = {(row["horse_number"]): row for row in diagnostics}
        for adj in adjusted:
            diagnostics_map.get(adj["horse_number"], {}).update(adj)
    else:
        for item in ranked:
            item["rank_score"] = round(item["rank_score"] + item["class_depth_bonus"], 4)

    ranked.sort(key=lambda item: (-item["rank_score"], -item["ability_score"], item["horse_number"]))
    picks = [(idx, row["horse_number"], row["horse_name"]) for idx, row in enumerate(ranked[:4], start=1)]
    return picks, diagnostics


def run_variant(base_dir: pathlib.Path, variant_name: str, variant: dict) -> dict:
    meetings = find_au_meetings(base_dir)
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

    for meeting in meetings:
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
        details.append({"meeting": meeting.name, **summary, "races_detail": [asdict(item) for item in race_stats]})

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
        "# AU Class Depth Shadow Test",
        "",
        "- Iterator: same recomputed benchmark path as `au_review_auto_weighting.py`.",
        "- Goal: test constrained prize-depth / venue-depth tie-breaks without touching live scoring.",
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
    return "\n".join(lines)


def main() -> int:
    base_dir = ARCHIVE_ROOT
    results = [run_variant(base_dir, name, config) for name, config in VARIANTS.items()]
    report = {
        "baseline_variant": "baseline",
        "variants": [{"variant": row["variant"], "current_live": row["current_live"]} for row in results],
    }
    OUTPUT_MD.write_text(build_report(results), encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
