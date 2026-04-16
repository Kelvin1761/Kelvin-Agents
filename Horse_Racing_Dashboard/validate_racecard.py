#!/usr/bin/env python3
"""
validate_racecard.py — Pre-Analysis Gate for Racecard/Formguide Data Integrity

Detects the header duplication bug where Race 1's metadata (distance, class, prize)
is incorrectly copied to all subsequent races.

Usage:
    python validate_racecard.py "/path/to/03-25 Race 1-8 Racecard.md"
    python validate_racecard.py "/path/to/03-25 Race 1-8 Formguide.md"
    python validate_racecard.py "/path/to/meeting_folder/"  # scans for Racecard + Formguide

Exit codes:
    0 = All checks passed
    1 = Warnings found (proceed with caution)
    2 = Critical errors found (DO NOT proceed with analysis)
"""

import re
import sys
from pathlib import Path
from collections import Counter
from typing import NamedTuple


class RaceHeader(NamedTuple):
    race_number: int
    distance: str       # e.g. "1100m"
    race_class: str     # e.g. "2-Y-O, Fillies, Handicap"
    prize: str          # e.g. "$60,000"


class HorseRecord(NamedTuple):
    race_number: int
    horse_number: int
    horse_name: str
    last_distance: str  # from "Last: X/Y ZZZZm Venue"
    age: int
    rating: str


def parse_race_headers(text: str) -> list[RaceHeader]:
    """Extract race headers from Racecard/Formguide format."""
    # Pattern: RACE N — 1100m | 2-Y-O, Fillies, Handicap | $60,000
    pattern = re.compile(
        r'RACE\s+(\d+)\s*[—–-]\s*(\d{3,4}m)\s*\|\s*(.+?)\s*\|\s*(\$[\d,]+)',
        re.MULTILINE
    )
    headers = []
    for m in pattern.finditer(text):
        headers.append(RaceHeader(
            race_number=int(m.group(1)),
            distance=m.group(2),
            race_class=m.group(3).strip(),
            prize=m.group(4).strip(),
        ))
    return headers


def parse_horse_records(text: str) -> list[HorseRecord]:
    """Extract horse records to cross-validate distances."""
    records = []

    # Split by RACE headers
    race_splits = re.split(r'(RACE\s+\d+\s*[—–-])', text)

    current_race = 0
    for i, chunk in enumerate(race_splits):
        race_m = re.match(r'RACE\s+(\d+)', chunk)
        if race_m:
            current_race = int(race_m.group(1))
            continue
        if current_race == 0:
            continue

        # Find horse entries: N. HorseName (barrier)
        horse_pattern = re.compile(
            r'(\d{1,2})\.\s+(.+?)\s+\(\d+\)\s*\n'
            r'.*?Age:\s*(\d+).*?Rating:\s*(\w+).*?'
            r'Last:\s*\d+/\d+\s+(\d{3,4}m)',
            re.DOTALL
        )
        for m in horse_pattern.finditer(chunk):
            records.append(HorseRecord(
                race_number=current_race,
                horse_number=int(m.group(1)),
                horse_name=m.group(2).strip(),
                age=int(m.group(3)),
                rating=m.group(4).strip(),
                last_distance=m.group(5),
            ))

    return records


def validate(filepath: Path) -> tuple[list[str], list[str]]:
    """Run validation checks. Returns (warnings, errors)."""
    warnings = []
    errors = []

    text = filepath.read_text(encoding='utf-8')
    headers = parse_race_headers(text)

    if not headers:
        errors.append(f"No race headers found in {filepath.name}")
        return warnings, errors

    print(f"\n📄 Validating: {filepath.name}")
    print(f"   Found {len(headers)} race headers\n")

    # ─── Check 1: Header Duplication Detection ───
    distances = [h.distance for h in headers]
    classes = [h.race_class for h in headers]
    prizes = [h.prize for h in headers]

    dist_counter = Counter(distances)
    class_counter = Counter(classes)

    # If ALL races have the same distance → almost certainly a bug
    if len(headers) >= 4 and len(dist_counter) == 1:
        errors.append(
            f"🔴 CRITICAL: ALL {len(headers)} races show distance={distances[0]}. "
            f"This is almost certainly a header duplication bug!"
        )

    # If ALL races have the same class → almost certainly a bug
    if len(headers) >= 4 and len(class_counter) == 1:
        errors.append(
            f"🔴 CRITICAL: ALL {len(headers)} races show class='{classes[0]}'. "
            f"This is almost certainly a header duplication bug!"
        )

    # If >60% of races have the same distance but not ALL → suspicious
    most_common_dist, most_common_count = dist_counter.most_common(1)[0]
    if most_common_count > len(headers) * 0.6 and most_common_count < len(headers):
        warnings.append(
            f"⚠️ SUSPICIOUS: {most_common_count}/{len(headers)} races share "
            f"distance={most_common_dist}. Possible partial duplication."
        )

    # Print each race's header for visual inspection
    print("   Race Headers:")
    for h in headers:
        dup_flag = ""
        if len(dist_counter) == 1 and len(headers) > 1:
            dup_flag = " ⚠️ DUPLICATED"
        print(f"   R{h.race_number}: {h.distance} | {h.race_class} | {h.prize}{dup_flag}")
    print()

    # ─── Check 2: Cross-validate with horse records ───
    records = parse_horse_records(text)
    if records:
        for race_num in sorted(set(r.race_number for r in records)):
            race_records = [r for r in records if r.race_number == race_num]
            race_header = next((h for h in headers if h.race_number == race_num), None)

            if not race_header or not race_records:
                continue

            header_dist_m = int(re.search(r'\d+', race_header.distance).group())

            # Check if horse last-start distances suggest a different race distance
            last_dists = [int(re.search(r'\d+', r.last_distance).group())
                          for r in race_records if r.last_distance != 'None']
            if last_dists:
                avg_last_dist = sum(last_dists) / len(last_dists)
                # If average last-start distance is >300m different from header
                if abs(avg_last_dist - header_dist_m) > 300:
                    warnings.append(
                        f"⚠️ R{race_num}: Header says {race_header.distance} but "
                        f"average last-start distance of runners is {int(avg_last_dist)}m "
                        f"(diff: {int(abs(avg_last_dist - header_dist_m))}m)"
                    )

            # Check if horse ages contradict the class
            ages = [r.age for r in race_records]
            if '2-Y-O' in race_header.race_class and any(a > 2 for a in ages):
                non_2yo = [r for r in race_records if r.age > 2]
                warnings.append(
                    f"⚠️ R{race_num}: Header says '2-Y-O' but has {len(non_2yo)} "
                    f"horse(s) aged {', '.join(str(r.age) for r in non_2yo[:3])}+ "
                    f"(e.g. {non_2yo[0].horse_name})"
                )

            # Check if ratings contradict class (2yo shouldn't have BM ratings)
            ratings = [r.rating for r in race_records if r.rating != 'None']
            if '2-Y-O' in race_header.race_class and ratings:
                numeric_ratings = [int(r) for r in ratings if r.isdigit()]
                if numeric_ratings:
                    warnings.append(
                        f"⚠️ R{race_num}: Header says '2-Y-O' but horses have "
                        f"BM ratings ({', '.join(str(r) for r in numeric_ratings[:3])})"
                    )

    # ─── Check 3: Prize money sanity ───
    if len(set(prizes)) == 1 and len(headers) >= 6:
        warnings.append(
            f"⚠️ All {len(headers)} races show same prize money ({prizes[0]}). "
            f"Unusual for a meeting with mixed race types."
        )

    return warnings, errors


def main():
    if len(sys.argv) < 2:
        print("Usage: python validate_racecard.py <file_or_folder_path>")
        sys.exit(1)

    target = Path(sys.argv[1])
    files_to_check = []

    if target.is_dir():
        # Search for Racecard and Formguide files
        for pattern in ['*Racecard*', '*Formguide*', '*racecard*', '*formguide*']:
            files_to_check.extend(target.glob(pattern))
    elif target.is_file():
        files_to_check = [target]
    else:
        print(f"❌ Path not found: {target}")
        sys.exit(2)

    if not files_to_check:
        print(f"❌ No Racecard/Formguide files found in {target}")
        sys.exit(2)

    all_warnings = []
    all_errors = []

    print("=" * 60)
    print("🏇 Racecard/Formguide Data Integrity Validator")
    print("=" * 60)

    for f in files_to_check:
        w, e = validate(f)
        all_warnings.extend(w)
        all_errors.extend(e)

    # Print results
    print("=" * 60)
    print("📊 VALIDATION RESULTS")
    print("=" * 60)

    if all_errors:
        print(f"\n🔴 {len(all_errors)} CRITICAL ERROR(S):")
        for e in all_errors:
            print(f"   {e}")

    if all_warnings:
        print(f"\n⚠️  {len(all_warnings)} WARNING(S):")
        for w in all_warnings:
            print(f"   {w}")

    if not all_errors and not all_warnings:
        print("\n✅ All checks passed! Data integrity looks good.")
        sys.exit(0)
    elif all_errors:
        print(f"\n🚨 DO NOT PROCEED WITH ANALYSIS — fix the data extraction first!")
        sys.exit(2)
    else:
        print(f"\n⚠️  Proceed with caution — review warnings above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
