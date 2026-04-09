from bs4 import BeautifulSoup
import re

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print("Parsing HTML...")
# Find the horse header
horses = soup.find_all(string=re.compile(r"Absolute Power"))
for h in horses:
    print(f"Found hit: '{h.strip()}'")
    # Looking for a structured parent
    parent = h.parent
    for _ in range(5):
        if not parent: break
        print(f"  Parent: <{parent.name} class='{parent.get('class')}'> text: {parent.get_text(separator='|', strip=True)[:100]}")
        parent = parent.parent

# Let's try to find all form guide blocks
# Usually they are inside a container like 'form-guide-horse' or similar
blocks = soup.find_all('div', class_=re.compile('horse-details|competitor|runner|print'))
print(f"Found {len(blocks)} potential horse blocks.")

# Let's find exactly the form guide table or rows for Absolute Power
print("\n--- Rows with 'Absolute Power' ---")
for tag in soup.find_all(string=re.compile("Absolute Power")):
    p = tag.find_parent('div', class_=re.compile("event(?:-selection|-card)"))
    if p:
        print(f"Parent Match: {p.get('class')}")
        print(p.get_text(" ", strip=True)[:200])
