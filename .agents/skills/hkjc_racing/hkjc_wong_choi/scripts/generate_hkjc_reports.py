#!/usr/bin/env python3
"""
This module generates an Excel summary report from HKJC Hong Kong racing analysis text files.
It parses CSV output blocks or fallback Markdown top 4 tables from generated analysis records.
"""
import os
import sys
import re
import argparse
import pandas as pd


def _make_result_row(race_no="", distance="", jockey="", trainer="",
                     horse_no="", horse_name="", grade="",
                     race_class="", track_type=""):
    """Create a standardized result row dictionary."""
    return {
        "Date": "",
        "馬場": "",
        "賽事編號": race_no,
        "Class": race_class,
        "Range": distance,
        "Type": track_type,
        "Weather": "",
        "評級": grade,
        "Jockey": jockey,
        "Trainer": trainer,
        "Horse Number": horse_no,
        "馬匹名稱": horse_name,
    }


def parse_csv_block(content):
    """
    Primary method: Parse the CSV code block from the analysis text.
    The Analyst outputs a structured CSV at the end of each race.
    Format: Race Number, Distance, Jockey, Trainer, Horse Number, Horse Name, Grade
    """
    results = []
    csv_matches = re.findall(r'```csv\s*\n(.*?)```', content, re.DOTALL)
    for csv_text in csv_matches:
        for line in csv_text.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 7:
                # Skip header lines
                if parts[0].lower() in ("race", "horse", "number", "race number") or \
                   not parts[0].replace(" ", "").isdigit():
                    continue
                results.append(_make_result_row(
                    race_no=parts[0],
                    distance=parts[1],
                    jockey=parts[2],
                    trainer=parts[3],
                    horse_no=parts[4],
                    horse_name=parts[5],
                    grade=parts[6],
                ))
    return results


def _extract_race_specs(content):
    """
    Helper method to extract the Class, Distance, and Track Type from the Spec section.
    """
    spec_match = re.search(r'\*\*賽事規格：\*\*(.*?)\n', content)
    if spec_match:
        parts = [p.strip() for p in spec_match.group(1).split('/')]
        if len(parts) >= 4:
            return parts[1], parts[2], parts[3]
    return "", "", ""


def parse_analysis_file(file_path):
    """
    Parse a Race Analysis text file to extract the Top 4 picks.
    Tries CSV block first (primary), falls back to regex Markdown parsing.
    """
    results = []

    race_match = re.search(r'Race[_ ](\d+)', os.path.basename(file_path))
    race_no = race_match.group(1) if race_match else "Unknown"

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError as e:
        print(f"Warning: Encoding error reading {file_path}: {e}. Skipping.")
        return results

    try:
        # Try CSV block first (primary method)
        csv_results = parse_csv_block(content)
        if csv_results:
            # distance from specs ignored; CSV provides its own distance in parts[1]
            race_class, _distance, track_type = _extract_race_specs(content)
            for res in csv_results:
                if not res["Class"]:
                    res["Class"] = race_class
                if not res["Type"]:
                    res["Type"] = track_type
            return csv_results

        # Fallback: regex parsing of text Top 4 section
        race_class, distance, track_type = _extract_race_specs(content)

        # Locate the Top 4 block
        top4_match = re.search(
            r'🏆 Top 4 位置精選(.*?)(?:🔄 步速逆轉保險|🚨 緊急煞車檢查|第四部分|$)',
            content,
            re.DOTALL
        )

        if top4_match:
            top4_text = top4_match.group(1)
            pick_blocks = re.split(r'(?:🥇|🥈|🥉|🏅)\s*\*\*第[一二三四]選\*\*', top4_text)

            for block in pick_blocks[1:]:
                if not block.strip():
                    continue

                horse_match = re.search(r'-\s*\*\*馬號及馬名[：:]\*\*\s*\[?(\d+)\]?\s*(.+)', block)
                if horse_match:
                    grade = ""
                    grade_match = re.search(r'\*\*評級與.*?\*\*.*?`([^`]+)`', block)
                    if grade_match:
                        grade = grade_match.group(1).strip()

                    results.append(_make_result_row(
                        race_no=race_no,
                        distance=distance,
                        race_class=race_class,
                        track_type=track_type,
                        grade=grade,
                        horse_no=horse_match.group(1).strip(),
                        horse_name=horse_match.group(2).strip(),
                    ))

            # Attempt to find Jockey and Trainer for matched horses (fallback only)
            for res in results:
                horse_str = f"**{res['Horse Number']} {res['馬匹名稱']}**"
                escape_val = re.escape(horse_str)
                line_match = re.search(rf'{escape_val}\s*\|\s*(.+?)\s*\|\s*(.+?)\s*\|', content)
                if line_match:
                    res["Jockey"] = line_match.group(1).replace('**', '').strip()
                    res["Trainer"] = line_match.group(2).replace('**', '').strip()
        else:
            print(f"Warning: No Top 4 section found in {file_path}")

    except (IOError, OSError) as e:
        print(f"Error parsing {file_path}: {e}")

    return results


def main():
    """
    Main function to parse arguments and drive the report generation process.
    """
    parser = argparse.ArgumentParser(description="Generate Excel Report for HK Wong Choi")
    parser.add_argument("--target_dir", required=True,
                        help="Absolute path to the directory containing txt analysis files")
    parser.add_argument("--weather", default="", help="Weather/Going condition (e.g. 好地)")
    args = parser.parse_args()

    target_dir = args.target_dir
    weather = args.weather

    if not os.path.exists(target_dir):
        print(f"Error: Directory {target_dir} does not exist.")
        sys.exit(1)

    folder_name = os.path.basename(target_dir)
    parts = folder_name.split('_')
    date_str = parts[0] if len(parts) >= 2 else ""
    # Strip parenthesized suffix like "(Kelvin)" from course name
    raw_course = parts[1] if len(parts) >= 2 else ""
    course_str = re.sub(r'\s*\(.*?\)\s*$', '', raw_course).strip()

    all_rows = []

    for filename in sorted(os.listdir(target_dir)):
        if (filename.endswith(".txt") or filename.endswith(".md")) and "Analysis" in filename:
            filepath = os.path.join(target_dir, filename)
            picks = parse_analysis_file(filepath)
            all_rows.extend(picks)

    if not all_rows:
        print("Warning: No Top 4 data found in any txt files. No report generated.")
        sys.exit(0)

    try:
        all_rows.sort(key=lambda x: int(x["賽事編號"]))
    except (KeyError, ValueError, TypeError) as e:
        print(f"Warning: Could not sort by race number: {e}")

    for row in all_rows:
        row["Date"] = date_str
        row["馬場"] = course_str
        row["Weather"] = weather

    cols = [
        "Date", "馬場", "賽事編號", "Class", "Range", "Type",
        "Weather", "評級", "Jockey", "Trainer", "Horse Number", "馬匹名稱"
    ]
    df = pd.DataFrame(all_rows)[cols]

    output_xlsx = os.path.join(target_dir, f"{date_str}_{course_str}_總結表.xlsx")

    try:
        df.to_excel(output_xlsx, index=False)
        print(f"Successfully generated HKJC summary report: {output_xlsx}")
    except (IOError, OSError) as e:
        print(f"Failed to write Excel file: {e}")


if __name__ == "__main__":
    main()
