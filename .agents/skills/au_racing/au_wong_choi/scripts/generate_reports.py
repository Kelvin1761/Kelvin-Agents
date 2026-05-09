#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import re
import glob
import pandas as pd
import io
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../../scripts")))
from racing_content_guard import scan_text_for_dummy, scan_json_for_dummy, quarantine_file


def _write_report_blocked(target_dir, race_num, reasons):
    runtime_dir = os.path.join(target_dir, ".runtime")
    os.makedirs(runtime_dir, exist_ok=True)
    path = os.path.join(runtime_dir, f"report_blocked_Race_{race_num}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Report generation blocked for Race {race_num}:\n")
        for reason in reasons:
            f.write(f"  - {reason}\n")


def _report_ready(target_dir, file_path, race_num):
    reasons = []
    runtime_dir = os.path.join(target_dir, ".runtime")
    for marker in (
        f"compile_blocked_Race_{race_num}.txt",
        f"final_qa_failed_Race_{race_num}.txt",
    ):
        if os.path.exists(os.path.join(runtime_dir, marker)):
            reasons.append(f"{marker} exists")

    strikes_file = os.path.join(target_dir, ".qa_strikes.json")
    if os.path.exists(strikes_file):
        try:
            with open(strikes_file, "r", encoding="utf-8") as f:
                strikes = json.load(f)
            if int(strikes.get(str(race_num), 0) or 0) > 0:
                reasons.append(f"open QA strike: {strikes.get(str(race_num))}")
        except Exception as exc:
            reasons.append(f"QA strikes read error: {exc}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            analysis_text = f.read()
        text_errs = scan_text_for_dummy(analysis_text)
        if text_errs:
            quarantine_file(file_path, "AU report guard dummy Analysis.md:\n" + "\n".join(text_errs))
            reasons.append(text_errs[0])
    except Exception as exc:
        reasons.append(f"Analysis.md read error: {exc}")

    logic_json = os.path.join(target_dir, f"Race_{race_num}_Logic.json")
    if not os.path.exists(logic_json):
        reasons.append(f"Race_{race_num}_Logic.json missing")
    else:
        try:
            with open(logic_json, "r", encoding="utf-8") as f:
                logic = json.load(f)
            json_errs = scan_json_for_dummy(logic, allow_pending_fill=False)
            if json_errs:
                reasons.append(f"Logic.json dummy content: {json_errs[0]}")
        except Exception as exc:
            reasons.append(f"Logic.json read error: {exc}")

    if reasons:
        _write_report_blocked(target_dir, race_num, reasons)
    return not reasons, reasons

def generate_reports(target_dir):
    """
    Reads all Race_X_Analysis files in the meeting directory or Race Analysis subfolder.
    Extracts the CSV blocks from the ends to compile an Excel file.
    Skips DOCX generation as user requested txt is fine.
    """
    if not os.path.exists(target_dir):
        print(f"Error: Directory {target_dir} does not exist.")
        sys.exit(1)

    search_dirs = [target_dir]
    analysis_dir = os.path.join(target_dir, "Race Analysis")
    if os.path.isdir(analysis_dir):
        search_dirs.append(analysis_dir)

    files = []
    for search_dir in search_dirs:
        files.extend(glob.glob(os.path.join(search_dir, "*Race_*_Analysis.txt")))
        files.extend(glob.glob(os.path.join(search_dir, "*Race * Analysis.txt")))
        files.extend(glob.glob(os.path.join(search_dir, "*Race_*_Analysis.md")))
        files.extend(glob.glob(os.path.join(search_dir, "*Race * Analysis.md")))
    files = list(dict.fromkeys(files))  # deduplicate preserving order

    if not files:
        print(f"No Race Analysis files found in {target_dir} or {analysis_dir}.")
        sys.exit(1)

    def get_race_num(filepath):
        match = re.search(r'Race[_ ]?(\d+)', os.path.basename(filepath))
        return int(match.group(1)) if match else 999

    files.sort(key=get_race_num)

    all_csv_lines = []
    header = None

    for file_path in files:
        race_num = get_race_num(file_path)
        print(f"Processing {os.path.basename(file_path)} for Top 4 Summary...")
        ready, reasons = _report_ready(target_dir, file_path, race_num)
        if not ready:
            print(f"🚨 Report blocked for Race {race_num}: {reasons[0]}")
            continue

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError as e:
            print(f"Warning: Encoding error reading {os.path.basename(file_path)}: {e}. Skipping.")
            continue

        # Intentionally use the LAST ```csv block -- the Top 4 CSV is always at the end of the analysis
        if "```csv" in content and "```" in content.split("```csv")[-1]:
            parts = content.split("```csv")
            csv_block_section = parts[-1].split("```")[0].strip()

            lines = [line.strip() for line in csv_block_section.split('\n') if line.strip() and not line.strip().startswith('[')]

            if not lines:
                print(f"Warning: No CSV data lines found in {os.path.basename(file_path)}. Skipping.")
                continue

            first_line = lines[0]
            if "Race" in first_line or "Horse" in first_line:
                if not header:
                    header = first_line
                all_csv_lines.extend(lines[1:])
            else:
                all_csv_lines.extend(lines)

    if all_csv_lines:
        if not header:
            header = "Race Number,Level of Race,Distance,Jockey,Trainer,Horse Number,Horse Name,Grade"

        csv_data = header + "\n" + "\n".join(all_csv_lines)
        try:
            df = pd.read_csv(io.StringIO(csv_data), skipinitialspace=True)
            excel_path = os.path.join(target_dir, "Top4_Summary.xlsx")
            df.to_excel(excel_path, index=False)
            print(f"Successfully created {excel_path}")
        except Exception as e:
            print(f"Warning: Error parsing CSV to Excel ({type(e).__name__}): {e}")
            fallback_path = os.path.join(target_dir, "Top4_Summary_Raw.csv")
            with open(fallback_path, "w", encoding='utf-8') as f:
                f.write(csv_data)
            print(f"Saved raw CSV fallback to {fallback_path}")
    else:
        print("Warning: No CSV Top 4 blocks found in any analysis files. Excel not generated.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_reports.py <target_directory_path>")
        sys.exit(1)

    target = sys.argv[1]
    generate_reports(target)
