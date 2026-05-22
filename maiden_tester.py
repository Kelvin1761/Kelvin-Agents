import json
from pathlib import Path

import sys
SCRIPT_DIR = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts")
sys.path.append(str(SCRIPT_DIR / "racing_engine"))
sys.path.append(str(SCRIPT_DIR))

from engine_core import RacingEngine
from au_archive_calibrator import ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV, iter_logic_rows, load_historical_results, parse_int

class ProposedRacingEngine(RacingEngine):
    def _is_wfa_or_sw_race(self):
        race_class = str(self.race_context.get("race_class", "")).lower()
        race_name = str(self.race_context.get("race_name", "")).lower()
        condition = str(self.race_context.get("condition", "")).lower()
        
        keywords = ["wfa", "weight for age", "set weight", "sw", "plate", "plte"]
        return any(k in race_class or k in race_name or k in condition for k in keywords)

    def _form_score(self):
        starts = self._career_starts()
        race_class = str(self.race_context.get("race_class", "")).lower()
        is_maiden = "maiden" in race_class or "mdn" in race_class

        if starts == 0:
            d_obj = self.horse_data.get("_data", {})
            trial_top3 = parse_int(d_obj.get("trial_top3_count")) or 0
            if is_maiden and trial_top3 >= 1:
                return 60.0, "初出馬 (試閘上名 Proxy)", "Engine_Custom"
            return 58.0, "初出馬 (無近績/無靚閘)", "Engine_Custom"
            
        return super()._form_score()
        
    def _weight_score(self):
        weight = float(self.horse_data.get("weight") or 0.0)
        if not weight: return 0.0, "No Weight Data", "Engine"
        
        if self._is_wfa_or_sw_race():
            return 62.0, "定磅賽/分齡讓磅賽豁免負磅扣分", "Engine_Custom"
            
        return super()._weight_score()
        
    def _barrier_bias_adjustment(self):
        base_adj = super()._barrier_bias_adjustment()
        
        barrier = parse_int(self.horse_data.get("barrier"))
        if barrier is None: return base_adj
        
        race_class = str(self.race_context.get("race_class", "")).lower()
        is_maiden = "maiden" in race_class or "mdn" in race_class
        
        if is_maiden:
            if barrier <= 4:
                base_adj += 2.0
            elif barrier >= 10:
                base_adj -= 3.0
                
        return base_adj

def has_complete(rows):
    if not rows: return False
    return any(r["actual_pos"] == 1 for r in rows) and sum(1 for r in rows if r["actual_pos"] <= 3) >= 3

def pct(c, tot):
    return (c/max(1,tot))*100

hist_results = load_historical_results(HISTORICAL_RESULTS_CSV)
races_evaluated = 0
hits = {"old": {"1":0, "top3":0, "pass":0}, "new": {"1":0, "top3":0, "pass":0}}

for race_rows in iter_logic_rows(ARCHIVE_ROOT, hist_results):
    rc = str(race_rows[0].get("race_class", "")).lower()
    if "maiden" not in rc and "mdn" not in rc: continue
    
    scored_rows = []
    # For baseline, we use the original score stored in the JSON
    for row in race_rows:
        horse_data = row["horse_data"]
        race_analysis = row["race_analysis"]
        
        # New proposed score
        new_engine = ProposedRacingEngine(horse_data, race_analysis)
        n_res = new_engine.analyze_horse()
        
        scored_rows.append({
            "horse": row["horse_number"],
            "actual_pos": int(row["actual_pos"]),
            "old": float(row["model_score"]), # Original rank_score from JSON
            "new": n_res["rank_score"]        # New calculated rank_score
        })
        
    if not has_complete(scored_rows): continue
    
    races_evaluated += 1
    
    # Eval Old
    old_ranked = sorted(scored_rows, key=lambda x: (-x["old"], x["horse"]))
    if old_ranked[0]["actual_pos"] == 1: hits["old"]["1"] += 1
    top3_count = sum(1 for x in old_ranked[:3] if x["actual_pos"] <= 3)
    if top3_count == 3: hits["old"]["top3"] += 1
    if top3_count >= 2: hits["old"]["pass"] += 1

    # Eval New
    new_ranked = sorted(scored_rows, key=lambda x: (-x["new"], x["horse"]))
    if new_ranked[0]["actual_pos"] == 1: hits["new"]["1"] += 1
    top3_count_new = sum(1 for x in new_ranked[:3] if x["actual_pos"] <= 3)
    if top3_count_new == 3: hits["new"]["top3"] += 1
    if top3_count_new >= 2: hits["new"]["pass"] += 1

print(f"Total Maiden Races Matched & Scored: {races_evaluated}")

print(f"\n🥇 CHAMPION (1st choice wins)")
print(f"  Old Logic: {hits['old']['1']} / {races_evaluated} ({pct(hits['old']['1'], races_evaluated):.1f}%)")
print(f"  New Logic: {hits['new']['1']} / {races_evaluated} ({pct(hits['new']['1'], races_evaluated):.1f}%)")
print(f"  Δ: {pct(hits['new']['1'], races_evaluated) - pct(hits['old']['1'], races_evaluated):+.1f}pp")

print(f"\n🏆 GOLD (3/3 choices in Top 3)")
print(f"  Old Logic: {hits['old']['top3']} / {races_evaluated} ({pct(hits['old']['top3'], races_evaluated):.1f}%)")
print(f"  New Logic: {hits['new']['top3']} / {races_evaluated} ({pct(hits['new']['top3'], races_evaluated):.1f}%)")
print(f"  Δ: {pct(hits['new']['top3'], races_evaluated) - pct(hits['old']['top3'], races_evaluated):+.1f}pp")

print(f"\n✅ PASS (2+ choices in Top 3)")
print(f"  Old Logic: {hits['old']['pass']} / {races_evaluated} ({pct(hits['old']['pass'], races_evaluated):.1f}%)")
print(f"  New Logic: {hits['new']['pass']} / {races_evaluated} ({pct(hits['new']['pass'], races_evaluated):.1f}%)")
print(f"  Δ: {pct(hits['new']['pass'], races_evaluated) - pct(hits['old']['pass'], races_evaluated):+.1f}pp")
