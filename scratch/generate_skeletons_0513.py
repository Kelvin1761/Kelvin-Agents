
import os
import subprocess
import re
from pathlib import Path

def run():
    meeting_dir = Path("2026-05-13_HappyValley")
    facts_files = sorted(list(meeting_dir.glob("* Facts.md")))
    
    for facts_file in facts_files:
        name = facts_file.name
        match = re.search(r"Race (\d+)", name)
        if not match:
            continue
        race_num = int(match.group(1))
        
        print(f"--- Processing Race {race_num} ---")
        
        with open(facts_file, "r", encoding="utf-8") as f:
            content = f.read()
            
        horse_nums = re.findall(r"### 馬號 (\d+)", content)
        for h_num in horse_nums:
            print(f"  Generating skeleton for Horse {h_num}...")
            # Using 'python' instead of 'python3' for Windows
            cmd = [
                "python", 
                ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py",
                str(facts_file),
                str(race_num),
                str(h_num)
            ]
            subprocess.run(cmd, env=os.environ.copy())

if __name__ == "__main__":
    os.environ['PYTHONUTF8'] = '1'
    run()
