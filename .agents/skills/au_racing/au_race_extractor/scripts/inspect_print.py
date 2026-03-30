from bs4 import BeautifulSoup
import re

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print(f"Total HTML length: {len(text)}")
print("First 100 chars:", text[:100])

horse_divs = soup.find_all('div', class_=re.compile('horse'))
print(f"Number of divs with class 'horse': {len(horse_divs)}")

# Find all text containing "Absolute Power"
import re
texts = soup.find_all(string=re.compile("Absolute Power"))
for t in texts:
    print("Found text:", t.strip())
    p = t.parent
    for i in range(5):
        if p:
            print(f"Parent {i}: {p.name} class={p.get('class')}")
            p = p.parent
    print("---")
