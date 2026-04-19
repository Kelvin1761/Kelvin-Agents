import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from bs4 import BeautifulSoup

with open('./racenet_curl.html', 'r') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

# Try to find horse rows
rows = soup.select('.fg-event-card-container .horse-racing')
print(f"Found {len(rows)} potential horse rows based on .horse-racing")

# Another common class
cards = soup.select('.fg-event-card')
print(f"Found {len(cards)} .fg-event-card elements")

for card in cards[:2]:
    print("---")
    print(card.get_text(strip=True)[:500])
