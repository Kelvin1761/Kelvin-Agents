import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup
import json
import re

with open('./racenet_print_curl.html', 'r') as f:
    text = f.read()

print(f"File length: {len(text)}")
soup = BeautifulSoup(text, 'html.parser')

print("Title:", soup.title.string if soup.title else "No title")

# Look for horse names
for name in ["Absolute Power", "Weasel Sea", "California Flyer"]:
    found = text.find(name)
    print(f"'{name}' found at index {found}")
