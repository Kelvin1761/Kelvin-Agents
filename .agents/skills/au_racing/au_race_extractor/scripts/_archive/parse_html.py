from bs4 import BeautifulSoup

with open('/Users/imac/Desktop/Drive/Antigravity/racenet_curl.html', 'r') as f:
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
