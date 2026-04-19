import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import urllib.request
import ssl
from bs4 import BeautifulSoup

url = "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/03/04&Racecourse=HV&RaceNo=3"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
try:
    with urllib.request.urlopen(req, context=ctx) as response:
        html = response.read().decode('utf-8')
        soup = BeautifulSoup(html, 'html.parser')
        print("=== Header Info ===")
        for div in soup.find_all('div', class_='race-meeting-info'):
            print(div.text.strip())
        for div in soup.find_all('div', class_='bg-blue'):
            print(div.text.strip())
        
        print("\n=== Horses ===")
        table = soup.find('table', class_='draggable')
        if table:
            headers = [th.text.strip() for th in table.find_all('th')]
            print("Headers:", headers)
            for tr in table.find('tbody').find_all('tr'):
                tds = [td.text.strip().replace('\n', ' ') for td in tr.find_all('td')]
                print("Row:", tds)
        else:
            print("Could not find table")
except Exception as e:
    print(f"Error: {e}")
