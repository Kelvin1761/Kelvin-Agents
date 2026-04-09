from bs4 import BeautifulSoup
import re

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print("Looking for known form guide string...")
runs = soup.find_all(string=re.compile(r"Boxed on steadily to line"))
for r in runs:
    print("Found string:", r.strip())
    parent = r.parent
    for _ in range(5):
        if not parent: break
        print(f"Parent: {parent.name} class={parent.get('class')}")
        parent = parent.parent
        
    p2 = r.find_parent('div', class_=re.compile("form|run|race|details"))
    if p2:
        print("\nContainer found:", p2.get('class'))
        print("HTML Dump:\n", p2.prettify()[:1000])
