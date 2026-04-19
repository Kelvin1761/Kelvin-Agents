import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

script = soup.find(string=lambda s: s and "window.__NUXT__" in s)

if script:
    print("Found window.__NUXT__ !!")
    # window.__NUXT__=(function(a,b,...){return {state:...}}(...));
    # Let's just find "Absolute Power" in it
    idx = script.find("Absolute Power")
    print(f"Index of 'Absolute Power' inside script: {idx}")
    print("Script string length:", len(script))
else:
    print("Not found.")
