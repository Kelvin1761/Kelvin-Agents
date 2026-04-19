import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import re
import json

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

# Look for window.__NUXT__=(function(...){...}(...));
# It contains huge data objects.
nuxt_start = text.find('window.__NUXT__=(function')
if nuxt_start != -1:
    print("Found window.__NUXT__")
    # Finding the closing ); of the IIFE is tricky.
    # Let's extract the raw script tag contents.
    script_start = text.rfind('<script', 0, nuxt_start)
    script_end = text.find('</script>', nuxt_start)
    script_content = text[nuxt_start:script_end]
    
    with open('./.agents/skills/au_race_extractor/scripts/nuxt.js', 'w') as out:
        out.write(script_content)
    print("Saved nuxt payload to nuxt.js, length:", len(script_content))
