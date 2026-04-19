import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import urllib.request
import ssl

url = "https://racing.hkjc.com/zh-hk/local/info/speedpro/formguide?racedate=2026/03/04&Racecourse=HV&RaceNo=2"

# Bypass SSL verification if needed
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

req = urllib.request.Request(
    url, 
    headers={'User-Agent': 'Mozilla/5.0'}
)

try:
    with urllib.request.urlopen(req, context=ctx) as response:
        html = response.read().decode('utf-8')
        print(f"Length: {len(html)}")
        print("Has horses?", "問鼎巔峰" in html)
        print("Has speedpro?", "速勢能量" in html)
except Exception as e:
    print(f"Error: {e}")
