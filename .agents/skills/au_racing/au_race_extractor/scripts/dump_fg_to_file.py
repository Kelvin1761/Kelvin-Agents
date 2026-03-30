from bs4 import BeautifulSoup

with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

details = soup.find('div', class_='racing-full-form-details')
if details:
    html = details.prettify()
    print("Full Form Details HTML Length:", len(html))
    
    # Save it to a file so we can read it easily
    with open('/Users/imac/Desktop/Drive/Antigravity/.agents/skills/au_race_extractor/scripts/absolute_power_form.html', 'w') as out:
        out.write(html)
        
    print("Saved to absolute_power_form.html")
