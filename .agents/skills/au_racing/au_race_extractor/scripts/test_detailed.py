import json

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/nuxt.json', 'r') as f:
    nuxt = json.load(f)

apollo = nuxt.get('apollo', {}).get('horseClient', {})
selections = nuxt.get('fetch', {}).get('FormGuidePrint:0', {}).get('selections', [])

# Find Absolute Power
sel = next((s for s in selections if s.get('competitorNumber') == 1), None)

def safe_get(d, key, default=""):
    return d.get(key) if d.get(key) is not None else default

if sel:
    c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else str(sel.get('competitor', {}).get('__ref', '')).replace('Competitor:', '')
    comp = apollo.get(f"Competitor:{c_id}", {})
    name = comp.get('name', 'Unknown')
    stats = sel.get('stats', {})
    
    # 1. HORSE HEADER
    age = comp.get('age', '?')
    sex = comp.get('sexShort', '?')
    colour = comp.get('colour', '?')
    
    # Sire / Dam info: The refs might be in comp directly, or we just stringify
    sire_ref = comp.get('sire', {}).get('__ref') if isinstance(comp.get('sire'), dict) else None
    sire_name = apollo.get(sire_ref, {}).get('name', 'Unknown') if sire_ref else 'Unknown'
    
    dam_ref = comp.get('dam', {}).get('__ref') if isinstance(comp.get('dam'), dict) else None
    dam_name = apollo.get(dam_ref, {}).get('name', 'Unknown') if dam_ref else 'Unknown'
    sire_of_dam = comp.get('sireOfDam', 'Unknown')
    
    header = f"{age}yo{sex} {colour} Sire: {sire_name} Dam: {dam_name} ({sire_of_dam}) "
    header += f"Prize: ${stats.get('totalPrizeMoney', 0):,} ROI: {stats.get('roi', 0)}% "
    header += f"Career: {stats.get('career', '0:0-0-0')} Last 10: {stats.get('lastTenFigure', '')} "
    header += f"Win: {stats.get('winPercentage', 0)}% Place: {stats.get('placePercentage', 0)}%"
    print(f"--- Header ---\n{header}\n")
    
    # 2. RUN HISTORY
    runs = sel.get('forms', [])
    print("--- Runs ---")
    for pr in runs[:3]:  # Print first 3
         date = pr.get('meetingDate', '')
         track = pr.get('meetingName', '')
         dist = pr.get('eventDistance', '')
         cond = safe_get(pr, 'trackConditionRating', '?')
         money = safe_get(pr, 'racePrizeMoney', 0)
         
         jockey_name = pr.get('jockey', {}).get('name', 'Unknown') if isinstance(pr.get('jockey'), dict) else 'Unknown'
         barrier = safe_get(pr, 'barrier', '?')
         weight = safe_get(pr, 'weightCarried', '?')
         pos = pr.get('finishPosition', '?')
         starters = pr.get('eventStarters', '?')
         
         flucs = f"Flucs: {safe_get(pr, 'openPrice', '')} -> {safe_get(pr, 'startingWinPriceDecimal', '')}"
         time = safe_get(pr, 'winnerTime', '')
         
         # Margins
         margin = safe_get(pr, 'margin', '')
         win_name = safe_get(pr, 'winnerName', '')
         win_wt = safe_get(pr, 'winnerWeight', '')
         sec_name = safe_get(pr, 'secondName', '')
         sec_wt = safe_get(pr, 'secondWeight', '')
         third_name = safe_get(pr, 'thirdName', '')
         third_wt = safe_get(pr, 'thirdWeight', '')
         
         # Positioning
         pos_summary = "\nPositions:"
         pos_refs = pr.get('competitorPositionSummary', [])
         for pref in pos_refs:
             p_id = pref.get('id')
             p_data = apollo.get(f"CompetitorPositionSummary:{p_id}", {})
             if p_data:
                 pos_summary += f" {p_data.get('position')}@{p_data.get('positionMark')}m"
                 
         print(f"{track} {date} {dist}m cond:{cond} ${money} {jockey_name} ({barrier}) {weight}kg {flucs} Time: {time} {pos}/{starters}")
         print(f"{pos_summary}")
         print(f"1st: {win_name}({win_wt}kg) 2nd: {sec_name}({sec_wt}kg) 3rd: {third_name}({third_wt}kg) Margin: {margin}L")
         
         comment = safe_get(pr, 'videoComment', '')
         note = safe_get(pr, 'videoNote', '')
         stewards = safe_get(pr, 'stewardsReport', '')
         print(f"Video: {comment}")
         print(f"Note: {note}")
         print(f"Stewards: {stewards}")
         print()

