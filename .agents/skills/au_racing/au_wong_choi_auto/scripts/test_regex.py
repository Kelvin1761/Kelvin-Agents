import json
import re
from pathlib import Path
from au_archive_calibrator import normalize_horse_name, ARCHIVE_ROOT

def get_true_horse_name(horse: dict) -> str:
    data = horse.get("_data") or {}
    facts = data.get("facts_section") or ""
    match = re.search(r"^\[\d+\]\s+([^(]+?)(?:\s+\(\d+\))?\n", facts)
    if match:
        return match.group(1).strip()
    return str(horse.get("horse_name") or "").strip()

total_horses = 0
fixed_horses = 0
for meeting_dir in ARCHIVE_ROOT.iterdir():
    if not meeting_dir.is_dir(): continue
    for logic_path in meeting_dir.glob("Race_*_Logic.json"):
        sample = json.loads(logic_path.read_text())
        for horse in sample.get("horses", {}).values():
            total_horses += 1
            orig = str(horse.get("horse_name") or "").strip()
            true_name = get_true_horse_name(horse)
            if orig != true_name:
                fixed_horses += 1
                if fixed_horses <= 5:
                    print(f"Fixed: {orig} -> {true_name}")
print(f"Total: {total_horses}, Fixed: {fixed_horses}")
