import re

p = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\Open Dashboard.html'
with open(p, 'r', encoding='utf-8') as f:
    html = f.read()

new_code = "alert(`⚠️ Backend 伺服器未開啟 (無法寫入 DB)。\\n\\n已自動轉為下載檔案: betting_records_${datePrefix}.json`);\n                }"

idx = html.find(new_code)
if idx != -1:
    print('Found duplication point!')
    end_of_new_code = idx + len(new_code)
    
    # Extract the second half which is A_modified[13:]
    second_half = html[end_of_new_code:]
    
    # A_modified is <!DOCTYPE htm + second_half
    recon = '<!DOCTYPE htm' + second_half
    
    # Now we need to un-inject the CSS and JSON data to make it static_template.html again!
    # generate_static.py replaces /* __CSS_PLACEHOLDER__ */ with index.css
    css_start = recon.find('<style>') + 7
    css_end = recon.find('</style>')
    recon = recon[:css_start] + '\n        /* __CSS_PLACEHOLDER__ */\n    ' + recon[css_end:]
    
    # replace the huge JSON data
    data_start = recon.find('const DASHBOARD_DATA = ') + len('const DASHBOARD_DATA = ')
    data_end = recon.find(';\n', data_start)
    recon = recon[:data_start] + '"__DATA_PLACEHOLDER__"' + recon[data_end:]
    
    # Replace the generated time
    time_start = recon.find('<span class="generated-time">更新時間: ') + len('<span class="generated-time">更新時間: ')
    time_end = recon.find('</span>', time_start)
    recon = recon[:time_start] + '__GENERATED_TIME__' + recon[time_end:]
    
    # Save it back to static_template.html
    out_path = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\Horse Racing Dashboard\static_template.html'
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(recon)
    print('RECONSTRUCTED static_template.html SUCCESSFULLY!')
else:
    print('Not found')
