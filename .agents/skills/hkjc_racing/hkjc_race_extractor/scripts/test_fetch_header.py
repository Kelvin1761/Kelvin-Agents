import urllib.request
import ssl
from bs4 import BeautifulSoup

url = "https://racing.hkjc.com/zh-hk/local/information/racecard?racedate=2026/03/04&Racecourse=HV&RaceNo=3"
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req, context=ctx) as response:
    html = response.read().decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    
    print("ALL CLASS NAMES of div:")
    classes = set()
    for div in soup.find_all('div'):
        c = div.get('class')
        if c:
            classes.add(" ".join(c))
    print(list(classes)[:20])
    
    print("Titles:", [h.text.strip() for h in soup.find_all(['h1', 'h2', 'h3'])])
