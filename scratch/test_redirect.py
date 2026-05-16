from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup
import sys
if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')

url = "https://racing.hkjc.com/racing/information/Chinese/Racing/LocalResults.aspx?RaceDate=2024/09/08&RaceNo=1"
resp = cffi_requests.get(url, impersonate="chrome120", allow_redirects=True)
print(f"Final URL: {resp.url}")
soup = BeautifulSoup(resp.text, 'html.parser')
table = soup.find('table', class_='f_tac')
if table:
    print(f"Success! Found table on {resp.url}")
else:
    print(f"Failed to find table on {resp.url}")
