import re
import json
from curl_cffi import requests

url = "https://www.sportsbet.com.au/betting/basketball-us/nba/miami-heat-at-toronto-raptors-10345078"
resp = requests.get(url, impersonate="chrome120")
html = resp.text

match = re.search(r"window\.__APOLLO_STATE__\s*=\s*(.*?);</script>", html)
if match:
    state = json.loads(match.group(1))
    print(f"Total keys: {len(state.keys())}")
    for k in list(state.keys())[:30]:
        print(k)
        
match2 = re.search(r"window\.__PRELOADED_STATE__\s*=\s*(.*?);</script>", html)
if match2:
    state2 = json.loads(match2.group(1))
    print("Found PRELOADED_STATE!")
    print(list(state2.keys())[:20])
