import os
import ag_wong_choi_analyst

target_dir = "2026-04-12_ShaTin"
for r in range(2, 12):
    # Fix the filename construction
    facts_file = os.path.join(target_dir, f"04-12_ShaTin Race {r} Facts.md")
    # Redefine the function internally to just use facts_file directly
    ag_wong_choi_analyst.generate_race_logic.__globals__['os'] = os
    # We can just change the facts_file path in the script and re-run.
