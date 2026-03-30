import sys
from bs4 import BeautifulSoup

with open('racecard_debug.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("=== Header Info ===")
for div in soup.find_all('div', class_='race-meeting-info'):
    print(div.text.strip())
for div in soup.find_all('div', class_='bg-blue'):
    print(div.text.strip())

print("\n=== Horses ===")
table = soup.find('table', class_='draggable')
if table:
    headers = [th.text.strip() for th in table.find_all('th')]
    print("Headers:", headers)
    for tr in table.find('tbody').find_all('tr'):
        tds = [td.text.strip().replace('\n', ' ') for td in tr.find_all('td')]
        print("Row:", tds)
else:
    print("Could not find table")
