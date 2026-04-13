import os
import re

dir_path = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/2026-04-14 Hawkesbury Race 1-7"
date_prefix = "04-14"

def split_file(file_type):
    combined_path = os.path.join(dir_path, f"{date_prefix} Race 1-7 {file_type}.md")
    if not os.path.exists(combined_path):
        print(f"Not found: {combined_path}")
        return
    with open(combined_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Split by `RACE (\d+) —`
    chunks = re.split(r'(?=RACE \d+ — )', content)
    for chunk in chunks:
        m = re.search(r'RACE (\d+) —', chunk)
        if m:
            r = m.group(1)
            out_path = os.path.join(dir_path, f"Race {r} {file_type}.md")
            with open(out_path, "w", encoding="utf-8") as out:
                out.write(chunk)
            print(f"Wrote {out_path}")

split_file("Racecard")
split_file("Formguide")
