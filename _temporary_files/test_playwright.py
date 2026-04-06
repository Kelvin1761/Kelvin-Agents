from curl_cffi import requests

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Origin": "https://prizepicks.com",
    "Referer": "https://prizepicks.com/",
}

# The GraphQL endpoint usually needs cookies, but let's test if there is any other endpoint
url = "https://api.prizepicks.com/projections?league_id=7&per_page=1"
try:
    r = requests.get(url, impersonate="chrome120", headers=headers, timeout=5)
    print("PrizePicks Status Code:", r.status_code)
except Exception as e:
    print(e)
