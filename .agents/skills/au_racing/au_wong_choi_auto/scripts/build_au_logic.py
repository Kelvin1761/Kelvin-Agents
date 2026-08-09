#!/usr/bin/env python3
"""
Build deterministic AU Race_X_Logic.json from Facts.md.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TRACK_RESOURCE_DIR = SCRIPT_DIR.parents[1] / "au_horse_analyst" / "resources"
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from source_alignment import (
    HORSE_HEADER_RE,
    RACECARD_HORSE_RE,
    RACECARD_META_RE,
    clean_identity as _clean_identity,
    normalize_horse_name as _normalize_horse_name,
    race_source_candidates,
    validate_facts_horse_alignment,
    venue_from_meeting_name,
)
from engine_core import (
    _extract_race_meta as _canonical_extract_race_meta,
    _load_meeting_intelligence as _canonical_load_meeting_intelligence,
    _load_track_profile as _canonical_load_track_profile,
    _parse_meeting_intelligence as _canonical_parse_meeting_intelligence,
    _parse_speed_map as _canonical_parse_speed_map,
    _venue_from_folder_name as _canonical_venue_from_folder_name,
    build_logic_from_facts as _canonical_build_logic_from_facts,
)
from io_utils import write_json_atomic

VENUE_TRACK_MAP = {
    "randwick": "04b_track_randwick.md",
    "rosehill": "04b_track_rosehill.md",
    "flemington": "04b_track_flemington.md",
    "caulfield": "04b_track_caulfield.md",
    "moonee valley": "04b_track_moonee_valley.md",
    "eagle farm": "04b_track_eagle_farm.md",
    "doomben": "04b_track_doomben.md",
    "warwick farm": "04b_track_warwick_farm.md",
    "canterbury": "04b_track_provincial.md",
    "provincial": "04b_track_provincial.md",
}


def build_logic_from_facts(facts_path: Path) -> dict:
    """Compatibility entrypoint backed by the canonical engine parser."""
    return _canonical_build_logic_from_facts(facts_path)


def _extract_race_number(filename: str, text: str) -> int:
    match = re.search(r"Race[ _](\d+)", filename)
    if match:
        return int(match.group(1))
    block = re.search(r"# .*Race\s+(\d+)", text)
    return int(block.group(1)) if block else 1


def _extract_race_meta(facts_path: Path, text: str) -> tuple[str, str, int]:
    race_number = _extract_race_number(facts_path.name, text)
    distance_match = re.search(r"今仗距離:\s*([0-9]+m)", text)
    distance = distance_match.group(1) if distance_match else ""
    racecard_candidates = race_source_candidates(
        facts_path.parent,
        race_number,
        "Racecard",
    )
    race_class = ""
    prize = 0
    if racecard_candidates:
        racecard_path = racecard_candidates[0]
        lines = racecard_path.read_text(encoding="utf-8").splitlines()
        if not lines:
            raise ValueError(
                f"Race {race_number} Racecard is empty: {racecard_path.name}"
            )
        header = lines[0]
        class_match = re.search(r"\d+m\s*\|\s*([^|$]+?)(?:\s*\||\s*$)", header)
        if class_match:
            race_class = class_match.group(1).strip()
        prize_match = re.search(r"\$\s*([0-9,]+)", header)
        if prize_match:
            prize = int(prize_match.group(1).replace(",", ""))
        if not distance:
            dist_match = re.search(r"[—–-]\s*(\d{3,5}m)", header)
            if dist_match:
                distance = dist_match.group(1)
    return race_class, distance, prize


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


def _load_racecard_profiles(facts_path: Path, race_number: int) -> dict[str, dict]:
    candidates = race_source_candidates(facts_path.parent, race_number, "Racecard")
    if not candidates:
        return {}
    lines = candidates[0].read_text(encoding="utf-8").splitlines()
    profiles = {}
    index = 0
    while index < len(lines):
        horse_match = RACECARD_HORSE_RE.match(lines[index].strip())
        if not horse_match or index + 1 >= len(lines):
            index += 1
            continue
        meta_match = RACECARD_META_RE.match(lines[index + 1].strip())
        if meta_match:
            horse_name = _clean_identity(horse_match.group(1))
            rating_raw = meta_match.group(2)
            profiles[_normalize_horse_name(horse_name)] = {
                "horse_rating": float(rating_raw) if rating_raw else None,
                "declared_weight": float(meta_match.group(1)),
            }
        index += 2
    return profiles


def _extract_career_starts(block: str) -> int:
    line = _capture(block, r"生涯: ([^\n]+)")
    match = re.match(r"\s*(\d+)\s*(?::|$)", line or "")
    return int(match.group(1)) if match else 0


def _extract_career_tag(block: str) -> str:
    starts = _extract_career_starts(block)
    if starts == 0:
        return "DEBUT"
    if starts <= 5:
        return "EARLY_CAREER"
    return "ESTABLISHED"


def _parse_speed_map(text: str) -> dict:
    block_match = re.search(r"### 🗺️ 自動步速圖.*?(?=^=+|\Z)", text, re.M | re.S)
    if not block_match:
        return {}
    block = block_match.group(0)
    def field(name):
        match = re.search(rf"- \*\*{re.escape(name)}:\*\* (.+)$", block, re.M)
        return match.group(1).strip() if match else ""
    return {
        "predicted_pace": field("predicted_pace"),
        "expected_pace": field("expected_pace") or field("predicted_pace"),
        "pace_confidence": field("pace_confidence"),
        "style_confidence": field("style_confidence"),
        "leaders": [int(x) for x in re.findall(r"\d+", field("leaders"))],
        "pressers": [int(x) for x in re.findall(r"\d+", field("pressers"))],
        "on_pace": [int(x) for x in re.findall(r"\d+", field("on_pace"))],
        "mid_pack": [int(x) for x in re.findall(r"\d+", field("mid_pack"))],
        "closers": [int(x) for x in re.findall(r"\d+", field("closers"))],
        "style_evidence": field("style_evidence"),
        "going": field("going"),
        "track_bias": _normalize_speed_map_text(field("track_bias")),
        "tactical_nodes": _normalize_speed_map_text(field("tactical_nodes")),
        "collapse_point": _normalize_speed_map_text(field("collapse_point")),
        "source": field("source"),
    }


def _capture(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.M)
    return match.group(1).strip() if match else ""


def _capture_multiline(text: str, pattern: str) -> str:
    match = re.search(pattern, text, re.M | re.S)
    return " ".join(line.strip() for line in match.group(1).splitlines() if line.strip()) if match else ""


def _record_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        text = line.strip()
        if not text.startswith("|") or "| 類型 |" in text or "|---" in text:
            continue
        cols = [col.strip() for col in text.strip("|").split("|")]
        if len(cols) >= 10:
            rows.append(cols)
    return rows


def _count_trial_rows(block: str) -> int:
    return sum(1 for cols in _record_rows(block) if "試閘" in cols[1])


def _count_formal_rows(block: str) -> int:
    return sum(1 for cols in _record_rows(block) if "試閘" not in cols[1])


def _count_trial_top3(block: str) -> int:
    total = 0
    for cols in _record_rows(block):
        if "試閘" not in cols[1]:
            continue
        place_text = cols[7]
        match = re.search(r"\d+", place_text)
        if match and int(match.group(0)) <= 3:
            total += 1
    return total


def _extract_latest_class_move(block: str) -> str:
    for cols in _record_rows(block):
        if "試閘" in cols[1]:
            continue
        return cols[8]
    return ""


def _extract_running_style_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"跑法:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_running_style_confidence(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"跑法:\s*[^|]+\|\s*信心:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_engine_type_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"引擎:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_engine_confidence(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"引擎:\s*[^|]+\|\s*信心:\s*([^|]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_distance_profile_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"距離分佈:\s*([^\n]+)", engine_block)
    return match.group(1).strip() if match else ""


def _extract_target_distance_line(block: str) -> str:
    engine_block = _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)")
    match = re.search(r"今仗\s+[0-9]+m\s+\([^)]+\):\s*([^\n]+)", engine_block)
    return match.group(0).strip() if match else ""


def _build_tactical_plan(barrier: int, block: str) -> dict:
    style = _extract_running_style_line(block)
    latest_official = next((cols for cols in _record_rows(block) if "試閘" not in cols[1]), None)
    latest_run_style = latest_official[14].strip() if latest_official and len(latest_official) > 14 else ""
    latest_consumption = latest_official[15].strip() if latest_official and len(latest_official) > 15 else ""
    latest_notes = latest_official[16].strip() if latest_official and len(latest_official) > 16 else ""
    expected_position = _expected_position_label(style, latest_run_style, barrier)
    race_scenario = _tactical_scenario_text(expected_position, barrier, latest_consumption, latest_notes)
    return {
        "expected_position": expected_position,
        "race_scenario": race_scenario,
    }


def _expected_position_label(style: str, latest_run_style: str, barrier: int) -> str:
    text = f"{style} {latest_run_style}".strip()
    if any(token in text for token in ("前置", "跟前", "居中前", "前領", "領放")):
        return "前置 / 跟前"
    if any(token in text for token in ("後上", "中後", "後追")):
        return "中後 / 後上"
    if barrier <= 3:
        return "守中 / 內欄"
    return "守中 / 居中"


def _tactical_scenario_text(expected_position: str, barrier: int, consumption: str, notes: str) -> str:
    if "前置" in expected_position:
        if barrier <= 4:
            text = f"出閘後可憑{barrier}檔主動守住前列，首彎前以省位切入為先，入直路前保持走位主動權。"
        elif barrier <= 8:
            text = f"出閘後宜先推前爭位，盡量喺首彎前切入前列，避免中段被迫走外疊。"
        else:
            text = f"外檔下若要保持前置，需要出閘後即時推前搶位；若未能順利切入，走位成本會較高。"
    elif "中後" in expected_position or "後上" in expected_position:
        if barrier <= 4:
            text = f"可先靠{barrier}檔節省腳程守中後列，等待入直路前望空再逐步推進。"
        elif barrier <= 8:
            text = "預計先留居中後列搵遮擋，入直路前再逐步移出追勢。"
        else:
            text = "外檔下宜先收後搵遮擋，避免早段白白走外疊，入直路前再逐步移出追勢。"
    else:
        if barrier <= 3:
            text = f"出閘後可先憑{barrier}檔貼欄守中，首彎前減少白走，入直路前再搵位發力。"
        elif barrier <= 8:
            text = "預計先守中列或中內疊，沿途以慳位為主，入直路前再視乎空位逐步推進。"
        else:
            text = "外檔下先求順利搵遮擋守中，避免長時間無遮擋走外疊，末段再逐步移出。"
    if any(token in notes for token in ("Looking for run", "Crowded", "Steadied", "Across heels")):
        text += " 入直路前亦要留意望空同移位時機。"
    return text


def _normalize_speed_map_text(text: str) -> str:
    value = str(text or "")
    value = value.replace("EEM/settled", "video/settled")
    return value


def _load_meeting_intelligence(facts_path: Path, race_number: int = 0) -> dict:
    """Compatibility wrapper around the single canonical context loader."""
    return _canonical_load_meeting_intelligence(facts_path, race_number)


def _meeting_context_from_extractor_files(facts_path: Path, race_number: int = 0) -> dict:
    folder = facts_path.parent
    context = {
        "venue": _venue_from_folder_name(folder.name),
        "date": _capture(folder.name, r"(\d{4}-\d{2}-\d{2})"),
        "weather_summary": "",
        "track_summary": "",
        "going": "",
        "rail_position": "",
        "bias_summary": "",
        "surface": "",
        "source": "",
    }
    sources: list[str] = []

    summary_path = folder / "Meeting_Summary.md"
    if summary_path.exists():
        summary = summary_path.read_text(encoding="utf-8")
        context["date"] = _first_clean(_capture(summary, r"^Date:\s*([^\n]+)"), context["date"])
        context["going"] = _first_clean(_capture(summary, r"^Track Condition:\s*([^\n]+)"), context["going"])
        context["surface"] = _first_clean(_capture(summary, r"^Surface:\s*([^\n]+)"), context["surface"])
        context["weather_summary"] = _first_clean(_capture(summary, r"^Weather:\s*([^\n]+)"), context["weather_summary"])
        context["rail_position"] = _first_clean(_capture(summary, r"^Rails?:\s*([^\n]+)"), context["rail_position"])
        sources.append("Meeting_Summary.md")

    race_number = race_number or _extract_race_number(facts_path.name, facts_path.read_text(encoding="utf-8"))
    racecards = race_source_candidates(folder, race_number, "Racecard")
    if racecards:
        racecard = racecards[0].read_text(encoding="utf-8")
        meta_line = _first_line_matching(racecard, r"^Track:")
        if meta_line:
            context["going"] = _first_clean(_capture(meta_line, r"Track:\s*([^|]+)"), context["going"])
            context["weather_summary"] = _first_clean(_capture(meta_line, r"Weather:\s*([^|]+)"), context["weather_summary"])
            context["rail_position"] = _first_clean(_capture(meta_line, r"Rail:\s*([^|]+)"), context["rail_position"])
            sources.append(racecards[0].name)

    if context["going"]:
        context["track_summary"] = context["going"]
    context["source"] = " + ".join(dict.fromkeys(sources + (["folder_name"] if context["venue"] else [])))
    return {key: value for key, value in context.items() if value}


def _venue_from_folder_name(name: str) -> str:
    if not re.match(r"^\d{4}-\d{2}-\d{2}(?:[_\s-]|$)", str(name or "")):
        return ""
    return venue_from_meeting_name(name)


def _first_line_matching(text: str, pattern: str) -> str:
    regex = re.compile(pattern)
    for line in str(text or "").splitlines():
        if regex.search(line.strip()):
            return line.strip()
    return ""


def _first_clean(value: str, fallback: str = "") -> str:
    clean = str(value or "").strip().strip(" |")
    return clean or str(fallback or "").strip()


def _merge_sources(primary: str, fallback: str) -> str:
    parts = []
    for raw in (primary, fallback):
        for part in re.split(r"\s+\+\s+|;", str(raw or "")):
            clean = part.strip()
            if clean and clean not in parts:
                parts.append(clean)
    return " + ".join(parts)


def _context_completeness(meeting_intelligence: dict, track_profile: dict) -> dict:
    return {
        "venue": bool(meeting_intelligence.get("venue")),
        "date": bool(meeting_intelligence.get("date")),
        "going": bool(meeting_intelligence.get("going")),
        "rail_position": bool(meeting_intelligence.get("rail_position")),
        "weather_summary": bool(meeting_intelligence.get("weather_summary")),
        "track_profile": bool(track_profile),
    }


def _parse_meeting_intelligence(text: str, fallback_venue: str = "") -> dict:
    """Compatibility wrapper around the single canonical package parser."""
    return _canonical_parse_meeting_intelligence(text, fallback_venue)


def _load_track_profile(venue: str, distance_m: int = 0) -> dict:
    if not str(venue or "").strip():
        return {}
    venue_lower = venue.lower().strip()
    track_file = None
    for key, filename in VENUE_TRACK_MAP.items():
        if key in venue_lower:
            track_file = TRACK_RESOURCE_DIR / filename
            break
    if not track_file or not track_file.exists():
        fallback = TRACK_RESOURCE_DIR / "04b_track_provincial.md"
        track_file = fallback if fallback.exists() else None
    if not track_file or not track_file.exists():
        return {}
    text = track_file.read_text(encoding="utf-8")
    section = _track_venue_section(text, venue) or text
    return {
        "venue": venue,
        "circumference_m": _track_table_int(section, "周長") or _extract_first_int(section, r"(?:賽道)?周長:\**\s*([0-9]+)m"),
        "straight_m": _track_table_int(section, "直路") or _extract_first_int(section, r"直路(?:長度)?:\**\s*([0-9]+)m"),
        "direction": _track_table_text(section, "方向") or _capture(section, r"賽道風向:\**\s*([^\n]+)"),
        "key_traits": _extract_track_traits(section),
        "distance_note": _compact_text(_track_distance_note(section, distance_m) or _track_distance_note(text, distance_m)),
        "going_note": _compact_text(_section_text(section, "## 🌧️ 天氣與場地互動 (Track Condition Bias)") or _section_text(text, "## 🌧️ 天氣與場地互動 (Track Condition Bias)")),
        "source_file": track_file.name,
    }


def _track_venue_section(text: str, venue: str) -> str:
    venue_words = [re.escape(part) for part in re.split(r"\s+", str(venue or "").strip()) if part]
    if not venue_words:
        return ""
    venue_pattern = r"\s+".join(venue_words)
    match = re.search(rf"(^##\s+.*{venue_pattern}.*?\n.*?)(?=^##\s+|\Z)", text, re.I | re.M | re.S)
    return match.group(1).strip() if match else ""


def _track_table_text(text: str, label: str) -> str:
    match = re.search(rf"^\|\s*\*\*{re.escape(label)}\*\*\s*\|\s*([^|\n]+)", text, re.M)
    return match.group(1).strip() if match else ""


def _track_table_int(text: str, label: str) -> int:
    value = _track_table_text(text, label)
    match = re.search(r"([0-9]+)", value)
    return int(match.group(1)) if match else 0


def _track_distance_note(text: str, distance_m: int) -> str:
    if distance_m <= 0:
        return ""
    sections = (
        (range(1000, 1101), r"### 1000m & 1100m .*?\n"),
        (range(1200, 1301), r"### 1200m & 1300m\n"),
        (range(1400, 1601), r"### 1400m & 1600m\n"),
    )
    for distance_range, heading in sections:
        if distance_m not in distance_range:
            continue
        match = re.search(rf"({heading}.*?)(?=\n### |\n## |\Z)", text, re.S)
        if match:
            return match.group(1)
    return ""


def _extract_track_traits(text: str) -> list[str]:
    line = _capture(text, r"特徵標籤:\**\s*([^\n]+)")
    traits = []
    for item in re.split(r"/|,|\|", line):
        clean = item.strip().strip("[]`")
        clean = clean.replace("ON-PACE", "On-Pace").replace("TIGHT-TURNING", "Tight-turning")
        if clean:
            traits.append(clean)
    if not traits:
        traits.extend(_compact_text(item) for item in re.findall(r"^\-\s+(.+)$", text, re.M))
    return traits


def _section_text(text: str, start: str, end: str | None = None) -> str:
    if start not in text:
        return ""
    pattern = re.escape(start) + r"(.*)"
    if end:
        pattern = re.escape(start) + r"(.*?)(?=" + re.escape(end) + r"|\Z)"
    match = re.search(pattern, text, re.S)
    return match.group(1).strip() if match else ""


def _compact_text(text: str) -> str:
    value = str(text or "").replace("*", "")
    value = re.sub(r"^###\s*", "", value, flags=re.M)
    value = re.sub(r"^\-\s*", "", value, flags=re.M)
    return " ".join(value.split())


def _distance_to_int(distance: str) -> int:
    match = re.search(r"(\d+)", str(distance or ""))
    return int(match.group(1)) if match else 0


def _extract_first_int(text: str, pattern: str) -> int:
    match = re.search(pattern, text)
    return int(match.group(1)) if match else 0


# Preserve the public helper imports used by research/tests while routing them
# through the same implementation as the live builder. The legacy definitions
# above remain temporarily for source compatibility but are no longer active.
_extract_race_meta = _canonical_extract_race_meta
_load_track_profile = _canonical_load_track_profile
_parse_speed_map = _canonical_parse_speed_map
_venue_from_folder_name = _canonical_venue_from_folder_name


def main():
    parser = argparse.ArgumentParser(description="Build deterministic AU Logic.json from Facts.md")
    parser.add_argument("facts", help="Path to Facts.md")
    parser.add_argument("--output", help="Output Logic.json path")
    args = parser.parse_args()

    facts_path = Path(args.facts).resolve()
    logic = build_logic_from_facts(facts_path)
    output = Path(args.output).resolve() if args.output else facts_path.with_name(f"Race_{logic['race_analysis']['race_number']}_Logic.json")
    write_json_atomic(output, logic)
    print(f"✅ Logic built: {output}")


if __name__ == "__main__":
    main()
