import os
import glob
from pathlib import Path
import re

files = [
    '.agents/skills/au_racing/claw_racenet_results.py',
    '.agents/skills/au_racing/claw_racenet_scraper.py',
    '.agents/skills/au_racing/claw_profile_scraper.py',
    '.agents/skills/au_racing/au_wong_choi/scripts/generate_meeting_intel.py'
]

for filepath in files:
    if os.path.exists(filepath):
        p = Path(filepath)
        content = p.read_text(encoding='utf-8')
        
        # Replace occurrences of page.goto(f"file://...") without wait_until
        def replace_goto(m):
            if 'wait_until' not in m.group(0):
                return m.group(1) + ', wait_until="domcontentloaded")'
            return m.group(0)
            
        new_content = re.sub(
            r'(page\.goto\([^\)]+?"file://[^\)]+?)\)',
            replace_goto,
            content
        )
        
        if new_content != content:
            p.write_text(new_content, encoding='utf-8')
            print(f'Updated {filepath}')
