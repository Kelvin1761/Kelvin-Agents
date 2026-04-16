#!/usr/bin/env python3
"""
inject_fact_anchors.py — V2: 完整賽績檔案 (Full Race Dossier) Auto-Generator
============================================================================

Parses BOTH Racecard.md and Formguide.md to produce rich, pre-verified data
blocks for the LLM analyst. ALL computation is done by Python.

V2 Upgrades (2026-04-08):
  - Includes TRIALS in race dossier (up to 10 entries total)
  - Each entry tagged as 🏁 RACE or 🔰 TRIAL
  - EEM energy extraction from Video commentary
  - Position Index (PI) trend computation (proxy for sectional quality)
  - Engine Type classification (A/B/C/AB) from running patterns
  - Distance Aptitude statistics (W-P-L by distance band)
  - Restructured output: 📌 Racecard → 📋 Full Dossier → 📊 Sectional →
    ⚡ EEM → 🔧 Engine/Distance

Python computes. LLM interprets. No arithmetic by the LLM.

Usage:
    python3 inject_fact_anchors.py <Racecard.md> [<Formguide.md>]
"""
from typing import Optional
import re
import json
import sys
import shutil
from pathlib import Path
from datetime import datetime

# ── Constants ────────────────────────────────────────────────────────────

# Known trial venue keywords (case-insensitive substring match)
TRIAL_VENUE_KEYWORDS = ['southside', 'picklebet', 'balnarring']
TRIAL_DISTANCES = {600, 650, 700, 750, 800, 900, 950}
TRIAL_MARKER = '**(TRIAL)**'

# Max real races for 完整賽績檔案 (and trials interspersed)
MAX_REAL_RACES_IN_DOSSIER = 10

# Max NON-TRIAL races for engine/distance/trend computation
MAX_REAL_RACES_FOR_COMPUTE = 10

# AU Track profiles resource directory (relative to script)
_SCRIPT_DIR = Path(__file__).resolve().parent
_TRACK_RESOURCE_DIR = _SCRIPT_DIR.parent / 'skills' / 'au_racing' / 'au_horse_analyst' / 'resources'

# Venue → track filename mapping
VENUE_TRACK_MAP = {
    'randwick': '04b_track_randwick.md',
    'rosehill': '04b_track_rosehill.md',
    'flemington': '04b_track_flemington.md',
    'caulfield': '04b_track_caulfield.md',
    'moonee valley': '04b_track_moonee_valley.md',
    'eagle farm': '04b_track_eagle_farm.md',
    'doomben': '04b_track_doomben.md',
    'warwick farm': '04b_track_warwick_farm.md',
    # Provincial fallback
    'provincial': '04b_track_provincial.md',
}


def load_track_profile(venue: str, distance: int = 0) -> dict:
    """Parse a 04b_track_*.md file and extract structured track data.
    
    Args:
        venue: Venue name (e.g. 'Randwick', 'Caulfield') 
        distance: Today's race distance (to find specific barrier info)
    
    Returns: {
        'name': 'Caulfield',
        'circumference': '2080m',
        'straight': '367m',
        'direction': '逆時針',
        'key_traits': ['三角形跑道', 'On-pace bias', ...],
        'bias_good': '偏利前置/箱位',
        'distance_note': '1400m: 起步即入急彎,外檔(8+)嚴重蟀位',
        'raw_text': '...',
    }
    """
    venue_lower = venue.lower().strip()
    
    # Find matching track file
    track_file = None
    for key, fname in VENUE_TRACK_MAP.items():
        if key in venue_lower:
            track_file = _TRACK_RESOURCE_DIR / fname
            break
    
    # Fallback to provincial
    if not track_file or not track_file.exists():
        fallback = _TRACK_RESOURCE_DIR / '04b_track_provincial.md'
        if fallback.exists():
            track_file = fallback
        else:
            return {'name': venue, 'raw_text': ''}
    
    text = track_file.read_text(encoding='utf-8')
    
    result = {
        'name': venue,
        'circumference': '',
        'straight': '',
        'direction': '',
        'surface': '',
        'key_traits': [],
        'bias_good': '',
        'distance_note': '',
        'raw_text': text,
    }
    
    # Parse table structure: | 項目 | 數據 |
    for line in text.split('\n'):
        if '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) >= 3:
            key = parts[1].replace('**', '').strip()
            val = parts[2].replace('**', '').strip()
            if '周長' in key:
                result['circumference'] = val
            elif '直路' in key:
                result['straight'] = val
            elif '方向' in key:
                result['direction'] = val
            elif '場地' in key and '偏差' not in key:
                result['surface'] = val
    
    # Extract key traits (bullet points under 關鍵特性)
    in_key_section = False
    for line in text.split('\n'):
        if '關鍵特性' in line:
            in_key_section = True
            continue
        if in_key_section:
            if line.startswith('##') or line.startswith('|'):
                in_key_section = False
                continue
            if line.strip().startswith('- '):
                trait = line.strip()[2:].split(' — ')[0].strip().replace('**', '')
                result['key_traits'].append(trait)
    
    # Extract bias for Good going
    for line in text.split('\n'):
        if 'Good' in line and '|' in line and '偏' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 3:
                result['bias_good'] = parts[-2].strip()
    
    # Extract distance-specific note if distance provided
    if distance > 0:
        for line in text.split('\n'):
            if f'{distance}m' in line and '|' in line:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 5:
                    # Get the last 2 meaningful columns (barrier + traits)
                    barrier_impact = parts[-3].strip() if len(parts) > 4 else ''
                    traits = parts[-2].strip() if len(parts) > 4 else ''
                    result['distance_note'] = f"{distance}m: 檔位影響 {barrier_impact} | {traits}"
    
    return result


def format_track_profile_summary(tp: dict) -> str:
    """Format track profile as a compact summary for Facts.md header."""
    if not tp.get('circumference'):
        return ''
    
    lines = []
    lines.append(f"🏟️ **賽場檔案 — {tp['name']}** (Python 自動解析)")
    specs = []
    if tp['circumference']: specs.append(f"周長 {tp['circumference']}")
    if tp['straight']: specs.append(f"直路 {tp['straight']}")
    if tp['direction']: specs.append(tp['direction'])
    if tp['surface']: specs.append(tp['surface'])
    lines.append(f"  {' | '.join(specs)}")
    
    if tp['key_traits']:
        lines.append(f"  特性: {' / '.join(tp['key_traits'][:3])}")
    if tp['bias_good']:
        lines.append(f"  Good 偏差: {tp['bias_good']}")
    if tp['distance_note']:
        lines.append(f"  🎯 {tp['distance_note']}")
    
    return '\n'.join(lines)


# ── Racecard Parsing ─────────────────────────────────────────────────────

def parse_last10(last10_str: str) -> list[int]:
    """Decode Last 10 string. '0' = 10th, 'x' = skip (trial/scratch)."""
    positions = []
    for ch in last10_str:
        if ch == 'x':
            continue
        elif ch == '0':
            positions.append(10)
        elif ch.isdigit():
            positions.append(int(ch))
    positions.reverse()  # AU format: right-most is most recent
    return positions


def is_trial_venue(venue: str, distance_str: str = '') -> bool:
    """Heuristic: detect if a venue/distance combo is likely a trial."""
    venue_lower = venue.lower()
    for kw in TRIAL_VENUE_KEYWORDS:
        if kw in venue_lower:
            return True
    try:
        dist_m = int(re.search(r'(\d+)', distance_str).group(1))
        if dist_m in TRIAL_DISTANCES:
            return True
    except (AttributeError, ValueError):
        pass
    return False


def parse_racecard(filepath: str) -> list[dict]:
    """Parse Racecard.md and extract facts for each horse."""
    text = Path(filepath).read_text(encoding='utf-8')
    horses = []

    horse_pattern = re.compile(
        r'^(\d+)\.\s+(.+?)\s*\((\d+)\)\s*$', re.MULTILINE
    )
    matches = list(horse_pattern.finditer(text))

    for i, match in enumerate(matches):
        horse_num = int(match.group(1))
        horse_name = match.group(2).strip()
        barrier = int(match.group(3))

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        horse_block = block.split('---')[0]
        if 'Scratched' in horse_block or 'status:Scratched' in horse_block:
            continue

        career_match = re.search(r'Career:\s*(\S+)', block)
        career = career_match.group(1) if career_match else 'N/A'

        last10_match = re.search(r'Last 10:\s*(\S+)', block)
        last10_raw = last10_match.group(1) if last10_match else 'None'

        last_match = re.search(
            r'Last:\s*(\d+)/(\d+)\s+(\S+)\s+(.+?)$', block, re.MULTILINE
        )
        if last_match:
            last_finish = int(last_match.group(1))
            last_field = int(last_match.group(2))
            last_dist = last_match.group(3).strip()
            last_venue = last_match.group(4).strip()
        else:
            last_finish = None
            last_field = None
            last_dist = 'N/A'
            last_venue = 'N/A'
            
        jockey_match = re.search(r'Jockey:\s*([^|]+)', block)
        jockey = jockey_match.group(1).strip() if jockey_match else 'Unknown'
        
        trainer_match = re.search(r'Trainer:\s*([^|]+)', block)
        trainer = trainer_match.group(1).strip() if trainer_match else 'Unknown'

        last_is_trial = is_trial_venue(last_venue, last_dist) if last_venue != 'N/A' else False
        decoded = parse_last10(last10_raw) if last10_raw not in ('None', '-') else []

        horses.append({
            'num': horse_num, 'name': horse_name, 'barrier': barrier,
            'jockey': jockey, 'trainer': trainer,
            'career': career, 'last10_raw': last10_raw,
            'last_finish': last_finish, 'last_field': last_field,
            'last_dist': last_dist, 'last_venue': last_venue,
            'last_is_trial': last_is_trial,
            'decoded': decoded,
            # These will be enriched from Formguide
            'track_stats': 'N/A', 'dist_stats': 'N/A', 'trkdist_stats': 'N/A',
            'good_stats': 'N/A', 'soft_stats': 'N/A', 'heavy_stats': 'N/A',
            'first_up': 'N/A', 'second_up': 'N/A',
            'dossier_entries': [],
        })
    return horses


# ── Formguide Stats Enrichment ────────────────────────────────────────────

def _enrich_stats_from_formguide(fg_text: str, horse: dict):
    """Extract Track/Distance/Surface/Cycle stats from formguide header."""
    pattern = re.compile(rf'^\[{horse["num"]}\]\s+', re.MULTILINE)
    match = pattern.search(fg_text)
    if not match:
        return

    next_horse = re.search(r'^\[\d+\]\s+', fg_text[match.end():], re.MULTILINE)
    section_end = match.end() + next_horse.start() if next_horse else len(fg_text)
    section = fg_text[match.start():section_end]

    # Extract stats from the header block (before first race entry)
    first_race = re.search(r'^\S.+?\s+R\d+\s+\d{4}-\d{2}-\d{2}', section, re.MULTILINE)
    header = section[:first_race.start()] if first_race else section[:500]

    def _extract(key):
        m = re.search(rf'{key}:\s*(\S+)', header)
        return m.group(1) if m else 'N/A'

    horse['track_stats'] = _extract('Track')
    horse['dist_stats'] = _extract('Distance')
    horse['trkdist_stats'] = _extract('Trk/Dist')
    horse['good_stats'] = _extract('Good')
    horse['soft_stats'] = _extract('Soft')
    horse['heavy_stats'] = _extract('Heavy')
    horse['first_up'] = _extract('1st Up')
    horse['second_up'] = _extract('2nd Up')


# ── Formguide Parsing ─────────────────────────────────────────────────────

def parse_formguide_for_horse(fg_text: str, horse_num: int, horse_name: str,
                               decoded_positions: list[int]) -> list[dict]:
    """Extract up to MAX_REAL_RACES_IN_DOSSIER real race entries (plus trials)
    from Formguide for a single horse.

    Returns list of dicts, each representing one race/trial entry.
    """
    hn_clean = horse_name.split("(")[0].strip()
    pattern = re.compile(rf'^\[{horse_num}\]\s+', re.MULTILINE)
    match = pattern.search(fg_text)
    if not match:
        return []

    next_horse = re.search(r'^\[\d+\]\s+', fg_text[match.end():], re.MULTILINE)
    section_end = match.end() + next_horse.start() if next_horse else len(fg_text)
    section = fg_text[match.start():section_end]

    # Parse race entries
    race_simple = re.compile(
        r'^(\S.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+m)\s+cond:(\S+)\s+\$([0-9,]+)',
        re.MULTILINE
    )

    all_entries = []
    non_trial_idx = 0  # Index into decoded_positions (skips trials)

    for rm in race_simple.finditer(section):
        venue = rm.group(1).strip()
        race_no = rm.group(2)
        date = rm.group(3)
        distance = rm.group(4)
        condition = rm.group(5)
        prize_str = rm.group(6).replace(',', '')

        # Detect trial
        is_trial = TRIAL_MARKER in section[max(0, rm.start()-50):rm.start()+10]
        if not is_trial:
            is_trial = is_trial_venue(venue, distance)
        if not is_trial and prize_str == '0':
            is_trial = True

        # Get the full block
        block_end_match = race_simple.search(section, rm.end())
        block_end = block_end_match.start() if block_end_match else len(section)
        race_block = section[rm.start():block_end]

        # Extract jockey from the race header line
        jockey_match = re.search(
            rf'\$[0-9,]+\s+(.+?)\s+\(\d+\)\s+(\S+kg)',
            race_block.split('\n')[0]
        )
        jockey = jockey_match.group(1).strip() if jockey_match else ''
        weight = jockey_match.group(2).strip() if jockey_match else ''

        # Extract barrier from header
        barrier_match = re.search(r'\((\d+)\)\s+\S+kg', race_block.split('\n')[0])
        race_barrier = int(barrier_match.group(1)) if barrier_match else None

        # Extract race time
        time_match = re.search(r'(\d{2}:\d{2}\.\d{2,3})', race_block.split('\n')[0])
        race_time = time_match.group(1) if time_match else ''

        # Extract Margin and HC from crawler modification
        header_line = race_block.split('\n')[0]
        margin_match = re.search(r'margin:([0-9.]+)', header_line)
        hc_match = re.search(r'HC:(\d+)', header_line)
        race_margin = float(margin_match.group(1)) if margin_match else None
        race_hc = int(hc_match.group(1)) if hc_match else None

        # Extract PuntingForm advanced metrics from PF[...] block
        pf_match = re.search(r'PF\[(.+?)\]', header_line)
        pf_last600 = None
        pf_runner_time = None
        pf_race_time = None
        pf_erp = None
        pf_erace_pace = None
        pf_rt_rating = None
        if pf_match:
            pf_text = pf_match.group(1)
            l6 = re.search(r'Last600:\s*([-\d.]+)', pf_text)
            rt = re.search(r'Runner Time:\s*([-\d.]+)', pf_text)
            rct = re.search(r'Race Time:\s*([-\d.]+)', pf_text)
            erp = re.search(r'Early Runner Pace:\s*([^.]+)\.', pf_text)
            erc = re.search(r'Early Race Pace:\s*([^.]+)\.', pf_text)
            rtr = re.search(r'RT Rating:\s*([-\d.]+)', pf_text)
            pf_last600 = float(l6.group(1)) if l6 else None
            pf_runner_time = float(rt.group(1)) if rt else None
            pf_race_time = float(rct.group(1)) if rct else None
            pf_erp = erp.group(1).strip() if erp else None
            pf_erace_pace = erc.group(1).strip() if erc else None
            pf_rt_rating = float(rtr.group(1)) if rtr else None

        # Extract positions (Xth@1200m Xth@800m Xth@400m Xth@Settled)
        pos_1200_match = re.search(r'(\d+)\w+@1200m', race_block)
        pos_800_match = re.search(r'(\d+)\w+@800m', race_block)
        pos_400_match = re.search(r'(\d+)\w+@400m', race_block)
        pos_settled_match = re.search(r'(\d+)\w+@Settled', race_block)

        pos_1200 = int(pos_1200_match.group(1)) if pos_1200_match else None
        pos_800 = int(pos_800_match.group(1)) if pos_800_match else None
        pos_400 = int(pos_400_match.group(1)) if pos_400_match else None
        settled = int(pos_settled_match.group(1)) if pos_settled_match else None

        # Extract field size from result line
        result_match = re.search(r'^(1-.+?)$', race_block, re.MULTILINE)
        result_line = result_match.group(1).strip() if result_match else ''

        # Video, Note, Stewards
        video_match = re.search(r'^Video:\s*(.+?)$', race_block, re.MULTILINE)
        note_match = re.search(r'^Note:\s*(.+?)$', race_block, re.MULTILINE)
        stewards_match = re.search(r'^Stewards:\s*(.+?)$', race_block, re.MULTILINE)

        video = video_match.group(1).strip() if video_match else ''
        note = note_match.group(1).strip() if note_match else ''
        stewards = stewards_match.group(1).strip() if stewards_match else ''

        # Determine finish position
        finish_from_result = None
        if result_line and hn_clean:
            for pos_m in re.finditer(r'(\d+)-(.+?)\s*\(', result_line):
                name_in_result = pos_m.group(2).strip()
                if hn_clean.lower()[:6] in name_in_result.lower() or \
                   name_in_result.lower()[:6] in hn_clean.lower():
                    finish_from_result = int(pos_m.group(1))
                    break

        # Assign finish position using Last 10 for non-trial races
        if is_trial:
            # Trials: use result line if found, else None
            finish_pos = finish_from_result
            pos_source = 'result' if finish_from_result else 'trial'
            pos_note = ''
        else:
            result_pos = finish_from_result
            last10_pos = decoded_positions[non_trial_idx] if non_trial_idx < len(decoded_positions) else None

            if result_pos is not None:
                finish_pos = result_pos
                pos_source = 'result'
                pos_note = ''
                if last10_pos is not None and last10_pos != result_pos:
                    pos_note = f'⚠️ Last10[{non_trial_idx}]={last10_pos} ≠ Result={result_pos}'
            elif last10_pos is not None:
                finish_pos = last10_pos
                pos_source = 'last10'
                pos_note = ''
            else:
                finish_pos = None
                pos_source = 'unknown'
                pos_note = ''

            non_trial_idx += 1

        # Extract distance as integer
        dist_m = int(re.search(r'(\d+)', distance).group(1))

        # Extract flucs
        flucs_match = re.search(r'Flucs:([\$\d\s.]+)', race_block.split('\n')[0])
        flucs = flucs_match.group(1).strip() if flucs_match else ''
        last_flucs = ''
        if flucs:
            parts = flucs.split()
            last_flucs = parts[-1].replace('$', '') if parts else ''

        # Parse date
        try:
            race_date = datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            race_date = None

        entry = {
            'venue': venue, 'race_no': race_no, 'date': date,
            'date_dt': race_date,
            'distance': distance, 'dist_m': dist_m,
            'condition': condition,
            'is_trial': is_trial,
            'jockey': jockey, 'weight': weight, 'barrier': race_barrier, 'prize': prize_str,
            'race_time': race_time, 'last_flucs': last_flucs,
            'margin': race_margin, 'hc': race_hc,
            'pos_1200': pos_1200, 'pos_800': pos_800,
            'pos_400': pos_400, 'settled': settled,
            'finish_pos': finish_pos, 'pos_source': pos_source,
            'pos_note': pos_note if not is_trial else '',
            'result_line': result_line,
            'video': video, 'note': note, 'stewards': stewards,
            'pf_last600': pf_last600, 'pf_runner_time': pf_runner_time,
            'pf_race_time': pf_race_time, 'pf_erp': pf_erp,
            'pf_erace_pace': pf_erace_pace, 'pf_rt_rating': pf_rt_rating,
        }

        all_entries.append(entry)

    # Take up to MAX_REAL_RACES_IN_DOSSIER real races (plus trials)
    entries = []
    real_count = 0
    for e in all_entries:
        entries.append(e)
        if not e['is_trial']:
            real_count += 1
            if real_count >= MAX_REAL_RACES_IN_DOSSIER:
                break

    # Compute derived metrics for non-trial entries
    real_races = [e for e in entries if not e['is_trial']]

    for entry in entries:
        if entry['is_trial']:
            entry['pi'] = None
            entry['l400_pi'] = None
            entry['l800_pi'] = None
            entry['sectional_quality'] = 'N/A'
            entry['class_change'] = 'N/A'
            entry['eem'] = extract_eem_from_video(entry['video'])
            continue

        # Position Index (PI) = Settled - Finish
        if entry['settled'] is not None and entry['finish_pos'] is not None:
            entry['pi'] = entry['settled'] - entry['finish_pos']
        else:
            entry['pi'] = None

        # L400 PI = pos_400 - finish
        if entry['pos_400'] is not None and entry['finish_pos'] is not None:
            entry['l400_pi'] = entry['pos_400'] - entry['finish_pos']
        else:
            entry['l400_pi'] = None

        # L800 PI = pos_800 - finish
        if entry['pos_800'] is not None and entry['finish_pos'] is not None:
            entry['l800_pi'] = entry['pos_800'] - entry['finish_pos']
        else:
            entry['l800_pi'] = None

        # Sectional quality from PI
        entry['sectional_quality'] = compute_sectional_quality(entry['pi'])

        # EEM from video
        entry['eem'] = extract_eem_from_video(entry['video'])

    # Compute class change between consecutive real races
    for i, entry in enumerate(entries):
        if entry['is_trial']:
            entry['class_change'] = 'N/A'
            continue
        # Find the next non-trial entry after this one
        next_real = None
        for j in range(i + 1, len(entries)):
            if not entries[j]['is_trial']:
                next_real = entries[j]
                break
        if next_real:
            entry['class_change'] = compute_class_change(int(entry['prize']), int(next_real['prize']))
        else:
            entry['class_change'] = '?'

    return entries


# ── Sectional Quality ─────────────────────────────────────────────────────

def compute_sectional_quality(pi: Optional[int]) -> str:
    """Compute 段速質量 from Position Index (PI = Settled - Finish).
    Positive = gained positions (faster sectionals).
    """
    if pi is None:
        return '未知'
    if pi >= 5:
        return '極快'
    elif pi >= 2:
        return '較快'
    elif pi >= -1:
        return '一般'
    elif pi >= -3:
        return '較慢'
    else:
        return '極慢'


def compute_class_change(current_prize: int, prev_prize: int) -> str:
    """Compute 班次落差 from prize money comparison."""
    if prev_prize == 0 or current_prize == 0:
        return '?'
    ratio = current_prize / prev_prize
    if ratio >= 2.5:
        return '↑↑大幅升班'
    elif ratio >= 1.3:
        return '↑升班'
    elif ratio <= 0.4:
        return '↓↓大幅降班'
    elif ratio <= 0.7:
        return '↓降班'
    else:
        return '='


# ── Form Lines (賽績線 API) ────────────────────────────────────────────────

import subprocess

# Path to claw_profile_scraper.py (resolved relative to this script)
_CLAW_SCRAPER_PATH = str(_SCRIPT_DIR.parent / 'skills' / 'au_racing' / 'claw_profile_scraper.py')


def compute_form_lines_via_api(entries: list[dict], max_races: int = 5) -> dict:
    """Extract Top-3 opponents per race and track their future form.
    
    V2 Upgrade (2026-04-08):
      - Tracks Top-3 opponents (1st/2nd/3rd) per race, excluding self
      - Adds Class tracking column (venue-based inference)
      - 3-tier strength: ✅✅超強 / ✅強 / ⚠️中 / ❌弱
      - 5-level overall rating
      - Graceful fallback when scraper unavailable
      - 8-column table format aligned with HKJC
    
    Returns markdown table strings and strong-form rating.
    """
    real_races = [e for e in entries if not e['is_trial']][:max_races]
    
    # 1. Identify Top-3 opponents per race
    queries = []
    for race_idx, race in enumerate(real_races):
        result_line = race.get('result_line', '')
        my_pos = race.get('finish_pos')
        if not result_line or my_pos is None:
            continue
            
        # Parse '1-Perfect Night (57kg), 2-Angling Angel...'
        pos_map = {}
        for pos_m in re.finditer(r'(\d+)-([^(]+)\s*\(', result_line):
            pos_int = int(pos_m.group(1))
            horse_name = pos_m.group(2).strip()
            pos_map[pos_int] = horse_name
        
        # Collect Top-3 opponents (excluding self)
        lbl_map = {1: '(頭馬)', 2: '(亞軍)', 3: '(季軍)'}
        for target_pos in [1, 2, 3]:
            if target_pos == my_pos:
                continue
            if target_pos in pos_map:
                queries.append({
                    'race_idx': race_idx,
                    'date_dt': race.get('date_dt'),
                    'date_str': race.get('date', ''),
                    'venue': race.get('venue', ''),
                    'race_no': race.get('race_no', ''),
                    'my_pos': race.get('finish_pos'),
                    'margin': race.get('margin'),
                    'opp_pos': target_pos,
                    'opp_name': pos_map[target_pos],
                    'opp_prefix': lbl_map[target_pos],
                })
    
    if not queries:
        return {'table_lines': [], 'rating': '無資料', 'stats': 'N/A'}
    
    # 2. Fetch profiles via claw_profile_scraper.py
    unique_names = list(set(q['opp_name'] for q in queries))
    profile_data = {}
    scraper_available = True
    
    if unique_names:
        # Try absolute path first, then fallback to relative
        scraper_path = _CLAW_SCRAPER_PATH
        if not Path(scraper_path).exists():
            # Fallback to relative path from CWD
            scraper_path = '../.agents/skills/au_racing/claw_profile_scraper.py'
        
        _python_cmd = "python3" if shutil.which("python3") else "python"
        cmd = [_python_cmd, scraper_path, "--names", ",".join(unique_names)]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            if res.stdout.strip():
                profile_data = json.loads(res.stdout)
            elif res.returncode != 0:
                print(f"  [FormLines] scraper exit code {res.returncode}: {res.stderr[:200]}", file=sys.stderr)
                scraper_available = False
        except FileNotFoundError:
            print(f"  [FormLines] claw_profile_scraper.py not found at {scraper_path}", file=sys.stderr)
            scraper_available = False
        except subprocess.TimeoutExpired:
            print(f"  [FormLines] scraper timeout (90s)", file=sys.stderr)
            scraper_available = False
        except Exception as e:
            print(f"  [FormLines] API Error: {e}", file=sys.stderr)
            scraper_available = False
            
    # 3. Analyze Future form — Top-3 per race
    table_lines = []
    strong_score = 0.0  # Float for fractional scoring
    total_valid = 0
    
    def _to_slug(name):
        c = re.sub(r'\s*\([^)]+\)', '', name)
        return re.sub(r'[^a-z0-9]+', '-', c.lower().strip()).strip('-')
    
    prev_race_idx = -1
    for q in queries:
        slug = _to_slug(q['opp_name'])
        opp_data = profile_data.get(slug, {})
        
        future_wins = 0
        future_places = 0  # Top-3 finishes
        future_runs = 0
        future_venues = set()
        
        if 'runs' in opp_data:
            runs = opp_data['runs']
            for r in runs:
                try:
                    r_dt = datetime.strptime(r['date'], '%Y-%m-%d')
                    if q['date_dt'] and r_dt > q['date_dt']:
                        future_runs += 1
                        if r.get('venue'):
                            future_venues.add(r['venue'])
                        finish = r.get('finish')
                        if finish == 1:
                            future_wins += 1
                        if finish is not None and 1 <= finish <= 3:
                            future_places += 1
                except:
                    pass
        
        # Infer class from venues (AU-specific heuristic)
        class_str = '-'
        if future_venues:
            metro_venues = {'Randwick', 'Rosehill', 'Flemington', 'Caulfield', 'Moonee Valley',
                           'Eagle Farm', 'Doomben', 'Sandown', 'Canterbury'}
            has_metro = any(v in metro_venues for v in future_venues)
            has_country = any(v not in metro_venues for v in future_venues)
            if has_metro and not has_country:
                class_str = 'Metro'
            elif has_metro and has_country:
                class_str = 'Metro+省'
            else:
                class_str = '省賽'
        
        # 3-tier strength evaluation
        strength_lbl = "-"
        if not scraper_available:
            perf_str = "查冊不可用"
        elif 'error' in opp_data:
            perf_str = "查冊失敗"
        elif future_runs == 0:
            perf_str = "未有出賽"
        else:
            perf_str = f"出 {future_runs} 次: {future_wins} 勝"
            total_valid += 1
            place_rate = future_places / future_runs if future_runs > 0 else 0
            
            if future_wins >= 2 or (future_wins >= 1 and class_str == 'Metro'):
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
        
        # Build table row — show race details only on first opponent row per race
        is_first_opp = (q['race_idx'] != prev_race_idx)
        prev_race_idx = q['race_idx']
        
        race_num_str = str(q['race_idx'] + 1) if is_first_opp else ""
        date_col = q['date_str'] if is_first_opp else ""
        venue_col = f"{q['venue']} R{q['race_no']}" if is_first_opp else ""
        
        my_pos_str = str(q['my_pos']) if q['my_pos'] and is_first_opp else ''
        if is_first_opp and q['margin'] is not None and q['margin'] > 0:
            my_pos_str += f" (-{q['margin']}L)"
        
        table_lines.append(
            f"| {race_num_str} | {date_col} | {venue_col} | "
            f"{my_pos_str} | [{q['opp_pos']}] {q['opp_name']} {q['opp_prefix']} | {class_str} | {perf_str} | {strength_lbl} |"
        )
        
    # 5-level overall rating
    rating = "無資料"
    stats_str = "N/A"
    if total_valid > 0:
        ratio = strong_score / total_valid
        stats_str = f"{strong_score:.0f}/{total_valid}"
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
    elif not scraper_available:
        rating = "查冊不可用"
            
    return {
        'table_lines': table_lines,
        'rating': rating,
        'stats': stats_str,
    }


# ── EEM Energy Extraction ─────────────────────────────────────────────────

def extract_eem_from_video(video: str) -> dict:
    """Extract EEM (Energy-Effort Model) data from Video commentary.

    Parses English abbreviations commonly used in AU race videos:
    - Running style: Led, handy, MF, WTMF, tail, last, S/A
    - Width: XW, XWNC (X wide no cover)
    - Effort: keen, faded, DGO, ROS, flashed home
    """
    result = {
        'run_style': '未知',
        'run_style_en': '',
        'width': 0,
        'no_cover': False,
        'effort_signals': [],
        'consumption': '未知',
    }

    if not video or video == 'None':
        return result

    v = video.upper()

    # ── Running style detection ──
    if re.search(r'\bLED\b', v):
        result['run_style'] = '前領'
        result['run_style_en'] = 'Led'
    elif re.search(r'\bS/A\b', v) or re.search(r'\bSLOW\s*(TO\s*)?BEGIN', v):
        result['run_style'] = '慢出'
        result['run_style_en'] = 'S/A'
    elif re.search(r'\bLAST\b', v) or re.search(r'\bTAIL\b', v) or re.search(r'\bBACK\b', v):
        result['run_style'] = '後追'
        result['run_style_en'] = 'Last/Tail'
    elif re.search(r'\bWTMF\b', v):
        result['run_style'] = '中後'
        result['run_style_en'] = 'WTMF'
    elif re.search(r'\bMF\b', v) and re.search(r'HANDY', v):
        result['run_style'] = '居中前'
        result['run_style_en'] = 'MF/handy'
    elif re.search(r'\bMF\b', v):
        result['run_style'] = '居中'
        result['run_style_en'] = 'MF'
    elif re.search(r'\bHANDY\b', v):
        result['run_style'] = '居中前'
        result['run_style_en'] = 'Handy'
    elif re.search(r'[2-3](?:RD|ND|TH)\b', v):
        result['run_style'] = '居中前'
        result['run_style_en'] = 'Handy'
    elif re.search(r'[4-6](?:TH)\b', v):
        result['run_style'] = '居中'
        result['run_style_en'] = 'Mid'
    elif re.search(r'[7-9](?:TH)\b|1[0-9](?:TH)\b', v):
        result['run_style'] = '居中後'
        result['run_style_en'] = 'Mid-rear'

    # ── Width extraction ──
    width_matches = re.findall(r'(\d+)W', v)
    if width_matches:
        widths = [int(w) for w in width_matches]
        result['width'] = max(widths)

    # ── No cover ──
    if 'NC' in v or 'NO COVER' in v or 'WITHOUT COVER' in v:
        result['no_cover'] = True

    # ── Effort signals ──
    if re.search(r'\bKEEN\b', v) or 'HEAD UP' in v or 'OVER RAC' in v:
        result['effort_signals'].append('搶口')
    if re.search(r'\bFADED\b', v) or re.search(r'\bDROPPED\b', v) or 'STRUGGLED' in v:
        result['effort_signals'].append('乏力')
    if 'DGO' in v or 'DIDN\'T GO ON' in v:
        result['effort_signals'].append('無以為繼')
    if 'DRO' in v:
        result['effort_signals'].append('無反應')
    if re.search(r'ROS\b', v) or 'RAN ON STRONG' in v:
        result['effort_signals'].append('後勁強')
    if 'FLASHED HOME' in v or 'CHARGED HOME' in v:
        result['effort_signals'].append('末段急衝')
    if 'KEPT COMING' in v or 'FOUGHT' in v or 'GAMELY' in v:
        result['effort_signals'].append('鬥志強')
    if 'HELD UP' in v or 'BLOCKED' in v:
        result['effort_signals'].append('受困')
    if re.search(r'U/P\b', v) or 'URGED' in v or 'SCRUBBED' in v:
        result['effort_signals'].append('催策')
    if 'EASED' in v:
        result['effort_signals'].append('收韁')

    # ── Consumption level ──
    w = result['width']
    nc = result['no_cover']
    has_keen = '搶口' in result['effort_signals']
    has_faded = '乏力' in result['effort_signals'] or '無以為繼' in result['effort_signals']

    if w >= 5 or (w >= 4 and nc):
        result['consumption'] = '極高'
    elif w >= 4 or (w >= 3 and nc) or (w >= 3 and has_keen):
        result['consumption'] = '高'
    elif w >= 3 or (w >= 2 and nc) or has_keen:
        result['consumption'] = '中等'
    elif w >= 2:
        result['consumption'] = '中低'
    elif w >= 1:
        result['consumption'] = '低'
    else:
        # No width info — guess from style
        if result['run_style'] in ('前領',):
            result['consumption'] = '中等'  # Leading = steady effort
        elif result['run_style'] in ('後追', '慢出'):
            result['consumption'] = '低'
        else:
            result['consumption'] = '中低'

    return result


# ── PI Trend Computation ──────────────────────────────────────────────────

def compute_pi_trends(entries: list[dict]) -> dict:
    """Compute Position Index trends from real races (up to 6).

    Returns trend info for:
    - PI (Settled - Finish): overall positional gain
    - L400 PI (pos_400 - Finish): last 400m ability
    """
    real_races = [e for e in entries if not e['is_trial']][:MAX_REAL_RACES_FOR_COMPUTE]

    result = {
        'pi_values': [],
        'l400_pi_values': [],
        'pi_trend': '數據不足',
        'l400_pi_trend': '數據不足',
        'pi_summary': '',
    }

    pis = [r['pi'] for r in real_races if r['pi'] is not None]
    l400s = [r['l400_pi'] for r in real_races if r['l400_pi'] is not None]

    result['pi_values'] = pis
    result['l400_pi_values'] = l400s

    # PI trend
    if len(pis) >= 3:
        if len(pis) >= 4:
            recent_avg = sum(pis[:len(pis)//2]) / (len(pis)//2)
            older_avg = sum(pis[len(pis)//2:]) / (len(pis) - len(pis)//2)
            delta = recent_avg - older_avg
        else:
            delta = pis[0] - pis[-1]

        if abs(delta) < 0.5:
            result['pi_trend'] = '穩定'
        elif delta > 1.5:
            result['pi_trend'] = '上升軌 ✅'
        elif delta > 0:
            result['pi_trend'] = '微升'
        elif delta < -1.5:
            result['pi_trend'] = '衰退中 ⚠️'
        else:
            result['pi_trend'] = '微跌'

    # L400 PI trend
    if len(l400s) >= 3:
        if len(l400s) >= 4:
            recent_avg = sum(l400s[:len(l400s)//2]) / (len(l400s)//2)
            older_avg = sum(l400s[len(l400s)//2:]) / (len(l400s) - len(l400s)//2)
            delta = recent_avg - older_avg
        else:
            delta = l400s[0] - l400s[-1]

        if abs(delta) < 0.5:
            result['l400_pi_trend'] = '穩定'
        elif delta > 1.5:
            result['l400_pi_trend'] = '上升軌 ✅'
        elif delta > 0:
            result['l400_pi_trend'] = '微升'
        elif delta < -1.5:
            result['l400_pi_trend'] = '衰退中 ⚠️'
        else:
            result['l400_pi_trend'] = '微跌'

    return result


# ── EEM Cumulative Consumption ────────────────────────────────────────────

def compute_cumulative_eem(entries: list[dict]) -> dict:
    """Compute cumulative EEM consumption from recent 3 real races.

    Weighting: last race 0.5, previous 0.3, before that 0.2
    """
    consumption_scores = {
        '極高': 5, '高': 4, '中等': 3, '中低': 2, '低': 1, '未知': 2.5
    }
    weights = [0.5, 0.3, 0.2]

    real_races = [e for e in entries if not e['is_trial']][:3]

    result = {
        'weighted_score': 0,
        'cumulative_level': '未知',
        'recent_consumptions': [],
    }

    if not real_races:
        return result

    total_weight = 0
    weighted_sum = 0
    for i, race in enumerate(real_races):
        c = race.get('eem', {}).get('consumption', '未知')
        result['recent_consumptions'].append(c)
        w = weights[i] if i < len(weights) else 0.1
        weighted_sum += consumption_scores.get(c, 2.5) * w
        total_weight += w

    if total_weight > 0:
        score = weighted_sum / total_weight
        result['weighted_score'] = round(score, 1)

        if score >= 4.5:
            result['cumulative_level'] = '嚴重'
        elif score >= 3.5:
            result['cumulative_level'] = '中等偏高'
        elif score >= 2.5:
            result['cumulative_level'] = '中等'
        elif score >= 1.5:
            result['cumulative_level'] = '輕微'
        else:
            result['cumulative_level'] = '極輕'

    return result


# ── Engine Type Classification ────────────────────────────────────────────

def classify_engine_type(entries: list[dict]) -> dict:
    """Classify horse engine type from running style patterns.

    Uses EEM extracted run_style and PI to determine:
    - Type A (前領均速): Consistently in front, even positional movement
    - Type B (末段爆發): Runs from behind, strong L400 PI
    - Type C (持續衝刺): Flexible positioning, consistent effort
    - Type A/B (混合): No clear pattern
    """
    result = {
        'type': 'A/B',
        'type_cn': '混合型',
        'confidence': '低',
        'evidence': [],
    }

    real_races = [e for e in entries if not e['is_trial']][:MAX_REAL_RACES_FOR_COMPUTE]

    if len(real_races) < 2:
        result['evidence'].append('數據不足 (少於2場正式賽事)')
        return result

    front_count = 0
    back_count = 0
    mid_count = 0
    l400_gains = []
    total_valid = len(real_races)

    for r in real_races:
        eem = r.get('eem', {})
        style = eem.get('run_style', '未知')

        if style in ('前領', '居中前'):
            front_count += 1
        elif style in ('後追', '慢出', '居中後'):
            back_count += 1
        else:
            mid_count += 1

        l400_pi = r.get('l400_pi')
        if l400_pi is not None:
            l400_gains.append(l400_pi)

    # Also use settled position as secondary signal
    for r in real_races:
        settled = r.get('settled')
        if settled is not None and settled <= 3 and r.get('eem', {}).get('run_style') == '未知':
            front_count += 1
            total_valid += 1  # Avoid double count by incrementing total
        elif settled is not None and settled >= 7 and r.get('eem', {}).get('run_style') == '未知':
            back_count += 1
            total_valid += 1

    avg_l400_gain = sum(l400_gains) / len(l400_gains) if l400_gains else 0

    # Classification
    if total_valid >= 3:
        front_pct = front_count / total_valid
        back_pct = back_count / total_valid

        if front_pct >= 0.5:
            result['type'] = 'A'
            result['type_cn'] = '前領均速型'
            result['evidence'].append(f'前列跑法 {front_count}/{total_valid} 場')
            result['confidence'] = '高' if front_pct >= 0.7 else '中'
        elif back_pct >= 0.5 and avg_l400_gain >= 1.5:
            result['type'] = 'B'
            result['type_cn'] = '末段爆發型'
            result['evidence'].append(f'後段跑法 {back_count}/{total_valid} 場')
            result['evidence'].append(f'平均 L400 追前 {avg_l400_gain:.1f} 位')
            result['confidence'] = '高' if back_pct >= 0.7 and avg_l400_gain >= 2.0 else '中'
        elif back_pct >= 0.5 and avg_l400_gain < 1.5:
            result['type'] = 'B'
            result['type_cn'] = '後追型(爆發力一般)'
            result['evidence'].append(f'後段跑法但 L400 位移 {avg_l400_gain:.1f} 偏低')
            result['confidence'] = '低'
        elif abs(front_pct - back_pct) < 0.2:
            result['type'] = 'C'
            result['type_cn'] = '持續衝刺型'
            result['evidence'].append(f'跑法多變 前{front_count}/中{mid_count}/後{back_count}')
            result['confidence'] = '中'
        else:
            result['type'] = 'A/B'
            result['type_cn'] = '混合型'
            result['evidence'].append(f'前{front_count}/中{mid_count}/後{back_count}')
            result['confidence'] = '低'
    else:
        result['evidence'].append('場次不足，未能可靠分類')

    return result


# ── Distance Aptitude ──────────────────────────────────────────────────────

def compute_distance_aptitude(entries: list[dict], today_dist_m: int = 0) -> dict:
    """Compute distance aptitude from non-trial race history."""
    dist_bands = {}  # {distance: [win, place(2-3), lose]}

    real_races = [e for e in entries if not e['is_trial']]

    for r in real_races:
        d = r.get('dist_m', 0)
        if d <= 0:
            continue

        # Normalize to bands
        if d <= 1100:
            band = '≤1100m'
        elif d <= 1300:
            band = '1200m'
        elif d <= 1500:
            band = '1400m'
        elif d <= 1700:
            band = '1600m'
        elif d <= 1900:
            band = '1800m'
        else:
            band = '≥2000m'

        if band not in dist_bands:
            dist_bands[band] = [0, 0, 0]

        finish = r.get('finish_pos')
        if finish is None:
            continue
        if finish == 1:
            dist_bands[band][0] += 1
        elif 2 <= finish <= 3:
            dist_bands[band][1] += 1
        elif finish > 0:
            dist_bands[band][2] += 1

    # Find best distance band
    best_band = ''
    best_rate = -1
    for band, (w, p, l) in dist_bands.items():
        total = w + p + l
        if total == 0:
            continue
        rate = (w * 3 + p * 1.5) / total
        if rate > best_rate:
            best_rate = rate
            best_band = band

    # Today's distance band
    if today_dist_m <= 1100:
        today_band = '≤1100m'
    elif today_dist_m <= 1300:
        today_band = '1200m'
    elif today_dist_m <= 1500:
        today_band = '1400m'
    elif today_dist_m <= 1700:
        today_band = '1600m'
    elif today_dist_m <= 1900:
        today_band = '1800m'
    else:
        today_band = '≥2000m'

    # Compute win sequence and tolerance
    win_list = []
    close_wins = []
    close_places = []
    
    # Iterate in reverse because entries are newest first, we want oldest first (chronological)
    for r in reversed([e for e in entries if not e['is_trial']]):
        d = r.get('dist_m', 0)
        f = r.get('finish_pos')
        if d <= 0 or not f:
            continue
            
        if f == 1:
            win_list.append(f"{d}m")
            if today_dist_m > 0 and abs(d - today_dist_m) <= 100:
                close_wins.append(d)
        elif 2 <= f <= 3:
            if today_dist_m > 0 and abs(d - today_dist_m) <= 100:
                close_places.append(d)
                
    # Remove duplicates from tolerance matches but keep order
    close_wins = list(dict.fromkeys(close_wins))
    close_places = list(dict.fromkeys(close_places))

    # Format
    dist_lines = []
    for band in ['≤1100m', '1200m', '1400m', '1600m', '1800m', '≥2000m']:
        if band not in dist_bands:
            continue
        w, p, l = dist_bands[band]
        total = w + p + l
        marker = ''
        if band == best_band:
            marker = ' ⭐最佳'
        if band == today_band:
            place_count = w + p
            rate = place_count / total * 100 if total > 0 else 0
            emoji = '✅' if rate >= 50 else ('⚠️' if rate >= 25 else '❌')
            marker += f' ← 今仗 {emoji}'
        dist_lines.append(f'{band}: {total}場 ({w}-{p}-{l}){marker}')

    today_rec = dist_bands.get(today_band, [0, 0, 0])

    return {
        'best_band': best_band,
        'dist_bands': dist_bands,
        'dist_lines': dist_lines,
        'today_band': today_band,
        'today_record': today_rec,
        'win_seq': win_list,
        'close_wins': close_wins,
        'close_places': close_places
    }


# ── Output Generation ─────────────────────────────────────────────────────

import re
def translate_notes(text):
    if not text or text == '-': return '-'
    dict_map = {
        r'(?i)\bled\b': '領放',
        r'(?i)\btackled\b': '受纏鬥',
        r'(?i)dropped away': '大幅轉弱',
        r'(?i)needs (much )?easier': '班次不合',
        r'(?i)one[- ]paced( effort)?': '均速',
        r'(?i)\bunlucky\b': '欠運',
        r'(?i)honest effort': '已盡所能',
        r'(?i)held up': '受困',
        r'(?i)clear (\d+m)?': r'\1望空',
        r'(?i)flashed home': '變速強勁',
        r'(?i)missed out': '無功而回',
        r'(?i)shaken[- ]up': '受推策',
        r'(?i)drifting wider': '向外斜跑',
        r'(?i)drifted wider': '向外斜跑',
        r'(?i)\bDGO\b': '毫無威脅',
        r'(?i)no threat': '毫無威脅',
        r'(?i)never likely': '殊無勝機',
        r'(?i)faded': '轉弱',
        r'(?i)weakened': '力弱',
        r'(?i)ran on( well)?': '後上跟前',
        r'(?i)stormed home': '後上強勁',
        r'(?i)slow away': '慢閘',
        r'(?i)\bs/a\b': '慢閘',
        r'(?i)jumped poorly': '出閘笨拙',
        r'(?i)j awk\b': '出閘笨拙',
        r'(?i)good effort': '表現良好',
        r'(?i)every chance': '全程順境',
        r'(?i)chased hard': '力拼',
        r'(?i)app t': '入直路',
        r'(?i)into strt': '入直路',
        r'(?i)tt': '轉彎',
        r'(?i)on pace': '跟前',
        r'(?i)U/p': '受推策',
        r'(?i)Urged along': '受推策',
        r'(?i)Scrubbed along': '受鞭策',
        r'(?i)Revved-up': '受推策',
        r'(?i)\bWTMF\b': '中後列',
        r'(?i)\bMF\b': '中游',
        r'(?i)Left behind': '被拋離',
        r'(?i)grinding': '均速力拚',
        r'(?i)\bstrt\b': '直路',
        r'(?i)straightening': '入直路',
        r'(?i)keen\b': '搶口',
        r'(?i)Forged line': '力拼到底',
        r'(?i)bob for \d+': '影相拼入',
        r'(?i)On improve': '發力上前',
        r'(?i)Wide run no help': '沿途外疊影響發揮',
        r'(?i)Pace slackened midrace': '中段步速收慢',
        r'(?i)Fanned wider': '被迫出大外疊',
        r'(?i)Stuck on( w)?': '保持走勢',
        r'(?i)Strode up': '展步上前',
        r'(?i)Forced wider losing ground': '被迫大外疊兼失地',
        r'(?i)Only battled': '僅能均速跟隨',
        r'(?i)Battled away': '均速力拚',
        r'(?i)About as good as can go': '已發揮最佳水準',
        r'(?i)Back t\'out': '全程居後',
        r'(?i)\bPoor\b': '表現欠佳',
        r'(?i)Worked to S/L rail': '發力上前單欄領放',
        r'(?i)Challenged': '受挑戰',
        r'(?i)Tried hard but no match': '已盡所能但未及對手',
        r'(?i)Wd to line': '直路力弱',
        r'(?i)Out of depth': '班次不合',
        r'(?i)Not up to this': '班次不合',
        r'(?i)K-up': '嚴重轉弱',
        r'(?i)Knocked up': '嚴重轉弱',
        r'(?i)\bMSG\b': '稍為追近',
        r'(?i)Made some ground': '稍為追近',
        r'(?i)Kept coming gamely': '奮力力拼',
        r'(?i)Found faster going in straight': '於直路移出較佳場地衝刺',
        r'(?i)Well out': '出閘伶俐',
        r'(?i)eased right back near tail': '留居包尾',
        r'(?i)\bDRO\b': '毫無威脅(DRO)',
        r'(?i)Failed to fire off quiet ride': '採取被動跑法下毫無表現',
        r'(?i)Passed a few runners late': '尾段趕過數匹疲馬',
        r'(?i)Lacked dash': '欠缺末段衝刺力',
        r'(?i)Plain performance': '表現平庸',
        r'(?i)Crept closer': '逐步迫近',
        r'(?i)Peaked and': '走勢見弱',
        r'(?i)Hit by kickback': '食泥沙影響發揮',
        r'(?i)Let unfold last': '順其自然留居包尾',
        r'(?i)\bROS\b': '後上強勁',
        r'(?i)Best closing splits': '締造全場最佳末段',
        r'(?i)\bSG\b': '移入內欄慳位',
        r'(?i)Fought evenly along inside': '沿內欄均速力拼',
        r'(?i)Lacked necessary acceleration': '欠缺凌厲變速力',
        r'(?i)Poked thru O/L': '穿插上前至領放馬外側',
        r'(?i)Edged ahead': '稍為帶出',
        r'(?i)Levelled-up': '平頭',
        r'(?i)Strong showing': '表現出色',
        r'(?i)taking closer order': '移近馬群',
        r'(?i)Vetted clear': '獸醫檢查無事'
    }
    res = text
    for eng, chi in dict_map.items():
        res = re.sub(eng, chi, res)
    return res.strip()

def _format_notes(video, note, stewards):
    note_parts = []
    if video and video != 'None':
        note_parts.append(video[:80])
    if note and note != 'None':
        note_parts.append(note[:60])
    raw = '; '.join(note_parts) if note_parts else '-'
    return raw

def generate_full_block(horse: dict, today_dist_m: int = 0,
                        max_display: int = 5) -> str:
    """Generate the complete fact anchor + dossier block for one horse.

    Args:
        max_display: Maximum number of race entries to show in the
                     Markdown table (default 5). All entries are still
                     used for PI/EEM/Engine computations.
    """
    lines = []
    entries = horse.get('dossier_entries', [])

    # ═══════════════════════════════════════════════════
    # 📌 Racecard 事實錨點
    # ═══════════════════════════════════════════════════
    jockey_str = horse.get('jockey', 'Unknown')
    trainer_str = horse.get('trainer', 'Unknown')
    lines.append(f"### 馬匹 #{horse['num']} {horse['name']} (檔位 {horse['barrier']}) | 騎師: {jockey_str} | 練馬師: {trainer_str}")
    lines.append(f"- **📌 事實錨點 (由 Python 預填，嚴禁修改):**")
    lines.append(f"  - Last 10 字串: `{horse['last10_raw']}`")

    if horse['last_finish'] is not None:
        trial_tag = ' ⚠️[試閘]' if horse['last_is_trial'] else ''
        lines.append(
            f"  - 上仗結果(Racecard): {horse['last_finish']}/{horse['last_field']}"
            f" @ {horse['last_venue']} {horse['last_dist']}{trial_tag}"
        )
    else:
        lines.append("  - 上仗結果: N/A (初出馬)")

    lines.append(f"  - 生涯: {horse['career']}")
    lines.append(f"  - 同場: {horse['track_stats']} | 同程: {horse['dist_stats']} | 同場同程: {horse['trkdist_stats']}")
    lines.append(f"  - 好地: {horse['good_stats']} | 軟地: {horse['soft_stats']} | 重地: {horse['heavy_stats']}")
    lines.append(f"  - 初出: {horse['first_up']} | 二出: {horse['second_up']}")

    if horse['decoded']:
        pos_str = '-'.join(str(p) for p in horse['decoded'])
        lines.append(f"  - 近績序列解讀: `{pos_str}` (最新→最舊, 已跳過試閘, 0=10th)")

    # Cross-verify
    if horse['decoded'] and horse['last_finish'] is not None:
        if horse['last_is_trial']:
            lines.append(
                f"  - ℹ️ Racecard Last: 指向試閘 — 最近正式比賽名次 = {horse['decoded'][0]}"
                f" (從 Last 10 解碼)"
            )
        elif horse['decoded'][0] != horse['last_finish']:
            lines.append(
                f"  - ⚠️ 警告: Last 10 首位 ({horse['decoded'][0]})"
                f" ≠ Racecard Last ({horse['last_finish']})"
            )

    # ═══════════════════════════════════════════════════
    # 📋 完整賽績檔案 — Markdown Table (max_display rows)
    # ═══════════════════════════════════════════════════
    real_count = sum(1 for e in entries if not e['is_trial'])
    trial_count = sum(1 for e in entries if e['is_trial'])
    display_entries = entries
    llm_omitted = max(0, len(entries) - 5)

    lines.append(f"")
    lines.append(
        f"- **📋 完整賽績檔案 (全數列出 {len(display_entries)} 場"
        f"；共 {real_count} 正式 + {trial_count} 試閘，嚴禁修改數值):**"
    )
    # Table header
    lines.append("| # | 類型 | 日期 | 場地 | 路程 | 場地狀況 | 檔位 | 名次 | 班次 | 跑位軌跡 | PI | 段速 | 早段步速 | L600/RT | EEM 跑法 | EEM 消耗 | 備註 | 寬恕認定 |")
    lines.append("|---|------|------|------|------|---------|------|------|------|---------|-----|------|---------|---------|---------|---------|------|----------|")

    for idx, entry in enumerate(display_entries):
        if entry['is_trial']:
            tag = '試閘'
        elif entry.get('hc'):
            tag = f"BM{entry['hc']}"
        else:
            tag = 'Maiden/SW'

        cond = entry['condition'] if entry['condition'] != 'None' else '-'
        
        finish_str = str(entry['finish_pos']) if entry['finish_pos'] is not None else '-'
        if not entry['is_trial'] and entry.get('margin') is not None:
            # Show margin in brackets if > 0, otherwise just position
            if entry['margin'] > 0:
                finish_str += f" (-{entry['margin']}L)"

        class_ch = entry.get('class_change', '-')
        if class_ch in ('N/A', '?'):
            class_ch = '-'

        # Build position trajectory string
        pos_parts = []
        if entry['settled'] is not None:
            pos_parts.append(f"S{entry['settled']}")
        if entry['pos_800'] is not None:
            pos_parts.append(f"8th{entry['pos_800']}")
        if entry['pos_400'] is not None:
            pos_parts.append(f"4th{entry['pos_400']}")
        if entry['finish_pos'] is not None:
            pos_parts.append(f"F{entry['finish_pos']}")
        pos_str = '→'.join(pos_parts) if pos_parts else '-'

        # PI
        pi_str = '-'
        if entry.get('pi') is not None:
            pi = entry['pi']
            pi_str = f"{'+' if pi > 0 else ''}{pi}"

        sect_q = entry.get('sectional_quality', '-')
        if sect_q == 'N/A':
            sect_q = '-'

        # EEM
        eem = entry.get('eem', {})
        run_style = eem.get('run_style', '-')
        if run_style == '未知':
            run_style = '-'
        width_str = ''
        if eem.get('width', 0) > 0:
            nc = '(無遮擋)' if eem.get('no_cover') else ''
            width_str = f" {eem['width']}疊{nc}"
        eem_style = f"{run_style}{width_str}"
        consumption = eem.get('consumption', '-')
        if consumption == '未知':
            consumption = '-'

        notes = _format_notes(entry.get('video'), entry.get('note'), entry.get('stewards'))
        # Escape pipes in notes
        notes = notes.replace('|', '/')

        venue_short = f"{entry['venue']} R{entry['race_no']}"

        # PuntingForm advanced metrics
        pf_erp = entry.get('pf_erp') or '-'
        pf_l600 = entry.get('pf_last600')
        pf_rt = entry.get('pf_rt_rating')
        if pf_l600 is not None and pf_rt is not None:
            l600_sign = '+' if pf_l600 > 0 else ''
            pf_l600_rt_str = f"{l600_sign}{pf_l600}/RT{pf_rt}"
        elif pf_l600 is not None:
            l600_sign = '+' if pf_l600 > 0 else ''
            pf_l600_rt_str = f"{l600_sign}{pf_l600}"
        else:
            pf_l600_rt_str = '-'

        lines.append(
            f"| {idx+1} | {tag} | {entry['date']} | {venue_short} | "
            f"{entry['distance']} | {cond} | {entry.get('barrier') or '-'} | {finish_str} | {class_ch} | "
            f"{pos_str} | {pi_str} | {sect_q} | {pf_erp} | {pf_l600_rt_str} | {eem_style} | {consumption} | {notes} | [需判定] |"
        )

    # Output is already complete, no omitted string needed here



    # ═══════════════════════════════════════════════════
    # 📊 段速趨勢 (PI Trends)
    # ═══════════════════════════════════════════════════
    trends = compute_pi_trends(entries)

    if trends['pi_values']:
        lines.append(f"")
        lines.append(f"- **📊 段速趨勢 (近 {len(trends['pi_values'])} 場正式賽事):**")
        pi_str = ' → '.join(f"{'+' if v > 0 else ''}{v}" for v in trends['pi_values'])
        lines.append(f"  - PI (定位→終點): {pi_str} → 趨勢: {trends['pi_trend']}")
        if trends['l400_pi_values']:
            l400_str = ' → '.join(f"{'+' if v > 0 else ''}{v}" for v in trends['l400_pi_values'])
            lines.append(f"  - L400 PI (400m→終點): {l400_str} → 趨勢: {trends['l400_pi_trend']}")

    # ═══════════════════════════════════════════════════
    # ⚡ EEM 能量摘要
    # ═══════════════════════════════════════════════════
    cum_eem = compute_cumulative_eem(entries)
    if cum_eem['recent_consumptions']:
        lines.append(f"")
        lines.append(f"- **⚡ EEM 能量摘要:**")
        cons_str = ' → '.join(cum_eem['recent_consumptions'])
        lines.append(f"  - 近 {len(cum_eem['recent_consumptions'])} 仗消耗: {cons_str}")
        lines.append(f"  - 加權累積消耗: {cum_eem['weighted_score']}/5.0 → 等級: {cum_eem['cumulative_level']}")

    # ═══════════════════════════════════════════════════
    # 🔗 賽績線分析 (API Form Profile)
    # ═══════════════════════════════════════════════════
    form_lines = compute_form_lines_via_api(entries)
    if form_lines['table_lines']:
        lines.append(f"")
        lines.append(f"- **🔗 賽績線 (近 5 場正式賽事，Top-3 對手追蹤):**")
        lines.append(f"  - **綜合評估:** {form_lines['rating']} (強組比例: {form_lines['stats']})")
        lines.append(f"")
        lines.append(f"| # | 日期 | 賽事 | 我嘅名次 | 對手 | 後續比賽Class | 對手後續成績 | 強度評估 |")
        lines.append(f"|---|------|------|----------|------|---------------|--------------|----------|")
        for tl in form_lines['table_lines']:
            lines.append(tl)

    # ═══════════════════════════════════════════════════
    # 🔧 引擎與距離
    # ═══════════════════════════════════════════════════
    engine = classify_engine_type(entries)
    dist_apt = compute_distance_aptitude(entries, today_dist_m)

    lines.append(f"")
    lines.append(f"- **🔧 引擎與距離:**")
    lines.append(
        f"  - 引擎: Type {engine['type']} ({engine['type_cn']}) | "
        f"信心: {engine['confidence']} | "
        f"依據: {'; '.join(engine['evidence']) if engine['evidence'] else '數據不足'}"
    )
    if dist_apt['dist_lines']:
        lines.append(f"  - 距離分佈: {' | '.join(dist_apt['dist_lines'])}")
        
    win_seq_str = " → ".join(dist_apt['win_seq']) if dist_apt['win_seq'] else "未有頭馬紀錄"
    lines.append(f"  - 頭馬距離序列: {win_seq_str}")
    
    today_rec = dist_apt['today_record']
    today_total = sum(today_rec)
    if today_dist_m > 0:
        if today_total > 0:
            lines.append(f"  - 今仗 {today_dist_m}m ({dist_apt['today_band']}): {today_total}場 ({today_rec[0]}-{today_rec[1]}-{today_rec[2]})")
        elif dist_apt['close_wins']:
            cw_str = ", ".join([f"{d}m" for d in dist_apt['close_wins']])
            lines.append(f"  - 今仗 {today_dist_m}m: 未跑過，但有相近贏馬經驗 ({cw_str}) ✅")
        elif dist_apt['close_places']:
            cp_str = ", ".join([f"{d}m" for d in dist_apt['close_places']])
            lines.append(f"  - 今仗 {today_dist_m}m: 未跑過，但有相近上名經驗 ({cp_str})")
        else:
            lines.append(f"  - 今仗 {today_dist_m}m: 未跑過且無相近近績 (±100m) ⚠️")

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    import argparse as _ap
    parser = _ap.ArgumentParser(
        description='inject_fact_anchors.py V2 — 完整賽績檔案自動生成器'
    )
    parser.add_argument('racecard', help='Racecard.md 路徑')
    parser.add_argument('formguide', nargs='?', default=None,
                        help='Formguide.md 路徑（可選）')
    parser.add_argument('--distance', type=int, default=0,
                        help='今仗距離（米），若未指定則自動偵測')
    parser.add_argument('--output', '-o', default=None,
                        help='輸出 .md 文件路徑（默認 = 與 Racecard 同目錄）')
    parser.add_argument('--max-display', type=int, default=5,
                        help='每匹馬顯示嘅最近賽績場次數（默認 5）')
    parser.add_argument('--venue', type=str, default='',
                        help='賽場名稱 (e.g. Randwick, Caulfield) — 自動載入賽場檔案')
    args = parser.parse_args()

    racecard_path = args.racecard
    formguide_path = args.formguide
    today_dist_m = args.distance
    max_display = args.max_display

    if not Path(racecard_path).exists():
        print(f"❌ 找不到文件: {racecard_path}")
        sys.exit(1)

    # Try to extract distance from racecard HEADER only (not horse content)
    if today_dist_m == 0:
        rc_text = Path(racecard_path).read_text(encoding='utf-8')
        # Only match distance in the RACE header line (e.g. "RACE 1 — 900m | Maiden SW")
        header_dist = re.search(r'^RACE\s+\d+\s*[—–-]\s*(\d{3,5})m', rc_text, re.MULTILINE)
        if header_dist:
            today_dist_m = int(header_dist.group(1))
        else:
            print(f"\n❌ [FATAL] 無法從 Racecard header 提取今仗距離！")
            print(f"   Racecard: {racecard_path}")
            print(f"   Header 前 3 行:")
            for line in rc_text.splitlines()[:3]:
                print(f"     {line}")
            print(f"\n💡 可能原因: extractor.py 提取距離失敗，Racecard header 無 '— XXXm' 格式")
            print(f"   請用 --distance XXX 手動指定，或修復 extractor.py")
            sys.exit(1)

    horses = parse_racecard(racecard_path)
    if not horses:
        print("❌ Racecard 中找不到馬匹")
        sys.exit(1)

    # If Formguide provided, enrich with full dossier
    fg_enriched = 0
    if formguide_path:
        if not Path(formguide_path).exists():
            print(f"⚠️ Formguide 找不到: {formguide_path} — 使用 Racecard-only 模式")
        else:
            fg_text = Path(formguide_path).read_text(encoding='utf-8')
            for horse in horses:
                entries = parse_formguide_for_horse(
                    fg_text, horse['num'], horse['name'],
                    horse['decoded']
                )
                if entries:
                    horse['dossier_entries'] = entries
                    fg_enriched += 1
                _enrich_stats_from_formguide(fg_text, horse)

    # Generate output
    mode = f"Racecard+Formguide ({fg_enriched} 匹已豐富)" if formguide_path else "僅 Racecard"
    dist_str = f" | 今仗距離: {today_dist_m}m" if today_dist_m > 0 else ''
    header = f"# 📌 V2 完整賽績檔案 — {len(horses)} 匹馬 [{mode}]{dist_str}\n"

    body_lines = [header]
    
    # Track profile injection (Phase 4A)
    if args.venue:
        tp = load_track_profile(args.venue, today_dist_m)
        tp_summary = format_track_profile_summary(tp)
        if tp_summary:
            body_lines.append(tp_summary)
            body_lines.append('')
    
    body_lines.append('=' * 70)
    body_lines.append('')
    for horse in horses:
        body_lines.append(generate_full_block(horse, today_dist_m, max_display))
        body_lines.append('')
    body_lines.append('=' * 70)

    trial_count = sum(1 for h in horses if h.get('last_is_trial'))
    if trial_count:
        body_lines.append(f"\n⚠️ {trial_count} 匹馬嘅 Racecard Last: 指向試閘。")
        body_lines.append("   LLM 必須使用近績序列解讀 (來自 Last 10) 取得真實上仗名次。")

    body_lines.append(f"\n✅ {len(horses)} 匹馬嘅完整賽績檔案已生成。")

    full_output = '\n'.join(body_lines)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        # Default: same directory as racecard, replace "Racecard" with "Facts"
        rc_dir = Path(racecard_path).parent
        rc_name = Path(racecard_path).stem
        out_name = rc_name.replace('Racecard', 'Facts')
        if out_name == rc_name:  # Fallback if no "Racecard" in name
            out_name = rc_name + ' Facts'
        output_path = rc_dir / f"{out_name}.md"

    # Write to file
    output_path.write_text(full_output, encoding='utf-8')
    print(f"📌 V2 完整賽績檔案 — {len(horses)} 匹馬 [{mode}]{dist_str}")
    print(f"✅ 已寫入 → {output_path}")
    if trial_count:
        print(f"⚠️ {trial_count} 匹馬嘅 Racecard Last: 指向試閘。")


if __name__ == '__main__':
    main()
