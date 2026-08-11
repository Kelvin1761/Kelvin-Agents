#!/usr/bin/env python3
"""
hkjc_auto_orchestrator.py — HKJC Wong Choi Auto Orchestrator (V1)
=================================================================
Main entry point for the Python-only deterministic scoring pipeline.
"""

import os
import sys
import json
import argparse
import re
import tempfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

# Add project root and engine to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))

from engine_core import (
    MAINLINE_HEALTH_PROFILE,
    RacingEngine,
    SUPPORTED_HEALTH_PROFILES,
    SUPPORTED_SHADOW_PROFILES,
    scoring_run_contract,
)
from renderer import (
    ensure_verdict,
    prepare_race_outputs,
    render_meeting_csv,
    write_prepared_race_outputs,
)
from scoring import compute_grade
from validation import validate_engine_scripts, validate_logic_data
from full_rank_ml import apply_full_rank_ml
from wongchoi_paths import is_materialized_file

# Optional: horse-profile scraper for multi-season (近三季) readout enrichment.
# DISPLAY-ONLY — failures degrade gracefully and never affect scoring.
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
_PROFILE_SCRAPER = None


def _run_stability_residual_shadow(target_path):
    """Lazy-load the research shadow so default Auto has no ML dependency."""
    reflector_scripts = (
        PROJECT_ROOT
        / ".agents"
        / "skills"
        / "hkjc_racing"
        / "hkjc_reflector"
        / "scripts"
    )
    if str(reflector_scripts) not in sys.path:
        sys.path.append(str(reflector_scripts))
    from hkjc_stability_residual_shadow import run_shadow

    return run_shadow(Path(target_path).resolve())


def _get_profile_scraper():
    """Lazy-load display enrichment so scoring-only runs have no cache side effect."""
    global _PROFILE_SCRAPER
    if _PROFILE_SCRAPER is False:
        return None
    if _PROFILE_SCRAPER is None:
        try:
            from scrape_hkjc_horse_profile import scrape_horse_profile
            _PROFILE_SCRAPER = scrape_horse_profile
        except Exception:
            _PROFILE_SCRAPER = False
            return None
    return _PROFILE_SCRAPER

# class_grade → readable label (graded races vs 班次)
_PROFILE_CLASS_LABEL = {
    "G1": "一級賽", "G2": "二級賽", "G3": "三級賽",
    "1": "第一班", "2": "第二班", "3": "第三班", "4": "第四班", "5": "第五班",
}
_PROFILE_CLASS_ORDER = {
    "一級賽": 1, "二級賽": 2, "三級賽": 3, "上市賽": 4,
    "第一班": 10, "第二班": 11, "第三班": 12, "第四班": 13, "第五班": 14,
}


def _race_file_sort_key(path):
    match = re.search(r"Race_(\d+)_Logic\.json$", path.name, re.I)
    return (int(match.group(1)) if match else 10**9, path.name)


def _atomic_write_json(path, data):
    path = Path(path)
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, path)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def _profile_season_key(date_str):
    """HK racing season (Sep–Aug) start year from a dd/mm/yy date."""
    parsed = _profile_entry_date(date_str)
    if parsed is None:
        return None
    return parsed.year if parsed.month >= 9 else parsed.year - 1


def _style_from_positions(positions, field_size=12):
    """Single-race tactical style from in-race positions (mirrors the engine's
    position fallback): 前置 / 守好位 / 守中 / 後上."""
    if not positions:
        return None
    fp = positions[0] if isinstance(positions[0], int) else None
    if not fp or fp <= 0:
        return None
    mid_cut = max(int(field_size * 0.55), 4)
    if fp == 1:
        return "前置"
    if fp <= 4:
        return "守好位"
    if fp <= mid_cut:
        return "守中"
    return "後上"


def _profile_entry_date(value):
    text = str(value or "").strip()
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _meeting_date_for_logic(logic_path, race_context):
    for value in (
        race_context.get("race_date"),
        race_context.get("racedate"),
        race_context.get("date"),
    ):
        text = str(value or "").strip().replace("/", "-")
        try:
            return date.fromisoformat(text)
        except ValueError:
            pass
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", str(Path(logic_path).parent))
    return date.fromisoformat(match.group(1)) if match else None


def _enrich_profile_history(horses, *, as_of_date=None):
    """Inject point-in-time multi-season fields from the horse profile page:
    近三季 per-class average finish, season-start + 近三季 high/low rating, and a
    近6仗 running-style breakdown. Never raises."""
    scrape_horse_profile = _get_profile_scraper()
    if scrape_horse_profile is None:
        return
    for h_obj in horses.values():
        if not isinstance(h_obj, dict):
            continue
        tw = h_obj.get("trackwork")
        hid = tw.get("horseid") if isinstance(tw, dict) else None
        if not hid:
            continue
        try:
            ents = (scrape_horse_profile(hid) or {}).get("entries") or []
        except Exception:
            continue
        if as_of_date is not None:
            # Strictly pre-race. The current meeting's result may already be on
            # the profile page when an archive is rescored later that day.
            ents = [
                entry
                for entry in ents
                if (entry_date := _profile_entry_date(entry.get("date"))) is not None
                and entry_date < as_of_date
            ]
        if not ents:
            continue
        data = h_obj.setdefault("_data", {})
        seasons = sorted({s for s in (_profile_season_key(e.get("date")) for e in ents) if s},
                         reverse=True)[:3]
        recent = [e for e in ents if _profile_season_key(e.get("date")) in seasons] if seasons else ents
        buckets, ratings = {}, []
        for e in recent:
            lbl = _PROFILE_CLASS_LABEL.get(str(e.get("class_grade") or "").strip(),
                                           str(e.get("class_grade") or "").strip())
            pl = e.get("placing")
            if lbl and isinstance(pl, int) and pl > 0:
                buckets.setdefault(lbl, []).append(pl)
            rt = e.get("rating")
            if isinstance(rt, int) and rt > 0:
                ratings.append(rt)
        if buckets:
            parts = [f"{lbl} 平均{sum(v) / len(v):.1f}名（{len(v)}場）"
                     for lbl, v in sorted(buckets.items(), key=lambda kv: _PROFILE_CLASS_ORDER.get(kv[0], 99))]
            data["class_perf_3s"] = " ｜ ".join(parts)
        if ratings:
            data["rating_high_3s"] = max(ratings)
            data["rating_low_3s"] = min(ratings)
        history = []
        for entry in ents[:12]:
            history.append({
                "date": entry.get("date") or entry.get("race_date_full") or "",
                "rating": entry.get("rating") if isinstance(entry.get("rating"), int) else None,
                "class_grade": str(entry.get("class_grade") or "").strip(),
                "distance": entry.get("distance") if isinstance(entry.get("distance"), int) else None,
                "placing": entry.get("placing") if isinstance(entry.get("placing"), int) else None,
            })
        if history:
            data["rating_class_history"] = history
            data["rating_history_samples"] = sum(
                1 for row in history if isinstance(row.get("rating"), int) and row["rating"] > 0
            )
            recent_ratings = [
                row["rating"] for row in history[:6]
                if isinstance(row.get("rating"), int) and row["rating"] > 0
            ]
            if len(recent_ratings) >= 2:
                # Positive means the official rating has risen from the older
                # observation to the most recent pre-race observation.
                data["rating_delta_recent"] = recent_ratings[0] - recent_ratings[-1]
        if seasons:
            cur = [e["rating"] for e in ents
                   if _profile_season_key(e.get("date")) == seasons[0]
                   and isinstance(e.get("rating"), int) and e["rating"] > 0]
            if cur:
                data["rating_season_start"] = cur[-1]  # earliest race of current season
        style_counts = {}
        for e in ents[:6]:
            st = _style_from_positions(e.get("running_positions"))
            if st:
                style_counts[st] = style_counts.get(st, 0) + 1
        if style_counts:
            order = ["前置", "守好位", "守中", "後上"]
            data["style_breakdown_6"] = "、".join(
                f"{style_counts[st]}場{st}" for st in order if style_counts.get(st))
        # Jockey change vs LAST start (authoritative: entries[0] = most recent race).
        # Only flag a real change, and if the new rider has ridden THIS horse before,
        # report the horse's running style under that rider.
        declared = str(h_obj.get("jockey") or "").strip()
        last_j = str(ents[0].get("jockey") or "").strip()
        if declared and last_j and declared != last_j:
            prior = [e for e in ents if str(e.get("jockey") or "").strip() == declared]
            if prior:
                wins = sum(1 for e in prior if e.get("placing") == 1)
                pstyles = Counter(s for s in (_style_from_positions(e.get("running_positions"))
                                              for e in prior) if s)
                sstr = "、".join(f"{n}次{st}" for st, n in pstyles.most_common())
                win_txt = f"，{wins}勝" if wins else ""
                style_txt = f"，跑法：{sstr}" if sstr else ""
                data["jockey_change_note"] = (
                    f"今仗轉用騎師{declared}（曾策此駒{len(prior)}次{win_txt}{style_txt}）")
            else:
                data["jockey_change_note"] = f"今仗轉用騎師{declared}（與此駒首次合作）"


def _safe_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _relative_field_scores(values, *, higher_is_better):
    """Map full-field evidence to a 45–75 competitiveness band."""
    if len(values) < 2:
        return {horse_num: 60.0 for horse_num in values}
    output = {}
    for horse_num, value in values.items():
        others = [
            other_value
            for other_horse, other_value in values.items()
            if other_horse != horse_num
        ]
        worse = sum(
            other_value < value if higher_is_better else other_value > value
            for other_value in others
        )
        ties = sum(other_value == value for other_value in others)
        output[horse_num] = 45.0 + 30.0 * (worse + 0.5 * ties) / len(others)
    return output


def _enrich_relative_high_quality_scores(horses):
    """Build evidence-only rating and normalized-sectional field scores.

    Missing evidence leaves the score absent, so it cannot drag an existing
    matrix dimension toward a neutral default.
    """
    rating_gaps = {}
    rating_samples = {}
    l400_values = {}
    total_values = {}
    sectional_samples = {}

    for horse_num, horse_obj in horses.items():
        if not isinstance(horse_obj, dict):
            continue
        data = horse_obj.setdefault("_data", {})
        if not isinstance(data, dict):
            continue
        current_rating = _safe_float(data.get("current_rating"))
        profile_history = data.get("rating_class_history")
        if isinstance(profile_history, list):
            recent_ratings = [
                _safe_float(row.get("rating"))
                for row in profile_history[:6]
                if isinstance(row, dict)
            ]
            recent_ratings = [value for value in recent_ratings if value is not None]
        else:
            recent_ratings = []
        if not recent_ratings:
            source_series = data.get("rating_series")
            if isinstance(source_series, list):
                recent_ratings = [
                    value
                    for value in (_safe_float(item) for item in source_series[:6])
                    if value is not None
                ]
        if current_rating is not None and recent_ratings:
            rating_gaps[str(horse_num)] = current_rating - max(recent_ratings)
            rating_samples[str(horse_num)] = len(recent_ratings)
            data["rating_recent_peak"] = max(recent_ratings)
            data["rating_peak_gap"] = rating_gaps[str(horse_num)]

        l400 = _safe_float(data.get("sectional_normalized_l400_delta"))
        total = _safe_float(data.get("sectional_normalized_total_delta"))
        samples = _safe_float(data.get("sectional_normalized_samples")) or 0.0
        if samples > 0:
            sectional_samples[str(horse_num)] = samples
            if l400 is not None:
                l400_values[str(horse_num)] = l400
            if total is not None:
                total_values[str(horse_num)] = total

    rating_relative = _relative_field_scores(rating_gaps, higher_is_better=True)
    for horse_num, relative_score in rating_relative.items():
        reliability = rating_samples[horse_num] / (rating_samples[horse_num] + 2.0)
        data = horses[horse_num]["_data"]
        data["rating_near_peak_reliability"] = round(reliability, 4)
        data["rating_near_peak_score"] = round(
            60.0 + reliability * (relative_score - 60.0),
            4,
        )

    l400_relative = _relative_field_scores(l400_values, higher_is_better=False)
    total_relative = _relative_field_scores(total_values, higher_is_better=False)
    for horse_num in set(l400_relative) | set(total_relative):
        reliability = sectional_samples[horse_num] / (
            sectional_samples[horse_num] + 2.0
        )
        available = []
        if horse_num in l400_relative:
            available.append((l400_relative[horse_num], 0.6))
        if horse_num in total_relative:
            available.append((total_relative[horse_num], 0.4))
        total_weight = sum(weight for _, weight in available)
        relative_score = sum(
            score * weight for score, weight in available
        ) / total_weight
        data = horses[horse_num]["_data"]
        data["sectional_normalized_reliability"] = round(reliability, 4)
        data["sectional_normalized_score"] = round(
            60.0 + reliability * (relative_score - 60.0),
            4,
        )


CLASS_RANK_MAP = {
    "一級賽": 0,
    "二級賽": 1,
    "三級賽": 2,
    "第一班": 3,
    "第二班": 4,
    "第三班": 5,
    "第四班": 6,
    "第五班": 7,
    "C1": 3,
    "C2": 4,
    "C3": 5,
    "C4": 6,
    "C5": 7,
}

def _apply_sip_enhancements(horses):
    """
    SIP-C: B- horse with light weight + good draw → +1.5 ability_score
    SIP-A: C+/C/C- horse with ≥2 positive signals → +2.0 ability_score
    """
    weights = []
    for h_obj in horses.values():
        w = h_obj.get("weight")
        if w is not None:
            try:
                weights.append(int(w))
            except (ValueError, TypeError):
                pass
    if not weights:
        return
    field_median = sorted(weights)[len(weights) // 2]

    for h_num, h_obj in horses.items():
        auto = h_obj.get("python_auto", {})
        if not auto:
            continue
        weight = h_obj.get("weight")
        barrier = h_obj.get("barrier")
        try:
            weight_val = int(weight) if weight is not None else None
            barrier_val = int(barrier) if barrier is not None else None
        except (ValueError, TypeError):
            continue
        if weight_val is None or barrier_val is None:
            continue

        fs = auto.get("feature_scores", {})
        _apply_sip_to_score(auto, fs, weight_val, barrier_val, field_median)
        for shadow in (auto.get("shadow_profiles") or {}).values():
            if isinstance(shadow, dict):
                _apply_sip_to_score(shadow, fs, weight_val, barrier_val, field_median)


def _apply_sip_to_score(target, feature_scores, weight_val, barrier_val, field_median):
    """Apply the same downstream SIP rule independently to one score profile."""
    grade = target.get("grade", "")
    ability_score = float(target.get("ability_score", 0) or 0)
    is_light = weight_val <= field_median
    is_good_draw = barrier_val <= 5
    speed = feature_scores.get("speed_score", 0)
    form = feature_scores.get("form_score", 0)
    consist = feature_scores.get("consistency_score", 0)
    boost = 0.0
    reasons = []
    if grade == "B-" and is_light and is_good_draw:
        if speed >= 68 or (form >= 55 and consist >= 55):
            boost = 1.0
            reasons.append("輕磅+好檔+速度/穩定性(SIP-C)")
    if boost <= 0:
        return
    target["ability_score"] = round(ability_score + boost, 2)
    target["grade"] = compute_grade(target["ability_score"])
    target.setdefault("sip_flags", []).append({
        "reason": "; ".join(reasons),
        "boost": round(boost, 1),
        "original_score": ability_score,
        "original_grade": grade,
    })


def _class_rank(text):
    content = str(text or "").strip()
    if not content:
        return None
    ranks = [rank for token, rank in CLASS_RANK_MAP.items() if token in content]
    return min(ranks) if ranks else None


def _class_bucket(class_text, current_rank):
    target_rank = _class_rank(class_text)
    if target_rank is None or current_rank is None:
        return "unknown"
    if target_rank < current_rank:
        return "higher"
    if target_rank > current_rank:
        return "lower"
    return "same"


def _pretty_class_text(text):
    return "/".join(part for part in str(text or "").split() if part)


def _format_followup_example(item):
    class_text = _pretty_class_text(item["class_text"])
    if item["wins"] <= 1:
        return f"{item['name']}其後於{class_text}再贏"
    return f"{item['name']}其後於{class_text}再贏{item['wins']}場"


def _format_followup_bucket_summary(counts):
    parts = []
    if counts.get("higher"):
        parts.append(f"當中有{counts['higher']}匹其後升上更高班仍能再贏")
    if counts.get("same"):
        parts.append(f"{counts['same']}匹其後於同班再贏")
    if counts.get("lower"):
        parts.append(f"{counts['lower']}匹其後於較低班再贏")
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return "；".join(parts[:-1]) + "；另有" + parts[-1]


def _unique_materialized_match(logic_path, pattern, label):
    matches = [
        path
        for path in sorted(logic_path.parent.glob(pattern))
        if is_materialized_file(path)
    ]
    if len(matches) > 1:
        names = ", ".join(path.name for path in matches)
        raise ValueError(f"multiple {label} files match {logic_path.name}: {names}")
    return matches[0] if matches else None


def _facts_path_for_logic(logic_path, race_number):
    if race_number in (None, ""):
        return None
    return _unique_materialized_match(
        logic_path, f"*Race {race_number} Facts.md", "Facts"
    )


def _trackwork_path_for_logic(logic_path, race_number):
    if race_number in (None, ""):
        return None
    return _unique_materialized_match(
        logic_path, f"*Race {race_number} 晨操.md", "trackwork"
    )


def _racecard_path_for_logic(logic_path, race_number):
    if race_number in (None, ""):
        return None
    return _unique_materialized_match(
        logic_path, f"*Race {race_number} 排位表.md", "racecard"
    )


def _parse_racecard_meta(text):
    """Read the authoritative race class + each runner's CURRENT official rating
    and the official rating CHANGE since last start (評分+/-) from the racecard
    (排位表.md). The Facts header can mis-label graded races (三級賽/二級賽/一級賽)
    as a default 'C4', so the racecard wins for display. The 評分+/- is the real
    last-race delta (previous rating = current - change) — more reliable than the
    rating_trend tail, which is ordered newest→oldest."""
    race_class = ""
    cm = re.search(r"班次:\s*(.+)", text)
    if cm and cm.group(1).strip():
        race_class = cm.group(1).strip()
    info = {}
    numbered_blocks = list(
        re.finditer(r"^馬號:\s*\d+.*?(?=^馬號:\s*\d+|\Z)", text, re.M | re.S)
    )
    blocks = (
        [match.group(0) for match in numbered_blocks]
        if numbered_blocks
        else re.split(r"(?=馬名:\s*)", text)
    )
    for block in blocks:
        nm = re.search(r"馬名:\s*(.+)", block)
        number = re.search(r"^馬號:\s*(\d+)", block, re.M)
        rt = re.search(r"^評分:\s*(\d+)", block, re.M)
        if nm:
            ch = re.search(r"^評分\+/-:\s*(-?\d+)", block, re.M)
            jockey = re.search(r"^騎師:\s*(.+)", block, re.M)
            trainer = re.search(r"^練馬師:\s*(.+)", block, re.M)
            declared_weight = re.search(r"^負磅:\s*(\d+)", block, re.M)
            barrier = re.search(r"^檔位:\s*(\d+)", block, re.M)
            horse_id = re.search(r"^HKJC馬匹ID:\s*(HK_\d{4}_[A-HJ-Z]\d{3})", block, re.M | re.I)
            profile_url = re.search(r"^官方馬匹資料:\s*(\S+)", block, re.M)
            horse_code = re.search(r"^烙號:\s*([A-HJ-Z]\d{3})", block, re.M | re.I)
            jockey_text = jockey.group(1).strip() if jockey else ""
            claim_match = re.search(r"\(\s*(-\d+)\s*\)\s*$", jockey_text)
            claim = abs(int(claim_match.group(1))) if claim_match else 0
            effective_weight = (
                int(declared_weight.group(1)) - claim
                if declared_weight
                else None
            )
            entry = {
                "horse_name": nm.group(1).strip(),
                "jockey": re.sub(r"\s*\(\s*-\d+\s*\)\s*$", "", jockey_text).strip(),
                "trainer": trainer.group(1).strip() if trainer else None,
                "weight": effective_weight,
                "barrier": int(barrier.group(1)) if barrier else None,
                "jockey_claim": claim,
                "rating": int(rt.group(1)) if rt else None,
                "change": int(ch.group(1)) if ch else None,
                "horse_code": horse_code.group(1).upper() if horse_code else None,
                "hkjc_horse_id": horse_id.group(1).upper() if horse_id else None,
                "horse_profile_url": profile_url.group(1).strip() if profile_url else None,
            }
            info[nm.group(1).strip()] = entry
            if number:
                info[number.group(1)] = entry
    return race_class, info


def _section_for_horse(text, horse_number):
    pattern = re.compile(
        rf"^### 馬號 {re.escape(str(horse_number))} — .*?(?=^### 馬號 \d+ — |\Z)",
        re.M | re.S,
    )
    match = pattern.search(text)
    return match.group(0) if match else ""


def _parse_formline_rows(section_text):
    marker = "🔗 **賽績線:**"
    start = section_text.find(marker)
    if start < 0:
        return []
    lines = section_text[start:].splitlines()
    rows = []
    in_table = False
    for line in lines:
        if line.startswith("| # | 日期 | 賽事 |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.startswith("|"):
            break
        if set(line.replace("|", "").strip()) == {"-"}:
            continue
        cols = [part.strip() for part in line.strip().strip("|").split("|")]
        if len(cols) < 8:
            continue
        rows.append(
            {
                "opponent": cols[4],
                "class_text": cols[5],
                "result_text": cols[6],
            }
        )
    return rows


def _build_formline_opponent_summary(rows, current_rank):
    winners = {}
    for row in rows:
        match = re.search(r"出\s*\d+\s*次:\s*(\d+)\s*勝", row["result_text"])
        if not match:
            continue
        wins = int(match.group(1))
        if wins <= 0:
            continue
        name_match = re.search(r"\]\s*([^(]+)", row["opponent"])
        name = (name_match.group(1) if name_match else row["opponent"]).strip()
        if not name:
            continue
        bucket = _class_bucket(row["class_text"], current_rank)
        class_rank = _class_rank(row["class_text"])
        candidate = {
            "name": name,
            "wins": wins,
            "bucket": bucket,
            "class_rank": 99 if class_rank is None else class_rank,
            "class_text": row["class_text"],
        }
        existing = winners.get(name)
        if existing is None or (candidate["wins"], -candidate["class_rank"]) > (existing["wins"], -existing["class_rank"]):
            winners[name] = candidate
    if not winners:
        return {}

    bucket_order = {"higher": 0, "same": 1, "lower": 2, "unknown": 3}
    items = sorted(
        winners.values(),
        key=lambda item: (bucket_order.get(item["bucket"], 9), -item["wins"], item["class_rank"], item["name"]),
    )
    top_items = items[:2]
    highlight = "、".join(_format_followup_example(item) for item in top_items)
    counts = Counter(item["bucket"] for item in items)
    summary = f"對手後續交代: {highlight}"
    bucket_summary = _format_followup_bucket_summary(counts)
    if bucket_summary:
        summary += f"。整體睇，{bucket_summary}。"
    else:
        summary += "。"
    return {
        "formline_opponent_highlight": highlight,
        "formline_opponent_summary": summary,
        "formline_higher_win_count": counts.get("higher", 0),
        "formline_same_win_count": counts.get("same", 0),
        "formline_lower_win_count": counts.get("lower", 0),
    }


def _clean_anchor_value(value):
    text = str(value or "").strip()
    if text in {"", "N/A", "未知", "?", "？"}:
        return ""
    return text


def _parse_horse_headers(text):
    pattern = re.compile(
        r"^### 馬號\s*(\d+)\s*—\s*(.+?)\s*\|\s*騎師:\s*(.+?)(?:\s*\|\s*練馬師:\s*(.+?))?(?:\s*\|\s*負磅:\s*(\d+))?(?:\s*\|\s*檔位:\s*(\d+))?\s*$",
        re.M,
    )
    anchors = {}
    for match in pattern.finditer(text):
        horse_num = match.group(1).strip()
        entry = anchors.setdefault(horse_num, {})
        for key, group_idx in (
            ("horse_name", 2),
            ("jockey", 3),
            ("trainer", 4),
            ("weight", 5),
            ("barrier", 6),
        ):
            value = _clean_anchor_value(match.group(group_idx))
            if value:
                entry[key] = value
    return anchors


def _load_header_anchor_map(logic_path, race_context):
    race_number = race_context.get("race_number")
    anchors = {}
    # Trackwork is a fallback. Facts is generated from the complete pre-race
    # dataset and wins if the two documents disagree.
    for source_path in (
        _trackwork_path_for_logic(logic_path, race_number),
        _facts_path_for_logic(logic_path, race_number),
    ):
        if not source_path or not source_path.exists():
            continue
        parsed = _parse_horse_headers(source_path.read_text(encoding="utf-8"))
        for horse_num, values in parsed.items():
            merged = anchors.setdefault(str(horse_num), {})
            for key, value in values.items():
                if _clean_anchor_value(value):
                    merged[key] = value
    return anchors


def _enrich_horse_headers(horses, anchor_map, *, keep_embedded_combo_prior=False):
    for horse_num, horse_obj in horses.items():
        if not isinstance(horse_obj, dict):
            continue
        anchors = anchor_map.get(str(horse_num), {})
        for field in ("horse_name", "jockey", "trainer", "weight", "barrier"):
            fallback = _clean_anchor_value(anchors.get(field))
            if fallback:
                horse_obj[field] = fallback
        data = horse_obj.setdefault("_data", {})
        if isinstance(data, dict):
            if not keep_embedded_combo_prior:
                # Legacy Auto injected a reflector-wide "Full" prior here.
                # Remove it so production has one deterministic prior resolver.
                data.pop("jockey_trainer_combo_prior", None)
            if _clean_anchor_value(horse_obj.get("jockey")):
                data["jockey_name"] = horse_obj.get("jockey")
            if _clean_anchor_value(horse_obj.get("trainer")):
                data["trainer_name"] = horse_obj.get("trainer")
            if _clean_anchor_value(horse_obj.get("weight")):
                data["weight_carried"] = horse_obj.get("weight")
            # Scoring priors are resolved centrally by RacingEngine.  Do not
            # inject reflector "Full" priors here: doing so made the same Logic
            # score differently merely because a Facts file happened to exist.


def _align_runner_headers(logic_path, race_context, horses):
    """Canonicalize runner identity once before any scoring context is derived."""
    _enrich_horse_headers(
        horses,
        _load_header_anchor_map(logic_path, race_context),
    )

    racecard_path = _racecard_path_for_logic(logic_path, race_context.get("race_number"))
    if racecard_path and racecard_path.exists():
        rc_class, rc_info = _parse_racecard_meta(
            racecard_path.read_text(encoding="utf-8")
        )
        if rc_class:
            race_context["race_class"] = rc_class
        official_numbers = {key for key in rc_info if str(key).isdigit()}
        logic_numbers = {str(key) for key in horses}
        if official_numbers and official_numbers != logic_numbers:
            number_key = lambda value: (
                0,
                int(value),
            ) if str(value).isdigit() else (1, str(value))
            raise ValueError(
                "runner set differs between Logic and racecard: "
                f"Logic={sorted(logic_numbers, key=number_key)}, "
                f"racecard={sorted(official_numbers, key=number_key)}"
            )
        for horse_num, horse_obj in horses.items():
            if not isinstance(horse_obj, dict):
                continue
            info = rc_info.get(str(horse_num)) or rc_info.get(horse_obj.get("horse_name"))
            if not info:
                continue
            for field in ("horse_name", "jockey", "trainer", "weight", "barrier"):
                if info.get(field) not in (None, ""):
                    horse_obj[field] = info[field]
            for field in ("horse_code", "hkjc_horse_id", "horse_profile_url"):
                if info.get(field):
                    horse_obj[field] = info[field]
            if info.get("rating") is not None:
                data = horse_obj.setdefault("_data", {})
                data["current_rating"] = info["rating"]
                if info.get("change") is not None:
                    data["rating_change"] = info["change"]

    # Mirror authoritative top-level values into _data after racecard overrides.
    _enrich_horse_headers(horses, {})
    race_context["field_horse_names"] = [
        horse.get("horse_name")
        for horse in horses.values()
        if isinstance(horse, dict) and horse.get("horse_name")
    ]


def _load_formline_opponent_summaries(logic_path, race_context, horses):
    facts_path = _facts_path_for_logic(logic_path, race_context.get("race_number"))
    if not facts_path or not facts_path.exists():
        return {}
    text = facts_path.read_text(encoding="utf-8")
    current_rank = _class_rank(race_context.get("race_class"))
    summaries = {}
    for horse_num in horses.keys():
        section = _section_for_horse(text, horse_num)
        if not section:
            continue
        rows = _parse_formline_rows(section)
        summary = _build_formline_opponent_summary(rows, current_rank)
        if summary:
            summaries[str(horse_num)] = summary
    return summaries

class HKJCAutoOrchestrator:
    def __init__(
        self,
        target_path,
        scoring_profile="mainline",
        shadow_profile=None,
        health_profile=MAINLINE_HEALTH_PROFILE,
        stability_residual_shadow=False,
        matrix_only=False,
    ):
        self.target_path = Path(target_path)
        self.is_meeting = self.target_path.is_dir()
        self.scoring_profile = scoring_profile
        self.shadow_profile = shadow_profile
        self.health_profile = health_profile
        self.stability_residual_shadow = bool(stability_residual_shadow)
        self.matrix_only = bool(matrix_only)
        self.races = []
        self.log_path = (self.target_path if self.is_meeting else self.target_path.parent) / "racing_run_log.jsonl"
        self.summary_path = (self.target_path if self.is_meeting else self.target_path.parent) / "evaluation_summary.json"
        
    def run(self):
        print(f"🚀 Starting HKJC Wong Choi Auto scoring on: {self.target_path}")
        if self.validate_engine():
            return 1
        
        if self.is_meeting:
            logic_files = sorted(
                self.target_path.glob("Race_*_Logic.json"),
                key=_race_file_sort_key,
            )
            if not logic_files:
                print(f"❌ No Race_*_Logic.json files found in {self.target_path}")
                return 1
            self.races = logic_files
        else:
            if not self.target_path.name.endswith("_Logic.json"):
                print(f"❌ Target {self.target_path} is not a Logic JSON file.")
                return 1
            self.races = [self.target_path]
        self._emit_event(
            "run_started",
            target=str(self.target_path),
            scoring_profile=self.scoring_profile,
            shadow_profile=self.shadow_profile,
            health_profile=self.health_profile,
            race_count=len(self.races),
            is_meeting=self.is_meeting,
            ranking_mode="matrix_only" if self.matrix_only else "matrix_ml_hybrid",
        )
            
        results = []
        failed = []
        for race_file in self.races:
            try:
                result = self.score_race(race_file)
            except Exception as exc:
                print(f"❌ {race_file.name}: unhandled scoring error: {exc}")
                result = None
            if result:
                results.append(result)
            else:
                failed.append(race_file.name)

        if self.is_meeting and results:
            meeting_csv = self.target_path / "HKJC_Auto_Scoring.csv"
            meeting_csv.write_text(render_meeting_csv(results), encoding="utf-8")
            print(f"📄 Meeting CSV: {meeting_csv}")
            summary = self._write_evaluation_summary(results)
            self._emit_event(
                "evaluation_completed",
                summary_path=str(self.summary_path),
                kpis=summary.get("kpis", {}),
            )
            
        if failed:
            print("\n❌ HKJC Wong Choi Auto completed with failed races:")
            for name in failed:
                print(f"   - {name}")
            return 1

        if self.stability_residual_shadow:
            try:
                shadow_csv, shadow_json, shadow_report = _run_stability_residual_shadow(
                    self.target_path
                )
            except Exception as exc:
                print(f"\n❌ Stability residual shadow failed: {exc}")
                self._emit_event(
                    "stability_residual_shadow_failed",
                    error=str(exc),
                )
                return 1
            print(f"📄 Stability residual shadow CSV: {shadow_csv}")
            print(f"📄 Stability residual shadow JSON: {shadow_json}")
            self._emit_event(
                "stability_residual_shadow_completed",
                csv_path=str(shadow_csv),
                json_path=str(shadow_json),
                model_version=shadow_report.get("model_version"),
                race_count=len(shadow_report.get("races") or []),
                mainline_modified=False,
            )

        print("\n✅ HKJC Wong Choi Auto scoring completed.")
        return 0

    def validate_engine(self):
        if not getattr(self, "_validate_engine_requested", False):
            return []
        errors = []
        errors.extend(validate_engine_scripts(SCRIPT_DIR))
        if errors:
            print("\n❌ Engine validation failed:")
            for error in errors:
                print(f"   - {error}")
            return errors
        print("✅ Engine validation passed.")
        return []

    def score_race(self, race_file):
        print(f"\n📊 Scoring {race_file.name}...")
        if not is_materialized_file(race_file):
            print(f"❌ Logic file is not materialized locally: {race_file}")
            return None
        try:
            with open(race_file, "r", encoding="utf-8") as f:
                logic_data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load {race_file}: {e}")
            return

        race_context = logic_data.get("race_analysis", {})
        horses = logic_data.get("horses", {})
        if isinstance(race_context, dict):
            _align_runner_headers(race_file, race_context, horses)
            # 近三季 profile enrichment (display-only; graceful if offline)
            meeting_date = _meeting_date_for_logic(race_file, race_context)
            if meeting_date is not None:
                race_context["race_date"] = meeting_date.isoformat()
            _enrich_profile_history(
                horses,
                as_of_date=meeting_date,
            )
            _enrich_relative_high_quality_scores(horses)
        formline_summaries = _load_formline_opponent_summaries(race_file, race_context, horses)
        for h_num, summary in formline_summaries.items():
            horse_obj = horses.get(h_num)
            if not isinstance(horse_obj, dict):
                continue
            data = horse_obj.setdefault("_data", {})
            if isinstance(data, dict):
                data.update(summary)
        
        for h_num, h_obj in horses.items():
            h_name = h_obj.get("horse_name", "Unknown")
            print(f"   - Scoring Horse {h_num}: {h_name}")
            
            engine = RacingEngine(h_obj, race_context, health_profile=self.health_profile)
            result = engine.analyze_horse()
            shadow = self._build_shadow_profile(engine, result)
            if shadow:
                result.setdefault("shadow_profiles", {})[shadow["profile"]] = shadow
            
            h_obj["python_auto"] = result
            self._emit_event(
                "horse_scored",
                race_file=race_file.name,
                race_number=race_context.get("race_number"),
                horse_number=str(h_num),
                horse_name=h_name,
                ability_score=result.get("ability_score"),
                grade=result.get("grade"),
                shadow_profile=shadow["profile"] if shadow else "",
                shadow_ability_score=shadow.get("ability_score") if shadow else "",
                health_profile=self.health_profile,
            )
            # Also update the classic matrix if requested (optional rule)
            # h_obj["matrix"] = result["matrix"]
            
        _apply_sip_enhancements(horses)

        if self.matrix_only:
            logic_data.pop("python_auto_ranking_contract", None)
        else:
            try:
                ranking_contract = apply_full_rank_ml(logic_data)
            except Exception as exc:
                print(f"❌ Full-rank ML failed closed for {race_file.name}: {exc}")
                self._emit_event(
                    "full_rank_ml_failed",
                    race_file=race_file.name,
                    race_number=race_context.get("race_number"),
                    error=str(exc),
                )
                return None
            self._emit_event(
                "full_rank_ml_applied",
                race_file=race_file.name,
                race_number=race_context.get("race_number"),
                ranking_version=ranking_contract.get("version"),
                matrix_weight=ranking_contract.get("matrix_weight"),
                ml_weight=ranking_contract.get("ml_weight"),
                model_sha256=ranking_contract.get("model_sha256"),
            )

        ensure_verdict(logic_data)
        self._finalize_shadow_profiles(logic_data)
        logic_data["python_auto_run_contract"] = scoring_run_contract()
            
        logic_errors = validate_logic_data(logic_data)
        if logic_errors:
            print("❌ Logic validation failed:")
            for error in logic_errors:
                print(f"   - {error}")
            return None

        # Build and validate every derived artifact before replacing any
        # last-known-good file.
        try:
            prepared_outputs = prepare_race_outputs(race_file, logic_data)
            _atomic_write_json(race_file, logic_data)
            print(f"   ✅ Updated {race_file.name}")
            md_path, csv_path = write_prepared_race_outputs(prepared_outputs)
            print(f"   📄 Markdown: {md_path.name}")
            print(f"   📄 CSV: {csv_path.name}")
            return logic_data
        except Exception as e:
            print(f"❌ Failed to write outputs for {race_file}: {e}")
            return None

    def _emit_event(self, event_type, **payload):
        record = {"event_type": event_type, **payload}
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_evaluation_summary(self, results):
        actual = self._load_meeting_results()
        kpis = {"gold": 0, "good": 0, "min_threshold": 0, "single": 0, "champion": 0}
        shadow_profile_stats = {}
        evaluated_races = 0
        for logic_data in results:
            race_number = str((logic_data.get("race_analysis") or {}).get("race_number") or "")
            actual_top3 = actual.get(race_number, [])
            if not actual_top3:
                continue
            evaluated_races += 1
            ranked = sorted(
                (
                    (
                        int(horse_num),
                        horse_data.get("python_auto", {}).get("rank", 999),
                        horse_data.get("python_auto", {}).get("ability_score", 0.0),
                    )
                    for horse_num, horse_data in (logic_data.get("horses") or {}).items()
                ),
                key=lambda item: (item[1], -item[2], item[0]),
            )
            picks = [horse_num for horse_num, _rank, _ability in ranked[:3]]
            actual_top3_set = set(actual_top3)
            hits_in_top3 = sum(1 for horse_num in picks[:3] if horse_num in actual_top3_set)
            top2_hits = sum(1 for horse_num in picks[:2] if horse_num in actual_top3_set)
            if hits_in_top3 == 3:
                kpis["gold"] += 1
            if top2_hits == 2:
                kpis["good"] += 1
            if hits_in_top3 >= 2:
                kpis["min_threshold"] += 1
            if hits_in_top3 >= 1:
                kpis["single"] += 1
            if picks and actual_top3 and picks[0] == actual_top3[0]:
                kpis["champion"] += 1
            for profile_name, verdict in (logic_data.get("python_auto_shadow_verdicts") or {}).items():
                shadow_stats = shadow_profile_stats.setdefault(
                    profile_name,
                    {"gold": 0, "good": 0, "min_threshold": 0, "single": 0, "champion": 0, "races": 0},
                )
                shadow_picks = []
                for item in verdict.get("top4", []):
                    try:
                        shadow_picks.append(int(item.get("horse_number")))
                    except (TypeError, ValueError):
                        continue
                if not shadow_picks:
                    continue
                shadow_stats["races"] += 1
                shadow_hits_in_top3 = sum(1 for horse_num in shadow_picks[:3] if horse_num in actual_top3_set)
                shadow_top2_hits = sum(1 for horse_num in shadow_picks[:2] if horse_num in actual_top3_set)
                if shadow_hits_in_top3 == 3:
                    shadow_stats["gold"] += 1
                if shadow_top2_hits == 2:
                    shadow_stats["good"] += 1
                if shadow_hits_in_top3 >= 2:
                    shadow_stats["min_threshold"] += 1
                if shadow_hits_in_top3 >= 1:
                    shadow_stats["single"] += 1
                if actual_top3 and shadow_picks[0] == actual_top3[0]:
                    shadow_stats["champion"] += 1

        summary = {
            "scoring_profile": self.scoring_profile,
            "shadow_profile": self.shadow_profile,
            "health_profile": self.health_profile,
            "race_count": len(results),
            "evaluated_race_count": evaluated_races,
            "kpis": kpis,
        }
        if shadow_profile_stats:
            summary["shadow_profiles"] = shadow_profile_stats
        self.summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        return summary

    def _load_meeting_results(self):
        if not self.is_meeting:
            return {}
        result_files = [
            path
            for path in sorted(self.target_path.glob("*全日賽果.json"))
            if is_materialized_file(path)
        ]
        if not result_files:
            return {}
        if len(result_files) > 1:
            print(
                "⚠️ Multiple materialized result files found; "
                "evaluation skipped to avoid mixing meetings: "
                + ", ".join(path.name for path in result_files)
            )
            return {}
        try:
            payload = json.loads(result_files[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        results = {}
        for race_no, race_data in payload.items():
            rows = []
            for row in race_data.get("results", []):
                try:
                    pos = int(row.get("pos"))
                    horse_no = int(row.get("horse_no"))
                except (TypeError, ValueError):
                    continue
                if pos <= 3:
                    rows.append((pos, horse_no))
            rows.sort()
            results[str(race_no)] = [horse_no for _pos, horse_no in rows[:3]]
        return results

    def _build_shadow_profile(self, engine, result):
        if self.shadow_profile not in SUPPORTED_SHADOW_PROFILES:
            return None
        return engine.build_shadow_profile(self.shadow_profile, base_auto=result)

    def _finalize_shadow_profiles(self, logic_data):
        if self.shadow_profile not in SUPPORTED_SHADOW_PROFILES:
            return
        horses = logic_data.get("horses", {})
        ranked = []
        for horse_num, horse in horses.items():
            auto = horse.get("python_auto", {})
            shadow = ((auto.get("shadow_profiles") or {}).get(self.shadow_profile) or {})
            if not shadow:
                continue
            ranked.append(
                {
                    "horse_number": str(horse_num),
                    "horse_name": horse.get("horse_name", ""),
                    "ability_score": float(shadow.get("ability_score", auto.get("ability_score", 0.0))),
                    "grade": shadow.get("grade", ""),
                    "applied": bool(shadow.get("applied")),
                    "reason": shadow.get("reason", ""),
                }
            )
        ranked.sort(key=lambda item: (-item["ability_score"], int(item["horse_number"]) if item["horse_number"].isdigit() else 999))
        promoted = []
        for idx, item in enumerate(ranked, start=1):
            horse = horses[item["horse_number"]]
            auto = horse["python_auto"]
            shadow = auto["shadow_profiles"][self.shadow_profile]
            base_rank = int(auto.get("rank", 999) or 999)
            shadow["ability_delta"] = round(float(shadow.get("ability_score", 0.0)) - float(auto.get("ability_score", 0.0)), 2)
            shadow["rank"] = idx
            shadow["rank_delta"] = base_rank - idx
            shadow["entered_top4"] = idx <= 4 and base_rank > 4
            shadow["entered_top2"] = idx <= 2 and base_rank > 2
            shadow["exited_top2"] = idx > 2 and base_rank <= 2
            item["rank"] = idx
            item["base_rank"] = base_rank
            item["rank_delta"] = shadow["rank_delta"]
            item["entered_top2"] = shadow["entered_top2"]
            item["exited_top2"] = shadow["exited_top2"]
            if shadow["entered_top2"] or shadow["entered_top4"] or shadow["rank_delta"] >= 2:
                promoted.append(item)
        base_top2 = [
            item["horse_number"]
            for item in sorted(ranked, key=lambda item: (item["base_rank"], int(item["horse_number"])))[:2]
        ]
        shadow_top2 = [item["horse_number"] for item in ranked[:2]]
        logic_data.setdefault("python_auto_shadow_verdicts", {})[self.shadow_profile] = {
            "profile": self.shadow_profile,
            "ranking": ranked,
            "top4": ranked[:4],
            "promoted": promoted,
            "base_top2": base_top2,
            "shadow_top2": shadow_top2,
            "top2_changed": set(base_top2) != set(shadow_top2),
            "entered_top2": [item for item in ranked if item.get("entered_top2")],
            "exited_top2": [item for item in ranked if item.get("exited_top2")],
        }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HKJC Wong Choi Auto Orchestrator")
    parser.add_argument("target", help="Path to Race_X_Logic.json or meeting folder")
    parser.add_argument(
        "--validate-engine",
        action="store_true",
        help="Also scan engine source policy; Logic/report validation always runs before files are replaced",
    )
    parser.add_argument("--scoring-profile", default="mainline", help="Observability label for this scoring run")
    parser.add_argument(
        "--health-profile",
        default=MAINLINE_HEALTH_PROFILE,
        choices=SUPPORTED_HEALTH_PROFILES,
        help=(
            f"Horse-health scoring profile (default/current mainline: "
            f"{MAINLINE_HEALTH_PROFILE}; readiness_health_slot remains experimental)"
        ),
    )
    parser.add_argument(
        "--shadow-profile",
        default=None,
        choices=SUPPORTED_SHADOW_PROFILES,
        help="Optional shadow profile to compute without changing mainline ranking",
    )
    parser.add_argument(
        "--stability-residual-shadow",
        action="store_true",
        help=(
            "Write the frozen stability-residual research CSV/JSON after Auto "
            "scoring; never changes mainline ranking or recommendations"
        ),
    )
    parser.add_argument(
        "--matrix-only",
        action="store_true",
        help="Emergency rollback: rank only by 7D Matrix ability and skip full-rank ML",
    )
    args = parser.parse_args()
    
    orchestrator = HKJCAutoOrchestrator(
        args.target,
        scoring_profile=args.scoring_profile,
        shadow_profile=args.shadow_profile,
        health_profile=args.health_profile,
        stability_residual_shadow=args.stability_residual_shadow,
        matrix_only=args.matrix_only,
    )
    orchestrator._validate_engine_requested = args.validate_engine
    raise SystemExit(orchestrator.run())
