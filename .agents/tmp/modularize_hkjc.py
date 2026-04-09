import os

def refactor_agent(target_path, resources_dir):
    with open(target_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_skill_md = []
    file_map = {
        '00_intent_router.md': [],
        '00_engine_adaptations.md': [],
        '00_session_state_rules.md': [],
        '00_cost_reporting.md': []
    }
    
    capture_mode = None

    for line in lines:
        if '# 🔀 Intent Router' in line:
            capture_mode = '00_intent_router.md'
            new_skill_md.append('> **[Resource Reference]** 此部分已移至 `resources/00_intent_router.md`\n')
            
        elif '# 🧠 Engine Awareness' in line:
            capture_mode = '00_engine_adaptations.md'
            new_skill_md.append('> **[Resource Reference]** 系統適應性與防呆機制已移至 `resources/00_engine_adaptations.md`\n')
            
        elif '## 🛑 Pre-Flight Environment Scan' in line:
            capture_mode = None
            
        elif '# 💾 Session State' in line:
            capture_mode = '00_session_state_rules.md'
            new_skill_md.append('> **[Resource Reference]** Session State 結構與規則已移至 `resources/00_session_state_rules.md`\n')
            
        elif '## Step 5: ' in line:
            capture_mode = None
            new_skill_md.append(line)
            continue
            
        elif '## Step 7b: Session Cost Report' in line:
            capture_mode = '00_cost_reporting.md'
            new_skill_md.append('## Step 7b: Session Cost Report\n> **[Resource Reference]** 報告格式請參考 `resources/00_cost_reporting.md`\n')
            continue
            
        elif '## Step 8: ' in line:
            capture_mode = None
            new_skill_md.append(line)
            continue
            
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


hkjc_target = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc_racing\hkjc_wong_choi\SKILL.md'
hkjc_res = r'g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc_racing\hkjc_wong_choi\resources'
print("\nRefactoring HKJC Wong Choi...")
refactor_agent(hkjc_target, hkjc_res)
