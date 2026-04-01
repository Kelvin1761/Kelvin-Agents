import re

# 1. Update static_template.html
html_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

fetch_pattern = re.compile(r'try\s*\{\s*const response = await fetch[^{]+?\{\s*method:\s*\'POST\'[^\}]+\}\);\s*if[^}]+\}\s*catch[^\}]+?\}', re.DOTALL)

new_blob = '''                // Export as static JSON file
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
                const downloadAnchorNode = document.createElement('a');
                downloadAnchorNode.setAttribute("href", dataStr);
                const datePrefix = new Date().toISOString().slice(0, 10);
                downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
                document.body.appendChild(downloadAnchorNode); // required for firefox
                downloadAnchorNode.click();
                downloadAnchorNode.remove();
                alert(`✅ 成功匯出 ${betsToExport.length} 筆投注記錄`);'''

# Use lambda to avoid parsing escape sequences
html_new = fetch_pattern.sub(lambda m: new_blob, html)
with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_new)
print('static_template.html modified:', html != html_new)

# 2. Update parser_hkjc.py
py_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\backend\services\parser_hkjc.py'
with open(py_path, 'r', encoding='utf-8') as f:
    py = f.read()

old_part3 = '''    # Extract Part 3 (verdict)
    part3 = _extract_section(text,
        ['[第三部分]', '## [第三部分]', '#### [第三部分]'],
        ['[第四部分]', '## [第四部分]', '#### [第四部分]']
    )
    
    # Extract Part 4 (blind spots)
    part4 = _extract_section(text,
        ['[第四部分]', '## [第四部分]', '#### [第四部分]'],
        ['```csv', '🔒 COMPLIANCE']
    )'''

new_part3 = '''    # Extract Part 3 (verdict) - Handle dynamic batch numbers (can be Part 3, 5, 7, etc.)
    part3 = _extract_section(text,
        ['最終結論 (The Verdict)', '最終結論', '賽事總結與預期崩潰點', '[第三部分]', '## [第三部分]', '#### [第三部分]'],
        ['分析盲區', '[第四部分]', '## [第四部分]', '#### [第四部分]', '```csv', '🔒 COMPLIANCE', '🐴⚡ 冷門馬總計']
    )
    
    # Extract Part 4 (blind spots)
    part4 = _extract_section(text,
        ['分析盲區', '[第四部分]', '## [第四部分]', '#### [第四部分]'],
        ['```csv', '🔒 COMPLIANCE', '📂 分析檔案更新完成', '---']
    )'''

py_new = py.replace(old_part3, new_part3)
with open(py_path, 'w', encoding='utf-8') as f:
    f.write(py_new)
print('parser_hkjc.py modified:', py != py_new)
