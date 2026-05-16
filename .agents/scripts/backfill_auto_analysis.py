import os
import sys
import glob
import shutil
import datetime
import subprocess

ARCHIVE_DIR = os.path.join("Archive_Race_Analysis", "AU_Racing")
ORCHESTRATOR_PATH = os.path.join(".agents", "skills", "au_racing", "au_wong_choi", "scripts", "au_orchestrator.py")

def run():
    print("="*50)
    print("AU Auto Analysis Backfiller")
    print("="*50)
    
    if not os.path.exists(ARCHIVE_DIR):
        print(f"Directory {ARCHIVE_DIR} does not exist.")
        return
        
    for folder in os.listdir(ARCHIVE_DIR):
        folder_path = os.path.join(ARCHIVE_DIR, folder)
        if not os.path.isdir(folder_path):
            continue
            
        # Example folder: "2026-04-02 Gosford Race 1-7" or "2026-03-28 Flemington"
        parts = folder.split(' ')
        if len(parts) < 2:
            continue
            
        date_str = parts[0] # YYYY-MM-DD
        
        # Extract track name
        # It's everything after date and before "Race" (if "Race" is in the name)
        track_parts = []
        for p in parts[1:]:
            if p == "Race" or p.startswith("Race"):
                break
            track_parts.append(p)
            
        if not track_parts:
            continue
            
        track = "-".join(track_parts).lower()
        date_compact = date_str.replace('-', '')
        
        url = f"https://www.racenet.com.au/form-guide/horse-racing/{track}-{date_compact}/all-races"
        
        print(f"\n>> Processing: {folder}")
        print(f"URL: {url}")
        
        # Check if Auto Analysis already exists
        auto_files = glob.glob(os.path.join(folder_path, "*Auto_Analysis.md"))
        if auto_files:
            print(f"Skipping {folder} because Auto_Analysis.md already exists.")
            continue
            
        cmd = [sys.executable, ORCHESTRATOR_PATH, url, "--autopilot"]
        env = os.environ.copy()
        env["PYTHONUTF8"] = "1"
        
        try:
            subprocess.run(cmd, env=env, check=False)
        except Exception as e:
            print(f"Error running orchestrator for {folder}: {e}")
            continue
            
        # Find the generated folder in PROJECT_ROOT
        project_root = os.getcwd()
        pattern = os.path.join(project_root, f"{date_str}*{' '.join(track_parts)}*")
        candidates = [p for p in glob.glob(pattern) if os.path.isdir(p) and os.path.abspath(p) != os.path.abspath(folder_path)]
        
        if candidates:
            src = candidates[0]
            print(f"Merging generated folder {src} into {folder_path}...")
            try:
                shutil.copytree(src, folder_path, dirs_exist_ok=True)
                shutil.rmtree(src)
                print(f"Successfully backfilled Auto Analysis for {folder}!")
            except Exception as e:
                print(f"Error merging folder: {e}")
        else:
            print(f"⚠️ Could not find generated folder in project root for {folder}")

if __name__ == "__main__":
    run()
