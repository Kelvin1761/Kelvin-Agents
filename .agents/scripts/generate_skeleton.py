#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
generate_skeleton.py — V4 Strict Fidelity Auto-Generator
===========================================================
"""
import re
from pathlib import Path

def detect_mode(text: str) -> str:
    if '### 馬匹 #' in text: return 'au'
    elif '### 馬號' in text: return 'hkjc'
    return 'au'

def parse_facts_md_au(text: str) -> list[dict]:
    horse_pattern = re.compile(r'^### 馬匹 #(\d+) (.+?) \(檔位 (\d+)\)', re.MULTILINE)
    matches = list(horse_pattern.finditer(text))
    horses = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        
        table = _extract_between(block, '📋 完整賽績檔案', '📊 段速趨勢')
        trends = _extract_between(block, '📊 段速趨勢', '⚡ EEM 能量摘要')
        eem = _extract_between(block, '⚡ EEM 能量摘要', '🔗 賽績線')
        formline = _extract_between(block, '🔗 賽績線', '🔧 引擎與距離')
        
        horses.append({
            'num': int(match.group(1)), 'name': match.group(2).strip(), 'barrier': int(match.group(3)),
            'table': table, 'trends': trends, 'eem': eem, 'formline': formline,
            'jockey': '', 'trainer': '', 'weight': 0, 'mode': 'au',
        })
    return horses

def parse_facts_md_hkjc(text: str, trainers_dict: dict = None) -> list[dict]:
    if trainers_dict is None: trainers_dict = {}
    horse_pattern = re.compile(r'^### 馬號 (\d+) — (.+?)(?:\s*\|)', re.MULTILINE)
    matches = list(horse_pattern.finditer(text))
    horses = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        
        header_line = block.split('\n')[0]
        # Handle "(無往績記錄)" case directly
        if '(無往績記錄)' in block:
            table = '(無往績記錄)'
            summary = ''
            trends = ''
            engine = ''
            new_dims = ''
            formline = ''
        else:
            summary = _extract_between(block, '📌 **賽績總結', '📋 **完整賽績檔案')
            if not summary:
                summary = _extract_between(block, '📌 賽績總結', '📋 完整賽績檔案')
            
            table = _extract_between(block, '📋 **完整賽績檔案', '📊 **段速趨勢')
            if not table:
                table = _extract_between(block, '📋 完整賽績檔案', '📊 段速趨勢')
                
            if '📋 **較舊歷史賽績' in table: table = table[:table.find('📋 **較舊歷史賽績')].strip()
            if '📋 較舊歷史賽績' in table: table = table[:table.find('📋 較舊歷史賽績')].strip()
                
            trends = _extract_between(block, '📊 **段速趨勢', '🔧 **引擎距離')
            if not trends: trends = _extract_between(block, '📊 段速趨勢', '🔧 引擎距離')
            
            engine = _extract_between(block, '🔧 **引擎距離', '📏 **頭馬距離')
            if not engine: engine = _extract_between(block, '🔧 引擎距離', '📏 頭馬距離')
            if not engine: engine = _extract_between(block, '🔧 **引擎距離', '💡 **LLM')
            
            new_dims = '\n'.join(filter(None, [
                _extract_between(block, '📏 **頭馬距離', '📊 **體重趨勢') or _extract_between(block, '📏 頭馬距離', '📊 體重趨勢'),
                _extract_between(block, '📊 **體重趨勢', '🔧 **配備變動') or _extract_between(block, '📊 體重趨勢', '🔧 配備變動'),
                _extract_between(block, '🔧 **配備變動', '📈 **評分變動') or _extract_between(block, '🔧 配備變動', '📈 評分變動'),
                _extract_between(block, '📈 **評分變動', '🏃 **走位 PI') or _extract_between(block, '📈 評分變動', '🏃 走位 PI'),
                _extract_between(block, '🏃 **走位 PI', '🔗 **賽績線') or _extract_between(block, '🏃 走位 PI', '🔗 賽績線') or _extract_between(block, '🏃 **走位 PI', '💡 **LLM')
            ]))
            formline = _extract_between(block, '🔗 **賽績線', '💡 **LLM')
            if not formline: formline = _extract_between(block, '🔗 賽績線', '💡 LLM')
            
        jockey_m = re.search(r'騎師:\s*([^\s\|]+)', header_line)
        trainer_m = re.search(r'練馬師:\s*([^\s\|]+)', header_line)
        weight_m = re.search(r'負磅:\s*(\d+)', header_line)
        barrier_m = re.search(r'檔位:\s*(\d+)', header_line)

        horse_num = int(match.group(1))
        horse_trainer = trainer_m.group(1).strip() if trainer_m else trainers_dict.get(horse_num, '')

        horses.append({
            'num': horse_num, 'name': match.group(2).strip(), 'barrier': int(barrier_m.group(1)) if barrier_m else 0,
            'jockey': jockey_m.group(1).replace('(-7)', '').replace('(-5)', '').replace('(-3)', '').strip() if jockey_m else '', 
            'trainer': horse_trainer,
            'weight': int(weight_m.group(1)) if weight_m else 0,
            'summary': summary, 'table': table, 'trends': trends, 'engine': engine, 'new_dims': new_dims, 'formline': formline,
            'mode': 'hkjc',
        })
    return horses

def _extract_between(block: str, start_marker: str, end_marker: str) -> str:
    start_idx = block.find(start_marker)
    if start_idx == -1: return ''
    line_start = block.rfind('\n', 0, start_idx)
    line_start = line_start + 1 if line_start != -1 else 0
    end_idx = block.find(end_marker, start_idx + len(start_marker))
    if end_idx == -1: return block[line_start:].strip()
    line_end = block.rfind('\n', 0, end_idx)
    if line_end <= line_start: return block[line_start:end_idx].strip()
    return block[line_start:line_end].strip()

def _truncate_table(table_str: str, max_rows: int = 6) -> str:
    lines = table_str.strip().split('\n')
    out_lines = []
    data_row_count = 0
    truncated = False
    
    for line in lines:
        if "💡 LLM 輸出指示" in line or "💡 **LLM 輸出指示**: 在你輸出的分析報告表格中" in line:
            continue
        is_table_row = line.strip().startswith('|') and line.strip().endswith('|')
        if is_table_row:
            clean_str = line.strip().replace('|', '').replace(' ', '').replace(':', '').replace('-', '')
            is_delimiter = len(clean_str) == 0 and '-' in line
            is_header = ('日期' in line or '#' in line) and not is_delimiter and data_row_count == 0
            
            stripped_line = line.strip()
            if stripped_line.endswith('|'):
                stripped_line = stripped_line[:-1]
                
            if is_header or is_delimiter:
                out_lines.append(stripped_line)
            else:
                data_row_count += 1
                if data_row_count <= max_rows:
                    out_lines.append(stripped_line)
                else:
                    truncated = True
        else:
            if truncated and "> *(...空間所限" not in out_lines[-1]:
                out_lines.append("> *(...空間所限，只截取最前 6 場；研讀完整紀錄請強烈參考 Facts.md...)*")
                truncated = False
            out_lines.append(line)
            
    if truncated and "> *(...空間所限" not in out_lines[-1]:
        out_lines.append("> *(...空間所限，只截取最前 6 場；研讀完整紀錄請強烈參考 Facts.md...)*")
        
    return '\n'.join(out_lines)

# ── Generating Horse Skeletons ──────────────────────────────────────────

def generate_horse_skeleton_hkjc(h: dict) -> str:
    lines = []
    jockey_str = h['jockey'] if h['jockey'] else '[FILL]'
    trainer_str = h['trainer'] if h['trainer'] else '[FILL]'
    weight_str = str(h['weight']) if h['weight'] else '[FILL]'

    lines.append(f"**【No.{h['num']}】 {h['name']}** | 騎師:{jockey_str} | 練馬師:{trainer_str} | 負磅:{weight_str} | 檔位:{h['barrier']}")
    lines.append('**📌 情境標記:** `[FILL]`\n')
    
    lines.append('**賽績總結:**')
    if h.get('summary') and '(無往績記錄)' not in h.get('summary'): 
        lines.append(h['summary'].replace('📌 **賽績總結:**','').replace('📌 賽績總結:','').strip())
    else:
        lines.append('- **近六場:** `[FILL]`')
        lines.append('- **休後復出:** [FILL] 日')
        lines.append('- **統計:** 季內 [FILL] | 同程 [FILL] | 同場同程 [FILL]')
    lines.append('')

    if h['table'] and '(無往績記錄)' not in h['table']:
        lines.append('**📋 完整賽績與寬恕檔案 (包含 Step 12 判斷):**\n')
        lines.append(_truncate_table(h['table']) + '\n')
        lines.append('- **逐場寬恕判定:** `[JSON Array 格式, 對應上表由最新到最舊每一場, 例如: ["[-]", "受阻", "[-]", "泥沙", "[-]"] (無寬恕必須填 "[-]")]`\n')
    else:
        lines.append('**完整賽績檔案:** (無往績記錄)\n')

    # Optional facts fields
    if h.get('trends') and '(無往績記錄)' not in h.get('trends'): lines.append(h['trends'] + '\n')
    if h.get('engine') and '(無往績記錄)' not in h.get('engine'): lines.append(h['engine'] + '\n')
    if h.get('new_dims'): lines.append(h['new_dims'] + '\n')

    lines.append('**馬匹分析:**')
    lines.extend([
        '- **走勢趨勢 (Step 10.3+):** [FILL]',
        '- **隱藏賽績 (Step 6+12):** [FILL]',
        '- **贏馬回落風險 / 穩定性 (Step 5):** [FILL]',
        '- **級數評估 (Step 8.1):** [FILL]',
        '- **路程場地適性 (Step 2):** [FILL]',
        '- **引擎距離 (Step 2.6):** [FILL]',
        '- **配備變動 (Step 6):** [FILL]',
        '- **部署與練馬師訊號 (Step 8.2):** [FILL]',
        '- **人馬/騎練配搭 (Step 2.5):** [FILL]',
        '- **步速段速 (Step 0+10):** [FILL]',
        '- **競賽事件 / 馬匹特性:** [FILL]\n'
    ])

    if h.get('formline') and '(無往績記錄)' not in h.get('formline'):
        lines.append('**🔗 賽績線 (近績對手強弱追蹤庫):**\n')
        lines.append(h['formline'].replace('🔗 **賽績線 (近 5 場正式賽事，官方追蹤):**','').replace('🔗 賽績線 (近 5 場正式賽事，官方追蹤):','').strip() + '\n')
        lines.append('- **綜合結論:** `[FILL]`\n')
    else:
        lines.append('**🔗 賽績線:** (無往績記錄)\n')

    lines.append('**📊 評級矩陣 (Step 14):**')
    lines.extend([
        '- 穩定性 [核心]: `[FILL]` | 理據: `[FILL]`',
        '- 段速質量 [核心]: `[FILL]` | 理據: `[FILL]`',
        '- EEM 潛力 [半核心]: `[FILL]` | 理據: `[FILL]`',
        '- 練馬師訊號 [半核心]: `[FILL]` | 理據: `[FILL]`',
        '- 情境適配 [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- 路程/新鮮度 [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- 賽績線 [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- 級數優勢 [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- 寬恕加分: `[FILL]` | 理據: `[FILL]`\n'
    ])

    lines.extend([
        '**🔢 矩陣算術:** 核心✅=[FILL] | 半核心✅=[FILL] | 輔助✅=[FILL] (含寬恕加分) | 總❌=[FILL] | 核心❌=[FILL] → 查表命中行=[FILL]',
        '**14.2 基礎評級:** `[FILL]` | `[FILL]`',
        '**14.2B 微調:** `[FILL]` | `[FILL]`',
        '**14.3 覆蓋:** `[FILL]`\n'
    ])

    lines.append('**💡 結論與評語 (Conclusion & Analyst View):**')
    lines.extend([
        '> - **核心邏輯:** [呢匹馬今場為什麼會/不會跑好？篇幅約 80-100 字。寫作指引：強烈建議參考「馬性與數據結合」框架 (1)點出最忌諱/擅長條件 (如谷草/田草/泥地、場地偏差適性等) 及 (2)配合量化數據(如L400/EEM/Matrix✅)。⚠️ 自由度授權：若你在分析中發現其他「極具價值的特殊盲點或獨特賽績角度」，你有完全的自由將其作為核心邏輯發表。必須保持 Forensic 級深度，嚴禁空泛馬評。請適當使用點列式 (Bullet points) 分行寫出不同論點以方便閱讀。]',
        '> - **最大競爭優勢:** [明確列出]',
        '> - **最大失敗風險:** [若為A-或以上必須寫,否則明確寫「無」]\n'
    ])

    lines.append('**⭐ 最終評級:** `[FILL]`\n')
    lines.append('🐴⚡ **冷門馬訊號 (Underhorse Signal):** `[觸發 / 未觸發]`')
    lines.append('若觸發,必須列明:')
    lines.append('- **受惠條件:** `[若步速比預測更快/更慢 / 若天氣變化導致場地偏軟 / 若核心領放馬退出 / 若跑道偏差轉換 / 若AWT轉草地 等]`')
    lines.append('- **理由:** [簡述為何此馬會在此條件下受惠,如:「後追型引擎配合快步速」、「濕地血統優勢」、「放頭馬退出後可單騎偏襲」、「谷草內檔偏差受惠」]')
    return '\n'.join(lines)

def generate_horse_skeleton_au(h: dict) -> str:
    lines = []
    lines.append(f"### 【No.{h['num']}】{h['name']} (檔位:{h['barrier']}) | 騎師:[FILL] / 練馬師:[FILL] | 負重:[FILL]kg | 評分:[FILL]")
    lines.append('**📌 情境標記:** `[FILL]`\n')
    
    lines.append('#### ⏱️ 近績解構')
    lines.append('- **近績序列:** `[FILL]` (剛戰 → 最舊) | **狀態週期:** `[FILL]`')
    lines.append('- **統計數據:** 季內 [FILL] | 同程 [FILL] | 同場同程 [FILL]')
    lines.append('- **趨勢總評:** [FILL]\n')

    lines.append('#### 📋 完整賽績與寬恕檔案')
    if h.get('table'): lines.append(_truncate_table(h['table']))
    lines.append('')
    if h.get('trends'): lines.append(h['trends'] + '\n')
    if h.get('eem'): lines.append(h['eem'] + '\n')

    lines.append('#### 🐴 馬匹剖析')
    lines.extend([
        '- **班次負重:** [FILL]',
        '- **引擎距離:** [FILL]',
        '- **步態場地:** [FILL]',
        '- **配備意圖:** [FILL]',
        '- **人馬組合:** [FILL]\n'
    ])

    if h.get('formline'): lines.append(h['formline'] + '\n')

    lines.append('#### 🧭 陣型預判')
    lines.append('- 預計守位 (800m 處):[位置],形勢 `[極利 / 一般 / 陷阱]`\n')

    lines.append('#### ⚠️ 風險儀表板')
    lines.append('- 重大風險:`[FILL]` | 穩定指數:`[FILL]`\n')

    lines.append('#### 📊 評級矩陣')
    lines.extend([
        '- **狀態與穩定性** [核心]: `[FILL]` | 理據: `[FILL]`',
        '- **段速與引擎** [核心]: `[FILL]` | 理據: `[FILL]`',
        '- **EEM與形勢** [半核心]: `[FILL]` | 理據: `[FILL]`',
        '- **騎練訊號** [半核心]: `[FILL]` | 理據: `[FILL]`',
        '- **級數與負重** [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- **場地適性** [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- **賽績線** [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- **裝備與距離** [輔助]: `[FILL]` | 理據: `[FILL]`',
        '- **編號矩陣:** 核心✅=[FILL] | 半核心✅=[FILL] | 輔助✅=[FILL] | 總❌=[FILL] | 核心❌=[FILL] → 查表命中行=[FILL]',
        '- **基礎評級:** `[FILL]` | **規則**: `[FILL]`',
        '- **微調:** `[FILL]` | **觸發**: `[FILL]`',
        '- **覆蓋規則:** `[FILL]`\n'
    ])

    lines.append('#### 💡 核心邏輯與結論')
    lines.extend([
        '> - **核心邏輯:** [FILL]',
        '> - **最大競爭優勢:** [FILL]',
        '> - **最大失敗風險:** [FILL]\n'
    ])

    lines.append('⭐ **最終評級:** `[FILL]`\n')

    lines.append('📗📙 **場地雙軌評級 (Dual-Track Grade):** `[若賽道 STABLE，請直接填寫 "無"。若判定為 UNSTABLE，請按此格式輸出: 📗預期場地(...) / 📙備選場地(...)]`\n')

    lines.append('🐴⚡ **冷門馬訊號 (Underhorse Signal):** `[觸發 / 未觸發]`')
    lines.extend([
        '若觸發,必須列明:',
        '- **受惠條件:** `[FILL]`',
        '- **理由:** [FILL]'
    ])
    return '\n'.join(lines)


# ── Verdict Generators ──────────────────────────────────────────────────

def generate_final_verdict_hkjc() -> str:
    lines = []
    lines.append('#### [第三部分] 最終預測 (The Verdict)\n')
    lines.append('- **跑道形勢:** [FILL]')
    lines.append('- **信心指數:** `[極高/高/中高/中/低]`')
    lines.append('- **關鍵變數:** [FILL]\n')
    lines.append('**🏆 Top 4 位置精選**\n')
    for label in ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']:
        lines.extend([label, '- **馬號及馬名:** [FILL]', '- **評級與✅數量:** `[FILL]` | ✅ [FILL]', '- **核心理據:** [FILL]', '- **最大風險:** [FILL]\n'])
    lines.extend([
        '**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**',
        '🥇 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]',
        '🥈 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅:[FILL]\n',
        '**🔄 步速逆轉保險 (Pace Flip Insurance):**',
        '- 若步速比預測更快 → 最受惠: [FILL] | 最受損: [FILL]',
        '- 若步速比預測更慢 → 最受惠: [FILL] | 最受損: [FILL]\n',
        '**🚨 緊急煞車檢查 (Emergency Brake Protocol):**',
        '- [FILL]\n',
        '---\n',
        '#### [第四部分] 分析盲區(緊隨第三部分)\n',
        '**1. 段速含金量:** [FILL]',
        '**2. 風險管理:** [FILL]',
        '**3. 試閘與預期假象:** [FILL]',
        '**4. 特定與老馬風險:** [FILL]',
        '**5. 步速情境分支:**',
        '- 快步速:最利 → [FILL];最不利 → [FILL]',
        '- 慢步速:最利 → [FILL];最不利 → [FILL]\n',
        '**6. 🎯 步速崩潰冷門 (Pace Collapse Dark Horse) [強制檢查點]:**',
        '[FILL]\n',
        '**🐴⚡ 冷門馬總計 (Underhorse Signal Summary):**',
        '[FILL]\n'
    ])
    return '\n'.join(lines)

def generate_final_verdict_au() -> str:
    lines = []
    lines.append('## [第三部分] 🏆 全場最終決策')
    lines.append('**Speed Map 回顧:** [預期步速] | 領放群: [Names] | 受牽制: [Names]\n')
    lines.append('**Top 4 位置精選**\n')
    for label in ['🥇 **第一選**', '🥈 **第二選**', '🥉 **第三選**', '🏅 **第四選**']:
        lines.extend([label, '- **馬號及馬名:** [FILL]', '- **評級與✅數量:** `[FILL]` | ✅ [FILL]', '- **核心理據:** [FILL]', '- **最大風險:** [FILL]\n'])
    lines.extend([
        '---',
        '**🎯 Top 2 入三甲信心度 (Top 2 Place Confidence)**',
        '🥇 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅: [FILL]',
        '🥈 [FILL]:`[🟢極高 / 🟢高 / 🟡中 / 🔴低]` — 最大威脅: [FILL]\n',
        '---',
        '🎰 Exotic 建議:[FILL]\n',
        '---',
        '## [第四部分] 分析陷阱\n',
        '- **市場預期警告:** [FILL]',
        '- **🔄 步速逆轉保險 (Pace Flip Insurance):**',
        '  - 若步速比預測更快 → Top 4 中最受惠:`[FILL]` | 最受損:`[FILL]`',
        '  - 若步速比預測更慢 → Top 4 中最受惠:`[FILL]` | 最受損:`[FILL]`',
        '- **整體潛在機會建議:** [FILL]\n',
        '---',
        '## [第五部分] 📊 數據庫匯出 (CSV)\n',
        '```csv',
        'race_id,horse_number,horse_name,win_odds,place_odds,verdict,risk_level',
        '[FILL: 由 compute_rating_matrix.py 自動生成]',
        '```\n'
    ])
    return '\n'.join(lines)

# ── Main ─────────────────────────────────────────────────────────────────

def main():
    import argparse as _ap
    parser = _ap.ArgumentParser(description='generate_skeleton.py V4 — Perfect HKJC Match')
    parser.add_argument('facts', help='Facts.md 路徑')
    parser.add_argument('--output', '-o', default=None, help='輸出 Analysis.md 路徑')
    parser.add_argument('--batch-size', type=int, default=3, help='每批馬匹數')
    parser.add_argument('--mode', choices=['au', 'hkjc'], default=None, help='模式：au 或 hkjc')
    args = parser.parse_args()

    facts_path = Path(args.facts)
    if not facts_path.exists(): sys.exit(1)

    text = facts_path.read_text(encoding='utf-8')
    mode = args.mode or detect_mode(text)
    
    trainers_dict = {}
    if mode == 'hkjc':
        rc_name = facts_path.stem.replace('Facts', '排位表') + '.md'
        rc_path = facts_path.parent / rc_name
        if rc_path.exists():
            import re
            rc_content = rc_path.read_text(encoding='utf-8')
            blocks = rc_content.split('馬號: ')
            for block in blocks[1:]:
                num_m = re.search(r'^(\d+)', block)
                trainer_m = re.search(r'練馬師:\s*([^\n]+)', block)
                if num_m and trainer_m:
                    trainers_dict[int(num_m.group(1))] = trainer_m.group(1).strip()
                    
    horses = parse_facts_md_hkjc(text, trainers_dict) if mode == 'hkjc' else parse_facts_md_au(text)
    if not horses: sys.exit(1)

    print(f"📝 模式: {mode.upper()} | 馬匹: {len(horses)}")

    def build_au_battlefield_panorama(facts_path: str) -> str:
        import subprocess, os, re
        rc_path = str(facts_path).replace('Facts.md', 'Racecard.md')
        if not os.path.exists(rc_path):
            return "## [第一部分] 🗺️ 戰場全景\n\n[FILL — 由 LLM 填充]\n"

        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            gen_script = os.path.join(script_dir, 'au_speed_map_generator.py')
            res = subprocess.run([sys.executable, gen_script, rc_path], capture_output=True, text=True)
            out = res.stdout

            pace_type = "[FILL]"
            m = re.search(r'PACE_TYPE_SUGGESTION:\s*(.*)', out)
            if m: pace_type = m.group(1).strip()

            leaders = "[FILL]"
            on_pace = "[FILL]"
            mid_pack = "[FILL]"
            closers = "[FILL]"

            m_lead = re.search(r'領放群 \([^)]*\):\s*(.*)', out)
            if m_lead: leaders = m_lead.group(1).strip()
            m_on = re.search(r'前中段 \([^)]*\):\s*(.*)', out)
            if m_on: on_pace = m_on.group(1).strip()
            m_mid = re.search(r'中後段 \([^)]*\):\s*(.*)', out)
            if m_mid: mid_pack = m_mid.group(1).strip()
            m_cls = re.search(r'後上群 \([^)]*\):\s*(.*)', out)
            if m_cls: closers = m_cls.group(1).strip()

            return f"""## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | [FILL] |
| **賽事類型** | **`[STANDARD RACE 標準彎道賽]`** |
| 天氣 / 場地 | [FILL] |
| 跑道偏差 | [FILL] |
| 步速預測 | {pace_type} |
| 戰術節點 | [FILL] |

**📍 Speed Map (速度地圖):**
- 領放群: {leaders}
- 前中段: {on_pace}
- 中後段: {mid_pack}
- 後上群: {closers}

**🏃 步速瀑布推演 (Step 10 結論):**
- 領放馬: [FILL] | 搶位數量: [FILL]
- 預計步速: {pace_type} | 崩潰點: [FILL]
- 偏差方向: [FILL]
- 受惠: [FILL] | 受損: [FILL]
"""
        except Exception as e:
            return f"## [第一部分] 🗺️ 戰場全景\n\n[FILL — 生成錯誤: {e}]\n"

    def build_hkjc_battlefield_panorama(text: str) -> str:
        import re
        venue = "[馬場]"
        dist = "[路程]"
        cls_grade = "[班次]"
        
        m = re.search(r'場地:\s*([^|]*?)\s*\|\s*距離:\s*([^|]*?)\s*\|\s*班次:\s*([^\n]+)', text)
        if m:
            v_val = m.group(1).strip()
            if v_val: venue = v_val
            d_val = m.group(2).strip()
            if d_val and d_val != "0m": dist = d_val
            c_val = m.group(3).strip()
            if c_val: cls_grade = c_val
            
        race_type = "`[全天候跑道 (AWT)]`" if "AWT" in venue or "泥地" in text else "`[草地]`"
        
        return f"""## [第一部分] 🗺️ 戰場全景

| 項目 | 內容 |
|:---|:---|
| 賽事格局 | {cls_grade} / {dist} / {race_type.replace('`[','').replace(']`','')} / {venue} |
| **賽事類型** | **{race_type}** |
| 天氣 / 場地 | [FILL] |
| 跑道偏差 | [FILL] |
| 步速預測 | [FILL] |
| 戰術節點 | [FILL] |

**📍 Speed Map (速度地圖):**
- 領放群: [FILL]
- 前中段: [FILL]
- 中後段: [FILL]
- 後上群: [FILL]

**🏃 步速瀑布推演 (Step 0 結論):**
- 領放馬: [FILL] | 搶位數量: [FILL]
- 預計步速: [FILL] | 崩潰點: [FILL]
- 偏差方向: [FILL]
- 受惠: [FILL] | 受損: [FILL]
"""

    if mode == 'au':
        body = [build_au_battlefield_panorama(args.facts)]
    else:
        body = [build_hkjc_battlefield_panorama(text)]

    body.extend(['---\n', '#### [第二部分] 全場馬匹深度分析\n' if mode == 'hkjc' else '## [第二部分] 🔬 深度顯微鏡\n'])
    
    skel_fn = generate_horse_skeleton_hkjc if mode == 'hkjc' else generate_horse_skeleton_au
    for i, horse in enumerate(horses):
        body.append(skel_fn(horse))
        body.append('---\n')
        if ((i % args.batch_size) + 1) == args.batch_size or i == len(horses) - 1:
            body.append(f'✅ 批次完成:{i + 1}/{len(horses)} 馬匹 | ' +
                        ('每匹含 📌情境+賽績+表格+分析(10項)+📋寬恕+🔗賽績線+📊矩陣+💡評語+⭐評級 全 9 欄位 | D 級馬 ≥300 字 ✔️' if mode == 'hkjc' else
                         '每匹含 ⏱️近績+📋賽績檔案+🐴剖析+📋寬恕+🔗賽績線+🧭陣型+⚠️風險+📊矩陣+💡核心邏輯+⭐評級 全 10 欄位 | D 級馬 ≥300 字 ✔️'))
            body.append('')

    body.append('---\n')
    body.append(generate_final_verdict_hkjc() if mode == 'hkjc' else generate_final_verdict_au())

    out_path = Path(args.output) if args.output else facts_path.with_name(facts_path.stem.replace('Facts', 'Analysis') + '.md')
    out_path.write_text('\n'.join(body), encoding='utf-8')
    print(f"✅ 骨架生成完畢 → {out_path}")

if __name__ == '__main__': main()
