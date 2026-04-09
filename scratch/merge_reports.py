import os
import glob

base_dir = "/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity/nba_analysis_20260410"

games = [
    "Game_MIA_TOR_Full_Analysis.md",
    "Game_CHI_WSH_Full_Analysis.md",
    "Game_IND_BKN_Full_Analysis.md",
    "Game_BOS_NY_Full_Analysis.md",
    "Game_PHI_HOU_Full_Analysis.md",
    "Game_LAL_GS_Full_Analysis.md"
]

full_report_path = os.path.join(base_dir, "NBA_Analysis_Report.md")
banker_report_path = os.path.join(base_dir, "NBA_Banker_Report.md")

full_content = []
banker_content = []

for g in games:
    path = os.path.join(base_dir, g)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
        full_content.extend(lines)
        full_content.append('\n---\n---\n')
        
        # Banker Extraction roughly
        banker_lines = []
        in_banker = False
        for line in lines:
            if "### 🛡️ 組合 1" in line:
                in_banker = True
            elif in_banker and ("### 🔥" in line or "### 💎" in line or "---" in line and len(banker_lines) > 5):
                in_banker = False
            
            if in_banker:
                banker_lines.append(line)
        
        if banker_lines:
            banker_content.append(f"# {g.replace('_Full_Analysis.md', '')}\n")
            banker_content.extend(banker_lines)
            banker_content.append('\n---\n')

with open(full_report_path, 'w', encoding='utf-8') as f:
    f.writelines(full_content)

with open(banker_report_path, 'w', encoding='utf-8') as f:
    f.writelines(banker_content)
    
print("Merge complete!")
