#!/usr/bin/env python3
import os
import sys
import re
import glob
import pandas as pd
import io

def generate_reports(target_dir):
    """
    Reads all Race_X_Analysis.txt files in the given directory.
    Extracts the CSV blocks from the ends to compile an Excel file.
    Skips DOCX generation as user requested txt is fine.
    """
    if not os.path.exists(target_dir):
        print(f"Error: Directory {target_dir} does not exist.")
        sys.exit(1)

    analysis_dir = os.path.join(target_dir, "Race Analysis")
    if not os.path.exists(analysis_dir):
        print(f"Error: Directory {analysis_dir} does not exist. No analysis files to process.")
        sys.exit(1)

    files = glob.glob(os.path.join(analysis_dir, "*Race_*_Analysis.txt"))
    files.extend(glob.glob(os.path.join(analysis_dir, "*Race * Analysis.txt")))
    files.extend(glob.glob(os.path.join(analysis_dir, "*Race_*_Analysis.md")))
    files.extend(glob.glob(os.path.join(analysis_dir, "*Race * Analysis.md")))
    files = list(dict.fromkeys(files))  # deduplicate preserving order

    if not files:
        print(f"No Race Analysis files found in {analysis_dir}.")
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generate_reports.py <target_directory_path>")
        sys.exit(1)

    target = sys.argv[1]
    generate_reports(target)
