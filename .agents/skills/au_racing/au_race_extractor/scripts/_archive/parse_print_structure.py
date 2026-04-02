from bs4 import BeautifulSoup

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print("Classes containing 'horse':")
count = 0
for tag in soup.find_all(class_=lambda x: x and isinstance(x, list) and any('horse' in c for c in x)):
    print(tag.name, tag.get('class'))
    count += 1
    if count > 5: break

# Let's find exactly the container for Absolute Power
abs_power = soup.find(string=lambda s: s and "1. Absolute Power" in s)
if abs_power:
    print("\nFound Absolute Power!")
    parent = abs_power.parent
    for _ in range(7):
        if parent:
            print(f"Parent: <{parent.name} class='{parent.get('class')}'>")
            parent = parent.parent
