#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Compile Final Report
Usage: python compile_final_report.py --target_dir "/path/to/meeting/dir"

This script scans all *_Analysis.md files in the target directory, extracts the ```csv blocks
(which contain the Top 4 horses), and aggregates them into a single 'Final_Report.csv'
in that same directory.
"""

import argparse
import glob
import re
import shutil
import subprocess
import sys

def compile_reports(target_dir):
    print(f"Scanning {target_dir} for analysis files...")
    search_pattern = os.path.join(target_dir, '*_Analysis.md')
    files = glob.glob(search_pattern)
    files.sort()  # Optional sorting, but Race number extraction is more robust for order

    if not files:
        print(f"No *_Analysis.md files found in {target_dir}.")
        return False

    all_csv_lines = []
    
    # Optional headers; we'll write ours just in case the AI didn't
    header_written = False

    for filepath in files:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find the CSV block
        # Pattern looks for ```csv followed by content, then ```
        pattern = r'```csv\s*\r?\n(.*?)\r?\n```'
        match = re.search(pattern, content, re.DOTALL)

        if match:
            # Extract lines, dropping empty lines
            lines = [l.strip() for l in match.group(1).split('\n') if l.strip()]
            for line in lines:
                # If it's a header line, only keep it if we haven't written one yet
                # Usually AI writes [Race Number], [Distance] or Race, Distance
                if 'Race' in line or 'Grade' in line:
                    if not header_written:
                        all_csv_lines.insert(0, line)
                        header_written = True
                else:
                    all_csv_lines.append(line)
        else:
            print(f"Warning: No ```csv block found in {os.path.basename(filepath)}")

    if not all_csv_lines:
        print("No CSV data extracted from any analysis files.")
        return False

    # Ensure there is a header if none was found
    if not header_written:
        all_csv_lines.insert(0, "Race Number, Distance, Jockey, Trainer, Horse Number, Horse Name, Grade")

    out_file = os.path.join(target_dir, 'Final_Report.csv')
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(all_csv_lines) + '\n')

    print(f"✅ Successfully compiled {len(all_csv_lines)-1} rows into {out_file}")
    
    # [NEW V3.0] Trigger Monte Carlo Simulation Engine in Shadow Mode
    monte_carlo_script = os.path.join(os.path.dirname(__file__), 'run_monte_carlo.py')
    if os.path.exists(monte_carlo_script):
        print("🎲 Triggering Monte Carlo Dynamic Simulation Engine (Shadow Mode)...")
        _py = "python3" if shutil.which("python3") else "python"
        subprocess.run([_py, monte_carlo_script, "--target_dir", target_dir], check=False)
    else:
        print("⚠️ run_monte_carlo.py not found. Skipping shadow simulation.")

    return True

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Extract and compile all Top 4 metrics into a single CSV report.")
    parser.add_argument('--target_dir', type=str, required=True, help="Absolute path to the meeting directory containing Analysis.md files")
    args = parser.parse_args()

    success = compile_reports(args.target_dir)
    if not success:
        exit(1)
