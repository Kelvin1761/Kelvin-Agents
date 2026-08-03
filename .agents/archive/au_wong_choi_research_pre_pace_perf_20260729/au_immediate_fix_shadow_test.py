#!/usr/bin/env python3
"""
AU immediate-fix shadow test.

This script does not change live scoring. It applies small post-hoc rank deltas
to existing AU Auto scores so candidate fixes can be validated against known
results before any production bake.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]

import sys

sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from au_archive_calibrator import (  # noqa: E402
    ARCHIVE_ROOT,
    HISTORICAL_RESULTS_CSV,
    choose_track_rows,
    detect_meeting_date,
    detect_meeting_track,
    load_historical_results,
    normalize_horse_name,
    parse_int,
)
from matrix_mapper import map_features_to_matrix_scores  # noqa: E402
from scoring import (  # noqa: E402
    PLACE_TIGHTENING_FEATURE_WEIGHTS,
    PLACE_TIGHTENING_SCALE,
    get_dynamic_matrix_weights,
    parse_float,
)
import engine_core  # noqa: E402


OUTPUT_MD = PROJECT_ROOT / "2026-06-09 AU Immediate Fix Shadow Test.md"
OUTPUT_JSON = PROJECT_ROOT / "2026-06-09 AU Immediate Fix Shadow Test.json"

FEATURE_KEYS = (
    "form_score",
    "trial_score",
    "sectional_score",
    "pace_map_score",
    "jockey_score",
    "trainer_score",
    "jockey_horse_fit_score",
    "class_score",
    "rating_score",
    "weight_score",
    "distance_score",
    "track_score",
    "formline_score",
    "consistency_score",
    "health_score",
    "confidence_score",
)

TIGHT_TURN_VENUES = {
    "canterbury",
    "warwick farm",
    "kensington",
    "moonee valley",
    "caulfield",
    "caulfield heath",
    "cranbourne",
    "sandown lakeside",
}

COMMENT_POSITIVE = (
    ("pick of the first starters", 0.85),
    ("trialing well", 0.65),
    ("trialling well", 0.65),
    ("ready to fire", 0.65),
    ("rock hard fit", 0.55),
    ("drawn ideally", 0.45),
    ("main danger", 0.55),
    ("better suited", 0.45),
    ("races extremely well", 0.55),
    ("will be in it", 0.45),
    ("can't be ruled out", 0.35),
    ("hard to beat", 0.65),
    ("looks suited", 0.45),
    ("should relish", 0.35),
)

COMMENT_NEGATIVE = (
    ("needs to improve", -0.45),
    ("prefer others", -0.45),
    ("looking elsewhere", -0.45),
    ("hard to have", -0.55),
    ("query", -0.25),
    ("unlikely", -0.45),
    ("struggling", -0.45),
)


def norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def venue_key(value: Any) -> str:
    return norm_text(value).lower()


def parse_distance(value: Any) -> int:
    n = parse_int(value)
    return int(n or 0)


def load_json_results(path: Path) -> dict[int, dict[int, dict[str, Any]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    raw = data.get("results") if isinstance(data, dict) else None
    if not isinstance(raw, dict):
        return {}
    out: dict[int, dict[int, dict[str, Any]]] = {}
    for race_key, rows in raw.items():
        rn = parse_int(race_key)
        if rn is None or not isinstance(rows, list):
            continue
        race: dict[int, dict[str, Any]] = {}
        for row in rows:
            hn = parse_int(row.get("competitor_number"))
            pos = parse_int(row.get("finish_position"))
            if hn is None or pos is None:
                continue
            race[hn] = {
                "pos": pos,
                "horse_name": norm_text(row.get("horse_name")),
                "comment": norm_text(row.get("comments")),
                "barrier": parse_int(row.get("barrier")),
                "condition": norm_text(row.get("track_condition")),
            }
        out[rn] = race
    return out


def meeting_results_json(meeting: Path) -> Path | None:
    candidates = sorted(meeting.glob("Race_Results_*.json"))
    return candidates[0] if candidates else None


def load_csv_rows(meeting: Path) -> dict[int, list[dict[str, Any]]]:
    path = meeting / "Meeting_Auto_Scoring.csv"
    if not path.exists():
        return {}
    out: dict[int, list[dict[str, Any]]] = defaultdict(list)
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rn = parse_int(row.get("race_number"))
            hn = parse_int(row.get("horse_number"))
            if rn is None or hn is None:
                continue
            row["race_number"] = rn
            row["horse_number"] = hn
            row["rank"] = parse_int(row.get("rank")) or 999
            for key in FEATURE_KEYS + ("ability_score", "rank_score"):
                row[key] = float(parse_float(row.get(key)) or 0.0)
            out[rn].append(row)
    return out


def logic_for_race(meeting: Path, race_no: int) -> dict[str, Any]:
    path = meeting / f"Race_{race_no}_Logic.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def actuals_from_historical(
    historical: dict,
    meeting: Path,
    sample_logic: dict[str, Any],
    race_no: int,
) -> dict[int, dict[str, Any]]:
    meeting_date = detect_meeting_date(meeting)
    meeting_track = detect_meeting_track(meeting, sample_logic)
    if not meeting_date or not meeting_track:
        return {}
    rows = choose_track_rows(historical.get((meeting_date, race_no), []), meeting_track)
    out: dict[int, dict[str, Any]] = {}
    horses = sample_logic.get("horses") or {}
    slug_to_num = {
        normalize_horse_name(horse.get("horse_name")): parse_int(num)
        for num, horse in horses.items()
    }
    for row in rows:
        hn = slug_to_num.get(row.get("horse_slug"))
        if hn is None:
            continue
        out[hn] = {
            "pos": int(row["pos"]),
            "horse_name": row.get("horse_name", ""),
            "comment": "",
            "barrier": parse_int(row.get("barrier")),
            "condition": row.get("condition", ""),
        }
    return out


def running_style(horse: dict[str, Any]) -> str:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    text = " ".join(
        norm_text(value)
        for value in (
            horse.get("tactical_plan"),
            data.get("running_style_line"),
            data.get("recent_settled_pattern_line"),
            data.get("engine_line"),
        )
    ).lower()
    if any(token in text for token in ("前", "lead", "front", "on pace", "on-speed", "prominent", "box")):
        return "front"
    if any(token in text for token in ("守中", "mid", "stalk", "behind speed", "居中")):
        return "mid"
    if any(token in text for token in ("後", "back", "closer", "rear", "settled worse")):
        return "back"
    return "unknown"


def context_audit(meeting: Path, race_logic: dict[int, dict[str, Any]]) -> dict[str, int]:
    audit = Counter()
    for logic in race_logic.values():
        race = logic.get("race_analysis") or {}
        audit["races"] += 1
        going = (
            race.get("going")
            or (race.get("speed_map") or {}).get("going")
            or (race.get("meeting_intelligence") or {}).get("going")
        )
        if not norm_text(going):
            audit["going_blank"] += 1
        profile = race.get("track_profile") if isinstance(race.get("track_profile"), dict) else {}
        if not profile:
            audit["track_profile_blank"] += 1
        geometry_text = " ".join(
            norm_text(profile.get(key))
            for key in ("geometry", "track_geometry", "profile", "turns", "straight", "bias_summary")
        )
        if not geometry_text and not norm_text((race.get("meeting_intelligence") or {}).get("bias_summary")):
            audit["geometry_blank"] += 1
        values = []
        for horse in (logic.get("horses") or {}).values():
            auto = horse.get("python_auto") or {}
            values.append(float(auto.get("barrier_bias_modifier") or 0.0))
        if values and all(abs(v) < 1e-9 for v in values):
            audit["barrier_all_zero"] += 1
        if values and any(abs(v) >= 1e-9 for v in values):
            audit["barrier_nonzero"] += 1
    return dict(audit)


def recompute_score_with_feature_delta(row: dict[str, Any], race: dict[str, Any], deltas: dict[str, float]) -> float:
    features = {key: float(row.get(key) or 60.0) for key in FEATURE_KEYS}
    original_matrix = map_features_to_matrix_scores(features)
    for key, delta in deltas.items():
        features[key] = max(0.0, min(100.0, features.get(key, 60.0) + delta))
    new_matrix = map_features_to_matrix_scores(features)
    weights = get_dynamic_matrix_weights(race)
    ability_delta = sum((new_matrix[k] - original_matrix[k]) * weights.get(k, 0.0) for k in weights)
    place_delta = 0.0
    for key, weight in PLACE_TIGHTENING_FEATURE_WEIGHTS.items():
        place_delta += weight * (features.get(key, 60.0) - float(row.get(key, 60.0)))
    place_delta *= PLACE_TIGHTENING_SCALE
    return float(row["rank_score"]) + ability_delta + place_delta


def trial_sectional_delta(row: dict[str, Any], horse: dict[str, Any], race: dict[str, Any]) -> tuple[float, str]:
    data = horse.get("_data") if isinstance(horse.get("_data"), dict) else {}
    speed = parse_float(data.get("timing_trial_600m_avg_speed"))
    trial_count = parse_int(data.get("trial_count")) or 0
    if not speed or speed <= 0 or trial_count <= 0:
        return 0.0, ""
    l600 = 600.0 / speed
    # Only touch profiles the live engine effectively left at sectional floor.
    if float(row.get("sectional_score") or 0.0) > 42.0:
        return 0.0, ""
    if l600 <= 33.5:
        new_score = recompute_score_with_feature_delta(row, race, {"sectional_score": 8.0})
        return new_score - float(row["rank_score"]), f"trial_extreme_l600_{l600:.2f}"
    if l600 <= 34.0:
        new_score = recompute_score_with_feature_delta(row, race, {"sectional_score": 4.0})
        return new_score - float(row["rank_score"]), f"trial_excellent_l600_{l600:.2f}"
    return 0.0, ""


def geometry_delta(
    row: dict[str, Any],
    horse: dict[str, Any],
    race: dict[str, Any],
    venue: str,
    canterbury_only: bool,
) -> tuple[float, str]:
    vk = venue_key(venue)
    if canterbury_only and "canterbury" not in vk:
        return 0.0, ""
    if not canterbury_only and not any(token in vk for token in TIGHT_TURN_VENUES):
        return 0.0, ""
    distance = parse_distance(race.get("distance"))
    if distance and distance > 1600:
        return 0.0, ""
    barrier = parse_int(horse.get("barrier")) or parse_int(row.get("barrier"))
    if barrier is None:
        return 0.0, ""
    style = running_style(horse)
    delta = 0.0
    reasons = []
    if barrier <= 3:
        delta += 0.45
        reasons.append("inside")
    elif barrier <= 5:
        delta += 0.20
        reasons.append("low_draw")
    elif barrier >= 12:
        delta -= 0.70
        reasons.append("very_wide")
    elif barrier >= 9:
        delta -= 0.40
        reasons.append("wide")
    if style in {"front", "mid"} and barrier <= 5:
        delta += 0.20
        reasons.append("position_geometry")
    if style == "back" and distance and distance <= 1300:
        delta -= 0.20
        reasons.append("short_straight_closer")
    going = norm_text(
        race.get("going")
        or (race.get("speed_map") or {}).get("going")
        or (race.get("meeting_intelligence") or {}).get("going")
    ).lower()
    if "soft" in going and barrier <= 4:
        delta += 0.10
        reasons.append("soft_inside_control")
    return max(-0.9, min(0.75, delta)), "+".join(reasons)


def comment_delta(comment: str) -> tuple[float, str]:
    text = norm_text(comment).lower()
    if not text:
        return 0.0, ""
    delta = 0.0
    reasons = []
    for phrase, value in COMMENT_POSITIVE:
        if phrase in text:
            delta += value
            reasons.append(phrase.replace(" ", "_"))
    for phrase, value in COMMENT_NEGATIVE:
        if phrase in text:
            delta += value
            reasons.append(phrase.replace(" ", "_"))
    return max(-1.0, min(1.25, delta)), "+".join(reasons)


def score_variant(
    row: dict[str, Any],
    horse: dict[str, Any],
    race: dict[str, Any],
    actual: dict[str, Any],
    venue: str,
    variant: str,
) -> tuple[float, list[str]]:
    score = float(row["rank_score"])
    reasons: list[str] = []
    if variant in {"existing_barrier_table", "all"}:
        vk = venue_key(venue)
        adj_map = getattr(engine_core, "_BARRIER_ADJ", {}).get(vk)
        barrier = parse_int(horse.get("barrier")) or parse_int(row.get("barrier"))
        if adj_map and barrier is not None:
            delta = float(adj_map.get(int(barrier), 0.0) or 0.0)
            field_count = len((race.get("field_summary") or {}).get("horses", []) or [])
            if not field_count:
                field_count = 0
            # Mirror live behaviour: scale up for large fields.
            if len((race.get("field_summary") or {})) == 0:
                # race_analysis often lacks field_summary in archived CSV-only snapshots;
                # use no scale in that case instead of inventing field size.
                field_count = 0
            if field_count >= 13:
                delta *= 1.5
            if delta:
                score += delta
                reasons.append(f"existing_barrier:{vk}_b{barrier}:{delta:+.2f}")
    if variant in {"trial", "immediate_canterbury", "immediate_tight", "all"}:
        delta, reason = trial_sectional_delta(row, horse, race)
        if delta:
            score += delta
            reasons.append(f"trial:{reason}:{delta:+.2f}")
    if variant in {"geometry_canterbury", "immediate_canterbury"}:
        delta, reason = geometry_delta(row, horse, race, venue, True)
        if delta:
            score += delta
            reasons.append(f"geo_ctb:{reason}:{delta:+.2f}")
    if variant in {"geometry_tight", "immediate_tight", "all"}:
        delta, reason = geometry_delta(row, horse, race, venue, False)
        if delta:
            score += delta
            reasons.append(f"geo_tight:{reason}:{delta:+.2f}")
    if variant in {"comments", "all"}:
        delta, reason = comment_delta(actual.get("comment", ""))
        if delta:
            score += delta
            reasons.append(f"comment:{reason}:{delta:+.2f}")
    return score, reasons


def summarize_races(races: list[dict[str, Any]], variant: str) -> dict[str, Any]:
    summary = Counter()
    reciprocal = 0.0
    top4_hits = 0
    changed = 0
    examples = []
    for race in races:
        rows = []
        for item in race["horses"]:
            score, reasons = score_variant(
                item["row"],
                item["horse"],
                race["race"],
                item["actual"],
                race["venue"],
                variant,
            )
            rows.append({**item, "score": score, "reasons": reasons})
        base_order = [x["row"]["horse_number"] for x in sorted(race["horses"], key=lambda x: (-float(x["row"]["rank_score"]), -float(x["row"]["ability_score"]), int(x["row"]["horse_number"])))]
        order = [x["row"]["horse_number"] for x in sorted(rows, key=lambda x: (-x["score"], -float(x["row"]["ability_score"]), int(x["row"]["horse_number"])))]
        ranked = sorted(rows, key=lambda x: (-x["score"], -float(x["row"]["ability_score"]), int(x["row"]["horse_number"])))
        top3 = ranked[:3]
        top4 = ranked[:4]
        hits = sum(1 for x in top3 if int(x["actual"]["pos"]) <= 3)
        top4_hits += sum(1 for x in top4 if int(x["actual"]["pos"]) <= 3)
        winner_rank = next((idx for idx, x in enumerate(ranked, 1) if int(x["actual"]["pos"]) == 1), None)
        if winner_rank:
            reciprocal += 1.0 / winner_rank
        summary["races"] += 1
        summary["top3_place"] += hits
        summary[f"{hits}hit"] += 1
        if hits == 3:
            summary["gold"] += 1
        if hits >= 2:
            summary["good"] += 1
        if hits >= 1:
            summary["pass"] += 1
        if any(int(x["actual"]["pos"]) == 1 for x in top3):
            summary["top3_win"] += 1
        if order[:4] != base_order[:4]:
            changed += 1
            if len(examples) < 12:
                examples.append(
                    {
                        "meeting": race["meeting"],
                        "race": race["race_no"],
                        "base_top4": base_order[:4],
                        "variant_top4": order[:4],
                        "reasons": [
                            {
                                "horse": x["row"]["horse_name"],
                                "horse_number": x["row"]["horse_number"],
                                "actual_pos": x["actual"]["pos"],
                                "reasons": x["reasons"],
                            }
                            for x in ranked[:5]
                            if x["reasons"]
                        ],
                    }
                )
    races_n = summary["races"] or 1
    return {
        **dict(summary),
        "mrr": round(reciprocal / races_n, 4),
        "avg_top4_hits": round(top4_hits / races_n, 3),
        "changed_races": changed,
        "examples": examples,
    }


def delta(base: dict[str, Any], cand: dict[str, Any]) -> dict[str, Any]:
    races = base.get("races") or 1
    return {
        "gold": cand.get("gold", 0) - base.get("gold", 0),
        "good": cand.get("good", 0) - base.get("good", 0),
        "pass": cand.get("pass", 0) - base.get("pass", 0),
        "top3_win": cand.get("top3_win", 0) - base.get("top3_win", 0),
        "top3_place": cand.get("top3_place", 0) - base.get("top3_place", 0),
        "0hit": cand.get("0hit", 0) - base.get("0hit", 0),
        "mrr": round(cand.get("mrr", 0.0) - base.get("mrr", 0.0), 4),
        "place_pp": round((cand.get("top3_place", 0) - base.get("top3_place", 0)) / (races * 3) * 100.0, 2),
    }


def discover_meetings(include_current: bool) -> list[Path]:
    meetings = [p for p in ARCHIVE_ROOT.iterdir() if p.is_dir() and (p / "Meeting_Auto_Scoring.csv").exists()]
    if include_current:
        for p in PROJECT_ROOT.glob("20*-* Race*"):
            if p.is_dir() and (p / "Meeting_Auto_Scoring.csv").exists():
                meetings.append(p)
    return sorted(set(meetings))


def load_races(include_current: bool, result_source: str = "both") -> tuple[list[dict[str, Any]], dict[str, Any]]:
    historical = load_historical_results(HISTORICAL_RESULTS_CSV) if result_source in {"historical", "both"} else {}
    races: list[dict[str, Any]] = []
    audit_by_venue: dict[str, Counter] = defaultdict(Counter)
    result_sources = Counter()
    meetings = discover_meetings(include_current)
    print(f"Discovered {len(meetings)} meetings", flush=True)
    for index, meeting in enumerate(meetings, start=1):
        csv_rows = load_csv_rows(meeting)
        if not csv_rows:
            continue
        result_json = meeting_results_json(meeting)
        if result_source == "json" and not result_json:
            continue
        if index == 1 or index % 10 == 0:
            print(f"Loading meeting {index}/{len(meetings)}: {meeting.name}", flush=True)
        json_results = load_json_results(result_json) if result_json and result_source in {"json", "both"} else {}
        race_logic = {rn: logic_for_race(meeting, rn) for rn in csv_rows}
        sample_logic = next((logic for logic in race_logic.values() if logic), {})
        meeting_date = detect_meeting_date(meeting)
        venue = detect_meeting_track(meeting, sample_logic) or meeting.name
        audit = context_audit(meeting, race_logic)
        audit_by_venue[venue].update(audit)
        for race_no, rows in csv_rows.items():
            logic = race_logic.get(race_no) or {}
            if not logic:
                continue
            actual_map = json_results.get(race_no)
            source = "json"
            if not actual_map:
                if result_source == "json":
                    continue
                actual_map = actuals_from_historical(historical, meeting, logic, race_no)
                source = "historical_csv"
            if not actual_map:
                continue
            result_sources[source] += 1
            race = logic.get("race_analysis") or {}
            horses = logic.get("horses") or {}
            race_items = []
            for row in rows:
                hn = int(row["horse_number"])
                horse = horses.get(str(hn)) or {}
                actual = actual_map.get(hn)
                if not actual:
                    # Fall back to name matching for archival oddities.
                    slug = normalize_horse_name(row.get("horse_name"))
                    actual = next(
                        (
                            value
                            for value in actual_map.values()
                            if normalize_horse_name(value.get("horse_name")) == slug
                        ),
                        None,
                    )
                if not actual:
                    continue
                race_items.append({"row": row, "horse": horse, "actual": actual})
            if len(race_items) >= 4:
                races.append(
                    {
                        "meeting": meeting.name,
                        "date": meeting_date,
                        "venue": venue,
                        "race_no": race_no,
                        "race": race,
                        "horses": race_items,
                    }
                )
    return races, {
        "audit_by_venue": {k: dict(v) for k, v in audit_by_venue.items()},
        "result_sources": dict(result_sources),
    }


def subset(races: list[dict[str, Any]], name: str) -> list[dict[str, Any]]:
    if name == "all":
        return races
    if name == "canterbury":
        return [r for r in races if "canterbury" in venue_key(r["venue"])]
    if name == "tight_turn":
        return [r for r in races if any(token in venue_key(r["venue"]) for token in TIGHT_TURN_VENUES)]
    return races


def pct(value: int, denom: int) -> str:
    return f"{value / denom * 100.0:.1f}%" if denom else "0.0%"


def build_report(results: dict[str, dict[str, dict[str, Any]]], meta: dict[str, Any]) -> str:
    lines = [
        "# AU Immediate Fix Shadow Test",
        "",
        "This is a validation report only. No live scoring code or matrix weights were changed.",
        "",
        "## Data",
        f"- Result sources: `{meta['result_sources']}`",
        "",
        "## Context Audit",
        "",
        "| Venue | Races | Going blank | Track profile blank | Geometry blank | Barrier all-zero | Barrier nonzero |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for venue, audit in sorted(meta["audit_by_venue"].items(), key=lambda kv: (-kv[1].get("races", 0), kv[0])):
        if audit.get("races", 0) < 5:
            continue
        lines.append(
            f"| {venue} | {audit.get('races', 0)} | {audit.get('going_blank', 0)} | "
            f"{audit.get('track_profile_blank', 0)} | {audit.get('geometry_blank', 0)} | "
            f"{audit.get('barrier_all_zero', 0)} | {audit.get('barrier_nonzero', 0)} |"
        )
    for group, variants in results.items():
        baseline = variants["baseline"]
        races = baseline.get("races", 0)
        lines += [
            "",
            f"## {group.replace('_', ' ').title()}",
            f"- Races: **{races}**",
            f"- Baseline: Gold `{baseline.get('gold',0)}`, Good `{baseline.get('good',0)}`, Pass `{baseline.get('pass',0)}`, Top3 win `{baseline.get('top3_win',0)}`, Top3 place `{baseline.get('top3_place',0)}/{races*3 if races else 0}`",
            "",
            "| Variant | Gold | Good | Pass | Top3 Win | Top3 Place | 0-hit | MRR | Changed | Delta |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
        for name, summary in variants.items():
            d = delta(baseline, summary)
            lines.append(
                f"| {name} | {summary.get('gold',0)} | {summary.get('good',0)} | {summary.get('pass',0)} | "
                f"{summary.get('top3_win',0)} | {summary.get('top3_place',0)} | {summary.get('0hit',0)} | "
                f"{summary.get('mrr',0)} | {summary.get('changed_races',0)} | "
                f"G {d['gold']:+d}, Good {d['good']:+d}, Pass {d['pass']:+d}, Win {d['top3_win']:+d}, Place {d['top3_place']:+d} ({d['place_pp']:+.2f}pp), 0H {d['0hit']:+d}, MRR {d['mrr']:+.4f} |"
            )
        for name, summary in variants.items():
            if name == "baseline" or not summary.get("examples"):
                continue
            lines += ["", f"### Example Reranks: {group} / {name}", ""]
            for item in summary["examples"][:5]:
                lines.append(
                    f"- {item['meeting']} R{item['race']}: `{item['base_top4']}` -> `{item['variant_top4']}`"
                )
                for reason in item["reasons"][:4]:
                    lines.append(
                        f"  - #{reason['horse_number']} {reason['horse']} P{reason['actual_pos']}: {', '.join(reason['reasons'])}"
                    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="AU immediate fix shadow validation")
    parser.add_argument("--no-current", action="store_true", help="Exclude current root-level meetings")
    parser.add_argument(
        "--result-source",
        choices=("json", "historical", "both"),
        default="both",
        help="Which result source to validate against",
    )
    parser.add_argument("--output-md", default=str(OUTPUT_MD))
    parser.add_argument("--output-json", default=str(OUTPUT_JSON))
    args = parser.parse_args()

    races, meta = load_races(include_current=not args.no_current, result_source=args.result_source)
    variants = (
        "baseline",
        "existing_barrier_table",
        "trial",
        "geometry_canterbury",
        "immediate_canterbury",
        "geometry_tight",
        "immediate_tight",
        "comments",
        "all",
    )
    groups = ("all", "canterbury", "tight_turn")
    results: dict[str, dict[str, dict[str, Any]]] = {}
    for group in groups:
        group_races = subset(races, group)
        results[group] = {variant: summarize_races(group_races, variant) for variant in variants}

    output_json = Path(args.output_json)
    output_md = Path(args.output_md)
    output_json.write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    output_md.write_text(build_report(results, meta), encoding="utf-8")

    base = results["all"]["baseline"]
    print(f"Loaded {len(races)} races")
    print(f"Baseline all: Gold {base.get('gold',0)} Good {base.get('good',0)} Pass {base.get('pass',0)} Top3Win {base.get('top3_win',0)}")
    for variant in variants[1:]:
        d = delta(base, results["all"][variant])
        print(
            f"{variant}: Gold {d['gold']:+d} Good {d['good']:+d} Pass {d['pass']:+d} "
            f"Win {d['top3_win']:+d} Place {d['top3_place']:+d} 0H {d['0hit']:+d} MRR {d['mrr']:+.4f}"
        )
    print(f"Report: {output_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
