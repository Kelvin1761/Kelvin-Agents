#!/usr/bin/env python3
import sys
import json
import csv
import re
from pathlib import Path
from collections import defaultdict

# Add shadow engine to path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.append(str(SCRIPT_DIR / "shadow_engine"))

try:
    from engine_core import RacingEngine
    from scoring import MATRIX_WEIGHTS
except ImportError as e:
    print(f"Error importing shadow engine: {e}")
    sys.exit(1)

ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
HISTORICAL_RESULTS_CSV = ARCHIVE_ROOT / "AU_Historical_Raw_Race_Results.csv"

def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())

def normalize_horse_name(name: str) -> str:
    clean = re.sub(r"\s*\([^)]*\)", "", str(name or ""))
    return slug(clean)

def parse_int(value, default=None):
    if value is None: return default
    match = re.search(r"-?\d+", str(value))
    return int(match.group(0)) if match else default

def load_results():
    by_date_race = defaultdict(dict)
    if not HISTORICAL_RESULTS_CSV.exists():
        return by_date_race
    with HISTORICAL_RESULTS_CSV.open("r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            date = row.get("Date", "").strip()
            race = parse_int(row.get("Race"))
            horse = normalize_horse_name(row.get("Horse"))
            pos = parse_int(row.get("Pos"), 99)
            if date and race and horse:
                by_date_race[(date, race)][horse] = pos
    return by_date_race

def detect_date(path: Path):
    match = re.search(r"(\d{4}-\d{2}-\d{2})", path.name)
    return match.group(1) if match else None

def run_backtest():
    results = load_results()
    total_races = 0
    total_horses = 0
    champion_hits = 0
    pass_hits = 0
    gold_hits = 0
    zero_hits = 0
    
    print(f"Starting backtest on archive: {ARCHIVE_ROOT}")
    
    for meeting_dir in sorted(ARCHIVE_ROOT.iterdir()):
        if not meeting_dir.is_dir(): continue
        date = detect_date(meeting_dir)
        if not date: continue
        
        logic_files = sorted(meeting_dir.glob("Race_*_Logic.json"), key=lambda p: parse_int(p.stem.split("_")[1], 99))
        for logic_path in logic_files:
            try:
                with logic_path.open("r", encoding="utf-8") as f:
                    logic = json.load(f)
            except: continue
            
            race_no = parse_int(logic.get("race_analysis", {}).get("race_number")) or parse_int(logic_path.stem.split("_")[1])
            race_results = results.get((date, race_no))
            if not race_results: continue
            
            horses = logic.get("horses", {})
            race_context = logic.get("race_analysis", {})
            
            scored_horses = []
            for h_num, h_data in horses.items():
                horse_name = normalize_horse_name(h_data.get("horse_name"))
                actual_pos = race_results.get(horse_name)
                if actual_pos is None: continue
                
                # Re-run engine
                engine = RacingEngine(h_data, race_context)
                analysis = engine.analyze_horse()
                
                scored_horses.append({
                    "name": h_data.get("horse_name"),
                    "rank_score": analysis["rank_score"],
                    "pos": actual_pos
                })
            
            if len(scored_horses) < 4: continue
            
            total_races += 1
            total_horses += len(scored_horses)
            
            # Rank by rank_score DESC
            ranked = sorted(scored_horses, key=lambda x: (-x["rank_score"], x["name"]))
            
            top1 = ranked[0]
            top3 = ranked[:3]
            
            actual_top3 = [h for h in scored_horses if h["pos"] <= 3]
            if not actual_top3: continue # Skip if no result data
            
            hits = sum(1 for h in top3 if h["pos"] <= 3)
            
            # Stats
            if top1["pos"] == 1:
                champion_hits += 1
            
            if hits >= 2:
                pass_hits += 1
            
            if hits == 3:
                gold_hits += 1
                
            if hits == 0:
                zero_hits += 1
                
    if total_races == 0:
        print("No races found to backtest.")
        return

    print("\n" + "="*40)
    print(f"Backtest Results ({total_races} races, {total_horses} horses)")
    print("-" * 40)
    print(f"🏆 Gold (3/3):   {gold_hits:3d} ({gold_hits/total_races:5.1%})")
    print(f"⚠️ Pass (2/3):    {pass_hits:3d} ({pass_hits/total_races:5.1%})")
    print(f"⬛ 0-hit (0/3):  {zero_hits:3d} ({zero_hits/total_races:5.1%})")
    print(f"🥇 Champion:     {champion_hits:3d} ({champion_hits/total_races:5.1%})")
    print("="*40)

if __name__ == "__main__":
    run_backtest()
