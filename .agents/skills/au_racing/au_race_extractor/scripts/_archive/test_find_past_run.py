from bs4 import BeautifulSoup
import re

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

print("Looking for a specific past run indicator...")
# In racenet, usually the placing is like "4th/9" and there's a date and track.
# Let's find any element containing '4th/9'
runs = soup.find_all(string=re.compile(r"4th/9"))
for r in runs:
    parent = r.parent
    for _ in range(3):
        if not parent: break
        print(f"Parent Class: {parent.get('class')}")
        parent = parent.parent

    # Let's get the container that holds the entire past run
    # usually it's a div with some class like `form-guide-horse__past-run` or `printing-past-run`
    run_container = r.find_parent('div', class_=re.compile("run|race|competitor|form"))
    if run_container:
        print(f"Run Container Class: {run_container.get('class')}")
        print("Text:", run_container.get_text(" | ", strip=True)[:300])
        print("--- HTML ---")
        print(run_container.prettify()[:500])
