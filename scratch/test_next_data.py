from curl_cffi import requests as cffi_requests
url = "https://racing.hkjc.com/zh-hk/local/information/localresults?RaceDate=2024/09/08&RaceNo=1"
resp = cffi_requests.get(url, impersonate="chrome120")
if "__NEXT_DATA__" in resp.text:
    print("Found __NEXT_DATA__ script tag!")
    start = resp.text.find("__NEXT_DATA__")
    print(resp.text[start:start+200])
else:
    print("NOT found __NEXT_DATA__")
