#!/usr/bin/env python3
"""
Build deterministic AU Race_X_Logic.json from Facts.md.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
TRACK_RESOURCE_DIR = SCRIPT_DIR.parents[2] / "au_horse_analyst" / "resources"

VENUE_TRACK_MAP = {
    "randwick": "04b_track_randwick.md",
    "rosehill": "04b_track_rosehill.md",
    "flemington": "04b_track_flemington.md",
    "caulfield": "04b_track_caulfield.md",
    "moonee valley": "04b_track_moonee_valley.md",
    "eagle farm": "04b_track_eagle_farm.md",
    "doomben": "04b_track_doomben.md",
    "warwick farm": "04b_track_warwick_farm.md",
    "provincial": "04b_track_provincial.md",
}


HORSE_HEADER_RE = re.compile(
    r"^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\) \| 騎師: ([^|]+) \| 練馬師: (.+?) \| 負重: ([0-9.]+)kg$",
    re.M,
)
FIELD_TRAILER_RE = re.compile(r"\s*\|\s*負重:\s*[0-9.]+kg\s*$")


def build_logic_from_facts(facts_path: Path) -> dict:
    text = facts_path.read_text(encoding="utf-8")
    race_number = _extract_race_number(facts_path.name, text)
    race_class, distance = _extract_race_meta(facts_path, text)
    meeting_intelligence = _load_meeting_intelligence(facts_path)
    track_profile = _load_track_profile(
        meeting_intelligence.get("venue", ""),
        _distance_to_int(distance),
    )
    speed_map = _parse_speed_map(text)
    if meeting_intelligence.get("going") and not speed_map.get("going"):
        speed_map["going"] = meeting_intelligence["going"]
    logic = {
        "race_analysis": {
            "race_number": race_number,
            "race_class": race_class,
            "distance": distance,
            "speed_map": speed_map,
            "meeting_intelligence": meeting_intelligence,
            "track_profile": track_profile,
            "going": meeting_intelligence.get("going", ""),
            "track_bias": meeting_intelligence.get("bias_summary", ""),
        },
        "horses": {},
    }
    matches = list(HORSE_HEADER_RE.finditer(text))
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        horse_num = match.group(1)
        logic["horses"][horse_num] = {
            "horse_name": _clean_identity(match.group(2)),
            "barrier": int(match.group(3)),
            "jockey": _clean_identity(match.group(4)),
            "trainer": _clean_identity(match.group(5)),
            "weight": float(match.group(6)),
            "career_race_starts": _extract_career_starts(block),
            "career_tag": _extract_career_tag(block),
            "tactical_plan": _build_tactical_plan(int(match.group(3)), block),
            "_data": {
                "facts_section": block,
                "last10_raw": _capture(block, r"Last 10 字串:\s*`?([^`\n]+)`?"),
                "recent_form": _capture(block, r"近績序列解讀: `?([^`\n]+)`?"),
                "career_record_line": _capture(block, r"生涯: ([^\n]+)"),
                "track_record_line": _capture(block, r"同場: ([^\n]+)") or _capture(block, r"好地: ([^\n]+)"),
                "track_stats_line": _capture(block, r"同場: ([^\n]+)"),
                "going_stats_line": _capture(block, r"好地: ([^\n]+)"),
                "stage_stats_line": _capture(block, r"初出: ([^\n]+)"),
                "last_finish_line": _capture(block, r"上仗結果\(Racecard\): ([^\n]+)"),
                "warning_line": _capture(block, r"⚠️ 警告: ([^\n]+)"),
                "consumption_summary": _capture_multiline(block, r"- \*\*⚡ 走位消耗摘要:\*\*(.*?)(?=\n- \*\*🔗|\n- \*\*🔧|\n### |\Z)"),
                "formline_line": _capture(block, r"\*\*綜合評估:\*\* ([^\n]+)"),
                "engine_line": _capture_multiline(block, r"- \*\*🔧 引擎與距離:\*\*(.*?)(?=\n### |\Z)"),
                "sectional_trend_line": _capture_multiline(block, r"- \*\*📊 段速趨勢.*?\*\*(.*?)(?=\n- \*\*⚡|\n### |\Z)"),
                "running_style_line": _extract_running_style_line(block),
                "style_confidence_line": _extract_running_style_confidence(block),
                "engine_type_line": _extract_engine_type_line(block),
                "engine_confidence_line": _extract_engine_confidence(block),
                "distance_profile_line": _extract_distance_profile_line(block),
                "target_distance_line": _extract_target_distance_line(block),
                "class_move": _extract_latest_class_move(block),
                "formal_count": _count_formal_rows(block),
                "trial_count": _count_trial_rows(block),
                "trial_top3_count": _count_trial_top3(block),
            },
        }
    return logic


def _extract_race_number(filename: str, text: str) -> int:
    match = re.search(r"Race[ _](\d+)", filename)
    if match:
        return int(match.group(1))
    block = re.search(r"# .*Race\s+(\d+)", text)
    return int(block.group(1)) if block else 1


def _extract_race_meta(facts_path: Path, text: str) -> tuple[str, str]:
    distance_match = re.search(r"今仗距離:\s*([0-9]+m)", text)
    distance = distance_match.group(1) if distance_match else ""
    racecard_candidates = list(facts_path.parent.glob(f"*Race {_extract_race_number(facts_path.name, text)} Racecard.md"))
    race_class = ""
    if racecard_candidates:
        header = racecard_candidates[0].read_text(encoding="utf-8").splitlines()[0]
        class_match = re.search(r"\d+m\s*\|\s*([^|$]+?)(?:\s*\||\s*$)", header)
        if class_match:
            race_class = class_match.group(1).strip()
        if not distance:
            dist_match = re.search(r"[—–-]\s*(\d{3,5}m)", header)
            if dist_match:
                distance = dist_match.group(1)
    return race_class, distance


def _extract_career_starts(block: str) -> int:
    line = _capture(block, r"生涯: ([^\n]+)")
    match = re.match(r"(\d+):", line or "")
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
        "expected_pace": field("predicted_pace"),
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


def _load_meeting_intelligence(facts_path: Path) -> dict:
    meeting_path = facts_path.parent / "_Meeting_Intelligence_Package.md"
    if not meeting_path.exists():
        return {}
    text = meeting_path.read_text(encoding="utf-8")
    return _parse_meeting_intelligence(text, facts_path.parent.name)


def _parse_meeting_intelligence(text: str, fallback_venue: str = "") -> dict:
    venue_match = re.search(r"Venue:\s*([^\n]+)", text)
    date_match = re.search(r"Date:\s*([^\n]+)", text)
    weather_block = _section_text(text, "## Weather / 天氣狀況", "## Track Condition / 場地狀況")
    track_block = _section_text(text, "## Track Condition / 場地狀況", "## Track Bias / 賽道偏差預測")
    bias_block = _section_text(text, "## Track Bias / 賽道偏差預測", "## Sources / 資料來源")
    source_block = _section_text(text, "## Sources / 資料來源")
    going_match = re.search(r"Track condition extracted:\s*([^\n.]+)", track_block)
    rail_match = re.search(r"Rail position .*?:\s*([^\n.]+)", track_block)
    return {
        "venue": (venue_match.group(1).strip() if venue_match else fallback_venue).strip(),
        "date": date_match.group(1).strip() if date_match else "",
        "weather_summary": _compact_text(weather_block),
        "track_summary": _compact_text(track_block),
        "going": going_match.group(1).strip() if going_match else "",
        "rail_position": rail_match.group(1).strip() if rail_match else "",
        "bias_summary": _compact_text(bias_block),
        "source": _compact_text(source_block),
    }


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
    return {
        "venue": venue,
        "circumference_m": _extract_first_int(text, r"賽道周長:\**\s*([0-9]+)m"),
        "straight_m": _extract_first_int(text, r"直路長度:\**\s*([0-9]+)m"),
        "direction": _capture(text, r"賽道風向:\**\s*([^\n]+)"),
        "key_traits": _extract_track_traits(text),
        "distance_note": _compact_text(_track_distance_note(text, distance_m)),
        "going_note": _compact_text(_section_text(text, "## 🌧️ 天氣與場地互動 (Track Condition Bias)")),
        "source_file": track_file.name,
    }


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


def _clean_identity(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = FIELD_TRAILER_RE.sub("", text)
    return text.strip(" |")


def main():
    parser = argparse.ArgumentParser(description="Build deterministic AU Logic.json from Facts.md")
    parser.add_argument("facts", help="Path to Facts.md")
    parser.add_argument("--output", help="Output Logic.json path")
    args = parser.parse_args()

    facts_path = Path(args.facts).resolve()
    logic = build_logic_from_facts(facts_path)
    output = Path(args.output).resolve() if args.output else facts_path.with_name(f"Race_{logic['race_analysis']['race_number']}_Logic.json")
    output.write_text(json.dumps(logic, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Logic built: {output}")


if __name__ == "__main__":
    main()
