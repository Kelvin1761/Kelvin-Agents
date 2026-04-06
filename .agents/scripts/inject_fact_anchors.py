#!/usr/bin/env python3
"""
inject_fact_anchors.py — P37 Racecard Fact Anchor Auto-Injector
Parses a Racecard.md file and outputs pre-filled fact anchor blocks
for each horse, ready to be injected into the analysis skeleton.

Usage:
    python3 inject_fact_anchors.py <Racecard.md>

Output:
    Prints fact anchor blocks for each horse to stdout.
"""
import re
import sys
from pathlib import Path


def parse_last10(last10_str: str) -> list[int]:
    """Decode Last 10 string into list of finishing positions (newest first).
    Skips 'x' entries (trials/scratchings). '0' = 10th place.
    """
    positions = []
    for ch in last10_str:
        if ch == 'x':
            continue
        elif ch == '0':
            positions.append(10)
        elif ch.isdigit():
            positions.append(int(ch))
    return positions


def parse_racecard(filepath: str) -> list[dict]:
    """Parse Racecard.md and extract facts for each horse."""
    text = Path(filepath).read_text(encoding='utf-8')
    horses = []

    # Match: "1. HorseName (barrier)" — skipping scratched entries
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

        # Skip scratched horses
        if 'Scratched' in block or 'status:Scratched' in block:
            continue

        # Extract Career stats
        career_match = re.search(r'Career:\s*(\S+)', block)
        career = career_match.group(1) if career_match else 'N/A'

        # Extract Last 10
        last10_match = re.search(r'Last 10:\s*(\S+)', block)
        last10_raw = last10_match.group(1) if last10_match else 'None'

        # Extract Last race info
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

        decoded = parse_last10(last10_raw) if last10_raw != 'None' else []

        horses.append({
            'num': horse_num, 'name': horse_name, 'barrier': barrier,
            'career': career, 'last10_raw': last10_raw,
            'last_finish': last_finish, 'last_field': last_field,
            'last_dist': last_dist, 'last_venue': last_venue,
            'decoded': decoded,
        })

    return horses


def generate_anchor_block(horse: dict) -> str:
    """Generate the fact anchor markdown block for a single horse."""
    lines = [
        f"### Horse #{horse['num']} {horse['name']} (Barrier {horse['barrier']})",
        f"- **📌 Racecard 事實錨點 (由 Wong Choi 預填,嚴禁修改):**",
        f"  - Last 10 String: `{horse['last10_raw']}`",
    ]
    if horse['last_finish'] is not None:
        lines.append(
            f"  - 上仗結果: {horse['last_finish']}/{horse['last_field']}"
            f" @ {horse['last_venue']} {horse['last_dist']}"
        )
    else:
        lines.append(f"  - 上仗結果: N/A (初出馬)")
    lines.append(f"  - Career: {horse['career']}")

    if horse['decoded']:
        pos_str = '-'.join(str(p) for p in horse['decoded'])
        lines.append(f"  - 近績序列解讀: `{pos_str}` (最新→最舊, 已跳過 trials)")

    # Cross-verify Last 10 vs Last race finish
    if horse['decoded'] and horse['last_finish'] is not None:
        if horse['decoded'][0] != horse['last_finish']:
            lines.append(
                f"  - ⚠️ ALERT: Last 10 首位 ({horse['decoded'][0]})"
                f" ≠ Last race finish ({horse['last_finish']})"
            )
    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 inject_fact_anchors.py <Racecard.md>")
        sys.exit(1)

    racecard_path = sys.argv[1]
    if not Path(racecard_path).exists():
        print(f"❌ File not found: {racecard_path}")
        sys.exit(1)

    horses = parse_racecard(racecard_path)
    if not horses:
        print("❌ No horses found in Racecard")
        sys.exit(1)

    print(f"📌 P37 Fact Anchors — {len(horses)} horses parsed\n")
    print("=" * 60)
    for horse in horses:
        print()
        print(generate_anchor_block(horse))
    print()
    print("=" * 60)
    print(f"\n✅ {len(horses)} fact anchors generated.")


if __name__ == '__main__':
    main()
