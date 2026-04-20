#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
extract_formguide_data.py — AU Wong Choi Protocol Structured Data Extractor
Parses Formguide.md and extracts machine-readable data per horse.

Usage:
    python3 extract_formguide_data.py <Formguide.md> [--format json|markdown] [--output <file>]

Extracts per horse (last 8 starts, skipping trials):
  - Finish position, field size, distance, track, condition, weight, jockey
  - L600 time, settling position
  - Stewards notes, video notes
  - Career/Track/Distance/Condition stats
  - 1st-up/2nd-up/3rd-up stats
  - Season/12-month stats
  - Trainer/Jockey LY stats
  - Age, sire, dam info
  - Flucs (market moves)
  - Computed: fitness arc, L600 trend, condition suitability
"""
import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional


# ──────────────────────────────────────────────
# Formguide Parser
# ──────────────────────────────────────────────

def parse_formguide(filepath: str, source: str = "punters") -> list[dict]:
    """Parse Formguide.md and extract structured data per horse."""
    text = Path(filepath).read_text(encoding='utf-8')

    # Split by horse separator
    horse_blocks = re.split(r'={40,}', text)

    horses = []
    for block in horse_blocks:
        block = block.strip()
        if not block:
            continue

        # Match horse header: [NUM] Name (barrier)
        header_match = re.search(
            r'^\[(\d+)\]\s+(.+?)\s*\((\d+)\)', block, re.MULTILINE
        )
        if not header_match:
            continue

        horse_num = int(header_match.group(1))
        horse_name = header_match.group(2).strip()
        barrier = int(header_match.group(3))

        # Extract bio info
        bio_match = re.search(
            r'(\d+)yo(\w)\s+(\w+)\s*\|\s*Sire:\s*(.+?)\s*\|\s*Dam:\s*(.+?)$',
            block, re.MULTILINE
        )
        age = int(bio_match.group(1)) if bio_match else 0
        sex = bio_match.group(2) if bio_match else ''
        colour = bio_match.group(3) if bio_match else ''
        sire = bio_match.group(4).strip() if bio_match else ''
        dam = bio_match.group(5).strip().rstrip(')') if bio_match else ''

        # Extract flucs
        flucs_match = re.search(r'Flucs:\s*(.+?)$', block, re.MULTILINE)
        flucs_raw = flucs_match.group(1).strip() if flucs_match else ''
        flucs = re.findall(r'\$([\d.]+)', flucs_raw)
        flucs = [float(f) for f in flucs if f != 'None']

        # Extract trainer/jockey LY stats
        tj_match = re.search(
            r'T:\s*(.+?)\s*\(LY:\s*(.+?)\)\s*\|\s*J:\s*(.+?)\s*\(LY:\s*(.+?)\)',
            block
        )
        trainer = tj_match.group(1).strip() if tj_match else ''
        trainer_ly = tj_match.group(2).strip() if tj_match else ''
        jockey = tj_match.group(3).strip() if tj_match else ''
        jockey_ly = tj_match.group(4).strip() if tj_match else ''

        # Extract stats tables
        stats = {}
        stat_patterns = {
            'career': r'Career:\s*([\d:]+[\d\-]+)',
            'win_pct': r'Win %:\s*(\d+)',
            'place_pct': r'Place %:\s*(\d+)',
            'roi': r'ROI:\s*(-?\d+)',
            'track': r'Track:\s*([\d:]+[\d\-]+)',
            'distance': r'Distance:\s*([\d:]+[\d\-]+)',
            'trk_dist': r'Trk/Dist:\s*([\d:]+[\d\-]+)',
            'good': r'Good:\s*([\d:]+[\d\-]+)',
            'soft': r'Soft:\s*([\d:]+[\d\-]+)',
            'heavy': r'Heavy:\s*([\d:]+[\d\-]+)',
            'firm': r'Firm:\s*([\d:]+[\d\-]+)',
            'first_up': r'1st Up:\s*([\d:]+[\d\-]+)',
            'second_up': r'2nd Up:\s*([\d:]+[\d\-]+)',
            'third_up': r'3rd Up:\s*([\d:]+[\d\-]+)',
            'season': r'Season:\s*([\d:]+[\d\-]+)',
            'twelve_month': r'12 Month:\s*([\d:]+[\d\-]+)',
            'fav': r'Fav:\s*([\d:]+[\d\-]+)',
            'class_stat': r'Class:\s*([\d:]+[\d\-]+)',
        }
        
        if source == 'racenet':
            stat_patterns = {
                'career': r'Career\s*([\d:]+[\d\-]+)',
                'win_pct': r'Win %:\s*(\d+)',
                'place_pct': r'Place %:\s*(\d+)',
                'roi': r'ROI\s*(-?\d+)',
                'track': r'Track\s*([\d:]+[\d\-]+)',
                'distance': r'Distance\s*([\d:]+[\d\-]+)',
                'trk_dist': r'Track/Dist\s*([\d:]+[\d\-]+)',
                'good': r'Good\s*([\d:]+[\d\-]+)',
                'soft': r'Soft\s*([\d:]+[\d\-]+)',
                'heavy': r'Heavy\s*([\d:]+[\d\-]+)',
                'firm': r'Firm\s*([\d:]+[\d\-]+)',
                'first_up': r'1st Up\s*([\d:]+[\d\-]+)',
                'second_up': r'2nd Up\s*([\d:]+[\d\-]+)',
                'third_up': r'3rd Up\s*([\d:]+[\d\-]+)',
                'class_stat': r'Class\s*([\d:]+[\d\-]+)'
            }

        for key, pattern in stat_patterns.items():
            m = re.search(pattern, block)
            stats[key] = m.group(1) if m else 'N/A'

        # Extract race entries (non-trial)
        race_entries = extract_race_entries(block, source)

        # Extract ALL dates (including trials) for fitness arc calculation
        all_dates = extract_all_dates(block)

        # Compute derived fields
        fitness_arc = compute_fitness_arc(race_entries, all_dates=all_dates)
        l600_trend = compute_l600_trend(race_entries)
        condition_profile = compute_condition_profile(stats)

        horses.append({
            'num': horse_num,
            'name': horse_name,
            'barrier': barrier,
            'age': age,
            'sex': sex,
            'colour': colour,
            'sire': sire,
            'dam': dam,
            'flucs': flucs,
            'flucs_direction': compute_flucs_direction(flucs),
            'trainer': trainer,
            'trainer_ly': trainer_ly,
            'jockey': jockey,
            'jockey_ly': jockey_ly,
            'stats': stats,
            'race_entries': race_entries[:8],  # Last 8 starts
            'fitness_arc': fitness_arc,
            'l600_trend': l600_trend,
            'condition_profile': condition_profile,
        })

    return horses


def extract_race_entries(block: str, source: str = "punters") -> list[dict]:
    """Extract individual race entries from a horse block, skipping trials."""
    entries = []

    # Match race lines: Venue RN Date Distance cond:X $Prize Jockey (barrier) Weight
    race_pattern = re.compile(
        r'^(\S+(?:\s+\S+)*?)\s+R(\d+)\s+'
        r'(\d{4}-\d{2}-\d{2})\s+'
        r'(\d+)m\s+'
        r'cond:(\d+)\s+'
        r'\$([,\d]+)\s+'
        r'(.+?)\s+\((\d+)\)\s+'
        r'([\d.]+)kg\s+'
        r'Flucs:(\S+\s+\S+)\s+'
        r'(\d{2}:\d{2}\.\d{3})\s+'
        r'(.*?)$',
        re.MULTILINE
    )

    # Trial detection
    
    if source == 'racenet':
        # Custom logic to parse Racenet markdown
        # Format:
        # **Venue R1**
        # 12/03/2026 1200m
        # **Good4**
        # Race Name
        # (cond...) Out 3m $45K Jockey (4) 59.5kg Flucs:$... 01:11.510 (600/35.1) 3@800
        
        matches = re.finditer(r'\*\*(.*? R\d+)\*\*\s+(\d{2}/\d{2}/\d{4})\s+(\d+)m\s+\*\*(.*?)\*\*\s+(.*?)\s+\((.*?)\).*?\$([\dK]+).*?([a-zA-Z\s]+)\s+\((\d+)\)\s+([\d.]+)kg.*?Flucs:(.*?)(\d{2}:\d{2}\.\d{3})', block, re.DOTALL)
        for idx, m in enumerate(matches):
            entries.append({
                'venue': m.group(1).split()[0].strip(),
                'race_no': int(re.search(r'R(\d+)', m.group(1)).group(1)),
                'date': '-'.join(m.group(2).split('/')[::-1]), # reformat DD/MM/YYYY to YYYY-MM-DD
                'distance': int(m.group(3)),
                'condition': 4 if 'Good' in m.group(4) else 5,
                'prize': m.group(7).replace('K', '000'),
                'jockey': m.group(8).strip(),
                'jockey_barrier': int(m.group(9)),
                'weight': float(m.group(10)),
                'flucs': [e for e in m.group(11).split() if '$' in e],
                'track_time': m.group(12),
                'l600_time': "0:35.000", # placeholder as racenet format is tricky here
                'position_settling': m.group(12) # placeholder
            })
        return entries

    trial_marker = '**(TRIAL)**'

    # Split block into lines for processing
    lines = block.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Skip trials
        if trial_marker in line:
            # Skip until next race entry or separator
            i += 1
            while i < len(lines) and not re.match(r'^\S+.*R\d+\s+\d{4}', lines[i].strip()) and '====' not in lines[i]:
                i += 1
            continue

        # Try to match a race entry start line
        race_start = re.match(
            r'^(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\s+cond:(\d+)\s+\$([\d,]+)\s+'
            r'(.+?)\s+\((\d+)\)\s+([\d.]+)kg\s+Flucs:(.+?)\s+'
            r'(\d{2}:\d{2}\.\d{3})\s*(.*?)$',
            line
        )

        if race_start:
            venue = race_start.group(1).strip()
            race_no = int(race_start.group(2))
            date = race_start.group(3)
            distance = int(race_start.group(4))
            condition = int(race_start.group(5))
            prize = race_start.group(6).replace(',', '')
            jockey = race_start.group(7).strip()
            jockey_barrier = int(race_start.group(8))
            weight = float(race_start.group(9))
            flucs_str = race_start.group(10).strip()
            time_str = race_start.group(11)
            position_info = race_start.group(12).strip()

            # Extract settling/sectional info from position_info
            l600 = None
            l600_match = re.search(r'\(600m/([\d:]+\.?\d*)\)', position_info)
            if l600_match:
                l600 = l600_match.group(1)

            settling = None
            settling_match = re.search(r'(\d+)(?:th|st|nd|rd)@(?:800m|Settled)', position_info)
            if settling_match:
                settling = int(settling_match.group(1))

            # Collect subsequent lines (result, video, note, stewards)
            result_line = ''
            video_line = ''
            note_line = ''
            stewards_line = ''

            j = i + 1
            while j < len(lines) and j <= i + 5:
                next_line = lines[j].strip()
                if not next_line or re.match(r'^\S+.*R\d+\s+\d{4}', next_line) or '====' in next_line:
                    break
                if next_line.startswith('1-'):
                    result_line = next_line
                elif next_line.startswith('Video:'):
                    video_line = next_line.replace('Video:', '').strip()
                elif next_line.startswith('Note:'):
                    note_line = next_line.replace('Note:', '').strip()
                elif next_line.startswith('Stewards:'):
                    stewards_line = next_line.replace('Stewards:', '').strip()
                j += 1

            # Extract finish position from result line
            finish_pos = None
            field_size = None
            margin = None
            if result_line:
                # Check if this horse won
                result_parts = re.findall(r'(\d+)-(.+?)(?:,|$)', result_line)
                for pos, detail in result_parts:
                    # Look for the horse's name or margin info
                    pass
                # Simpler: check if horse is listed as winner (1-Name)
                # The result line format is: 1-Winner (Wkg), 2-Second (Wkg) MarginL, 3-Third (Wkg) MarginL

            entry = {
                'venue': venue,
                'race_no': race_no,
                'date': date,
                'distance': distance,
                'condition': condition,
                'prize': int(prize) if prize else 0,
                'jockey': jockey,
                'weight': weight,
                'time': time_str,
                'l600': l600,
                'settling_position': settling,
                'result_line': result_line,
                'video': video_line,
                'note': note_line if note_line != 'None' else '',
                'stewards': stewards_line if stewards_line != 'None' else '',
            }
            entries.append(entry)
            i = j
        else:
            i += 1

    return entries


def extract_all_dates(block: str) -> list[str]:
    """Extract ALL dates from a horse block, including trials.
    This is used to build a complete timeline for spell detection."""
    return re.findall(r'\b(\d{4}-\d{2}-\d{2})\b', block)


def compute_fitness_arc(entries: list, all_dates: Optional[list] = None) -> dict:
    """Compute fitness arc from race entries.
    
    Uses a multi-signal approach to detect spell boundaries:
    1. Gap > 56 days from last formal race to today → new prep (First-up)
    2. Gap > 56 days between race entries when no trial fills the gap
    3. Stewards/notes mentioning "spell" or "sent for a spell"
    
    Args:
        entries: list of formal race entries (trials excluded)
        all_dates: list of ALL chronological dates (incl. trials) for gap detection
    """
    if not entries:
        return {'stage': 'Unknown', 'spell_days': 0, 'starts_this_prep': 0}

    # Sort by date (newest first)
    sorted_entries = sorted(entries, key=lambda x: x['date'], reverse=True)

    # Build a combined timeline of all dates (races + trials) if provided
    all_sorted_dates = None
    if all_dates:
        unique_dates = sorted(set(all_dates), reverse=True)
        all_sorted_dates = [datetime.strptime(d, '%Y-%m-%d') for d in unique_dates]

    # Determine spell days (from most recent formal race to today)
    spell_days = 0
    today = datetime.now()
    if sorted_entries:
        try:
            last_race_date = datetime.strptime(sorted_entries[0]['date'], '%Y-%m-%d')
            spell_days = (today - last_race_date).days
        except ValueError:
            pass

    # CRITICAL CHECK: Is today's race a new prep start?
    # If gap from last formal race to today > 56 days → check if trials fill the gap
    if spell_days > 56:
        # The horse hasn't had a formal race in > 56 days
        # Check if trials exist between last race and today
        if all_sorted_dates:
            last_race_dt = datetime.strptime(sorted_entries[0]['date'], '%Y-%m-%d')
            events_after_last_race = [d for d in all_sorted_dates if last_race_dt < d <= today]
            
            if events_after_last_race:
                # There are trials after the last race — check sub-gaps
                all_points = sorted([last_race_dt] + events_after_last_race + [today])
                max_sub_gap = max(
                    (all_points[j+1] - all_points[j]).days
                    for j in range(len(all_points) - 1)
                )
                if max_sub_gap > 56:
                    # Still a genuine spell despite trials
                    return {
                        'stage': 'First-up',
                        'spell_days': spell_days,
                        'starts_this_prep': 0,
                    }
                # else: trials are close together, could be same prep → fall through
            
            # No trials at all after last race → definitely a new prep
            if not events_after_last_race:
                return {
                    'stage': 'First-up',
                    'spell_days': spell_days,
                    'starts_this_prep': 0,
                }
        else:
            # No trial data available → use simple 56-day rule
            return {
                'stage': 'First-up',
                'spell_days': spell_days,
                'starts_this_prep': 0,
            }

    # Count starts in current preparation (going backwards)
    starts_this_prep = 1
    for i in range(1, len(sorted_entries)):
        try:
            d1 = datetime.strptime(sorted_entries[i-1]['date'], '%Y-%m-%d')
            d2 = datetime.strptime(sorted_entries[i]['date'], '%Y-%m-%d')
            race_gap = (d1 - d2).days

            # Check 1: Large gap between race entries (> 56 days)
            if race_gap > 56:
                # Check if a trial fills the gap
                if all_sorted_dates:
                    events_between = [d for d in all_sorted_dates if d2 < d < d1]
                    if events_between:
                        all_points = sorted([d2] + events_between + [d1])
                        max_sub_gap = max(
                            (all_points[j+1] - all_points[j]).days
                            for j in range(len(all_points) - 1)
                        )
                        if max_sub_gap > 56:
                            break  # Still a genuine spell
                        else:
                            starts_this_prep += 1
                            continue  # Trial filled the gap — same prep
                    else:
                        break  # No trial fill → genuine spell
                else:
                    break  # No trial data → use simple gap

            # Check 2: Stewards notes mentioning "spell"
            entry = sorted_entries[i]
            spell_keywords = ['sent for a spell', 'let up', 'paddock rest',
                            'turned out', 'given a spell', 'freshened']
            stewards_text = (entry.get('stewards', '') + ' ' + entry.get('note', '')).lower()
            if any(kw in stewards_text for kw in spell_keywords):
                break  # This was the last race before a spell

            starts_this_prep += 1
        except (ValueError, KeyError):
            break

    # Determine stage label
    spell_days = 0
    if sorted_entries:
        try:
            last_date = datetime.strptime(sorted_entries[0]['date'], '%Y-%m-%d')
            spell_days = (today - last_date).days
        except ValueError:
            pass

    stage_map = {
        1: 'First-up',
        2: 'Second-up',
        3: 'Third-up (黃金期)',
        4: 'Fourth-up',
        5: 'Fifth-up',
    }
    if starts_this_prep >= 6:
        stage = f'Deep Prep (第{starts_this_prep}仗 ⚠️)'
    else:
        stage = stage_map.get(starts_this_prep, f'{starts_this_prep}th-up')

    return {
        'stage': stage,
        'spell_days': spell_days,
        'starts_this_prep': starts_this_prep,
    }


def compute_l600_trend(entries: list[dict]) -> dict:
    """Compute L600 trend from race entries."""
    l600_times = []
    for e in entries[:8]:  # Last 8 starts
        if e.get('l600'):
            try:
                parts = e['l600'].split(':')
                if len(parts) == 2:
                    secs = float(parts[0]) * 60 + float(parts[1])
                else:
                    secs = float(e['l600'])
                l600_times.append({
                    'time': secs,
                    'raw': e['l600'],
                    'date': e['date'],
                    'distance': e['distance'],
                    'condition': e['condition'],
                    'venue': e['venue'],
                })
            except (ValueError, IndexError):
                pass

    if len(l600_times) < 2:
        return {'trend': 'N/A (不足數據)', 'times': l600_times}

    # Compare recent 3 vs older 3
    recent = l600_times[:3]
    older = l600_times[3:6] if len(l600_times) >= 4 else l600_times[3:]

    avg_recent = sum(t['time'] for t in recent) / len(recent)
    avg_older = sum(t['time'] for t in older) / len(older) if older else avg_recent

    diff = avg_recent - avg_older
    if diff < -0.3:
        trend = '上升軌 ↑'
    elif diff > 0.3:
        trend = '衰退中 ↓'
    else:
        trend = '穩定 →'

    return {
        'trend': trend,
        'avg_recent': round(avg_recent, 3),
        'avg_older': round(avg_older, 3) if older else None,
        'times': l600_times,
    }


def compute_condition_profile(stats: dict) -> dict:
    """Compute condition suitability profile."""
    profile = {}
    for cond in ['good', 'soft', 'heavy']:
        raw = stats.get(cond, 'N/A')
        if raw != 'N/A':
            # Parse X:W-P-S format
            m = re.match(r'(\d+):(\d+)-(\d+)-(\d+)', raw)
            if m:
                starts = int(m.group(1))
                wins = int(m.group(2))
                places = int(m.group(3))
                shows = int(m.group(4))
                win_rate = (wins / starts * 100) if starts > 0 else 0
                place_rate = ((wins + places + shows) / starts * 100) if starts > 0 else 0
                profile[cond] = {
                    'starts': starts, 'wins': wins, 'places': places, 'shows': shows,
                    'win_rate': round(win_rate, 1),
                    'place_rate': round(place_rate, 1),
                }
    return profile


def compute_flucs_direction(flucs: list[float]) -> str:
    """Determine market movement direction from fluctuations."""
    if not flucs or len(flucs) < 2:
        return 'N/A'
    first = flucs[0]
    last = flucs[-1]
    if last < first * 0.85:
        return '大幅縮水 ⬇️'
    elif last < first * 0.95:
        return '略縮水 ↓'
    elif last > first * 1.15:
        return '大幅外漂 ⬆️'
    elif last > first * 1.05:
        return '略外漂 ↑'
    else:
        return '穩定 →'


def parse_racecard_weights(filepath: str) -> dict:
    """Parse Racecard.md to extract current race weights per horse number.
    Returns {horse_num: {'weight': float, 'base_weight': float, 'claim': float}}"""
    text = Path(filepath).read_text(encoding='utf-8')
    weights = {}
    # Match: 1. Name (barrier)\nTrainer:... | Weight: 58.5kg (Base 61.5kg, Claim -3kg)
    # or: Weight: 61.5 | ...
    for m in re.finditer(
        r'^(\d+)\.\s+.+?\n.+?Weight:\s*([\d.]+)(?:kg)?'
        r'(?:\s*\(Base\s*([\d.]+)kg,\s*Claim\s*(-?[\d.]+)kg\))?',
        text, re.MULTILINE
    ):
        num = int(m.group(1))
        weight = float(m.group(2))
        base = float(m.group(3)) if m.group(3) else weight
        claim = float(m.group(4)) if m.group(4) else 0
        weights[num] = {'weight': weight, 'base_weight': base, 'claim': claim}
    return weights


def compute_weight_differentials(horses: list, racecard_weights: dict) -> list:
    """Compute weight differential data for all horses."""
    if not racecard_weights:
        return horses

    # Field-level stats
    all_weights = [v['weight'] for v in racecard_weights.values()]
    if not all_weights:
        return horses

    field_top = max(all_weights)
    field_lightest = min(all_weights)
    field_median = sorted(all_weights)[len(all_weights) // 2]
    field_avg = sum(all_weights) / len(all_weights)

    for h in horses:
        num = h['num']
        rc = racecard_weights.get(num)
        if not rc:
            h['weight_diff'] = None
            continue

        current_w = rc['weight']
        # Weight vs last start
        last_start_w = None
        weight_change = None
        if h['race_entries']:
            last_start_w = h['race_entries'][0].get('weight')
            if last_start_w:
                weight_change = round(current_w - last_start_w, 1)

        h['weight_diff'] = {
            'current': current_w,
            'base': rc['base_weight'],
            'claim': rc['claim'],
            'field_top': field_top,
            'field_lightest': field_lightest,
            'field_median': round(field_median, 1),
            'field_avg': round(field_avg, 1),
            'diff_vs_top': round(current_w - field_top, 1),
            'diff_vs_lightest': round(current_w - field_lightest, 1),
            'diff_vs_median': round(current_w - field_median, 1),
            'is_top_weight': current_w == field_top,
            'is_lightest': current_w == field_lightest,
            'last_start_weight': last_start_w,
            'weight_change': weight_change,
        }

    return horses


# ──────────────────────────────────────────────
# Output Formatters
# ──────────────────────────────────────────────

def format_markdown(horses: list[dict]) -> str:
    """Format extracted data as compact Markdown for LLM consumption."""
    output = []
    output.append("# 📦 Formguide 結構化數據提取\n")

    for h in horses:
        output.append(f"## [{h['num']}] {h['name']} (檔位:{h['barrier']})")
        output.append(f"**基本:** {h['age']}歲{h['sex']} | 父:{h['sire']} | 母:{h['dam']}")
        output.append(f"**練馬師:** {h['trainer']} (LY: {h['trainer_ly']})")
        output.append(f"**騎師:** {h['jockey']} (LY: {h['jockey_ly']})")
        output.append(f"**狀態週期:** `{h['fitness_arc']['stage']}` | 距上仗: {h['fitness_arc']['spell_days']}日 | 本備賽期第 {h['fitness_arc']['starts_this_prep']} 仗")
        output.append(f"**市場動向:** {h['flucs_direction']} ({' → '.join(f'${f}' for f in (h['flucs'][:3] + h['flucs'][-2:]) if h['flucs'])})" if h['flucs'] else "**市場動向:** N/A")

        # Stats summary
        s = h['stats']
        output.append(f"\n**統計概覽:**")
        output.append(f"| 類別 | 數據 |")
        output.append(f"|:---|:---|")
        output.append(f"| Career | {s.get('career', 'N/A')} (W:{s.get('win_pct', '?')}% P:{s.get('place_pct', '?')}%) |")
        output.append(f"| Season | {s.get('season', 'N/A')} |")
        output.append(f"| 同場 Track | {s.get('track', 'N/A')} |")
        output.append(f"| 同程 Distance | {s.get('distance', 'N/A')} |")
        output.append(f"| 同場同程 Trk/Dist | {s.get('trk_dist', 'N/A')} |")
        output.append(f"| Good | {s.get('good', 'N/A')} |")
        output.append(f"| Soft | {s.get('soft', 'N/A')} |")
        output.append(f"| Heavy | {s.get('heavy', 'N/A')} |")
        output.append(f"| 1st Up | {s.get('first_up', 'N/A')} |")
        output.append(f"| 2nd Up | {s.get('second_up', 'N/A')} |")
        output.append(f"| 3rd Up | {s.get('third_up', 'N/A')} |")
        output.append(f"| Favourite | {s.get('fav', 'N/A')} |")

        # Condition profile
        cp = h['condition_profile']
        if cp:
            output.append(f"\n**場地適性:**")
            for cond, data in cp.items():
                output.append(f"- {cond.capitalize()}: {data['starts']}戰 {data['wins']}勝 (W:{data['win_rate']}% P:{data['place_rate']}%)")

        # Weight Differential
        wd = h.get('weight_diff')
        if wd:
            top_flag = ' 🔴頂磅' if wd['is_top_weight'] else ''
            light_flag = ' 🟢最輕' if wd['is_lightest'] else ''
            change_str = f"{wd['weight_change']:+.1f}kg" if wd['weight_change'] is not None else 'N/A'
            claim_str = f" (減磅 {wd['claim']}kg)" if wd['claim'] else ''
            output.append(f"\n**⚖️ 磅差分析:**")
            output.append(f"- 今場負重: **{wd['current']}kg**{claim_str}{top_flag}{light_flag}")
            output.append(f"- 場均: {wd['field_avg']}kg | 頂磅: {wd['field_top']}kg | 最輕: {wd['field_lightest']}kg")
            output.append(f"- 距頂磅: `{wd['diff_vs_top']:+.1f}kg` | 距最輕: `{wd['diff_vs_lightest']:+.1f}kg`")
            output.append(f"- 對比上仗: `{change_str}` (上仗: {wd['last_start_weight']}kg)" if wd['last_start_weight'] else "- 對比上仗: N/A")

        # L600 Trend
        lt = h['l600_trend']
        output.append(f"\n**L600 段速趨勢:** `{lt['trend']}`")
        if lt.get('times'):
            output.append(f"| # | 日期 | 場地 | 距離 | Cond | L600 |")
            output.append(f"|:--|:-----|:-----|:-----|:-----|:-----|")
            for i, t in enumerate(lt['times'][:8]):
                output.append(f"| {i+1} | {t['date']} | {t['venue']} | {t['distance']}m | {t['condition']} | {t['raw']} |")

        # Race entries (last 8 starts)
        if h['race_entries']:
            output.append(f"\n**近 {len(h['race_entries'])} 仗詳細法醫:**")
            for i, e in enumerate(h['race_entries']):
                label = ['上仗', '前仗', '大前仗'][i] if i < 3 else f'第{i+1}仗'
                output.append(f"\n**[{label}]** {e['date']} | {e['venue']} R{e['race_no']} | {e['distance']}m | Cond:{e['condition']} | {e['weight']}kg | J:{e['jockey']}")
                if e.get('l600'):
                    output.append(f"  - L600: {e['l600']}")
                if e.get('settling_position'):
                    output.append(f"  - Settling: {e['settling_position']}th")
                if e.get('video'):
                    output.append(f"  - 📹 Video: {e['video']}")
                if e.get('note'):
                    output.append(f"  - 📝 Note: {e['note']}")
                if e.get('stewards'):
                    output.append(f"  - ⚖️ Stewards: {e['stewards']}")
                if e.get('result_line'):
                    output.append(f"  - 🏁 Result: {e['result_line']}")

        output.append(f"\n{'─' * 60}\n")

    return '\n'.join(output)


def format_json(horses: list[dict]) -> str:
    """Format extracted data as JSON."""
    return json.dumps(horses, ensure_ascii=False, indent=2, default=str)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="AU Wong Choi Protocol — Formguide Data Extractor"
    )
    parser.add_argument("formguide", type=str, help="Path to Formguide.md")
    parser.add_argument("--racecard", type=str, default=None,
                        help="Path to Racecard.md (for weight differential calculation)")
    parser.add_argument("--format", type=str, choices=['json', 'markdown'], default='json', help="Output format (json or markdown)")
    parser.add_argument("--output", type=str, default=None, help="Output file path (default: stdout)")
    parser.add_argument("--source", type=str, default="punters", help="Source format: punters or racenet")
    args = parser.parse_args()

    if not Path(args.formguide).exists():
        print(f"❌ File not found: {args.formguide}")
        sys.exit(1)

    horses = parse_formguide(args.formguide)

    if not horses:
        print("❌ No horses found in Formguide")
        sys.exit(1)

    # Weight differential (optional, requires Racecard)
    if args.racecard and Path(args.racecard).exists():
        rc_weights = parse_racecard_weights(args.racecard)
        horses = compute_weight_differentials(horses, rc_weights)
        weight_tag = f" | ⚖️ {len(rc_weights)} weights loaded"
    else:
        weight_tag = ''

    if args.format == 'json':
        result = format_json(horses)
    else:
        result = format_markdown(horses)

    if args.output:
        Path(args.output).write_text(result, encoding='utf-8')
        print(f"✅ Data extracted: {args.output}")
        print(f"   📊 {len(horses)} horses | {sum(len(h['race_entries']) for h in horses)} race entries parsed{weight_tag}")
    else:
        print(result)


if __name__ == '__main__':
    main()
