#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
scrape_hkjc_horse_profile.py — HKJC 馬匹往績 SSR Scraper
==========================================================
Scrapes the horse profile page (Server-Side Rendered HTML) from HKJC.
Extracts full race history including: margin, trainer, class, rating,
running positions, finish time, declared weight, gear.

Also computes trend dimensions:
  - Weight trend (體重趨勢)
  - Gear change detection (配備變動)
  - Margin trend (頭馬距離趨勢)
  - Rating trend (評分變動)
  - Running position PI (沿途走位精確化)

Usage:
    python3 scrape_hkjc_horse_profile.py HK_2024_K416
    python3 scrape_hkjc_horse_profile.py HK_2024_K416 --today-weight 1180 --today-gear TT
    python3 scrape_hkjc_horse_profile.py --json HK_2024_K416
"""

import sys
import re
import json
import time
import os
import argparse
from typing import Optional

import requests
from bs4 import BeautifulSoup

# ── Disk Cache Setup ────────────────────────────────────────────────────────
CACHE_DIR = os.path.join(os.getcwd(), '.hkjc_cache')
for i, arg in enumerate(sys.argv):
    if arg == '--output' and i + 1 < len(sys.argv):
        out_dir = os.path.dirname(os.path.abspath(sys.argv[i+1]))
        if out_dir: CACHE_DIR = os.path.join(out_dir, '.hkjc_cache')
        break
    elif arg.endswith('.txt') or arg.endswith('.md') or arg.endswith('.csv'):
        if os.path.exists(arg):
            file_dir = os.path.dirname(os.path.abspath(arg))
            if file_dir: CACHE_DIR = os.path.join(file_dir, '.hkjc_cache')

os.makedirs(CACHE_DIR, exist_ok=True)
PROFILE_CACHE_FILE = os.path.join(CACHE_DIR, 'profile_cache.json')

def _load_profile_cache():
    if os.path.exists(PROFILE_CACHE_FILE):
        try:
            with open(PROFILE_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_profile_cache(cache):
    try:
        with open(PROFILE_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

_profile_cache = _load_profile_cache()



# ── HKJC Margin Format → Numeric Lengths ────────────────────────────────
MARGIN_MAP = {
    '---': 0.0, '頭': 0.0,      # Winner
    '短頭': 0.1, 'SH': 0.1,
    '頸': 0.25, 'NK': 0.25, 'Nk': 0.25,
    '半': 0.5,
    '3/4': 0.75,
}


def parse_margin(margin_str: str) -> Optional[float]:
    """Convert HKJC margin string to numeric lengths.
    
    Examples: '2-1/2' → 2.5, '頸' → 0.25, '短頭' → 0.1, '---' → 0.0
    """
    if not margin_str or margin_str.strip() == '':
        return None
    s = margin_str.strip()
    
    # Direct lookup
    if s in MARGIN_MAP:
        return MARGIN_MAP[s]
    
    # Pattern: X-Y/Z (e.g. '2-1/2', '1-1/4', '3-3/4')
    m = re.match(r'^(\d+)-(\d+)/(\d+)$', s)
    if m:
        whole = int(m.group(1))
        numer = int(m.group(2))
        denom = int(m.group(3))
        return whole + numer / denom
    
    # Pattern: X/Y (e.g. '1/2', '3/4')
    m = re.match(r'^(\d+)/(\d+)$', s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    
    # Pattern: pure number (e.g. '1', '2', '3', '10')
    m = re.match(r'^(\d+)$', s)
    if m:
        return float(m.group(1))
    
    # Pattern: X-Y (e.g. '1-3' meaning 1 and 3/4? unlikely, but safe)
    # Actually in HKJC '1-3/4' is common, but '1-3' alone is unusual
    
    return None


def parse_running_positions(pos_str: str) -> list[int]:
    """Parse running positions string into list of ints.
    
    Examples: '4 5 5 8' → [4, 5, 5, 8], '- 9 5½ 9 4½ 5 2¾' → [9, 9, 5]
    """
    if not pos_str:
        return []
    # Split by whitespace, filter to integers
    positions = []
    for part in pos_str.strip().split():
        # Remove fractions like '5½' → just take the integer part
        clean = re.sub(r'[½¼¾]', '', part)
        if clean == '-':
            continue
        try:
            positions.append(int(clean))
        except ValueError:
            continue
    return positions


def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """Convert HKJC time format to seconds.
    
    Examples: '1.22.36' → 82.36, '0.56.65' → 56.65
    """
    if not time_str or time_str.strip() in ('', '-'):
        return None
    m = re.match(r'^(\d+)\.(\d{2})\.(\d{2})$', time_str.strip())
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        centis = int(m.group(3))
        return mins * 60 + secs + centis / 100
    return None


# ── Core Scraper ──────────────────────────────────────────────────────────

def scrape_horse_profile(horse_id: str, timeout: int = 15) -> dict:
    """Scrape HKJC horse profile page (SSR HTML).
    
    Args:
        horse_id: e.g. 'HK_2024_K416'
        timeout: HTTP request timeout in seconds
        
    Returns:
        {
            'horse_id': 'HK_2024_K416',
            'name': '有情有義',
            'trainer': '方嘉柏',
            'entries': [
                {
                    'race_index': 476, 'placing': 8, 'date': '01/03/26',
                    'venue_track': '沙田草地"B+2"', 'distance': 1400,
                    'going': '好', 'class_grade': '4', 'barrier': 2,
                    'rating': 42, 'trainer': '方嘉柏', 'jockey': '巴度',
                    'margin_raw': '2-1/2', 'margin_numeric': 2.5,
                    'weight_carried': 118, 'running_positions': [4, 5, 5, 8],
                    'finish_time_raw': '1.22.36', 'finish_time_secs': 82.36,
                    'declared_weight': 1175, 'gear': 'TT',
                    'race_link': '/zh-hk/local/information/localresults?...'
                },
                ...
            ],
            'error': None
        }
    """
    global _profile_cache
    now = time.time()
    
    # Check disk cache (48 hours expiry)
    if horse_id in _profile_cache:
        cached = _profile_cache[horse_id]
        if now - cached.get('_ts', 0) < 86400 * 2:
            return cached['data']

    if '_' in horse_id:
        url = f"https://racing.hkjc.com/zh-hk/local/information/horse?horseid={horse_id}"
    else:
        url = f"https://racing.hkjc.com/zh-hk/local/information/horse?HorseNo={horse_id}"
    
    result = {
        'horse_id': horse_id,
        'name': '',
        'trainer': '',
        'entries': [],
        'error': None,
    }
    
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code != 200:
            result['error'] = f"HTTP {resp.status_code}"
            return result
    except Exception as e:
        result['error'] = str(e)
        return result
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Extract horse name from page title
    title = soup.find('title')
    if title:
        title_text = title.get_text(strip=True)
        # Format: "有情有義 - 馬匹資料 - ..."
        name_match = re.match(r'^(.+?)\s*-\s*馬匹資料', title_text)
        if name_match:
            result['name'] = name_match.group(1).strip()
    
    # Find all data rows (rows with >= 15 htable_text/htable_eng_text cells)
    all_rows = soup.find_all('tr')
    
    for row in all_rows:
        cells = row.find_all('td')
        if len(cells) < 19:
            continue
        
        # Check this is a data row (first cell should have htable_text class)
        first_class = cells[0].get('class', [])
        if 'htable_text' not in first_class and 'htable_eng_text' not in first_class:
            continue
        
        # Skip season header rows (colspan)
        if cells[0].get('colspan'):
            continue
        
        try:
            entry = {}
            
            # [0] 場次 — contains link to results
            race_text = cells[0].get_text(strip=True)
            entry['race_index'] = int(race_text) if race_text.isdigit() else 0
            race_link = cells[0].find('a')
            entry['race_link'] = race_link.get('href', '') if race_link else ''
            
            # Extract race_date and race_no from link
            if entry['race_link']:
                date_m = re.search(r'racedate=(\d{4}/\d{2}/\d{2})', entry['race_link'])
                rno_m = re.search(r'RaceNo=(\d+)', entry['race_link'])
                entry['race_date_full'] = date_m.group(1) if date_m else ''
                entry['race_no'] = int(rno_m.group(1)) if rno_m else 0
                # Derive racecourse from link
                rc_m = re.search(r'Racecourse=(\w+)', entry['race_link'])
                entry['racecourse'] = rc_m.group(1) if rc_m else ''
            
            # [1] 名次
            placing_text = cells[1].get_text(strip=True)
            entry['placing'] = int(placing_text) if placing_text.isdigit() else 0
            
            # [2] 日期
            entry['date'] = cells[2].get_text(strip=True)
            
            # [3] 馬場/跑道/賽道
            entry['venue_track'] = cells[3].get_text(strip=True)
            
            # [4] 途程
            dist_text = cells[4].get_text(strip=True)
            entry['distance'] = int(dist_text) if dist_text.isdigit() else 0
            
            # [5] 場地狀況
            entry['going'] = cells[5].get_text(strip=True)
            
            # [6] 賽事班次
            entry['class_grade'] = cells[6].get_text(strip=True)
            
            # [7] 檔位
            barrier_text = cells[7].get_text(strip=True)
            entry['barrier'] = int(barrier_text) if barrier_text.isdigit() else 0
            
            # [8] 評分
            rating_text = cells[8].get_text(strip=True)
            entry['rating'] = int(rating_text) if rating_text.isdigit() else 0
            
            # [9] 練馬師
            entry['trainer'] = cells[9].get_text(strip=True)
            if not result['trainer'] and entry['trainer']:
                result['trainer'] = entry['trainer']
            
            # [10] 騎師
            entry['jockey'] = cells[10].get_text(strip=True)
            
            # [11] 頭馬距離
            margin_raw = cells[11].get_text(strip=True)
            entry['margin_raw'] = margin_raw
            entry['margin_numeric'] = parse_margin(margin_raw)
            
            # [12] 獨贏賠率 — extracted but NOT included in output per user request
            # We still parse it for internal use but won't output it
            odds_text = cells[12].get_text(strip=True)
            entry['_win_odds'] = float(odds_text) if odds_text.replace('.', '').isdigit() else None
            
            # [13] 實際負磅
            weight_text = cells[13].get_text(strip=True)
            entry['weight_carried'] = int(weight_text) if weight_text.isdigit() else 0
            
            # [14] 沿途走位
            pos_text = cells[14].get_text(strip=True)
            entry['running_positions_raw'] = pos_text
            entry['running_positions'] = parse_running_positions(pos_text)
            
            # [15] 完成時間
            time_raw = cells[15].get_text(strip=True)
            entry['finish_time_raw'] = time_raw
            entry['finish_time_secs'] = parse_time_to_seconds(time_raw)
            
            # [16] 排位體重
            dw_text = cells[16].get_text(strip=True)
            entry['declared_weight'] = int(dw_text) if dw_text.isdigit() else 0
            
            # [17] 配備
            entry['gear'] = cells[17].get_text(strip=True)
            
            result['entries'].append(entry)
            
        except Exception as e:
            # Skip malformed rows
            continue
            
    if not result['error']:
        _profile_cache[horse_id] = {'_ts': now, 'data': result}
        _save_profile_cache(_profile_cache)
    
    return result


# ── Trend Computations (Phase 1D) ────────────────────────────────────────

def compute_weight_trend(entries: list[dict], today_weight: Optional[int] = None) -> dict:
    """Compute weight trend from horse profile entries.
    
    Aligned with Analyst Step 7.5 rules:
    - ≥3lb/race consistent increase → 📈持續增磅 (positive)
    - ≥3lb/race consistent decrease → 📉持續減磅 (warning)
    - Fluctuation ≤5lb → 📊穩定 (neutral)
    - Single race diff ≥15lb → 🔴急劇變化 (risk)
    """
    weights = [e['declared_weight'] for e in entries if e.get('declared_weight', 0) > 0]
    if today_weight and today_weight > 0:
        weights = [today_weight] + weights
    
    if len(weights) < 2:
        return {'trend': '數據不足', 'signal': '中性', 'values': weights, 'detail': ''}
    
    diffs = [weights[i] - weights[i+1] for i in range(min(len(weights)-1, 5))]
    
    # Check for sudden change (today vs last)
    if abs(diffs[0]) >= 15:
        return {
            'trend': '🔴急劇變化',
            'signal': '風險',
            'values': weights[:6],
            'detail': f'今仗 vs 上仗差 {diffs[0]:+d}lb'
        }
    
    # Check for consistent 3-race increase
    if len(diffs) >= 3 and all(d >= 3 for d in diffs[:3]):
        return {
            'trend': '📈持續增磅',
            'signal': '正面',
            'values': weights[:6],
            'detail': f'近3仗每仗+{sum(diffs[:3])//3}lb'
        }
    
    # Check for consistent 3-race decrease
    if len(diffs) >= 3 and all(d <= -3 for d in diffs[:3]):
        return {
            'trend': '📉持續減磅',
            'signal': '警示',
            'values': weights[:6],
            'detail': f'近3仗每仗{sum(diffs[:3])//3}lb'
        }
    
    # Check overall fluctuation
    w_range = max(weights[:6]) - min(weights[:6])
    if w_range <= 5:
        return {
            'trend': '📊穩定',
            'signal': '中性',
            'values': weights[:6],
            'detail': f'波幅{w_range}lb'
        }
    
    # Mild trend
    avg_diff = sum(diffs[:3]) / min(len(diffs), 3)
    if avg_diff > 0:
        return {
            'trend': '📈微增',
            'signal': '中性偏正',
            'values': weights[:6],
            'detail': f'波幅{w_range}lb'
        }
    else:
        return {
            'trend': '📉微減',
            'signal': '中性偏負',
            'values': weights[:6],
            'detail': f'波幅{w_range}lb'
        }


def detect_gear_changes(entries: list[dict], today_gear: Optional[str] = None) -> dict:
    """Detect gear changes between today and last race.
    
    Aligned with Analyst SIP-HV2:
    - ≥2 items changed → 🔧 大幅配備變動 (triggers SIP-HV2)
    - 1 item added → 🔧 初戴 X
    - 1 item removed → 🔧 除去 X
    """
    def parse_gear(gear_str: str) -> set:
        if not gear_str or gear_str.strip() in ('', '-'):
            return set()
        # Split by / or common patterns
        parts = re.split(r'[/,]', gear_str.strip())
        return set(p.strip() for p in parts if p.strip())
    
    last_gear_str = entries[0].get('gear', '') if entries else ''
    today_set = parse_gear(today_gear) if today_gear else set()
    last_set = parse_gear(last_gear_str)
    
    # Build gear history (last 5 races)
    gear_history = [e.get('gear', '') for e in entries[:5]]
    
    if not today_gear:
        return {
            'signal': '無今仗配備數據',
            'today': '',
            'last': last_gear_str,
            'history': gear_history,
            'added': set(),
            'removed': set(),
            'sip_hv2': False
        }
    
    added = today_set - last_set
    removed = last_set - today_set
    total_changes = len(added) + len(removed)
    
    if total_changes >= 2:
        return {
            'signal': f'🔧 大幅配備變動 (+{",".join(added) if added else "無"} / -{",".join(removed) if removed else "無"})',
            'today': today_gear,
            'last': last_gear_str,
            'history': gear_history,
            'added': added,
            'removed': removed,
            'sip_hv2': True
        }
    elif added:
        return {
            'signal': f'🔧 初戴 {"+".join(added)}',
            'today': today_gear,
            'last': last_gear_str,
            'history': gear_history,
            'added': added,
            'removed': set(),
            'sip_hv2': False
        }
    elif removed:
        return {
            'signal': f'🔧 除去 {"+".join(removed)}',
            'today': today_gear,
            'last': last_gear_str,
            'history': gear_history,
            'added': set(),
            'removed': removed,
            'sip_hv2': False
        }
    else:
        return {
            'signal': '無變動',
            'today': today_gear,
            'last': last_gear_str,
            'history': gear_history,
            'added': set(),
            'removed': set(),
            'sip_hv2': False
        }


def compute_margin_trend(entries: list[dict]) -> dict:
    """Compute margin trend from numeric margins.
    
    - Decreasing margins → 📈收窄中 (getting closer to winner)
    - Increasing margins → 📉擴大中 (falling further behind)
    - Winner races (margin=0) counted as positive anchor
    """
    margins = []
    margin_strs = []
    for e in entries[:6]:
        m = e.get('margin_numeric')
        if m is not None:
            margins.append(m)
            margin_strs.append(e.get('margin_raw', ''))
    
    if len(margins) < 3:
        return {
            'trend': '數據不足',
            'signal': '中性',
            'values': margin_strs,
            'numeric': margins
        }
    
    # Compare recent 3 vs older
    recent = margins[:3]
    recent_avg = sum(recent) / len(recent)
    
    if len(margins) >= 5:
        older = margins[3:6]
        older_avg = sum(older) / len(older)
        delta = recent_avg - older_avg
    else:
        # Just check directionality of recent 3
        if recent[0] < recent[1] < recent[2]:
            delta = -1.0  # Narrowing
        elif recent[0] > recent[1] > recent[2]:
            delta = 1.0  # Widening
        else:
            delta = 0.0
    
    if delta < -0.5:
        trend = '📈收窄中'
        signal = '正面'
    elif delta > 0.5:
        trend = '📉擴大中'
        signal = '負面'
    else:
        trend = '📊波動'
        signal = '中性'
    
    return {
        'trend': trend,
        'signal': signal,
        'values': margin_strs,
        'numeric': margins
    }


def compute_rating_trend(entries: list[dict]) -> dict:
    """Compute rating movement trend.
    
    - Consistent decrease → 降班趨勢 (may benefit from weaker opponents)
    - Consistent increase → 升班趨勢 (facing stronger opponents)
    """
    ratings = [e['rating'] for e in entries[:6] if e.get('rating', 0) > 0]
    
    if len(ratings) < 3:
        return {'trend': '數據不足', 'signal': '中性', 'values': ratings}
    
    # ratings[0] is most recent
    diffs = [ratings[i] - ratings[i+1] for i in range(min(len(ratings)-1, 4))]
    
    if len(diffs) >= 2 and all(d <= -2 for d in diffs[:3] if diffs[:3]):
        # Rating dropping = class dropped = weaker opponents
        return {'trend': '降班中', 'signal': '利好', 'values': ratings}
    elif len(diffs) >= 2 and all(d >= 2 for d in diffs[:3] if diffs[:3]):
        return {'trend': '升班中', 'signal': '利淡', 'values': ratings}
    else:
        return {'trend': '穩定', 'signal': '中性', 'values': ratings}


def compute_running_pi(entries: list[dict]) -> dict:
    """Compute Position Index from precise running positions.
    
    PI = settled_position - finish_position
    Positive = gained positions (closer style), Negative = lost positions (faded)
    
    L400_PI = position_at_800m - finish_position (last section gain)
    """
    pi_values = []
    l400_pi_values = []
    
    for e in entries[:6]:
        positions = e.get('running_positions', [])
        placing = e.get('placing', 0)
        
        if not positions or placing == 0:
            continue
        
        # Settled position = average of middle positions
        if len(positions) >= 3:
            settled = positions[1]  # Second call position
            pi = settled - placing
            pi_values.append(pi)
            
            # L400 PI: last position before finish - finish
            l400_pos = positions[-1] if len(positions) >= 2 else positions[0]
            l400_pi = l400_pos - placing
            l400_pi_values.append(l400_pi)
        elif len(positions) >= 2:
            settled = positions[0]
            pi = settled - placing
            pi_values.append(pi)
    
    # Compute trends
    def _trend(values):
        if len(values) < 3:
            return '數據不足'
        recent_avg = sum(values[:2]) / 2
        older_avg = sum(values[2:min(len(values), 4)]) / max(1, min(len(values)-2, 2))
        delta = recent_avg - older_avg
        if abs(delta) < 0.5:
            return '穩定'
        elif delta > 1.5:
            return '上升軌 ✅'
        elif delta > 0:
            return '微升'
        elif delta < -1.5:
            return '衰退中 ⚠️'
        else:
            return '微跌'
    
    return {
        'pi_values': pi_values,
        'l400_pi_values': l400_pi_values,
        'pi_trend': _trend(pi_values),
        'l400_pi_trend': _trend(l400_pi_values),
    }


# ── Output Formatting ────────────────────────────────────────────────────

def format_profile_report(profile: dict, today_weight: int = 0, today_gear: str = '') -> str:
    """Format the scraped profile into a readable report."""
    lines = []
    entries = profile['entries']
    
    lines.append(f"## 馬匹: {profile['name']} ({profile['horse_id']})")
    lines.append(f"練馬師: {profile['trainer']}")
    lines.append(f"總賽績: {len(entries)} 場")
    lines.append("")
    
    # ── Race History Table (last 6 displayed) ──
    lines.append("### 完整賽績檔案 (近 6 場)")
    lines.append("| # | 日期 | 場地 | 距離 | 班次 | 檔位 | 騎師 | 負磅 | 名次 | 頭馬距 | 走位 | 完成時間 | 體重 | 配備 |")
    lines.append("|---|------|------|------|------|------|------|------|------|--------|------|----------|------|------|")
    
    for i, e in enumerate(entries[:6]):
        pos_str = '-'.join(str(p) for p in e.get('running_positions', []))
        cmap = {'1': '第一班', '2': '第二班', '3': '第三班', '4': '第四班', '5': '第五班', 'G1': '一級賽', 'G2': '二級賽', 'G3': '三級賽', 'G': '分級賽', '4R': '四歲馬系列', 'GRIFFIN': '新馬賽'}
        class_str = cmap.get(str(e.get('class_grade', '')).upper(), f"C{e['class_grade']}" if str(e.get('class_grade', '')).isdigit() else e.get('class_grade', ''))
        lines.append(
            f"| {i+1} | {e['date']} | {e.get('venue_track', '')[:4]} | {e['distance']} | "
            f"{class_str} | {e.get('barrier', '')} | {e.get('jockey', '')} | {e.get('weight_carried', '')} | "
            f"{e['placing']} | {e['margin_raw']} | {pos_str} | {e['finish_time_raw']} | "
            f"{e['declared_weight']} | {e['gear']} |"
        )
    
    if len(entries) > 6:
        lines.append(f"*(另有 {len(entries) - 6} 場較舊賽績未顯示，已用於趨勢計算)*")
    lines.append("")
    
    # ── Trend Dimensions ──
    if entries:
        # Weight trend
        wt = compute_weight_trend(entries, today_weight if today_weight else None)
        wt_vals = '→'.join(str(v) for v in wt['values'][:6])
        lines.append(f"📊 **體重趨勢:** {wt_vals} → {wt['trend']} ({wt['detail']})")
        
        # Gear changes
        gc = detect_gear_changes(entries, today_gear if today_gear else None)
        hist = '→'.join(gc['history'][:5]) if gc['history'] else 'N/A'
        lines.append(f"🔧 **配備變動:** 上仗 {gc['last']} → 今仗 {gc['today']} | {gc['signal']}")
        if gc.get('sip_hv2'):
            lines.append(f"   ⚠️ SIP-HV2 觸發：大幅配備變動")
        lines.append(f"   配備歷史: {hist}")
        
        # Margin trend
        mt = compute_margin_trend(entries)
        margin_vals = '→'.join(mt['values'][:6])
        lines.append(f"📏 **頭馬距離趨勢:** {margin_vals} → {mt['trend']}")
        
        # Rating trend
        rt = compute_rating_trend(entries)
        rating_vals = '→'.join(str(v) for v in rt['values'][:6])
        lines.append(f"📈 **評分變動:** {rating_vals} → {rt['trend']}")
        
        # Running PI
        rpi = compute_running_pi(entries)
        pi_vals = ', '.join(f"{v:+d}" for v in rpi['pi_values'][:5])
        lines.append(f"🏃 **走位 PI:** [{pi_vals}] → 趨勢: {rpi['pi_trend']}")
        l400_vals = ', '.join(f"{v:+d}" for v in rpi['l400_pi_values'][:5])
        lines.append(f"   L400 PI: [{l400_vals}] → 趨勢: {rpi['l400_pi_trend']}")
    
    return '\n'.join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Scrape HKJC horse profile SSR page')
    parser.add_argument('horse_id', help='HKJC Horse ID (e.g. HK_2024_K416)')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument('--today-weight', type=int, default=0, help='Today declared weight for trend comparison')
    parser.add_argument('--today-gear', type=str, default='', help='Today gear for change detection')
    
    args = parser.parse_args()
    
    print(f"Scraping {args.horse_id}...", file=sys.stderr)
    profile = scrape_horse_profile(args.horse_id)
    
    if profile['error']:
        print(f"ERROR: {profile['error']}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(profile['entries'])} race entries for {profile['name']}", file=sys.stderr)
    
    if args.json:
        # Convert sets to lists for JSON serialization
        output = {
            'horse_id': profile['horse_id'],
            'name': profile['name'],
            'trainer': profile['trainer'],
            'entries': profile['entries'],
            'trends': {
                'weight': compute_weight_trend(profile['entries'], args.today_weight or None),
                'gear': detect_gear_changes(profile['entries'], args.today_gear or None),
                'margin': compute_margin_trend(profile['entries']),
                'rating': compute_rating_trend(profile['entries']),
                'running_pi': compute_running_pi(profile['entries']),
            }
        }
        # Make JSON serializable
        def _serialize(obj):
            if isinstance(obj, set):
                return list(obj)
            return obj
        print(json.dumps(output, ensure_ascii=False, indent=2, default=_serialize))
    else:
        print(format_profile_report(profile, args.today_weight, args.today_gear))


if __name__ == '__main__':
    main()
