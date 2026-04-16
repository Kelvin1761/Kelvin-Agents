#!/usr/bin/env python3
"""
Import bet JSON records into the AU/HK Horse Race Summary .numbers ROI files.

Usage:
    python3 import_bets_to_roi.py bets_2026-03-25_Kensington.json
    python3 import_bets_to_roi.py bets/              # import all JSONs in folder

The script reads each bet record and appends a new row to the ROI sheet
in the appropriate .numbers file (AU or HKJC based on the 'region' field).
Duplicate detection: skips bets that already exist (same date+venue+race+horse).
"""
import json
import sys
from pathlib import Path
from numbers_parser import Document

# Paths
SCRIPT_DIR = Path(__file__).resolve().parent
ANTIGRAVITY_ROOT = SCRIPT_DIR.parent
AU_ROI_PATH = ANTIGRAVITY_ROOT / ".agents" / "skills" / "au_racing" / "AU Horse Race Summary.numbers"
HK_ROI_PATH = ANTIGRAVITY_ROOT / ".agents" / "skills" / "hkjc_racing" / "HK Horse Race Summary.numbers"

# AU ROI columns: Date(0), 馬場(1), 賽事編號(2), Class(3), Range(4), Horse Number(5), 馬匹名稱(6), 投注本金(7), 位置賠率(8), Final Result(9), 總派彩回報(10), 單場淨利潤(11)
AU_COLS = {
    "date": 0, "venue": 1, "race_number": 2, "class": 3, "range": 4,
    "horse_number": 5, "horse_name": 6, "stake": 7, "odds": 8,
    "result": 9, "payout": 10, "profit": 11,
}

# HK ROI columns: Date(0), 馬場(1), 賽事編號(2), Class(3), Range(4), Type(5), Weather(6), Jockey(7), Trainer(8), Horse Number(9), 馬匹名稱(10), 投注本金(11), 位置賠率(12), Final Result(13), 總派彩回報(14), 單場淨利潤(15)
HK_COLS = {
    "date": 0, "venue": 1, "race_number": 2, "class": 3, "range": 4,
    "type": 5, "weather": 6, "jockey": 7, "trainer": 8,
    "horse_number": 9, "horse_name": 10, "stake": 11, "odds": 12,
    "result": 13, "payout": 14, "profit": 15,
}


def format_date_for_numbers(date_str: str) -> str:
    """Convert '2026-03-25' to '3.25' format used in .numbers files."""
    if not date_str or '-' not in date_str:
        return date_str
    parts = date_str.split('-')
    if len(parts) == 3:
        month = int(parts[1])
        day = int(parts[2])
        return f"{month}.{day:02d}"
    return date_str


def get_existing_keys(table, header_row, date_col, venue_col, race_col, horse_col):
    """Build a set of existing (date, venue, race, horse) keys for dedup."""
    keys = set()
    current_date = ''
    for r in range(header_row + 1, table.num_rows):
        try:
            d = table.cell(r, date_col).value
            if d is not None and str(d).strip():
                current_date = str(d).strip()
            v = table.cell(r, venue_col).value
            rc = table.cell(r, race_col).value
            h = table.cell(r, horse_col).value
            if v and h:
                keys.add((current_date, str(v).strip(), str(int(float(rc))) if rc else '', str(int(float(h))) if h else ''))
        except Exception:
            continue
    return keys


def find_last_data_row(table, horse_col, header_row=2):
    """Find the last row with data."""
    last = header_row
    for r in range(header_row + 1, table.num_rows):
        try:
            v = table.cell(r, horse_col).value
            if v is not None and str(v).strip():
                last = r
        except Exception:
            continue
    return last


def import_bets(json_path: Path):
    """Import bets from a JSON file into the appropriate .numbers ROI file."""
    with open(json_path) as f:
        bets = json.load(f)

    if not bets:
        print(f"  ⚠️ No bets in {json_path.name}")
        return 0

    # Group by region
    au_bets = [b for b in bets if b.get("region") == "au"]
    hk_bets = [b for b in bets if b.get("region") == "hkjc"]

    total_imported = 0

    if au_bets:
        total_imported += _write_to_numbers(AU_ROI_PATH, au_bets, AU_COLS, "au")
    if hk_bets:
        total_imported += _write_to_numbers(HK_ROI_PATH, hk_bets, HK_COLS, "hkjc")

    return total_imported


def _write_to_numbers(numbers_path: Path, bets, cols, region):
    """Write bet records to a .numbers file."""
    if not numbers_path.exists():
        print(f"  ⚠️ ROI file not found: {numbers_path}")
        return 0

    doc = Document(str(numbers_path))
    sheet = doc.sheets[0]  # ROI sheet
    table = sheet.tables[0]
    header_row = 2

    # Get existing keys for dedup
    existing = get_existing_keys(table, header_row, cols["date"], cols["venue"], cols["race_number"], cols["horse_number"])

    # Find insertion point
    horse_col = cols["horse_name"]
    last_row = find_last_data_row(table, horse_col, header_row)
    next_row = last_row + 1

    imported = 0
    current_date_str = None

    for bet in sorted(bets, key=lambda b: (b["date"], b["race_number"], b["horse_number"])):
        date_nums = format_date_for_numbers(bet["date"])
        key = (date_nums, bet["venue"], str(bet["race_number"]), str(bet["horse_number"]))
        if key in existing:
            print(f"  ⏭️ Skip duplicate: R{bet['race_number']} #{bet['horse_number']} {bet['horse_name']}")
            continue

        # Ensure we have enough rows
        while next_row >= table.num_rows:
            # Can't add rows dynamically with numbers_parser in all versions
            # We'll write to the next available row (Numbers files usually have extra empty rows)
            break

        if next_row >= table.num_rows:
            print(f"  ⚠️ Not enough rows in the spreadsheet. Need row {next_row} but only {table.num_rows} rows exist.")
            break

        # Write the date only for the first bet of each date group (or always)
        date_val = date_nums if date_nums != current_date_str else date_nums
        current_date_str = date_nums

        table.write(next_row, cols["date"], date_val)
        table.write(next_row, cols["venue"], bet["venue"])
        table.write(next_row, cols["race_number"], bet["race_number"])
        table.write(next_row, cols["horse_number"], bet["horse_number"])
        table.write(next_row, cols["horse_name"], bet["horse_name"])
        table.write(next_row, cols["stake"], bet.get("stake", 1))
        table.write(next_row, cols["odds"], bet.get("odds", 0))

        # Result: position number (1,2,3 = placed) or empty for lost
        result_pos = bet.get("result_position")
        if result_pos and result_pos > 0:
            table.write(next_row, cols["result"], result_pos)
            payout = bet.get("payout")
            if not payout:  # Handle cases where payout is explicitly 0 or None
                payout = bet.get("odds", 0) * bet.get("stake", 1)
            profit = payout - bet.get("stake", 1)
            table.write(next_row, cols["payout"], round(payout, 2))
            table.write(next_row, cols["profit"], round(profit, 2))
        # Lost bets: leave payout and profit empty (matching existing convention)

        # HK-specific fields
        if region == "hkjc" and "jockey" in cols:
            table.write(next_row, cols["jockey"], bet.get("jockey", ""))
            table.write(next_row, cols["trainer"], bet.get("trainer", ""))

        existing.add(key)
        imported += 1
        next_row += 1
        status_emoji = "✅" if result_pos and result_pos > 0 else "❌"
        print(f"  {status_emoji} R{bet['race_number']} #{bet['horse_number']} {bet['horse_name']} @{bet.get('odds',0)} → {'P'+str(result_pos) if result_pos and result_pos > 0 else 'X'}")

    if imported > 0:
        doc.save(str(numbers_path))
        print(f"  💾 Saved {imported} new bets to {numbers_path.name}")

    return imported


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 import_bets_to_roi.py <bets.json or bets_folder/>")
        sys.exit(1)

    target = Path(sys.argv[1])
    json_files = []

    if target.is_dir():
        json_files = sorted(target.glob("bets_*.json"))
    elif target.is_file() and target.suffix == ".json":
        json_files = [target]
    else:
        print(f"❌ Not a valid JSON file or directory: {target}")
        sys.exit(1)

    if not json_files:
        print("❌ No bet JSON files found")
        sys.exit(1)

    total = 0
    for jf in json_files:
        print(f"📥 Importing {jf.name}...")
        n = import_bets(jf)
        total += n

    print(f"\n🏁 Done: {total} bets imported to ROI database")


if __name__ == "__main__":
    main()
