import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

path = r'G:\我的雲端硬碟\Antigravity Shared\Antigravity\2026-04-01_ShaTin (Kelvin)\04-01 Race 3 Analysis.md'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

print(f"File size: {len(text)} chars")

for pattern in ['最終結論', 'The Verdict', 'Top 4', 'Top 3', '```csv', '第一選', '🥇', '推薦排名', '總排名', 'CSV', '排名']:
    idx = text.find(pattern)
    if idx >= 0:
        ctx = text[max(0,idx-30):idx+150].replace('\n', '\\n')
        print(f'FOUND "{pattern}" at {idx}: ...{ctx}...')
    else:
        print(f'NOT found: "{pattern}"')
