import json
import csv
import re
from pathlib import Path
from collections import defaultdict
import statistics

ARCHIVE_ROOT = Path("Archive_Race_Analysis/AU_Racing")
RESULTS_CSV = ARCHIVE_ROOT / "AU_Historical_Raw_Race_Results.csv"

def parse_int(val):
    m = re.search(r'-?\d+', str(val))
    return int(m.group(0)) if m else None

def parse_float(val):
    m = re.search(r'-?\d+(?:\.\d+)?', str(val))
    return float(m.group(0)) if m else None

def slug(s):
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())

def normalize_horse(s):
    return slug(re.sub(r"\s*\([^)]*\)", "", str(s or "")))

def normalize_track(s):
    clean = str(s or "").strip().lower()
    for rm in [" race 1-10", " race 1-9", " race 1-8", " race 1-7", " gardens"]:
        clean = clean.replace(rm, "")
    return slug(clean)

results = defaultdict(list)
with open(RESULTS_CSV, "r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        r = parse_int(row.get("Race"))
        p = parse_int(row.get("Pos"))
        if not r or not p: continue
        results[(str(row.get("Date")).strip(), r)].append({
            "track_slug": normalize_track(row.get("Track")),
            "horse_slug": normalize_horse(row.get("Horse")),
            "pos": p,
            "sp": row.get("SP")
        })

def detect_date(d):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", d.name)
    return m.group(1) if m else ""

def detect_track(d, logic):
    ra = logic.get("race_analysis", {})
    return str(ra.get("meeting_intelligence", {}).get("venue") or ra.get("track_profile", {}).get("venue") or ra.get("venue") or re.sub(r"^\d{4}-\d{2}-\d{2}\s+", "", d.name)).strip()

data = []

# Relaxed track mapping to get more horses
for d in sorted(ARCHIVE_ROOT.iterdir()):
    if not d.is_dir(): continue
    for lp in d.glob("Race_*_Logic.json"):
        logic = json.loads(lp.read_text("utf-8"))
        rc = str(logic.get("race_analysis", {}).get("race_class", "")).lower()
        if "maiden" not in rc and "mdn" not in rc: continue

        date = detect_date(d)
        rno = parse_int(logic.get("race_analysis", {}).get("race_number") or lp.stem.split("_")[1])
        
        hist = results.get((date, rno), [])
        if not hist: continue
        
        # Try to find the exact horse match without relying on track slug
        race_lookup = {x["horse_slug"]: x for x in hist}
        
        # Check if at least 1 horse matches to confirm it's the right race
        match_count = sum(1 for h in logic.get("horses", {}).values() if normalize_horse(h.get("horse_name")) in race_lookup)
        if match_count < 3: continue
        
        for hnum, horse in logic.get("horses", {}).items():
            hslug = normalize_horse(horse.get("horse_name"))
            hr = race_lookup.get(hslug)
            if not hr: continue
            
            d_obj = horse.get("_data", {})
            starts = parse_int(horse.get("career_race_starts"))
            if starts is None: starts = 0
            
            # Form calculations
            form_str = str(horse.get("recent_form", ""))
            form_nums = [int(x) for x in form_str if x.isdigit()]
            recent_top3 = sum(1 for x in form_nums[:3] if x <= 3) if form_nums else 0
            
            data.append({
                "horse": horse.get("horse_name"),
                "pos": hr["pos"],
                "top3": hr["pos"] <= 3,
                "winner": hr["pos"] == 1,
                "weight": parse_float(horse.get("weight")),
                "starts": starts,
                "debut": starts == 0,
                "trial_count": parse_int(d_obj.get("trial_count")) or 0,
                "trial_top3": parse_int(d_obj.get("trial_top3_count")) or 0,
                "barrier": parse_int(horse.get("barrier")),
                "status_cycle": str(horse.get("status_cycle", "")).lower(),
                "recent_form": form_str,
                "recent_top3_count": recent_top3,
                "distance_profile": str(d_obj.get("distance_profile_line", "")),
                "sp": parse_float(hr["sp"])
            })

print(f"Total Maiden Horses Evaluated: {len(data)}")

top3 = [x for x in data if x["top3"]]
rest = [x for x in data if not x["top3"]]
winners = [x for x in data if x["winner"]]

def avg(lst, key):
    vals = [x[key] for x in lst if x[key] is not None]
    return statistics.mean(vals) if vals else 0.0

def prop(lst, condition):
    return sum(1 for x in lst if condition(x)) / len(lst) if lst else 0.0

print("\n=== MAIDEN PLATE DISCOVERY ANALYSIS ===")

print("\n1. 📉 RECENT FORM DENSITY")
print(f"Avg Recent Top 3s (Last 3 Starts) - WINNERS: {avg(winners, 'recent_top3_count'):.2f} | TOP 3: {avg(top3, 'recent_top3_count'):.2f} | REST: {avg(rest, 'recent_top3_count'):.2f}")
print(f"% with NO Top 3s recently - WINNERS: {prop(winners, lambda x: x['recent_top3_count'] == 0 and not x['debut']):.1%} | REST: {prop(rest, lambda x: x['recent_top3_count'] == 0 and not x['debut']):.1%}")

print("\n2. 🏋️ WEIGHT DISTRIBUTION")
print(f"Avg Weight - WINNERS: {avg(winners, 'weight'):.2f}kg | TOP 3: {avg(top3, 'weight'):.2f}kg | REST: {avg(rest, 'weight'):.2f}kg")
print(f"% Heavy (>=59.0kg) - WINNERS: {prop(winners, lambda x: x['weight'] >= 59.0):.1%} | REST: {prop(rest, lambda x: x['weight'] >= 59.0):.1%}")

print("\n3. 🏇 EXPERIENCE LEVEL")
print(f"Avg Career Starts - WINNERS: {avg(winners, 'starts'):.2f} | TOP 3: {avg(top3, 'starts'):.2f} | REST: {avg(rest, 'starts'):.2f}")
print(f"% Unexposed (<=3 starts) - WINNERS: {prop(winners, lambda x: x['starts'] <= 3):.1%} | REST: {prop(rest, lambda x: x['starts'] <= 3):.1%}")
print(f"% Deep Maidens (>=10 starts) - WINNERS: {prop(winners, lambda x: x['starts'] >= 10):.1%} | REST: {prop(rest, lambda x: x['starts'] >= 10):.1%}")

print("\n4. 🚀 DEBUTANT PROFILES")
debut_winners = [x for x in winners if x["debut"]]
debut_top3 = [x for x in top3 if x["debut"]]
debut_rest = [x for x in rest if x["debut"]]
print(f"Total Debutants: {len(debut_top3) + len(debut_rest)}")
print(f"% of Debutants that hit Top 3: {len(debut_top3)/max(1, (len(debut_top3) + len(debut_rest))):.1%}")
print(f"Avg Trial Top 3s - DEBUT TOP 3: {avg(debut_top3, 'trial_top3'):.2f} | DEBUT REST: {avg(debut_rest, 'trial_top3'):.2f}")

print("\n5. 🔄 CYCLE & FITNESS")
print(f"% First-Up - TOP 3: {prop(top3, lambda x: 'first-up' in x['status_cycle']):.1%} | REST: {prop(rest, lambda x: 'first-up' in x['status_cycle']):.1%}")
print(f"% Peak (3rd/4th run) - TOP 3: {prop(top3, lambda x: 'peak' in x['status_cycle'] or '3rd-up' in x['status_cycle'] or '4th-up' in x['status_cycle']):.1%} | REST: {prop(rest, lambda x: 'peak' in x['status_cycle'] or '3rd-up' in x['status_cycle'] or '4th-up' in x['status_cycle']):.1%}")

print("\n6. 📊 BARRIER ADVANTAGE")
print(f"Avg Barrier - WINNERS: {avg(winners, 'barrier'):.2f} | TOP 3: {avg(top3, 'barrier'):.2f} | REST: {avg(rest, 'barrier'):.2f}")
print(f"% Inside Draw (1-4) - TOP 3: {prop(top3, lambda x: x['barrier'] <= 4):.1%} | REST: {prop(rest, lambda x: x['barrier'] <= 4):.1%}")
print(f"% Wide Draw (>=10) - TOP 3: {prop(top3, lambda x: x['barrier'] >= 10):.1%} | REST: {prop(rest, lambda x: x['barrier'] >= 10):.1%}")

