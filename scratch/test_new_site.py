from curl_cffi import requests as cffi_requests
import sys

# Ensure UTF-8 output
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

url = "https://racing.hkjc.com/zh-hk/local/information/localresults?RaceDate=2024/09/08&RaceNo=1"
resp = cffi_requests.get(url, impersonate="chrome120")
print(f"Status: {resp.status_code}")
print(f"Content Length: {len(resp.text)}")
if "上市魅力" in resp.text:
    print("Found '上市魅力' in raw HTML!")
else:
    print("NOT found in raw HTML. It might be Client-Side Rendered.")
