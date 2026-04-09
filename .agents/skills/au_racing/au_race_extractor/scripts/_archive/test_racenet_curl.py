from curl_cffi import requests
import os

def dump():
    url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"
    r = requests.get(url, impersonate="chrome110")
    
    with open('./racenet_curl.html', 'w') as f:
        f.write(r.text)
    print("Dumped racenet_curl.html, size:", len(r.text))

dump()
