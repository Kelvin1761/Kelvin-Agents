#!/usr/bin/env python3
import json
import pathlib
import sys
import collections

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[5]
SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
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

ARCHIVE_ROOT = PROJECT_ROOT / "Archive_Race_Analysis" / "AU_Racing"
OUTPUT_MD = ARCHIVE_ROOT / "AU_Double_Miss_Deep_Dive.md"

def extract_odds(horse_data):
    # Try multiple keys
    d = horse_data.get("_data", {})
    flucs = d.get("latest_official_last_flucs")
    if flucs:
        parts = str(flucs).split()
        if parts: return f"${parts[-1]}"
    market_last = d.get("current_market_last")
    if market_last: return f"${market_last}"
    market_line = d.get("current_market_line")
    if market_line: return str(market_line)
    return "N/A"

def heuristic_reason(top2_odds, top3_odds, field_size, distance, track_cond):
    reasons = []
    # Identify if winners were longshots
    longshot_win = False
    for o in top3_odds:
        try:
            val = float(str(o).replace('$', '').replace('N/A','0'))
            if val > 15.0: longshot_win = True
        except: pass
        
    top2_fav = False
    for o in top2_odds:
        try:
            val = float(str(o).replace('$', '').replace('N/A','0'))
            if 0 < val < 4.0: top2_fav = True
        except: pass
        
    if longshot_win and top2_fav:
        reasons.append("Pace collapse / Bias favored outsiders (爆大冷，熱門倒灶)")
    elif longshot_win:
        reasons.append("Unpredictable race with longshot winners (爆冷賽果)")
    elif top2_fav:
        reasons.append("Favorites underperformed, possibly blocked or track bias (大熱門未能交出水準，可能受阻或場地偏差)")
        
    if "heavy" in str(track_cond).lower() or "soft" in str(track_cond).lower():
        reasons.append("Track Condition impact (變化地影響)")
        
    if not reasons:
        reasons.append("Engine Logic Misalignment (引擎計算偏差 / 馬匹實力未能反映在數據上)")
        
    return " | ".join(reasons)

def generate_report():
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
            horses_dict = logic_data.get("horses", {})
            for horse_num, horse in horses_dict.items():
                try: horse_number = int(horse_num)
                except: horse_number = 999
                
                engine = RacingEngine(horse, race, facts_section=horse.get("_data", {}).get("facts_section", ""), facts_path=facts_path)
                auto = engine.analyze_horse()
                odds = extract_odds(horse)
                
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
            
            both_missed_top3 = True
            top2_results = []
            for pick in top2:
                finish = "Unplaced"
                for r in results:
                    if len(r) >= 2 and r[1] == pick["horse_number"]:
                        finish = str(r[0])
                        if str(r[0]) in ("1", "2", "3"):
                            both_missed_top3 = False
                        break
                top2_results.append({**pick, "finish": finish})
                
            if both_missed_top3:
                # Find actual top 3
                actual_top3 = []
                for r in results:
                    if len(r) >= 3 and str(r[0]) in ("1", "2", "3"):
                        # find odds
                        act_odds = "N/A"
                        for h_key, h_data in horses_dict.items():
                            if str(h_key) == str(r[1]):
                                act_odds = extract_odds(h_data)
                                break
                        actual_top3.append({"pos": r[0], "horse_number": r[1], "horse_name": r[2], "odds": act_odds})
                
                top2_odds_list = [p["odds"] for p in top2_results]
                top3_odds_list = [a["odds"] for a in actual_top3]
                
                missed_races.append({
                    "meeting": meeting.name,
                    "race_number": race_num,
                    "class": race.get("race_class", "Unknown"),
                    "distance": race.get("distance", "Unknown"),
                    "going": race.get("going", race.get("meeting_intelligence", {}).get("going", "Unknown")),
                    "field_size": race.get("field_summary", {}).get("count", len(horses_dict)),
                    "top2": top2_results,
                    "actual_top3": actual_top3,
                    "reason": heuristic_reason(top2_odds_list, top3_odds_list, len(horses_dict), race.get("distance", "Unknown"), race.get("going", "Unknown"))
                })

    # Generate Markdown
    lines = [
        "# AU Wong Choi - Double Misses Deep Dive",
        "呢份報告詳細分析咗 AU Wong Choi 預測中，**Top 2 首選及次選雙雙未能跑入三甲 (Top 3)** 嘅賽事。",
        f"**總雙重失誤場次**: {len(missed_races)} 場\n"
    ]
    
    # Classes distribution
    classes = collections.Counter(r["class"] for r in missed_races)
    lines.append("## 班次分佈 (Class Distribution - Top 10)")
    for cls, count in classes.most_common(10):
        lines.append(f"- **{cls}**: {count} 場")
    lines.append("")
    
    lines.append("## 賽事詳細分析 (Race Case Studies)")
    lines.append("下表列出具代表性嘅失誤賽事，包括引擎首選、實際三甲及失誤原因推斷：\n")
    
    for idx, r in enumerate(missed_races[:20]): # Output first 20 for extreme detail
        lines.append(f"### {idx+1}. {r['meeting']} - Race {r['race_number']}")
        lines.append(f"- **條件**: {r['class']} | {r['distance']} | {r['going']} | {r['field_size']}匹出賽")
        
        lines.append("\n**引擎 Top 2 預測 (Engine Top 2 Picks):**")
        for p in r['top2']:
            lines.append(f"- `#{p['horse_number']} {p['horse_name']}` | 賠率: {p['odds']} | 最終名次: {p['finish']}")
            
        lines.append("\n**實際三甲 (Actual Top 3):**")
        for a in r['actual_top3']:
            lines.append(f"- **第 {a['pos']} 名**: `#{a['horse_number']} {a['horse_name']}` | 賠率: {a['odds']}")
            
        lines.append(f"\n**💡 失誤原因推斷 (Diagnostic Reason):**\n> {r['reason']}\n")
        lines.append("---")
        
    OUTPUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report generated at {OUTPUT_MD}")

if __name__ == "__main__":
    generate_report()
