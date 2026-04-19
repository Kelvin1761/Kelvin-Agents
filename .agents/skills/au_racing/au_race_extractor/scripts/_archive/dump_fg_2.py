import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

details = soup.find('div', class_='racing-full-form-details')
if details:
    html = details.prettify()
    print(html[2000:5000])
