import json, os

base = "archive race analysis/hkjc results 2025 26"
dirs = [d for d in sorted(os.listdir(base), reverse=True)
        if os.path.isdir(os.path.join(base, d))
        and os.path.exists(os.path.join(base, d, "full_day_results.json"))]

fp = os.path.join(base, dirs[0], "full_day_results.json")
data = json.load(open(fp, "r", encoding="utf-8-sig"))

# Show first race fully
race = list(data.values())[0]

print("=== ALL RUNNERS ===")
for r in race["results"]:
    print(f"  {r['horse_name']}  pos={r['pos']}  draw={r['draw']}  "
          f"rp={r['running_positions']}  lbw={r['lbw']}  "
          f"ft={r['finish_time']}  odds={r['win_odds']}  "
          f"actual_wt={r['actual_wt']}  horse_wt={r['horse_wt']}")

print("\n=== FULL SECTIONAL_TIMES ===")
for row in race.get("sectional_times", []):
    print(row)

print("\n=== CUMULATIVE_TIMES ===")
for row in race.get("cumulative_times", []):
    print(row)

print("\n=== INCIDENT_REPORT ===")
print(race.get("incident_report", "N/A"))

# Check second race for class info
race2 = list(data.values())[1]
print("\n=== RACE 2 SECTIONAL_TIMES (for class) ===")
for row in race2.get("sectional_times", [])[:5]:
    print(row)
