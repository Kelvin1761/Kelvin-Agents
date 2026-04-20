#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
hkjc_profile_scraper.py — HKJC Form Lines (賽績線) Engine
==========================================================
Scrapes HKJC race results pages (SSR HTML) to track opponent performance.

Core Functions:
  1. scrape_race_result(url) → All horses + placings for a specific race
  2. compute_form_lines(entries) → Opponent tracking + strength rating

All SSR-based: requests + BeautifulSoup. No Playwright needed.

Usage:
    python3 hkjc_profile_scraper.py --horse-id HK_2024_K416
    python3 hkjc_profile_scraper.py --horse-id HK_2024_K416 --json
"""

import re
import json
import time
import argparse
from datetime import datetime
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
RESULT_CACHE_FILE = os.path.join(CACHE_DIR, 'result_cache.json')

def _load_result_cache():
    if os.path.exists(RESULT_CACHE_FILE):
        try:
            with open(RESULT_CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def _save_result_cache(cache):
    try:
        with open(RESULT_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False)
    except Exception:
        pass

_result_cache = _load_result_cache()

# Import the profile scraper for horse data
try:
    from scrape_hkjc_horse_profile import scrape_horse_profile, parse_margin
except ImportError:
    print("ERROR: scrape_hkjc_horse_profile.py not found", file=sys.stderr)
    sys.exit(1)


# ── HKJC Margin (Chinese) → Numeric ─────────────────────────────────────
MARGIN_CN_MAP = {
    '-': 0.0, '---': 0.0,
    '短馬頭位': 0.1, '短頭': 0.1,
    '頸位': 0.25, '頸': 0.25,
    '半個馬位': 0.5, '半': 0.5,
    '三又四分一馬位': 3.25,
}


def parse_margin_cn(margin_str: str) -> Optional[float]:
    """Parse Chinese race result margin to numeric lengths.
    
    Examples: '短馬頭位' → 0.1, '頸位' → 0.25, '1又1/4馬位' → 1.25
    """
    if not margin_str or margin_str.strip() in ('-', '---', ''):
        return 0.0  # Winner
    
    s = margin_str.strip()
    
    # Direct lookup
    if s in MARGIN_CN_MAP:
        return MARGIN_CN_MAP[s]
    
    # Pattern: X又Y/Z馬位 (e.g. '1又1/4馬位', '2又1/2馬位')
    m = re.match(r'(\d+)又(\d+)/(\d+)馬位', s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / int(m.group(3))
    
    # Pattern: Y/Z馬位 (e.g. '3/4馬位')
    m = re.match(r'(\d+)/(\d+)馬位', s)
    if m:
        return int(m.group(1)) / int(m.group(2))
    
    # Pattern: X馬位 (e.g. '2馬位', '10馬位')
    m = re.match(r'(\d+)馬位', s)
    if m:
        return float(m.group(1))
    
    # Pattern: X又Y馬位 (unlikely but safe)
    m = re.match(r'(\d+)又(\d+)馬位', s)
    if m:
        return float(m.group(1)) + float(m.group(2))
    
    return None


# ── Race Results Scraper ─────────────────────────────────────────────────

_result_cache = {}  # {url: [result_list]}


def scrape_race_result(result_url: str, timeout: int = 15) -> list[dict]:
    """Scrape a HKJC race results page (SSR HTML).
    
    Args:
        result_url: Full or relative URL to race results page
        
    Returns: [
        {'placing': 1, 'horse_no': 3, 'horse_name': '超拍檔', 
         'horse_id': 'HK_2024_K484', 'margin_raw': '-', 'margin_numeric': 0.0},
        {'placing': 2, 'horse_no': 7, 'horse_name': '加州勇勝',
         'horse_id': 'HK_2024_K364', 'margin_raw': '短馬頭位', 'margin_numeric': 0.1},
        ...
    ]
    """
    # Normalize URL
    if result_url.startswith('/'):
        result_url = f"https://racing.hkjc.com{result_url}"
    
    global _result_cache
    
    # Check cache
    if result_url in _result_cache:
        return _result_cache[result_url]
    
    try:
        resp = requests.get(result_url, timeout=timeout)
        if resp.status_code != 200:
            return []
    except Exception:
        return []
    
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    # Find the results table (first table_bd)
    tables = soup.find_all('table', class_='table_bd')
    if not tables:
        return []
    
    results = []
    rows = tables[0].find_all('tr')
    
    for row in rows[1:]:  # Skip header row
        cells = row.find_all('td')
        if len(cells) < 10:
            continue
        
        try:
            placing_txt = cells[0].get_text(strip=True)
            if not placing_txt.isdigit():
                continue
            
            placing = int(placing_txt)
            horse_no_txt = cells[1].get_text(strip=True)
            horse_no = int(horse_no_txt) if horse_no_txt.isdigit() else 0
            
            # Horse name + ID from link
            horse_cell = cells[2]
            horse_name_raw = horse_cell.get_text(strip=True)
            horse_link = horse_cell.find('a')
            horse_id = ''
            if horse_link:
                href = horse_link.get('href', '')
                id_m = re.search(r'horseid=([A-Z_0-9]+)', href)
                if id_m:
                    horse_id = id_m.group(1)
            
            # Clean horse name (remove brand no)
            horse_name = re.sub(r'\([A-Z]\d+\)', '', horse_name_raw).strip()
            
            # Margin
            margin_raw = cells[8].get_text(strip=True) if len(cells) > 8 else '-'
            margin_numeric = parse_margin_cn(margin_raw)
            
            results.append({
                'placing': placing,
                'horse_no': horse_no,
                'horse_name': horse_name,
                'horse_id': horse_id,
                'margin_raw': margin_raw,
                'margin_numeric': margin_numeric,
            })
        except Exception:
            continue
    
    # Cache the result
    if results:
        _result_cache[result_url] = results
        _save_result_cache(_result_cache)
        
    return results


# ── Form Lines Computation ───────────────────────────────────────────────

def compute_form_lines(entries: list[dict], max_races: int = 5,
                       rate_limit: float = 0.5) -> dict:
    """Compute form lines (賽績線) for a horse.
    
    For each of the horse's recent races:
    1. Scrape that race's result page → find winner/runner-up
    2. If target horse won → check runner-up's subsequent form
    3. If target horse lost → check winner's subsequent form
    4. Rate as ✅ 強組 or ❌ 弱組
    
    Args:
        entries: Horse profile entries (from scrape_horse_profile)
        max_races: Max number of races to check (default 5)
        rate_limit: Seconds between HTTP requests
        
    Returns: {
        'table_lines': ['| 1 | 01/03/26 | ST R2 | 8 (-2½L) | 超拍檔 (頭馬) | 出 2 次: 1 勝 | ✅ 強組 |', ...],
        'rating': '✅ 強' / '中強' / '❌ 弱' / '無資料',
        'stats': '2/3',
        'queries': [{...}]  # detailed query data
    }
    """
    queries = []
    
    for entry in entries[:max_races]:
        race_link = entry.get('race_link', '')
        if not race_link:
            continue
        
        placing = entry.get('placing', 0)
        if placing <= 0:
            continue
        
        # Extract race info from link
        date_m = re.search(r'racedate=(\d{4}/\d{2}/\d{2})', race_link)
        rno_m = re.search(r'RaceNo=(\d+)', race_link)
        rc_m = re.search(r'Racecourse=(\w+)', race_link)
        
        race_date = date_m.group(1) if date_m else ''
        race_no = int(rno_m.group(1)) if rno_m else 0
        racecourse = rc_m.group(1) if rc_m else ''
        
        # Parse date for comparison
        try:
            race_dt = datetime.strptime(race_date, '%Y/%m/%d')
        except (ValueError, AttributeError):
            continue
        
        # Short venue code
        venue_short = {'ST': '田', 'HV': '谷'}.get(racecourse, racecourse)
        
        queries.append({
            'entry_idx': entries.index(entry),
            'date_str': entry.get('date', ''),
            'race_date': race_date,
            'race_dt': race_dt,
            'race_link': race_link,
            'race_no': race_no,
            'racecourse': racecourse,
            'venue_short': venue_short,
            'my_placing': placing,
            'my_margin': entry.get('margin_numeric'),
            'my_margin_raw': entry.get('margin_raw', ''),
        })
    
    # Process each query
    table_lines = []
    # Track strong score as float (super-strong=2, strong=1, mid=0.5)
    strong_score = 0.0
    total_valid = 0
    
    for q_idx, q in enumerate(queries):
        # Rate limiting
        if q_idx > 0:
            time.sleep(rate_limit)
        
        # Scrape race results
        results = scrape_race_result(q['race_link'])
        if not results:
            table_lines.append(
                f"| {q_idx+1} | {q['date_str']} | {q['venue_short']} R{q['race_no']} | "
                f"{q['my_placing']} | 賽果查詢失敗 | - | - | - |"
            )
            continue
        
        # Find Top 3 opponents (excluding myself)
        opponents = []
        for p in [1, 2, 3]:
            if q['my_placing'] == p:
                continue
            opp = next((r for r in results if r['placing'] == p), None)
            if opp:
                lbl_map = {1: '(頭馬)', 2: '(亞軍)', 3: '(季軍)'}
                opponents.append((p, opp, lbl_map[p]))
        
        if not opponents:
            table_lines.append(
                f"| {q_idx+1} | {q['date_str']} | {q['venue_short']} R{q['race_no']} | "
                f"{q['my_placing']} | 搵唔到對手 | - | - | - |"
            )
            continue
        
        # Build my position string
        my_pos_str = str(q['my_placing'])
        if q['my_margin'] and q['my_margin'] > 0:
            my_pos_str += f" (-{q['my_margin_raw']})"
        
        for opp_idx, (p, opponent, opp_label) in enumerate(opponents):
            # Show empty boxes for the race details on subsequent opponent rows
            race_num_str = str(q_idx+1) if opp_idx == 0 else ""
            date_col = q['date_str'] if opp_idx == 0 else ""
            venue_col = f"{q['venue_short']} R{q['race_no']}" if opp_idx == 0 else ""
            my_pos_col = my_pos_str if opp_idx == 0 else ""
            
            # Check opponent's future form
            if opponent['horse_id']:
                time.sleep(rate_limit)
                opp_profile = scrape_horse_profile(opponent['horse_id'])
                if opp_profile.get('error') or not opp_profile.get('entries'):
                    table_lines.append(
                        f"| {race_num_str} | {date_col} | {venue_col} | "
                        f"{my_pos_col} | [{p}] {opponent['horse_name']} {opp_label} | - | 查冊失敗 | - |"
                    )
                    continue
                
                future_runs = 0
                future_wins = 0
                future_places = 0  # Top-3 finishes
                future_classes = set()
                has_class_upgrade = False
                
                for opp_entry in opp_profile['entries']:
                    opp_date = opp_entry.get('race_date_full', '')
                    if not opp_date: continue
                    try:
                        opp_dt = datetime.strptime(opp_date, '%Y/%m/%d')
                        if opp_dt > q['race_dt']:
                            future_runs += 1
                            cls_raw = str(opp_entry.get('class_grade', '')).upper()
                            if cls_raw:
                                cmap = {
                                    '1': '第一班', '2': '第二班', '3': '第三班', '4': '第四班', '5': '第五班',
                                    'G1': '一級賽', 'G2': '二級賽', 'G3': '三級賽', 'G': '分級賽',
                                    '4R': '四歲馬系列', 'GRIFFIN': '新馬賽'
                                }
                                cls_name = cmap.get(cls_raw, f"C{cls_raw}")
                                future_classes.add(cls_name)
                                # Detect class upgrade (higher class than current)
                                if cls_raw in ('1', '2', '3', 'G1', 'G2', 'G3', 'G'):
                                    has_class_upgrade = True
                            placing = opp_entry.get('placing')
                            if placing == 1:
                                future_wins += 1
                            if placing is not None and 1 <= placing <= 3:
                                future_places += 1
                    except:
                        pass
                
                class_str = " ".join(sorted(future_classes)) if future_classes else "-"
                if future_runs == 0:
                    perf_str = "未有出賽"
                    strength_lbl = "-"
                else:
                    perf_str = f"出 {future_runs} 次: {future_wins} 勝"
                    total_valid += 1
                    place_rate = future_places / future_runs if future_runs > 0 else 0
                    
                    # 3-tier strength classification
                    if future_wins >= 2 or (future_wins >= 1 and has_class_upgrade):
                        strength_lbl = "✅✅ 超強組"
                        strong_score += 2
                    elif future_wins >= 1:
                        strength_lbl = "✅ 強組"
                        strong_score += 1
                    elif place_rate >= 0.4:
                        strength_lbl = "⚠️ 中組"
                        strong_score += 0.5
                    else:
                        strength_lbl = "❌ 弱組"
            else:
                perf_str = "無 horseid"
                strength_lbl = "-"
                class_str = "-"
            
            table_lines.append(
                f"| {race_num_str} | {date_col} | {venue_col} | "
                f"{my_pos_col} | [{p}] {opponent['horse_name']} {opp_label} | {class_str} | {perf_str} | {strength_lbl} |"
            )
    
    # 5-level overall rating
    if total_valid == 0:
        rating = "無資料"
        stats = "N/A"
    else:
        ratio = strong_score / total_valid
        stats = f"{strong_score:.0f}/{total_valid}"
        if ratio >= 0.7:
            rating = "✅✅ 極強"
        elif ratio >= 0.5:
            rating = "✅ 強"
        elif ratio >= 0.3:
            rating = "中強"
        elif ratio >= 0.15:
            rating = "中弱"
        else:
            rating = "❌ 弱"
    
    return {
        'table_lines': table_lines,
        'rating': rating,
        'stats': stats,
        'queries': queries,
    }


def format_form_lines_report(horse_name: str, form_lines: dict) -> str:
    """Format form lines result as markdown."""
    lines = []
    lines.append(f"🔗 **賽績線 — {horse_name}:**")
    lines.append(f"  **綜合評估:** {form_lines['rating']} (強組比例: {form_lines['stats']})")
    lines.append("")
    lines.append("| # | 日期 | 賽事 | 我嘅名次 | 對手 | 後續比賽Class | 對手後續成績 | 強度評估 |")
    lines.append("|---|------|------|----------|------|---------------|--------------|----------|")
    for line in form_lines['table_lines']:
        lines.append(line)
    return '\n'.join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='HKJC Form Lines (賽績線) Engine')
    parser.add_argument('--horse-id', required=True, help='HKJC Horse ID (e.g. HK_2024_K416)')
    parser.add_argument('--max-races', type=int, default=5, help='Max races to check')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    
    args = parser.parse_args()
    
    # Step 1: Get horse profile
    print(f"Scraping profile for {args.horse_id}...", file=sys.stderr)
    profile = scrape_horse_profile(args.horse_id)
    
    if profile.get('error'):
        print(f"ERROR: {profile['error']}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(profile['entries'])} entries for {profile['name']}", file=sys.stderr)
    
    # Step 2: Compute form lines
    print(f"Computing form lines (max {args.max_races} races)...", file=sys.stderr)
    form_lines = compute_form_lines(profile['entries'], max_races=args.max_races)
    
    print(f"Result: {form_lines['rating']} ({form_lines['stats']})", file=sys.stderr)
    
    if args.json:
        output = {
            'horse_id': args.horse_id,
            'name': profile['name'],
            'form_lines': {
                'rating': form_lines['rating'],
                'stats': form_lines['stats'],
                'table_lines': form_lines['table_lines'],
            }
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(format_form_lines_report(profile['name'], form_lines))


if __name__ == '__main__':
    main()
