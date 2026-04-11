#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
import re
import json

import urllib.request

def parse_url_for_details(url):
    match = re.search(r'RaceDate=(\d{4})/(\d{2})/(\d{2}).*?&Racecourse=([A-Za-z]+)', url, re.IGNORECASE)
    
    if not match:
        print(f"🔍 [Auto-Discovery] URL lacks explicit RaceDate. Fetching HTML to resolve next meeting date...")
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8')
            # Look for racedate=2026/04/12&Racecourse=ST matches in HTML
            html_match = re.search(r'racedate=(\d{4})/(\d{2})/(\d{2})&amp;Racecourse=([A-Za-z]+)', html, re.IGNORECASE)
            if not html_match:
                html_match = re.search(r'racedate=(\d{4})/(\d{2})/(\d{2})&Racecourse=([A-Za-z]+)', html, re.IGNORECASE)
            
            if html_match:
                print(f"✅ [Auto-Discovery] Found next meeting: {html_match.group(1)}/{html_match.group(2)}/{html_match.group(3)} at {html_match.group(4)}")
                match = html_match
            else:
                raise ValueError("Invalid HKJC URL format and could not auto-discover from HTML. Cannot extract Venue and Date.")
        except Exception as e:
            raise ValueError(f"Failed to auto-discover date from URL: {e}")

    date_str = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    venue_code = match.group(4).upper()
    venue_map = {"ST": "ShaTin", "HV": "HappyValley"}
    venue = venue_map.get(venue_code, venue_code)
    
    resolved_url = f"https://racing.hkjc.com/zh-hk/local/information/racecard?racedate={match.group(1)}/{match.group(2)}/{match.group(3)}&Racecourse={venue_code}&RaceNo=1"
    
    return venue, date_str, resolved_url

def get_target_dir(venue, formatted_date, auto_create=False):
    base_dir = "."
    dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date}_{venue}")]
    if dirs:
        return os.path.abspath(os.path.join(base_dir, dirs[0]))
    
    if auto_create:
        new_dir = os.path.abspath(os.path.join(base_dir, f"{formatted_date}_{venue}"))
        os.makedirs(new_dir, exist_ok=True)
        return new_dir
    return None

def trigger_extractor(url, target_dir):
    print(f"🚀 [Orchestrator] 啟動 HKJC Race Extractor 提取全日數據...")
    script_path = ".agents/skills/hkjc_racing/hkjc_race_extractor/scripts/batch_extract.py"
    if not os.path.exists(script_path):
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        sys.exit(1)
    try:
        subprocess.run(["python3", script_path, "--base_url", url, "--races", "1-11", "--output_dir", target_dir], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] 數據提取腳本執行失敗: {e}")
        sys.exit(1)

def discover_total_races(target_dir):
    racecards = [f for f in os.listdir(target_dir) if "排位表.md" in f or "Racecard.md" in f or "排位表" in f]
    max_race = 0
    for card in racecards:
        m = re.search(r'Race (\d+)', card)
        if m:
            race_num = int(m.group(1))
            if race_num > max_race:
                max_race = race_num
    return max_race

def check_raw_data_completeness(target_dir, total_races):
    missing_data = []
    
    if not any("全日出賽馬匹資料 (PDF).md" in f for f in os.listdir(target_dir)):
        missing_data.append("全日出賽馬匹資料 (PDF).md")
        
    for race_num in range(1, total_races + 1):
        if not any(re.search(rf'Race {race_num}.*(賽績|Formguide)\.md', f) for f in os.listdir(target_dir)) and not any(f"Race {race_num}" in f and "賽績" in f for f in os.listdir(target_dir)):
            missing_data.append(f"Race {race_num} 賽績.md")
        if not any(re.search(rf'Race {race_num}.*(排位表|Racecard)\.md', f) for f in os.listdir(target_dir)) and not any(f"Race {race_num}" in f and "排位表" in f for f in os.listdir(target_dir)):
            missing_data.append(f"Race {race_num} 排位表.md")
    return missing_data

def get_rc_fg_paths(target_dir, race_num):
    rc, fg = None, None
    for f in os.listdir(target_dir):
        if f"Race {race_num}" in f and ("排位表" in f or "Racecard" in f or "排位表" in f): rc = os.path.join(target_dir, f)
        if f"Race {race_num}" in f and ("賽績" in f or "Formguide" in f or "賽績" in f): fg = os.path.join(target_dir, f)
    return rc, fg
    
def get_horse_numbers(facts_file):
    # Parse facts file to get list of horse numbers
    content = open(facts_file).read()
    horse_pattern = re.compile(r'^### 馬號 (\d+) —', re.MULTILINE)
    horses = [int(m.group(1)) for m in horse_pattern.finditer(content)]
    return horses

def get_batches(horses, size=3):
    return [horses[i:i + size] for i in range(0, len(horses), size)]

def update_session_tasks(target_dir, total_races, missing_raw, chk_weather, chk_facts_done, analysis_status_dict):
    tasks_path = os.path.join(target_dir, "_session_tasks.md")
    
    lines = ["# HKJC Session Tasks\n"]
    lines.append("## 基礎建設")
    
    chk_pdf = '[ ]' if any("PDF" in str(m) for m in missing_raw) else '[x]'
    lines.append(f"- {chk_pdf} 官方大報表 PDF 提取 (starter_all_chi.pdf)")
    
    raw_files_missing = any("賽績" in str(m) for m in missing_raw) or any("排位表" in str(m) for m in missing_raw)
    lines.append(f"- {'[ ]' if raw_files_missing else '[x]'} 原始賽事資料下載 (Race 1-{total_races})")
    lines.append(f"- {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    lines.append(f"- {'[x]' if chk_facts_done == total_races else '[ ]'} 事實錨點 Facts.md 全部生成 ({chk_facts_done}/{total_races})\n")
    
    lines.append("## 馬匹分析 (Batch Status)")
    for r in range(1, total_races + 1):
        status = analysis_status_dict.get(r, "待啟動")
        chk = "[x]" if "完成" in status else "[ ]"
        lines.append(f"- {chk} **Race {r}**: {status}")

    with open(tasks_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    return tasks_path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="HKJC Race URL or target directory if URL is skipped")
    args = parser.parse_args()

    print("="*60)
    print("🏇 HKJC Wong Choi Orchestrator (State Machine V8)")
    print("="*60)
    
    if args.url.startswith("http"):
        venue, formatted_date, resolved_url = parse_url_for_details(args.url)
        args.url = resolved_url # override with strictly dated url
        target_dir = get_target_dir(venue, formatted_date)
    else:
        target_dir = os.path.abspath(args.url)
        if not os.path.isdir(target_dir):
            print(f"❌ [Error] 提供的路徑 {target_dir} 不是一個有效的目錄。")
            sys.exit(1)

    if not target_dir:
        print("📂 找不到目標數據庫，將執行 State 0 (提取資料)...")
        target_dir = get_target_dir(venue, formatted_date, auto_create=True)
        trigger_extractor(args.url, target_dir)
        if not os.path.isdir(target_dir):
            print("❌ [Fatal] 爬蟲執行後仍找不到目標資料夾！")
            sys.exit(1)
            
    total_races = discover_total_races(target_dir)
    print(f"✅ 目標目錄: {os.path.basename(target_dir)}")
    print(f"✅ 賽事總數: {total_races} 場\n")

    missing_raw = check_raw_data_completeness(target_dir, total_races)
    chk_raw = "[ ]" if missing_raw else "[x]"
    
    weather_file = os.path.join(target_dir, "_Meeting_Intelligence_Package.md")
    chk_weather = "[x]" if os.path.exists(weather_file) else "[ ]"
    
    facts_done = 0
    analysis_status_dict = {}
    analysis_passed = 0
    
    # Pre-scan states to build the task dashboard
    for r in range(1, total_races + 1):
        facts_file = os.path.join(target_dir, sorted([f for f in os.listdir(target_dir) if f"Race {r} Facts.md" in f] + ["None"])[-1]) if any(f"Race {r} Facts.md" in f for f in os.listdir(target_dir)) else None
        if facts_file and os.path.exists(facts_file): 
            facts_done += 1
            
            # Check batches
            horses = get_horse_numbers(facts_file)
            batches = get_batches(horses, 3)
            date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
            an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
            
            if os.path.exists(an_file) and "✅ HKJC Analysis 組裝完成" not in analysis_status_dict:
                content = open(an_file).read()
                if "[FILL]" not in content and "缺失核心" not in content and "未分析" not in content:
                    analysis_passed += 1
                    analysis_status_dict[r] = "✅ 分析與 QA 完成"
                    continue
            
            # If not completely passed, figure out what's missing
            logic_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            if not os.path.exists(logic_json):
                analysis_status_dict[r] = f"等待建立 Race_{r}_Logic.json，請從 Batch 0 (戰場全景) 啟動"
                continue
                
            # Logic JSON exists, check which batches are filled
            try:
                with open(logic_json, 'r', encoding='utf-8') as f:
                    logic_data = json.load(f)
            except Exception:
                analysis_status_dict[r] = "🚨 Race Logic JSON 解析失敗，需要修復"
                continue
                
            completed_horses = list(logic_data.get('horses', {}).keys())
            pending_batch = None
            for idx, batch in enumerate(batches):
                if not all(str(h) in completed_horses for h in batch):
                    pending_batch = (idx + 1, batch)
                    break
            
            if pending_batch:
                analysis_status_dict[r] = f"進行中 - 等待 Batch {pending_batch[0]} (馬匹 {pending_batch[1]})"
            elif not logic_data.get('race_analysis', {}).get('verdict'):
                analysis_status_dict[r] = "進行中 - 等待 Verdict (最終判定)"
            else:
                analysis_status_dict[r] = "✨ QA 校驗與編譯失敗重試中"
        else:
            analysis_status_dict[r] = "等待 Facts.md 生成"

    chk_facts = "[x]" if facts_done == total_races else "[ ]"
    chk_analysis = "[x]" if analysis_passed == total_races else "[ ]"

    # Save and display tasks
    tasks_file = update_session_tasks(target_dir, total_races, missing_raw, chk_weather, facts_done, analysis_status_dict)
    print("📊 執行進度 (Task List Checklist):")
    print(f"  {chk_raw} 賽事資料下載 (Race 1-{total_races})")
    print(f"  {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    print(f"  {chk_facts} 事實錨點生成 (Facts.md: {facts_done}/{total_races})")
    print(f"  {chk_analysis} JSON 組合與合規 QA (Analysis: {analysis_passed}/{total_races})")
    print(f"  (詳細進度已輸出至: {os.path.basename(tasks_file)})")
    print("="*60 + "\n")

    # --- EXECUTION STATE MACHINE ---
    if missing_raw:
        print("🚨 State 0: 發現原始數據缺失！自動呼叫 Extractor 進行修補...")
        trigger_extractor(args.url, target_dir)
        print("✅ 數據修補完畢，請重新執行 Orchestrator。")
        sys.exit(0)

    if chk_weather == "[ ]":
        print("🚨 State 1 行動要求 (Action Required):")
        print("👉 LLM Agent 請注意：請調查今日場地天氣與賽道偏差，並於此目錄建立 `_Meeting_Intelligence_Package.md`。")
        print("完成後，請重新執行本 Orchestrator！")
        sys.exit(0)

    if chk_facts == "[ ]":
        print("⚙️ State 2: 正在補全缺失之 Facts.md...")
        for r in range(1, total_races + 1):
            facts_file = None
            for f in os.listdir(target_dir):
                if f"Race {r} Facts.md" in f:
                    facts_file = os.path.join(target_dir, f)
                    break
            
            if not facts_file:
                print(f"  -> 生成 Race {r} Facts...")
                rc, fg = get_rc_fg_paths(target_dir, r)
                date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
                out_path = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
                cmd = ["python3", ".agents/scripts/inject_hkjc_fact_anchors.py", fg, "--output", out_path]
                subprocess.run(cmd, check=True)
                
        print("✅ Facts 全部生成完畢！")
        print("請立刻重新執行 Orchestrator 以前往 State 3。")
        sys.exit(0)

    if chk_analysis == "[ ]":
        date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
        strike_file = os.path.join(target_dir, ".qa_strikes.json")
        strikes = {}
        if os.path.exists(strike_file):
            strikes = json.load(open(strike_file))
            
        for r in range(1, total_races + 1):
            if "✅" in analysis_status_dict.get(r, ""):
                continue
                
            print(f"🐎 正在處理 Race {r} ...")
            facts_path = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            logic_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
            try:
                horses = get_horse_numbers(facts_path)
            except Exception:
                horses = []
            batches = get_batches(horses, 3)
            
            # 1. Provide Context for JSON Creation
            if "等待建立" in analysis_status_dict[r]:
                print(f"🚨 State 3 行動要求 (Race {r} JSON 未建立):")
                print(f"👉 LLM Agent 請注意：請讀取 `{os.path.basename(facts_path)}` 的地形檔位，")
                print(f"並在同目錄建立 `{os.path.basename(logic_json)}` 包含 Batch 0 的 `race_analysis.speed_map`。")
                print("生成完畢後，請重新執行本 Orchestrator！")
                sys.exit(0)
                
            # 2. Iterative Batches
            try:
                logic_data = json.load(open(logic_json))
            except Exception:
                logic_data = {}
            completed_horses = list(logic_data.get('horses', {}).keys())
            
            pending_batch = None
            for idx, batch in enumerate(batches):
                # check str compatibility too
                if not all(str(h) in completed_horses for h in batch):
                    pending_batch = (idx + 1, batch)
                    break
                    
            if pending_batch:
                print(f"🚨 State 3 行動要求 (Race {r} Batch {pending_batch[0]} 未完成):")
                print(f"👉 LLM Agent 請注意：請讀取這 3 匹馬的 Facts.md，並依據 Batch 0 結果，")
                print(f"填寫 `{os.path.basename(logic_json)}` 中的 {pending_batch[1]} 馬匹資料。")
                print("⚠️ 強制規定: 評級矩陣必須包含 `_reasoning` 欄位, 核心邏輯介於 100-200字。")
                print("生成完畢後，請重新執行本 Orchestrator！")
                sys.exit(0)
                
            # 3. Verdict
            if not logic_data.get('race_analysis', {}).get('verdict'):
                print(f"🚨 State 3 行動要求 (Race {r} 最終判定未完成):")
                print(f"👉 LLM Agent 請注意：所有馬匹已完成！請呼叫數學排序模組或自行比對分數，")
                print(f"然後在 `{os.path.basename(logic_json)}` 填寫 `verdict` 模塊。")
                print("生成完畢後，請重新執行本 Orchestrator！")
                sys.exit(0)
                
            # 4. Compilation & QA Filter
            print(f"⚙️ Race {r} JSON 填寫完畢，正在進行 Compilation (JSON -> MD)...")
            compile_cmd = ["python3", ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py", facts_path, logic_json, "--output", an_file]
            res = subprocess.run(compile_cmd)
            
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(logic_json)} 是否為合法 JSON。")
                sys.exit(1)
                
            print(f"🛡️ 正在就編譯好的 Race {r} 進行 Batch QA (completion_gate_v2.py)...")
            qa_res = subprocess.run(["python3", ".agents/scripts/completion_gate_v2.py", an_file, "--domain", "hkjc"])
            
            if qa_res.returncode != 0:
                key = f"race_{r}_qa"
                strikes[key] = strikes.get(key, 0) + 1
                json.dump(strikes, open(strike_file, 'w'))
                
                if strikes[key] >= 3:
                     print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗，恐為邊緣賽事狀況 (如新馬賽)！請人類介入調查或手動補全 `{os.path.basename(logic_json)}`。")
                     print("你可以手動略過此場的 QA 檢查以繼續。")
                     sys.exit(1)
                     
                print(f"\n❌ Race {r} 驗證失敗 (Failed with Exit Code 1)！ Strike {strikes[key]}/3")
                print(f"👉 LLM Agent 請注意：發現字數不足、格式遺失或觸發 Fluff Regex。")
                print("請檢查對話框的 QA 報錯點，修改 JSON 後再次重跑 Orchestrator。")
                sys.exit(1)
            else:
                strikes[f"race_{r}_qa"] = 0 # Reset strike
                json.dump(strikes, open(strike_file, 'w'))
                print(f"✅ Race {r} Batch QA 通過！將會自動推進下一場！")
                # Loop naturally advances to r+1

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！")
    # subprocess.run(["python3", ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py", "--target_dir", target_dir])
    
    print("\n🎉 [SUCCESS] HKJC Wong Choi Pipeline 任務全數擊破！")
    
if __name__ == "__main__":
    main()
