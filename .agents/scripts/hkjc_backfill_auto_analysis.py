import os
import sys
import glob
import subprocess

ARCHIVE_DIR = r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\Archive_Race_Analysis\HK_Racing"
ORCHESTRATOR_PATH = r"g:\我的雲端硬碟\Antigravity Shared\Antigravity\.agents\skills\hkjc_racing\hkjc_wong_choi\scripts\hkjc_orchestrator.py"

def run_backfill():
    print("="*50)
    print("HKJC Auto Analysis Backfiller (本地數據升級)")
    print("="*50)
    
    if not os.path.exists(ARCHIVE_DIR):
        print(f"找不到目錄: {ARCHIVE_DIR}")
        return

    # List all subdirectories
    for folder_name in sorted(os.listdir(ARCHIVE_DIR)):
        folder_path = os.path.join(ARCHIVE_DIR, folder_name)
        if not os.path.isdir(folder_path):
            continue
            
        if folder_name == "HKJC_Race_Results_Database":
            continue

        # Check if we have the raw json data (e.g. Race_1.json)
        raw_jsons = glob.glob(os.path.join(folder_path, "Race_*.json"))
        # Exclude Logic.json
        raw_jsons = [f for f in raw_jsons if not f.endswith("Logic.json")]
        
        if not raw_jsons:
            print(f"\n跳過 {folder_name}: 沒有找到原始的 Race_*.json 數據檔。")
            continue

        # Check if Auto_Analysis.md already exists
        has_analysis = len(glob.glob(os.path.join(folder_path, "*Auto_Analysis.md"))) > 0
        if has_analysis:
            print(f"Skipping {folder_name} because Auto_Analysis.md already exists.")
            continue

        print(f"\n>> Processing: {folder_name}")
        
        # Run orchestrator on the LOCAL FOLDER
        cmd = [sys.executable, ORCHESTRATOR_PATH, folder_path, "--autopilot"]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        env["PYTHONUNBUFFERED"] = "1"
        
        try:
            subprocess.run(cmd, env=env, check=True)
            print(f"成功補全: {folder_name}")
        except subprocess.CalledProcessError as e:
            print(f"處理失敗 {folder_name}: {e}")

if __name__ == "__main__":
    run_backfill()
