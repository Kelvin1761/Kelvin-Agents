import os
import re

roots = [
    r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\nba',
    r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\au_racing'
]
count = 0

for root in roots:
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith('.md'):
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        c = f.read()
                    oc = c
                    
                    c = re.sub(r'> \*\*🚫🚫🚫 TOTAL BAN — `write_to_file`.*?# 🛑 Pipeline Testing', 
                               r'# 🚨 終極防死機 / Safe-Writer Protocol (P33-WLTM)\n\n> 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 write_to_file。\n\n# 🛑 Pipeline Testing', 
                               c, flags=re.DOTALL)
                               
                    c = re.sub(r'5\. \*\*File Writing Protocol\*\*.*?管道。', 
                               r'5. **File Writing Protocol**：遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 `write_to_file`。', 
                               c, flags=re.DOTALL)
                               
                    c = re.sub(r'- ⚠️ \*\*P33-WLTM 封殺令\*\*.*?死鎖。?', 
                               r'- ⚠️ **P33-WLTM**: 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 `write_to_file`。', 
                               c, flags=re.DOTALL)

                    c = re.sub(r'> ⚠️ \*\*P33-WLTM 封殺令\*\*.*?Pipeline）。', 
                               r'> ⚠️ **P33-WLTM**: 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 `write_to_file`。', 
                               c, flags=re.DOTALL)
                               
                    c = re.sub(r'- ⚠️ `write_to_file` / `replace_file_content`：\*\*P33-WLTM 完全禁止\*\*( — 會導致 IDE 死鎖)?',
                               r'- ⚠️ `write_to_file`：**P33-WLTM 完全禁止**', c)
                               
                    if c != oc:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(c)
                        count += 1
                        print('Fixed', file_path.encode('utf-8', 'replace').decode('cp1252', 'replace'))
                except Exception as e:
                    pass
print('Total additional fixed:', count)
