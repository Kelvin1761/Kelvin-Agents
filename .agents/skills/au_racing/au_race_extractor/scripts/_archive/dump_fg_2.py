from bs4 import BeautifulSoup

with open('./.agents/skills/au_race_extractor/scripts/racenet_print_curl.html', 'r') as f:
    text = f.read()

soup = BeautifulSoup(text, 'html.parser')

details = soup.find('div', class_='racing-full-form-details')
if details:
    html = details.prettify()
    print(html[2000:5000])
