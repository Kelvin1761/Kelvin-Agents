import re
import subprocess

p = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\Open Dashboard.html'
with open(p, 'r', encoding='utf-8') as f:
    html = f.read()

# Find the main script tag
match = re.search(r'<script>(.*?)</script>', html, re.DOTALL)
if match:
    js_code = match.group(1)
    # The JSON data is injected into `const DASHBOARD_DATA = ...`
    out_js = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\test_script.js'
    with open(out_js, 'w', encoding='utf-8') as f:
        f.write(js_code)
    print("Extracted JS to test_script.js")
else:
    print("Could not find <script> tag.")
