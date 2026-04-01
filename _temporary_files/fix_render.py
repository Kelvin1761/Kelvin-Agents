p = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(p, 'r', encoding='utf-8') as f:
    html = f.read()

bad_str = '''  // Betting panel
  // Export as static JSON file
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
                const downloadAnchorNode = document.createElement('a');
                downloadAnchorNode.setAttribute("href", dataStr);
                const datePrefix = new Date().toISOString().slice(0, 10);
                downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
                document.body.appendChild(downloadAnchorNode); // required for firefox
                downloadAnchorNode.click();
                downloadAnchorNode.remove();
                alert(`\\u2705 成功匯出 ${betsToExport.length} 筆投注記錄`);'''

good_str = '''  // Betting panel
  try {
    const isDual = raceAnalysts.length > 1;
    html += renderBettingPanel(m, raceNum, isDual, consensus);
  } catch (e) {
    html += `<div class="card" style="margin-top:24px">
      <h3 style="color:red">⚠️ 投注區域匯入失敗</h3>
      <pre style="font-size:0.75rem">${e.message}'''

new_html = html.replace(bad_str, good_str)
with open(p, 'w', encoding='utf-8') as f:
    f.write(new_html)
print('Fixed renderRaceDetail:', html != new_html)
