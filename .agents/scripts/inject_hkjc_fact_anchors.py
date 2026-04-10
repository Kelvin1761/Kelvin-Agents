#!/usr/bin/env python3
"""
inject_hkjc_fact_anchors.py — V2 HKJC 完整賽績檔案 Auto-Generator

Merges TWO data sources to produce comprehensive Facts.md:
  Source A: Formguide.txt (sectional splits, energy, race comments)
  Source B: HKJC Horse Profile SSR HTML (margin, trainer, class, rating,
            running positions, finish time, declared weight, gear)

Produces:
  1. 賽績總結 — 近六場名次、休後復出日數、季內/同程/同場同程統計
  2. 完整賽績檔案 Markdown Table (近 6 場顯示,全部用於計算)
  3. L600/L400 自動計算 + 標準時間偏差
  4. 段速/能量趨勢
  5. 走位消耗預估（從短評 XW 提取）
  6. 新維度: 體重趨勢 / 配備變動 / 頭馬距離趨勢 / 評分變動 / 走位 PI
  7. 引擎距離分類

LLM 只需要做：解讀、判斷、評級。所有數學由 Python 處理。

Usage:
    python3 inject_hkjc_fact_anchors.py <Formguide.txt> [--race-date YYYY-MM-DD]
        [--venue ST|HV] [--distance 1200] [--class 4]
        [--horse-ids 'HK_2024_K416,HK_2024_K035,...']
        [--output Facts.md]
"""
import re
import sys
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Import scraper for enriched data
try:
    from scrape_hkjc_horse_profile import (
        scrape_horse_profile, parse_margin,
        compute_weight_trend, detect_gear_changes,
        compute_margin_trend, compute_rating_trend, compute_running_pi
    )
    HAS_SCRAPER = True
except ImportError:
    HAS_SCRAPER = False

# Import form lines engine
try:
    from hkjc_profile_scraper import compute_form_lines, format_form_lines_report
    HAS_FORM_LINES = True
except ImportError:
    HAS_FORM_LINES = False

# ========================================================================
# HKJC Official Standard Times (seconds) — last updated 2025-08-26
# Source: https://racing.hkjc.com (Reference Info → Race Course Standard Times)
# Format: (venue, distance) → {class: seconds}
# All times are for "Good" going
# ========================================================================
STANDARD_TIMES = {
    # --- 沙田草地 (Sha Tin Turf) ---
    ('沙田', 1000): {'G': 55.90, 'C2': 56.05, 'C3': 56.45, 'C4': 56.65, 'C5': 57.00, 'GR': 56.65},
    ('沙田', 1200): {'G': 68.15, 'C1': 68.45, 'C2': 68.65, 'C3': 69.00, 'C4': 69.35, 'C5': 69.55, 'GR': 69.90},
    ('沙田', 1400): {'G': 81.10, 'C1': 81.25, 'C2': 81.45, 'C3': 81.65, 'C4': 82.00, 'C5': 82.30},
    ('沙田', 1600): {'G': 93.90, 'C1': 94.05, 'C2': 94.25, 'C3': 94.70, 'C4': 94.90, 'C5': 95.45},
    ('沙田', 1800): {'G': 107.10, 'C2': 107.30, 'C3': 107.50, 'C4': 107.85, 'C5': 108.45},
    ('沙田', 2000): {'G': 120.50, 'C1': 121.20, 'C2': 121.70, 'C3': 121.90, 'C4': 122.35, 'C5': 122.65},
    ('沙田', 2400): {'G': 147.00},

    # --- 跑馬地草地 (Happy Valley Turf) ---
    ('跑馬地', 1000): {'C2': 56.40, 'C3': 56.65, 'C4': 57.20, 'C5': 57.35},
    ('跑馬地', 1200): {'C1': 69.10, 'C2': 69.30, 'C3': 69.60, 'C4': 69.90, 'C5': 70.10},
    ('跑馬地', 1650): {'C1': 99.10, 'C2': 99.30, 'C3': 99.90, 'C4': 100.10, 'C5': 100.30},
    ('跑馬地', 1800): {'G': 108.95, 'C2': 109.15, 'C3': 109.45, 'C4': 109.65, 'C5': 109.95},
    ('跑馬地', 2200): {'C3': 136.60, 'C4': 137.05, 'C5': 137.35},

    # --- 沙田全天候跑道 (Sha Tin AWT) ---
    ('沙田AWT', 1200): {'C2': 68.35, 'C3': 68.55, 'C4': 68.95, 'C5': 69.35},
    ('沙田AWT', 1650): {'C1': 97.80, 'C2': 98.40, 'C3': 98.60, 'C4': 99.05, 'C5': 99.45},
    ('沙田AWT', 1800): {'C3': 108.05, 'C4': 108.55, 'C5': 109.45},
}

# Season start month (Sep)
SEASON_START_MONTH = 9

# Max races to DISPLAY in the table (all used for computation)
MAX_DISPLAY_RACES = 6
# Max races used for computation (no limit — scraper handles all)
MAX_COMPUTE_RACES = 99


def parse_time_to_seconds(time_str: str) -> Optional[float]:
    """Convert HKJC time format (M.SS.CC or SS.CC) to total seconds.
    
    Examples: '1.09.35' → 69.35, '0.56.65' → 56.65, '01:02.750' → 62.75
    """
    if not time_str or time_str == '-':
        return None
    # Handle M.SS.CC format
    m = re.match(r'^(\d+)\.(\d{2})\.(\d{2})$', time_str.strip())
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        centis = int(m.group(3))
        return mins * 60 + secs + centis / 100
    # Handle MM:SS.CCC
    m = re.match(r'^(\d+):(\d{2})\.(\d{2,3})$', time_str.strip())
    if m:
        mins = int(m.group(1))
        secs = int(m.group(2))
        frac = m.group(3)
        if len(frac) == 3:
            return mins * 60 + secs + int(frac) / 1000
        else:
            return mins * 60 + secs + int(frac) / 100
    return None


def format_seconds(secs: float) -> str:
    """Format seconds back to M:SS.CC."""
    mins = int(secs // 60)
    remainder = secs - mins * 60
    return f"{mins}:{remainder:05.2f}"


def get_standard_time(venue: str, distance: int, race_class: str) -> Optional[float]:
    """Look up standard time for venue/distance/class."""
    # Normalise venue
    v = venue
    if 'AWT' in venue or '全天候' in venue:
        v = '沙田AWT'
    elif '沙田' in venue:
        v = '沙田'
    elif '跑馬地' in venue:
        v = '跑馬地'
    
    key = (v, distance)
    if key not in STANDARD_TIMES:
        return None
    
    class_map = STANDARD_TIMES[key]
    # Try exact match, then fallback
    if race_class in class_map:
        return class_map[race_class]
    
    # Fallback: try closest class
    for fallback in ['C4', 'C3', 'C5', 'C2', 'C1', 'G']:
        if fallback in class_map:
            return class_map[fallback]
    return None


def compute_sectional_from_splits(splits: list[float], distance: int) -> dict:
    """Compute L600 and L400 from sectional time splits.
    
    HKJC splits are typically:
    - 1000m: 3 splits (first ~200m, 2x~400m)
    - 1200m: 3 splits (~400m each) or 4 splits for some
    - 1400m: 4 splits (first ~200m + 3x~400m)
    - 1600m: 4 splits (~400m each)
    - 1800m: 5 splits (first ~200m + 4x~400m)
    - 2000m: 5 splits (~400m each)
    - 2200m: 6 splits
    
    L400 = last split
    L600 = contextual (last 1.5 splits approximately)
    """
    if not splits or len(splits) < 2:
        return {}
    
    result = {}
    result['L400'] = splits[-1]
    
    if len(splits) >= 2:
        result['L800'] = splits[-1] + splits[-2]
    
    # For L600: approximate as last split + half of second-to-last
    if len(splits) >= 2:
        result['L600_approx'] = splits[-1] + splits[-2] * 0.5
    
    # Total time
    result['total'] = sum(splits)
    
    return result


def extract_wide_pattern(comment: str) -> dict:
    """Extract running position pattern (XW) from race comment.
    
    HKJC comments contain patterns like (1W1W1W2W) or (2W2W2W3W).
    """
    result = {'pattern': '', 'max_wide': 0, 'avg_wide': 0, 'consumption': '未知'}
    
    # Find (XW...) pattern
    m = re.search(r'\((\d+W(?:\d+W)*)\)', comment)
    if not m:
        return result
    
    pattern = m.group(1)
    result['pattern'] = pattern
    
    # Parse each XW
    wides = [int(x) for x in re.findall(r'(\d+)W', pattern)]
    if not wides:
        return result
    
    result['max_wide'] = max(wides)
    result['avg_wide'] = sum(wides) / len(wides)
    
    # Determine consumption level
    max_w = result['max_wide']
    avg_w = result['avg_wide']
    
    if max_w >= 5 or (max_w >= 4 and avg_w >= 3.5):
        result['consumption'] = '極高消耗'
    elif max_w >= 4 or (max_w >= 3 and avg_w >= 2.5):
        result['consumption'] = '高消耗'
    elif max_w >= 3 or avg_w >= 2.0:
        result['consumption'] = '中等消耗'
    elif avg_w >= 1.5:
        result['consumption'] = '中低消耗'
    else:
        result['consumption'] = '低消耗'
    
    return result


def parse_pace_from_comment(comment: str) -> str:
    """Extract pace type from race comment."""
    if '極快步速' in comment:
        return '極快'
    elif '極慢步速' in comment:
        return '極慢'
    elif '快步速' in comment:
        return '快'
    elif '慢步速' in comment:
        return '慢'
    elif '中等偏快步速' in comment:
        return '中等偏快'
    elif '中等偏慢步速' in comment:
        return '中等偏慢'
    elif '中等步速' in comment:
        return '中等'
    return '未知'


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse HKJC date format (DD/MM/YYYY)."""
    try:
        return datetime.strptime(date_str.strip(), '%d/%m/%Y')
    except (ValueError, AttributeError):
        return None


def parse_hkjc_formguide(filepath: str) -> dict:
    """Parse the HKJC extracted formguide text file.
    
    Returns {
        'race_info': {...},
        'horses': [
            {'num': int, 'name': str, 'barrier': int, 'jockey': str,
             'weight': int, 'body_weight': int, 'races': [...]}
        ]
    }
    """
    import os
    def load_brand_mapping(fp):
        rc_path = str(fp).replace('賽績.md', '排位表.md').replace('Formguide.txt', '排位表.md')
        mapping = {}
        if os.path.exists(rc_path):
            text = Path(rc_path).read_text(encoding='utf-8')
            for match in re.finditer(r'馬名:\s*(.*?)\n.*?烙號:\s*([A-Za-z0-9_]+)', text, re.DOTALL):
                mapping[match.group(1).strip()] = match.group(2).strip()
        return mapping
    
    brand_mapping = load_brand_mapping(filepath)

    text = Path(filepath).read_text(encoding='utf-8')
    
    # Parse race overview
    race_info = {}
    overview_match = re.search(
        r'賽事日期.*?/\s*場次.*?/\s*跑道.*?:\s*(.+?)$',
        text, re.MULTILINE
    )
    if overview_match:
        race_info['overview'] = overview_match.group(1).strip()
    
    # Parse each horse
    horses = []
    # Horse header pattern
    horse_headers = list(re.finditer(
        r'^馬號:\s*\n?馬名:\s*(\d+)\s+(.+?)$',
        text, re.MULTILINE
    ))
    if not horse_headers:
        # Try alternate format
        horse_headers = list(re.finditer(
            r'^馬號:\s*(\d+)\s*\n馬名:\s*(.+?)$',
            text, re.MULTILINE
        ))
    if not horse_headers:
        # Try format where number is on 馬名 line
        horse_headers = list(re.finditer(
            r'^馬號:\s*\n?馬名:\s*(\d+)\s+(.+?)$',
            text, re.MULTILINE
        ))
    
    for idx, hm in enumerate(horse_headers):
        start = hm.end()
        end = horse_headers[idx + 1].start() if idx + 1 < len(horse_headers) else len(text)
        block = text[start:end]
        
        horse_num_str = hm.group(1).strip()
        horse_name = hm.group(2).strip()
        
        # Sometimes the format is "馬號: \n馬名: 1 競駿良駒"
        if not horse_num_str.isdigit():
            # Try to extract from horse_name
            nm = re.match(r'(\d+)\s+(.+)', horse_name)
            if nm:
                horse_num_str = nm.group(1)
                horse_name = nm.group(2).strip()
        
        horse_num = int(horse_num_str) if horse_num_str.isdigit() else idx + 1
        
        # Extract barrier, jockey, weight, body weight
        barrier_m = re.search(r'檔位:\s*(\d+)', block)
        jockey_m = re.search(r'騎師:\s*(.+?)$', block, re.MULTILINE)
        weight_m = re.search(r'負磅:\s*(\d+)', block)
        bw_m = re.search(r'排位體重:\s*(\d+)', block)
        
        barrier = int(barrier_m.group(1)) if barrier_m else 0
        jockey = jockey_m.group(1).strip() if jockey_m else ''
        weight = int(weight_m.group(1)) if weight_m else 0
        body_weight = int(bw_m.group(1)) if bw_m else 0
        
        brand_m = re.search(r'烙號:\s*([A-Za-z0-9_]+)', block)
        brand_no = brand_m.group(1).strip() if brand_m else ''
        if not brand_no:
            nm = re.search(r'\(([A-Z]\d{3})\)', horse_name)
            if nm:
                brand_no = nm.group(1)
                horse_name = re.sub(r'\([A-Z]\d{3}\)', '', horse_name).strip()
        if not brand_no:
            # Fallback to 排位表 matching
            brand_no = brand_mapping.get(horse_name, '')
        
        # Parse past races
        races = []
        race_pattern = re.compile(
            r'^\s*\[(\d+)\]\s+(\d{2}/\d{2}/\d{4})\s*\|\s*日數:\s*(\d+)\s*\|\s*(.+?)$',
            re.MULTILINE
        )
        
        for rm in race_pattern.finditer(block):
            race_idx = int(rm.group(1))
            date_str = rm.group(2)
            days_since = int(rm.group(3))
            venue_info = rm.group(4).strip()
            
            # Parse venue info: 沙田 "A" 2000 好
            vi = re.match(r'(.+?)\s+"(.+?)"\s+(\d+)\s+(.+)', venue_info)
            if vi:
                venue = vi.group(1).strip()
                rail = vi.group(2).strip()
                distance = int(vi.group(3))
                going = vi.group(4).strip()
            else:
                venue = venue_info
                rail = ''
                distance = 0
                going = ''
            
            # Get race details block until next race or end
            race_start = rm.end()
            next_race = race_pattern.search(block, race_start)
            race_end = next_race.start() if next_race else len(block)
            race_block = block[race_start:race_end]
            
            # Extract details
            details_m = re.search(
                r'檔位:\s*(\d+)\s*\|\s*馬重:\s*(\d+)\s*\|\s*負磅:\s*(\d+)\s*\|\s*騎師:\s*(.+?)\s*\|\s*名次:\s*(\d+)\s*/\s*(\d+)',
                race_block
            )
            r_barrier = int(details_m.group(1)) if details_m else 0
            r_bw = int(details_m.group(2)) if details_m else 0
            r_weight = int(details_m.group(3)) if details_m else 0
            r_jockey = details_m.group(4).strip() if details_m else ''
            r_finish = int(details_m.group(5)) if details_m else 0
            r_field = int(details_m.group(6)) if details_m else 0
            
            # Extract energy
            energy_m = re.search(r'能量:\s*(\d+)', race_block)
            energy = int(energy_m.group(1)) if energy_m else 0
            
            # Extract sectional times
            splits_m = re.search(r'分段時間:\s*(.+?)$', race_block, re.MULTILINE)
            splits_raw = splits_m.group(1).strip() if splits_m else ''
            splits = []
            if splits_raw:
                for s in splits_raw.split(','):
                    s = s.strip()
                    try:
                        splits.append(float(s))
                    except ValueError:
                        pass
            
            # Extract comment
            comment_m = re.search(r'短評:\s*(.+?)$', race_block, re.MULTILINE)
            comment = comment_m.group(1).strip() if comment_m else ''
            
            # Compute derived data
            sectionals = compute_sectional_from_splits(splits, distance)
            wide_info = extract_wide_pattern(comment)
            pace = parse_pace_from_comment(comment)
            
            races.append({
                'idx': race_idx,
                'date': date_str,
                'date_dt': parse_date(date_str),
                'days_since': days_since,
                'venue': venue,
                'rail': rail,
                'distance': distance,
                'going': going,
                'barrier': r_barrier,
                'body_weight': r_bw,
                'weight': r_weight,
                'jockey': r_jockey,
                'finish': r_finish,
                'field_size': r_field,
                'energy': energy,
                'splits': splits,
                'splits_raw': splits_raw,
                'comment': comment,
                'sectionals': sectionals,
                'wide_info': wide_info,
                'pace': pace,
            })
        
        horses.append({
            'num': horse_num,
            'name': horse_name,
            'brand_no': brand_no,
            'barrier': barrier,
            'jockey': jockey,
            'weight': weight,
            'body_weight': body_weight,
            'races': races,  # No limit — keep all for trend computation
        })
    
    return {'race_info': race_info, 'horses': horses}


def compute_stats(races: list, today_venue: str = '', today_dist: int = 0) -> dict:
    """Compute 賽績統計 from race history."""
    stats = {
        'recent_6': [],
        'days_since_last': 0,
        'season': [0, 0, 0, 0],      # W-2-3-L
        'same_dist': [0, 0, 0, 0],
        'same_venue_dist': [0, 0, 0, 0],
    }
    
    if not races:
        return stats
    
    # Recent 6 finishing positions
    stats['recent_6'] = [r['finish'] for r in races[:6]]
    
    # Days since last race
    stats['days_since_last'] = races[0].get('days_since', 0)
    
    # Current season check (Sep-Jul)
    today = datetime.now()
    if today.month >= SEASON_START_MONTH:
        season_start = datetime(today.year, SEASON_START_MONTH, 1)
    else:
        season_start = datetime(today.year - 1, SEASON_START_MONTH, 1)
    
    for r in races:
        dt = r.get('date_dt')
        finish = r.get('finish', 0)
        dist = r.get('distance', 0)
        venue = r.get('venue', '')
        
        if finish <= 0:
            continue
        
        pos = min(finish, 4)  # 1,2,3 or 4(=lost)
        idx = pos - 1 if pos <= 3 else 3
        
        # Season stats
        if dt and dt >= season_start:
            stats['season'][idx] += 1
        
        # Same distance
        if today_dist > 0 and dist == today_dist:
            stats['same_dist'][idx] += 1
        
        # Same venue + distance
        if today_venue and today_dist > 0 and venue == today_venue and dist == today_dist:
            stats['same_venue_dist'][idx] += 1
    
    return stats


def compute_trends(races: list) -> dict:
    """Compute L400 and energy trends for all available races (up to 6)."""
    trends = {'l400_trend': '', 'energy_trend': '', 'l400_values': [], 'energy_values': []}
    
    # Use all races (up to 6) for full picture
    recent = races[:6]
    
    # L400 trend
    l400s = [r['sectionals'].get('L400') for r in recent if r['sectionals'].get('L400')]
    if len(l400s) >= 2:
        trends['l400_values'] = l400s
        # Compare newest vs oldest for overall direction
        delta = l400s[0] - l400s[-1]  # negative = improving (getting faster)
        spread = max(l400s) - min(l400s)
        # Also check recent 3 vs older 3 for trend shift
        if len(l400s) >= 4:
            recent_avg = sum(l400s[:len(l400s)//2]) / (len(l400s)//2)
            older_avg = sum(l400s[len(l400s)//2:]) / (len(l400s) - len(l400s)//2)
            trend_delta = recent_avg - older_avg
        else:
            trend_delta = delta
        
        if spread < 0.5:
            trends['l400_trend'] = '穩定'
        elif trend_delta < -0.5:
            trends['l400_trend'] = '上升軌 ✅'
        elif trend_delta > 0.5:
            trends['l400_trend'] = '衰退中 ⚠️'
        else:
            trends['l400_trend'] = '波動'
    
    # Energy trend
    energies = [r['energy'] for r in recent if r['energy'] > 0]
    if len(energies) >= 2:
        trends['energy_values'] = energies
        if len(energies) >= 4:
            recent_avg = sum(energies[:len(energies)//2]) / (len(energies)//2)
            older_avg = sum(energies[len(energies)//2:]) / (len(energies) - len(energies)//2)
            delta = recent_avg - older_avg
        else:
            delta = energies[0] - energies[-1]
        if abs(delta) <= 2:
            trends['energy_trend'] = '穩定'
        elif delta > 0:
            trends['energy_trend'] = '上升 ✅'
        else:
            trends['energy_trend'] = '下降 ⚠️'
    
    return trends


def classify_engine_type(races: list) -> dict:
    """Classify horse engine type from race history (Step 2.6 automation).
    
    Type A (前領均速): Consistently runs in front positions, even splits
    Type B (末段爆發): Runs from behind, strong L400
    Type C (持續衝刺): Flexible positioning, consistent splits
    Type A/B (混合): No clear pattern
    """
    result = {
        'type': 'A/B',
        'type_cn': '混合型',
        'confidence': '低',
        'evidence': [],
    }
    
    if len(races) < 2:
        return result
    
    # === Layer 1: Running position pattern (60% weight) ===
    front_count = 0  # How many races horse ran in front positions
    back_count = 0   # How many races horse ran in back positions
    total_valid = 0
    
    for r in races[:6]:
        wide = r.get('wide_info', {})
        wides = []
        if wide.get('pattern'):
            wides = [int(x) for x in re.findall(r'(\d+)W', wide['pattern'])]
        
        # Use first W value as indicator of in-running position tier
        # Also check comment for position keywords
        comment = r.get('comment', '')
        is_front = False
        is_back = False
        
        if any(kw in comment for kw in ['領放', '領前', '居前列', '輕鬆放頭', '帶出', '搶口']):
            is_front = True
        elif any(kw in comment for kw in ['居包尾', '後列', '最後', '留守尾段']):
            is_back = True
        elif '居中間' in comment:
            pass  # mid-field
        elif wides and wides[0] <= 2 and len(wides) >= 2 and max(wides[:2]) <= 2:
            is_front = True  # 1W1W typically = front runners
        
        if is_front:
            front_count += 1
        elif is_back:
            back_count += 1
        total_valid += 1
    
    # === Layer 2: L400 quality verification (40% weight) ===
    l400_fast_count = 0  # Races where L400 was notably fast
    splits_even_count = 0  # Races where splits were even
    
    for r in races[:6]:
        splits = r.get('splits', [])
        if len(splits) < 3:
            continue
        l400 = splits[-1]
        # Compare L400 to average of other splits
        other_avg = sum(splits[:-1]) / len(splits[:-1])
        if l400 < other_avg - 0.5:
            l400_fast_count += 1
        
        # Check if splits are even (low variance)
        if len(splits) >= 3:
            main_splits = splits[1:]  # Skip first split (often shorter)
            spread = max(main_splits) - min(main_splits)
            if spread < 1.0:
                splits_even_count += 1
    
    # === Classification ===
    if total_valid >= 3:
        front_pct = front_count / total_valid
        back_pct = back_count / total_valid
        
        if front_pct >= 0.5:
            result['type'] = 'A'
            result['type_cn'] = '前領均速型'
            result['evidence'].append(f'前列走位 {front_count}/{total_valid} 場')
            result['confidence'] = '高' if front_pct >= 0.7 else '中'
            # Verify: if L400 is consistently fast, might be A/B
            if l400_fast_count >= 2:
                result['evidence'].append(f'但 L400 偏快 {l400_fast_count} 場')
        elif back_pct >= 0.5 and l400_fast_count >= 2:
            result['type'] = 'B'
            result['type_cn'] = '末段爆發型'
            result['evidence'].append(f'後段走位 {back_count}/{total_valid} 場')
            result['evidence'].append(f'L400 偏快 {l400_fast_count} 場')
            result['confidence'] = '高' if back_pct >= 0.7 and l400_fast_count >= 3 else '中'
        elif back_pct >= 0.5 and l400_fast_count < 2:
            result['type'] = 'A/B'
            result['type_cn'] = '混合型'
            result['evidence'].append(f'後段走位但 L400 唔突出 → 可能只係慢閘')
            result['confidence'] = '低'
        elif splits_even_count >= 3:
            result['type'] = 'C'
            result['type_cn'] = '持續衝刺型'
            result['evidence'].append(f'分段均勻 {splits_even_count}/{total_valid} 場')
            result['confidence'] = '中'
        else:
            result['type'] = 'A/B'
            result['type_cn'] = '混合型'
            result['evidence'].append(f'前{front_count}/後{back_count}/中{total_valid-front_count-back_count}')
            result['confidence'] = '低'
    
    return result


def compute_distance_aptitude(races: list, today_dist: int = 0) -> dict:
    """Compute distance aptitude from race history.
    
    Groups races into distance bands and calculates W/P/L record.
    """
    dist_bands = {}  # {distance: [win, place(2-3), lose]}
    
    for r in races:
        d = r.get('distance', 0)
        if d <= 0:
            continue
        # Round to standard HKJC distances
        if d not in dist_bands:
            dist_bands[d] = [0, 0, 0]  # W, P(2-3), L
        
        finish = r.get('finish', 0)
        if finish == 1:
            dist_bands[d][0] += 1
        elif 2 <= finish <= 3:
            dist_bands[d][1] += 1
        elif finish > 0:
            dist_bands[d][2] += 1
    
    # Find best distance (highest place rate)
    best_dist = 0
    best_rate = -1
    for d, (w, p, l) in dist_bands.items():
        total = w + p + l
        if total == 0:
            continue
        rate = (w * 3 + p * 1.5) / total  # Weighted score
        if rate > best_rate:
            best_rate = rate
            best_dist = d
    
    # Format output for each distance
    dist_lines = []
    for d in sorted(dist_bands.keys()):
        w, p, l = dist_bands[d]
        total = w + p + l
        marker = ''
        if d == best_dist:
            marker = ' ⭐最佳'
        if d == today_dist:
            place_count = w + p
            rate = place_count / total * 100 if total > 0 else 0
            emoji = '✅' if rate >= 50 else ('⚠️' if rate >= 25 else '❌')
            marker += f' ← 今仗 {emoji}'
        dist_lines.append(f'{d}m: {total}場 ({w}-{p}-{l}){marker}')
    
    return {
        'best_dist': best_dist,
        'dist_bands': dist_bands,
        'dist_lines': dist_lines,
        'today_record': dist_bands.get(today_dist, [0, 0, 0]),
    }


def generate_horse_block(horse: dict, today_venue: str = '',
                          today_dist: int = 0, race_class: str = 'C4',
                          profile_data: dict = None,
                          form_lines_data: dict = None) -> str:
    """Generate full fact anchor + forensic block for one horse.
    
    Args:
        horse: Parsed formguide horse data (splits, energy, comments)
        profile_data: Optional scraped horse profile data (margin, trainer, etc.)
        form_lines_data: Optional form lines computation result
    """
    lines = []
    races = horse['races']
    p_entries = profile_data.get('entries', []) if profile_data else []
    
    # Determine trainer (from profile if available)
    trainer = profile_data.get('trainer', '') if profile_data else ''
    
    # Header
    header_parts = [f"### 馬號 {horse['num']} — {horse['name']}"]
    header_parts.append(f"騎師: {horse['jockey']}")
    if trainer:
        header_parts.append(f"練馬師: {trainer}")
    header_parts.append(f"負磅: {horse['weight']}")
    header_parts.append(f"檔位: {horse['barrier']}")
    lines.append(' | '.join(header_parts))
    
    if not races and not p_entries:
        lines.append("  (無往績記錄)")
        return '\n'.join(lines)
    
    # === 賽績總結 ===
    stats = compute_stats(races, today_venue, today_dist)
    
    recent_str = '-'.join(str(p) for p in stats['recent_6'])
    season_str = f"({stats['season'][0]}-{stats['season'][1]}-{stats['season'][2]}-{stats['season'][3]})"
    dist_str = f"({stats['same_dist'][0]}-{stats['same_dist'][1]}-{stats['same_dist'][2]}-{stats['same_dist'][3]})"
    vd_str = f"({stats['same_venue_dist'][0]}-{stats['same_venue_dist'][1]}-{stats['same_venue_dist'][2]}-{stats['same_venue_dist'][3]})"
    
    lines.append(f"📌 **賽績總結:**")
    lines.append(f"- **近六場:** {recent_str} (左=剛戰 → 右=最舊)")
    lines.append(f"- **休後復出:** {stats['days_since_last']} 日")
    lines.append(f"- **統計:** 季內 {season_str} | 同程 {dist_str} | 同場同程 {vd_str}")
    
    # === 完整賽績檔案 Markdown Table ===
    display_races = min(len(races), MAX_DISPLAY_RACES)
    total_races = max(len(races), len(p_entries))
    
    lines.append(f"")
    lines.append(f"📋 **完整賽績檔案 (近 {display_races} 場,嚴禁修改數值):**")
    lines.append("")
    lines.append(f"| # | 日期 | 場地 | 距離 | 班次 | 檔位 | 騎師 | 負磅 | 名次 | 頭馬距離 | 能量 | L400 | 走位(XW) | 消耗 | 沿途位 | 完成時間 | 標準差 | 體重 | 配備 | 賽事短評 | 寬恕認定 |")
    lines.append(f"|---|------|------|------|------|------|------|------|------|--------|------|------|----------|------|--------|----------|--------|------|------|----------|---------|")
    
    for i in range(display_races):
        r = races[i] if i < len(races) else {}
        p = p_entries[i] if i < len(p_entries) else {}
        date = r.get('date', p.get('date', ''))
        venue = r.get('venue', p.get('venue_track', ''))[:4]
        distance = r.get('distance', p.get('distance', 0))
        class_g = p.get('class_grade', '')
        if class_g:
            cmap = {'1': '第一班', '2': '第二班', '3': '第三班', '4': '第四班', '5': '第五班', 'G1': '一級賽', 'G2': '二級賽', 'G3': '三級賽', 'G': '分級賽', '4R': '四歲馬系列', 'GRIFFIN': '新馬賽'}
            class_g = cmap.get(str(class_g).upper(), f"C{class_g}" if str(class_g).isdigit() else class_g)
        barrier = r.get('barrier', p.get('barrier', 0))
        jockey = r.get('jockey', p.get('jockey', ''))
        weight = r.get('weight', p.get('weight_carried', 0))
        finish = r.get('finish', p.get('placing', 0))
        margin = p.get('margin_raw', '-')
        energy = r.get('energy', 0)
        energy_str = str(energy) if energy > 0 else '-'
        sect = r.get('sectionals', {})
        l400_str = f"{sect['L400']:.2f}" if sect.get('L400') else '-'
        wide = r.get('wide_info', {})
        wide_str = f"({wide['pattern']})" if wide.get('pattern') else '-'
        consumption = wide.get('consumption', '-') if wide.get('pattern') else '-'
        pos_list = p.get('running_positions', [])
        pos_str = '-'.join(str(x) for x in pos_list) if pos_list else '-'
        ftime = p.get('finish_time_raw', '-')
        
        std_diff_str = '-'
        if ftime != '-':
            try:
                ftime_sec = time_str_to_seconds(ftime)
                race_std = get_standard_time(venue, distance, class_g)
                if ftime_sec and race_std:
                    diff = ftime_sec - race_std
                    std_diff_str = f"{diff:+.2f}s"
            except Exception:
                pass
                
        dw = p.get('declared_weight', r.get('body_weight', 0))
        dw_str = str(dw) if dw > 0 else '-'
        gear = p.get('gear', '-')
        comment = r.get('comment', '')
        
        lines.append(f"| {i+1} | {date} | {venue} | {distance} | {class_g} | {barrier} | {jockey} | {weight} | {finish} | {margin} | {energy_str} | {l400_str} | {wide_str} | {consumption} | {pos_str} | {ftime} | {std_diff_str} | {dw_str} | {gear} | {comment} | [需判定] |")

    if total_races > display_races:
        lines.append(f"")
        lines.append(f"📋 **較舊歷史賽績 (供參考):**")
        lines.append(f"| # | 日期 | 場地 | 距離 | 班次 | 檔位 | 騎師 | 負磅 | 名次 | 頭馬距離 | 能量 | L400 | 走位(XW) | 消耗 | 沿途位 | 完成時間 | 標準差 | 體重 | 配備 | 賽事短評 | 寬恕認定 |")
        lines.append(f"|---|------|------|------|------|------|------|------|------|--------|------|------|----------|------|--------|----------|--------|------|------|----------|---------|")
        for i in range(display_races, total_races):
            r = races[i] if i < len(races) else {}
            p = p_entries[i] if i < len(p_entries) else {}
            date = r.get('date', p.get('date', ''))
            venue = r.get('venue', p.get('venue_track', ''))[:4]
            distance = r.get('distance', p.get('distance', 0))
            class_g = p.get('class_grade', '')
            if class_g:
                cmap = {'1': '第一班', '2': '第二班', '3': '第三班', '4': '第四班', '5': '第五班', 'G1': '一級賽', 'G2': '二級賽', 'G3': '三級賽', 'G': '分級賽', '4R': '四歲馬系列', 'GRIFFIN': '新馬賽'}
                class_g = cmap.get(str(class_g).upper(), f"C{class_g}" if str(class_g).isdigit() else class_g)
                barrier = r.get('barrier', p.get('barrier', 0))
                jockey = r.get('jockey', p.get('jockey', ''))
                weight = r.get('weight', p.get('weight_carried', 0))
                finish = r.get('finish', p.get('placing', 0))
                margin = p.get('margin_raw', '-')
                energy = r.get('energy', 0)
                energy_str = str(energy) if energy > 0 else '-'
                sect = r.get('sectionals', {})
                l400_str = f"{sect['L400']:.2f}" if sect.get('L400') else '-'
                wide = r.get('wide_info', {})
                wide_str = f"({wide['pattern']})" if wide.get('pattern') else '-'
                consumption = wide.get('consumption', '-') if wide.get('pattern') else '-'
                pos_list = p.get('running_positions', [])
                pos_str = '-'.join(str(x) for x in pos_list) if pos_list else '-'
                ftime = p.get('finish_time_raw', '-')
                
                std_diff_str = '-'
                if ftime != '-':
                    try:
                        ftime_sec = time_str_to_seconds(ftime)
                        race_std = get_standard_time(venue, distance, class_g)
                        if ftime_sec and race_std:
                            diff = ftime_sec - race_std
                            std_diff_str = f"{diff:+.2f}s"
                    except Exception:
                        pass

                dw = p.get('declared_weight', r.get('body_weight', 0))
                dw_str = str(dw) if dw > 0 else '-'
                gear = p.get('gear', '-')
                comment = r.get('comment', '')
                
                lines.append(f"| {i+1} | {date} | {venue} | {distance} | {class_g} | {barrier} | {jockey} | {weight} | {finish} | {margin} | {energy_str} | {l400_str} | {wide_str} | {consumption} | {pos_str} | {ftime} | {std_diff_str} | {dw_str} | {gear} | {comment} | [需判定] |")

    lines.append(f"")
    
    # === 段速/能量趨勢 ===
    trends = compute_trends(races)
    lines.append(f"📊 **段速趨勢:**")
    
    if trends['l400_values']:
        l400_str = '→'.join(f"{v:.2f}" for v in trends['l400_values'])
        lines.append(f"  L400: {l400_str} → 趨勢: {trends['l400_trend']}")
    
    if trends['energy_values']:
        e_str = '→'.join(str(v) for v in trends['energy_values'])
        lines.append(f"  能量: {e_str} → 趨勢: {trends['energy_trend']}")
    
    # === 引擎距離 ===
    engine = classify_engine_type(races)
    dist_apt = compute_distance_aptitude(races, today_dist)
    
    today_rec = dist_apt['today_record']
    today_total = sum(today_rec)
    today_rec_str = f"{today_total}場 ({today_rec[0]}-{today_rec[1]}-{today_rec[2]})" if today_total else '未跑過'
    
    lines.append(f"🔧 **引擎距離:**")
    lines.append(f"  引擎: Type {engine['type']} ({engine['type_cn']}) | "
                 f"信心: {engine['confidence']} | "
                 f"依據: {'; '.join(engine['evidence']) if engine['evidence'] else '數據不足'}")
    lines.append(f"  最佳距離: {dist_apt['best_dist']}m | 今仗 {today_dist}m = {today_rec_str}")
    if dist_apt['dist_lines']:
        lines.append(f"  距離分佈: {' | '.join(dist_apt['dist_lines'])}")
    
    # === NEW: Phase 1D Trend Dimensions (from scraper data) ===
    if p_entries and HAS_SCRAPER:
        lines.append(f"")
        
        # Margin trend
        mt = compute_margin_trend(p_entries)
        if mt['values']:
            margin_vals = '→'.join(mt['values'][:6])
            lines.append(f"📏 **頭馬距離趨勢:** {margin_vals} → {mt['trend']}")
        
        # Weight trend
        wt = compute_weight_trend(p_entries, horse.get('body_weight'))
        if wt['values']:
            wt_vals = '→'.join(str(v) for v in wt['values'][:6])
            lines.append(f"📊 **體重趨勢:** {wt_vals} → {wt['trend']} ({wt['detail']})")
        
        # Gear changes
        gc = detect_gear_changes(p_entries)  # No today_gear in formguide context
        lines.append(f"🔧 **配備變動:** 上仗 {gc['last']} | {gc['signal']}")
        if gc.get('sip_hv2'):
            lines.append(f"   ⚠️ SIP-HV2 觸發：大幅配備變動")
        hist = '→'.join(gc['history'][:5]) if gc.get('history') else 'N/A'
        lines.append(f"   配備歷史: {hist}")
        
        # Rating trend
        rt = compute_rating_trend(p_entries)
        if rt['values']:
            rating_vals = '→'.join(str(v) for v in rt['values'][:6])
            lines.append(f"📈 **評分變動:** {rating_vals} → {rt['trend']}")
        
        # Running PI (precise from positions)
        rpi = compute_running_pi(p_entries)
        if rpi['pi_values']:
            pi_vals = ', '.join(f"{v:+d}" for v in rpi['pi_values'][:5])
            lines.append(f"🏃 **走位 PI:** [{pi_vals}] → 趨勢: {rpi['pi_trend']}")
    # === Form Lines (if available) ===
    if p_entries and HAS_FORM_LINES and form_lines_data:
        lines.append(f"")
        lines.append(f"🔗 **賽績線:**")
        lines.append(f"  **綜合評估:** {form_lines_data['rating']} (強組比例: {form_lines_data['stats']})")
        lines.append(f"")
        lines.append(f"| # | 日期 | 賽事 | 我嘅名次 | 對手 | 後續比賽Class | 對手後續成績 | 強度評估 |")
        lines.append(f"|---|------|------|----------|------|---------------|--------------|----------|")
        for tline in form_lines_data['table_lines']:
            lines.append(tline)
    
    lines.append(f"")
    lines.append(f"💡 **LLM 指示:** 引用此「完整賽績檔案」。嚴禁自行從 Formguide 重建。")
    lines.append(f"   所有 L400/走位/消耗/體重趨勢/配備變動/賽績線 均由 Python 計算，直接引用即可。")
    
    return '\n'.join(lines)


def extract_race_context(text: str) -> dict:
    """Extract race venue, distance, class from the overview line ONLY."""
    ctx = {'venue': '', 'distance': 0, 'class': 'C4'}
    
    # Only search the overview line, not the entire file
    overview_match = re.search(r'賽事日期.*?/\s*場次.*?/\s*跑道.*?:\s*(.+?)$', text, re.MULTILINE)
    if not overview_match:
        return ctx
    
    overview = overview_match.group(1)
    
    # Venue
    if '全天候' in overview or 'AWT' in overview:
        ctx['venue'] = '沙田AWT'
    elif '跑馬地' in overview:
        ctx['venue'] = '跑馬地'
    elif '沙田' in overview:
        ctx['venue'] = '沙田'
    
    # Distance
    dm = re.search(r'(\d{3,4})米', overview)
    if dm:
        ctx['distance'] = int(dm.group(1))
    
    # Class
    cm = re.search(r'第(\d)班', overview)
    if cm:
        ctx['class'] = f"C{cm.group(1)}"
    elif '分級賽' in overview or 'Group' in overview:
        ctx['class'] = 'G'
    elif '新馬' in overview or 'Griffin' in overview:
        ctx['class'] = 'GR'
    
    return ctx


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 inject_hkjc_fact_anchors.py <Formguide.txt> "
              "[--venue ST|HV] [--distance 1200] [--class 4] "
              "[--horse-ids 'HK_2024_K416,...'] [--output Facts.md]")
        sys.exit(1)
    
    fg_path = sys.argv[1]
    if not Path(fg_path).exists():
        print(f"❌ File not found: {fg_path}")
        sys.exit(1)
    
    # Parse CLI overrides
    venue_override = ''
    dist_override = 0
    class_override = ''
    horse_ids_str = ''
    output_path = ''
    enable_form_lines = True  # Re-enabled: User requested to keep Form Lines
    
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == '--venue' and i + 1 < len(args):
            v = args[i + 1]
            venue_override = {'ST': '沙田', 'HV': '跑馬地', 'AWT': '沙田AWT'}.get(v, v)
            i += 2
        elif args[i] == '--distance' and i + 1 < len(args):
            dist_override = int(args[i + 1])
            i += 2
        elif args[i] == '--class' and i + 1 < len(args):
            class_override = f"C{args[i + 1]}" if args[i + 1].isdigit() else args[i + 1]
            i += 2
        elif args[i] == '--horse-ids' and i + 1 < len(args):
            horse_ids_str = args[i + 1]
            enable_form_lines = True # Auto-enable if specifically requesting specific horses
            i += 2
        elif args[i] == '--output' and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] == '--form-lines':
            enable_form_lines = True
            i += 1
        elif args[i] == '--no-form-lines':
            enable_form_lines = False
            i += 1
        else:
            i += 1
    
    # Parse formguide
    data = parse_hkjc_formguide(fg_path)
    
    if not data['horses']:
        print("❌ No horses found in Formguide", file=sys.stderr)
        sys.exit(1)
    
    # Auto-detect race context
    text = Path(fg_path).read_text(encoding='utf-8')
    ctx = extract_race_context(text)
    
    today_venue = venue_override or ctx['venue']
    today_dist = dist_override or ctx['distance']
    race_class = class_override or ctx['class']
    
    # Parse horse IDs for scraper enrichment
    horse_id_list = [h.strip() for h in horse_ids_str.split(',') if h.strip()] if horse_ids_str else []
    if not horse_id_list:
        # Re-enabled automatic extraction
        horse_id_list = [h['brand_no'] for h in data['horses'] if h.get('brand_no')]
    
    print(f"📌 V2 HKJC 完整賽績檔案 — {len(data['horses'])} 匹馬", file=sys.stderr)
    print(f"   場地: {today_venue} | 距離: {today_dist}m | 班次: {race_class}", file=sys.stderr)
    if horse_id_list:
        print(f"   馬匹頁面: {len(horse_id_list)} 匹 (SSR enrichment)", file=sys.stderr)
    elif HAS_SCRAPER:
        print(f"   ⚠️ 未提供 --horse-ids，馬匹頁面數據不可用", file=sys.stderr)
    if not HAS_SCRAPER:
        print(f"   ⚠️ scrape_hkjc_horse_profile.py 未找到，新維度不可用", file=sys.stderr)
    if enable_form_lines:
        print(f"   🔗 賽績線: 已啟用", file=sys.stderr)
    
    std = get_standard_time(today_venue, today_dist, race_class)
    if std:
        print(f"   標準時間: {format_seconds(std)} ({std:.2f}s)", file=sys.stderr)
    else:
        print(f"   ⚠️ 找不到標準時間 ({today_venue}, {today_dist}m, {race_class})", file=sys.stderr)
    
    # Scrape horse profiles if IDs provided
    profiles = {}  # {horse_num: profile_data}
    form_lines_map = {}  # {horse_num: form_lines_data}
    if HAS_SCRAPER and horse_id_list:
        import time
        for idx, hid in enumerate(horse_id_list):
            if not hid or hid == '-':
                continue
            horse_num = idx + 1  # horse_ids are in order of horse number
            print(f"   Scraping {hid}...", file=sys.stderr)
            try:
                profile = scrape_horse_profile(hid)
                if not profile.get('error'):
                    profiles[horse_num] = profile
                    print(f"     ✅ {profile['name']}: {len(profile['entries'])} entries", file=sys.stderr)
                    
                    # Compute form lines if enabled
                    if enable_form_lines and HAS_FORM_LINES:
                        print(f"     🔗 Computing form lines...", file=sys.stderr)
                        fl = compute_form_lines(profile['entries'], max_races=5)
                        form_lines_map[horse_num] = fl
                        print(f"     🔗 {fl['rating']} ({fl['stats']})", file=sys.stderr)
                else:
                    print(f"     ❌ {hid}: {profile['error']}", file=sys.stderr)
            except Exception as e:
                print(f"     ❌ {hid}: {e}", file=sys.stderr)
            if idx < len(horse_id_list) - 1:
                time.sleep(0.5)  # Rate limiting
    
    # Generate output
    output_lines = []
    output_lines.append(f"# 📌 V2 HKJC 完整賽績檔案 — {len(data['horses'])} 匹馬")
    output_lines.append(f"場地: {today_venue} | 距離: {today_dist}m | 班次: {race_class}")
    if profiles:
        output_lines.append(f"馬匹頁面數據: {len(profiles)} 匹已豐富 (頭馬距離/體重/配備/評分/走位)")
    if form_lines_map:
        output_lines.append(f"賽績線: {len(form_lines_map)} 匹已查冊")
    output_lines.append(f"")
    output_lines.append(f"{'=' * 70}")
    output_lines.append(f"")
    
    for horse in data['horses']:
        profile = profiles.get(horse['num'])
        fl_data = form_lines_map.get(horse['num'])
        block = generate_horse_block(horse, today_venue, today_dist, race_class, profile, fl_data)
        output_lines.append(block)
        output_lines.append(f"")
        output_lines.append(f"{'─' * 70}")
        output_lines.append(f"")
    
    output_lines.append(f"✅ {len(data['horses'])} 匹馬嘅完整賽績檔案已生成。")
    if profiles:
        output_lines.append(f"   {len(profiles)} 匹已含馬匹頁面豐富數據。")
    if form_lines_map:
        output_lines.append(f"   {len(form_lines_map)} 匹已含賽績線。")
    
    output_text = '\n'.join(output_lines)
    
    if output_path:
        Path(output_path).write_text(output_text, encoding='utf-8')
        print(f"✅ 已寫入 → {output_path}", file=sys.stderr)
    else:
        print(output_text)


if __name__ == '__main__':
    main()
