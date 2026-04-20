#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
verify_form_accuracy.py — P39 Form Accuracy Verifier (V2)

Cross-references analysis claims against Racecard+Formguide ground truth.
    
Checks:
    1. 近績序列 vs Last 10 string
    2. 上仗名次 vs Racecard Last: (with Trial awareness)
    3. Settled Position confusion detection (Xth@Settled ≠ finishing position)
    4. Last 10 '0' = 10th enforcement

Usage:
    python3 verify_form_accuracy.py <Analysis.md> <Racecard.md> [<Formguide.md>]

Exit code: 0 = all match, 1 = mismatches found
"""
import re
from pathlib import Path


# Trial venue heuristics
TRIAL_VENUE_KEYWORDS = ['southside', 'picklebet', 'balnarring']
TRIAL_DISTANCES = {600, 650, 700, 750, 800, 900, 950}


def parse_last10(last10_str: str) -> list[int]:
    """Decode AU Last 10 string. '0' = 10th, 'x' = skip."""
    positions = []
    for ch in last10_str:
        if ch == 'x':
            continue
        elif ch == '0':
            positions.append(10)
        elif ch.isdigit():
            positions.append(int(ch))
    positions.reverse()
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


def parse_racecard_horses(text: str) -> dict:
    """Parse Racecard to get {horse_num: {...}}."""
    horses = {}
    horse_pattern = re.compile(
        r'^(\d+)\.\s+(.+?)\s*\((\d+)\)', re.MULTILINE
    )
    matches = list(horse_pattern.finditer(text))

    for i, match in enumerate(matches):
        horse_num = int(match.group(1))
        horse_name = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        if 'Scratched' in block:
            continue

        last10_match = re.search(r'Last 10:\s*(\S+)', block)
        last10_raw = last10_match.group(1) if last10_match else None

        last_match = re.search(r'Last:\s*(\d+)/(\d+)\s+(\S+)\s+(.+?)$', block, re.MULTILINE)
        last_finish = int(last_match.group(1)) if last_match else None
        last_dist = last_match.group(3).strip() if last_match else ''
        last_venue = last_match.group(4).strip() if last_match else ''

        # Detect if Last: is a trial
        last_is_trial = is_trial_venue(last_venue, last_dist) if last_venue else False

        decoded = parse_last10(last10_raw) if last10_raw and last10_raw not in ('None', '-') else []

        horses[horse_num] = {
            'name': horse_name,
            'last10_raw': last10_raw,
            'last_finish': last_finish,
            'last_is_trial': last_is_trial,
            'last_venue': last_venue,
            'last_dist': last_dist,
            'decoded': decoded,
        }

    return horses


def extract_settled_positions(fg_text: str, horse_num: int, horse_name: str) -> list[int]:
    """Extract Settled positions from the most recent races for a specific horse.
    Returns the settled positions (Xth@Settled or Xth@800m) from most recent 3 races.
    Used to detect if the LLM confused Settled with Final position.
    """
    pattern = re.compile(rf'^\[{horse_num}\]\s+', re.MULTILINE)
    match = pattern.search(fg_text)
    if not match:
        return []
    
    next_horse = re.search(r'^\[\d+\]\s+', fg_text[match.end():], re.MULTILINE)
    section_end = match.end() + next_horse.start() if next_horse else len(fg_text)
    section = fg_text[match.start():section_end]

    positions = []
    for m in re.finditer(r'(\d+)\w+@Settled', section):
        positions.append(int(m.group(1)))
    for m in re.finditer(r'(\d+)\w+@800m', section):
        positions.append(int(m.group(1)))
    
    return positions[:6]  # Return up to 6 positions


def parse_analysis_horses(text: str) -> dict:
    """Parse Analysis.md to get {horse_num: {form_sequence, last_finish_claim}}."""
    horses = {}

    horse_pattern = re.compile(
        r'【No\.(\d+)】\s*(.+?)(?:（|\()', re.MULTILINE
    )
    matches = list(horse_pattern.finditer(text))

    for i, match in enumerate(matches):
        horse_num = int(match.group(1))
        horse_name = match.group(2).strip()

        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]

        # Extract 近績序列
        form_match = re.search(r'近績序列[：:]\s*`?([^`\n]+)`?', block)
        form_sequence = form_match.group(1).strip() if form_match else None

        # Extract 上仗 名次 from 關鍵場次法醫
        last_finish_match = re.search(
            r'上仗[：:)]\s*名次\s*(\d+)', block
        )
        if not last_finish_match:
            last_finish_match = re.search(
                r'\[?上仗\]?[：:]\s*名次\s*(\d+)', block
            )
        last_finish_claim = int(last_finish_match.group(1)) if last_finish_match else None

        horses[horse_num] = {
            'name': horse_name,
            'form_sequence': form_sequence,
            'last_finish_claim': last_finish_claim,
        }

    return horses


def verify(racecard_horses: dict, analysis_horses: dict, fg_text: str = None) -> list[str]:
    """Cross-reference and return list of mismatches."""
    errors = []
    warnings = []

    for horse_num, analysis in analysis_horses.items():
        if horse_num not in racecard_horses:
            continue

        rc = racecard_horses[horse_num]
        name = analysis['name']

        # --- CHECK 1: 上仗名次 vs Last 10 decoded first position (PRIMARY check) ---
        if analysis['last_finish_claim'] is not None and rc['decoded']:
            expected = rc['decoded'][0]
            claimed = analysis['last_finish_claim']
            
            if rc['last_is_trial']:
                # Racecard Last: is a trial — Last 10 first real position is the truth
                if claimed != expected:
                    errors.append(
                        f"❌ [{horse_num}] {name}: 上仗名次 — "
                        f"Analysis claims {claimed}, but Last 10 decodes to {expected} "
                        f"(string: `{rc['last10_raw']}`). "
                        f"⚠️ Racecard Last: {rc['last_finish']}/{rc['last_venue']} is a TRIAL."
                    )
            else:
                # Normal case: check both Racecard Last and Last 10
                if claimed != rc['last_finish'] and claimed != expected:
                    errors.append(
                        f"❌ [{horse_num}] {name}: 上仗名次 — "
                        f"Analysis claims {claimed}, "
                        f"Racecard says {rc['last_finish']}, "
                        f"Last 10 decodes to {expected} "
                        f"(string: `{rc['last10_raw']}`)"
                    )
                elif claimed != expected and claimed == rc['last_finish']:
                    # Matched Racecard but not Last10 — could be OK if Last: isn't trial
                    pass  # Acceptable
                elif claimed != rc['last_finish'] and claimed == expected:
                    # Matched Last10 but not Racecard — could be trial confusion
                    warnings.append(
                        f"⚠️ [{horse_num}] {name}: 上仗名次 matches Last 10 ({expected}) "
                        f"but differs from Racecard Last ({rc['last_finish']}) — "
                        f"verify Racecard Last is not a Trial"
                    )

        # --- CHECK 2: Settled Position confusion detection ---
        if fg_text and analysis['last_finish_claim'] is not None:
            settled_positions = extract_settled_positions(fg_text, horse_num, name)
            claimed = analysis['last_finish_claim']
            if rc['decoded'] and settled_positions:
                expected_finish = rc['decoded'][0]
                # If claimed matches a settled position but NOT the actual finish
                if claimed != expected_finish and claimed in settled_positions:
                    errors.append(
                        f"🔄 [{horse_num}] {name}: SETTLED CONFUSION — "
                        f"Analysis claims 上仗={claimed} which matches a Settled/800m position, "
                        f"but Last 10 says finish was {expected_finish}. "
                        f"⛔ Xth@Settled ≠ final position!"
                    )

        # --- CHECK 3: 近績序列 consistency with Last 10 ---
        if analysis['form_sequence'] and rc['decoded']:
            form_nums = re.findall(r'\d+', analysis['form_sequence'])
            if form_nums:
                try:
                    first_form = int(form_nums[0])
                    if first_form != rc['decoded'][0]:
                        errors.append(
                            f"⚠️ [{horse_num}] {name}: 近績序列 — "
                            f"First position is {first_form}, "
                            f"Last 10 first position is {rc['decoded'][0]} "
                            f"(string: `{rc['last10_raw']}`)"
                        )
                except (ValueError, IndexError):
                    pass

        # --- CHECK 4: Last 10 '0' = 10th enforcement ---
        if rc['last10_raw'] and '0' in (rc['last10_raw'] or ''):
            # Verify the analysis doesn't skip or misinterpret '0'
            if analysis['form_sequence'] and rc['decoded']:
                if 10 in rc['decoded']:
                    if '10' not in (analysis['form_sequence'] or ''):
                        warnings.append(
                            f"⚠️ [{horse_num}] {name}: Last 10 contains '0'=10th "
                            f"but 近績序列 may not show '10' — "
                            f"(string: `{rc['last10_raw']}`, decoded: {rc['decoded']})"
                        )

    return errors + warnings


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 verify_form_accuracy.py <Analysis.md> <Racecard.md> [<Formguide.md>]")
        sys.exit(1)

    analysis_path = sys.argv[1]
    racecard_path = sys.argv[2]
    formguide_path = sys.argv[3] if len(sys.argv) >= 4 else None

    for path in [analysis_path, racecard_path]:
        if not Path(path).exists():
            print(f"❌ File not found: {path}")
            sys.exit(1)

    racecard_text = Path(racecard_path).read_text(encoding='utf-8')
    analysis_text = Path(analysis_path).read_text(encoding='utf-8')
    fg_text = None
    if formguide_path and Path(formguide_path).exists():
        fg_text = Path(formguide_path).read_text(encoding='utf-8')

    racecard_horses = parse_racecard_horses(racecard_text)
    analysis_horses = parse_analysis_horses(analysis_text)

    if not racecard_horses:
        print("❌ No horses found in Racecard")
        sys.exit(1)

    if not analysis_horses:
        print("❌ No horses found in Analysis")
        sys.exit(1)

    mode = "Racecard+Formguide" if fg_text else "Racecard-only"
    print(f"\n🔍 P39 Form Accuracy Verification [{mode}]")
    print(f"   Analysis: {len(analysis_horses)} horses")
    print(f"   Racecard: {len(racecard_horses)} horses")

    # Report trial detection
    trial_count = sum(1 for h in racecard_horses.values() if h.get('last_is_trial'))
    if trial_count:
        print(f"   ⚠️ Trial Detection: {trial_count} horse(s) have Racecard Last: → Trial")

    print(f"   {'=' * 50}")

    errors = verify(racecard_horses, analysis_horses, fg_text)

    if errors:
        real_errors = [e for e in errors if e.startswith('❌') or e.startswith('🔄')]
        soft_warnings = [e for e in errors if e.startswith('⚠️')]

        if real_errors:
            print(f"\n❌ [FAILED] {len(real_errors)} form accuracy error(s) found:\n")
            for err in real_errors:
                print(f"  {err}")
        
        if soft_warnings:
            print(f"\n⚠️ {len(soft_warnings)} warning(s):\n")
            for w in soft_warnings:
                print(f"  {w}")
        
        if real_errors:
            print(f"\n⚠️ ACTION REQUIRED: Fix the above errors before proceeding.")
            sys.exit(1)
        else:
            print(f"\n✅ [PASSED with warnings] No critical errors, {len(soft_warnings)} warning(s).")
            sys.exit(0)
    else:
        verified_count = sum(
            1 for h in analysis_horses
            if h in racecard_horses and analysis_horses[h].get('last_finish_claim') is not None
        )
        print(f"\n✅ [PASSED] All {verified_count} verifiable horses match Racecard data.")
        sys.exit(0)


if __name__ == '__main__':
    main()
