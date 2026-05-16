import os
import json
import csv
import re
from pathlib import Path
from collections import defaultdict
import sys

# Add shadow_engine to path
sys.path.append(str(Path(__file__).parent / "shadow_engine"))

from engine_core import RacingEngine
import scoring

ARCHIVE_DIR = Path("/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/Archive_Race_Analysis/AU_Racing")

def normalize_horse_name(name):
    if not name: return ""
    # Remove trainer/margin info if present in MD
    name = name.split("(")[0].strip()
    return re.sub(r'[^a-zA-Z0-9]', '', name).lower()

def parse_int(val, default=0):
    try:
        return int(float(val))
    except:
        return default

def harvest_results():
    by_date_course_race = defaultdict(dict)
    md_files = list(ARCHIVE_DIR.glob("**/Race_Results_Reflector.md"))
    print(f"Found {len(md_files)} result MD files.")
    
    for md_file in md_files:
        # Expected path: .../Archive_Race_Analysis/AU_Racing/2025-10-04 Randwick Race 1-10/Race_Results_Reflector.md
        parent_name = md_file.parent.name
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s+([A-Za-z]+)", parent_name)
        if not date_match: continue
        date = date_match.group(1)
        course = date_match.group(2).lower()
        
        content = md_file.read_text()
        races = re.split(r"## Race \d+", content)
        for i, race_content in enumerate(races[1:], 1):
            for pos_name, pos_val in [("1st", 1), ("2nd", 2), ("3rd", 3)]:
                match = re.search(fr"{pos_name}:\s*#?\d+\s+([^\$]+?)(?:\s+SP|\s*\(|$)", race_content)
                if match:
                    horse = normalize_horse_name(match.group(1))
                    by_date_course_race[(date, course, i)][horse] = pos_val
    return by_date_course_race

def run_backtest(logic_files, results_db):
    stats = {"total_races": 0, "total_horses": 0, "gold": 0, "gold_in_4": 0, "gold_in_5": 0, "good": 0, "minimum": 0, "zero": 0, "champion": 0, "hits_top3": 0}
    
    for logic_file in logic_files:
        try:
            name = logic_file.name
            match = re.search(r"Race_(\d+)", name)
            if not match: continue
            race_num = parse_int(match.group(1))
            
            parent_name = logic_file.parent.name
            # Expected path: .../Archive_Race_Analysis/AU_Racing/2025-10-04 Randwick Race 1-10/Race_7_Logic.json
            meeting_name = logic_file.parent.name
            date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s+([A-Za-z]+)", meeting_name)
            if not date_match: 
                # print(f"DEBUG: No date_match for {meeting_name}")
                continue
            date = date_match.group(1)
            course = date_match.group(2).lower()
            
            if (date, course, race_num) not in results_db:
                # if stats["total_races"] < 10:
                #     print(f"DEBUG: {(date, course, race_num)} not in results_db")
                continue
            race_results = results_db[(date, course, race_num)]
            if not race_results:
                continue
            
            with open(logic_file, "r") as f:
                logic_data = json.load(f)
            
            horses_raw = logic_data.get("horses")
            if horses_raw is None:
                horses_raw = logic_data.get("race_analysis", {}).get("horses", [])
            
            race_context = logic_data.get("race_context")
            if race_context is None:
                race_context = logic_data.get("race_analysis", {})
                
            horses = []
            if isinstance(horses_raw, dict):
                for h_id, h_data in horses_raw.items():
                    if isinstance(h_data, dict):
                        horses.append(h_data)
            elif isinstance(horses_raw, list):
                horses = horses_raw
                
            if not horses or len(horses) < 5:
                continue
                
            rankings = []
            for horse_data in horses:
                if not isinstance(horse_data, dict): continue
                engine = RacingEngine(horse_data, race_context)
                horse_analysis = engine.analyze_horse()
                h_name = horse_data.get("horse_name") or horse_data.get("name") or horse_data.get("horse") or ""
                rankings.append({
                    "horse": normalize_horse_name(h_name),
                    "rank_score": horse_analysis.get("rank_score", 0)
                })
            
            if not rankings:
                continue
                
            stats["total_races"] += 1
            stats["total_horses"] += len(rankings)
            
            rankings.sort(key=lambda x: x["rank_score"], reverse=True)
            top3 = rankings[:3]
            top4 = rankings[:4]
            top5 = rankings[:5]
            
            hits_in_3 = sum(1 for h in top3 if race_results.get(h["horse"], 99) <= 3)
            hits_in_4 = sum(1 for h in top4 if race_results.get(h["horse"], 99) <= 3)
            hits_in_5 = sum(1 for h in top5 if race_results.get(h["horse"], 99) <= 3)
            
            stats["hits_top3"] += hits_in_3
            
            if rankings[0]["horse"] in race_results and race_results[rankings[0]["horse"]] == 1:
                stats["champion"] += 1
            
            if hits_in_3 == 3: stats["gold"] += 1
            if hits_in_4 == 3: stats["gold_in_4"] += 1
            if hits_in_5 == 3: stats["gold_in_5"] += 1
            
            if hits_in_3 == 2: stats["good"] += 1
            if hits_in_3 == 1: stats["minimum"] += 1
            if hits_in_3 == 0: stats["zero"] += 1
            
        except Exception as e:
            continue
            
    return stats

def main():
    print(f"Harvesting results from MD files...")
    results_db = harvest_results()
    print(f"Total races with results: {len(results_db)}")
    
    print(f"Scanning logic files...")
    logic_files = list(ARCHIVE_DIR.glob("**/*Logic.json"))
    print(f"Found {len(logic_files)} logic files.")

    scenarios = [
        {"name": "Production (Default)", "stability": 0.14, "class_weight": 0.14, "sectional": 0.14},
        {"name": "Aggressive Class (SIP-032 Prep)", "stability": 0.10, "class_weight": 0.18, "sectional": 0.14},
        {"name": "Aggressive Sectional", "stability": 0.10, "class_weight": 0.14, "sectional": 0.22},
        {"name": "Forensic Class-First", "stability": 0.08, "class_weight": 0.22, "sectional": 0.10},
    ]

    for s in scenarios:
        print(f"\n--- Running Scenario: {s['name']} ---")
        scoring.MATRIX_WEIGHTS["stability"] = s["stability"]
        scoring.MATRIX_WEIGHTS["class_weight"] = s["class_weight"]
        scoring.MATRIX_WEIGHTS["sectional"] = s["sectional"]
        res = run_backtest(logic_files, results_db)
        print_stats(res)

def print_stats(res):
    if res["total_races"] == 0:
        print("No races matched.")
        return
    r = res["total_races"]
    g_pct = res["gold"] / r * 100
    g4_pct = res["gold_in_4"] / r * 100
    g5_pct = res["gold_in_5"] / r * 100
    gd_pct = res["good"] / r * 100
    m_pct = res["minimum"] / r * 100
    z_pct = res["zero"] / r * 100
    c_pct = res["champion"] / r * 100
    acc = res["hits_top3"] / (3 * r) * 100
    
    print(f"Races: {r}")
    print(f"🏆 Gold (3/3): {res['gold']} ({g_pct:.1f}%) [Target: 30%]")
    print(f"🥇 Gold (3/4): {res['gold_in_4']} ({g4_pct:.1f}%)")
    print(f"🥈 Gold (3/5): {res['gold_in_5']} ({g5_pct:.1f}%)")
    print(f"✅ Good (2/3): {res['good']} ({gd_pct:.1f}%) [Target: 40%]")
    print(f"⚠️ Minimum (1/3): {res['minimum']} ({m_pct:.1f}%) [Target: 60%]")
    print(f"🎯 Top 3 Acc: {acc:.1f}% [Target: 80%]")
    print(f"🏆 Champ (W): {res['champion']} ({c_pct:.1f}%)")

if __name__ == "__main__":
    main()
