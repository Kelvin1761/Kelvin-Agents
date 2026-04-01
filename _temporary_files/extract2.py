p = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(p, 'r', encoding='utf-8') as f:
    html = f.read()

idx1 = html.find('// Betting panel')
idx2 = html.find('function renderBettingPanel(', max(0, idx1))

out = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\snippet2.txt'
with open(out, 'w', encoding='utf-8') as f:
    f.write(html[idx1:idx2+200])
