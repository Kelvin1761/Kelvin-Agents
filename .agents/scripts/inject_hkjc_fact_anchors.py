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
from typing import Optional, Tuple
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
# HKJC Official Standard Times — Auto-loaded from scraped JSON
# Fallback: hardcoded dict if JSON not available
# ========================================================================
_SCRAPED_STD_TIMES = None
def _load_scraped_standard_times() -> dict:
    """Load standard times from hkjc_standard_times.json (cached)."""
    global _SCRAPED_STD_TIMES
    if _SCRAPED_STD_TIMES is not None:
        return _SCRAPED_STD_TIMES
    json_path = Path(__file__).parent / 'hkjc_standard_times.json'
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            _SCRAPED_STD_TIMES = data.get('standard_times', {})
            return _SCRAPED_STD_TIMES
        except Exception:
            pass
    _SCRAPED_STD_TIMES = {}
    return _SCRAPED_STD_TIMES

# Hardcoded fallback (used when JSON unavailable)
STANDARD_TIMES = {
    ('沙田', 1000): {'G': 55.90, 'C2': 56.05, 'C3': 56.45, 'C4': 56.65, 'C5': 57.00, 'GR': 56.65},
    ('沙田', 1200): {'G': 68.15, 'C1': 68.45, 'C2': 68.65, 'C3': 69.00, 'C4': 69.35, 'C5': 69.55, 'GR': 69.90},
    ('沙田', 1400): {'G': 81.10, 'C1': 81.25, 'C2': 81.45, 'C3': 81.65, 'C4': 82.00, 'C5': 82.30},
    ('沙田', 1600): {'G': 93.90, 'C1': 94.05, 'C2': 94.25, 'C3': 94.70, 'C4': 94.90, 'C5': 95.45},
    ('沙田', 1800): {'G': 107.10, 'C2': 107.30, 'C3': 107.50, 'C4': 107.85, 'C5': 108.45},
    ('沙田', 2000): {'G': 120.50, 'C1': 121.20, 'C2': 121.70, 'C3': 121.90, 'C4': 122.35, 'C5': 122.65},
    ('沙田', 2400): {'G': 147.00},
    ('跑馬地', 1000): {'C2': 56.40, 'C3': 56.65, 'C4': 57.20, 'C5': 57.35},
    ('跑馬地', 1200): {'C1': 69.10, 'C2': 69.30, 'C3': 69.60, 'C4': 69.90, 'C5': 70.10},
    ('跑馬地', 1650): {'C1': 99.10, 'C2': 99.30, 'C3': 99.90, 'C4': 100.10, 'C5': 100.30},
    ('跑馬地', 1800): {'G': 108.95, 'C2': 109.15, 'C3': 109.45, 'C4': 109.65, 'C5': 109.95},
    ('跑馬地', 2200): {'C3': 136.60, 'C4': 137.05, 'C5': 137.35},
    ('沙田AWT', 1200): {'C2': 68.35, 'C3': 68.55, 'C4': 68.95, 'C5': 69.35},
    ('沙田AWT', 1650): {'C1': 97.80, 'C2': 98.40, 'C3': 98.60, 'C4': 99.05, 'C5': 99.45},
    ('沙田AWT', 1800): {'C3': 108.05, 'C4': 108.55, 'C5': 109.45},
}

# ========================================================================
# Draw Stats Loader
# ========================================================================
_DRAW_STATS = None
def load_draw_stats() -> dict:
    """Load draw stats from hkjc_draw_stats.json (cached)."""
    global _DRAW_STATS
    if _DRAW_STATS is not None:
        return _DRAW_STATS
    json_path = Path(__file__).parent / 'hkjc_draw_stats.json'
    if json_path.exists():
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                _DRAW_STATS = json.load(f)
            return _DRAW_STATS
        except Exception:
            pass
    _DRAW_STATS = {}
    return _DRAW_STATS


def _normalize_draw_stats_meeting_venue(value: str) -> str:
    text = str(value or '').strip()
    if any(token in text for token in ('跑馬地', 'Happy Valley', 'HappyValley', 'HV')):
        return '跑馬地'
    if any(token in text for token in ('沙田', 'Sha Tin', 'ShaTin', 'ST')):
        return '沙田'
    return ''


def _normalize_expected_draw_venue(value: str) -> str:
    text = str(value or '').strip()
    if '跑馬地' in text:
        return '跑馬地'
    if '沙田' in text or 'AWT' in text:
        return '沙田'
    return ''


def _expected_draw_surface(expected_venue: str) -> str:
    text = str(expected_venue or '').strip()
    if 'AWT' in text or '全天候' in text or '泥' in text:
        return '全天候'
    if text:
        return '草地'
    return ''


def _resolve_draw_stats_race(
    race_num: int,
    expected_venue: str = '',
    expected_distance: int = 0,
    expected_surface: str = '',
) -> dict:
    ds = load_draw_stats()
    if not ds or 'races' not in ds:
        return {}
    race = next((item for item in ds.get('races', []) if item.get('race') == race_num), None)
    if not race:
        return {}

    meeting_venue = _normalize_draw_stats_meeting_venue(ds.get('meta', {}).get('meeting', ''))
    venue_norm = _normalize_expected_draw_venue(expected_venue)
    surface_norm = expected_surface or _expected_draw_surface(expected_venue)

    if venue_norm and meeting_venue != venue_norm:
        return {}
    if expected_distance:
        try:
            if int(race.get('distance') or 0) != int(expected_distance):
                return {}
        except (TypeError, ValueError):
            return {}
    if surface_norm and str(race.get('surface') or '').strip() != surface_norm:
        return {}

    return race


def get_draw_verdict(
    race_num: int,
    draw: int,
    expected_venue: str = '',
    expected_distance: int = 0,
    expected_surface: str = '',
) -> str:
    """Get draw verdict for a specific race/draw. Returns e.g. '✅有利 (上名30%)' or empty."""
    race = _resolve_draw_stats_race(race_num, expected_venue, expected_distance, expected_surface)
    if not race:
        return ''
    for d in race.get('draws', []):
        if d.get('draw') == draw:
            starts = d.get('starts', 0)
            low_sample = ' ⚠️樣本少' if starts < 10 else ''
            return f"{d['verdict']} (上名{d.get('place_pct','?')}%){low_sample}"
    return ''


def get_draw_detail(
    race_num: int,
    draw: int,
    expected_venue: str = '',
    expected_distance: int = 0,
    expected_surface: str = '',
) -> dict:
    """Get full draw stats dict for a specific race/draw.
    Returns dict with win_pct, quinella_pct, place_pct, verdict, etc."""
    race = _resolve_draw_stats_race(race_num, expected_venue, expected_distance, expected_surface)
    if not race:
        return {}
    for d in race.get('draws', []):
        if d.get('draw') == draw:
            return d
    return {}


def get_draw_summary_block(
    race_num: int,
    expected_venue: str = '',
    expected_distance: int = 0,
    expected_surface: str = '',
) -> str:
    """Generate 🎯 檔位優劣判讀 block for Facts.md header."""
    ds = load_draw_stats()
    race = _resolve_draw_stats_race(race_num, expected_venue, expected_distance, expected_surface)
    if not ds or not race:
        return ''
    lines = [f"### 🎯 檔位優劣判讀 ({race.get('distance','')}m {race.get('surface','')})"]
    avg_place = race.get('avg_place_pct', race.get('avg_win_pct', 0))
    lines.append(f"平均上名率: {avg_place}%")
    favourable = [d for d in race['draws'] if d['verdict'] == '✅有利']
    unfavourable = [d for d in race['draws'] if d['verdict'] == '❌不利']
    if favourable:
        draws_str = ', '.join(f"檔{d['draw']}(上名{d.get('place_pct','?')}%/入Q{d.get('quinella_pct','?')}%/勝{d['win_pct']}%{' ⚠️樣本少' if d.get('starts',0)<10 else ''})" for d in favourable)
        lines.append(f"✅ 有利檔位: {draws_str}")
    if unfavourable:
        draws_str = ', '.join(f"檔{d['draw']}(上名{d.get('place_pct','?')}%/入Q{d.get('quinella_pct','?')}%/勝{d['win_pct']}%{' ⚠️樣本少' if d.get('starts',0)<10 else ''})" for d in unfavourable)
        lines.append(f"❌ 不利檔位: {draws_str}")
    if not favourable and not unfavourable:
        lines.append("⚠️ 所有檔位上名率接近平均，無明顯優劣")
    lines.append(f"(數據來源: HKJC 檔位統計 {ds.get('meta',{}).get('meeting','')})")
    return '\n'.join(lines)

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
    """Look up standard time for venue/distance/class.
    Priority: scraped JSON > hardcoded fallback."""
    # Normalise venue
    v = venue
    if 'AWT' in venue or '全天候' in venue:
        v = '沙田AWT'
    elif '沙田' in venue:
        v = '沙田'
    elif '跑馬地' in venue:
        v = '跑馬地'
    
    # Try scraped JSON first
    scraped = _load_scraped_standard_times()
    if scraped:
        flat_key = f"{v}_{distance}_{race_class}"
        if flat_key in scraped:
            return scraped[flat_key]
        # Fallback within scraped
        for fb in ['C4', 'C3', 'C5', 'C2', 'C1', 'G']:
            fk = f"{v}_{distance}_{fb}"
            if fk in scraped:
                return scraped[fk]
    
    # Hardcoded fallback
    key = (v, distance)
    if key not in STANDARD_TIMES:
        return None
    class_map = STANDARD_TIMES[key]
    if race_class in class_map:
        return class_map[race_class]
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
    elif '中等偏快步速' in comment:
        return '中等偏快'
    elif '中等偏慢步速' in comment:
        return '中等偏慢'
    elif '快步速' in comment:
        return '快'
    elif '慢步速' in comment:
        return '慢'
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


def get_pdf_path(formguide_path: str) -> Optional[Path]:
    fp = Path(formguide_path)
    d_name = fp.parent.name
    # Extract month and day: "2026-05-24_ShaTin" -> "05-24"
    import re
    m = re.search(r'\d{4}-(\d{2}-\d{2})_', d_name)
    if m:
        prefix = m.group(1)
        pdf_path = fp.parent / f"{prefix} 全日出賽馬匹資料 (PDF).md"
        if pdf_path.exists():
            return pdf_path
    return None


def parse_pdf_overseas_races(pdf_path: Path, brand_no: str, horse_name: str) -> list:
    """Parse overseas race records from the full PDF dump."""
    if not pdf_path or not pdf_path.exists():
        return []
        
    try:
        with open(pdf_path, 'r', encoding='utf-8') as f:
            text = f.read()
    except Exception as e:
        print(f"Error reading PDF text: {e}")
        return []
        
    lines = text.split('\n')
    start_idx = -1
    
    # 1. Find horse section
    for i, line in enumerate(lines):
        # Match standard HKJC horse (e.g. "3 浪漫勇士 E486") or foreign horse (e.g. "2 大怪奇 池江泰壽")
        # Match format: start with index, then horse name
        if (brand_no and brand_no != 'UNKNOWN' and brand_no in line) or \
           re.search(rf'^\s*(?:S?\d+)\s+{re.escape(horse_name)}', line):
            start_idx = i
            break
            
    if start_idx == -1:
        return []
        
    extracted_races = []
    
    # 2. Extract race rows
    for line in lines[start_idx+1:]:
        # Break if we hit the next horse header
        if re.match(r'^\s*(?:S?\d+)\s+([^\x00-\x7F]+)', line) and horse_name not in line:
            # basic check to ensure it's actually a header (not just a race record)
            if len(line.split()) >= 3 and not '/' in line.split()[0]:
                break
                
        # Match a race row e.g. "1/8 16/3/25 3歲 ..." or "4/14 559 29/3/26 4 ..."
        m = re.match(r'^\s*([0-9a-zA-Z]+)/(\d+)\s+(.+)$', line)
        if m:
            placing_str = m.group(1)
            field_size = int(m.group(2))
            rest = m.group(3)
            
            date_m = re.search(r'\b(\d{1,2}/\d{1,2}/\d{2})\b', rest)
            if not date_m:
                continue
            date_str = date_m.group(1)
            
            # Format to dd/mm/yyyy
            parts = date_str.split('/')
            if len(parts) == 3:
                # Assuming PDF uses dd/mm/yy
                year = f"20{parts[2]}" if len(parts[2]) == 2 else parts[2]
                formatted_date = f"{parts[0].zfill(2)}/{parts[1].zfill(2)}/{year}"
            else:
                formatted_date = date_str
            
            dist_m = re.search(r'\b([1-4]\d00|1650)\b', rest)
            distance = int(dist_m.group(1)) if dist_m else 0
            
            placing = 0
            if placing_str.isdigit():
                placing = int(placing_str)
            elif placing_str in ['W', 'UR', 'F', 'T', 'PU', 'DISQ']:
                placing = 99
                
            time_m = re.findall(r'\b(\d{1,2}\.\d{2}\.\d{2})\b', rest)
            finish_time = time_m[-1] if time_m else '-'
            if finish_time == '-':
                 short_times = re.findall(r'\b(\d{2}\.\d{2})\b', rest)
                 finish_time = short_times[-1] if short_times else '-'
                 
            # Is this an overseas race? Often missing HKJC numeric index before the date.
            # E.g. "1/8 16/3/25" vs "10/12 518 15/3/26"
            # We'll tag it based on distance or context if needed, but for now just extract.
            
            extracted_races.append({
                'Date': formatted_date,
                'Distance': distance,
                'Placing': placing,
                'Field_Size': field_size,
                'Finish_Time_Raw': finish_time,
                'Is_PDF_Overseas': True,
                'Raw_Line': line
            })
            
    return extracted_races



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
        gear_map = {}
        trainer_map = {}
        if os.path.exists(rc_path):
            text = Path(rc_path).read_text(encoding='utf-8')
            for match in re.finditer(r'馬名:\s*(.*?)\n.*?烙號:\s*([A-Za-z0-9_]+)', text, re.DOTALL):
                mapping[match.group(1).strip()] = match.group(2).strip()
            # Extract gear per horse from racecard (配備: B/TT)
            horse_blocks = re.split(r'\n馬號:', text)
            for blk in horse_blocks:
                nm = re.search(r'馬名:\s*(.+?)$', blk, re.MULTILINE)
                gm = re.search(r'配備:\s*(.*)$', blk, re.MULTILINE)
                tm = re.search(r'練馬師:\s*(.*)$', blk, re.MULTILINE)
                if nm and gm:
                    gear_val = gm.group(1).strip()
                    # Guard against empty gear or accidental field bleed
                    if gear_val and not gear_val.startswith('父系') and not gear_val.startswith('母系'):
                        gear_map[nm.group(1).strip()] = gear_val
                if nm and tm:
                    trainer_val = tm.group(1).strip()
                    if trainer_val:
                        trainer_map[nm.group(1).strip()] = trainer_val
        return mapping, gear_map, trainer_map
    
    brand_mapping, gear_mapping, trainer_mapping = load_brand_mapping(filepath)
    pdf_path = get_pdf_path(filepath)

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
        
        # Extract barrier, jockey, trainer, weight, body weight, gear
        barrier_m = re.search(r'檔位:\s*(\d+)', block)
        jockey_m = re.search(r'騎師:\s*(.+?)$', block, re.MULTILINE)
        trainer_m = re.search(r'練馬師:\s*(.+?)$', block, re.MULTILINE)
        weight_m = re.search(r'負磅:\s*(\d+)', block)
        bw_m = re.search(r'排位體重:\s*(\d+)', block)
        gear_m = re.search(r'配備:\s*(.+?)$', block, re.MULTILINE)
        
        barrier = int(barrier_m.group(1)) if barrier_m else 0
        jockey = jockey_m.group(1).strip() if jockey_m else ''
        trainer = trainer_m.group(1).strip() if trainer_m else ''
        if not trainer:
            trainer = trainer_mapping.get(horse_name, '')
        weight = int(weight_m.group(1)) if weight_m else 0
        body_weight = int(bw_m.group(1)) if bw_m else 0
        today_gear = gear_m.group(1).strip() if gear_m else ''
        # Fallback: get gear from racecard (排位表) if not found in formguide
        if not today_gear:
            today_gear = gear_mapping.get(horse_name, '')
        
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
        
        # Extract PDF Overseas Races
        pdf_overseas_races = []
        if pdf_path:
            pdf_overseas_races = parse_pdf_overseas_races(pdf_path, brand_no, horse_name)
        
        horses.append({
            'num': horse_num,
            'name': horse_name,
            'brand_no': brand_no,
            'barrier': barrier,
            'jockey': jockey,
            'trainer': trainer,
            'weight': weight,
            'body_weight': body_weight,
            'today_gear': today_gear,
            'races': races,  # No limit — keep all for trend computation
            'pdf_overseas_races': pdf_overseas_races,
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
    """V5: Classify horse engine type from sectional profile patterns.

    Uses _classify_pace_shape() on each race's splits to determine the
    dominant speed distribution pattern. No longer uses running position.

    Types:
      均速型: Even pace across all segments
      漸進加速型: Gets faster in later segments
      快開慢收型: Fast early, fades late
      混合型: No clear dominant pattern
    """
    result = {
        'type_cn': '混合型',
        'confidence': '低',
        'evidence': [],
    }

    # Collect pace shapes from races with valid splits
    shape_counts = {'均速型': 0, '漸進加速': 0, '快開慢收': 0, '慢開快收': 0, '波動型': 0}
    valid_races = 0

    for r in races[:6]:
        splits = r.get('splits', [])
        if len(splits) < 3:
            continue
        shape = _classify_pace_shape(splits)
        valid_races += 1
        for key in shape_counts:
            if key in shape:
                shape_counts[key] += 1
                break

    if valid_races < 2:
        result['evidence'].append(f'段速數據不足 ({valid_races} 場有 splits)')
        return result

    # Find dominant shape
    # Merge 慢開快收 into 漸進加速 (both = late acceleration)
    accel_count = shape_counts['漸進加速'] + shape_counts['慢開快收']
    even_count = shape_counts['均速型']
    fade_count = shape_counts['快開慢收']

    dominant = max(
        [('均速型', even_count), ('漸進加速型', accel_count), ('快開慢收型', fade_count)],
        key=lambda x: x[1]
    )

    if dominant[1] >= valid_races * 0.5 and dominant[1] >= 2:
        result['type_cn'] = dominant[0]
        result['confidence'] = '高' if dominant[1] >= valid_races * 0.7 else '中'
        result['evidence'].append(f'近{valid_races}場全段速剖面 {dominant[1]}/{valid_races} 場{dominant[0]}')
    else:
        result['type_cn'] = '混合型'
        result['confidence'] = '低'
        result['evidence'].append(
            f'均速{even_count}/加速{accel_count}/快開慢收{fade_count} (共{valid_races}場)'
        )

    if valid_races < 4:
        result['confidence'] = '低'
        result['evidence'].append(f'樣本量少 ({valid_races} 場)')

    return result


STYLE_WEIGHTS_RECENT = [3.0, 2.0, 1.5, 1.0, 0.75, 0.5]


def _confidence_rank(label: str) -> int:
    return {'高': 2, '中': 1, '低': 0, 'High': 2, 'Medium': 1, 'Low': 0}.get(label, 0)


def _aggregate_confidence(labels: list[str]) -> str:
    if not labels:
        return 'Low'
    avg = sum(_confidence_rank(x) for x in labels) / len(labels)
    if avg >= 1.5:
        return 'High'
    if avg >= 0.75:
        return 'Medium'
    return 'Low'


def _pace_confidence(style_profiles: list[dict], n_leaders: int, n_pressers: int, field_size: int) -> str:
    if not style_profiles or field_size == 0:
        return 'Low'
    low_count = sum(1 for p in style_profiles if p.get('confidence') == '低')
    high_or_mid = sum(1 for p in style_profiles if p.get('confidence') in ('高', '中'))
    if low_count / max(field_size, 1) >= 0.4:
        return 'Low'
    if high_or_mid / max(field_size, 1) < 0.65:
        return 'Low'
    if n_leaders == 0 and n_pressers <= 1:
        return 'Mixed'
    return 'Clear'


def _hkjc_style_signal(race: dict) -> Tuple[Optional[str], str]:
    """Return a single-race tactical style signal from comment/positions.

    Uses in-race position evidence only. Finishing position is deliberately ignored
    because it measures result, not early/mid-race running style.
    """
    comment = race.get('comment', '') or ''
    positions = race.get('positions', []) or []
    field_size = race.get('field_size', 12) or 12

    is_behind_leader = any(neg in comment for neg in [
        '落後領放', '追趕領放', '跟隨領放', '與領放馬',
        '離領放馬', '在領放馬之後',
    ])

    if not is_behind_leader and any(kw in comment for kw in [
        '領放,', '領放;', '領放。', '領前', '帶頭', '帶出', '輕鬆放頭', '搶口'
    ]):
        return 'front', '評語顯示主動領放'

    if any(kw in comment for kw in [
        '居前列', '前列', '跟隨領先', '追趕領放馬', '居中間稍前', '第二位', '第三位'
    ]) or is_behind_leader:
        return 'presser', '評語顯示跟前/貼放'

    if any(kw in comment for kw in ['居包尾', '留居包尾', '後列', '尾列', '墮後']):
        return 'closer', '評語顯示留後'
    if '最後' in comment and '最後四百' not in comment and '最後直路' not in comment:
        return 'closer', '評語顯示尾段位置'

    if '居中間' in comment:
        return 'mid_pack', '評語顯示守中'

    if positions:
        first_pos = positions[0] if isinstance(positions[0], int) else 0
        if first_pos > 0:
            mid_cut = max(int(field_size * 0.55), 4)
            if first_pos == 1:
                return 'front', f'沿途位首段第{first_pos}'
            if first_pos <= 4:
                return 'presser', f'沿途位首段第{first_pos}'
            if first_pos <= mid_cut:
                return 'mid_pack', f'沿途位首段第{first_pos}'
            return 'closer', f'沿途位首段第{first_pos}'

    return None, '無走位證據'


def classify_running_style(races: list) -> dict:
    """V6: Classify running style from weighted recent in-race position evidence.

    Recent races carry more weight. Finishing position is never used as a proxy
    for running style. Output keeps the legacy 4-way style plus a 3-way tactical
    label (前置 / 守中 / 後上) for pace-map use.
    """
    result = {
        'style_cn': '靈活',
        'style_3way': '守中',
        'confidence': '低',
        'evidence': [],
    }

    style_counts = {'front': 0.0, 'presser': 0.0, 'mid_pack': 0.0, 'closer': 0.0}
    evidence_counts = {'front': 0, 'presser': 0, 'mid_pack': 0, 'closer': 0}
    evidence_notes = []
    total_weight = 0.0
    total_valid = 0

    for i, r in enumerate(races[:6]):
        style, note = _hkjc_style_signal(r)
        if not style:
            continue
        weight = STYLE_WEIGHTS_RECENT[i] if i < len(STYLE_WEIGHTS_RECENT) else 0.5
        style_counts[style] += weight
        evidence_counts[style] += 1
        total_weight += weight
        total_valid += 1
        if len(evidence_notes) < 3:
            evidence_notes.append(f"近{i+1}仗{note}")

    if total_valid < 2:
        result['evidence'].append(f'數據不足 ({total_valid} 場)')
        return result

    # Find dominant style
    dominant = max(style_counts.items(), key=lambda x: x[1])
    dominant_pct = dominant[1] / total_weight if total_weight > 0 else 0
    style_map = {'front': '前領', 'presser': '跟前', 'mid_pack': '中段', 'closer': '後上'}
    three_way_map = {'front': '前置', 'presser': '前置', 'mid_pack': '守中', 'closer': '後上'}

    if dominant_pct >= 0.45 and evidence_counts[dominant[0]] >= 2:
        result['style_cn'] = style_map[dominant[0]]
        result['style_3way'] = three_way_map[dominant[0]]
        result['confidence'] = '高' if dominant_pct >= 0.65 and evidence_counts[dominant[0]] >= 3 else '中'
        result['evidence'].append(
            f"近{total_valid}場加權走位 {style_map[dominant[0]]} 佔{dominant_pct:.0%} "
            f"({evidence_counts[dominant[0]]}/{total_valid}場)"
        )
    else:
        result['style_cn'] = '靈活'
        result['style_3way'] = '守中'
        result['confidence'] = '低'
        counts_str = '/'.join(
            f"{style_map[k]}{evidence_counts[k]}" for k in evidence_counts if evidence_counts[k] > 0
        )
        result['evidence'].append(f'{counts_str} (共{total_valid}場，無單一路向過半)')

    if evidence_notes:
        result['evidence'].append('；'.join(evidence_notes))

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


def _recent_running_style(races: list) -> str:
    """V3: Context-aware running style detection from HKJC comments.

    Key fix: '落後領放馬' should NOT match as 'front' — the horse was
    behind the leader, not leading. We check per-comment with negative filters.
    """
    front_score = 0
    presser_score = 0
    closer_score = 0
    mid_score = 0

    for r in races[:3]:
        comment = r.get('comment', '')
        if not comment:
            continue

        # --- Negative filters first: these phrases contain '領放' but mean opposite ---
        is_behind_leader = any(neg in comment for neg in [
            '落後領放', '追趕領放', '跟隨領放', '與領放馬',
            '離領放馬', '在領放馬之後',
        ])

        # --- Front: actual leading patterns ---
        if not is_behind_leader:
            # Only match '領放' when it's the horse's own action (usually at start of phrase)
            if any(kw in comment for kw in ['領放,', '領放;', '領放。']):
                front_score += 2  # Strong signal: 領放 + punctuation = subject is leading
            elif '領前' in comment and '取得領先' not in comment:
                front_score += 2
            elif any(kw in comment for kw in ['帶頭', '帶出', '輕鬆放頭', '搶口']):
                front_score += 2

        # '居前列' = front GROUP but not necessarily leading
        if '居前列' in comment or '前列' in comment:
            presser_score += 1  # V3: presser, not leader

        # --- Presser: tracking leader ---
        if any(kw in comment for kw in ['跟隨領先', '追趕領放馬', '居中間稍前', '第二位', '第三位']):
            presser_score += 1
        if is_behind_leader and '落後領放馬' in comment:
            # "落後領放馬X個馬位" = mid-to-presser depending on distance
            presser_score += 1

        # --- Closer ---
        if any(kw in comment for kw in ['居包尾', '留居包尾', '後列', '尾列', '墮後']):
            closer_score += 2
        if '最後' in comment and '最後四百' not in comment and '最後直路' not in comment:
            closer_score += 1

        # --- Mid ---
        if '居中間' in comment and '稍前' not in comment:
            mid_score += 1

        # '取得領先' = passing leader late, actually a closer/finisher
        if '取得領先' in comment and front_score == 0:
            closer_score += 1  # Late surge, not a natural leader

    # Resolve
    scores = {'front': front_score, 'presser': presser_score, 'closer': closer_score, 'mid_pack': mid_score}
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return 'mid_pack'
    return best


def _classify_pace_v2(n_leaders: int, n_on_pace: int, field_size: int,
                       distance: int = 1200, going: str = '',
                       n_pressers: int = 0) -> str:
    """V3: Multi-factor pace classification for HKJC.

    Returns Chinese labels: 極慢 / 慢 / 正常 / 快 / 極快
    """
    if field_size == 0:
        return '正常'

    # Base score from leader/presser pressure
    # V3: Pressers only contribute when leaders are present
    presser_weight = 1.0 if n_leaders >= 1 else 0.3
    base_score = n_leaders * 2.5 + n_pressers * presser_weight + n_on_pace * 0.2

    # Distance modifier
    dist_mod = {1000: 1.4, 1200: 1.1, 1400: 0.95, 1600: 0.9,
                1650: 0.88, 1800: 0.85, 2000: 0.8, 2200: 0.75, 2400: 0.7}
    d = min(dist_mod.keys(), key=lambda k: abs(k - distance))
    base_score *= dist_mod[d]

    # Going modifier
    going_lower = str(going).lower()
    if any(w in going_lower for w in ['深泵', 'yielding', '爛', 'heavy']):
        base_score *= 0.8
    elif any(w in going_lower for w in ['深好至深泵', '好至淵快', 'soft']):
        base_score *= 0.9
    elif any(w in going_lower for w in ['快', 'firm']):
        base_score *= 1.1

    # Map to 5-tier Chinese labels
    if base_score >= 6.0:
        return '極快'
    elif base_score >= 4.0:
        return '快'
    elif base_score >= 2.5:
        return '正常'
    elif base_score >= 1.5:
        return '慢'
    else:
        return '極慢'


def _classify_pace_volatility(n_leaders: int, n_closers: int, field_size: int) -> str:
    """Pace volatility: how predictable the pace scenario is.

    Returns: Stable / Volatile / Chaotic
    Used internally by MC simulator for sigma adjustment — NOT shown to LLM analysts.
    """
    if field_size == 0:
        return 'Stable'

    closer_ratio = n_closers / field_size

    if n_leaders >= 4 and n_closers >= 3:
        return 'Chaotic'
    elif n_leaders >= 3 and closer_ratio >= 0.3:
        return 'Volatile'
    else:
        return 'Stable'


def build_race_speed_map_block(data: dict, today_venue: str = '', today_dist: int = 0,
                               race_class: str = '', going: str = '') -> tuple[str, dict]:
    """V4: Build the first-class HKJC race speed map at Facts generation time.
    Includes pressers, weighted run-style confidence and pace confidence.
    """
    leaders, pressers, on_pace, mid_pack, closers = [], [], [], [], []
    style_profiles = []

    for horse in data.get('horses', []):
        races = horse.get('races', [])
        rs = classify_running_style(races)
        barrier = horse.get('barrier', 0)
        num = horse.get('num')
        if num:
            style_profiles.append({'num': num, **rs})

        # Use weighted in-race running style only (no finish-position shortcut).
        style = rs['style_cn']
        if style == '前領':
            leaders.append(num)
        elif style == '後上':
            closers.append(num)
        elif style == '跟前':
            pressers.append(num)
        elif style == '中段':
            mid_pack.append(num)
        else:  # 靈活
            if barrier and barrier <= 4:
                on_pace.append(num)
            else:
                mid_pack.append(num)

    field_size = len(data.get('horses', []))
    predicted_pace = _classify_pace_v2(len(leaders), len(on_pace), field_size,
                                       today_dist or 1200, going,
                                       n_pressers=len(pressers))
    pace_volatility = _classify_pace_volatility(len(leaders), len(closers), field_size)
    style_confidence = _aggregate_confidence([p.get('confidence', '低') for p in style_profiles])
    pace_confidence = _pace_confidence(style_profiles, len(leaders), len(pressers), field_size)

    track_bias = (
        f"FACTS_SPEED_MODEL: {today_venue or '未知場地'} {today_dist or '?'}m {race_class or ''}; "
        f"以前領數、檔位及近6仗加權跑法自動建模。"
    )
    speed_map = {
        'predicted_pace': predicted_pace,
        'pace_confidence': pace_confidence,
        'style_confidence': style_confidence,
        'pace_volatility': pace_volatility,
        'leaders': [n for n in leaders if n],
        'pressers': [n for n in pressers if n],  # V3: new
        'on_pace': [n for n in on_pace if n],
        'mid_pack': [n for n in mid_pack if n],
        'closers': [n for n in closers if n],
        'going': going,  # V3
        'track_bias': track_bias,
        'tactical_nodes': (
            f"FACTS_SPEED_MODEL: leaders={len(leaders)}, pressers={len(pressers)}, "
            f"on_pace={len(on_pace)}, mid={len(mid_pack)}, closers={len(closers)}；"
            f"步速預測 {predicted_pace}；pace_confidence={pace_confidence}。"
        ),
        'collapse_point': (
            'FACTS_SPEED_MODEL: 前速壓力高時後上/慳位馬受惠；若步速被控慢，前置馬形勢提升。'
        ),
        'style_evidence': [
            f"#{p['num']} {p.get('style_3way', '?')}/{p.get('style_cn', '?')}({p.get('confidence', '低')})"
            for p in style_profiles
        ],
        'source': 'FACTS_SPEED_MODEL_V4'
    }

    def _fmt(nums):
        return '[' + ', '.join(str(n) for n in nums if n) + ']'

    lines = [
        '### 🗺️ 自動步速圖 (Python Facts Model V4)',
        f"- **predicted_pace:** {speed_map['predicted_pace']}",
        f"- **pace_confidence:** {speed_map['pace_confidence']}",
        f"- **style_confidence:** {speed_map['style_confidence']}",
        f"- **leaders:** {_fmt(speed_map['leaders'])}",
        f"- **pressers:** {_fmt(speed_map['pressers'])}",
        f"- **on_pace:** {_fmt(speed_map['on_pace'])}",
        f"- **mid_pack:** {_fmt(speed_map['mid_pack'])}",
        f"- **closers:** {_fmt(speed_map['closers'])}",
        f"- **style_evidence:** {'; '.join(speed_map['style_evidence'])}",
        f"- **going:** {going}",
        f"- **track_bias:** {speed_map['track_bias']}",
        f"- **tactical_nodes:** {speed_map['tactical_nodes']}",
        f"- **collapse_point:** {speed_map['collapse_point']}",
        f"- **source:** {speed_map['source']}",
    ]
    return '\n'.join(lines), speed_map


def generate_horse_block(horse: dict, today_venue: str = '',
                          today_dist: int = 0, race_class: str = 'C4',
                          profile_data: dict = None,
                          form_lines_data: dict = None,
                          race_num: int = 0) -> str:
    """Generate full fact anchor + forensic block for one horse.
    
    Args:
        horse: Parsed formguide horse data (splits, energy, comments)
        profile_data: Optional scraped horse profile data (margin, trainer, etc.)
        form_lines_data: Optional form lines computation result
    """
    lines = []
    races = horse['races']
    p_entries = profile_data.get('entries', []) if profile_data else []
    
    # Prefer SSR trainer, but keep the formguide trainer as a fallback for
    # debutants or runners without profile enrichment.
    trainer = profile_data.get('trainer', '') if profile_data else ''
    if not trainer:
        trainer = horse.get('trainer', '')
    
    # Header
    header_parts = [f"### 馬號 {horse['num']} — {horse['name']}"]
    header_parts.append(f"騎師: {horse['jockey']}")
    if trainer:
        header_parts.append(f"練馬師: {trainer}")
    header_parts.append(f"負磅: {horse['weight']}")
    header_parts.append(f"檔位: {horse['barrier']}")
    lines.append(' | '.join(header_parts))
    
    # Per-horse draw verdict (if draw stats available)
    if race_num > 0:
        draw_detail = get_draw_detail(
            race_num,
            horse['barrier'],
            expected_venue=today_venue,
            expected_distance=today_dist,
        )
        if draw_detail:
            lines.append(f"📊 **檔位判定:** 檔{horse['barrier']} → {draw_detail.get('verdict', '?')} "
                         f"(勝率: {draw_detail.get('win_pct', '?')}% | "
                         f"入Q率: {draw_detail.get('quinella_pct', '?')}% | "
                         f"上名率: {draw_detail.get('place_pct', '?')}%)")
    
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
    # Career tag classification (V2.2)
    # Only horses with zero formal race records use debut templates.
    # Any horse that has run uses the standard template.
    total_races = len(races)
    # Check for imported horse (has profile entries but no/few formguide races)
    has_overseas = False
    if profile_data and profile_data.get('origin', '') not in ('', 'HK', '本地'):
        has_overseas = True
    if total_races == 0 and not has_overseas:
        _hk_ctag = 'DEBUT'
    elif total_races == 0 and has_overseas:
        _hk_ctag = 'IMPORTED_DEBUT'
    else:
        _hk_ctag = 'ESTABLISHED'
    lines.append(f"- **生涯標記:** `{_hk_ctag}` (香港出賽 {total_races} 場)")
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
    
    # === 海外賽績 (來自 PDF) ===
    if horse.get('pdf_overseas_races'):
        lines.append(f"🌍 **海外賽績 (來自 PDF):**")
        lines.append(f"| # | 日期 | 場地/路程 | 班次 | 名次/馬匹數 | 騎師 | 負磅 | 締速 | 勝負距離 |")
        lines.append(f"|---|------|-----------|------|-------------|------|------|------|----------|")
        for i, ovr in enumerate(horse['pdf_overseas_races']):
            # parse_pdf_overseas_races 出嘅 key 係 Date/Distance/Placing/Field_Size/
            # Finish_Time_Raw（大寫）；舊寫法讀 date/track_dist/... 全部 miss 晒，
            # 成個表變 '-'，下游 real_overseas_rows 就會當無海外賽績。
            ovr_date = ovr.get('Date', ovr.get('date', '-')) or '-'
            ovr_track = ovr.get('Distance', ovr.get('track_dist', '-')) or '-'
            ovr_class = ovr.get('class_level', '-') or '-'
            placing = ovr.get('Placing')
            field_size = ovr.get('Field_Size')
            if placing:
                ovr_rank = f"{placing}/{field_size}" if field_size else str(placing)
            else:
                ovr_rank = ovr.get('rank', '-') or '-'
            ovr_jockey = ovr.get('jockey', '-') or '-'
            ovr_weight = ovr.get('weight', '-') or '-'
            ovr_time = ovr.get('Finish_Time_Raw', ovr.get('time', '-')) or '-'
            ovr_margin = ovr.get('margin', '-') or '-'
            lines.append(f"| {i+1} | {ovr_date} | {ovr_track} | {ovr_class} | {ovr_rank} | {ovr_jockey} | {ovr_weight} | {ovr_time} | {ovr_margin} |")
        lines.append(f"")
    
    # === 段速/能量趨勢 ===
    trends = compute_trends(races)
    lines.append(f"📊 **段速趨勢:**")
    
    if trends['l400_values']:
        # Internal race arrays stay newest-first because the scoring logic relies on
        # that order.  Human-facing timelines are reversed so an arrow always reads
        # naturally from older evidence towards the latest run.
        l400_str = '→'.join(f"{v:.2f}" for v in reversed(trends['l400_values']))
        lines.append(f"  L400: （最舊 → 最新）{l400_str} → 趨勢: {trends['l400_trend']}")
    
    if trends['energy_values']:
        e_str = '→'.join(str(v) for v in reversed(trends['energy_values']))
        lines.append(f"  能量: （最舊 → 最新）{e_str} → 趨勢: {trends['energy_trend']}")
    
    # === 完成時間偏差趨勢 [SIP-P2c] ===
    ft_deviations = []
    adj_deviations = []  # V5.1: Pace-adjusted deviations
    pace_labels = []     # V5.1: Per-race pace label
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
                raw_dev = round(ftime_sec - race_std, 2)
                ft_deviations.append(raw_dev)
                # V5.1: Pace-adjusted deviation using winner time estimation
                margin_num = p.get('margin_numeric', 0) or 0
                placing = p.get('placing', 0) or 0
                margin_secs = round(margin_num * 0.17, 2) if placing != 1 else 0
                winner_time = ftime_sec - margin_secs
                pace_factor = round(winner_time - race_std, 2)
                adj_dev = round(raw_dev - pace_factor, 2)
                adj_deviations.append(adj_dev)
                # Pace label for context
                if pace_factor > 1.5:
                    pace_labels.append('極慢')
                elif pace_factor > 0.5:
                    pace_labels.append('偏慢')
                elif pace_factor < -0.5:
                    pace_labels.append('偏快')
                else:
                    pace_labels.append('正常')
    
    if len(ft_deviations) >= 2:
        lines.append(f"")
        lines.append(f"📊 **完成時間偏差趨勢 [SIP-P2c] (vs HKJC 標準):**")
        dev_str = '→'.join(f"{v:+.2f}s" for v in reversed(ft_deviations))
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
        lines.append(f"  偏差: （最舊 → 最新）{dev_str} → 趨勢: {ft_trend}")
        lines.append(f"  水平: {ft_level} (近 {min(len(ft_deviations), 3)} 仗平均偏差: {avg_dev:+.2f}s)")
        lines.append(f"  含金量: {ft_reading}")
        # V5.1: Pace-adjusted deviation (subtracts race pace factor)
        if len(adj_deviations) >= 2:
            adj_str_parts = []
            for j in range(len(adj_deviations) - 1, -1, -1):
                ad = adj_deviations[j]
                pl = pace_labels[j] if j < len(pace_labels) else ''
                if pl in ('極慢', '偏慢', '偏快'):
                    adj_str_parts.append(f"{ad:+.2f}s[{pl}]")
                else:
                    adj_str_parts.append(f"{ad:+.2f}s")
            adj_str = '→'.join(adj_str_parts)
            avg_adj = sum(adj_deviations[:3]) / min(len(adj_deviations), 3)
            if avg_adj < 0.3:
                adj_level = '✅ 步速修正後仍具競爭力'
            elif avg_adj < 0.8:
                adj_level = '➖ 步速修正後接近平均'
            elif avg_adj < 1.3:
                adj_level = '⚠️ 步速修正後仍偏慢'
            else:
                adj_level = '❌ 步速修正後明顯落後'
            lines.append(f"  🔧 步速修正偏差: （最舊 → 最新）{adj_str}")
            lines.append(f"  🔧 修正水平: {adj_level} (近 {min(len(adj_deviations), 3)} 仗修正平均: {avg_adj:+.2f}s)")
            lines.append(f"  💡 修正方法: 扣除全場頭馬偏差(步速因子) — [極慢/偏慢]場次嘅原始偏差會被折扣")
    
    # === V5.2: 人馬組合統計 (Jockey-Horse Combo Stats) — 全季往績 ===
    # FIX: previously the combo win/place rate was computed from
    # `zip(races, p_entries)`, which truncates to the shorter list. Since the
    # formguide `races` block only carries the most recent ~6 runs, the rate was
    # silently capped at ~6 starts — unreliable and not what the HKJC horse page
    # shows. We now compute over the FULL horse-profile history (all seasons the
    # HKJC horse page lists), falling back to the formguide only when no profile.
    current_jockey = horse.get('jockey', '')
    combo_stats = {}  # {jockey_name: {starts, wins, places, shows, total_placing}}
    jockey_history = []  # Recent races (display only): [{date, jockey, placing, changed}]

    if p_entries:
        full_record = [
            {'jockey': e.get('jockey', ''), 'finish': e.get('placing', 0), 'date': e.get('date', '')}
            for e in p_entries
        ]
    else:
        full_record = [
            {'jockey': r.get('jockey', ''), 'finish': r.get('finish', 0), 'date': r.get('date', '')}
            for r in races
        ]

    # DISPLAY window = the horse's two most recent HK seasons (Sep→Aug).
    # Point-in-time backtest rationale: a single-season window has a severe
    # season-start cold-start (~5% of early-season runners get any combo signal
    # vs ~33% for a 2-season window); two seasons gives full coverage with no
    # cold-start, and is effectively identical to full-career for current HK
    # horses while staying future-proof as careers lengthen. SCORING is
    # unaffected — it reads the 近6場 recency table, always inside this window.
    def _hk_season(dt):
        return dt.year if dt.month >= 9 else dt.year - 1
    def _combo_date(s):
        # Profile dates are DD/MM/YY; formguide DD/MM/YYYY. Try both.
        s = (s or '').strip()
        for fmt in ('%d/%m/%y', '%d/%m/%Y'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None
    _parsed = [(rec, _combo_date(rec['date'])) for rec in full_record]
    _seasons = sorted({_hk_season(dt) for _, dt in _parsed if dt})
    if len(_seasons) > 2:
        _keep = set(_seasons[-2:])
        full_record = [rec for rec, dt in _parsed if dt is None or _hk_season(dt) in _keep]
    season_span = len(_seasons[-2:]) if _seasons else 0

    prev_jockey_name = None
    for i, rec in enumerate(full_record):
        j_name = rec['jockey']
        finish = rec['finish']
        if isinstance(finish, str):
            try:
                finish = int(finish)
            except (ValueError, TypeError):
                finish = 0
        date = rec['date']

        # Only count completed runs (finish>0) so scratched/DNF rows do not
        # dilute the win/place denominator.
        if j_name and finish > 0:
            if j_name not in combo_stats:
                combo_stats[j_name] = {'starts': 0, 'wins': 0, 'places': 0, 'shows': 0, 'total_placing': 0}
            combo_stats[j_name]['starts'] += 1
            combo_stats[j_name]['total_placing'] += finish
            if finish == 1:
                combo_stats[j_name]['wins'] += 1
            if finish <= 2:
                combo_stats[j_name]['places'] += 1
            if finish <= 3:
                combo_stats[j_name]['shows'] += 1

        if i < 6:
            changed = '← 換騎' if prev_jockey_name and j_name != prev_jockey_name else ''
            jockey_history.append({'date': date, 'jockey': j_name, 'placing': finish, 'changed': changed})
        prev_jockey_name = j_name

    if combo_stats:
        total_starts = sum(s['starts'] for s in combo_stats.values())
        span = ''
        dated = [r['date'] for r in full_record if r['date']]
        if dated:
            scope = f"近{season_span}季" if season_span else "近期"
            span = f" ({scope} {total_starts} 場: {dated[-1]} → {dated[0]})"
        lines.append(f"")
        lines.append(f"🏇 **人馬組合統計 [V5.3 近2季]:**")
        lines.append(f"  今場騎師: {current_jockey}")
        lines.append(f"  📊 騎師×此馬歷史{span}:")
        lines.append(f"  | 騎師 | 場次 | 勝 | 入Q | 上名 | 平均名次 | 勝率 | 位率 |")
        lines.append(f"  |------|------|---|-----|------|----------|------|------|")
        # Sort: current jockey first, then by starts descending
        sorted_jockeys = sorted(combo_stats.items(), 
                                key=lambda x: (x[0] != current_jockey, -x[1]['starts']))
        for j_name, s in sorted_jockeys:
            avg_pos = round(s['total_placing'] / max(s['starts'], 1), 1)
            win_pct = round(s['wins'] / max(s['starts'], 1) * 100, 1)
            place_pct = round(s['shows'] / max(s['starts'], 1) * 100, 1)
            marker = ' ← 今場' if j_name == current_jockey else ''
            lines.append(f"  | {j_name}{marker} | {s['starts']} | {s['wins']} | {s['places']} | {s['shows']} | {avg_pos} | {win_pct}% | {place_pct}% |")
        
        if jockey_history:
            lines.append(f"  近6場騎師歷史:")
            lines.append(f"  | # | 日期 | 騎師 | 名次 | 備注 |")
            lines.append(f"  |---|------|------|------|------|")
            for i, jh in enumerate(jockey_history):
                lines.append(f"  | {i+1} | {jh['date']} | {jh['jockey']} | {jh['placing']} | {jh['changed']} |")
    
    # === 全段速剖面 (Full Sectional Profile) ===
    sect_profile_rows = []
    for i in range(min(len(races), 6)):  # V5: Last 6 races (aligned with race record)
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
    

    
    # === V5: 引擎 (速度分佈) + 跑法 (位置偏好) ===
    engine = classify_engine_type(races)
    run_style = classify_running_style(races)
    dist_apt = compute_distance_aptitude(races, today_dist)
    
    today_rec = dist_apt['today_record']
    today_total = sum(today_rec)
    
    low_sample_tag = ' [⚠️ 樣本不足 — LLM 可覆判]' if engine['confidence'] == '低' and '樣本' in ' '.join(engine['evidence']) else ''
    lines.append(f"🔧 **引擎 (速度分佈):**")
    lines.append(f"  引擎: {engine['type_cn']} | "
                 f"信心: {engine['confidence']} | "
                 f"依據: {'; '.join(engine['evidence']) if engine['evidence'] else '數據不足'}"
                 f"{low_sample_tag}")
    lines.append(f"🏇 **跑法 (位置偏好):**")
    lines.append(f"  跑法: {run_style['style_cn']} | "
                 f"信心: {run_style['confidence']} | "
                 f"依據: {'; '.join(run_style['evidence']) if run_style['evidence'] else '數據不足'}")
                 
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
        gc = detect_gear_changes(p_entries, horse.get('today_gear') or None)
        if gc.get('today'):
            lines.append(f"🔧 **配備變動:** 上仗 {gc['last']} → 今仗 {gc['today']} | {gc['signal']}")
        else:
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
    
    # Class — graded races (一/二/三級賽 = Group 1/2/3) rank ABOVE all 班次 and must
    # NOT collapse to the default 'C4'. Check graded/Listed before numbered classes.
    gm = re.search(r'([一二三])級賽', overview)
    if gm:
        ctx['class'] = gm.group(1) + '級賽'
    elif '上市賽' in overview or '表列賽' in overview or re.search(r'\b(?:Listed|LR)\b', overview, re.I):
        ctx['class'] = '上市賽'
    elif re.search(r'(?:Group|Grade|G)\s*([123])', overview, re.I):
        g = re.search(r'(?:Group|Grade|G)\s*([123])', overview, re.I).group(1)
        ctx['class'] = '一二三'[int(g) - 1] + '級賽'
    else:
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
    race_num = 0  # For draw stats matching
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
            enable_form_lines = True
            i += 2
        elif args[i] == '--output' and i + 1 < len(args):
            output_path = args[i + 1]
            i += 2
        elif args[i] == '--race-num' and i + 1 < len(args):
            race_num = int(args[i + 1])
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
    
    # Inject draw verdict block if race_num provided
    if race_num > 0:
        draw_block = get_draw_summary_block(
            race_num,
            expected_venue=today_venue,
            expected_distance=today_dist,
        )
        if draw_block:
            output_lines.append(draw_block)
            output_lines.append(f"")
            print(f"   🎯 檔位判讀: Race {race_num} 已注入", file=sys.stderr)
        elif load_draw_stats().get('races'):
            print(
                f"   ⚠️ 檔位統計與今場不匹配，已略過注入 (Race {race_num}: {today_venue} {today_dist}m)",
                file=sys.stderr,
            )

    speed_map_block, _speed_map = build_race_speed_map_block(data, today_venue, today_dist, race_class)
    output_lines.append(speed_map_block)
    output_lines.append(f"")
    print(f"   🗺️ 自動步速圖: { _speed_map['predicted_pace'] } ({_speed_map['source']})", file=sys.stderr)
    
    output_lines.append(f"{'=' * 70}")
    output_lines.append(f"")
    
    for horse in data['horses']:
        profile = profiles.get(horse['num'])
        fl_data = form_lines_map.get(horse['num'])
        block = generate_horse_block(horse, today_venue, today_dist, race_class, profile, fl_data, race_num=race_num)
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
