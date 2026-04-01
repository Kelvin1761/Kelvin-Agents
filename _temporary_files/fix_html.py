html_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

start_idx = html.find('function exportBetsJSON')
try_idx = html.find('try {', start_idx)
catch_end = html.find('}', html.find('catch', try_idx)) + 1

new_code = '''// Export as static JSON file
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
                const downloadAnchorNode = document.createElement('a');
                downloadAnchorNode.setAttribute("href", dataStr);
                const datePrefix = new Date().toISOString().slice(0, 10);
                downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
                document.body.appendChild(downloadAnchorNode); // required for firefox
                downloadAnchorNode.click();
                downloadAnchorNode.remove();
                alert(`\\u2705 成功匯出 ${betsToExport.length} 筆投注記錄`);'''

html_new = html[:try_idx] + new_code + html[catch_end:]
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_new)
print('static_template.html modified:', html != html_new)
