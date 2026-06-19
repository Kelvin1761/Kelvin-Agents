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

results = defaultdict(list)
with open(RESULTS_CSV, "r", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        r = parse_int(row.get("Race"))
        p = parse_int(row.get("Pos"))
        if not r or not p: continue
        results[(str(row.get("Date")).strip(), r)].append({
            "horse_slug": normalize_horse(row.get("Horse")),
            "pos": p,
            "sp": row.get("SP")
        })

def detect_date(d):
    m = re.match(r"(\d{4}-\d{2}-\d{2})", d.name)
    return m.group(1) if m else ""

data = []

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
        race_lookup = {x["horse_slug"]: x for x in hist}
        
        for hnum, horse in logic.get("horses", {}).items():
            hslug = normalize_horse(horse.get("horse_name"))
            hr = race_lookup.get(hslug)
            if not hr: continue
            
            d_obj = horse.get("_data", {})
            starts = parse_int(horse.get("career_race_starts"))
            if starts is None: starts = 0
            
            data.append({
                "pos": hr["pos"],
                "top3": hr["pos"] <= 3,
                "winner": hr["pos"] == 1,
                "weight": parse_float(horse.get("weight")),
                "starts": starts,
                "debut": starts == 0,
                "trial_count": parse_int(d_obj.get("trial_count")) or 0,
                "trial_top3": parse_int(d_obj.get("trial_top3_count")) or 0,
                "barrier": parse_int(horse.get("barrier")),
                "status_cycle": horse.get("status_cycle", ""),
                "recent_form": horse.get("recent_form", ""),
                "sp": parse_float(hr["sp"])
            })

print(f"Total Maiden Horses Evaluated: {len(data)}")

top3 = [x for x in data if x["top3"]]
rest = [x for x in data if not x["top3"]]

def avg(lst, key):
    vals = [x[key] for x in lst if x[key] is not None]
    return statistics.mean(vals) if vals else 0.0

def prop(lst, condition):
    return sum(1 for x in lst if condition(x)) / len(lst) if lst else 0.0

print("\n--- WEIGHT ---")
print(f"Avg Weight - Top 3: {avg(top3, 'weight'):.2f}kg | Rest: {avg(rest, 'weight'):.2f}kg")
print(f"% Heavy (>=59.0kg) - Top 3: {prop(top3, lambda x: x['weight'] >= 59.0):.1%} | Rest: {prop(rest, lambda x: x['weight'] >= 59.0):.1%}")
print(f"% Light (<57.0kg) - Top 3: {prop(top3, lambda x: x['weight'] < 57.0):.1%} | Rest: {prop(rest, lambda x: x['weight'] < 57.0):.1%}")

print("\n--- STARTS & DEBUTANTS ---")
print(f"Avg Career Starts - Top 3: {avg(top3, 'starts'):.2f} | Rest: {avg(rest, 'starts'):.2f}")
print(f"% Debutants (0 starts) - Top 3: {prop(top3, lambda x: x['debut']):.1%} | Rest: {prop(rest, lambda x: x['debut']):.1%}")
print(f"% Lightly Raced (1-3 starts) - Top 3: {prop(top3, lambda x: not x['debut'] and x['starts'] <= 3):.1%} | Rest: {prop(rest, lambda x: not x['debut'] and x['starts'] <= 3):.1%}")
print(f"% Exposed (>=8 starts) - Top 3: {prop(top3, lambda x: x['starts'] >= 8):.1%} | Rest: {prop(rest, lambda x: x['starts'] >= 8):.1%}")

print("\n--- DEBUTANT TRIAL QUALITY ---")
debut_top3 = [x for x in top3 if x["debut"]]
debut_rest = [x for x in rest if x["debut"]]
print(f"For Debutants: Avg Trial Count - Top 3: {avg(debut_top3, 'trial_count'):.2f} | Rest: {avg(debut_rest, 'trial_count'):.2f}")
print(f"For Debutants: % with Trial Top3 > 0 - Top 3: {prop(debut_top3, lambda x: x['trial_top3'] > 0):.1%} | Rest: {prop(debut_rest, lambda x: x['trial_top3'] > 0):.1%}")

print("\n--- BARRIER ---")
print(f"Avg Barrier - Top 3: {avg(top3, 'barrier'):.2f} | Rest: {avg(rest, 'barrier'):.2f}")

print("\n--- MARKET ---")
print(f"Avg SP - Top 3: {avg(top3, 'sp'):.2f} | Rest: {avg(rest, 'sp'):.2f}")
