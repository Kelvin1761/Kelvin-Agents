import sys
import json
import os
from pathlib import Path

# Add shadow_engine to path
# Add shadow_engine to path
sys.path.insert(0, str(Path(__file__).parent / "shadow_engine"))
from engine_core import RacingEngine

print(f"DEBUG: Using engine_core from {RacingEngine.__module__}")

LOGIC_FILE = "Archive_Race_Analysis/AU_Racing/2025-10-04 Randwick Race 1-10/Race_1_Logic.json"

def test():
    with open(LOGIC_FILE, "r") as f:
        data = json.load(f)
    
    horses = data.get("horses", {})
    results = []
    
    for h_id, h_data in horses.items():
        engine = RacingEngine(h_data, data.get("race_analysis"))
        analysis = engine.analyze_horse()
        # Removed JSON print to avoid truncation
        results.append({
            "name": h_data.get("horse_name"),
            "score": analysis.get("rank_score"),
            "rank": analysis.get("rank")
        })
    
    results.sort(key=lambda x: x["score"], reverse=True)
    print(f"\n--- Results for {LOGIC_FILE} ---")
    for i, r in enumerate(results):
        print(f"{i+1}. {r['name']}: {r['score']:.2f}")

if __name__ == "__main__":
    test()
