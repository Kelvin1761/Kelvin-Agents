#!/usr/bin/env python3
"""
compile_nba_report.py
(Phase 3: NBA Compilation & Archiving)

This script scans the generated Analysis.md files for each game, parses out
the SGM (Same Game Multi) blocks or Bankers, and synthesizes them into a single
final report ready for Telegram Push.
"""

import os
import argparse
import glob

def compile_reports(target_dir):
    print(f"📄 Compiling NBA final reports from {target_dir}...")
    
    analysis_files = glob.glob(os.path.join(target_dir, "*_Analysis.md"))
    
    if not analysis_files:
        print("⚠️ No analysis files found to compile.")
        return
        
    final_csv_lines = ["Matchup, Pick, Odds, Confidence, Recommendation"]
    
    for fpath in sorted(analysis_files):
        with open(fpath, "r") as f:
            lines = f.readlines()
            
        in_csv = False
        for line in lines:
            if line.strip() == "```csv":
                in_csv = True
                continue
            elif line.strip() == "```" and in_csv:
                in_csv = False
                continue
                
            if in_csv and line.strip():
                final_csv_lines.append(line.strip())

    out_file = os.path.join(target_dir, "Final_NBA_Report.csv")
    with open(out_file, "w") as f:
        f.write("\n".join(final_csv_lines))
        
    print(f"✅ Successfully compiled {len(final_csv_lines)-1} recommendations into {out_file}.")
    print("📲 Prepping Telegram Push Format...")
    # Mocking push info
    print("\n---\n🏀 **NBA Wong Choi Final Verdict** 🏀\n" + "\n".join(final_csv_lines[1:]) + "\n---")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--target_dir', type=str, required=True, help="Directory containing Analysis.md files")
    args = parser.parse_args()
    
    compile_reports(args.target_dir)
