#!/usr/bin/env python3
import os
import subprocess
from pathlib import Path

def run():
    meeting_dir = Path("2026-05-09_ShaTin")
    facts_files = sorted(list(meeting_dir.glob("* Facts.md")))
    
    for facts_file in facts_files:
        # Extract race number from filename (e.g., "05-09 Race 1 Facts.md")
        name = facts_file.name
        import re
        match = re.search(r"Race (\d+)", name)
        if not match:
            continue
        race_num = int(match.group(1))
        
        print(f"--- Processing Race {race_num} ---")
        
        # Read facts file to find all horses
        with open(facts_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        horse_nums = re.findall(r"### 馬號 (\d+)", content)
        for h_num in horse_nums:
            print(f"  Generating skeleton for Horse {h_num}...")
            # Usage: python3 create_hkjc_logic_skeleton.py <facts_path> <race_num> <horse_num>
            cmd = [
                "python3", 
                ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py",
                str(facts_file),
                str(race_num),
                str(h_num)
            ]
            subprocess.run(cmd)

if __name__ == "__main__":
    run()
