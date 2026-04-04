import re
from curl_cffi import requests

url = 'https://www.racenet.com.au/form-guide/horse-racing/randwick-20260404'
resp = requests.get(url, impersonate='chrome120', verify=False, timeout=30)
html = resp.text

links = re.findall(r'randwick-20260404/([^/]+-\d+)/', html)
# also try with event slugs that end with race-\d+
unique_slugs = sorted(set(links))

print(f"Found {len(unique_slugs)} slugs:")
for slug in unique_slugs:
    print(f"  {slug}")

if not unique_slugs:
    links = re.findall(r'randwick-20260404/([^/"]+)', html)
    unique_slugs = sorted(set(links))
    print(f"Found {len(unique_slugs)} slugs with alternative regex:")
    for slug in unique_slugs:
        print(f"  {slug}")
