from pathlib import Path

engine_file = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py")
lines = engine_file.read_text(encoding="utf-8").splitlines()

# Find the line: if not tw_avg or not tw_count or tw_count < 2:
start_idx = -1
for i, line in enumerate(lines):
    if 'if not tw_avg or not tw_count or tw_count < 2:' in line:
        start_idx = i
        break

if start_idx != -1:
    # Insert `        else:` at start_idx + 2
    # And indent everything from start_idx + 2 until `l600_score = clip_score(l600_score)`
    end_idx = -1
    for i in range(start_idx + 2, len(lines)):
        if 'l600_score = clip_score(l600_score)' in lines[i]:
            end_idx = i
            break
    
    if end_idx != -1:
        new_lines = lines[:start_idx + 2]
        new_lines.append("        else:")
        for i in range(start_idx + 2, end_idx):
            if lines[i].strip():
                new_lines.append("    " + lines[i])
            else:
                new_lines.append("")
        new_lines.extend(lines[end_idx:])
        engine_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        print("Indentation fixed.")
    else:
        print("End marker not found")
else:
    print("Start marker not found")
