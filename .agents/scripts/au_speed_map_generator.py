"""
au_speed_map_generator.py — AU Wong Choi Speed Map 初稿生成器

從 Racecard.md 提取 Last 10 + Barrier + Career 數據，
自動分類走位並生成 Speed Map 初稿。

Usage:
  python au_speed_map_generator.py <Racecard.md>
  python au_speed_map_generator.py <Racecard.md> --json
  python au_speed_map_generator.py <Racecard.md> --distance 1200

Output:
  Human-readable Speed Map draft for LLM to review & adjust.
  Includes PACE_TYPE_SUGGESTION and LEADER_COUNT.

NOTE: This is a DRAFT generator. LLM MUST review and adjust
      based on Formguide narrative + track/pace context.
"""
import sys, io, re, json, argparse, pathlib
from dataclasses import dataclass, field, asdict
from typing import Optional, List

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ──────────────────────────────────────────────
# Data Models
# ──────────────────────────────────────────────

@dataclass
class HorseProfile:
    number: int
    name: str
    barrier: int = 0
    last_10: str = ''       # e.g. "11214x87x4"
    career: str = ''        # e.g. "15: 3-2-1"
    weight: float = 0.0
    rating: int = 0
    jockey: str = ''
    trainer: str = ''
    # Derived
    run_style: str = 'Mid-Pack'   # Leader, On-Pace, Mid-Pack, Closer
    confidence: str = 'Normal'    # Normal, Low (insufficient data)
    notes: str = ''

# ──────────────────────────────────────────────
# Racecard Parsing
# ──────────────────────────────────────────────

# Horse entry header: "### 1. Horse Name" or "### [1] Horse Name" or "| 1 | Horse Name |"
HORSE_ENTRY_RE = re.compile(
    r'(?:###?\s*(?:\[?\s*(\d+)\s*\]?\.?\s+(.+?))\s*$'   # ### 1. Name or ### [1] Name
    r'|'
    r'^\|\s*(\d+)\s*\|\s*(.+?)\s*\|)',                    # | 1 | Name |
    re.MULTILINE
)

BARRIER_RE = re.compile(r'(?:Barrier|Bar|檔位)[\s:：]*(\d+)', re.IGNORECASE)
LAST10_RE = re.compile(r'(?:Last\s*10|近10場)[\s:：]*([0-9x]+)', re.IGNORECASE)
CAREER_RE = re.compile(r'(?:Career|生涯)[\s:：]*([\d]+:\s*[\d]+-[\d]+-[\d]+)', re.IGNORECASE)
WEIGHT_RE = re.compile(r'(?:Weight|負重|Wt)[\s:：]*([\d.]+)\s*kg', re.IGNORECASE)
RATING_RE = re.compile(r'(?:Rating|評分|Rtg)[\s:：]*(\d+)', re.IGNORECASE)
JOCKEY_RE = re.compile(r'(?:Jockey|騎師|J)[\s:：]*(.+?)(?:\||$)', re.IGNORECASE | re.MULTILINE)
TRAINER_RE = re.compile(r'(?:Trainer|練馬師|T)[\s:：]*(.+?)(?:\||$)', re.IGNORECASE | re.MULTILINE)


def parse_racecard(filepath: str) -> List[HorseProfile]:
    """Parse a Racecard.md file and extract horse profiles."""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    # Split into horse blocks
    matches = list(HORSE_ENTRY_RE.finditer(text))
    horses = []

    for i, m in enumerate(matches):
        num = m.group(1) or m.group(3)
        name = (m.group(2) or m.group(4) or '').strip()
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        horse = HorseProfile(
            number=int(num) if num else 0,
            name=name,
        )

        # Extract fields
        bar_m = BARRIER_RE.search(block)
        if bar_m:
            horse.barrier = int(bar_m.group(1))

        l10_m = LAST10_RE.search(block)
        if l10_m:
            horse.last_10 = l10_m.group(1)

        car_m = CAREER_RE.search(block)
        if car_m:
            horse.career = car_m.group(1)

        wt_m = WEIGHT_RE.search(block)
        if wt_m:
            horse.weight = float(wt_m.group(1))

        rtg_m = RATING_RE.search(block)
        if rtg_m:
            horse.rating = int(rtg_m.group(1))

        jk_m = JOCKEY_RE.search(block)
        if jk_m:
            horse.jockey = jk_m.group(1).strip()

        tr_m = TRAINER_RE.search(block)
        if tr_m:
            horse.trainer = tr_m.group(1).strip()

        horses.append(horse)

    return horses


# ──────────────────────────────────────────────
# Run Style Classification
# ──────────────────────────────────────────────

def classify_run_style(horse: HorseProfile) -> None:
    """
    Classify a horse's run style based on Last 10 string.
    
    Logic:
    - Parse Last 10: digits = finishing position, 'x' = skip
    - Look at most recent 5 actual race results
    - Count front-running (pos 1-3) vs backmarker (pos >= 7) tendencies
    - High front count = Leader/On-Pace
    - High back count = Closer
    - Mixed = Mid-Pack
    """
    if not horse.last_10 or len(horse.last_10) < 3:
        horse.run_style = 'Mid-Pack'
        horse.confidence = 'Low'
        horse.notes = '數據不足 — 需 LLM 審閱'
        return

    # Parse Last 10: left=newest, 0=10th, x=skip
    positions = []
    for ch in horse.last_10:
        if ch == 'x':
            continue
        elif ch == '0':
            positions.append(10)
        elif ch.isdigit():
            positions.append(int(ch))

    if len(positions) < 3:
        horse.run_style = 'Mid-Pack'
        horse.confidence = 'Low'
        horse.notes = f'只有 {len(positions)} 場有效數據 — 需 LLM 審閱'
        return

    # Use most recent 5 results
    recent = positions[:5]
    front_count = sum(1 for p in recent if p <= 3)
    back_count = sum(1 for p in recent if p >= 7)
    avg_pos = sum(recent) / len(recent)

    # Classification
    if front_count >= 3:
        horse.run_style = 'Leader'
    elif front_count >= 2 and avg_pos <= 4:
        horse.run_style = 'On-Pace'
    elif back_count >= 3:
        horse.run_style = 'Closer'
    elif back_count >= 2 and avg_pos >= 6:
        horse.run_style = 'Closer'
    elif avg_pos <= 4:
        horse.run_style = 'On-Pace'
    elif avg_pos >= 6:
        horse.run_style = 'Mid-Pack'  # Trending back but not extreme
    else:
        horse.run_style = 'Mid-Pack'

    horse.confidence = 'Normal'


def suggest_pace_type(horses: List[HorseProfile], distance: int = 0) -> tuple:
    """
    Suggest overall pace type based on leader count and distance.
    Returns (pace_type, leader_count, rationale).
    """
    leaders = [h for h in horses if h.run_style == 'Leader']
    on_pace = [h for h in horses if h.run_style == 'On-Pace']
    leader_count = len(leaders)
    front_count = leader_count + len(on_pace)

    # Distance factor
    is_sprint = distance > 0 and distance <= 1300
    is_staying = distance > 0 and distance >= 1800

    if leader_count >= 3 or (leader_count >= 2 and is_sprint):
        pace_type = 'Genuine'
        rationale = f'{leader_count} leaders' + (' in sprint distance' if is_sprint else '')
    elif leader_count >= 2 and front_count >= 4:
        pace_type = 'Genuine'
        rationale = f'{leader_count} leaders + {len(on_pace)} on-pace runners'
    elif leader_count <= 1 and front_count <= 2:
        pace_type = 'Moderate'
        if leader_count == 0:
            pace_type = 'Crawl'
            rationale = 'No clear leader — potential crawl'
        else:
            rationale = f'Only {leader_count} leader — likely moderate'
    else:
        pace_type = 'Moderate'
        rationale = f'{leader_count} leaders, {len(on_pace)} on-pace'

    # Staying distance adjustment
    if is_staying and pace_type == 'Genuine':
        pace_type = 'Moderate'
        rationale += ' (downgraded: staying distance)'

    return pace_type, leader_count, rationale


# ──────────────────────────────────────────────
# Output Generation
# ──────────────────────────────────────────────

def format_speed_map(horses: List[HorseProfile], pace_type: str,
                     leader_count: int, rationale: str) -> str:
    """Generate formatted Speed Map draft."""
    groups = {
        'Leader': [],
        'On-Pace': [],
        'Mid-Pack': [],
        'Closer': [],
    }
    for h in horses:
        groups[h.run_style].append(h)

    # Sort each group by barrier
    for key in groups:
        groups[key].sort(key=lambda h: h.barrier)

    lines = [
        f'PACE_TYPE_SUGGESTION: {pace_type} ({rationale})',
        f'LEADER_COUNT: {leader_count}',
        '',
        'Speed Map Draft (⚠️ Python 初稿 — LLM 必須 Review & Adjust):',
    ]

    group_labels = {
        'Leader': '領放群 (Leaders)',
        'On-Pace': '前中段 (On-Pace)',
        'Mid-Pack': '中後段 (Mid-Pack)',
        'Closer': '後上群 (Closers)',
    }

    for style, label in group_labels.items():
        members = groups[style]
        if members:
            entries = [f'#{h.number} {h.name} ({h.barrier})' for h in members]
            lines.append(f'  {label}: {", ".join(entries)}')
        else:
            lines.append(f'  {label}: [空]')

    # Notes section
    notes_horses = [h for h in horses if h.notes]
    if notes_horses:
        lines.append('')
        lines.append('⚠️ NOTES:')
        for h in notes_horses:
            lines.append(f'  - #{h.number} {h.name}: {h.notes}')

    return '\n'.join(lines)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='AU Wong Choi — Speed Map 初稿生成器'
    )
    parser.add_argument('racecard', help='Racecard .md file path')
    parser.add_argument('--json', action='store_true',
                        help='Output JSON instead of text')
    parser.add_argument('--distance', type=int, default=0,
                        help='Race distance in meters (for pace type estimation)')
    parser.add_argument('--output', type=str, default='',
                        help='Output file path (optional, defaults to stdout)')
    args = parser.parse_args()

    filepath = pathlib.Path(args.racecard)
    if not filepath.is_file():
        print(f'Error: {filepath} not found')
        sys.exit(2)

    # Parse
    horses = parse_racecard(str(filepath))
    if not horses:
        print(f'Error: No horses found in {filepath.name}')
        sys.exit(2)

    # Classify
    for h in horses:
        classify_run_style(h)

    # Pace suggestion
    pace_type, leader_count, rationale = suggest_pace_type(horses, args.distance)

    if args.json:
        output = {
            'pace_type': pace_type,
            'leader_count': leader_count,
            'rationale': rationale,
            'horses': [asdict(h) for h in horses],
        }
        result = json.dumps(output, ensure_ascii=False, indent=2)
    else:
        result = format_speed_map(horses, pace_type, leader_count, rationale)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(result)
        print(f'✅ Speed Map 初稿已寫入 {args.output}')
    else:
        print(result)


if __name__ == '__main__':
    main()
