#!/usr/bin/env python3
"""
verify_form_accuracy.py — P37 Per-Batch Form Accuracy Verifier
Cross-references analysis claims against Racecard ground truth to
detect LLM hallucination of horse past results.

Usage:
    python3 verify_form_accuracy.py <Analysis.md> <Racecard.md>

Checks:
    1. 近績序列 in analysis matches Last 10 from Racecard
    2. 上仗名次 claims match Racecard Last: field
    3. Flags any mismatches as errors

Exit code: 0 = all match, 1 = mismatches found
"""
import re
import sys
from pathlib import Path


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
    return positions


def parse_racecard_horses(text: str) -> dict:
    """Parse Racecard to get {horse_num: {last10, last_finish, name}}."""
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

        last_match = re.search(
            r'Last:\s*(\d+)/(\d+)', block
        )
        last_finish = int(last_match.group(1)) if last_match else None

        decoded = parse_last10(last10_raw) if last10_raw and last10_raw != 'None' else []

        horses[horse_num] = {
            'name': horse_name,
            'last10_raw': last10_raw,
            'last_finish': last_finish,
            'decoded': decoded,
        }

    return horses


def parse_analysis_horses(text: str) -> dict:
    """Parse Analysis.md to get {horse_num: {form_sequence, last_finish_claim}}."""
    horses = {}

    # Match horse headers: 【No.X】Name
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
            # Try alternative format
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


def verify(racecard_horses: dict, analysis_horses: dict) -> list[str]:
    """Cross-reference and return list of mismatches."""
    errors = []

    for horse_num, analysis in analysis_horses.items():
        if horse_num not in racecard_horses:
            continue  # Horse might be scratched or new

        rc = racecard_horses[horse_num]
        name = analysis['name']

        # Check 1: 上仗名次 vs Racecard Last finish
        if analysis['last_finish_claim'] is not None and rc['last_finish'] is not None:
            if analysis['last_finish_claim'] != rc['last_finish']:
                errors.append(
                    f"❌ [{horse_num}] {name}: 上仗名次 — "
                    f"Analysis claims {analysis['last_finish_claim']}, "
                    f"Racecard says {rc['last_finish']} "
                    f"(Last 10: `{rc['last10_raw']}`)"
                )

        # Check 2: 上仗名次 vs decoded Last 10 first position
        if (analysis['last_finish_claim'] is not None
                and rc['decoded']
                and analysis['last_finish_claim'] != rc['decoded'][0]):
            # Don't double-report if already caught above
            if rc['last_finish'] is None or rc['last_finish'] == rc['decoded'][0]:
                errors.append(
                    f"❌ [{horse_num}] {name}: 上仗名次 — "
                    f"Analysis claims {analysis['last_finish_claim']}, "
                    f"Last 10 decodes to {rc['decoded'][0]} "
                    f"(string: `{rc['last10_raw']}`)"
                )

        # Check 3: 近績序列 consistency with Last 10
        if analysis['form_sequence'] and rc['decoded']:
            # Extract numbers from form sequence
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

    return errors


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 verify_form_accuracy.py <Analysis.md> <Racecard.md>")
        sys.exit(1)

    analysis_path = sys.argv[1]
    racecard_path = sys.argv[2]

    for path in [analysis_path, racecard_path]:
        if not Path(path).exists():
            print(f"❌ File not found: {path}")
            sys.exit(1)

    racecard_text = Path(racecard_path).read_text(encoding='utf-8')
    analysis_text = Path(analysis_path).read_text(encoding='utf-8')

    racecard_horses = parse_racecard_horses(racecard_text)
    analysis_horses = parse_analysis_horses(analysis_text)

    if not racecard_horses:
        print("❌ No horses found in Racecard")
        sys.exit(1)

    if not analysis_horses:
        print("❌ No horses found in Analysis")
        sys.exit(1)

    print(f"\n🔍 P37 Form Accuracy Verification")
    print(f"   Analysis: {len(analysis_horses)} horses")
    print(f"   Racecard: {len(racecard_horses)} horses")
    print(f"   {'=' * 50}")

    errors = verify(racecard_horses, analysis_horses)

    if errors:
        print(f"\n❌ [FAILED] {len(errors)} form accuracy error(s) found:\n")
        for err in errors:
            print(f"  {err}")
        print(f"\n⚠️ ACTION REQUIRED: Fix the above errors before proceeding.")
        sys.exit(1)
    else:
        verified_count = sum(
            1 for h in analysis_horses
            if h in racecard_horses and analysis_horses[h].get('last_finish_claim') is not None
        )
        print(f"\n✅ [PASSED] All {verified_count} verifiable horses match Racecard data.")
        sys.exit(0)


if __name__ == '__main__':
    main()
