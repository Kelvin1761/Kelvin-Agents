import sys
import os
import glob
import json

base_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/Archive_Race_Analysis/AU_Racing"
# Or search all Race_*_Logic.json to be more robust
search_pattern = os.path.join(base_path, "**", "Race_*_Logic.json")
files = glob.glob(search_pattern, recursive=True)

if not files:
    # Also try the root directory
    base_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
    search_pattern = os.path.join(base_path, "**", "Race_*_Logic.json")
    files = glob.glob(search_pattern, recursive=True)

stats = {
    "stability": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "race_shape": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "jockey_trainer": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "class_weight": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "track": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "form_line": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0},
    "sectional": {"total": 0, "60s": 0, "sum": 0, "sum_sq": 0}
}

for f in files:
    if "HKJC" in f or "Archive_" not in f:
        # Just use archive to be fast and broad
        pass
        
    try:
        with open(f, "r") as json_file:
            data = json.load(json_file)
            for horse_id, horse_data in data.get("horses", {}).items():
                matrix = horse_data.get("python_auto", {}).get("matrix_scores", {})
                if not matrix:
                    continue
                
                for key in stats.keys():
                    val = matrix.get(key)
                    if val is not None:
                        val = float(val)
                        stats[key]["total"] += 1
                        if val == 60.0:
                            stats[key]["60s"] += 1
                        stats[key]["sum"] += val
                        stats[key]["sum_sq"] += val * val
    except Exception as e:
        continue

print("Matrix Diagnostics (Checking for constant 60s):")
print("-" * 50)
for key, data in stats.items():
    total = data["total"]
    if total == 0:
        print(f"{key}: NO DATA")
        continue
    
    pct_60 = (data["60s"] / total) * 100
    mean = data["sum"] / total
    variance = (data["sum_sq"] / total) - (mean * mean)
    stddev = variance ** 0.5
    print(f"{key:>15}: {pct_60:>6.2f}% are exactly 60.0 | Mean: {mean:.1f} | StdDev: {stddev:.2f}")

