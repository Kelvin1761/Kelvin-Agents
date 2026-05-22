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
import csv
from collections import Counter
from pathlib import Path

# Add project root and engine to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[4]
sys.path.append(str(PROJECT_ROOT))
sys.path.append(str(SCRIPT_DIR / "racing_engine"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "hkjc_racing" / "hkjc_reflector" / "scripts"))

from engine_core import RacingEngine
from hkjc_results_db import get_combo_priors_csv
from renderer import ensure_verdict, render_meeting_csv, write_race_outputs
from scoring import compute_grade
from validation import validate_engine_scripts, validate_logic_data


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

COMBO_PRIORS_PATH = get_combo_priors_csv()
_COMBO_PRIORS_CACHE = None


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
        grade = auto.get("grade", "")
        ability_score = auto.get("ability_score", 0)
        weight = h_obj.get("weight")
        barrier = h_obj.get("barrier")
        try:
            weight_val = int(weight) if weight is not None else None
            barrier_val = int(barrier) if barrier is not None else None
        except (ValueError, TypeError):
            continue
        if weight_val is None or barrier_val is None:
            continue

        is_light = weight_val <= field_median
        is_good_draw = barrier_val <= 5
        boost = 0.0
        reasons = []

        fs = auto.get("feature_scores", {})
        speed = fs.get("speed_score", 0)
        form = fs.get("form_score", 0)
        consist = fs.get("consistency_score", 0)

        if grade == "B-" and is_light and is_good_draw:
            if speed >= 68 or (form >= 55 and consist >= 55):
                boost = 1.0
                reasons.append("輕磅+好檔+速度/穩定性(SIP-C)")

        if boost > 0:
            new_score = round(ability_score + boost, 2)
            auto["ability_score"] = new_score
            auto["grade"] = compute_grade(new_score)
            auto.setdefault("sip_flags", []).append({
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


def _facts_path_for_logic(logic_path, race_number):
    if race_number in (None, ""):
        return None
    matches = sorted(logic_path.parent.glob(f"*Race {race_number} Facts.md"))
    return matches[0] if matches else None


def _load_combo_priors():
    global _COMBO_PRIORS_CACHE
    if _COMBO_PRIORS_CACHE is not None:
        return _COMBO_PRIORS_CACHE
    priors = {}
    if COMBO_PRIORS_PATH.exists():
        with COMBO_PRIORS_PATH.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                priors[(row.get("Jockey", ""), row.get("Trainer", ""))] = {
                    "starts": float(row.get("Starts", 0) or 0),
                    "wins": float(row.get("Wins", 0) or 0),
                    "places": float(row.get("Places", 0) or 0),
                    "win_rate": float(row.get("WinRate", 0) or 0),
                    "place_rate": float(row.get("PlaceRate", 0) or 0),
                }
    _COMBO_PRIORS_CACHE = priors
    return priors


def _trackwork_path_for_logic(logic_path, race_number):
    if race_number in (None, ""):
        return None
    matches = sorted(logic_path.parent.glob(f"*Race {race_number} 晨操.md"))
    return matches[0] if matches else None


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
    for source_path in (
        _facts_path_for_logic(logic_path, race_number),
        _trackwork_path_for_logic(logic_path, race_number),
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


def _enrich_horse_headers(horses, anchor_map):
    priors = _load_combo_priors()
    for horse_num, horse_obj in horses.items():
        if not isinstance(horse_obj, dict):
            continue
        anchors = anchor_map.get(str(horse_num), {})
        if not anchors:
            continue
        for field in ("horse_name", "jockey", "trainer", "weight", "barrier"):
            current = _clean_anchor_value(horse_obj.get(field))
            fallback = _clean_anchor_value(anchors.get(field))
            if not current and fallback:
                horse_obj[field] = fallback
        data = horse_obj.setdefault("_data", {})
        if isinstance(data, dict):
            if not _clean_anchor_value(data.get("jockey_name")) and _clean_anchor_value(horse_obj.get("jockey")):
                data["jockey_name"] = horse_obj.get("jockey")
            if not _clean_anchor_value(data.get("trainer_name")) and _clean_anchor_value(horse_obj.get("trainer")):
                data["trainer_name"] = horse_obj.get("trainer")
            if not _clean_anchor_value(data.get("weight_carried")) and _clean_anchor_value(horse_obj.get("weight")):
                data["weight_carried"] = horse_obj.get("weight")
            jockey = _clean_anchor_value(horse_obj.get("jockey"))
            trainer = _clean_anchor_value(horse_obj.get("trainer"))
            prior = priors.get((jockey, trainer))
            if prior and not isinstance(data.get("jockey_trainer_combo_prior"), dict):
                data["jockey_trainer_combo_prior"] = prior


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
    def __init__(self, target_path):
        self.target_path = Path(target_path)
        self.is_meeting = self.target_path.is_dir()
        self.races = []
        
    def run(self):
        print(f"🚀 Starting HKJC Wong Choi Auto scoring on: {self.target_path}")
        if self.validate_engine():
            return 1
        
        if self.is_meeting:
            logic_files = sorted(list(self.target_path.glob("Race_*_Logic.json")))
            if not logic_files:
                print(f"❌ No Race_*_Logic.json files found in {self.target_path}")
                return
            self.races = logic_files
        else:
            if not self.target_path.name.endswith("_Logic.json"):
                print(f"❌ Target {self.target_path} is not a Logic JSON file.")
                return
            self.races = [self.target_path]
            
        results = []
        failed = []
        for race_file in self.races:
            result = self.score_race(race_file)
            if result:
                results.append(result)
            else:
                failed.append(race_file.name)

        if self.is_meeting and results:
            meeting_csv = self.target_path / "HKJC_Auto_Scoring.csv"
            meeting_csv.write_text(render_meeting_csv(results), encoding="utf-8")
            print(f"📄 Meeting CSV: {meeting_csv}")
            
        if failed:
            print("\n❌ HKJC Wong Choi Auto completed with failed races:")
            for name in failed:
                print(f"   - {name}")
            return 1

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
        try:
            with open(race_file, "r", encoding="utf-8") as f:
                logic_data = json.load(f)
        except Exception as e:
            print(f"❌ Failed to load {race_file}: {e}")
            return

        race_context = logic_data.get("race_analysis", {})
        horses = logic_data.get("horses", {})
        header_anchor_map = _load_header_anchor_map(race_file, race_context)
        _enrich_horse_headers(horses, header_anchor_map)
        formline_summaries = _load_formline_opponent_summaries(race_file, race_context, horses)
        for h_num, summary in formline_summaries.items():
            horse_obj = horses.get(h_num)
            if not isinstance(horse_obj, dict):
                continue
            data = horse_obj.setdefault("_data", {})
            if isinstance(data, dict):
                data.update(summary)
        
        horse_results = []
        for h_num, h_obj in horses.items():
            h_name = h_obj.get("horse_name", "Unknown")
            print(f"   - Scoring Horse {h_num}: {h_name}")
            
            engine = RacingEngine(h_obj, race_context)
            result = engine.analyze_horse()
            
            h_obj["python_auto"] = result
            # Also update the classic matrix if requested (optional rule)
            # h_obj["matrix"] = result["matrix"]
            
            horse_results.append((h_num, result["ability_score"]))

        _apply_sip_enhancements(horses)
        horse_results = [(h_num, horses[h_num]["python_auto"]["ability_score"]) for h_num in horses]

        # Rank horses by ability score
        horse_results.sort(key=lambda x: x[1], reverse=True)
        for i, (h_num, score) in enumerate(horse_results):
            horses[h_num]["python_auto"]["rank"] = i + 1

        ensure_verdict(logic_data)
            
        # Write back to JSON
        try:
            with open(race_file, "w", encoding="utf-8") as f:
                json.dump(logic_data, f, ensure_ascii=False, indent=2)
            print(f"   ✅ Updated {race_file.name}")
            logic_errors = validate_logic_data(logic_data)
            if logic_errors:
                print("❌ Logic validation failed:")
                for error in logic_errors:
                    print(f"   - {error}")
                return None
            md_path, csv_path = write_race_outputs(race_file, logic_data)
            print(f"   📄 Markdown: {md_path.name}")
            print(f"   📄 CSV: {csv_path.name}")
            return logic_data
        except Exception as e:
            print(f"❌ Failed to write outputs for {race_file}: {e}")
            return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HKJC Wong Choi Auto Orchestrator")
    parser.add_argument("target", help="Path to Race_X_Logic.json or meeting folder")
    parser.add_argument("--validate-engine", action="store_true", help="Accepted for compatibility; renderer validation runs after writing Markdown")
    args = parser.parse_args()
    
    orchestrator = HKJCAutoOrchestrator(args.target)
    orchestrator._validate_engine_requested = args.validate_engine
    raise SystemExit(orchestrator.run())
