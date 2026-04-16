#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import argparse
import sys
import subprocess
import re
import json
import math
import time
import hashlib
import shutil

# Cross-platform Python executable
PYTHON = "python3" if shutil.which("python3") else "python"

def notify_telegram(msg):
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../scripts/send_telegram_msg.py")
    if os.path.exists(script_path):
        subprocess.run([PYTHON, script_path, msg])

# Session start time for preflight check
SESSION_START_TIME = time.time()

def parse_url_for_details(url):
    match = re.search(r'form-guide/horse-racing/([^/]+)-(\d{8})/', url)
    if not match:
        raise ValueError("Invalid URL format. Cannot extract Venue and Date.")
    venue = match.group(1).replace('-', ' ').title()
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
        subprocess.run([PYTHON, script_path, url, "all"], check=True)
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

def _next_cmd(target_dir):
    """Print machine-readable re-run command for LLM auto-execution."""
    dir_arg = os.path.basename(target_dir)
    print(f"\nNEXT_CMD: {PYTHON} .agents/skills/au_racing/au_wong_choi/scripts/au_orchestrator.py \"{dir_arg}\" --auto")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Racenet Event URL or target directory path")
    parser.add_argument("--auto", action="store_true", help="Auto mode: skip confirmation gate")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

    url = args.url
    target_dir = None

    if url.startswith("http"):
        venue, formatted_date = parse_url_for_details(url)
    else:
        # Directory resume mode (same as HKJC)
        target_dir = os.path.abspath(url)
        if not os.path.isdir(target_dir):
            print(f"❌ [Error] 提供的路徑 {target_dir} 不是有效目錄。")
            sys.exit(1)
        dir_name = os.path.basename(target_dir)
        parts = dir_name.split(" ", 1)
        formatted_date = parts[0] if parts else "unknown"
        venue = parts[1] if len(parts) > 1 else "Unknown"
        url = None

    print("="*60)
    print("🏇 AU Wong Choi Orchestrator (State Machine V9.3)")
    print("="*60)

    if not target_dir:
        target_dir = get_target_dir(venue, formatted_date)
    if not target_dir:
        if not url:
            print("❌ [Error] 找不到目標目錄且無 URL 可提取資料。")
            sys.exit(1)
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
            [PYTHON, preflight_script, target_dir, "--domain", "au",
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
                            done_horses = [int(k) for k, v in j_data['horses'].items()
                                           if v and '[FILL]' not in json.dumps(v, ensure_ascii=False)]
                except Exception:
                    pass
            batch_details[r] = {
                'batches': get_batches(horses, 3),
                'done': done_horses,
                'horses': horses
            }
            
        an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
        if os.path.exists(an_file):
            with open(an_file, 'r', encoding='utf-8') as _af:
                content = _af.read()
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

    # Race-by-race status board
    print(f"\n📋 逐場進度:")
    for _r in range(1, total_races + 1):
        if analysis_status.get(_r, False):
            print(f"  ✅ Race {_r}: 分析與 QA 完成")
        elif not facts_status.get(_r, False):
            print(f"  ⏳ Race {_r}: 等待 Facts.md 生成")
        elif _r in batch_details:
            _bd = batch_details[_r]
            _done_n = len(_bd.get('done', []))
            _total_n = len(_bd.get('horses', []))
            print(f"  🔄 Race {_r}: 進行中 ({_done_n}/{_total_n} horses)")
        else:
            print(f"  ⏳ Race {_r}: 等待開始")
    print("="*60 + "\n")

    # --- RACE DISTANCE & CLASS CONFIRMATION ---
    print("📏 全日賽事距離確認 (Race Distance Summary):")
    print("-" * 55)
    print(f"  {'Race':<8} {'Distance':<12} {'Class':<25} {'Status'}")
    print("-" * 55)
    distance_errors = []
    for r in range(1, total_races + 1):
        rc_path = get_racecard_path(target_dir, r)
        race_dist = "?"
        race_class = ""
        if rc_path and os.path.exists(rc_path):
            with open(rc_path, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
            # Parse: "RACE X — 900m | Maiden SW | $75,000"
            dist_m = re.search(r'[—–-]\s*(\d{3,5})m', header)
            class_m = re.search(r'\d+m\s*\|\s*([^|$]+)', header)
            if dist_m:
                race_dist = f"{dist_m.group(1)}m"
            if class_m:
                race_class = class_m.group(1).strip()
        
        if race_dist == "?":
            status = "❌ MISSING"
            distance_errors.append(r)
        else:
            status = "✅"
        
        print(f"  R{r:<7} {race_dist:<12} {race_class:<25} {status}")
    
    print("-" * 55)
    
    if distance_errors:
        print(f"\n🚨 [WARNING] 以下賽事距離提取失敗: {distance_errors}")
        print("   可能原因: extractor.py 嘅 Apollo cache Event lookup 失敗")
        print("   請檢查 Racecard header 格式是否包含 '— XXXm'")
        print("   建議: 重新執行 extractor 或手動修正 Racecard header\n")
    else:
        print(f"\n✅ 全部 {total_races} 場賽事距離確認正確！\n")

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

    # ── Confirmation Gate (first run only) ──
    if not args.auto and analysis_passed < total_races:
        print("🔒 【確認閘門】首次執行 — 請確認上述賽日資訊正確。")
        print("   確認後請執行以下指令啟動自動分析模式：")
        _next_cmd(target_dir)
        sys.exit(0)

    # --- EXECUTION STATE MACHINE ---
    if missing_raw:
        if not url:
            print("🚨 State 0: 原始數據缺失且無 URL（目錄模式），無法自動提取！")
            print("👉 請使用 Racenet URL 重新執行。")
            sys.exit(1)
        print("🚨 State 0: 發現原始數據缺失！自動呼叫 Extractor 進行修補...")
        trigger_extractor(url)
        print("✅ 數據修補完畢！")
        _next_cmd(target_dir)
        sys.exit(0)

    if chk_weather == "[ ]":
        if not url:
            print("⚙️ State 1: 缺少 MIP 且無 URL（目錄模式）。")
            print("👉 請手動建立 _Meeting_Intelligence_Package.md 或使用 URL 重新執行。")
            _next_cmd(target_dir)
            sys.exit(0)
        print("⚙️ State 1: 自動生成場地天氣情報 (_Meeting_Intelligence_Package.md)...")
        intel_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "generate_meeting_intel.py")
        if os.path.exists(intel_script):
            try:
                subprocess.run([
                    PYTHON, intel_script,
                    "--url", url,
                    "--target-dir", target_dir,
                    "--venue", venue,
                    "--date", formatted_date
                ], check=True)
                print("✅ Meeting Intelligence Package 自動生成完畢！")
                # Verify it was created
                if os.path.exists(weather_file):
                    chk_weather = "[x]"
                else:
                    print("❌ 生成失敗: _Meeting_Intelligence_Package.md 未被建立")
                    print("👉 請手動建立 _Meeting_Intelligence_Package.md")
                    notify_telegram("🚨 **AU State 1 Failed**\nMIP 自動生成失敗，請手動處理。")
                    _next_cmd(target_dir)
                    sys.exit(0)
            except subprocess.CalledProcessError as e:
                print(f"❌ MIP 生成腳本執行失敗: {e}")
                print("👉 Fallback: 請手動建立 _Meeting_Intelligence_Package.md")
                notify_telegram("🚨 **AU State 1 Failed**\nMIP 自動生成腳本執行失敗，請手動處理。")
                _next_cmd(target_dir)
                sys.exit(0)
        else:
            print(f"❌ 找不到 generate_meeting_intel.py: {intel_script}")
            print("👉 LLM Agent 請注意：請調查今日場地天氣與賽道偏差，並於此目錄建立 `_Meeting_Intelligence_Package.md`。")
            notify_telegram("🚨 **AU State 1 Action Required**\n缺少場地天氣與賽道偏差，請手動生成 `_Meeting_Intelligence_Package.md`。")
            _next_cmd(target_dir)
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
                cmd = [PYTHON, ".agents/scripts/inject_fact_anchors.py", rc, fg, "--max-display", "5", "--venue", venue]
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
        # I3: Auto-create Logic JSON skeleton if missing (HKJC parity)
        if not os.path.exists(json_file_b0):
            _rc_path = get_racecard_path(target_dir, r)
            _race_class, _race_dist = "[FILL]", "[FILL]"
            if _rc_path and os.path.exists(_rc_path):
                try:
                    with open(_rc_path, 'r', encoding='utf-8') as _rc_f:
                        _hdr = _rc_f.readline().strip()
                    _dm = re.search(r'[\u2014\u2013-]\s*(\d{3,5})m', _hdr)
                    _cm = re.search(r'\d+m\s*\|\s*([^|$]+)', _hdr)
                    if _dm: _race_dist = f"{_dm.group(1)}m"
                    if _cm: _race_class = _cm.group(1).strip()
                except Exception:
                    pass
            _init_json = {
                "race_analysis": {
                    "race_number": r, "race_class": _race_class, "distance": _race_dist,
                    "speed_map": {
                        "expected_pace": "[FILL]", "leaders": [], "on_pace": [],
                        "mid_pack": [], "closers": [],
                        "track_bias": "[FILL]", "tactical_nodes": "[FILL]", "collapse_point": "[FILL]"
                    }
                },
                "horses": {}
            }
            with open(json_file_b0, 'w', encoding='utf-8') as _wf:
                json.dump(_init_json, _wf, ensure_ascii=False, indent=2)
            print(f"   \u2705 \u5df2\u81ea\u52d5\u5efa\u7acb `Race_{r}_Logic.json` \u9aa8\u67b6 ({_race_class} / {_race_dist})")
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
                    print(f"")
                    print(f"📖 參考資源：")
                    print(f"   → 情報增強: .agents/skills/shared_instincts/intelligence_checklist.md (Tier 2 歷史場地 Pattern)")
                    print(f"\n缺失欄位: {missing_sm}")
                    print("生成完畢後，請重新執行本 Orchestrator！")
                    notify_telegram(f"📍 **AU Race {r} Action Required**\nBatch 0 步速瀑布 (Speed Map) 尚未填寫。")
                    _next_cmd(target_dir)
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
                with open(json_file, 'r', encoding='utf-8') as _jf:
                    logic_data = json.load(_jf)
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
                        [PYTHON, skeleton_script, facts_file, str(r), str(target_horse)],
                        capture_output=True, text=True
                    )
                    print(skel_result.stdout)
                    if skel_result.returncode != 0:
                        print(f"❌ Skeleton failed: {skel_result.stderr}")
                        sys.exit(1)
                    with open(json_file, 'r', encoding='utf-8') as _jf:
                        logic_data = json.load(_jf)
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
                
                # Determine venue-specific track module (#11)
                _dir_parts = os.path.basename(target_dir).split(" ", 1)
                _au_venue = _dir_parts[1].lower().replace(" ", "_") if len(_dir_parts) > 1 else ""
                _au_track_file = f"04b_track_{_au_venue}.md"
                _au_track_path = os.path.join(".agents", "skills", "au_racing", "au_horse_analyst", "resources", _au_track_file)
                _au_track_exists = os.path.exists(os.path.join(target_dir, "..", "..", "..", _au_track_path)) or os.path.exists(_au_track_path)
                
                # Inject speed map conclusion for analyst context
                _sm_data = logic_data.get('race_analysis', {}).get('speed_map', {})
                _sm_pace = _sm_data.get('expected_pace', _sm_data.get('predicted_pace', 'N/A'))
                _sm_bias = _sm_data.get('track_bias', 'N/A')
                
                with open(runtime_ctx_path, "w", encoding="utf-8") as _ctx_f:
                    _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                    _ctx_f.write(f"📖 分析引擎: .agents/skills/au_racing/au_horse_analyst/SKILL.md\n")
                    _ctx_f.write(f"📖 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md\n")
                    _ctx_f.write(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md\n")
                    if _au_track_exists:
                        _ctx_f.write(f"📖 場地模組: {_au_track_path}\n")
                    _ctx_f.write(f"📖 合規參考: .agents/skills/au_racing/au_compliance/SKILL.md\n")
                    _ctx_f.write(f"📍 步速判定: {_sm_pace} | 跑道偏差: {_sm_bias}\n\n")
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
                print(f"")
                print(f"📖 分析引擎（已注入 Active_Horse_Context.md）：")
                print(f"   → 🧠 SKILL.md: .agents/skills/au_racing/au_horse_analyst/SKILL.md")
                print(f"   → 📊 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md")
                print(f"   → 🔗 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md")
                if _au_track_exists:
                    print(f"   → 🏟️ 場地模組: {_au_track_path}")
                print(f"   → ✅ 合規標準: .agents/skills/au_racing/au_compliance/SKILL.md")
                print(f"   → 📍 步速: {_sm_pace} | 偏差: {_sm_bias}")
                print(f"")
                print(f"🔴 Firewall: no data tampering, single horse only, no .py scripts!")
                print(f"")
                notify_telegram(f"🚨 **AU Race {r} Action Required**\n請填寫 Horse #{target_horse} '{horse_name}' 嘅獨立分析。")
                _next_cmd(target_dir)
                sys.exit(0)
                
            # ─── Verdict Check (must be filled before compilation) ───
            verdict_data = logic_data.get('race_analysis', {}).get('verdict')
            if not verdict_data:
                print(f"\n🚨 State 3 行動要求 (Race {r} 最終判定未完成):")
                print(f"👉 LLM Agent 請注意：所有馬匹已完成！請呼叫數學排序模組或自行比對分數，")
                print(f"然後在 `{os.path.basename(json_file)}` 填寫 `verdict` 模塊。")
                print(f"📖 Verdict 前必讀: .agents/skills/au_racing/au_horse_analyst/resources/06_templates_rules.md")
                notify_telegram(f"🚨 **AU Race {r} Verdict Needed**\n請比對分析分數，填寫最終 verdict 判定。")
                _next_cmd(target_dir)
                sys.exit(0)
            
            # If ALL batches are done, compile and QA
            # But wait, did we fail Strike 3?
            if strikes.get(str(r), 0) >= 3:
                print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗 (Strike-3 Fallback)。")
                print(f"系統已中斷自動化，請人類直接打開 `{os.path.basename(json_file)}` 修正長度與邏輯！")
                print(f"修正後執行: {PYTHON} .agents/scripts/completion_gate_v2.py \"{an_file}\" --domain au")
                notify_telegram(f"❌ **AU Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，恐為極端異常賽事，請人工介入修正 JSON！")
                _next_cmd(target_dir)
                sys.exit(1)
                
            print(f"⚙️ 發現 Race {r} JSON 所有馬匹已聚齊！正在編譯...")
            compile_cmd = [PYTHON, ".agents/skills/au_racing/au_wong_choi/scripts/compile_analysis_template.py", facts_file, json_file, "--output", an_file]
            res = subprocess.run(compile_cmd)
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(json_file)}。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                _next_cmd(target_dir)
                sys.exit(1)
            
            # 4.5 Monte Carlo Simulation (AU two-step pipeline)
            print(f"🎲 Running AU Monte Carlo simulation for Race {r}...")
            mc_au_script = ".agents/skills/au_racing/au_wong_choi/scripts/monte_carlo_au.py"
            mc_inject_script = ".agents/scripts/inject_mc_au.py"
            mc_json_out = os.path.join(target_dir, f"Race_{r}_MC_Results.json")

            if os.path.exists(mc_au_script):
                # Step 1: Generate MC JSON
                mc_res = subprocess.run(
                    [PYTHON, mc_au_script, json_file, facts_file, "--output", mc_json_out],
                    capture_output=True, text=True
                )
                if mc_res.returncode == 0:
                    print(f"✅ MC JSON generated → Race_{r}_MC_Results.json")
                    # Step 2: Inject MC table into Analysis.md
                    if os.path.exists(mc_inject_script) and os.path.exists(mc_json_out):
                        inject_res = subprocess.run(
                            [PYTHON, mc_inject_script, target_dir, "--races", str(r)],
                            capture_output=True, text=True
                        )
                        if inject_res.returncode == 0:
                            print(f"✅ MC table injected into Race {r} Analysis.md")
                        else:
                            print(f"⚠️ MC inject failed (non-blocking): {inject_res.stderr[:200]}")
                    else:
                        print(f"⚠️ inject_mc_au.py not found — skipping injection")
                else:
                    print(f"⚠️ MC simulation failed (non-blocking): {mc_res.stderr[:200]}")
            else:
                print(f"⚠️ monte_carlo_au.py not found: {mc_au_script}")
            
            # QA
            print(f"🛡️ 正在進行 Batch QA (completion_gate_v2.py)...")
            qa_res = subprocess.run([PYTHON, ".agents/scripts/completion_gate_v2.py", an_file, "--domain", "au"])
            if qa_res.returncode != 0:
                print(f"\n❌ Race {r} QA 驗證失敗！")
                print(f"請重新修改 `{os.path.basename(json_file)}`，補齊 `_reasoning` 與字數。修改後重跑 Orchestrator。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                _next_cmd(target_dir)
                sys.exit(1)
            else:
                print(f"✅ Race {r} Batch QA 通過！")
                if str(r) in strikes:
                    del strikes[str(r)]
                    save_strikes()
                # Continue loop to next race

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！正在產製 Excel 報告...")
    subprocess.run([PYTHON, ".agents/skills/au_racing/au_wong_choi/scripts/generate_reports.py", target_dir])
    subprocess.run([PYTHON, ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "au"])
    
    print("☁️ State 5: 準備推送 Dashboard 至 Cloudflare...")
    push_script = "Horse Racing Dashboard/deploy.sh"
    if os.path.exists(push_script) and shutil.which("bash"):
        subprocess.run(["bash", push_script])
        print("✅ 雲端同步完成！")
    elif os.path.exists(push_script):
        print("⚠️ bash not found (Windows), skipping dashboard deploy. Run manually.")
    else:
        print("👉 (未偵測到 Dashboard 自動推送腳本，請手動發佈)。")
        
    print("\n🎉 [SUCCESS] AU Wong Choi Pipeline 任務全數擊破！")
    notify_telegram("🎉 **AU Wong Choi 任務完成**\n所有分析已順利通過 QA 及編譯！")
    
if __name__ == "__main__":
    main()
