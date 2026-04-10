import os
import re
from pathlib import Path

target_dir = "2026-04-11 Randwick Race 1-10"

for i in range(1, 11):
    rc_path = f"{target_dir}/04-11 Race {i} Racecard.md"
    if not os.path.exists(rc_path): continue
    
    rc_text = Path(rc_path).read_text()
    
    # Extract jockey and trainer
    horse_info = {}
    blocks = rc_text.split("----------------------------------------")
    for block in blocks:
        m = re.search(r'^(\d+)\.\s+(.+?)\s*\((\d+)\)', block.strip(), re.MULTILINE)
        if m:
            hnum = m.group(1)
            j_m = re.search(r'Jockey:\s*([^|]+)', block)
            t_m = re.search(r'Trainer:\s*([^|]+)', block)
            j = j_m.group(1).strip() if j_m else "Unknown"
            t = t_m.group(1).strip() if t_m else "Unknown"
            horse_info[hnum] = (j, t)
            
    # Update Facts.md
    f_path = f"{target_dir}/04-11 Race {i} Facts.md"
    if os.path.exists(f_path):
        f_text = Path(f_path).read_text()
        new_f_text = []
        for line in f_text.split('\n'):
            m = re.match(r'^(### 馬匹 #(\d+) .+? \(檔位 \d+\))$', line)
            if m:
                base = m.group(1)
                hnum = m.group(2)
                j, t = horse_info.get(hnum, ("Unknown", "Unknown"))
                # Only append if not already appended
                if "| 騎師" not in line:
                    line = f"{base} | 騎師: {j} | 練馬師: {t}"
            new_f_text.append(line)
        Path(f_path).write_text('\n'.join(new_f_text))
        
    # Update Analysis.md
    a_path = f"{target_dir}/04-11 Race {i} Analysis.md"
    if os.path.exists(a_path):
        a_text = Path(a_path).read_text()
        new_a_text = []
        for line in a_text.split('\n'):
            # ### 【No.1】Hydrobomb (檔位:4) | 評級: A+
            m = re.match(r'^(### 【No\.(\d+)】.+? \(檔位:\d+\)) \| 評級: (.+)$', line)
            if m:
                base = m.group(1)
                hnum = m.group(2)
                rating = m.group(3)
                j, t = horse_info.get(hnum, ("Unknown", "Unknown"))
                if "| 騎師" not in line:
                    line = f"{base} | 騎師: {j} | 練馬師: {t} | 評級: {rating}"
            new_a_text.append(line)
        Path(a_path).write_text('\n'.join(new_a_text))

print("Patching complete!")
