import os

def refactor_nba_agent(target_path, resources_dir):
    with open(target_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_skill_md = []
    file_map = {
        '00_wong_choi_protocols.md': []
    }
    
    capture_mode = None

    for line in lines:
        if '# 🧠 ENGINE ADAPTATION' in line:
            capture_mode = '00_wong_choi_protocols.md'
            new_skill_md.append('> **[Resource Reference]** 此代理所有專屬防護協議與引擎規則已移至 `resources/00_wong_choi_protocols.md`\n')
            
        elif '## 🛑 Pre-Flight Environment Scan' in line:
            capture_mode = None
            
        if capture_mode:
            file_map[capture_mode].append(line)
        else:
            new_skill_md.append(line)

    print(f'Original lines: {len(lines)}')
    print(f'New lines in SKILL.md: {len(new_skill_md)}')

    os.makedirs(resources_dir, exist_ok=True)
    
    for filename, text_lines in file_map.items():
        if len(text_lines) > 0:
            with open(os.path.join(resources_dir, filename), 'w', encoding='utf-8') as f:
                f.writelines(text_lines)
            print(f'Created {filename} with {len(text_lines)} lines')
    
    if len(new_skill_md) < len(lines):
        import base64
        import subprocess
        import sys
        
        content_str = ''.join(new_skill_md)
        b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
        
        safe_writer = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(resources_dir))), 'scripts', 'safe_file_writer.py')
        
        subprocess.run([sys.executable, safe_writer, "--target", target_path, "--mode", "overwrite", "--content", b64], capture_output=True, text=True)
        print("Updated SKILL.md using P33-WLTM safe file writer.")


nba_target = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\nba\nba_wong_choi\SKILL.md'
nba_res = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\nba\nba_wong_choi\resources'
print("\nRefactoring NBA Wong Choi Protocols...")
refactor_nba_agent(nba_target, nba_res)
