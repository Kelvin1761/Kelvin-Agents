#!/usr/bin/env python3
"""
compile_nba_report.py
(Phase 5: NBA Compilation & Archiving)

This script scans the generated Full_Analysis.md files for each game, parses out
the Combination blocks (Bankers & SGM), and synthesizes them into Master_SGM.md
and Banker_Combinations.md.
"""

import os
import argparse
import glob

def compile_reports(target_dir):
    print(f"📄 [編譯] 正在從 {target_dir} 抽取單場報告的過關組合...")
    
    analysis_files = glob.glob(os.path.join(target_dir, "*_Full_Analysis.md"))
    
    if not analysis_files:
        print("⚠️ 找不到任何 _Full_Analysis.md 檔案 (可能 Agent 尚未完成單場分析)。")
        return
        
    banker_lines = ["# 🛡️ 全日穩膽組合 (Banker Combinations)\n", "> 此報告由 Python 自動從各單場分析中抽取並匯總。\n\n"]
    sgm_lines = ["# 🚀 全日價值過關 (Master SGM)\n", "> 此報告由 Python 自動從各單場分析中抽取並匯總。\n\n"]
    
    for fpath in sorted(analysis_files):
        game_name = os.path.basename(fpath).replace("Game_", "").replace("_Full_Analysis.md", "")
        with open(fpath, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        current_block = None
        game_banker = []
        game_sgm = []
        
        for line in lines:
            # 尋找 Combo 區塊的標題
            if line.startswith("### ") and ("穩膽" in line or "Safe" in line or "combo_1" in line.lower()):
                current_block = "banker"
                game_banker.append(f"## 🏀 {game_name}\n\n")
                game_banker.append(line)
            elif line.startswith("### ") and ("組合" in line or "SGM" in line or "Value" in line or "combo" in line.lower() or "進取" in line or "炸" in line):
                current_block = "sgm"
                if not game_sgm:
                    game_sgm.append(f"## 🏀 {game_name}\n\n")
                game_sgm.append(line)
            # 遇到下一個大段落 (例如 ##) 則停止擷取
            elif current_block and line.startswith("## ") and not line.startswith("### "):
                current_block = None
            elif current_block == "banker":
                game_banker.append(line)
            elif current_block == "sgm":
                game_sgm.append(line)
                    
        if game_banker:
            banker_lines.extend(game_banker)
            banker_lines.append("\n---\n\n")
        if game_sgm:
            sgm_lines.extend(game_sgm)
            sgm_lines.append("\n---\n\n")

    out_banker = os.path.join(target_dir, "Banker_Combinations.txt")
    with open(out_banker, "w", encoding="utf-8") as f:
        f.writelines(banker_lines)
        
    out_sgm = os.path.join(target_dir, "Master_SGM.txt")
    with open(out_sgm, "w", encoding="utf-8") as f:
        f.writelines(sgm_lines)
        
    print(f"✅ 成功匯總！檔案已存至:")
    print(f"  - {out_banker}")
    print(f"  - {out_sgm}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target_dir', type=str, default=".", help="Directory containing Analysis.md files")
    args = parser.parse_args()
    
    target = os.path.abspath(args.target_dir)
    compile_reports(target)
