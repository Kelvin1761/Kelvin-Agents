#!/usr/bin/env python3
"""
Build deterministic AU Race_X_Logic.json from Facts.md.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
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
    "canterbury": "04b_track_provincial.md",
    "provincial": "04b_track_provincial.md",
}


# BUGFIX: weight may be unknown — inject_fact_anchors emits "負重: 未知" when the
# racecard has no declared weight. The trailing weight group must therefore also
# match 未知/N/A/- (group 6 stays None → weight=None) so the whole header line
# still matches and the horse is NOT silently dropped from the field.
HORSE_HEADER_RE = re.compile(
    r"^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\)(?:\s*\| 騎師: ([^|]+?))?(?:\s*\| 練馬師: ([^|\n\r]+?))?(?:\s*\| 負重: (?:([0-9.]+)kg|未知|N/A|-))?$",
    re.M,
)
FIELD_TRAILER_RE = re.compile(r"\s*\|\s*負重:\s*(?:[0-9.]+kg|未知|N/A|-)\s*$")
RACECARD_HORSE_RE = re.compile(r"^\d+\.\s+(.+?)\s+\((\d+)\)$")
# BUGFIX: rating may be a non-numeric placeholder ("-", "—", "NR", blank). Make the
# rating group optional so an unrated horse does not fail the whole meta line (which
# would also drop its declared weight). group(2) is None when rating is absent.
RACECARD_META_RE = re.compile(
    r"^Trainer:\s.*?\|\sJockey:\s.*?\|\sWeight:\s*([0-9.]+)(?:kg)?(?:\s*\([^|]*\))?\s*\|\sAge:\s.*?\|\sRating:\s*([0-9.]+)?"
)


_PF_TOKEN_RE = re.compile(r"PF\[(.+?)\]")
_FG_HORSE_HDR_RE = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\((\d+)\)\s*$", re.M)


def _pf_num(pattern: str, text: str):
    m = re.search(pattern, text)
    try:
        return float(m.group(1)) if m else None
    except (TypeError, ValueError):
        return None


def _pf_str(pattern: str, text: str):
    m = re.search(pattern, text)
    return m.group(1).strip() if m else None


def _parse_pf_token(tok: str) -> dict:
    return {
        "l600_time": _pf_num(r"Last600:\s*([-\d.]+)", tok),        # raw last-600m time (run-style confounded)
        "runner_time": _pf_num(r"Runner Time:\s*([-\d.]+)", tok),  # horse finishing time (s)
        "race_time_diff": _pf_num(r"Race Time:\s*([-\d.]+)", tok), # time vs race benchmark (adjusted)
        "l600_delta": _pf_num(r"L600 Delta:\s*([-\d.]+)", tok),    # L600 vs benchmark (adjusted)
        "rt_rating": _pf_num(r"RT Rating:\s*([-\d.]+)", tok),      # racenet RT rating (if scraped)
        "early_runner_pace": _pf_str(r"Early Runner Pace:\s*([^.]+)\.", tok),
        "early_race_pace": _pf_str(r"Early Race Pace:\s*([^.]+)\.", tok),
    }


def _parse_formguide_pf_metrics(facts_path: Path) -> dict:
    """Parse racenet PuntingForm PF[...] tokens from the sibling Formguide file.

    inject_fact_anchors only forwards L600/RT + early-runner-pace into the Facts;
    the adjusted benchmark metrics (race_time_diff, l600_delta, rt_rating) are
    dropped before scoring. Recover the full set here into _data so they are
    available for future testing / feature work. Keyed by saddlecloth number.
    Network-free (consumes already-scraped Formguide). Returns {} if absent.
    """
    fg = facts_path.with_name(facts_path.name.replace("Facts", "Formguide"))
    if not fg.exists():
        return {}
    try:
        text = fg.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict = {}
    headers = list(_FG_HORSE_HDR_RE.finditer(text))
    for idx, hm in enumerate(headers):
        body = text[hm.end(): headers[idx + 1].start() if idx + 1 < len(headers) else len(text)]
        runs = [_parse_pf_token(t) for t in _PF_TOKEN_RE.findall(body)]
        agg: dict = {}
        if runs:
            def col(k):
                return [r[k] for r in runs if r.get(k) is not None]
            for k in ("race_time_diff", "l600_delta", "runner_time", "l600_time"):
                vals = col(k)
                if vals:
                    agg[f"{k}_avg"] = round(sum(vals) / len(vals), 3)
                    agg[f"{k}_best"] = round(min(vals), 3)  # lower time/diff = better
            rt = col("rt_rating")
            if rt:
                agg["rt_rating_avg"] = round(sum(rt) / len(rt), 3)
                agg["rt_rating_best"] = round(max(rt), 3)  # higher rating = better
            agg["latest_early_runner_pace"] = runs[0].get("early_runner_pace")
            agg["latest_early_race_pace"] = runs[0].get("early_race_pace")
            agg["pf_run_count"] = len(runs)
        out[hm.group(1)] = {"pf_runs": runs, "pf_aggregates": agg}
    return out


def build_logic_from_facts(facts_path: Path) -> dict:
    text = facts_path.read_text(encoding="utf-8")
    pf_by_horse = _parse_formguide_pf_metrics(facts_path)
    race_number = _extract_race_number(facts_path.name, text)
    race_class, distance, prize = _extract_race_meta(facts_path, text)
    racecard_profiles = _load_racecard_profiles(facts_path, race_number)
    meeting_intelligence = _load_meeting_intelligence(facts_path, race_number)
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
            "prize": prize,
            "speed_map": speed_map,
            "meeting_intelligence": meeting_intelligence,
            "track_profile": track_profile,
            "context_completeness": _context_completeness(meeting_intelligence, track_profile),
            "going": meeting_intelligence.get("going", ""),
            "track_bias": meeting_intelligence.get("bias_summary", ""),
        },
        "horses": {},
    }
    matches = list(HORSE_HEADER_RE.finditer(text))
    # BUGFIX guard: every "### 馬匹 #N" block must parse. If the strict header regex
    # matches fewer than the raw horse-block count, a runner is being silently
    # dropped from the field (was the unknown-weight bug). Fail loudly instead.
    raw_header_count = len(re.findall(r"^### 馬匹 #\d+ ", text, re.M))
    if raw_header_count != len(matches):
        sys.stderr.write(
            f"⚠️ FIELD MISMATCH in {facts_path.name}: {raw_header_count} horse blocks "
            f"but only {len(matches)} parsed — a runner failed header parsing.\n"
        )
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        block = text[start:end]
        horse_num = match.group(1)
        horse_name = _clean_identity(match.group(2))
        racecard_profile = racecard_profiles.get(_slug(horse_name), {})
        logic["horses"][horse_num] = {
            "horse_name": horse_name,
            "barrier": int(match.group(3)),
            "jockey": _clean_identity(match.group(4)),
            "trainer": _clean_identity(match.group(5)),
            "weight": float(match.group(6)) if match.group(6) else None,
            "rating": racecard_profile.get("horse_rating"),
            "career_race_starts": _extract_career_starts(block),
            "career_tag": _extract_career_tag(block),
            "tactical_plan": _build_tactical_plan(int(match.group(3)), block),
            "_data": {
                "horse_rating": racecard_profile.get("horse_rating"),
                "facts_section": block,
                # Full racenet PuntingForm metrics recovered from the Formguide
                # (race_time_diff / l600_delta / rt_rating / paces). Stored for
                # future feature-testing; not yet consumed by the scorer.
                "pf_metrics": pf_by_horse.get(horse_num, {}),
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


def _extract_race_meta(facts_path: Path, text: str) -> tuple[str, str, int]:
    distance_match = re.search(r"今仗距離:\s*([0-9]+m)", text)
    distance = distance_match.group(1) if distance_match else ""
    racecard_candidates = list(facts_path.parent.glob(f"*Race {_extract_race_number(facts_path.name, text)} Racecard.md"))
    race_class = ""
    prize = 0
    if racecard_candidates:
        header = racecard_candidates[0].read_text(encoding="utf-8").splitlines()[0]
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


def _normalize_horse_name(name: str) -> str:
    return _slug(re.sub(r"\s*\([^)]*\)", "", str(name or "")))


def _load_racecard_profiles(facts_path: Path, race_number: int) -> dict[str, dict]:
    candidates = sorted(facts_path.parent.glob(f"*Race {race_number} Racecard.md"))
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
        "expected_pace": field("expected_pace"),
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
    meeting_path = facts_path.parent / "_Meeting_Intelligence_Package.md"
    if meeting_path.exists():
        text = meeting_path.read_text(encoding="utf-8")
        intelligence = _parse_meeting_intelligence(text, facts_path.parent.name)
    else:
        intelligence = {}
    fallback = _meeting_context_from_extractor_files(facts_path, race_number)
    for key, value in fallback.items():
        if value and not intelligence.get(key):
            intelligence[key] = value
    if fallback:
        intelligence["source"] = _merge_sources(intelligence.get("source"), fallback.get("source"))
    return intelligence


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
    racecards = sorted(folder.glob(f"*Race {race_number} Racecard.md"))
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
    value = re.sub(r"^\d{4}-\d{2}-\d{2}[_\s-]*", "", str(name or "")).strip()
    value = re.sub(r"\bRace\s*\d+.*$", "", value, flags=re.I).strip(" _-")
    value = value.replace("_", " ").strip()
    return value


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
