import os
import tempfile
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import urllib.parse
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import re

url = "https://racing.hkjc.com/zh-hk/local/info/speedpro/formguide?racedate=2026/03/04&Racecourse=HV&RaceNo=2"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, wait_until='networkidle')
    page.wait_for_timeout(3000)
    html_content = page.content()
    browser.close()

# Debug dumps go to a scratch dir, never into the repo. Writing them beside the
# script kept `live_page.html` tracked-and-modified after every run, so
# `git status` was permanently dirty and every release needed
# `--allow-unrelated`. Nothing reads these files — they are eyeball artefacts.
# 舊嘅 checked-in dump 冇刪（`git add` 加唔到一個已經 `git rm` 咗嘅路徑，
# 而 `保存.sh` 就係用 `git add`）—— 但既然冇人再寫落去，佢就永遠唔會再變。
out_dir = os.environ.get("WC_SCRATCH_DIR") or tempfile.gettempdir()
out_path = os.path.join(out_dir, "live_page.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html_content)

print(f"Saved live HTML! -> {out_path}")
