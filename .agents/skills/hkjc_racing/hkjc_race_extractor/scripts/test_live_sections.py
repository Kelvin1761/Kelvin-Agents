import os
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

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_page.html"), "w", encoding="utf-8") as f:
    f.write(html_content)

print("Saved live HTML!")
