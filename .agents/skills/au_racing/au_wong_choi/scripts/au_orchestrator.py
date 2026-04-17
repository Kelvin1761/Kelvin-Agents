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

# Import rating engine for auto-verdict computation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts')))
from rating_engine_v2 import parse_matrix_scores, compute_base_grade, apply_fine_tune, grade_sort_index

AU_MATRIX_SCHEMA = {
    "狀態與穩定性": "core", "段速與引擎": "core",
    "EEM與形勢": "semi", "騎練訊號": "semi",
    "級數與負重": "aux", "場地適性": "aux",
    "賽績線": "aux", "裝備與距離": "aux",
}

def auto_compute_verdict(logic_data, facts_file):
    """Auto-compute verdict Top 4 from matrix grades. Eliminates LLM verdict stop."""
    horses = logic_data.get('horses', {})
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    
    # Compute grade for each horse
    graded = []
    for h_num, h_obj in horses.items():
        m_data = h_obj.get('matrix', {})
        core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(m_data, AU_MATRIX_SCHEMA)
        b_grade = compute_base_grade(core_pass, semi_pass, aux_pass, core_fail, total_fail)
        ft = h_obj.get('fine_tune', {})
        ft_dir = ft.get('direction', '無') if isinstance(ft, dict) else str(ft)
        f_grade = apply_fine_tune(b_grade, ft_dir)
        grade_i = grade_sort_index(f_grade)
        graded.append((h_num, h_obj.get('horse_name', ''), f_grade, grade_i))
    
    # Sort by grade (lower index = better)
    graded.sort(key=lambda x: (x[3], int(x[0]) if x[0].isdigit() else 999))
    top4 = graded[:4]
    
    # Auto pace_flip_insurance from speed_map
    leaders = speed_map.get('leaders', [])
    closers = speed_map.get('closers', [])
    leader_names = {h_num: h_obj.get('horse_name', '') for h_num, h_obj in horses.items() if str(h_num) in [str(x) for x in leaders]}
    closer_names = {h_num: h_obj.get('horse_name', '') for h_num, h_obj in horses.items() if str(h_num) in [str(x) for x in closers]}
    
    faster_benefit = ''
    faster_hurt = ''
    slower_benefit = ''
    slower_hurt = ''
    if closer_names:
        best_closer = list(closer_names.items())[0]
        faster_benefit = f"{best_closer[0]}號 {best_closer[1]}"
    if leader_names:
        best_leader = list(leader_names.items())[0]
        slower_benefit = f"{best_leader[0]}號 {best_leader[1]}"
        faster_hurt = f"{best_leader[0]}號 {best_leader[1]}"
    if closer_names:
        worst_closer = list(closer_names.items())[-1]
        slower_hurt = f"{worst_closer[0]}號 {worst_closer[1]}"
    
    verdict = {
        'top4': [
            {'horse_number': str(h[0]), 'horse_name': h[1], 'grade': h[2]}
            for h in top4
        ],
        'confidence': '[AUTO]',
        'pace_flip_insurance': {
            'if_faster': {'benefit': faster_benefit or '[AUTO]', 'hurt': faster_hurt or '[AUTO]'},
            'if_slower': {'benefit': slower_benefit or '[AUTO]', 'hurt': slower_hurt or '[AUTO]'}
        }
    }
    
    logic_data.setdefault('race_analysis', {})['verdict'] = verdict
    return verdict

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


# ═══════════════════════════════════════════════════════════════
# V10 Helper Functions: Firewall Validation + File-Watch Loop
# ═══════════════════════════════════════════════════════════════

def extract_horse_facts_block(target_horse, facts_content):
    """Extract a single horse's facts block from AU Facts.md."""
    for marker_pat in [rf'\[#{target_horse}\]', rf'### 馬號 {target_horse} — ', rf'### 馬匹 #{target_horse} ']:
        h_match = re.search(marker_pat, facts_content)
        if h_match:
            h_start = h_match.start()
            h_next = re.search(r'(?:\[#\d+\]|### 馬號 \d+ — |### 馬匹 #\d+)', facts_content[h_match.end():])
            h_end = h_match.end() + h_next.start() if h_next else len(facts_content)
            return facts_content[h_start:h_end]
    return ""


def extract_fact_anchors(horse_block):
    """Extract key factual data points from a horse's Facts block for work card generation."""
    anchors = {}

    # Horse name, barrier, jockey, trainer
    m = re.search(r'### 馬匹 #(\d+)\s+(.+?)\s+\(檔位\s*(\d+)\)\s*\|\s*騎師:\s*(.+?)\s*\|\s*練馬師:\s*(.+?)$',
                  horse_block, re.MULTILINE)
    if m:
        anchors['name'] = m.group(2).strip()
        anchors['barrier'] = m.group(3)
        anchors['jockey'] = m.group(4).strip()
        anchors['trainer'] = m.group(5).strip()
    else:
        anchors['name'] = '未知'
        anchors['barrier'] = '?'
        anchors['jockey'] = '?'
        anchors['trainer'] = '?'

    # Recent form sequence
    m = re.search(r'近績序列解讀:\s*`([^`]+)`', horse_block)
    anchors['recent_form'] = m.group(1) if m else '無'

    # Career starts (official races)
    m = re.search(r'生涯:\s*(\d+):', horse_block)
    anchors['career_starts'] = m.group(1) if m else '0'

    # Fitness arc derivation
    starts = int(anchors['career_starts'])
    if starts == 0:
        anchors['fitness_arc'] = '初出馬（零正式賽事經驗）'
    elif starts == 1:
        anchors['fitness_arc'] = '二出'
    elif starts == 2:
        anchors['fitness_arc'] = 'Third-up（第三仗）'
    elif starts <= 5:
        anchors['fitness_arc'] = f'輕度備戰（{starts}仗）'
    else:
        anchors['fitness_arc'] = f'Deep Prep（{starts}仗）'

    # EEM drain
    m = re.search(r'加權累積消耗:\s*([^→]+?)→', horse_block)
    anchors['eem_drain'] = m.group(1).strip() if m else '無數據'

    # Last run style
    m = re.search(r'EEM 跑法.*?\|\s*(.+?)\s*\|', horse_block)
    anchors['last_run_style'] = m.group(1).strip() if m else '無數據'

    # Formline strength
    m = re.search(r'\*\*綜合評估:\*\*\s*(.+?)(?:\n|$)', horse_block)
    anchors['formline_strength'] = m.group(1).strip() if m else '無資料'

    # Track records
    m = re.search(r'好地:\s*([^\|]+)', horse_block)
    anchors['good_record'] = m.group(1).strip() if m else '無'
    m = re.search(r'軟地:\s*([^\|]+)', horse_block)
    anchors['soft_record'] = m.group(1).strip() if m else '無'
    m = re.search(r'同場:\s*([^\|]+)', horse_block)
    anchors['course_record'] = m.group(1).strip() if m else '無'

    # Distance record for today's distance
    m = re.search(r'今仗\s*\d+m.*?:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['distance_record'] = m.group(1).strip() if m else '無紀錄'

    # Best distance
    m = re.search(r'⭐最佳', horse_block)
    if m:
        dist_m = re.search(r'([\d≤]+m?).*?⭐最佳', horse_block)
        anchors['best_distance'] = dist_m.group(1) if dist_m else '未知'
    else:
        anchors['best_distance'] = '數據不足'

    # Engine type
    m = re.search(r'引擎:\s*(.+?)\s*\|', horse_block)
    anchors['engine_type'] = m.group(1).strip() if m else '未知'

    # PI trend
    m = re.search(r'PI.*?趨勢:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['pi_trend'] = m.group(1).strip() if m else '數據不足'

    # L400 trend
    m = re.search(r'L400.*?趨勢:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['l400_trend'] = m.group(1).strip() if m else '數據不足'

    # Class movement (from table)
    class_moves = re.findall(r'[↑↓].*?(?:升班|降班)', horse_block)
    anchors['class_move'] = class_moves[0] if class_moves else '無明顯升降'

    # Last run remark
    remarks = re.findall(r'\|\s*[^|]*(?:Led|Settled|Held|Keen|Pushed|Sat|Box seat)[^|]*\|', horse_block)
    anchors['last_run_remark'] = remarks[0].strip('| ') if remarks else '無'

    return anchors


def generate_work_card(horse_num, facts_content, logic_data, runtime_dir,
                       sm_pace, sm_bias, horse_idx=0, total_horses=1):
    """Generate a guided analysis work card for a SINGLE horse.

    Instead of dumping raw data and expecting the LLM to figure out what to do,
    this creates structured analytical questions with the horse's actual data
    embedded, forcing the LLM to produce data-specific reasoning.
    """
    horse_block = extract_horse_facts_block(horse_num, facts_content)
    if not horse_block:
        return None

    anchors = extract_fact_anchors(horse_block)
    race_class = logic_data.get('race_analysis', {}).get('race_class', '?')
    distance = logic_data.get('race_analysis', {}).get('distance', '?')

    card = []
    card.append(f"# 🐎 分析工作卡 [{horse_idx+1}/{total_horses}] — Horse #{horse_num} {anchors['name']}")
    card.append(f"**檔位: {anchors['barrier']} | 騎師: {anchors['jockey']} | 練馬師: {anchors['trainer']}**")
    card.append(f"📍 步速: {sm_pace} | 偏差: {sm_bias} | 班次: {race_class} | 距離: {distance}")
    card.append(f"📖 評級矩陣規則: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md")
    card.append(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md")
    card.append("")
    card.append("---")
    card.append("## ⚠️ 指引")
    card.append("- 每個維度必須根據下方列出嘅**具體數據**作出判斷")
    card.append("- 分數只可以係 ✅✅ / ✅ / ➖ / ❌ / ❌❌")
    card.append("- 理據必須引用具體數據（日期、場地、名次、PI 數值等）")
    card.append("- 唔可以寫「一般」、「尚可」、「配搭無特別異常」等模板化語句")
    card.append("---")
    card.append("")

    # ── Dimension 1: 狀態與穩定性 [核心] ──
    card.append("## 1️⃣ 狀態與穩定性 [核心維度]")
    card.append(f"- 正式賽事場次: **{anchors['career_starts']}**")
    card.append(f"- 近績序列: `{anchors['recent_form']}`")
    card.append(f"- 狀態週期: **{anchors['fitness_arc']}**")
    card.append(f"- 上仗備註: {anchors['last_run_remark']}")
    card.append("👉 **你嘅判斷:** ✅✅/✅/➖/❌/❌❌？寫 1-2 句引用上述數據嘅理據。")
    card.append("")

    # ── Dimension 2: 段速與引擎 [核心] ──
    card.append("## 2️⃣ 段速與引擎 [核心維度]")
    card.append(f"- PI 趨勢: {anchors.get('pi_trend', '數據不足')}")
    card.append(f"- L400 趨勢: {anchors.get('l400_trend', '數據不足')}")
    card.append(f"- 引擎類型: {anchors.get('engine_type', '未知')}")
    card.append(f"- 今仗步速預測: {sm_pace}")
    card.append("👉 **你嘅判斷:** 段速質素如何？引擎同今仗步速配唔配？")
    card.append("")

    # ── Dimension 3: EEM與形勢 [半核心] ──
    card.append("## 3️⃣ EEM與形勢 [半核心]")
    card.append(f"- 累積消耗: {anchors.get('eem_drain', '無數據')}")
    card.append(f"- 上仗跑法: {anchors.get('last_run_style', '無數據')}")
    card.append(f"- 今仗檔位: {anchors.get('barrier', '?')}")
    card.append(f"- 跑道偏差: {sm_bias}")
    card.append("👉 **你嘅判斷:** 消耗水平 + 檔位形勢對呢匹馬有利定不利？")
    card.append("")

    # ── Dimension 4: 騎練訊號 [半核心] ──
    card.append("## 4️⃣ 騎練訊號 [半核心]")
    card.append(f"- 騎師: {anchors.get('jockey', '?')}")
    card.append(f"- 練馬師: {anchors.get('trainer', '?')}")
    card.append("👉 **你嘅判斷:** 有冇出擊訊號？騎練組合有冇特殊意義？冇資料就寫 ➖。")
    card.append("")

    # ── Dimension 5: 級數與負重 [輔助] ──
    card.append("## 5️⃣ 級數與負重 [輔助]")
    card.append(f"- 今仗班次: {race_class}")
    card.append(f"- 班次變動: {anchors.get('class_move', '無明顯升降')}")
    card.append("👉 **你嘅判斷:** 班次有冇優勢？有冇超班降班？")
    card.append("")

    # ── Dimension 6: 場地適性 [輔助] ──
    card.append("## 6️⃣ 場地適性 [輔助]")
    card.append(f"- 好地紀錄: {anchors.get('good_record', '無')}")
    card.append(f"- 軟地紀錄: {anchors.get('soft_record', '無')}")
    card.append(f"- 同場紀錄: {anchors.get('course_record', '無')}")
    card.append("👉 **你嘅判斷:** 對今日場地有冇經驗？有冇贏過？")
    card.append("")

    # ── Dimension 7: 賽績線 [輔助] ──
    card.append("## 7️⃣ 賽績線 [輔助]")
    card.append(f"- 賽績線強度: {anchors.get('formline_strength', '無資料')}")
    card.append("👉 **你嘅判斷:** 對手後續表現強唔強？強組/弱組？")
    card.append("")

    # ── Dimension 8: 裝備與距離 [輔助] ──
    card.append("## 8️⃣ 裝備與距離 [輔助]")
    card.append(f"- 今仗距離: {distance}")
    card.append(f"- 距離紀錄: {anchors.get('distance_record', '無紀錄')}")
    card.append(f"- 最佳距離: {anchors.get('best_distance', '數據不足')}")
    card.append("👉 **你嘅判斷:** 路程啱唔啱？裝備有冇變？")
    card.append("")

    # ── Final synthesis ──
    card.append("---")
    card.append("## 📋 綜合部分（填完 8 個維度後）")
    card.append("- **core_logic**: 串連所有維度寫成連貫分析（最少 100 字，必須引用具體賽事/數據）")
    card.append("- **advantages**: 2-3 個主要優勢")
    card.append("- **disadvantages**: 2-3 個致命風險")
    card.append("- **fine_tune**: 方向(+/-/無) + trigger_code（從預定義列表揀）")
    card.append("")
    card.append("---")
    card.append("## 📄 原始賽績數據（嚴禁修改）")
    card.append(horse_block)

    # Write to file
    card_path = os.path.join(runtime_dir, f"Horse_{horse_num}_WorkCard.md")
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(card))

    return card_path


def watch_single_horse(json_file, horse_num, validate_fn, all_horses,
                       poll_interval=3, timeout_minutes=10):
    """Watch for a SINGLE horse to be filled and validated.
    Returns the horse entry dict on success, None on timeout.
    
    Key difference from watch_and_validate: only monitors one horse,
    shorter timeout, and returns immediately when that horse passes.
    """
    hkey = str(horse_num)
    last_mtime = os.path.getmtime(json_file)
    own_write_mtime = 0
    start_time = time.time()
    last_heartbeat = time.time()

    # Pre-check: maybe already filled
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            init_data = json.load(f)
        h_entry = init_data.get('horses', {}).get(hkey, {})
        if h_entry:
            h_check = json.dumps(
                {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                ensure_ascii=False
            )
            if '[FILL]' not in h_check:
                errors = validate_fn(horse_num, h_entry, init_data.get('horses', {}), all_horses, json_file)
                if not errors:
                    return h_entry
    except Exception:
        pass

    print(f"\n👀 Python 正在監控 Horse #{horse_num}... (每 {poll_interval} 秒 | 超時 {timeout_minutes} 分鐘)")

    try:
        while True:
            time.sleep(poll_interval)

            elapsed = time.time() - start_time
            if elapsed > timeout_minutes * 60:
                print(f"\n⏰ Horse #{horse_num} 監控超時 ({timeout_minutes} 分鐘)！")
                return None

            # Heartbeat every 60s
            if time.time() - last_heartbeat > 60:
                mins = int(elapsed / 60)
                print(f"   💓 [{mins}m] 仍在等待 Horse #{horse_num}...")
                last_heartbeat = time.time()

            try:
                current_mtime = os.path.getmtime(json_file)
            except OSError:
                continue

            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                continue

            time.sleep(0.5)  # Debounce
            last_mtime = current_mtime

            # Read JSON with retry
            logic_data = None
            for attempt in range(3):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        logic_data = json.load(f)
                    break
                except (json.JSONDecodeError, OSError):
                    if attempt < 2:
                        time.sleep(0.5)

            if logic_data is None:
                continue

            horses_dict = logic_data.get('horses', {})
            h_entry = horses_dict.get(hkey, {})
            if not h_entry:
                continue

            h_check = json.dumps(
                {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                ensure_ascii=False
            )
            if '[FILL]' in h_check:
                continue

            # Validate
            errors = validate_fn(horse_num, h_entry, horses_dict, all_horses, json_file)
            if errors:
                name = h_entry.get('horse_name', '')
                print(f"\n🚨 Horse #{horse_num} ({name}) Firewall 失敗!")
                for e in errors:
                    print(f"   ❌ {e}")
                print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
                # Reset core_logic to force redo
                h_entry['core_logic'] = '[FILL]'
                with open(json_file, 'w', encoding='utf-8') as wf:
                    json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                own_write_mtime = os.path.getmtime(json_file)
                last_mtime = own_write_mtime
            else:
                return h_entry

    except KeyboardInterrupt:
        print(f"\n⚠️ 用戶中斷！Horse #{horse_num} 未完成。")
        return None


def print_analysis_summary(horse_entry, horse_num):
    """Print a quality summary after a horse passes validation, providing positive feedback."""
    matrix = horse_entry.get('matrix', {})
    scores = []
    for dim in ['狀態與穩定性', '段速與引擎', 'EEM與形勢', '騎練訊號',
                '級數與負重', '場地適性', '賽績線', '裝備與距離']:
        data = matrix.get(dim, {})
        score = data.get('score', '?') if isinstance(data, dict) else str(data)
        # Compact display
        short_dim = dim[:4]
        scores.append(f"{short_dim}:{score}")

    print(f"   📊 矩陣: {' | '.join(scores)}")

    core_logic = horse_entry.get('core_logic', '')
    if core_logic and len(core_logic) > 20:
        print(f"   💡 邏輯: {core_logic[:80]}...")
        print(f"   📏 長度: {len(core_logic)} 字")

    # Quality check: score diversity
    all_scores = [d.get('score', '') for d in matrix.values() if isinstance(d, dict)]
    unique_scores = set(all_scores)
    if len(unique_scores) <= 2 and len(all_scores) >= 6:
        print(f"   ⚠️ 品質警告: 分數差異度低（只有 {len(unique_scores)} 種分數）— 可能需要重新審視")
    elif len(unique_scores) >= 4:
        print(f"   ✨ 分數差異度良好 ({len(unique_scores)} 種不同分數)")


def validate_au_firewalls(h, h_entry, horses_dict, all_horses, json_file):
    """AU-specific per-horse firewall validation. Returns list of error strings.
    Extracted from V9.3 inline code — logic is identical.
    """
    errors = []
    horse_name = h_entry.get('horse_name', '')
    core_logic = h_entry.get('core_logic', '')
    locked_nonce = h_entry.get('_validation_nonce', '')
    
    # WALL-008: Nonce validation
    if not locked_nonce:
        errors.append("WALL-008: Missing _validation_nonce")
    
    # WALL-009: base_rating/final_rating are now [AUTO] — computed by Python
    # No LLM validation needed; compile_analysis_template.py handles this
    
    # WALL-010: Pre-Analysis Checklist Consistency Check (V9.5)
    checklist = h_entry.get('pre_analysis_checklist', {})
    if checklist:
        ev_src = checklist.get('primary_evidence_source', '')
        trial_pct = checklist.get('trial_influence_pct', 0)
        grade_wo = checklist.get('grade_without_trial', '')
        trial_flag = h_entry.get('trial_illusion', False)
        
        if ev_src == 'trial_only' and not trial_flag:
            errors.append(
                f"WALL-010: 你自己答咗 primary_evidence_source='trial_only'，"
                f"但 trial_illusion=false。呢個前後矛盾！"
                f"請將 trial_illusion 設為 true（封頂 B+）。"
            )
        if grade_wo == 'no_data' and not trial_flag:
            errors.append(
                f"WALL-010: 你答咗 grade_without_trial='no_data'（冇試閘就冇數據），"
                f"但 trial_illusion=false。矛盾！請設 trial_illusion=true。"
            )
        try:
            if isinstance(trial_pct, str):
                trial_pct = int(trial_pct)
            if trial_pct > 50 and not trial_flag:
                errors.append(
                    f"WALL-010: trial_influence_pct={trial_pct}%（>50%），"
                    f"表示分析過度依賴試閘。請重新審視 trial_illusion 是否應為 true。"
                )
        except (ValueError, TypeError):
            pass
    
    # WALL-011: Fine-Tune Trigger Code Validation (V9.5)
    VALID_UP_CODES = {
        'PACE_FIT', 'JOCKEY_FIT', 'WEIGHT_SYNERGY', 'GEAR_POSITIVE',
        'TRAINER_TRACK', 'MOMENTUM_3WIN', 'MOMENTUM_2WIN',
        'WEIGHT_EXTREME', 'MID_CLASS_LIGHT', 'SOFT_LIGHT', 'LAST_WIN', '無'
    }
    VALID_DOWN_CODES = {
        'FATAL_DRAW', 'INSIDE_TRAP', 'INTERSTATE', 'DISTANCE_JUMP',
        'WIN_REGRESSION', 'TOP_WEIGHT', 'PACE_AGAINST', 'JOCKEY_CLASH',
        'PACE_BURN', 'CONTRADICTION', '無'
    }
    ft = h_entry.get('fine_tune', {})
    ft_dir = ft.get('direction', '無')
    ft_code = ft.get('trigger_code', '無')
    
    if ft_code and ft_code not in ('[FILL: 代碼或「無」]', ''):
        all_valid = VALID_UP_CODES | VALID_DOWN_CODES
        if ft_code not in all_valid:
            errors.append(
                f"WALL-011: trigger_code '{ft_code}' 唔係合法代碼！"
                f"請從骨架註釋嘅預定義列表揀選。"
            )
        if ft_dir == '+' and ft_code in VALID_DOWN_CODES and ft_code != '無':
            errors.append(
                f"WALL-011: direction='+' 但 trigger_code='{ft_code}' 係降級代碼，矛盾！"
            )
        if ft_dir == '-' and ft_code in VALID_UP_CODES and ft_code != '無':
            errors.append(
                f"WALL-011: direction='-' 但 trigger_code='{ft_code}' 係升級代碼，矛盾！"
            )
    
    # WALL-012: Direction/Code Coupling (V9.5)
    if isinstance(ft, dict):
        ft_dir_012 = ft.get('direction', '無')
        ft_code_012 = ft.get('trigger_code', '無')
        
        if ft_dir_012 in ('+', '-') and ft_code_012 == '無':
            errors.append(
                f"WALL-012: direction='{ft_dir_012}' 但 trigger_code='無'。"
                f"如果要微調，必須從預定義列表揀選一個合法代碼。"
            )
        if ft_dir_012 == '無' and ft_code_012 != '無' and ft_code_012 not in ('[FILL: 代碼或「無」]', ''):
            errors.append(
                f"WALL-012: direction='無' 但 trigger_code='{ft_code_012}'。"
                f"如果無微調，trigger_code 都應該係「無」。"
            )
    
    # WALL-013: Anti-Double-Counting Warning (WARNING only, not error)
    DOUBLE_COUNT_MAP = {
        'GEAR_POSITIVE': '裝備與距離',
        'JOCKEY_FIT': '騎練訊號',
        'WEIGHT_SYNERGY': '級數與負重',
        'WEIGHT_EXTREME': '級數與負重',
        'MID_CLASS_LIGHT': '級數與負重',
        'MOMENTUM_3WIN': '狀態與穩定性',
        'MOMENTUM_2WIN': '狀態與穩定性',
        'LAST_WIN': '狀態與穩定性',
    }
    if isinstance(ft, dict):
        ft_code_013 = ft.get('trigger_code', '無')
        if ft_code_013 in DOUBLE_COUNT_MAP:
            mapped_dim = DOUBLE_COUNT_MAP[ft_code_013]
            matrix = h_entry.get('matrix', {})
            dim_data = matrix.get(mapped_dim, {})
            dim_score = dim_data.get('score', '➖') if isinstance(dim_data, dict) else str(dim_data)
            if '✅' in dim_score:
                print(
                    f"   ⚠️ WALL-013 雙重計算警告: trigger_code='{ft_code_013}' "
                    f"對應嘅矩陣維度「{mapped_dim}」已經係 {dim_score}。"
                    f"請確認微調理由唔係重複計算已有嘅 ✅。"
                )

    # WALL-016: Core Logic Fact Citation Check (V2.2)
    if core_logic and '[FILL]' not in core_logic and not errors:
        has_specific_date = bool(re.search(r'20\d{2}[-/]\d{1,2}[-/]\d{1,2}', core_logic))
        has_specific_track = bool(re.search(
            r'(?:Cranbourne|Flemington|Caulfield|Moonee Valley|Sandown|Pakenham|'
            r'Bendigo|Ballarat|Geelong|Mornington|Sale|Warrnambool|Echuca|'
            r'Randwick|Rosehill|Canterbury|Kensington|Newcastle)',
            core_logic
        ))
        has_pi_value = bool(re.search(r'PI\s*[=:：]?\s*[+\-]?\d', core_logic))
        has_numeric_evidence = bool(re.search(r'\d{2,}m|\d+(?:th|st|nd|rd)\b|\d+/\d+', core_logic))
        
        fact_score = sum([has_specific_date, has_specific_track, has_pi_value, has_numeric_evidence])
        if fact_score == 0:
            errors.append(
                f"WALL-016: core_logic 缺乏具體事實引用！"
                f"真正嘅分析應該包含至少一個：具體日期、場地名、PI 數值、或距離/名次數據。"
                f"當前文本疑似由模板腳本生成。"
            )

    return errors


def validate_au_global_firewalls(horses_dict, all_horses, json_file):
    """AU global firewall checks (WALL-015 Batch Injection Detection). Returns list of error strings."""
    errors = []
    try:
        horses_with_logic = sum(
            1 for hk, hv in horses_dict.items()
            if hv.get('core_logic') and '[FILL]' not in str(hv.get('core_logic', ''))
        )
        if horses_with_logic >= len(all_horses) and len(all_horses) >= 5:
            nonces = [horses_dict.get(str(hh), {}).get('_validation_nonce', '') for hh in all_horses]
            unique_nonces = set(n for n in nonces if n)
            if len(unique_nonces) <= 2 and len(nonces) >= 5:
                errors.append(
                    f"WALL-015: 全場 {len(all_horses)} 匹馬只用咗 {len(unique_nonces)} 個 NONCE！"
                    f"正常流程每匹馬應有獨立 NONCE。疑似腳本批量注入。"
                )
    except Exception:
        pass
    return errors


def watch_and_validate(json_file, all_horses, validate_fn, poll_interval=3,
                       timeout_minutes=30, heartbeat_interval=60, stale_minutes=5):
    """V10 File-Watch Loop with production hardening:
    - Timeout: exits after timeout_minutes if not all horses validated
    - Heartbeat: prints alive status every heartbeat_interval seconds
    - Stale detection: warns if no file changes for stale_minutes
    - Debounce: waits 0.5s after mtime change to avoid reading partial writes
    - JSON retry: retries reads up to 3 times on parse failure
    - KeyboardInterrupt: clean exit on Ctrl+C
    Returns final logic_data when all horses pass, or None on timeout/interrupt.
    """
    last_mtime = os.path.getmtime(json_file)
    validated_horses = set()
    own_write_mtime = 0
    start_time = time.time()
    last_change_time = time.time()
    last_heartbeat = time.time()
    stale_warned = False
    
    # Pre-scan for already validated horses
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            init_data = json.load(f)
        init_horses = init_data.get('horses', {})
        for h in all_horses:
            hkey = str(h)
            h_entry = init_horses.get(hkey, {})
            if not h_entry:
                continue
            h_check = json.dumps(
                {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                ensure_ascii=False
            )
            if '[FILL]' in h_check:
                continue
            errors = validate_fn(h, h_entry, init_horses, all_horses, json_file)
            if not errors:
                validated_horses.add(hkey)
    except Exception:
        pass
    
    if validated_horses:
        print(f"   ✅ {len(validated_horses)}/{len(all_horses)} 匹馬已預先驗證通過")
    
    if len(validated_horses) == len(all_horses):
        with open(json_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    remaining = len(all_horses) - len(validated_horses)
    print(f"\n👀 Python 正在監控 {os.path.basename(json_file)}... (每 {poll_interval} 秒 | 超時 {timeout_minutes} 分鐘)")
    print(f"   等待 LLM 填寫餘下 {remaining} 匹馬")
    
    try:
        while True:
            time.sleep(poll_interval)
            
            elapsed = time.time() - start_time
            
            # Timeout check
            if elapsed > timeout_minutes * 60:
                print(f"\n⏰ Watch loop 超時 ({timeout_minutes} 分鐘)！")
                print(f"   已驗證: {len(validated_horses)}/{len(all_horses)}")
                print(f"   請確認 LLM 是否仍在運作，然後重跑 Orchestrator。")
                return None
            
            # Heartbeat
            if time.time() - last_heartbeat > heartbeat_interval:
                mins = int(elapsed / 60)
                print(f"   💓 [{mins}m] 仍在監控... {len(validated_horses)}/{len(all_horses)} 已完成")
                last_heartbeat = time.time()
            
            # Stale detection
            if time.time() - last_change_time > stale_minutes * 60 and not stale_warned:
                print(f"   ⚠️ 已 {stale_minutes} 分鐘無檔案變動。LLM 是否仍在填寫？")
                stale_warned = True
            
            try:
                current_mtime = os.path.getmtime(json_file)
            except OSError:
                continue
            
            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                continue
            
            # Debounce: wait for write to complete
            time.sleep(0.5)
            last_mtime = current_mtime
            last_change_time = time.time()
            stale_warned = False
            
            # JSON read with retry (handles partial writes)
            logic_data = None
            for attempt in range(3):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        logic_data = json.load(f)
                    break
                except (json.JSONDecodeError, OSError):
                    if attempt < 2:
                        time.sleep(0.5)
                    continue
            
            if logic_data is None:
                print(f"   ⚠️ JSON 解析失敗（可能正在寫入），等待下次輪詢...")
                continue
            
            horses_dict = logic_data.get('horses', {})
            newly_validated = []
            
            for h in all_horses:
                hkey = str(h)
                if hkey in validated_horses:
                    continue
                
                h_entry = horses_dict.get(hkey, {})
                if not h_entry:
                    continue
                
                h_check = json.dumps(
                    {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                    ensure_ascii=False
                )
                if '[FILL]' in h_check:
                    continue
                
                # Validate
                errors = validate_fn(h, h_entry, horses_dict, all_horses, json_file)
                
                if errors:
                    name = h_entry.get('horse_name', '')
                    print(f"\n🚨 Horse #{h} ({name}) Firewall 失敗!")
                    for e in errors:
                        print(f"   ❌ {e}")
                    print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
                    # Reset core_logic to force redo
                    h_entry['core_logic'] = '[FILL]'
                    with open(json_file, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    own_write_mtime = os.path.getmtime(json_file)
                    last_mtime = own_write_mtime
                else:
                    validated_horses.add(hkey)
                    name = h_entry.get('horse_name', '')
                    newly_validated.append(f"#{h} {name}")
            
            if newly_validated:
                for nv in newly_validated:
                    print(f"   ✅ {nv} 驗證通過")
                print(f"   📊 進度: {len(validated_horses)}/{len(all_horses)}")
            
            if len(validated_horses) == len(all_horses):
                # Final read with retry
                for _ in range(3):
                    try:
                        with open(json_file, 'r', encoding='utf-8') as f:
                            final_data = json.load(f)
                        return final_data
                    except (json.JSONDecodeError, OSError):
                        time.sleep(0.5)
                # Fallback
                return logic_data
    
    except KeyboardInterrupt:
        print(f"\n\n⚠️ 用戶中斷 (Ctrl+C)！已驗證 {len(validated_horses)}/{len(all_horses)} 匹馬。")
        print(f"   已完成嘅驗證會保留喺 JSON 中。重跑 Orchestrator 可恢復進度。")
        return None


# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Racenet Event URL or target directory path")
    parser.add_argument("--auto", action="store_true", help="Auto mode: skip confirmation gate")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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
    print("🏇 AU Wong Choi Orchestrator (State Machine V10)")
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
    short_prefix = date_prefix[5:] if len(date_prefix) == 10 else date_prefix
    
    for r in range(1, total_races + 1):
        facts_status[r] = any(re.search(rf'Race {r} Facts\.md', f) for f in os.listdir(target_dir))
        if facts_status[r]: 
            facts_done += 1
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            if not os.path.exists(facts_file):
                facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
            horses = get_horse_numbers(facts_file)
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            done_horses = []
            if os.path.exists(json_file):
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        j_data = json.load(f)
                        if 'horses' in j_data:
                            done_horses = [int(k) for k, v in j_data['horses'].items()
                                           if v and '[FILL]' not in json.dumps(
                                               {fk: fv for fk, fv in v.items() if fk not in ('base_rating', 'final_rating')},
                                               ensure_ascii=False)]
                except Exception:
                    pass
            batch_details[r] = {
                'batches': get_batches(horses, 3),
                'done': done_horses,
                'horses': horses
            }
            
        an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
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
    print(f"  {chk_raw} 賽事資料下載")
    print(f"  {chk_weather} 天氣與場地情報")
    print(f"  {chk_facts} 事實錨點生成")
    print(f"  {chk_analysis} JSON 組合與合規 QA")
    print("  (詳細進度已輸出至: _session_tasks.md)")

    # ── Information Isolation (V9.4) ─────────────────────────────
    _current_race = None
    for _r in range(1, total_races + 1):
        if not analysis_status.get(_r, False):
            _current_race = _r
            break
    if _current_race and _current_race in batch_details:
        _bd = batch_details[_current_race]
        _done_n = len(_bd.get('done', []))
        _total_n = len(_bd.get('horses', []))
        print(f"\n📋 當前任務: Race {_current_race} ({_done_n}/{_total_n} 匹馬已完成)")
    elif _current_race:
        print(f"\n📋 當前任務: Race {_current_race} (等待開始)")
    else:
        print(f"\n📋 所有賽事分析已完成！")
    print("="*60 + "\n")

    # --- RACE DISTANCE & CLASS CONFIRMATION ---
    distance_errors = []
    _race_info_cache = {}
    for r in range(1, total_races + 1):
        rc_path = get_racecard_path(target_dir, r)
        race_dist = "?"
        race_class = ""
        if rc_path and os.path.exists(rc_path):
            with open(rc_path, 'r', encoding='utf-8') as f:
                header = f.readline().strip()
            dist_m = re.search(r'[—–-]\s*(\d{3,5})m', header)
            class_m = re.search(r'\d+m\s*\|\s*([^|$]+)', header)
            if dist_m:
                race_dist = f"{dist_m.group(1)}m"
            if class_m:
                race_class = class_m.group(1).strip()
        
        if race_dist == "?":
            distance_errors.append(r)
        
        _race_info_cache[r] = (race_dist, race_class)
    
    if _current_race and _current_race in _race_info_cache:
        _cd, _cc = _race_info_cache[_current_race]
        print(f"📏 當前賽事: R{_current_race} — {_cd} | {_cc}")
    
    if distance_errors:
        print(f"\n🚨 [WARNING] 部分賽事距離提取失敗")
        print("   請檢查 Racecard header 格式是否包含 '— XXXm'\n")
    else:
        print(f"✅ 賽事距離確認正確！\n")

    # --- 3-Strike QA Tracker ---
    qa_tracker_file = os.path.join(target_dir, ".qa_strikes.json")
    strikes = {}
    if os.path.exists(qa_tracker_file):
        try:
            with open(qa_tracker_file, 'r', encoding='utf-8') as f:
                strikes = json.load(f)
        except: pass
        
    def save_strikes():
        with open(qa_tracker_file, 'w', encoding='utf-8') as f:
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

    # ═══════════════════════════════════════════════════════════════
    # STATE 2.5 + 3: V10 Unified Per-Race Loop (File-Watch Architecture)
    # Python is the controller. LLM only fills JSON.
    # ═══════════════════════════════════════════════════════════════
    if chk_analysis == "[ ]":
        skeleton_script = ".agents/skills/au_racing/au_wong_choi/scripts/create_au_logic_skeleton.py"
        
        for r in range(1, total_races + 1):
            # ── Skip completed races ──
            an_file = os.path.join(target_dir, f"{short_prefix} Race {r} Analysis.md")
            if os.path.exists(an_file):
                try:
                    with open(an_file, 'r', encoding='utf-8') as _af:
                        _recheck_content = _af.read()
                    if "[FILL]" not in _recheck_content and "FILL:" not in _recheck_content:
                        print(f"   ✅ Race {r} 已完成 (跳過)")
                        continue
                except Exception:
                    pass
            if analysis_status.get(r, False):
                continue
            
            print(f"\n{'─'*60}")
            print(f"🐎 正在處理 Race {r}...")
            print(f"{'─'*60}")
            
            # ── FLUSH_HINT: Context Window Reset Signal ──
            if r > 1:
                print(f"")
                print(f"{'#'*60}")
                print(f"### FLUSH_HINT ###")
                print(f"# LLM Agent — 請立即丟棄上場賽事所有馬匹個別分析記憶。")
                print(f"# Race {r} 係全新獨立分析單元。")
                print(f"# 只參考以下資源：")
                print(f"#   → .runtime/Horse_N_Context.md (每匹馬獨立)")
                print(f"#   → Race {r} Facts.md (本場事實錨點)")
                print(f"# 上場馬匹名字、評分、走勢均與本場無關，請勿帶入。")
                print(f"{'#'*60}")
                print(f"")

            # Preflight check for each race
            if os.path.exists(preflight_script):
                pf_r = subprocess.run(
                    [PYTHON, preflight_script, target_dir, "--domain", "au",
                     "--session-start", str(SESSION_START_TIME)],
                    capture_output=True, text=True
                )
                if pf_r.returncode == 2:
                    print(pf_r.stdout)
                    print("🛑 Preflight FAILED mid-session!")
                    sys.exit(2)
            
            facts_file = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            if not os.path.exists(facts_file):
                facts_file = os.path.join(target_dir, f"{short_prefix} Race {r} Facts.md")
            json_file = os.path.join(target_dir, f"Race_{r}_Logic.json")
            
            # ── Step A: Ensure Logic JSON exists ──
            if not os.path.exists(json_file):
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
                with open(json_file, 'w', encoding='utf-8') as _wf:
                    json.dump(_init_json, _wf, ensure_ascii=False, indent=2)
                print(f"   ✅ 已自動建立 `Race_{r}_Logic.json` 骨架 ({_race_class} / {_race_dist})")
            
            # ── Step B: Check Speed Map ──
            try:
                with open(json_file, 'r', encoding='utf-8') as _f:
                    logic_data = json.load(_f)
            except Exception:
                logic_data = {}
            
            sm = logic_data.get('race_analysis', {}).get('speed_map', {})
            _sm_check_keys = ['expected_pace', 'track_bias', 'tactical_nodes', 'collapse_point']
            missing_sm = [k for k in _sm_check_keys if not sm.get(k) or sm.get(k) == '[FILL]']
            
            if missing_sm:
                facts_file_b0 = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
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
                print("生成完畢後，Python 會自動偵測並推進！")
                notify_telegram(f"📍 **AU Race {r} Action Required**\nBatch 0 步速瀑布 (Speed Map) 尚未填寫。")
                _next_cmd(target_dir)
                sys.exit(0)
            
            # ── Step C: Get all horses ──
            try:
                all_horses = get_horse_numbers(facts_file)
            except:
                all_horses = []
            
            if not all_horses:
                print(f"⚠️ Race {r}: 無法從 Facts.md 提取馬匹列表")
                continue
            
            # ── Step D: Read facts content for context generation ──
            try:
                with open(facts_file, 'r', encoding='utf-8') as _f:
                    facts_content = _f.read()
            except:
                facts_content = ""
            
            horses_dict = logic_data.get('horses', {})
            
            # ── Step E: Validate already-filled + collect pending ──
            validated_count = 0
            pending_horses = []
            
            for h in all_horses:
                hkey = str(h)
                h_entry = horses_dict.get(hkey, {})
                
                if not h_entry:
                    pending_horses.append(h)
                    continue
                
                h_json_for_check = json.dumps(
                    {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                    ensure_ascii=False
                )
                
                if '[FILL]' in h_json_for_check:
                    pending_horses.append(h)
                    continue
                
                # Validate
                errors = validate_au_firewalls(h, h_entry, horses_dict, all_horses, json_file)
                
                if errors:
                    horse_name = h_entry.get('horse_name', '')
                    print(f"\n🚨 Horse #{h} ({horse_name}) firewall failed!")
                    for e in errors:
                        print(f"   ❌ {e}")
                    horses_dict[hkey]['core_logic'] = '[FILL]'
                    logic_data['horses'] = horses_dict
                    with open(json_file, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    pending_horses.append(h)
                else:
                    validated_count += 1
            
            if validated_count > 0:
                print(f"   ✅ {validated_count}/{len(all_horses)} 匹馬已驗證通過")
            
            # ── Step F+G: Per-Horse Sequential Analysis (V10.1 Quality Architecture) ──
            # Instead of generating ALL skeletons at once and watching for bulk completion,
            # we now process ONE horse at a time: generate work card → watch → validate → next.
            # This prevents the LLM from taking shortcuts with batch-fill scripts.
            if pending_horses:
                # Determine venue-specific track module
                _dir_parts = os.path.basename(target_dir).split(" ", 1)
                _au_venue = _dir_parts[1].lower().replace(" ", "_") if len(_dir_parts) > 1 else ""
                _au_track_file = f"04b_track_{_au_venue}.md"
                _au_track_path = os.path.join(".agents", "skills", "au_racing", "au_horse_analyst", "resources", _au_track_file)
                _au_track_exists = os.path.exists(os.path.join(target_dir, "..", "..", "..", _au_track_path)) or os.path.exists(_au_track_path)
                
                _sm_data = logic_data.get('race_analysis', {}).get('speed_map', {})
                _sm_pace = _sm_data.get('expected_pace', _sm_data.get('predicted_pace', 'N/A'))
                _sm_bias = _sm_data.get('track_bias', 'N/A')
                
                runtime_dir = os.path.join(target_dir, ".runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                
                print(f"\n{'='*60}")
                print(f"📋 Race {r}: {len(pending_horses)} 匹馬待分析（逐匹驅動模式）")
                print(f"{'='*60}")
                print(f"📖 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md")
                print(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md")
                if _au_track_exists:
                    print(f"📖 場地模組: {_au_track_path}")
                print(f"📍 步速: {_sm_pace} | 偏差: {_sm_bias}")
                
                completed_in_session = 0
                
                for horse_idx, ph in enumerate(pending_horses):
                    print(f"\n{'─'*60}")
                    print(f"🐎 [{horse_idx+1}/{len(pending_horses)}] 正在處理 Horse #{ph}")
                    print(f"{'─'*60}")
                    
                    # 1. Generate skeleton (if not already present)
                    skel_result = subprocess.run(
                        [PYTHON, skeleton_script, facts_file, str(r), str(ph)],
                        capture_output=True, text=True
                    )
                    if skel_result.stdout.strip():
                        for line in skel_result.stdout.strip().split('\n'):
                            if '✅' in line or '⚙️' in line:
                                print(f"   {line.strip()}")
                    
                    # 2. Reload JSON to get the nonce
                    with open(json_file, 'r', encoding='utf-8') as _jf:
                        logic_data = json.load(_jf)
                    
                    # 3. Generate guided Work Card (the key quality improvement)
                    card_path = generate_work_card(
                        ph, facts_content, logic_data, runtime_dir,
                        _sm_pace, _sm_bias,
                        horse_idx=horse_idx, total_horses=len(pending_horses)
                    )
                    
                    # 4. Also write legacy Context file for backward compat
                    h_entry = logic_data.get('horses', {}).get(str(ph), {})
                    locked_nonce = h_entry.get('_validation_nonce', 'MISSING')
                    horse_facts_block = extract_horse_facts_block(ph, facts_content)
                    ctx_path = os.path.join(runtime_dir, f"Horse_{ph}_Context.md")
                    with open(ctx_path, "w", encoding="utf-8") as _ctx_f:
                        _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                        _ctx_f.write(f"📖 分析引擎: .agents/skills/au_racing/au_horse_analyst/SKILL.md\n")
                        _ctx_f.write(f"📖 評級矩陣: .agents/skills/au_racing/au_horse_analyst/resources/02f_synthesis.md\n")
                        _ctx_f.write(f"📖 覆蓋規則: .agents/skills/au_racing/au_horse_analyst/resources/02g_override_chain.md\n")
                        if _au_track_exists:
                            _ctx_f.write(f"📖 場地模組: {_au_track_path}\n")
                        _ctx_f.write(f"📖 合規參考: .agents/skills/au_racing/au_compliance/SKILL.md\n")
                        _ctx_f.write(f"📍 步速判定: {_sm_pace} | 跑道偏差: {_sm_bias}\n\n")
                        _ctx_f.write(horse_facts_block)
                    
                    # Copy to Active_Horse_Context.md for backward compat
                    active_ctx = os.path.join(runtime_dir, "Active_Horse_Context.md")
                    shutil.copy2(ctx_path, active_ctx)
                    
                    # 5. Print instructions for THIS SINGLE HORSE
                    h_name = h_entry.get('horse_name', '?')
                    print(f"\n👉 LLM: 請讀取以下檔案並分析 Horse #{ph} ({h_name}):")
                    print(f"   📋 工作卡: .runtime/Horse_{ph}_WorkCard.md")
                    print(f"   📄 原始數據: .runtime/Horse_{ph}_Context.md")
                    print(f"   ✏️ 填寫目標: Race_{r}_Logic.json → horses.{ph}")
                    print(f"\n   ⚠️ 只做呢一匹馬！Python 會自動偵測變動並驗證。")
                    
                    # 6. Watch for THIS SINGLE HORSE to pass validation
                    result = watch_single_horse(
                        json_file, ph,
                        validate_fn=validate_au_firewalls,
                        all_horses=all_horses,
                        poll_interval=3,
                        timeout_minutes=10
                    )
                    
                    if result:
                        completed_in_session += 1
                        print(f"\n   ✅ Horse #{ph} ({h_name}) 驗證通過！ [{completed_in_session}/{len(pending_horses)}]")
                        print_analysis_summary(result, ph)
                        print(f"\n   ### FLUSH: Horse #{ph} 分析完畢 — 清除記憶準備下一匹 ###")
                    else:
                        print(f"\n   ⏰ Horse #{ph} 超時或被中斷。")
                        print(f"   已完成 {completed_in_session}/{len(pending_horses)} 匹馬。")
                        print(f"   重跑 Orchestrator 可從斷點繼續。")
                        _next_cmd(target_dir)
                        sys.exit(0)
                
                # All horses done — reload final data
                with open(json_file, 'r', encoding='utf-8') as _jf:
                    logic_data = json.load(_jf)
                
                print(f"\n✅ Race {r} 所有 {len(pending_horses)} 匹馬驗證通過！")
            
            # ── Step H: WALL-015 Global Check ──
            horses_dict = logic_data.get('horses', {})
            global_errors = validate_au_global_firewalls(horses_dict, all_horses, json_file)
            if global_errors:
                for ge in global_errors:
                    print(f"🚨 {ge}")
                print(f"請清理 JSON 後重跑。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step I: 3-Strike Check ──
            if strikes.get(str(r), 0) >= 3:
                print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗 (Strike-3 Fallback)。")
                print(f"系統已中斷自動化，請人類直接打開 `{os.path.basename(json_file)}` 修正長度與邏輯！")
                notify_telegram(f"❌ **AU Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，請人工介入！")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step J: Auto-Verdict ──
            verdict_data = logic_data.get('race_analysis', {}).get('verdict')
            if not verdict_data:
                print(f"\n⚙️ Auto-Verdict: 正在為 Race {r} 自動計算 Top 4 排序...")
                verdict = auto_compute_verdict(logic_data, facts_file)
                with open(json_file, 'w', encoding='utf-8') as _wf:
                    json.dump(logic_data, _wf, ensure_ascii=False, indent=2)
                t4_display = ', '.join([f"#{v['horse_number']} {v['horse_name']} ({v['grade']})" for v in verdict['top4']])
                print(f"   ✅ Top 4: {t4_display}")
                notify_telegram(f"✅ **AU Race {r} Auto-Verdict**\nTop 4: {t4_display}")
            
            # ── Step K: Compile ──
            print(f"⚙️ 發現 Race {r} JSON 所有馬匹已聚齊！正在編譯...")
            compile_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "compile_analysis_template.py")
            compile_cmd = [PYTHON, compile_script_path, facts_file, json_file, "--output", an_file]
            res = subprocess.run(compile_cmd)
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(json_file)}。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                _next_cmd(target_dir)
                sys.exit(1)
            
            # Post-compile verification
            if not os.path.exists(an_file):
                print(f"❌ 編譯完成但 Analysis.md 未生成！請檢查 compile 腳本。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step L: Monte Carlo Simulation ──
            print(f"🎲 Running AU Monte Carlo simulation for Race {r}...")
            mc_au_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monte_carlo_au.py")
            mc_inject_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts", "inject_mc_au.py")
            mc_json_out = os.path.join(target_dir, f"Race_{r}_MC_Results.json")

            if os.path.exists(mc_au_script):
                mc_res = subprocess.run(
                    [PYTHON, mc_au_script, json_file, facts_file, "--output", mc_json_out],
                    capture_output=True, text=True
                )
                if mc_res.returncode == 0:
                    print(f"✅ MC JSON generated → Race_{r}_MC_Results.json")
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
            
            # ── Step M: QA ──
            print(f"🛡️ 正在進行 Batch QA (completion_gate_v2.py)...")
            qa_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "..", "scripts", "completion_gate_v2.py")
            qa_res = subprocess.run([PYTHON, qa_script, an_file, "--domain", "au"])
            if qa_res.returncode != 0:
                print(f"\n❌ Race {r} QA 驗證失敗！")
                print(f"請重新修改 `{os.path.basename(json_file)}`，補齊字數。修改後重跑 Orchestrator。")
                strikes[str(r)] = strikes.get(str(r), 0) + 1
                save_strikes()
                _next_cmd(target_dir)
                sys.exit(1)
            else:
                print(f"\n{'🎉'*10}")
                print(f"✅ Race {r} Batch QA 通過！")
                print(f"{'🎉'*10}")
                if str(r) in strikes:
                    del strikes[str(r)]
                    save_strikes()
            
            # ── Step N: Auto-advance to next race (no exit) ──
            if r < total_races:
                print(f"\n{'─'*60}")
                print(f"🔄 Race {r} 完成！自動推進到 Race {r+1}...")
                print(f"{'─'*60}")
                # Continue the for-loop to process next race automatically
                continue

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
