with open(r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\test_script.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i in range(620, 635):
    try:
        print(f'{i+1}: ' + lines[i].strip(), flush=True)
    except Exception:
        print(f'{i+1}: <emoji data>')
