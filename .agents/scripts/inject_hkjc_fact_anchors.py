#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
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

# Load HKJC Reference Sectional Times (Claw Code extracted)
_REF_SECTIONALS = None
def load_reference_sectionals() -> dict:
    """Load reference sectional times from JSON (cached)."""
    global _REF_SECTIONALS
    if _REF_SECTIONALS is not None:
        return _REF_SECTIONALS
    ref_path = Path(__file__).parent / 'hkjc_reference_sectionals.json'
    if ref_path.exists():
        try:
            with open(ref_path, 'r', encoding='utf-8') as f:
                _REF_SECTIONALS = json.load(f)
            return _REF_SECTIONALS
        except Exception:
            pass
    _REF_SECTIONALS = {}
    return _REF_SECTIONALS

def get_reference_sections(venue: str, distance: int, race_class: str) -> dict:
    """Get reference sectional times for a venue/distance/class.
    Returns dict with 'sections', 'labels' or empty dict."""
    ref = load_reference_sectionals()
    if not ref or 'venues' not in ref:
        return {}
    # Map venue
    if 'AWT' in venue or '全天候' in venue:
        vkey = 'sha_tin_awt'
    elif '跑馬地' in venue:
        vkey = 'happy_valley_turf'
    elif '沙田' in venue:
        vkey = 'sha_tin_turf'
    else:
        vkey = 'sha_tin_turf'
    venues = ref.get('venues', {})
    if vkey not in venues:
        return {}
    dists = venues[vkey]
    dkey = str(distance)
    if dkey not in dists:
        return {}
    classes = dists[dkey]
    # Map class
    cmap = {'第一班': 'C1', '第二班': 'C2', '第三班': 'C3', '第四班': 'C4',
            '第五班': 'C5', '一級賽': 'G', '二級賽': 'G', '三級賽': 'G',
            '分級賽': 'G', '新馬賽': 'GR', 'C1': 'C1', 'C2': 'C2',
            'C3': 'C3', 'C4': 'C4', 'C5': 'C5', 'G': 'G', 'GR': 'GR'}
    ckey = cmap.get(race_class, race_class)
    if ckey not in classes:
        # Fallback
        for fb in ['C4', 'C3', 'C5', 'C2', 'C1', 'G']:
            if fb in classes:
                ckey = fb
                break
    if ckey not in classes:
        return {}
    return classes[ckey]

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


def compute_sectional_from_splits(splits: list, distance: int,
                                   venue: str = '', race_class: str = '') -> dict:
    """Compute full sectional profile from splits.
    
    HKJC splits are typically:
    - 1000m: 3 splits (first ~200m, 2x~400m)
    - 1200m: 3 splits (~400m each) or 4 splits for some
    - 1400m: 4 splits (first ~200m + 3x~400m)
    - 1600m: 4 splits (~400m each)
    - 1800m: 5 splits (first ~200m + 4x~400m)
    - 2000m: 5 splits (~400m each)
    - 2200m: 6 splits
    
    Returns L400, L800, full section profile, and standard deviation per section.
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
    
    # === Full sectional profile ===
    result['all_sections'] = splits
    result['section_count'] = len(splits)
    
    # Generate section labels based on distance
    labels = _compute_section_labels(distance, len(splits))
    result['section_labels'] = labels
    
    # === Standard deviation per section ===
    if venue and race_class:
        ref = get_reference_sections(venue, distance, race_class)
        ref_sections = ref.get('sections', [])
        if ref_sections and len(ref_sections) == len(splits):
            diffs = [round(a - r, 2) for a, r in zip(splits, ref_sections)]
            result['section_diffs'] = diffs
            result['par_sections'] = ref_sections
            result['par_labels'] = ref.get('labels', [])
    
    # === Pace shape classification ===
    result['pace_shape'] = _classify_pace_shape(splits)
    
    return result


def _compute_section_labels(distance: int, n_sections: int) -> list:
    """Generate section labels like ['0-400m', '400-800m', ...]."""
    if distance == 1000 and n_sections == 3:
        return ['0-200m', '200-600m', '600-1000m']
    elif distance == 1200 and n_sections == 3:
        return ['0-400m', '400-800m', '800-1200m']
    elif distance == 1400 and n_sections == 4:
        return ['0-200m', '200-600m', '600-1000m', '1000-1400m']
    elif distance == 1600 and n_sections == 4:
        return ['0-400m', '400-800m', '800-1200m', '1200-1600m']
    elif distance == 1800 and n_sections == 5:
        return ['0-200m', '200-600m', '600-1000m', '1000-1400m', '1400-1800m']
    elif distance == 2000 and n_sections == 5:
        return ['0-400m', '400-800m', '800-1200m', '1200-1600m', '1600-2000m']
    elif distance == 2200 and n_sections == 6:
        return ['0-200m', '200-600m', '600-1000m', '1000-1400m', '1400-1800m', '1800-2200m']
    elif distance == 2400 and n_sections == 6:
        return ['0-400m', '400-800m', '800-1200m', '1200-1600m', '1600-2000m', '2000-2400m']
    else:
        return [f'S{i+1}' for i in range(n_sections)]


def _classify_pace_shape(splits: list) -> str:
    """Classify pace shape from sectional splits."""
    if len(splits) < 2:
        return '未知'
    # Compare first half vs second half (excluding short first section)
    main_splits = splits if len(splits) <= 3 else splits[1:]  # skip short first section
    mid = len(main_splits) // 2
    first_half_avg = sum(main_splits[:mid]) / max(mid, 1)
    second_half_avg = sum(main_splits[mid:]) / max(len(main_splits) - mid, 1)
    diff = second_half_avg - first_half_avg
    if abs(diff) < 0.3:
        return '均速型 ✅'
    elif diff < -0.3:
        return '漸進加速 ✅'
    elif diff > 0.5:
        return '快開慢收 ⚠️'
    elif diff < -0.5:
        return '慢開快收 ✅'
    else:
        return '波動型 ➖'


def compute_eem_pre_assessment(races: list) -> dict:
    """Pre-compute EEM (Energy Expenditure Model) assessment from race history.
    
    Analyzes running position patterns (XW) across recent races to provide:
    - Last race running position and consumption
    - Cumulative fatigue from last 3 races
    - Consumption trend (increasing/stable/decreasing)
    - EEM trigger conditions (Monster/Rebounder/Hidden Rebound)
    """
    result = {
        'last_wide': '-',
        'last_consumption': '-',
        'consumption_history': [],
        'cumulative_fatigue': '-',
        'consumption_trend': '-',
        'triggers': [],
        'summary': '-'
    }
    
    if not races:
        return result
    
    # Extract wide info from recent races
    consumption_levels = []  # (pattern, consumption, finish)
    for r in races[:6]:
        wide = r.get('wide_info', {})
        pattern = wide.get('pattern', '')
        consumption = wide.get('consumption', '未知')
        finish = r.get('finish', 0)
        if pattern:
            consumption_levels.append({
                'pattern': pattern,
                'consumption': consumption,
                'finish': finish,
                'max_wide': wide.get('max_wide', 0),
                'avg_wide': wide.get('avg_wide', 0)
            })
    
    if not consumption_levels:
        result['summary'] = '走位數據不足，基於可用信息推斷為中等消耗'
        return result
    
    # Last race
    last = consumption_levels[0]
    result['last_wide'] = f"({last['pattern']})" if last['pattern'] else '-'
    result['last_consumption'] = last['consumption']
    
    # Consumption history string
    result['consumption_history'] = [c['consumption'] for c in consumption_levels[:3]]
    
    # Cumulative fatigue (last 3 races)
    consumption_map = {'極高消耗': 5, '高消耗': 4, '中等消耗': 3, '中低消耗': 2, '低消耗': 1, '未知': 2}
    recent_scores = [consumption_map.get(c['consumption'], 2) for c in consumption_levels[:3]]
    avg_score = sum(recent_scores) / len(recent_scores)
    if avg_score >= 4:
        result['cumulative_fatigue'] = '高 ⚠️'
    elif avg_score >= 3:
        result['cumulative_fatigue'] = '中等'
    elif avg_score >= 2:
        result['cumulative_fatigue'] = '中低'
    else:
        result['cumulative_fatigue'] = '低 ✅'
    
    # Consumption trend
    if len(recent_scores) >= 2:
        if recent_scores[0] > recent_scores[-1] + 0.5:
            result['consumption_trend'] = '逐仗增加 ⚠️'
        elif recent_scores[0] < recent_scores[-1] - 0.5:
            result['consumption_trend'] = '逐仗減少 ✅'
        else:
            result['consumption_trend'] = '穩定'
    
    # EEM Triggers
    triggers = []
    # Monster: high consumption + still finished top 3
    if consumption_levels[0]['consumption'] in ('極高消耗', '高消耗') and consumption_levels[0]['finish'] <= 3:
        triggers.append(f"✅ 逆境破格: 上仗{consumption_levels[0]['consumption']}仍跑第{consumption_levels[0]['finish']} → 實力深不見底")
    
    # Rebounder: high consumption last time → expect rebound with lower consumption
    if len(consumption_levels) >= 2:
        if consumption_levels[0]['consumption'] in ('極高消耗', '高消耗') and consumption_levels[0]['finish'] > 4:
            triggers.append(f"✅ 超級反彈候選: 上仗{consumption_levels[0]['consumption']}跑第{consumption_levels[0]['finish']}，若今仗減少消耗可大幅反彈")
    
    # Engine Depletion: consecutive high consumption
    if len(consumption_levels) >= 2 and all(
        c['consumption'] in ('極高消耗', '高消耗') for c in consumption_levels[:2]
    ):
        triggers.append(f"⚠️ 實力見底風險: 連續{len([c for c in consumption_levels[:3] if c['consumption'] in ('極高消耗', '高消耗')])}仗高消耗，累積疲勞顯著")
    
    result['triggers'] = triggers
    
    # Summary
    trigger_str = ' | '.join(triggers) if triggers else '無特殊觸發'
    result['summary'] = f"上仗{result['last_consumption']} → 累積{result['cumulative_fatigue']} → {trigger_str}"
    
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


def auto_determine_forgiveness(comment: str) -> str:
    """Auto-determine forgiveness status from race comment keywords.
    
    Scans the comment for known forgiveness triggers and returns
    a specific determination instead of [需判定].
    
    Returns:
        str: Forgiveness determination, e.g. '受阻蝕位', '外疊蝕位', or '[-]'
    """
    if not comment:
        return '[-]'
    
    # Priority-ordered triggers (more severe first)
    triggers = []
    
    # Health issues (most forgiving)
    if any(kw in comment for kw in ['心律不正常', '氣管有血', '喘鳴症', '氣管有痰']):
        triggers.append('健康問題')
    
    # Physical interference
    if any(kw in comment for kw in ['受阻', '受擠迫', '被碰撞', '發生碰撞', '被夾',
                                      '受困', '未能望空', '空位不足']):
        triggers.append('受阻蝕位')
    
    # Wide running
    if any(kw in comment for kw in ['走大外疊', '大外疊', '五疊', '六疊']):
        triggers.append('外疊蝕位')
    elif any(kw in comment for kw in ['外閃', '向外斜跑']):
        triggers.append('外閃蝕位')
    
    # Pace disadvantage
    if any(kw in comment for kw in ['極慢步速', '極快步速']):
        triggers.append('步速極端')
    
    # Gate issues
    if any(kw in comment for kw in ['出閘緩慢', '起步時向外', '起步時發生', '慢閘']):
        triggers.append('起步不利')
    
    # Competition events (noted by stewards)
    if '見競賽事件報告' in comment:
        triggers.append('見競賽事件')
    
    if triggers:
        return ' / '.join(triggers[:2])  # Max 2 triggers for conciseness
    
    return '[-]'


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
            sectionals = compute_sectional_from_splits(splits, distance, venue=venue)
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
    
    win_list = []
    close_wins = []
    close_places = []
    
    for r in reversed(races):
        d = r.get('distance', 0)
        f = r.get('finish', 0)
        if d <= 0 or f <= 0:
            continue
            
        if f == 1:
            win_list.append(f"{d}m")
            if today_dist > 0 and abs(d - today_dist) <= 100:
                close_wins.append(d)
        elif 2 <= f <= 3:
            if today_dist > 0 and abs(d - today_dist) <= 100:
                close_places.append(d)
                
    close_wins = list(dict.fromkeys(close_wins))
    close_places = list(dict.fromkeys(close_places))

    return {
        'best_dist': best_dist,
        'dist_bands': dist_bands,
        'dist_lines': dist_lines,
        'today_record': dist_bands.get(today_dist, [0, 0, 0]),
        'win_seq': win_list,
        'close_wins': close_wins,
        'close_places': close_places
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
                ftime_sec = parse_time_to_seconds(ftime)
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
        
        forgiveness = auto_determine_forgiveness(comment)
        lines.append(f"| {i+1} | {date} | {venue} | {distance} | {class_g} | {barrier} | {jockey} | {weight} | {finish} | {margin} | {energy_str} | {l400_str} | {wide_str} | {consumption} | {pos_str} | {ftime} | {std_diff_str} | {dw_str} | {gear} | {comment} | {forgiveness} |")

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
                        ftime_sec = parse_time_to_seconds(ftime)
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
                forgiveness = auto_determine_forgiveness(comment)
                lines.append(f"| {i+1} | {date} | {venue} | {distance} | {class_g} | {barrier} | {jockey} | {weight} | {finish} | {margin} | {energy_str} | {l400_str} | {wide_str} | {consumption} | {pos_str} | {ftime} | {std_diff_str} | {dw_str} | {gear} | {comment} | {forgiveness} |")

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
    
    # === 完成時間偏差趨勢 [SIP-P2c] ===
    ft_deviations = []
    for i in range(min(len(races), 6)):
        r = races[i]
        p = p_entries[i] if i < len(p_entries) else {}
        ftime = p.get('finish_time_raw', '-')
        if ftime and ftime != '-':
            ftime_sec = parse_time_to_seconds(ftime)
            r_venue = r.get('venue', '')[:4]
            r_dist = r.get('distance', 0)
            r_class = p.get('class_grade', '')
            if r_class:
                cmap = {'1': '第一班', '2': '第二班', '3': '第三班', '4': '第四班', '5': '第五班'}
                r_class = cmap.get(str(r_class), r_class)
            race_std = get_standard_time(r_venue, r_dist, r_class)
            if ftime_sec and race_std:
                ft_deviations.append(round(ftime_sec - race_std, 2))
    
    if len(ft_deviations) >= 2:
        lines.append(f"")
        lines.append(f"📊 **完成時間偏差趨勢 [SIP-P2c] (vs HKJC 標準):**")
        dev_str = '→'.join(f"{v:+.2f}s" for v in ft_deviations)
        # Trend analysis
        if len(ft_deviations) >= 3:
            recent_avg = sum(ft_deviations[:len(ft_deviations)//2]) / max(len(ft_deviations)//2, 1)
            older_avg = sum(ft_deviations[len(ft_deviations)//2:]) / max(len(ft_deviations) - len(ft_deviations)//2, 1)
            trend_delta = recent_avg - older_avg
        else:
            trend_delta = ft_deviations[0] - ft_deviations[-1]
        if trend_delta < -0.3:
            ft_trend = '📈改善中 ✅'
            ft_reading = '近仗越跑越快於標準 — 正面'
        elif trend_delta > 0.3:
            ft_trend = '📉退步中 ⚠️'
            ft_reading = '近仗越跑越慢於標準 — 負面'
        else:
            ft_trend = '📊穩定'
            ft_reading = '完成時間相對標準穩定'
        # Absolute level
        avg_dev = sum(ft_deviations[:3]) / min(len(ft_deviations), 3)
        if avg_dev < -0.5:
            ft_level = '✅✅ 持續快於標準'
        elif avg_dev < 0:
            ft_level = '✅ 略快於標準'
        elif avg_dev < 0.5:
            ft_level = '➖ 接近標準水平'
        elif avg_dev < 1.5:
            ft_level = '⚠️ 略慢於標準'
        else:
            ft_level = '❌ 明顯慢於標準'
        lines.append(f"  偏差: {dev_str} → 趨勢: {ft_trend}")
        lines.append(f"  水平: {ft_level} (近 {min(len(ft_deviations), 3)} 仗平均偏差: {avg_dev:+.2f}s)")
        lines.append(f"  含金量: {ft_reading}")
    
    # === 全段速剖面 (Full Sectional Profile) ===
    sect_profile_rows = []
    for i in range(min(len(races), 3)):  # Last 3 races
        r = races[i]
        sect = r.get('sectionals', {})
        all_sects = sect.get('all_sections', [])
        if all_sects:
            r_venue = r.get('venue', '')
            r_dist = r.get('distance', 0)
            r_class = ''
            if p_entries and i < len(p_entries):
                r_class = p_entries[i].get('class_grade', '')
            # Get reference sections
            ref = get_reference_sections(r_venue, r_dist, r_class)
            ref_sects = ref.get('sections', [])
            labels = sect.get('section_labels', [])
            
            row = {
                'date': r.get('date', ''),
                'dist': r_dist,
                'sections': all_sects,
                'labels': labels,
                'ref_sections': ref_sects,
                'shape': sect.get('pace_shape', '-')
            }
            sect_profile_rows.append(row)
    
    if sect_profile_rows:
        lines.append(f"")
        lines.append(f"📊 **全段速剖面 (Full Sectional Profile — 近 {len(sect_profile_rows)} 仗):**")
        # Dynamic header based on max sections
        max_sects = max(len(r['sections']) for r in sect_profile_rows)
        s_headers = ' | '.join(f"S{i+1}" for i in range(max_sects))
        d_headers = ' | '.join(f"Δ{i+1}" for i in range(max_sects))
        lines.append(f"| # | 日期 | 距離 | {s_headers} | {d_headers} | 形態 |")
        sep = ' | '.join('---' for _ in range(max_sects))
        lines.append(f"|---|------|------|{sep}|{sep}|------|")
        for idx, row in enumerate(sect_profile_rows):
            s_vals = ' | '.join(f"{v:.2f}" for v in row['sections'])
            # Pad if fewer sections
            pad_count = max_sects - len(row['sections'])
            if pad_count > 0:
                s_vals += ' | ' + ' | '.join('-' for _ in range(pad_count))
            # Diffs
            if row['ref_sections'] and len(row['ref_sections']) == len(row['sections']):
                d_vals = ' | '.join(f"{a-r:+.2f}" for a, r in zip(row['sections'], row['ref_sections']))
            else:
                d_vals = ' | '.join('-' for _ in range(len(row['sections'])))
            if pad_count > 0:
                d_vals += ' | ' + ' | '.join('-' for _ in range(pad_count))
            lines.append(f"| {idx+1} | {row['date']} | {row['dist']} | {s_vals} | {d_vals} | {row['shape']} |")
        
        # Section analysis summary
        if sect_profile_rows[0]['ref_sections'] and len(sect_profile_rows[0]['ref_sections']) == len(sect_profile_rows[0]['sections']):
            diffs = [a - r for a, r in zip(sect_profile_rows[0]['sections'], sect_profile_rows[0]['ref_sections'])]
            alerts = []
            labels = sect_profile_rows[0].get('labels', [])
            for j, d in enumerate(diffs):
                lbl = labels[j] if j < len(labels) else f'S{j+1}'
                if d < -0.3:
                    alerts.append(f"⚡ {lbl} 比標準快 {abs(d):.2f}s → 前段消耗偏高" if j < len(diffs)//2 else f"⚡ {lbl} 比標準快 {abs(d):.2f}s → 有餘力")
                elif d > 0.5:
                    alerts.append(f"⚠️ {lbl} 比標準慢 {d:.2f}s → {'後段衰退' if j >= len(diffs)//2 else '起步偏慢'}")
            if alerts:
                for alert in alerts:
                    lines.append(f"  {alert}")
    
    # === EEM 預評估 (自動計算) ===
    eem = compute_eem_pre_assessment(races)
    lines.append(f"")
    lines.append(f"⚡ **EEM 預評估 (自動計算):**")
    lines.append(f"  上仗走位: {eem['last_wide']} → {eem['last_consumption']}")
    if eem['consumption_history']:
        hist_str = ' → '.join(eem['consumption_history'])
        lines.append(f"  近 {len(eem['consumption_history'])} 仗消耗: {hist_str} → 累積: {eem['cumulative_fatigue']}")
    if eem['consumption_trend'] != '-':
        lines.append(f"  走位消耗趨勢: {eem['consumption_trend']}")
    if eem['triggers']:
        lines.append(f"  EEM 觸發:")
        for trigger in eem['triggers']:
            lines.append(f"    {trigger}")
    else:
        lines.append(f"  EEM 觸發: ➖ 正常消耗，無特殊條件")
    
    # === 引擎距離 ===
    engine = classify_engine_type(races)
    dist_apt = compute_distance_aptitude(races, today_dist)
    
    today_rec = dist_apt['today_record']
    today_total = sum(today_rec)
    
    lines.append(f"🔧 **引擎與距離:**")
    lines.append(f"  引擎: Type {engine['type']} ({engine['type_cn']}) | "
                 f"信心: {engine['confidence']} | "
                 f"依據: {'; '.join(engine['evidence']) if engine['evidence'] else '數據不足'}")
                 
    if dist_apt['dist_lines']:
        lines.append(f"  距離分佈: {' | '.join(dist_apt['dist_lines'])}")
        
    w_seq_str = " → ".join(dist_apt['win_seq']) if dist_apt.get('win_seq') else "未有頭馬紀錄"
    lines.append(f"  勝出途程序列: {w_seq_str}")
    
    if today_dist > 0:
        if today_total > 0:
            lines.append(f"  最佳距離: {dist_apt['best_dist']}m | 今仗 {today_dist}m = {today_total}場 ({today_rec[0]}-{today_rec[1]}-{today_rec[2]})")
        elif dist_apt.get('close_wins'):
            lines.append(f"  最佳距離: {dist_apt['best_dist']}m | 今仗 {today_dist}m = 未跑過，但有相近贏馬經驗 ({', '.join([str(x)+'m' for x in dist_apt['close_wins']])}) ✅")
        elif dist_apt.get('close_places'):
            lines.append(f"  最佳距離: {dist_apt['best_dist']}m | 今仗 {today_dist}m = 未跑過，但有相近上名經驗 ({', '.join([str(x)+'m' for x in dist_apt['close_places']])})")
        else:
            lines.append(f"  最佳距離: {dist_apt['best_dist']}m | 今仗 {today_dist}m = 未跑過且無相近近績 (±100m) ⚠️")
    
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
