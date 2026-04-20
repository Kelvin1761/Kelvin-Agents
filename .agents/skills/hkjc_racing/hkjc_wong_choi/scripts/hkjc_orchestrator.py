#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import argparse
import sys
import subprocess
import re
import json
import time
import shutil

import urllib.request

# Import rating engine for auto-verdict computation
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'scripts')))
from rating_engine_v2 import parse_matrix_scores, compute_base_grade, apply_fine_tune, grade_sort_index

# Import SIP engine for automated SIP rule evaluation
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from sip_engine import evaluate_horse_sips, evaluate_race_sips, format_sip_summary
    SIP_ENGINE_AVAILABLE = True
except ImportError:
    SIP_ENGINE_AVAILABLE = False

HKJC_MATRIX_SCHEMA = {
    "stability": "core", "speed_mass": "core",
    "eem": "semi", "trainer_jockey": "semi",
    "scenario": "aux", "freshness": "aux",
    "formline": "aux", "class_advantage": "aux",
}

def auto_compute_verdict_hkjc(logic_data, facts_path):
    """Auto-compute verdict Top 4 from matrix grades. Eliminates LLM verdict stop."""
    horses = logic_data.get('horses', {})
    speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
    
    # Compute grade for each horse
    graded = []
    for h_num, h_obj in horses.items():
        m_data = h_obj.get('matrix', {})
        core_pass, semi_pass, aux_pass, core_fail, total_fail = parse_matrix_scores(m_data, HKJC_MATRIX_SCHEMA)
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
        subprocess.run([PYTHON, script_path, "--base_url", url, "--races", "1-11", "--output_dir", target_dir], check=True)
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
    with open(facts_file, 'r', encoding='utf-8') as f:
        content = f.read()
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
            [PYTHON, preflight_script, target_dir, "--domain", "hkjc",
             "--session-start", str(SESSION_START_TIME)],
            capture_output=True, text=True
        )
        print(result.stdout)
        if result.returncode == 2:
            print("🛑 Preflight check FAILED — 請清理可疑檔案後再執行！")
            sys.exit(2)


def _next_cmd(target_dir):
    """Print machine-readable re-run command for LLM auto-execution."""
    dir_arg = os.path.basename(target_dir)
    print(f"\nNEXT_CMD: {PYTHON} .agents/skills/hkjc_racing/hkjc_wong_choi/scripts/hkjc_orchestrator.py \"{dir_arg}\" --auto")


# ═══════════════════════════════════════════════════════════════
# V10 Helper Functions: Firewall Validation + File-Watch Loop
# ═══════════════════════════════════════════════════════════════

def extract_hkjc_horse_facts_block(target_horse, facts_content):
    """Extract a single horse's facts block from HKJC Facts.md."""
    h_block_match = re.search(rf'### 馬號 {target_horse} — ', facts_content)
    if h_block_match:
        h_start = h_block_match.start()
        h_next = re.search(r'### 馬號 \d+ — ', facts_content[h_block_match.end():])
        h_end = h_block_match.end() + h_next.start() if h_next else len(facts_content)
        return facts_content[h_start:h_end]
    return ""


def extract_hkjc_fact_anchors(horse_block):
    """Extract key factual data points from a HKJC horse's Facts block for work card generation."""
    anchors = {}

    # Horse name, jockey, trainer, weight, barrier
    m = re.search(r'### 馬號 (\d+) — (.+?) \| 騎師:\s*(.+?) \| 練馬師:\s*(.+?) \| 負磅:\s*(\d+) \| 檔位:\s*(\d+)',
                  horse_block)
    if m:
        anchors['name'] = m.group(2).strip()
        anchors['jockey'] = m.group(3).strip()
        anchors['trainer'] = m.group(4).strip()
        anchors['weight'] = m.group(5)
        anchors['barrier'] = m.group(6)
    else:
        anchors['name'] = '未知'
        anchors['jockey'] = '?'
        anchors['trainer'] = '?'
        anchors['weight'] = '?'
        anchors['barrier'] = '?'

    # Recent form (Last 10)
    m = re.search(r'Last 10.*?:\s*`([^`]+)`', horse_block)
    anchors['recent_form'] = m.group(1) if m else '無'

    # Career stats
    m = re.search(r'生涯:\s*(\d+):', horse_block)
    anchors['career_starts'] = m.group(1) if m else '0'

    # Fitness arc
    starts = int(anchors['career_starts'])
    if starts == 0:
        anchors['fitness_arc'] = '初出馬'
    elif starts == 1:
        anchors['fitness_arc'] = '二出'
    elif starts == 2:
        anchors['fitness_arc'] = 'Third-up'
    elif starts <= 5:
        anchors['fitness_arc'] = f'輕度備戰（{starts}仗）'
    else:
        anchors['fitness_arc'] = f'Deep Prep（{starts}仗）'

    # EEM drain
    m = re.search(r'加權累積消耗:\s*([^→]+?)→', horse_block)
    anchors['eem_drain'] = m.group(1).strip() if m else '無數據'

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

    # Engine type
    m = re.search(r'引擎:\s*(.+?)\s*\|', horse_block)
    anchors['engine_type'] = m.group(1).strip() if m else '未知'

    # Distance record
    m = re.search(r'今仗\s*\d+m.*?:\s*(.+?)$', horse_block, re.MULTILINE)
    anchors['distance_record'] = m.group(1).strip() if m else '無紀錄'

    # Best distance
    m = re.search(r'⭐最佳', horse_block)
    if m:
        dist_m = re.search(r'([\d≤]+m?).*?⭐最佳', horse_block)
        anchors['best_distance'] = dist_m.group(1) if dist_m else '未知'
    else:
        anchors['best_distance'] = '數據不足'

    # Last run remark
    remarks = re.findall(r'\|\s*[^|]*(?:Led|Settled|Held|Keen|Pushed|Sat|Box seat)[^|]*\|', horse_block)
    anchors['last_run_remark'] = remarks[0].strip('| ') if remarks else '無'

    return anchors


def generate_hkjc_work_card(horse_num, facts_content, logic_data, runtime_dir,
                            sm_pace, sm_bias, horse_idx=0, total_horses=1):
    """Generate a guided analysis work card for a SINGLE HKJC horse."""
    horse_block = extract_hkjc_horse_facts_block(horse_num, facts_content)
    if not horse_block:
        return None

    anchors = extract_hkjc_fact_anchors(horse_block)
    race_class = logic_data.get('race_analysis', {}).get('race_class', '?')
    distance = logic_data.get('race_analysis', {}).get('distance', '?')

    card = []
    card.append(f"# 🐎 分析工作卡 [{horse_idx+1}/{total_horses}] — 馬號 {horse_num} {anchors['name']}")
    card.append(f"**檔位: {anchors['barrier']} | 騎師: {anchors['jockey']} | 練馬師: {anchors['trainer']} | 負磅: {anchors['weight']}**")
    card.append(f"📍 步速: {sm_pace} | 偏差: {sm_bias} | 班次: {race_class} | 距離: {distance}")
    card.append(f"📖 評級矩陣: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/06_rating_aggregation.md")
    card.append("")
    card.append("---")
    card.append("## ⚠️ 指引")
    card.append("- 每個維度必須根據下方列出嘅**具體數據**作出判斷")
    card.append("- 分數只可以係 ✅✅ / ✅ / ➖ / ❌ / ❌❌")
    card.append("- 理據必須引用具體數據（日期、場地、名次、PI 數值等）")
    card.append("- 唔可以寫「一般」、「尚可」、「配搭無特別異常」等模板化語句")
    card.append("---")
    card.append("")

    card.append("## 1️⃣ 狀態與穩定性 [核心維度]")
    card.append(f"- 正式賽事場次: **{anchors['career_starts']}**")
    card.append(f"- 近績序列: `{anchors['recent_form']}`")
    card.append(f"- 狀態週期: **{anchors['fitness_arc']}**")
    card.append(f"- 上仗備註: {anchors['last_run_remark']}")
    card.append("👉 **你嘅判斷:** ✅✅/✅/➖/❌/❌❌？寫 1-2 句引用上述數據嘅理據。")
    card.append("")

    card.append("## 2️⃣ 段速與引擎 [核心維度]")
    card.append(f"- 引擎類型: {anchors.get('engine_type', '未知')}")
    card.append(f"- 今仗步速預測: {sm_pace}")
    card.append("👉 **你嘅判斷:** 段速質素如何？引擎同今仗步速配唔配？")
    card.append("")

    card.append("## 3️⃣ EEM與形勢 [半核心]")
    card.append(f"- 累積消耗: {anchors.get('eem_drain', '無數據')}")
    card.append(f"- 今仗檔位: {anchors.get('barrier', '?')}")
    card.append(f"- 跑道偏差: {sm_bias}")
    card.append("👉 **你嘅判斷:** 消耗水平 + 檔位形勢？")
    card.append("")

    card.append("## 4️⃣ 騎練訊號 [半核心]")
    card.append(f"- 騎師: {anchors.get('jockey', '?')}")
    card.append(f"- 練馬師: {anchors.get('trainer', '?')}")
    card.append("👉 **你嘅判斷:** 有冇出擊訊號？冇資料就寫 ➖。")
    card.append("")

    card.append("## 5️⃣ 級數與負重 [輔助]")
    card.append(f"- 今仗班次: {race_class}")
    card.append(f"- 負磅: {anchors.get('weight', '?')}磅")
    card.append("👉 **你嘅判斷:** 班次/負磅有冇優勢？")
    card.append("")

    card.append("## 6️⃣ 場地適性 [輔助]")
    card.append(f"- 好地紀錄: {anchors.get('good_record', '無')}")
    card.append(f"- 軟地紀錄: {anchors.get('soft_record', '無')}")
    card.append(f"- 同場紀錄: {anchors.get('course_record', '無')}")
    card.append("👉 **你嘅判斷:** 場地有冇經驗？有冇贏過？")
    card.append("")

    card.append("## 7️⃣ 賽績線 [輔助]")
    card.append(f"- 賽績線強度: {anchors.get('formline_strength', '無資料')}")
    card.append("👉 **你嘅判斷:** 對手後續表現強唔強？")
    card.append("")

    card.append("## 8️⃣ 裝備與距離 [輔助]")
    card.append(f"- 今仗距離: {distance}")
    card.append(f"- 距離紀錄: {anchors.get('distance_record', '無紀錄')}")
    card.append(f"- 最佳距離: {anchors.get('best_distance', '數據不足')}")
    card.append("👉 **你嘅判斷:** 路程啱唔啱？裝備有冇變？")
    card.append("")

    # ── SIP Trigger Section (auto-evaluated) ──
    if SIP_ENGINE_AVAILABLE:
        _sip_horse_data = {
            'horse_name': anchors.get('name', ''),
            'wins': 0 if anchors.get('career_starts', '0') != '0' else None,
            'starts': int(anchors.get('career_starts', '0')) if anchors.get('career_starts', '0').isdigit() else 0,
            'weight': int(anchors.get('weight', '126')) if str(anchors.get('weight', '')).isdigit() else 126,
            'barrier': int(anchors.get('barrier', '5')) if str(anchors.get('barrier', '')).isdigit() else 5,
            'core_logic': '',
            'matrix': {},
        }
        _sip_race_ctx = {
            'distance': distance,
            'track': '草地',
            'field_size': total_horses,
        }
        _horse_sips = evaluate_horse_sips(_sip_horse_data, _sip_race_ctx)
        _race_sips = evaluate_race_sips(_sip_race_ctx, {})
        sip_text = format_sip_summary(_horse_sips, _race_sips)
        card.append(sip_text)
    
    # ── Trend Indicators Section ──
    card.append("## 📈 趨勢指標 [自動]")
    recent_form = anchors.get('recent_form', '無')
    card.append(f"- 近績序列: `{recent_form}`")
    # Parse trend from recent form
    if recent_form and recent_form != '無':
        positions = []
        for ch in recent_form:
            if ch.isdigit():
                positions.append(int(ch))
        if len(positions) >= 3:
            last3 = positions[-3:]
            if last3[-1] < last3[-2] < last3[-3]:
                card.append(f"- 趨勢: ↗ 連續上升中 ({last3[0]}→{last3[1]}→{last3[2]})")
            elif last3[-1] > last3[-2] > last3[-3]:
                card.append(f"- 趨勢: ↘ 連續下滑中 ({last3[0]}→{last3[1]}→{last3[2]})")
            else:
                card.append(f"- 趨勢: ↔ 波動 ({last3[0]}→{last3[1]}→{last3[2]})")
    card.append(f"- 同場同距離紀錄: {anchors.get('course_record', '無')}")
    card.append(f"- 最佳距離: {anchors.get('best_distance', '數據不足')}")
    card.append("")
    
    card.append("---")
    card.append("## 📋 綜合部分（填完 8 個維度後）")
    card.append("- **core_logic**: 串連所有維度寫成連貫分析（必須引用具體賽事/數據）")
    card.append("- **advantages**: 2-3 個主要優勢")
    card.append("- **disadvantages**: 2-3 個致命風險")
    card.append("")
    card.append("---")
    card.append("## 📄 原始賽績數據（嚴禁修改）")
    card.append(horse_block)

    card_path = os.path.join(runtime_dir, f"Horse_{horse_num}_WorkCard.md")
    with open(card_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(card))
    return card_path


def watch_single_horse_hkjc(json_file, horse_num, validate_fn, all_horses,
                            poll_interval=3, timeout_minutes=10):
    """Watch for a SINGLE HKJC horse to be filled and validated."""
    hkey = str(horse_num)
    last_mtime = os.path.getmtime(json_file)
    own_write_mtime = 0
    start_time = time.time()
    last_heartbeat = time.time()

    # Pre-check
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

    print(f"\n👀 Python 正在監控 馬號 {horse_num}... (每 {poll_interval} 秒 | 超時 {timeout_minutes} 分鐘)")

    try:
        while True:
            time.sleep(poll_interval)
            elapsed = time.time() - start_time
            if elapsed > timeout_minutes * 60:
                print(f"\n⏰ 馬號 {horse_num} 監控超時！")
                return None
            if time.time() - last_heartbeat > 60:
                mins = int(elapsed / 60)
                print(f"   💓 [{mins}m] 仍在等待 馬號 {horse_num}...")
                last_heartbeat = time.time()
            try:
                current_mtime = os.path.getmtime(json_file)
            except OSError:
                continue
            if current_mtime == last_mtime or current_mtime == own_write_mtime:
                continue
            time.sleep(0.5)
            last_mtime = current_mtime

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

            errors = validate_fn(horse_num, h_entry, horses_dict, all_horses, json_file)
            if errors:
                name = h_entry.get('horse_name', '')
                print(f"\n🚨 馬號 {horse_num} ({name}) Firewall 失敗!")
                for e in errors:
                    print(f"   ❌ {e}")
                print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
                h_entry['core_logic'] = '[FILL]'
                with open(json_file, 'w', encoding='utf-8') as wf:
                    json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                own_write_mtime = os.path.getmtime(json_file)
                last_mtime = own_write_mtime
            else:
                return h_entry

    except KeyboardInterrupt:
        print(f"\n⚠️ 用戶中斷！馬號 {horse_num} 未完成。")
        return None


def print_hkjc_analysis_summary(horse_entry, horse_num):
    """Print quality summary for HKJC horse analysis."""
    matrix = horse_entry.get('matrix', {})
    scores = []
    for dim in ['狀態與穩定性', '段速與引擎', 'EEM與形勢', '騎練訊號',
                '級數與負重', '場地適性', '賽績線', '裝備與距離']:
        data = matrix.get(dim, {})
        score = data.get('score', '?') if isinstance(data, dict) else str(data)
        short_dim = dim[:4]
        scores.append(f"{short_dim}:{score}")
    print(f"   📊 矩陣: {' | '.join(scores)}")

    core_logic = horse_entry.get('core_logic', '')
    if core_logic and len(core_logic) > 20:
        print(f"   💡 邏輯: {core_logic[:80]}...")
        print(f"   📏 長度: {len(core_logic)} 字")

    all_scores = [d.get('score', '') for d in matrix.values() if isinstance(d, dict)]
    unique_scores = set(all_scores)
    if len(unique_scores) <= 2 and len(all_scores) >= 6:
        print(f"   ⚠️ 品質警告: 分數差異度低（只有 {len(unique_scores)} 種分數）")
    elif len(unique_scores) >= 4:
        print(f"   ✨ 分數差異度良好 ({len(unique_scores)} 種不同分數)")



# Fluff phrases that indicate lazy/template analysis
FLUFF_PHRASES = [
    '配搭無特別異常', '一般而言', '整體尚可', '無特別優劣',
    '中規中矩', '表現平平', '沒有明顯', '無明顯',
    '暫時未有特別', '有待觀察', '資料有限',
]

def validate_hkjc_firewalls(h, h_entry, horses_dict, all_horses, json_file):
    """HKJC-specific per-horse firewall validation. Returns list of error strings.
    V2: Light quality checks — strict enough to catch garbage, but not so strict
    that models produce dummy content to bypass.
    """
    errors = []
    locked_nonce = h_entry.get('_validation_nonce', '')
    
    # WALL-008: Nonce validation
    if not locked_nonce:
        errors.append(f"WALL-008: 缺失防偽標籤 _validation_nonce (可能使用了不合規的 Batch Script 繞過)")
    
    # WALL-009: Matrix completeness — all 8 dimensions must have valid scores
    matrix = h_entry.get('matrix', {})
    valid_scores = {'✅✅', '✅', '➖', '❌', '❌❌'}
    filled_dims = 0
    for dim_name, dim_data in matrix.items():
        if isinstance(dim_data, dict):
            score = dim_data.get('score', '')
            if score in valid_scores:
                filled_dims += 1
    if filled_dims < 6:  # At least 6 of 8 dimensions (allow 2 missing for edge cases)
        errors.append(f"WALL-009: 矩陣維度不足 ({filled_dims}/8)，至少需要 6 個有效維度")
    
    # WALL-010: Score variety — at least 3 different scores (prevent all-same lazy fill)
    if filled_dims >= 6:
        unique_scores = set()
        for dim_data in matrix.values():
            if isinstance(dim_data, dict):
                score = dim_data.get('score', '')
                if score in valid_scores:
                    unique_scores.add(score)
        if len(unique_scores) < 2:
            errors.append(f"WALL-010: 分數差異度過低 (只有 {len(unique_scores)} 種分數)，可能為批量填充")
    
    # WALL-011: Fluff detection — core_logic must not contain template phrases
    core_logic = str(h_entry.get('core_logic', ''))
    for phrase in FLUFF_PHRASES:
        if phrase in core_logic:
            errors.append(f"WALL-011: core_logic 含有模板化語句「{phrase}」，請替換為具體數據分析")
            break  # Only report first fluff hit
    
    return errors


def watch_and_validate_hkjc(json_file, all_horses, validate_fn, poll_interval=3,
                            timeout_minutes=30, heartbeat_interval=60, stale_minutes=5):
    """V10 File-Watch Loop for HKJC with production hardening.
    Same features as AU version: timeout, heartbeat, stale detection, debounce, JSON retry.
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
            
            # JSON read with retry
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
                
                errors = validate_fn(h, h_entry, horses_dict, all_horses, json_file)
                
                if errors:
                    name = h_entry.get('horse_name', '')
                    print(f"\n🚨 馬號 {h} ({name}) Firewall 失敗!")
                    for e in errors:
                        print(f"   ❌ {e}")
                    print(f"   👉 請修正後儲存，Python 會自動重新驗證。")
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
                return logic_data
    
    except KeyboardInterrupt:
        print(f"\n\n⚠️ 用戶中斷 (Ctrl+C)！已驗證 {len(validated_horses)}/{len(all_horses)} 匹馬。")
        print(f"   已完成嘅驗證會保留喺 JSON 中。重跑 Orchestrator 可恢復進度。")
        return None


# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="HKJC Race URL or target directory if URL is skipped")
    parser.add_argument("--auto", action="store_true", help="Auto mode: skip confirmation gate")
    args = parser.parse_args()

    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    print("="*60)
    print("🏇 HKJC Wong Choi Orchestrator (State Machine V10)")
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
            
            horses = get_horse_numbers(facts_file)
            batches = get_batches(horses, 3)
            date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
            an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
            
            if os.path.exists(an_file):
                with open(an_file, 'r', encoding='utf-8') as _af:
                    content = _af.read()
                if "[FILL]" not in content and "缺失核心" not in content and "未分析" not in content:
                    analysis_passed += 1
                    analysis_status_dict[r] = "✅ 分析與 QA 完成"
                    continue
            
            logic_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            if not os.path.exists(logic_json):
                analysis_status_dict[r] = f"等待建立 Race_{r}_Logic.json (Speed Map)"
                continue
                
            try:
                with open(logic_json, 'r', encoding='utf-8') as f:
                    logic_data = json.load(f)
            except Exception:
                analysis_status_dict[r] = "🚨 Race Logic JSON 解析失敗，需要修復"
                continue
            
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
    print(f"  {chk_raw} 賽事資料下載")
    print(f"  {chk_weather} 天氣與場地情報")
    print(f"  {chk_facts} 事實錨點生成")
    print(f"  {chk_analysis} JSON 組合與合規 QA")
    print(f"  (詳細進度已輸出至: {os.path.basename(tasks_file)})")

    # ── Information Isolation (V9.4) ─────────────────────────────
    _current_race = None
    for _r in range(1, total_races + 1):
        _st = analysis_status_dict.get(_r, "待啟動")
        if "✅" not in _st:
            _current_race = _r
            break
    if _current_race:
        _cst = analysis_status_dict.get(_current_race, "等待開始")
        print(f"\n📋 當前任務: Race {_current_race} — {_cst}")
    else:
        print(f"\n📋 所有賽事分析已完成！")
    print("=" * 60 + "\n")

    # ── Confirmation Gate (first run only) ──
    if not args.auto and analysis_passed < total_races:
        print("🔒 【確認閘門】首次執行 — 請確認上述賽日資訊正確。")
        print("   確認後請執行以下指令啟動自動分析模式：")
        _next_cmd(target_dir)
        sys.exit(0)

    # --- EXECUTION STATE MACHINE ---
    if missing_raw:
        if not args.url.startswith("http"):
            print("🚨 State 0: 原始數據缺失且無 URL（目錄模式），無法自動提取！")
            print("👉 請使用 HKJC URL 重新執行。")
            sys.exit(1)
        print("🚨 State 0: 發現原始數據缺失！自動呼叫 Extractor 進行修補...")
        trigger_extractor(args.url, target_dir)
        print("✅ 數據修補完畢！")
        _next_cmd(target_dir)
        sys.exit(0)

    if chk_weather == "[ ]":
        _dir_name = os.path.basename(target_dir)
        _det_venue = _dir_name.split("_", 1)[1] if "_" in _dir_name else "Unknown"
        _track_hint = {
            "ShaTin": "10a_track_sha_tin_turf.md (草地) 或 10c_track_awt.md (全天候)",
            "HappyValley": "10b_track_happy_valley.md"
        }.get(_det_venue, "請手動選擇對應場地模組")
        
        print("🚨 State 1 行動要求 (Action Required):")
        print(f"👉 LLM Agent 請注意：請建立 `_Meeting_Intelligence_Package.md`。")
        print(f"")
        print(f"📋 必須包含以下內容：")
        print(f"   1. 天氣預報（溫度、濕度、降雨概率、風向風速）")
        print(f"   2. 場地狀態（Going 評級、灌溉、已知偏差）")
        print(f"   3. 跑道偏差（內/外欄優勢、不同距離影響）")
        print(f"   4. 重大退出 / 配備變動")
        print(f"")
        print(f"📖 參考資源：")
        print(f"   → 場地模組: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/{_track_hint}")
        print(f"   → 情報增強: .agents/skills/shared_instincts/intelligence_checklist.md (Tier 2 歷史場地 Pattern)")
        print(f"")
        notify_telegram("🚨 **HKJC State 1 Action Required**\n缺少場地天氣與賽道偏差，請手動生成 `_Meeting_Intelligence_Package.md`。")
        _next_cmd(target_dir)
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
                cmd = [PYTHON, ".agents/scripts/inject_hkjc_fact_anchors.py", fg, "--output", out_path]
                subprocess.run(cmd, check=True)
                
        print("✅ Facts 全部生成完畢！自動無縫推進前往 State 3 執行分析...")

    # ═══════════════════════════════════════════════════════════════
    # STATE 2.5 + 3: V10 Unified Per-Race Loop (File-Watch Architecture)
    # Python is the controller. LLM only fills JSON.
    # ═══════════════════════════════════════════════════════════════
    if chk_analysis == "[ ]":
        date_prefix = os.path.basename(target_dir).split(" ")[0][5:]
        strike_file = os.path.join(target_dir, ".qa_strikes.json")
        strikes = {}
        if os.path.exists(strike_file):
            with open(strike_file, 'r', encoding='utf-8') as _sf:
                strikes = json.load(_sf)
        
        def save_strikes():
            with open(strike_file, 'w', encoding='utf-8') as f:
                json.dump(strikes, f)
        
        skeleton_script = ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/create_hkjc_logic_skeleton.py"
            
        for r in range(1, total_races + 1):
            # ── Skip completed races ──
            an_file = os.path.join(target_dir, f"{date_prefix} Race {r} Analysis.md")
            if os.path.exists(an_file):
                try:
                    with open(an_file, 'r', encoding='utf-8') as _af:
                        _recheck_content = _af.read()
                    if "[FILL]" not in _recheck_content and "缺失核心" not in _recheck_content and "未分析" not in _recheck_content:
                        print(f"   ✅ Race {r} 已完成 (跳過)")
                        continue
                except Exception:
                    pass
            if "✅" in analysis_status_dict.get(r, ""):
                continue
            
            print(f"\n{'─'*60}")
            print(f"🐎 正在處理 Race {r} ...")
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

            run_preflight_check(target_dir)  # Continuous Preflight Check
            
            facts_path = os.path.join(target_dir, f"{date_prefix} Race {r} Facts.md")
            logic_json = os.path.join(target_dir, f"Race_{r}_Logic.json")
            
            try:
                horses = get_horse_numbers(facts_path)
            except Exception:
                horses = []
            
            if not horses:
                print(f"⚠️ Race {r}: 無法從 Facts.md 提取馬匹列表")
                continue
            
            # ── Step A: Auto-create Logic JSON skeleton if needed ──
            if not os.path.exists(logic_json):
                race_class = "[FILL]"
                race_distance = "[FILL]"
                try:
                    with open(facts_path, 'r', encoding='utf-8') as _fc:
                        facts_content = _fc.read()
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
            
            # ── Step B: Check Speed Map ──
            try:
                with open(logic_json, 'r', encoding='utf-8') as _lf:
                    logic_data = json.load(_lf)
            except Exception:
                logic_data = {}
            
            speed_map = logic_data.get('race_analysis', {}).get('speed_map', {})
            speed_map_str = json.dumps(speed_map, ensure_ascii=False)
            
            _sm_check_keys = ['predicted_pace', 'track_bias', 'tactical_nodes', 'collapse_point']
            _still_missing_sm = [k for k in _sm_check_keys if not speed_map.get(k) or speed_map.get(k) == '[FILL]']
            
            if _still_missing_sm or '[FILL]' in speed_map_str:
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
                print(f"📖 參考資源：")
                print(f"   → 情報增強: .agents/skills/shared_instincts/intelligence_checklist.md (Tier 2 歷史場地 Pattern)")
                print(f"")
                notify_telegram(f"📍 **HKJC Race {r} Action Required**\n步速瀑布 (Speed Map) 尚未填寫，請查閱全景資訊。")
                
                # ── V11: File-Watch Loop for Speed Map (no more sys.exit!) ──
                print(f"\n👀 Python 正在監控 Speed Map... (每 3 秒檢查)")
                _sm_start = time.time()
                _SM_TIMEOUT = 45 * 60  # 45 minutes
                while True:
                    time.sleep(3)
                    if time.time() - _sm_start > _SM_TIMEOUT:
                        print(f"⏰ Speed Map 填寫超時！請檢查後重跑。")
                        _next_cmd(target_dir)
                        sys.exit(1)
                    try:
                        with open(logic_json, 'r', encoding='utf-8') as _smf:
                            _sm_data_check = json.load(_smf)
                        _sm_now = _sm_data_check.get('race_analysis', {}).get('speed_map', {})
                        _sm_now_missing = [k for k in _sm_check_keys if not _sm_now.get(k) or _sm_now.get(k) == '[FILL]']
                        _sm_now_str = json.dumps(_sm_now, ensure_ascii=False)
                        if not _sm_now_missing and '[FILL]' not in _sm_now_str:
                            print(f"   ✅ Speed Map 已填寫完畢！自動推進...")
                            logic_data = _sm_data_check
                            speed_map = _sm_now
                            break
                    except (json.JSONDecodeError, OSError):
                        continue
            
            # ── Step C: Read facts content ──
            try:
                with open(facts_path, 'r', encoding='utf-8') as _f:
                    facts_content = _f.read()
            except:
                facts_content = ""
            
            horses_dict = logic_data.get('horses', {})
            
            # ── Step D: Validate filled + collect pending ──
            validated_count = 0
            pending_horses = []
            
            for h in horses:
                hkey = str(h)
                h_entry = horses_dict.get(hkey, {})
                
                if not h_entry:
                    pending_horses.append(h)
                    continue
                
                h_json_str = json.dumps(
                    {k: v for k, v in h_entry.items() if k not in ('base_rating', 'final_rating')},
                    ensure_ascii=False
                )
                
                if '[FILL]' in h_json_str:
                    pending_horses.append(h)
                    continue
                
                errors = validate_hkjc_firewalls(h, h_entry, horses_dict, horses, logic_json)
                
                if errors:
                    horse_name = h_entry.get('horse_name', '')
                    print(f"\n🚨 馬號 {h}（{horse_name}）阻火牆驗證失敗！")
                    for e in errors:
                        print(f"   ❌ {e}")
                    horses_dict[hkey]['core_logic'] = '[FILL]'
                    logic_data['horses'] = horses_dict
                    with open(logic_json, 'w', encoding='utf-8') as wf:
                        json.dump(logic_data, wf, ensure_ascii=False, indent=2)
                    pending_horses.append(h)
                else:
                    validated_count += 1
            
            if validated_count > 0:
                print(f"   ✅ {validated_count}/{len(horses)} 匹馬已驗證通過")
            
            # ── Step E+F: Per-Horse Sequential Analysis (V10.1 Quality Architecture) ──
            # Process ONE horse at a time: generate work card → watch → validate → next.
            if pending_horses:
                _dir_name = os.path.basename(target_dir)
                _hk_venue = _dir_name.split("_", 1)[1] if "_" in _dir_name else ""
                _track_map = {"ShaTin": "10a_track_sha_tin_turf.md", "HappyValley": "10b_track_happy_valley.md"}
                _track_ref = _track_map.get(_hk_venue, "")
                
                _sm_pace = speed_map.get('predicted_pace', 'N/A')
                _sm_bias = speed_map.get('track_bias', 'N/A')
                
                runtime_dir = os.path.join(target_dir, ".runtime")
                os.makedirs(runtime_dir, exist_ok=True)
                
                print(f"\n{'='*60}")
                print(f"📋 Race {r}: {len(pending_horses)} 匹馬待分析（逐匹驅動模式）")
                print(f"{'='*60}")
                print(f"📖 評級矩陣: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/06_rating_aggregation.md")
                if _track_ref:
                    print(f"📖 場地模組: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/{_track_ref}")
                print(f"📍 步速: {_sm_pace} | 偏差: {_sm_bias}")
                
                completed_in_session = 0
                
                for horse_idx, ph in enumerate(pending_horses):
                    print(f"\n{'─'*60}")
                    print(f"🐎 [{horse_idx+1}/{len(pending_horses)}] 正在處理 馬號 {ph}")
                    print(f"{'─'*60}")
                    
                    # 1. Generate skeleton (if not already present)
                    skel_result = subprocess.run(
                        [PYTHON, skeleton_script, facts_path, str(r), str(ph)],
                        capture_output=True, text=True
                    )
                    if skel_result.stdout.strip():
                        for line in skel_result.stdout.strip().split('\n'):
                            if '✅' in line or '⚙️' in line:
                                print(f"   {line.strip()}")
                    
                    # 2. Reload JSON to get the nonce
                    with open(logic_json, 'r', encoding='utf-8') as _jf:
                        logic_data = json.load(_jf)
                    
                    # 3. Generate guided Work Card
                    card_path = generate_hkjc_work_card(
                        ph, facts_content, logic_data, runtime_dir,
                        _sm_pace, _sm_bias,
                        horse_idx=horse_idx, total_horses=len(pending_horses)
                    )
                    
                    # 4. Also write legacy Context file for backward compat
                    h_entry = logic_data.get('horses', {}).get(str(ph), {})
                    locked_nonce = h_entry.get('_validation_nonce', 'MISSING')
                    horse_facts_block = extract_hkjc_horse_facts_block(ph, facts_content)
                    ctx_path = os.path.join(runtime_dir, f"Horse_{ph}_Context.md")
                    with open(ctx_path, "w", encoding="utf-8") as _ctx_f:
                        _ctx_f.write(f"🔒 NONCE: {locked_nonce}\n")
                        _ctx_f.write(f"📖 分析引擎: .agents/skills/hkjc_racing/hkjc_horse_analyst/SKILL.md\n")
                        _ctx_f.write(f"📖 評級矩陣: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/06_rating_aggregation.md\n")
                        if _track_ref:
                            _ctx_f.write(f"📖 場地模組: .agents/skills/hkjc_racing/hkjc_horse_analyst/resources/{_track_ref}\n")
                        _ctx_f.write(f"📖 合規參考: .agents/skills/hkjc_racing/hkjc_compliance/SKILL.md\n")
                        _ctx_f.write(f"📍 步速判定: {_sm_pace} | 跑道偏差: {_sm_bias}\n\n")
                        _ctx_f.write(horse_facts_block)
                    
                    # Copy to Active_Horse_Context.md for backward compat
                    active_ctx = os.path.join(runtime_dir, "Active_Horse_Context.md")
                    shutil.copy2(ctx_path, active_ctx)
                    
                    # 5. Print instructions for THIS SINGLE HORSE
                    h_name = h_entry.get('horse_name', '?')
                    print(f"\n👉 LLM: 請讀取以下檔案並分析 馬號 {ph} ({h_name}):")
                    print(f"   📋 工作卡: .runtime/Horse_{ph}_WorkCard.md")
                    print(f"   📄 原始數據: .runtime/Horse_{ph}_Context.md")
                    print(f"   ✏️ 填寫目標: Race_{r}_Logic.json → horses.{ph}")
                    print(f"\n   ⚠️ 只做呢一匹馬！Python 會自動偵測變動並驗證。")
                    
                    # 6. Watch for THIS SINGLE HORSE to pass validation
                    result = watch_single_horse_hkjc(
                        logic_json, ph,
                        validate_fn=validate_hkjc_firewalls,
                        all_horses=horses,
                        poll_interval=3,
                        timeout_minutes=10
                    )
                    
                    if result:
                        completed_in_session += 1
                        print(f"\n   ✅ 馬號 {ph} ({h_name}) 驗證通過！ [{completed_in_session}/{len(pending_horses)}]")
                        print_hkjc_analysis_summary(result, ph)
                        print(f"\n   ### FLUSH: 馬號 {ph} 分析完畢 — 清除記憶準備下一匹 ###")
                    else:
                        print(f"\n   ⏰ 馬號 {ph} 超時或被中斷。")
                        print(f"   已完成 {completed_in_session}/{len(pending_horses)} 匹馬。")
                        print(f"   重跑 Orchestrator 可從斷點繼續。")
                        _next_cmd(target_dir)
                        sys.exit(0)
                
                # All horses done — reload final data
                with open(logic_json, 'r', encoding='utf-8') as _jf:
                    logic_data = json.load(_jf)
                
                print(f"\n✅ Race {r} 所有 {len(pending_horses)} 匹馬驗證通過！")
            
            # ── Step G: 3-Strike Check ──
            if strikes.get(f"race_{r}_qa", 0) >= 3:
                key = f"race_{r}_qa"
                print(f"\n🚨 [CRITICAL ALERT] Race {r} 連續 3 次 QA 失敗，恐為邊緣賽事狀況 (如新馬賽)！請人類介入調查或手動補全 `{os.path.basename(logic_json)}`。")
                print("你可以手動略過此場的 QA 檢查以繼續。")
                notify_telegram(f"❌ **HKJC Race {r} Critical QA Alert**\n連續 3 次 QA 失敗，恐為邊緣賽事狀況，請人工介入！")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step H: Auto-Verdict ──
            if not logic_data.get('race_analysis', {}).get('verdict'):
                print(f"\n⚙️ Auto-Verdict: 正在為 Race {r} 自動計算 Top 4 排序...")
                verdict = auto_compute_verdict_hkjc(logic_data, facts_path)
                with open(logic_json, 'w', encoding='utf-8') as _wf:
                    json.dump(logic_data, _wf, ensure_ascii=False, indent=2)
                t4_display = ', '.join([f"#{v['horse_number']} {v['horse_name']} ({v['grade']})" for v in verdict['top4']])
                print(f"   ✅ Top 4: {t4_display}")
                notify_telegram(f"✅ **HKJC Race {r} Auto-Verdict**\nTop 4: {t4_display}")

            # ── Step I: Compile ──
            print(f"⚙️ Race {r} JSON 填寫完畢，正在進行 Compilation (JSON -> MD)...")
            compile_cmd = [PYTHON, ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/compile_analysis_template_hkjc.py", facts_path, logic_json, "--output", an_file]
            res = subprocess.run(compile_cmd)
            
            if res.returncode != 0:
                print(f"❌ JSON 格式編譯失敗，請檢查 {os.path.basename(logic_json)} 是否為合法 JSON。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # Post-compile verification
            if not os.path.exists(an_file):
                print(f"❌ 編譯完成但 Analysis.md 未生成！請檢查 compile 腳本。")
                _next_cmd(target_dir)
                sys.exit(1)
            
            # ── Step J: Monte Carlo Simulation (mc_simulator.py v2.2) ──
            print(f"🎲 正在為 Race {r} 執行 Monte Carlo 模擬...")
            # Robust path discovery: walk up from script dir to find workspace root
            _script_dir = os.path.dirname(os.path.abspath(__file__))
            _search_dir = _script_dir
            mc_simulator_script = None
            for _ in range(8):  # Max 8 levels up
                _candidate = os.path.join(_search_dir, "mc_simulator.py")
                if os.path.exists(_candidate):
                    mc_simulator_script = _candidate
                    break
                _parent = os.path.dirname(_search_dir)
                if _parent == _search_dir:
                    break
                _search_dir = _parent
            if not mc_simulator_script:
                mc_simulator_script = os.path.join(_script_dir, "..", "..", "..", "..", "..", "mc_simulator.py")
            mc_json_out = os.path.join(target_dir, f"Race_{r}_MC_Results.json")

            if os.path.exists(mc_simulator_script):
                mc_res = subprocess.run(
                    [PYTHON, mc_simulator_script, "--input", logic_json, "--platform", "hkjc"],
                    capture_output=True, text=True
                )
                if mc_res.returncode == 0 and os.path.exists(mc_json_out):
                    print(f"✅ MC Results 生成完畢 → Race_{r}_MC_Results.json")
                    # Parse concordance summary from stdout
                    for line in mc_res.stdout.strip().split('\n'):
                        if 'Concordance' in line or '⚠️' in line:
                            print(f"   {line.strip()}")
                else:
                    print(f"⚠️ MC 模擬失敗 (非阻塞): {mc_res.stderr[:300]}")
            else:
                print(f"⚠️ mc_simulator.py 未找到: {mc_simulator_script}")
                
            # ── Step K: QA ──
            print(f"🛡️ 正在就編譯好的 Race {r} 進行 Batch QA (completion_gate_v2.py)...")
            qa_res = subprocess.run([PYTHON, ".agents/scripts/completion_gate_v2.py", an_file, "--domain", "hkjc"])
            
            if qa_res.returncode != 0:
                key = f"race_{r}_qa"
                strikes[key] = strikes.get(key, 0) + 1
                with open(strike_file, 'w', encoding='utf-8') as _sf:
                    json.dump(strikes, _sf)
                
                print(f"\n❌ Race {r} 驗證失敗 (Failed with Exit Code 1)！ Strike {strikes[key]}/3")
                print(f"👉 LLM Agent 請注意：發現字數不足、格式遺失或觸發 Fluff Regex。")
                print("請檢查對話框的 QA 報錯點，修改 JSON 後再次重跑 Orchestrator。")
                _next_cmd(target_dir)
                sys.exit(1)
            else:
                strikes[f"race_{r}_qa"] = 0
                with open(strike_file, 'w', encoding='utf-8') as _sf:
                    json.dump(strikes, _sf)
                print(f"\n{'🎉'*10}")
                print(f"✅ Race {r} 分析完成並通過 QA！")
                print(f"{'🎉'*10}")
            
            # ── Step L: Auto-advance to next race (no exit) ──
            if r < total_races:
                print(f"\n{'─'*60}")
                print(f"🔄 Race {r} 完成！自動推進至 Race {r + 1}...")
                print(f"{'─'*60}")
                # Continue the for-loop to process next race automatically
                continue

    # --- STATE 4 & 5: Completion ---
    print("🏆 State 4: 全日賽事分析合規過關！正在產製 Excel 報告...")
    reports_script = ".agents/skills/hkjc_racing/hkjc_wong_choi/scripts/generate_hkjc_reports.py"
    if os.path.exists(reports_script):
        subprocess.run([PYTHON, reports_script, "--target_dir", target_dir])
    else:
        print("⚠️ generate_hkjc_reports.py 未找到，略過報告生成。")
    subprocess.run([PYTHON, ".agents/scripts/session_cost_tracker.py", target_dir, "--domain", "hkjc"])
    
    print("\n🎉 [SUCCESS] HKJC Wong Choi Pipeline 任務全數擊破！")
    notify_telegram("🎉 **HKJC Wong Choi 任務完成**\n所有分析已順利通過 QA 及編譯！")
    
if __name__ == "__main__":
    main()
