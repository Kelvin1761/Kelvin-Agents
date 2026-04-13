#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
import re
import json
import time

import urllib.request

def notify_telegram(msg):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../scripts/send_telegram_msg.py")
    if os.path.exists(script_path):
        subprocess.run(["python3", script_path, msg])

# Session start time for preflight check
SESSION_START_TIME = time.time()

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

def run_preflight_check(target_dir):
    """Run preflight environment scan to detect suspicious files."""
    preflight_script = ".agents/scripts/preflight_environment_check.py"
    if os.path.exists(preflight_script):
        result = subprocess.run(
            ["python3", preflight_script, target_dir, "--domain", "hkjc",
             "--session-start", str(SESSION_START_TIME)],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode == 2:
            print("🛑 Preflight check FAILED — 請清理可疑檔案後再執行！")
            sys.exit(2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="HKJC Race URL or target directory if URL is skipped")
    args = parser.parse_args()

    print("="*60)
    print("🏇 HKJC Wong Choi Orchestrator (State Machine V9.2)")
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
    
    # ── Preflight Security Check ──
    run_preflight_check(target_dir)
            
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
        matching_facts = [f for f in os.listdir(target_dir) if f"Race {r} Facts.md" in f]
        facts_file = os.path.join(target_dir, matching_facts[0]) if matching_facts else None
        if facts_file and os.path.exists(facts_file): 
            facts_done += 1
            
            # Check batches
            horses = get_horse_numbers(facts_file)
            batches = get_batches(horses, 3)
            date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
            an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
            
            if os.path.exists(an_file):
                content = open(an_file).read()
                if "[FILL]" not in content and "缺失核心" not in content and "未分析" not in content:
                    analysis_passed += 1
                    analysis_status_dict[r] = "✅ 分析與 QA 完成"
                    continue
            
            # If not completely passed, figure out what's missing
            logic_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            if not os.path.exists(logic_json):
                analysis_status_dict[r] = f"等待建立 Race_{r}_Logic.json (Speed Map)"
                continue
                
            # Logic JSON exists, check which batches are filled
            try:
                with open(logic_json, 'r', encoding='utf-8') as f:
                    logic_data = json.load(f)
            except Exception:
                analysis_status_dict[r] = "🚨 Race Logic JSON 解析失敗，需要修復"
                continue
            
            # Check if Speed Map is filled
            speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
            speed_map_str = json.dumps(speed_map, ensure_ascii=False)
            if '[FILL]' in speed_map_str or not speed_map.get('predicted_pace') or speed_map.get('predicted_pace') == '[FILL]':
                analysis_status_dict[r] = "等待填寫 Speed Map (步速瀑布)"
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
        notify_telegram("🚨 **HKJC State 1 Action Required**\n缺少場地天氣與賽道偏差，請手動生成 `_Meeting_Intelligence_Package.md`。")
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
                
        print("✅ Facts 全部生成完畢！自動無縫推進前往 State 3 執行分析...")
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
            
            # ─────────────────────────────────────────────────────────
            # STEP A: Auto-create Logic JSON skeleton if it doesn't exist
            # ─────────────────────────────────────────────────────────
            if not os.path.exists(logic_json):
                # Extract race class and distance from Facts.md
                race_class = "[FILL]"
                race_distance = "[FILL]"
                try:
                    facts_content = open(facts_path, encoding='utf-8').read()
                    m = re.search(r'場地:\s*([^|]*?)\s*\|\s*距離:\s*([^|]*?)\s*\|\s*班次:\s*([^\n]+)', facts_content)
                    if m:
                        race_distance = m.group(2).strip()
                        race_class = m.group(3).strip()
                except Exception:
                    pass
                
                initial_json = {
                    "race_analysis": {
                        "race_number": r,
                        "race_class": race_class,
                        "distance": race_distance,
                        "speed_map": {
                            "predicted_pace": "[FILL]",
                            "leaders": [],
                            "on_pace": [],
                            "mid_pack": [],
                            "closers": [],
                            "track_bias": "[FILL]",
                            "tactical_nodes": "[FILL]",
                            "collapse_point": "[FILL]"
                        }
                    },
                    "horses": {}
                }
                
                with open(logic_json, 'w', encoding='utf-8') as wf:
                    json.dump(initial_json, wf, ensure_ascii=False, indent=2)
                print(f"   ✅ 已自動建立 `{os.path.basename(logic_json)}` 骨架 ({race_class} / {race_distance})")
            
            # ─────────────────────────────────────────────────────────
            # STEP B: Check Speed Map — must be filled before horse analysis
            # ─────────────────────────────────────────────────────────
            try:
                logic_data = json.load(open(logic_json, encoding='utf-8'))
            except Exception:
                logic_data = {}
            
            speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
            speed_map_str = json.dumps(speed_map, ensure_ascii=False)
            
            if '[FILL]' in speed_map_str or not speed_map.get('predicted_pace') or speed_map.get('predicted_pace') == '[FILL]':
                print(f"\n{'='*60}")
                print(f"📍 Race {r} — 步速瀑布 (Speed Map) 待填寫")
                print(f"{'='*60}")
                print(f"")
                print(f"👉 請閱讀 `{os.path.basename(facts_path)}`，然後填入 `{os.path.basename(logic_json)}` 嘅 speed_map：")
                print(f"   → predicted_pace: 'Crawl' / 'Moderate' / 'Fast' / 'Chaotic'")
                print(f"   → leaders / on_pace / mid_pack / closers: 馬號列表 (字串)")
                print(f"   → track_bias: 跑道偏差描述")
                print(f"   → tactical_nodes: 戰術節點分析")
                print(f"   → collapse_point: 步速崩潰點分析")
                print(f"")
                print(f"完成後重新執行 Orchestrator！")
                notify_telegram(f"📍 **HKJC Race {r} Action Required**\n步速瀑布 (Speed Map) 尚未填寫，請查閱全景資訊。")
                sys.exit(0)
                
            # ============================================================
            # V9: 逐匹馬分析模式 (One Horse at a Time)
            # ============================================================
            skeleton_script = ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py"
            
            try:
                logic_data = json.load(open(logic_json, encoding='utf-8'))
            except Exception:
                logic_data = {}
            
            horses_dict = logic_data.get('horses', {})
            
            # Find the NEXT undone horse (one at a time)
            target_horse = None
            target_horse_name = None
            
            for h in horses:
                hkey = str(h)
                h_entry = horses_dict.get(hkey, {})
                h_json_str = json.dumps(h_entry, ensure_ascii=False)
                
                if not h_entry:
                    # No skeleton yet → create it
                    target_horse = h
                    break
                    
                if '[FILL]' in h_json_str:
                    # Skeleton exists but LLM hasn't filled it yet
                    target_horse = h
                    break
                
                # Horse filled → validate (firewall)
                horse_name = h_entry.get('horse_name', '')
                core_logic = h_entry.get('core_logic', '')
                locked_nonce = h_entry.get('_validation_nonce', '')
                
                errors = []
                # V9.2: Relaxed rules — no horse name or word count enforcement
                # Only nonce validation remains as hard requirement
                
                # WALL-008: Nonce 驗證
                if not locked_nonce:
                    errors.append(f"WALL-008: 缺失防偽標籤 _validation_nonce (可能使用了不合規的 Batch Script 繞過)")
                    
                if errors:
                    print(f"\n🚨 馬號 {h}（{horse_name}）阻火牆驗證失敗！")
                    for e in errors:
                        print(f"   ❌ {e}")
                    # Reset core_logic to [FILL] to force redo
                    horses_dict[hkey]['core_logic'] = '[FILL]'
                    logic_data['horses'] = horses_dict
                    with open(logic_json, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    target_horse = h
                    break
                else:
                    print(f"   ✅ 馬號 {h}（{horse_name}）驗證通過")
            
            if target_horse is None:
                # All horses done! Skip to verdict
                pass
            else:
                hkey = str(target_horse)
                
                # Step 1: Call Python skeleton generator to pre-fill factual data
                h_entry = horses_dict.get(hkey, {})
                if not h_entry or '[FILL]' in json.dumps(h_entry, ensure_ascii=False):
                    print(f"\n⚙️ 正在為馬號 {target_horse} 建立/更新 JSON 骨架...")
                    skel_result = subprocess.run(
                        ["python3", skeleton_script, facts_path, str(r), str(target_horse)],
                        capture_output=True, text=True
                    )
                    print(skel_result.stdout)
                    if skel_result.returncode != 0:
                        print(f"❌ 骨架建立失敗: {skel_result.stderr}")
                        sys.exit(1)
                    
                    # Reload JSON after skeleton creation
                    logic_data = json.load(open(logic_json, encoding='utf-8'))
                    h_entry = logic_data.get('horses', {}).get(hkey, {})
                
                # Step 2: Extract this horse's Facts block for LLM context
                try:
                    with open(facts_path, 'r', encoding='utf-8') as _f:
                        facts_content = _f.read()
                except:
                    facts_content = ""
                
                # Extract single horse block
                h_block_match = re.search(rf'### 馬號 {target_horse} — ', facts_content)
                horse_facts_block = ""
                if h_block_match:
                    h_start = h_block_match.start()
                    h_next = re.search(r'### 馬號 \d+ — ', facts_content[h_block_match.end():])
                    h_end = h_block_match.end() + h_next.start() if h_next else len(facts_content)
                    horse_facts_block = facts_content[h_start:h_end]
                
                horse_name = h_entry.get('horse_name', '?')
                locked_l400 = h_entry.get('sectional_forensic', {}).get('raw_L400', 'N/A')
                locked_pos = h_entry.get('eem_energy', {}).get('last_run_position', 'N/A')
                locked_nonce = h_entry.get('_validation_nonce', 'MISSING')
                
                # --- V9.1 JIT Slicing Mechanism ---
                runtime_dir = os.path.join(target_dir, ".runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                runtime_ctx_path = os.path.join(runtime_dir, "Active_Horse_Context.md")
                
                with open(runtime_ctx_path, "w", encoding="utf-8") as _ctx_f:
                    _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                    _ctx_f.write(horse_facts_block)
                
                # Step 3: Print focused single-horse instruction
                print(f"\n{'='*60}")
                print(f"🚨🚨🚨【HKJC HORSE ANALYST — Race {r} / 馬號 {target_horse}「{horse_name}」】🚨🚨🚨")
                print(f"{'='*60}")
                print(f"")
                print(f"📋 Python 已預填事實數據。當前已將該馬匹事實寫入：")
                print(f"   => {runtime_ctx_path}")
                print(f"   ⛔ 絕對禁止自行查閱全局 Facts.md")
                print(f"")
                print(f"👉 請讀取上述暫存檔，打開 `{os.path.basename(logic_json)}`，找到馬號 \"{target_horse}\" 嘅 JSON 節點。")
                print(f"⚠️ 將所有標記為 [FILL] 的欄位替換為你的分析結果。")
                print(f"")
                print(f"🔴 阻火牆規則 (違反即退回)：")
                print(f"   1. 嚴禁修改 raw_L400 ({locked_l400}) 同 last_run_position ({locked_pos})")
                print(f"   2. 嚴禁填寫其他馬號的數據！只做馬號 {target_horse}")
                print(f"   3. 嚴禁修改 _validation_nonce！")
                print(f"   4. 嚴禁自行建立任何 .py 腳本！")
                print(f"")
                print(f"📌 完成後必須執行:")
                print(f"   python3 .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py {os.path.basename(target_dir)}")
                notify_telegram(f"🚨 **HKJC Race {r} Action Required**\n請填寫 Horse #{target_horse} '{horse_name}' 嘅獨立分析。")
                sys.exit(0)
                
            # 3. Verdict
            if not logic_data.get('race_analysis', {}).get('verdict'):
                print(f"🚨 State 3 行動要求 (Race {r} 最終判定未完成):")
                print(f"👉 LLM Agent 請注意：所有馬匹已完成！請呼叫數學排序模組或自行比對分數，")
                print(f"然後在 `{os.path.basename(logic_json)}` 填寫 `verdict` 模塊。")
                print("生成完畢後，請重新執行本 Orchestrator！")
                notify_telegram(f"🚨 **HKJC Race {r} Verdict Needed**\n請比對分析分數，填寫最終 verdict 判定。")
                sys.exit(0)
                


            # 4. Compilation & QA Filter
            print(f"⚙️ Race {r} JSON 填寫完畢，正在進行 Compilation (JSON -> MD)...")
            compile_cmd = ["python3", ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py", facts_path, logic_json, "--output", an_file]
            res = subprocess.run(compile_cmd)
            
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(logic_json)} 是否為合法 JSON。")
                sys.exit(1)
            
            # 4.5 Monte Carlo Simulation (non-blocking)
            print(f"🎲 正在為 Race {r} 執行 Monte Carlo 模擬...")
            mc_script = ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/monte_carlo_hkjc.py"
            if os.path.exists(mc_script):
                mc_res = subprocess.run(
                    ["python3", mc_script, logic_json, facts_path],
                    capture_output=True, text=True)
                if mc_res.returncode == 0:
                    print(f"✅ MC 模擬完成")
                    # Append MC section to Analysis.md
                    mc_json_path = os.path.join(target_dir, f"Race_{r}_MC.json")
                    if os.path.exists(mc_json_path):
                        try:
                            mc_data = json.load(open(mc_json_path, 'r', encoding='utf-8'))
                            mc_section = mc_res.stdout
                            # Find the MC table in stdout and append to Analysis.md
                            if '📊 Monte Carlo' in mc_section:
                                with open(an_file, 'a', encoding='utf-8') as af:
                                    # Extract only the table section
                                    mc_lines = []
                                    in_mc = False
                                    for line in mc_section.split('\n'):
                                        if '📊 Monte Carlo' in line:
                                            in_mc = True
                                        if in_mc:
                                            mc_lines.append(line)
                                    if mc_lines:
                                        af.write('\n\n' + '\n'.join(mc_lines) + '\n')
                                        print(f"📊 MC 結果已附加到 {os.path.basename(an_file)}")
                        except Exception as e:
                            print(f"⚠️ MC 結果附加失敗: {e}")
                else:
                    print(f"⚠️ MC 模擬未能完成（非阻塞）: {mc_res.stderr[:200] if mc_res.stderr else 'unknown'}")
            else:
                print(f"⚠️ MC 腳本不存在: {mc_script}")
                
            print(f"🛡️ 正在就編譯好的 Race {r} 進行 Batch QA (completion_gate_v2.py)...")
            qa_res = subprocess.run(["python3", ".agents/scripts/completion_gate_v2.py", an_file, "--domain", "hkjc"])
            
            if qa_res.returncode != 0:
                key = f"race_{r}_qa"
                strikes[key] = strikes.get(key, 0) + 1
                json.dump(strikes, open(strike_file, 'w'))
                
                if strikes[key] >= 3:
                     print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗，恐為邊緣賽事狀況 (如新馬賽)！請人類介入調查或手動補全 `{os.path.basename(logic_json)}`。")
                     print("你可以手動略過此場的 QA 檢查以繼續。")
                     notify_telegram(f"❌ **HKJC Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，恐為邊緣賽事狀況，請人工介入！")
                     sys.exit(1)
                     
                print(f"\n❌ Race {r} 驗證失敗 (Failed with Exit Code 1)！ Strike {strikes[key]}/3")
                print(f"👉 LLM Agent 請注意：發現字數不足、格式遺失或觸發 Fluff Regex。")
                print("請檢查對話框的 QA 報錯點，修改 JSON 後再次重跑 Orchestrator。")
                sys.exit(1)
            else:
                strikes[f"race_{r}_qa"] = 0 # Reset strike
                json.dump(strikes, open(strike_file, 'w'))
                completed_count = sum(1 for x in analysis_status_dict.values() if "✅" in str(x)) + 1
                print(f"\n{'🎉'*10}")
                print(f"✅ Race {r} 分析完成並通過 QA！ ({completed_count}/{total_races})")
                print(f"{'🎉'*10}")
                if r < total_races:
                    print(f"\n{'─'*60}")
                    print(f"🔄 正在自動推進至 Race {r + 1}...")
                    print(f"{'─'*60}")
                # Loop naturally advances to r+1

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！正在產製 Excel 報告...")
    reports_script = ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py"
    if os.path.exists(reports_script):
        subprocess.run(["python3", reports_script, "--target_dir", target_dir])
    else:
        print("⚠️ generate_hkjc_reports.py 未找到，略過報告生成。")
    subprocess.run(["python3", ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "hkjc"])
    
    print("\n🎉 [SUCCESS] HKJC Wong Choi Pipeline 任務全數擊破！")
    notify_telegram("🎉 **HKJC Wong Choi 任務完成**\n所有分析已順利通過 QA 及編譯！")
    
if __name__ == "__main__":
    main()
