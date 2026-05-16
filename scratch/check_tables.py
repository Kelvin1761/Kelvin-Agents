from bs4 import BeautifulSoup
import json
html = open('scratch/debug_2024.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
tables = soup.find_all('table')
summary = []
for i, t in enumerate(tables):
    summary.append({
        'index': i,
        'text': t.get_text(strip=True)[:100],
        'rows': len(t.find_all('tr'))
    })
with open('scratch/table_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
