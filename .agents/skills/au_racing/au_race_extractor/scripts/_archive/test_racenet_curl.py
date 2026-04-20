import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from curl_cffi import requests

def dump():
    url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"
    r = requests.get(url, impersonate="chrome110")
    
    with open('./racenet_curl.html', 'w', encoding='utf-8') as f:
        f.write(r.text)
    print("Dumped racenet_curl.html, size:", len(r.text))

dump()
