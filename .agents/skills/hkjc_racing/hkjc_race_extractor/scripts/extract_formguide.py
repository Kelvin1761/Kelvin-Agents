import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
DEPRECATED: This placeholder script is no longer the primary extraction method.

Use scripts/extract_formguide.js instead, executed via browser_execute_js
on the HKJC Form Guide page. The JS script extracts all data from the DOM
in a single call and returns structured JSON.

See SKILL.md for full instructions.
"""

def extract_formguide(url):
    print("DEPRECATED: Use extract_formguide.js via browser_execute_js instead.")
    print(f"URL: {url}")
    pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_formguide(sys.argv[1])
