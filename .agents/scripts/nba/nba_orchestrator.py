#!/usr/bin/env python3
"""
nba_orchestrator.py
(The Brain of NBA Wong Choi Pipeline)

This master script replaces the mocked orchestrator. It executes a fully deterministic
assembly line:
1. Detects raw Sportsbet JSON files in the workspace (or specified directory).
2. Triggers `generate_nba_auto.py` to compile pure Data Brief JSONs and Skeleton MDs.
3. Performs a Gate Check to ensure completeness of the mathematical dataset.
4. Outputs the Trigger Command for the Agent Analyst to conduct final reasoning.
"""

import os
import sys
import argparse
import subprocess
import datetime
import glob

# Base directory relative to this script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

def run_db_extractor(target_dir):
    print(f"🚀 [Orchestrator] 啟動 NBA 數據生成器 (generate_nba_auto.py)...")
    script_path = os.path.join(BASE_DIR, "generate_nba_auto.py")
    
    if not os.path.exists(script_path):
        print(f"❌ [Error] 找不到數據生成腳本: {script_path}")
        sys.exit(1)
        
    try:
        # Run generate_nba_auto.py in the target directory
        subprocess.run(["python3", script_path, "--dir", target_dir], check=True)
        print("✅ [Orchestrator] V7 Data Brief 生成流程完成！")
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] generate_nba_auto.py 執行失敗: {e}")
        sys.exit(1)

def discover_sportsbet_files(target_dir):
    """Find all raw Sportsbet JSON files."""
    files = glob.glob(os.path.join(target_dir, "Sportsbet_Odds_*.json"))
    valid_files = [f for f in files if "TEST" not in f and "MIN" not in f and "GEMINI" not in f]
    return valid_files

def check_data_completeness(target_dir, sportsbet_files):
    missing_data = []
    
    for fpath in sportsbet_files:
        basename = os.path.basename(fpath)
        parts = basename.replace("Sportsbet_Odds_", "").replace(".json", "").split("_")
        
        if len(parts) >= 2:
            away_abbr, home_abbr = parts[0], parts[1]
            
            # Check for Data Brief JSON
            brief_file = os.path.join(target_dir, f"Data_Brief_{away_abbr}_{home_abbr}.json")
            if not os.path.exists(brief_file):
                missing_data.append(f"Data_Brief_{away_abbr}_{home_abbr}.json")
                
            # Check for Full Analysis
            analysis_file = os.path.join(target_dir, f"Game_{away_abbr}_{home_abbr}_Full_Analysis.md")
            if not os.path.exists(analysis_file):
                missing_data.append(f"Game_{away_abbr}_{home_abbr}_Full_Analysis.md")
                
    return missing_data

def main():
    parser = argparse.ArgumentParser(description="NBA Orchestrator: Main Pipeline Entry")
    parser.add_argument("--dir", default=".", help="Target directory containing Sportsbet JSONs (defaults to workspace root)")
    args = parser.parse_args()

    # Use the provided directory, default is current working directory (Antigravity Root)
    target_dir = os.path.abspath(args.dir)
    print(f"🌐 [Orchestrator] 掃描賽事資料目錄: {target_dir}")
    
    # Check for raw files
    sportsbet_files = discover_sportsbet_files(target_dir)
    if not sportsbet_files:
        print(f"❌ [Fatal] 找不到任何 Sportsbet_Odds_*.json 檔案於 {target_dir}")
        print("💡 請先確定 Crawler 已經將今日嘅盤口數據 JSON 放喺這個資料夾內。")
        sys.exit(1)
        
    print(f"✅ 發現 {len(sportsbet_files)} 場賽事盤口數據。")
    
    # Run the generator
    run_db_extractor(target_dir)
    
    # Verify outputs
    missing_data = check_data_completeness(target_dir, sportsbet_files)
    
    if missing_data:
        print(f"🚨 [Fatal] 發現缺漏最終數據: {missing_data}")
        print("💡 可能部分賽事 API 數據抓取失敗，請檢查 generate_nba_auto.py 嘅輸出 log。")
        sys.exit(1)
        
    print("\n" + "="*50)
    print("✅ [micro-analysis PASSED] 15 場微觀賽事之數據計算及完整分析已成功由 Python 生成！")
    print("="*50 + "\n")
    
    print(f"🚀 [Orchestrator] 啟動自動編譯 (compile_nba_report.py)...")
    compile_script = os.path.join(BASE_DIR, ".agents", "scripts", "nba", "compile_nba_report.py")
    try:
        subprocess.run(["python3", compile_script, "--target_dir", target_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] compile_nba_report.py 執行失敗: {e}")
        sys.exit(1)
    # State file setup
    state_file = os.path.join(target_dir, "_nba_session_state.md")
    with open(state_file, "a", encoding="utf-8") as f:
        f.write(f"\n🔒 NBA_EXTRACTION_GATE: FULLY_EXTRACTED ({datetime.datetime.now()})\n")
        
    print(f"🎯 [Orchestrator] V8 管線就緒！Banker 與 SGM 報告已存於: {os.path.relpath(target_dir)}")
    print(f"👉 請在 Chat 呼叫 `@nba wong choi` 並輸入以下指令，以完成最後的「宏觀解讀」：")
    print("\n------------------------------------------------------------")
    print("請根據剛才生成的 `2026-04-11 NBA Analysis/Banker_Combinations.txt` 與所有 Data Brief 提供今日賽事的【宏觀解讀】(Macro Slate Intelligence)。")
    print("無需再做微觀球員分析。請告訴我：")
    print("1. 全日傷病與擺爛版圖 (邊幾隊極大隱患？有咩避險建議？)")
    print("2. Python 嘅投注邏輯拆解 (今日點解 Python 偏向買邊啲球員/球隊？有咩戰術/防守漏洞被 Python 捕捉到？)")
    print("------------------------------------------------------------\n")

if __name__ == "__main__":
    main()
