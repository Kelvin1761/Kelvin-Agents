import re

html_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

start_idx = html.find('function exportBetsJSON() {')
end_idx = html.find('function selectMeeting', start_idx)

block = html[start_idx:end_idx]

pattern = re.compile(r'try\s*\{\s*const\s+apiUrl[^\}]+\}\s*catch\s*\(err\)\s*\{[^\}]+?\}', re.DOTALL)
pattern_old = re.compile(r'try\s*\{\s*const\s+response\s*=\s*await\s+fetch\([^{]+?\{\s*method:\s*\'POST\'[^\}]+\}\);\s*if\s*\(!response\.ok\)[^}]+?\}\s*catch\s*\(err\)\s*\{\s*alert\(\'[^\']+\'\s*\+\s*err\.message\);\s*\}', re.DOTALL)

new_blob = """// Export as static JSON file
    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
    const downloadAnchorNode = document.createElement('a');
    downloadAnchorNode.setAttribute("href", dataStr);
    const datePrefix = new Date().toISOString().slice(0, 10);
    downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
    document.body.appendChild(downloadAnchorNode); // required for firefox
    downloadAnchorNode.click();
    downloadAnchorNode.remove();
    alert(`\\u2705 成功匯出 ${betsToExport.length} 筆投注記錄`);"""

# Fix escape the simple way:
new_blob = new_blob.replace('\\u', '\\\\u')

if pattern.search(block):
    block_new = pattern.sub(new_blob, block)
elif pattern_old.search(block):
    block_new = pattern_old.sub(new_blob, block)
else:
    block_new = block

if block != block_new:
    html_new = html[:start_idx] + block_new + html[end_idx:]
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html_new)
    print('fixed static_template.html successfully!')
else:
    print('Failed to fix: regex did not match in the block.')
