import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from bs4 import BeautifulSoup
import re

html = """
<div class="Sectional_Times">
 <div class="Sectional_Times_item">
  24.56
 </div>
 <div class="Sectional_Times_item2">
  22.64
  <div class="Sectional_Times_sub_item">
   11.18 11.46
  </div>
 </div>
 <div>
  中等步速;(2W1W1W) 居後列，走內欄。直路彎略為追前。末段追近領先馬匹，但一直落後。
 </div>
</div>
"""
soup = BeautifulSoup(html, 'html.parser')

sect_div = soup.find('div', class_='Sectional_Times')
# Search specifically for items that have 'Sectional_Times_item' somewhere in their class name
items = sect_div.find_all('div', class_=re.compile('Sectional_Times_item'))

print("--- USING text=True ---")
new_sections = []
for item in items:
    text = ''.join(item.find_all(text=True, recursive=False)).strip()
    if re.match(r'^[\d.]+$', text):
        new_sections.append(text)
print(new_sections)

print("--- USING string=True ---")
new_sections = []
for item in items:
    text = ''.join(item.find_all(string=True, recursive=False)).strip()
    if re.match(r'^[\d.]+$', text):
        new_sections.append(text)
print(new_sections)

