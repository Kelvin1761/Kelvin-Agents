import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import urllib.request

url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'})

try:
    with urllib.request.urlopen(req) as response:
        html = response.read().decode('utf-8')
        print("Overview Length:", len(html))
        print("Contains '10 Results'?", "10 Results" in html)
        with open('racenet_overview.html', 'w', encoding='utf-8') as f:
            f.write(html)
except Exception as e:
    print("Overview Error:", e)

url_print = "https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug=caulfield-heath-20260304&eventSlug=briga-fliedner-2026-lady-of-racing-finalist-race-1&printSlug=print-form"
req_print = urllib.request.Request(url_print, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'})

try:
    with urllib.request.urlopen(req_print) as response:
        html = response.read().decode('utf-8')
        print("Print Form Length:", len(html))
        with open('racenet_print.html', 'w', encoding='utf-8') as f:
            f.write(html)
except Exception as e:
    print("Print Form Error:", e)
