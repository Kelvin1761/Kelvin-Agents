"""
prefill_horse_data.py — Extract structured statistics from formguide/racecard
to pre-populate horse analysis skeletons, reducing LLM hallucination risk.

Usage:
  python prefill_horse_data.py --racecard <racecard.md> --output <prefilled.json>

Output JSON structure per horse:
  {
    "num": 1,
    "name": "Golden Star",
    "jockey": "Z Purton",
    "trainer": "J Size",
    "weight": 133,
    "barrier": 5,
    "last_6_finishes": "1-3-2-5-1-4",
    "days_since_last": 21,
    "season_record": "3-1-2-8",
    "same_distance_record": "2-0-1-3",
    "same_course_distance_record": "1-0-1-2",
    "gear_changes": "First time blinkers"
  }
"""
import sys, io, re, json, argparse
from pathlib import Path

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')


def extract_horses_from_racecard(text: str) -> list:
    """Extract structured horse data from racecard markdown."""
    horses = []

    # Pattern: Match horse entries (e.g. "## 1. GOLDEN STAR" or "**1** GOLDEN STAR")
    # Support multiple racecard formats
    horse_blocks_re = re.compile(
        r'(?:^##?\s*(\d+)[.、]?\s*(.+?)$|'
        r'^\*\*(\d+)\*\*\s*(.+?)$)',
        re.MULTILINE
    )

    matches = list(horse_blocks_re.finditer(text))
    for i, m in enumerate(matches):
        num = int(m.group(1) or m.group(3))
        name = (m.group(2) or m.group(4) or '').strip()

        # Extract block for this horse
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        horse = {
            'num': num,
            'name': name,
            'jockey': extract_field(block, r'(?:騎師|Jockey)[：:]\s*(.+?)(?:\n|$)'),
            'trainer': extract_field(block, r'(?:練馬師|Trainer)[：:]\s*(.+?)(?:\n|$)'),
            'weight': extract_int(block, r'(?:負磅|Weight|Wt)[：:]\s*(\d+)'),
            'barrier': extract_int(block, r'(?:檔位|Draw|Barrier)[：:]\s*(\d+)'),
            'last_6_finishes': extract_last_6(block),
            'days_since_last': extract_int(block, r'(?:休後|Days since|上賽距今)[：:]\s*(\d+)'),
            'season_record': extract_field(block, r'(?:季內|Season)[：:]\s*([\d]+-[\d]+-[\d]+-[\d]+)'),
            'same_distance_record': extract_field(block, r'(?:同程|Same Dist)[：:]\s*([\d]+-[\d]+-[\d]+-[\d]+)'),
            'same_course_distance_record': extract_field(block, r'(?:同場同程|Same C\+D)[：:]\s*([\d]+-[\d]+-[\d]+-[\d]+)'),
            'gear_changes': extract_field(block, r'(?:配備|Gear)[：:]\s*(.+?)(?:\n|$)'),
        }
        horses.append(horse)

    return horses


def extract_field(block: str, pattern: str) -> str:
    """Extract a text field using regex, return empty string if not found."""
    m = re.search(pattern, block, re.IGNORECASE)
    return m.group(1).strip() if m else ''


def extract_int(block: str, pattern: str) -> int:
    """Extract an integer field, return 0 if not found."""
    m = re.search(pattern, block, re.IGNORECASE)
    return int(m.group(1)) if m else 0


def extract_last_6(block: str) -> str:
    """Extract last 6 finishes pattern like 1-3-2-5-1-4."""
    # Look for a sequence of dash-separated numbers
    m = re.search(r'(?:近六場|Last 6|Form)[：:]\s*([\d]+-[\d]+-[\d]+-[\d]+-[\d]+-[\d]+)', block, re.IGNORECASE)
    if m:
        return m.group(1)
    # Try to find any 6-number dash-separated sequence
    m = re.search(r'\b(\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2}-\d{1,2})\b', block)
    return m.group(1) if m else ''


def main():
    parser = argparse.ArgumentParser(description='HKJC Pre-fill Horse Data Extractor')
    parser.add_argument('--racecard', type=str, required=True, help='Path to racecard markdown file')
    parser.add_argument('--output', type=str, default=None, help='Output JSON file path')
    args = parser.parse_args()

    racecard_path = Path(args.racecard)
    if not racecard_path.exists():
        print(f'❌ File not found: {racecard_path}')
        sys.exit(1)

    text = racecard_path.read_text(encoding='utf-8')
    horses = extract_horses_from_racecard(text)

    if not horses:
        print(f'⚠️ No horses found in {racecard_path.name}')
        sys.exit(1)

    result = json.dumps(horses, ensure_ascii=False, indent=2)

    if args.output:
        Path(args.output).write_text(result, encoding='utf-8')
        print(f'✅ Extracted {len(horses)} horses → {args.output}')
    else:
        print(result)

    # Summary
    filled = sum(1 for h in horses for k, v in h.items() if v and k != 'num')
    total = len(horses) * 11
    print(f'\n📊 Pre-fill coverage: {filled}/{total} fields ({filled/total*100:.0f}%)')


if __name__ == '__main__':
    main()
