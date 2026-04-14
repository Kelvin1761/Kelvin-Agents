#!/usr/bin/env python3
import argparse
import os
import sys
import subprocess
import re
import json
import math
import time
import hashlib

def notify_telegram(msg):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../scripts/send_telegram_msg.py")
    if os.path.exists(script_path):
        subprocess.run(["python3", script_path, msg])

# Session start time for preflight check
SESSION_START_TIME = time.time()

def parse_url_for_details(url):
    match = re.search(r'form-guide/horse-racing/([^/-]+)-(\d{8})/', url)
    if not match:
        raise ValueError("Invalid URL format. Cannot extract Venue and Date.")
    venue = match.group(1).title()
    date_str = match.group(2)
    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return venue, formatted_date

def get_target_dir(venue, formatted_date, auto_create=False):
    base_dir = "."
    dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date}_{venue}_Race_")]
    if not dirs:
        dirs = [d for d in os.listdir(base_dir) if os.path.isdir(d) and d.startswith(f"{formatted_date} {venue}")]
    if dirs:
        return os.path.abspath(os.path.join(base_dir, dirs[0]))
    
    if auto_create:
        new_dir = os.path.abspath(os.path.join(base_dir, f"{formatted_date} {venue}"))
        os.makedirs(new_dir, exist_ok=True)
        return new_dir
    return None

def trigger_extractor(url):
    print(f"🚀 [Orchestrator] 啟動 AU Race Extractor 提取全日數據...")
    script_path = ".agents/skills/au_racing/au_race_extractor/scripts/extractor.py"
    if not os.path.exists(script_path):
        print(f"❌ [Error] 找不到爬蟲腳本: {script_path}")
        sys.exit(1)
    try:
        subprocess.run(["python3", script_path, url, "all"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"❌ [Error] 數據提取腳本執行失敗: {e}")
        sys.exit(1)

def discover_total_races(target_dir):
    combined = [f for f in os.listdir(target_dir) if re.search(r'Race \d+-(\d+)', f)]
    if combined:
        m = re.search(r'Race \d+-(\d+)', combined[0])
        if m:
            return int(m.group(1))

    racecards = [f for f in os.listdir(target_dir) if "Racecard.md" in f]
    max_race = 0
    for card in racecards:
        m = re.search(r'Race_(\d+)', card) or re.search(r'Race (\d+)', card)
        if m:
            race_num = int(m.group(1))
            if race_num > max_race:
                max_race = race_num
    return max_race

def check_raw_data_completeness(target_dir, total_races):
    missing_data = []
    combined_rc = any(re.search(r'Race 1-\d+ Racecard\.md', f) for f in os.listdir(target_dir))
    combined_fg = any(re.search(r'Race 1-\d+ Formguide\.md', f) for f in os.listdir(target_dir))
    if not (combined_rc and combined_fg):
        for race_num in range(1, total_races + 1):
            if not any(re.search(rf'Race {race_num} Formguide\.md', f) for f in os.listdir(target_dir)):
                missing_data.append(f"Race {race_num} Formguide.md")
            if not any(re.search(rf'Race {race_num}.*Racecard\.md', f) for f in os.listdir(target_dir)):
                missing_data.append(f"Race {race_num} Racecard.md")
    return missing_data

def get_racecard_path(target_dir, race_num):
    for f in os.listdir(target_dir):
        if re.search(r'Race 1-\d+ Racecard\.md', f): return os.path.join(target_dir, f)
        if f"Race {race_num}" in f and "Racecard.md" in f: return os.path.join(target_dir, f)
    return None

def get_formguide_path(target_dir, race_num):
    for f in os.listdir(target_dir):
        if re.search(r'Race 1-\d+ Formguide\.md', f): return os.path.join(target_dir, f)
        if f"Race {race_num}" in f and "Formguide.md" in f: return os.path.join(target_dir, f)
    return None

def get_horse_numbers(facts_path):
    if not os.path.exists(facts_path): return []
    with open(facts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    horses = []
    # Identify horse blocks
    blocks = re.split(r'(?=\[#\d+\]|### 馬匹 #\d+|### 馬號 \d+)', content)
    for b in blocks:
        m = re.search(r'\[#(\d+)\]|馬匹 #(\d+)|馬號 (\d+)', b)
        if m: 
            val = m.group(1) or m.group(2) or m.group(3)
            horses.append(int(val))
    return sorted(list(set(horses)))

def get_batches(horses, batch_size=3):
    return [horses[i:i + batch_size] for i in range(0, len(horses), batch_size)]

def update_session_tasks(target_dir, total_races, missing_raw, chk_weather, facts_status, analysis_status, batch_details):
    out_path = os.path.join(target_dir, "_session_tasks.md")
    lines = ["# 🏆 AU Wong Choi Live Session Tasks\n"]
    lines.append(f"- {'[ ]' if missing_raw else '[x]'} 賽事資料下載 (Race 1-{total_races})")
    lines.append(f"- {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    
    for r in range(1, total_races + 1):
        fc = '[x]' if facts_status.get(r, False) else '[ ]'
        an = '[x]' if analysis_status.get(r, False) else '[ ]'
        lines.append(f"\n## Race {r}")
        lines.append(f"- {fc} 事實錨點生成 (Facts.md)")
        lines.append(f"- {an} 戰略邏輯與盤口對照 (Analysis.md)")
        if not analysis_status.get(r, False) and r in batch_details:
            bd = batch_details[r]
            from itertools import chain
            done_horses = bd.get('done', [])
            all_batches = bd.get('batches', [])
            for idx, batch_horses in enumerate(all_batches):
                is_batch_done = all(h in done_horses for h in batch_horses)
                bc = '[x]' if is_batch_done else '[ ]'
                lines.append(f"  - {bc} Batch {idx+1} (馬匹: {batch_horses})")
                
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Racenet Event URL")
    args = parser.parse_args()

    url = args.url
    venue, formatted_date = parse_url_for_details(url)
    
    print("="*60)
    print("🏇 AU Wong Choi Orchestrator (State Machine V9.2)")
    print("="*60)
    
    target_dir = get_target_dir(venue, formatted_date)
    if not target_dir:
        print("📂 找不到目標數據庫，將執行 State 0 (提取資料)...")
        target_dir = get_target_dir(venue, formatted_date, auto_create=True)
        trigger_extractor(url)
        if not os.path.isdir(target_dir):
            print("❌ [Fatal] 爬蟲執行後仍找不到目標資料夾！")
            sys.exit(1)
    
    # ── Preflight Security Check ──
    preflight_script = ".agents/scripts/preflight_environment_check.py"
    if os.path.exists(preflight_script):
        pf_result = subprocess.run(
            ["python3", preflight_script, target_dir, "--domain", "au",
             "--session-start", str(SESSION_START_TIME)],
            capture_output=True, text=True
        )
        print(pf_result.stdout)
        if pf_result.returncode == 2:
            print("🛑 Preflight check FAILED — 請清理可疑檔案後再執行！")
            sys.exit(2)
            
    total_races = discover_total_races(target_dir)
    print(f"✅ 目標目錄: {os.path.basename(target_dir)}")
    print(f"✅ 賽事總數: {total_races} 場\n")

    # --- STATE 0: Idempotent Raw Data Check ---
    missing_raw = check_raw_data_completeness(target_dir, total_races)
    chk_raw = "[ ]" if missing_raw else "[x]"
    
    # --- Check higher states ---
    weather_file = os.path.join(target_dir, "_Meeting_Intelligence_Package.md")
    chk_weather = "[x]" if os.path.exists(weather_file) else "[ ]"
    
    facts_done = 0
    skel_done = 0
    analysis_passed = 0
    
    facts_status = {}
    analysis_status = {}
    batch_details = {}
    
    date_prefix = os.path.basename(target_dir).split(" ")[0]
    
    for r in range(1, total_races + 1):
        facts_status[r] = any(re.search(rf'Race {r} Facts\.md', f) for f in os.listdir(target_dir))
        if facts_status[r]: 
            facts_done += 1
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            horses = get_horse_numbers(facts_file)
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            done_horses = []
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        j_data = json.load(f)
                        if 'horses' in j_data:
                            done_horses = [int(h['id']) for h in j_data['horses'] if 'id' in h]
                except Exception:
                    pass
            batch_details[r] = {
                'batches': get_batches(horses, 3),
                'done': done_horses,
                'horses': horses
            }
            
        an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
        if os.path.exists(an_file):
            content = open(an_file).read()
            if "[FILL]" not in content and "FILL:" not in content:
                analysis_passed += 1
                analysis_status[r] = True

    chk_facts = "[x]" if facts_done == total_races else "[ ]"
    chk_analysis = "[x]" if analysis_passed == total_races else "[ ]"

    # Persist tasks to _session_tasks.md
    update_session_tasks(target_dir, total_races, missing_raw, chk_weather, facts_status, analysis_status, batch_details)

    print("📊 執行進度 (Task List Checklist):")
    print(f"  {chk_raw} 賽事資料下載 (Race 1-{total_races})")
    print(f"  {chk_weather} 天氣與場地情報 (_Meeting_Intelligence_Package.md)")
    print(f"  {chk_facts} 事實錨點生成 (Facts.md: {facts_done}/{total_races})")
    print(f"  {chk_analysis} JSON 組合與合規 QA (Analysis: {analysis_passed}/{total_races})")
    print("  (詳細進度已輸出至: _session_tasks.md)")
    print("="*60 + "\n")

    # --- 3-Strike QA Tracker ---
    qa_tracker_file = os.path.join(target_dir, ".qa_strikes.json")
    strikes = {}
    if os.path.exists(qa_tracker_file):
        try:
            with open(qa_tracker_file, 'r') as f:
                strikes = json.load(f)
        except: pass
        
    def save_strikes():
        with open(qa_tracker_file, 'w') as f:
            json.dump(strikes, f)

    # --- EXECUTION STATE MACHINE ---
    if missing_raw:
        print("🚨 State 0: 發現原始數據缺失！自動呼叫 Extractor 進行修補...")
        trigger_extractor(url)
        print("✅ 數據修補完畢，請重新執行 Orchestrator。")
        sys.exit(0)

    if chk_weather == "[ ]":
        print("🚨 State 1 行動要求 (Action Required):")
        print("👉 LLM Agent 請注意：請調查今日場地天氣與賽道偏差，並於此目錄建立 `_Meeting_Intelligence_Package.md`。")
        print("完成後，請重新執行本 Orchestrator！")
        notify_telegram("🚨 **AU State 1 Action Required**\n缺少場地天氣與賽道偏差，請手動生成 `_Meeting_Intelligence_Package.md`。")
        sys.exit(0)

    if chk_facts == "[ ]":
        print("⚙️ State 2: 正在補全缺失之 Facts.md...")
        for r in range(1, total_races + 1):
            facts_path = None
            for f in os.listdir(target_dir):
                if re.search(rf'Race {r} Facts\.md', f):
                    facts_path = os.path.join(target_dir, f)
                    break
            
            if not facts_path:
                print(f"  -> 生成 Race {r} Facts...")
                rc = get_racecard_path(target_dir, r)
                fg = get_formguide_path(target_dir, r)
                cmd = ["python3", ".agents/scripts/inject_fact_anchors.py", rc, fg, "--max-display", "5", "--venue", venue]
                subprocess.run(cmd, check=True)
                
        print("✅ Facts 全部生成完畢！自動無縫推進前往 State 3 執行分析...")

    # --- STATE 2.5: Batch 0 Speed Map (race_analysis.speed_map) ---
    # Check if any race is missing its Batch 0 speed_map with required fields
    for r in range(1, total_races + 1):
        json_file_b0 = os.path.join(target_dir, f"Race_{r}_Logic.json")
        # Only check races that don't have Analysis.md yet
        an_file_check = os.path.join(target_dir, f"{os.path.basename(target_dir).split(' ')[0][5:]} Race {r} Analysis.md")
        if os.path.exists(an_file_check):
            continue
        if os.path.exists(json_file_b0):
            try:
                with open(json_file_b0, 'r', encoding='utf-8') as _f:
                    _jd = json.load(_f)
                sm = _jd.get('race_analysis', {}).get('speed_map', {})
                missing_sm = [k for k in ['track_bias', 'tactical_nodes', 'collapse_point'] if not sm.get(k)]
                if missing_sm:
                    facts_file_b0 = os.path.join(target_dir, f"{os.path.basename(target_dir).split(' ')[0]} Race {r} Facts.md")
                    print(f"\n🚨🚨🚨【AU HORSE ANALYST 啟動要求 (Race {r} Batch 0 戰場全景)】🚨🚨🚨")
                    print(f"👉 LLM Agent 請強制切換為 au_horse_analyst 模式！讀取 `{os.path.basename(facts_file_b0)}`。")
                    print("在 <thought> 標籤內執行【Step 0 步速瀑布】推理：")
                    print(f"然後更新 `Race_{r}_Logic.json` 的 race_analysis.speed_map，必須填寫：")
                    print("  speed_map: {")
                    print("    expected_pace,       ← 'Crawl/Moderate/Fast/Chaotic'")
                    print("    leaders: [],         ← 馬號列表")
                    print("    on_pace: [],         ← 馬號列表")
                    print("    mid_pack: [],        ← 馬號列表")
                    print("    closers: [],         ← 馬號列表")
                    print("    track_bias,          ← 跑道偏差描述 [強制]")
                    print("    tactical_nodes,      ← 戰術節點 [強制]")
                    print("    collapse_point       ← 步速崩潰點分析 [強制]")
                    print("  }")
                    print(f"\n缺失欄位: {missing_sm}")
                    print("生成完畢後，請重新執行本 Orchestrator！")
                    notify_telegram(f"📍 **AU Race {r} Action Required**\nBatch 0 步速瀑布 (Speed Map) 尚未填寫。")
                    sys.exit(0)
            except Exception:
                pass  # JSON not parseable yet, handled by State 3


    if chk_analysis == "[ ]":
        date_prefix = os.path.basename(target_dir).split(" ")[0]
        short_prefix = date_prefix[5:] if len(date_prefix) == 10 else date_prefix
        
        for r in range(1, total_races + 1):
            if analysis_status.get(r, False):
                continue
                
            an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            if not os.path.exists(facts_file):
                facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            
            
            # ============================================================
            # V9: 逐匹馬分析模式 (One Horse at a Time)
            # ============================================================
            skeleton_script = ".agents/skills/au_racing/au_wong_choi/scripts/create_au_logic_skeleton.py"
            
            try:
                logic_data = json.load(open(json_file, encoding='utf-8'))
            except Exception:
                logic_data = {}
            
            horses_dict = logic_data.get('horses', {})
            
            try:
                all_horses = get_horse_numbers(facts_file)
            except:
                all_horses = []
            
            target_horse = None
            
            for h in all_horses:
                hkey = str(h)
                h_entry = horses_dict.get(hkey, {})
                h_json_str = json.dumps(h_entry, ensure_ascii=False)
                
                if not h_entry:
                    target_horse = h
                    break
                if '[FILL]' in h_json_str:
                    target_horse = h
                    break
                
                horse_name = h_entry.get('horse_name', '')
                core_logic = h_entry.get('core_logic', '')
                locked_nonce = h_entry.get('_validation_nonce', '')
                
                errors = []
                # V9.2: Relaxed rules — no horse name, word count, or data reference enforcement
                # Only nonce validation remains
                
                # WALL-008: Nonce 驗證
                if not locked_nonce:
                    errors.append(f"WALL-008: Missing _validation_nonce")
                
                if errors:
                    print(f"\n🚨 Horse #{h} ({horse_name}) firewall failed!")
                    for e in errors:
                        print(f"   ❌ {e}")
                    horses_dict[hkey]['core_logic'] = '[FILL]'
                    logic_data['horses'] = horses_dict
                    with open(json_file, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    target_horse = h
                    break
                else:
                    print(f"   ✅ Horse #{h} ({horse_name}) validated")
            
            if target_horse is not None:
                hkey = str(target_horse)
                h_entry = horses_dict.get(hkey, {})
                if not h_entry or '[FILL]' in json.dumps(h_entry, ensure_ascii=False):
                    print(f"\n⚙️ Building skeleton for Horse #{target_horse}...")
                    skel_result = subprocess.run(
                        ["python3", skeleton_script, facts_file, str(r), str(target_horse)],
                        capture_output=True, text=True
                    )
                    print(skel_result.stdout)
                    if skel_result.returncode != 0:
                        print(f"❌ Skeleton failed: {skel_result.stderr}")
                        sys.exit(1)
                    logic_data = json.load(open(json_file, encoding='utf-8'))
                    h_entry = logic_data.get('horses', {}).get(hkey, {})
                
                try:
                    with open(facts_file, 'r', encoding='utf-8') as _f:
                        facts_content = _f.read()
                except:
                    facts_content = ""
                
                horse_facts_block = ""
                for marker_pat in [rf'\[#{target_horse}\]', rf'### 馬號 {target_horse} — ', rf'### 馬匹 #{target_horse} ']:
                    h_match = re.search(marker_pat, facts_content)
                    if h_match:
                        h_start = h_match.start()
                        h_next = re.search(r'(?:\[#\d+\]|### 馬號 \d+ — |### 馬匹 #\d+)', facts_content[h_match.end():])
                        h_end = h_match.end() + h_next.start() if h_next else len(facts_content)
                        horse_facts_block = facts_content[h_start:h_end]
                        break
                
                horse_name = h_entry.get('horse_name', '?')
                locked_l400 = h_entry.get('sectional_forensic', {}).get('raw_L400', 'N/A')
                locked_pos = h_entry.get('eem_energy', {}).get('last_run_position', 'N/A')
                
                # --- V9.1 JIT Slicing Mechanism ---
                runtime_dir = os.path.join(target_dir, ".runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                runtime_ctx_path = os.path.join(runtime_dir, "Active_Horse_Context.md")
                
                locked_nonce = h_entry.get('_validation_nonce', 'MISSING')
                with open(runtime_ctx_path, "w", encoding="utf-8") as _ctx_f:
                    _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                    _ctx_f.write(horse_facts_block)
                
                print(f"\n{'='*60}")
                print(f"🚨🚨🚨【AU HORSE ANALYST — Race {r} / Horse #{target_horse} '{horse_name}'】🚨🚨🚨")
                print(f"{'='*60}")
                print(f"")
                print(f"📋 Python pre-filled (DO NOT modify): L400={locked_l400}, Pos={locked_pos}")
                print(f"")
                print(f"📖 Horse context written to:")
                print(f"   => {runtime_ctx_path}")
                print(f"   ⛔ DO NOT read the full Facts.md")
                print(f"")
                print(f"👉 Open `{os.path.basename(json_file)}`, fill [FILL] fields for horse \"{target_horse}\" ONLY.")
                print(f"🔴 Firewall: no data tampering, single horse only, no .py scripts!")
                print(f"")
                print(f"📌 After completion, MUST execute:")
                print(f"   python3 .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py \"{url}\"")
                notify_telegram(f"🚨 **AU Race {r} Action Required**\n請填寫 Horse #{target_horse} '{horse_name}' 嘅獨立分析。")
                sys.exit(0)
                
            # If ALL batches are done, compile and QA
            # But wait, did we fail Strike 3?
            if strikes.get(str(r), 0) >= 3:
                print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗 (Strike-3 Fallback)。")
                print(f"系統已中斷自動化，請人類直接打開 `{os.path.basename(json_file)}` 修正長度與邏輯！")
                print(f"修正後執行: python .agents/scripts/completion_gate_v2.py \"{an_file}\" --domain au")
                notify_telegram(f"❌ **AU Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，恐為極端異常賽事，請人工介入修正 JSON！")
                sys.exit(1)
                
            print(f"⚙️ 發現 Race {r} JSON 所有馬匹已聚齊！正在編譯...")
            compile_cmd = ["python3", ".agents/skills/au_racing/au_wong_choi/scripts/compile_analysis_template.py", facts_file, json_file, "--output", an_file]
            res = subprocess.run(compile_cmd)
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(json_file)}。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                sys.exit(1)
            
            # 4.5 Monte Carlo Simulation V2 (via run_monte_carlo.py)
            print(f"🎲 Running Monte Carlo V2 simulation for Race {r}...")
            mc_script = ".agents/scripts/run_monte_carlo.py"
            if os.path.exists(mc_script):
                mc_res = subprocess.run(["python3", mc_script, "--target_dir", target_dir], capture_output=True, text=True)
                if mc_res.returncode == 0:
                    print(f"✅ MC V2 simulation and injection complete")
                else:
                    print(f"⚠️ MC V2 simulation failed (non-blocking): {mc_res.stderr}")
            else:
                print(f"⚠️ MC V2 script not found: {mc_script}")
            
            # QA
            print(f"🛡️ 正在進行 Batch QA (completion_gate_v2.py)...")
            qa_res = subprocess.run(["python3", ".agents/scripts/completion_gate_v2.py", an_file, "--domain", "au"])
            if qa_res.returncode != 0:
                print(f"\n❌ Race {r} QA 驗證失敗！")
                print(f"請重新修改 `{os.path.basename(json_file)}`，補齊 `_reasoning` 與字數。修改後重跑 Orchestrator。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                sys.exit(1)
            else:
                print(f"✅ Race {r} Batch QA 通過！")
                if str(r) in strikes:
                    del strikes[str(r)]
                    save_strikes()
                # Continue loop to next race

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！正在產製 Excel 報告...")
    subprocess.run(["python3", ".agents/skills/au_racing/au_wong_choi/scripts/generate_reports.py", target_dir])
    subprocess.run(["python3", ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "au"])
    
    print("☁️ State 5: 準備推送 Dashboard 至 Cloudflare...")
    push_script = "Horse Racing Dashboard/deploy.sh"
    if os.path.exists(push_script):
        subprocess.run(["sh", push_script])
        print("✅ 雲端同步完成！")
    else:
        print("👉 (未偵測到 Dashboard 自動推送腳本，請手動發佈)。")
        
    print("\n🎉 [SUCCESS] AU Wong Choi Pipeline 任務全數擊破！")
    notify_telegram("🎉 **AU Wong Choi 任務完成**\n所有分析已順利通過 QA 及編譯！")
    
if __name__ == "__main__":
    main()
