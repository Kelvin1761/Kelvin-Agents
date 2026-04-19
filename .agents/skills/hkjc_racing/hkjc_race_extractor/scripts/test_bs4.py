import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import urllib.parse
from bs4 import BeautifulSoup
import re

html = open("/Users/imac/Desktop/Drive/Antigravity/.agents/skills/hkjc_race_extractor/scripts/page.html").read()

soup = BeautifulSoup(html, 'html.parser')
trs = soup.find_all('tr')
horses = [tr for tr in trs if 'comment' in tr.get('class', [])]
print(f"Found {len(horses)} horses by tr.comment!")

# See if any tr has comment-title td
trs_with_comment_title = []
for tr in soup.find_all('tr'):
    for td in tr.find_all('td'):
        if 'comment-title' in td.get('class', []):
            trs_with_comment_title.append(tr)
            break
print(f"Found {len(trs_with_comment_title)} horses by td.comment-title!")
