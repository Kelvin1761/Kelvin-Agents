import re
import json

with open('scratch_pdf_0524.txt', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

start_idx = -1
for i, line in enumerate(lines):
    if re.search(r'^\s*(?:S?\d+)\s+大怪奇', line):
        start_idx = i
        print(f"FOUND AT {i}: {line}")
        break

extracted = []
for line in lines[start_idx+1:]:
    # break if we see another horse
    if re.match(r'^\s*(?:S?\d+)\s+([^\x00-\x7F]+)', line):
        print(f"BREAKING ON: {line}")
        break
        
    m = re.match(r'^\s*([0-9a-zA-Z]+)/(\d+)\s+(.+)$', line)
    if m:
        extracted.append(line)
        
print(extracted)
