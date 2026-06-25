import os
import glob
import subprocess
import re
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
import sys as _sys; _sys.path.insert(0, str(PROJECT_ROOT))
from wongchoi_paths import AU_RACING

def main():
    base = str(AU_RACING)
    claw_script = r'.agents\skills\au_racing\claw_racenet_results.py'
    
    # 1. 找出所有有 Analysis 嘅 folders
    target_folders = []
    for folder in os.listdir(base):
        path = os.path.join(base, folder)
        if not os.path.isdir(path):
            continue
            
        analyses = glob.glob(os.path.join(path, '*Analysis*.md'))
        results = glob.glob(os.path.join(path, '*Results*.md'))
        
        # 必須要有 analysis，而且冇 result
        if len(analyses) > 0 and len(results) == 0:
            target_folders.append((folder, path))
            
    print(f"找到 {len(target_folders)} 個需要補全賽果嘅已分析賽馬日。")
    
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    
    for folder, path in target_folders:
        # 嘗試從 folder name 提取 date 同 track
        # e.g., "2026-03-28 Rosehill Gardens Race 1-10"
        match = re.search(r'^(\d{4}-\d{2}-\d{2})\s+([A-Za-z\s]+?)(?:\s+Race|\s*$)', folder)
        if not match:
            print(f"⚠️ 無法從資料夾名稱解析日期與馬場: {folder}")
            continue
            
        date_str = match.group(1) # 2026-03-28
        track_str = match.group(2).strip().lower().replace(' ', '-') # rosehill-gardens
        
        date_compact = date_str.replace('-', '') # 20260328
        
        url = f"https://www.racenet.com.au/results/horse-racing/{track_str}-{date_compact}/all-races"
        print(f"\n[{date_str}] 正在補全 {track_str} 嘅賽果...")
        print(f"目標 URL: {url}")
        
        cmd = ["python", claw_script, "--url", url, "--output_dir", path]
        
        try:
            subprocess.run(cmd, env=env, check=False)
            print(f"✅ {folder} 補全完成！休眠 5 秒...")
            time.sleep(5)
        except Exception as e:
            print(f"❌ 補全失敗 {folder}: {e}")

if __name__ == "__main__":
    main()
