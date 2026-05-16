import os
import sys
import time
import random
import datetime
import subprocess
from curl_cffi import requests

# ==============================================================================
# AU Wong Choi - Season Batch Crawler
# Automatically crawls and processes all Randwick and Flemington races
# ==============================================================================

# 設定爬取範圍：2025/2026 馬季 (2025年8月1日至今日)
START_DATE = datetime.date(2025, 8, 1)
END_DATE = datetime.date.today()
TRACKS = ["flemington", "randwick"]

# 工具路徑
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORCHESTRATOR_PATH = os.path.join(".agents", "skills", "au_racing", "au_wong_choi", "scripts", "au_orchestrator.py")
RESULTS_SCRIPT_PATH = os.path.join(".agents", "skills", "au_racing", "claw_racenet_results.py")
ARCHIVE_DIR = os.path.join("Archive_Race_Analysis", "AU_Racing")

def check_date_for_tracks(date_obj):
    """檢查 Racenet 該日是否有指定的馬場賽事"""
    date_compact = date_obj.strftime("%Y%m%d")
    found_tracks = []
    
    for track in TRACKS:
        url = f"https://www.racenet.com.au/results/horse-racing/{track}-{date_compact}/all-races"
        print(f"Checking {track.title()} on {date_obj.strftime('%Y-%m-%d')}...", end="\r")
        try:
            # requests default handles 302 redirects
            r = requests.get(url, impersonate='chrome120', timeout=15)
            # 若果賽事不存在，Racenet 會將 URL redirect 返去 /results/horse-racing/ (無 track name)
            if r.status_code == 200 and track in r.url:
                found_tracks.append(track)
            
            # 短暫延遲避免過度請求
            time.sleep(1)
        except Exception as e:
            print(f"\n[Warning] Error checking {track} on {date_compact}: {e}")
            
    return found_tracks

def run_pipeline(track, date_obj):
    """執行完整 Wong Choi 分析及賽果補全"""
    date_str_dashed = date_obj.strftime("%Y-%m-%d")
    date_str_compact = date_obj.strftime("%Y%m%d")
    
    # 0. Check if already processed
    import glob
    existing_folders = [f for f in os.listdir(ARCHIVE_DIR) if f.startswith(date_str_dashed) and track.lower() in f.lower()]
    if existing_folders:
        folder_path = os.path.join(ARCHIVE_DIR, existing_folders[0])
        has_analysis = len(glob.glob(os.path.join(folder_path, "*Auto_Analysis.md"))) > 0
        has_results = len(glob.glob(os.path.join(folder_path, "*Result*.md"))) > 0 or len(glob.glob(os.path.join(folder_path, "*Result*.txt"))) > 0
        if has_analysis and has_results:
            print(f"[{date_str_dashed}] {track.title()} 已經有完整 Auto Analysis 同 Results，自動跳過！")
            return
    
    # 1. 執行 Orchestrator
    form_guide_url = f"https://www.racenet.com.au/form-guide/horse-racing/{track}-{date_str_compact}/all-races"
    print(f"\n[{date_str_dashed}] 啟動 {track.title()} 完整分析 Pipeline...")
    print(f"目標 URL: {form_guide_url}")
    
    cmd_orch = ["python", ORCHESTRATOR_PATH, form_guide_url, "--autopilot"]
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    
    try:
        subprocess.run(cmd_orch, env=env, check=False)
    except Exception as e:
        print(f"Orchestrator failed for {track} on {date_str_dashed}: {e}")
        
    # 2. 找出產出的資料夾並移至 ARCHIVE_DIR
    import glob
    import shutil
    
    project_root = os.path.dirname(BASE_DIR)
    # The generated folder looks like "2025-11-04 Randwick Race 1-10"
    pattern = os.path.join(project_root, f"{date_str_dashed}*{track.title()}*")
    candidates = [p for p in glob.glob(pattern) if os.path.isdir(p)]
    
    target_folder = None
    if candidates:
        src = candidates[0]
        dst = os.path.join(ARCHIVE_DIR, os.path.basename(src))
        if os.path.abspath(src) != os.path.abspath(dst):
            try:
                if os.path.exists(dst):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    shutil.rmtree(src)
                else:
                    shutil.move(src, dst)
            except Exception as e:
                print(f"Error moving folder {src} to {dst}: {e}")
        target_folder = dst
                
    if not target_folder:
        print(f"⚠️ 找不到 Orchestrator 產出的分析資料夾，跳過 {track} on {date_str_dashed}")
        return

    
    # 3. 執行賽果爬蟲
    results_url = f"https://www.racenet.com.au/results/horse-racing/{track}-{date_str_compact}/all-races"
    print(f"[{date_str_dashed}] 下載及補全賽果 ({track.title()})...")
    
    cmd_res = ["python", RESULTS_SCRIPT_PATH, "--url", results_url, "--output_dir", target_folder]
    
    try:
        subprocess.run(cmd_res, env=env, check=False)
    except Exception as e:
        print(f"Results crawler failed for {track} on {date_str_dashed}: {e}")
        
    print(f"[{date_str_dashed}] {track.title()} 處理完畢！\n" + "-"*50)

def main():
    print("="*50)
    print("AU Wong Choi - 全季批量爬蟲及分析腳本 (Randwick & Flemington)")
    print(f"掃描範圍: {START_DATE} 至 {END_DATE}")
    print("="*50)
    
    current_date = START_DATE
    total_processed = 0
    
    while current_date <= END_DATE:
        tracks_found = check_date_for_tracks(current_date)
        
        if tracks_found:
            print(f"\n>> 發現賽事: {current_date.strftime('%Y-%m-%d')} ({', '.join(tracks_found).title()})")
            for track in tracks_found:
                run_pipeline(track, current_date)
                total_processed += 1
                
                # 休眠避免封鎖
                sleep_time = random.uniform(15, 30)
                print(f"等待 {sleep_time:.1f} 秒避免被封鎖...")
                time.sleep(sleep_time)
        else:
            # 日常檢查隨機休眠 (快)
            time.sleep(random.uniform(0.5, 1.5))
            
        current_date += datetime.timedelta(days=1)
        
    print("="*50)
    print(f"全部完成！共處理了 {total_processed} 個賽馬日。")
    print("="*50)

if __name__ == '__main__':
    main()
