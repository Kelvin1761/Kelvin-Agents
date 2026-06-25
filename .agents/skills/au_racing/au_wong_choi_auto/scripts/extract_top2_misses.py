#!/usr/bin/env python3
import json
import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING
sys.path.append(str(SCRIPT_DIR))
sys.path.append(str(PROJECT_ROOT / ".agents" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_wong_choi_auto" / "scripts" / "racing_engine"))
sys.path.append(str(PROJECT_ROOT / ".agents" / "skills" / "au_racing" / "au_reflector" / "scripts"))

from reflector_auto_stats import compute_race_stats
from au_review_auto_weighting import (
    _load_results_map,
    _logic_sort_key,
    find_au_meetings,
    meeting_results_file,
    _build_field_summary,
    _facts_path_for_logic,
)
from engine_core import RacingEngine, enrich_logic_from_facts

ARCHIVE_ROOT = AU_RACING

def extract_misses():
    meetings = find_au_meetings(ARCHIVE_ROOT)
    missed_races = []
    
    for meeting in meetings:
        results_file = meeting_results_file(meeting)
        if not results_file: continue
        results_map = _load_results_map(results_file)
        
        for logic_path in sorted(meeting.glob("Race_*_Logic.json"), key=_logic_sort_key):
            race_num = _logic_sort_key(logic_path)
            results = results_map.get(race_num, [])
            if not results: continue
            
            logic_data = json.loads(logic_path.read_text(encoding="utf-8"))
            race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
            
            facts_path = _facts_path_for_logic(logic_path, int(race.get("race_number")) if str(race.get("race_number")).isdigit() else None)
            if facts_path and facts_path.exists():
                logic_data = enrich_logic_from_facts(logic_data, facts_path)
                race = logic_data.get("race_analysis", {}) if isinstance(logic_data.get("race_analysis"), dict) else {}
            race["field_summary"] = _build_field_summary(logic_data.get("horses", {}))
            
            ranked = []
            for horse_num, horse in logic_data.get("horses", {}).items():
                try: horse_number = int(horse_num)
                except: horse_number = 999
                
                engine = RacingEngine(horse, race, facts_section=horse.get("_data", {}).get("facts_section", ""), facts_path=facts_path)
                auto = engine.analyze_horse()
                
                # Extract odds if possible
                odds = "N/A"
                facts = str(horse.get("_data", {}).get("facts_section", ""))
                import re
                m = re.search(r'(?i)(?:odds|price)[\s:]+\$*([0-9.]+)', facts)
                if m: odds = f"${m.group(1)}"
                
                ranked.append({
                    "horse_number": horse_number,
                    "horse_name": str(horse.get("horse_name", "")),
                    "rank_score": float(auto.get("rank_score", 0)),
                    "ability_score": float(auto.get("ability_score", 0)),
                    "odds": odds
                })
                
            ranked.sort(key=lambda row: (-row["rank_score"], -row["ability_score"], row["horse_number"]))
            top2 = ranked[:2]
            if len(top2) < 2: continue
            
            # Find actual finish position for top 2
            top2_results = []
            both_missed_top3 = True
            for pick in top2:
                finish = "Unplaced"
                for r in results:
                    if len(r) >= 2 and r[1] == pick["horse_number"]:
                        finish = str(r[0])
                        if str(r[0]) in ("1", "2", "3"):
                            both_missed_top3 = False
                        break
                top2_results.append({"horse": pick["horse_name"], "number": pick["horse_number"], "finish": finish, "odds": pick["odds"]})
                
            if both_missed_top3:
                # This is a double miss
                missed_races.append({
                    "meeting": meeting.name,
                    "race_number": race_num,
                    "class": race.get("race_class", "Unknown"),
                    "distance": race.get("distance", "Unknown"),
                    "going": race.get("going", race.get("meeting_intelligence", {}).get("going", "Unknown")),
                    "field_size": race.get("field_summary", {}).get("count", len(logic_data.get("horses", {}))),
                    "top2": top2_results
                })

    with open(ARCHIVE_ROOT / "double_misses.json", "w") as f:
        json.dump(missed_races, f, indent=2)
    print(f"Found {len(missed_races)} double misses.")

if __name__ == "__main__":
    extract_misses()
