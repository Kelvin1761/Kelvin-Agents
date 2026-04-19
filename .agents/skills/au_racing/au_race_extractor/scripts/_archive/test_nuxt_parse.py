import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import re

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

# Let's find Nuxt script
nuxt_match = re.search(r'window\.__NUXT__=\(function\((.*?)\)\{return \{state:(.*?)\}\}\((.*?)\)\);', text)

if nuxt_match:
    print("Found exact Nuxt JS structure!")
    args = nuxt_match.group(1).split(',')
    vals = nuxt_match.group(3).split(',')
    
    print(f"Num args: {len(args)}, Num vals: {len(vals)}")
    print("Args mapping:")
    for i in range(min(5, len(args))):
        print(f"  {args[i]} = {vals[i]}")
        
    state_str = nuxt_match.group(2)
    print(f"\nState string length: {len(state_str)}")
    print("Start:", state_str[:200])
    print("End:", state_str[-200:])
else:
    print("Did not match NUXT regex.")
