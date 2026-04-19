import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import urllib.request
import ssl
from bs4 import BeautifulSoup
import json

url = "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/03/04&Racecourse=HV&RaceNo=3"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx) as response:
    html = response.read().decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    
    # Dump the first 幾 lines of the main content
    main = soup.find('div', class_='race_tab')
    if main:
        print("FOUND race_tab text:")
        print(main.text.replace('\n\n', '\n')[:500])
    
    # Or maybe the title is in a different container
    title = soup.find('title')
    print("Title:", title.text if title else "")

    for r in soup.find_all('div', class_='row'):
        if '米' in r.text and '班' in r.text:
            print("FOUND row with class info:")
            print(r.text.strip())
            break
