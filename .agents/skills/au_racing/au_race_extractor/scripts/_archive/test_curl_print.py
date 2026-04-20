import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from curl_cffi import requests

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

url_print = "https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug=caulfield-heath-20260304&eventSlug=briga-fliedner-2026-lady-of-racing-finalist-race-1&printSlug=print-form"

print(f"Fetching {url_print}")
try:
    response = requests.get(url_print, impersonate="chrome120", headers=headers, timeout=30)
    print(f"Status Code: {response.status_code}")
    with open('./racenet_print_curl.html', 'w', encoding='utf-8') as f:
        f.write(response.text)
    print("Saved to racenet_print_curl.html")
except Exception as e:
    print(f"Error: {e}")
