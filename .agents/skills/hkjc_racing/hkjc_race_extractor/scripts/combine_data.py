import os

target_dir = '/Users/imac/Desktop/Drive/Antigravity/2026-03-04Happy Valley'
os.makedirs(target_dir, exist_ok=True)

# Determine the date prefix and race range based on hardcoded knowledge for this specific task
date_prefix = "03-04" 
races = [3, 4]
if len(races) > 1:
    race_str = f"Race {min(races)}-{max(races)}"
elif len(races) == 1:
    race_str = f"Race {races[0]}"
else:
    race_str = "Race Unknown"

# New file names logic
racecard_filename = f"{date_prefix} {race_str} 排位表.txt"
formguide_filename = f"{date_prefix} {race_str} 賽績.txt"

# Combine Racecards
print(f"Combining racecards into {racecard_filename}...")
with open(os.path.join(target_dir, racecard_filename), 'w') as out_f:
    for i in races:
        f_path = f'/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/racecard_{i}.txt'
        if os.path.exists(f_path):
            with open(f_path, 'r') as in_f:
                out_f.write(in_f.read())
                out_f.write('\n\n# ==========================================\n\n')

# Combine Form Guides
print(f"Combining formguides into {formguide_filename}...")
with open(os.path.join(target_dir, formguide_filename), 'w') as out_f:
    for i in races:
        f_path = f'/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/formguide_{i}.txt'
        if os.path.exists(f_path):
            with open(f_path, 'r') as in_f:
                lines = in_f.readlines()
                for line in lines:
                    if "Extracting form guide using Playwright" in line:
                        pass # filter out standard output logs
                    else:
                        out_f.write(line)
                out_f.write('\n\n# ==========================================\n\n')

# Delete Old Output Files
old_rc = os.path.join(target_dir, 'all_races_racecard.txt')
if os.path.exists(old_rc): os.remove(old_rc)
old_fg = os.path.join(target_dir, 'all_races_formguide.txt')
if os.path.exists(old_fg): os.remove(old_fg)

print("Done combining files natively with new naming format.")
