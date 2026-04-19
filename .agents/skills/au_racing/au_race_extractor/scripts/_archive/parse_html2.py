import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup
import re

with open('./racenet_curl.html', 'r') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

celerity = soup.find(string=re.compile("Celerity"))
if celerity:
    parent = celerity.parent
    while parent and parent.name != 'body':
        print(f"<{parent.name} class={parent.get('class')}>")
        parent = parent.parent
