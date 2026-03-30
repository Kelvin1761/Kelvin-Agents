import sys
sys.path.append("/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts")
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

with open("/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/live_page.html", "w") as f:
    f.write(html_content)

print("Saved live HTML!")
