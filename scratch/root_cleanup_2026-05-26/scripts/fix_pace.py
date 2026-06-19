import sys
from pathlib import Path

path = Path(".agents/skills/au_racing/au_wong_choi_auto/scripts/racing_engine/engine_core.py")
lines = path.read_text().splitlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if line.strip() == 'if style_conf in {"高", "High"}:':
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if line.strip() == 'if geometry_fit and not any(geometry_fit in note for note in notes):':
        end_idx = i
        break

if start_idx != -1:
    # Let's find end_idx dynamically by searching backwards from return score
    for i in range(start_idx, len(lines)):
        if 'if geometry_fit and not any(geometry_fit in note for note in notes):' in lines[i]:
            end_idx = i
            break
            
    print(f"Removing lines from {start_idx} to {end_idx-1}")
    new_lines = lines[:start_idx] + lines[end_idx:]
    path.write_text("\n".join(new_lines) + "\n")
else:
    print("Could not find start_idx")
