from bs4 import BeautifulSoup

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

stats = soup.find('div', class_='print-form__stats')
if stats:
    print("Found print-form__stats!")
    # Inside this, there are probably past runs?
    divs = stats.find_all('div', recursive=False)
    print(f"Direct children of print-form__stats: {len(divs)}")
    
    for i, child in enumerate(divs):
        print(f"\nChild {i} classes: {child.get('class')}")
        # Look for full form details
        full_form = child.find('div', class_='racing-full-form-details')
        if full_form:
            print("  Found racing-full-form-details!")
            runs = child.find_all('div', class_='printing-past-run')
            print(f"  Found {len(runs)} past runs (printing-past-run)!")
            if runs:
                print("  Sample run:")
                print(runs[0].get_text(" | ", strip=True)[:300])
        else:
            print(f"  Text: {child.get_text(' | ', strip=True)[:200]}")
