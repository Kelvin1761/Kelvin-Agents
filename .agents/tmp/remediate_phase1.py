import os
import re

roots = [
    r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\au_racing',
    r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc',
    r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\nba'
]

hardcoded_paths = [
    (r'/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity', r'.'),
    (r'/Users/imac/Desktop/Drive/Antigravity', r'.'),
    (r'/tmp/', r'.agents/tmp/'),
    (r'P19v6', r'P33-WLTM'),
    (r'write_to_file / replace_file_content / multi_replace_file_content 已完全封殺', r'write_to_file 封殺 (可使用 replace_file_content/multi_replace_file_content 或 safe_file_writer.py)'),
    (r'`write_to_file` / `replace_file_content` / `multi_replace_file_content` 等工具已完全封殺', r'`write_to_file` 工具已完全封殺'),
]

for root in roots:
    for dirpath, _, filenames in os.walk(root):
        for filename in filenames:
            if filename.endswith('.md') or filename.endswith('.py'):
                file_path = os.path.join(dirpath, filename)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    original_content = content
                    for pattern, replacement in hardcoded_paths:
                        content = re.sub(pattern, replacement, content)
                        
                    # Specific fixes for the massive P19v6 block
                    content = re.sub(r'# 🚨 終極防死機 / Safe-Writer Protocol \(P33-WLTM — 2026-04-04 更新\).*?# 🛑 Pipeline Testing', 
                                     r'# 🚨 終極防死機 / Safe-Writer Protocol (P33-WLTM)\n\n> 遵循 GEMINI.md 之中規定的 `safe_file_writer.py` 進行操作。嚴禁使用 write_to_file。\n\n# 🛑 Pipeline Testing', 
                                     content, flags=re.DOTALL)
                                     
                    if content != original_content:
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(content)
                        print(f'Fixed {file_path}')
                except Exception as e:
                    pass

print('Phase 1 Path & Sync Lock Text Replacement Completed.')
