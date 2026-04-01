import re

html_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
with open(html_path, 'r', encoding='utf-8') as f:
    html = f.read()

# We need to replace the download logic we just inserted with a try/catch that does DB first, then download.
old_blob = """// Export as static JSON file
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
                const downloadAnchorNode = document.createElement('a');
                downloadAnchorNode.setAttribute("href", dataStr);
                const datePrefix = new Date().toISOString().slice(0, 10);
                downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
                document.body.appendChild(downloadAnchorNode); // required for firefox
                downloadAnchorNode.click();
                downloadAnchorNode.remove();
                alert(`✅ 成功匯出 ${betsToExport.length} 筆投注記錄`);"""

new_logic = """try {
                    // Try to save directly to Database if backend is running
                    const apiUrl = window.location.protocol === 'file:' ? 'http://localhost:8000/api/bets/batch' : '/api/bets/batch';
                    const response = await fetch(apiUrl, {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(betsToExport)
                    });
                    if (!response.ok) throw new Error('DB API rejected request');
                    
                    alert(`✅ 成功寫入 Database (${betsToExport.length} 筆投注)`);
                } catch (err) {
                    console.log("Backend not reachable or error:", err.message);
                    // Fallback to static JSON file download
                    const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(betsToExport, null, 2));
                    const downloadAnchorNode = document.createElement('a');
                    downloadAnchorNode.setAttribute("href", dataStr);
                    const datePrefix = new Date().toISOString().slice(0, 10);
                    downloadAnchorNode.setAttribute("download", `betting_records_${datePrefix}.json`);
                    document.body.appendChild(downloadAnchorNode);
                    downloadAnchorNode.click();
                    downloadAnchorNode.remove();
                    
                    alert(`⚠️ Backend 伺服器未開啟 (無法寫入 DB)。\n\n已自動轉為下載檔案: betting_records_${datePrefix}.json`);
                }"""

# Fix escaped checks
old_blob_real = old_blob.replace('`✅ 成功匯出 ${betsToExport.length} 筆投注記錄`', '`\\u2705 成功匯出 ${betsToExport.length} 筆投注記錄，請查看下載資料夾。`')

html_new = html.replace(old_blob_real, new_logic)

with open(html_path, 'w', encoding='utf-8') as f:
    f.write(html_new)
print('static_template.html modified:', html != html_new)
