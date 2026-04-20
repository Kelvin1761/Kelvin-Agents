#!/usr/bin/env python3
"""
scrape_draw_stats.py — Claw Code 檔位統計抓取器

Usage:
    python3 scrape_draw_stats.py [--output draw_stats.json]

Extracts draw statistics from:
    https://racing.hkjc.com/zh-hk/local/information/draw

Data is inline HTML tables (ASP.NET SSR). Each race has:
    檔位, 出賽次數, 冠, 亞, 季, 殿, 勝出率%, 入Q率%, 上名率%, 前4名率%
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import re
import json
import argparse
from pathlib import Path
from datetime import datetime
from bs4 import BeautifulSoup


URL = "https://racing.hkjc.com/zh-hk/local/information/draw"


def fetch_html() -> str:
    """Fetch draw stats page via curl_cffi."""
    from curl_cffi import requests as cffi_requests
    print(f"[Claw Code] Fetching {URL} ...")
    resp = cffi_requests.get(URL, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    print(f"[OK] Got {len(resp.text)} bytes")
    return resp.text


def parse_race_header(header_text: str) -> dict:
    """Parse '第 1 場      1200米      草地      "B" 賽道' into structured info."""
    header_text = re.sub(r'\xa0+', ' ', header_text).strip()
    info = {}

    # Race number
    m = re.search(r'第\s*(\d+)\s*場', header_text)
    if m:
        info['race'] = int(m.group(1))

    # Distance
    m = re.search(r'(\d{3,4})\s*米', header_text)
    if m:
        info['distance'] = int(m.group(1))

    # Surface
    if '草地' in header_text:
        info['surface'] = '草地'
    elif '全天候' in header_text:
        info['surface'] = '全天候'

    # Course
    m = re.search(r'"([A-Z]+)"\s*賽道', header_text)
    if m:
        info['course'] = m.group(1)

    return info


def parse_draw_tables(html: str) -> dict:
    """Parse all draw statistics tables from HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    tables = soup.find_all('table')

    # Extract meeting info from first table
    meeting_info = ""
    if tables:
        first_header = tables[0].get_text(strip=True) if tables[0] else ""
        # e.g. "22/04/2026跑馬地"
        m = re.search(r'(\d{2}/\d{2}/\d{4})(.*?)進階', first_header)
        if m:
            meeting_info = f"{m.group(1)} {m.group(2).strip()}"

    result = {
        "meta": {
            "source": URL,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "meeting": meeting_info,
        },
        "races": []
    }

    for table in tables:
        rows = table.find_all('tr')
        if len(rows) < 3:
            continue

        # Check if first row is a race header
        first_row_text = rows[0].get_text(strip=True)
        if '場' not in first_row_text or '米' not in first_row_text:
            continue

        # Parse race header
        race_info = parse_race_header(first_row_text)
        if 'race' not in race_info:
            continue

        # Second row should be column headers
        header_cells = rows[1].find_all(['th', 'td'])
        headers = [c.get_text(strip=True) for c in header_cells]

        # Parse data rows (row 2 onwards)
        draws = []
        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) < 7:
                continue
            vals = [c.get_text(strip=True) for c in cells]
            try:
                draw_entry = {
                    "draw": int(vals[0]),
                    "starts": int(vals[1]),
                    "wins": int(vals[2]),
                    "seconds": int(vals[3]),
                    "thirds": int(vals[4]),
                    "fourths": int(vals[5]),
                    "win_pct": float(vals[6]),
                }
                if len(vals) > 7:
                    draw_entry["quinella_pct"] = float(vals[7])
                if len(vals) > 8:
                    draw_entry["place_pct"] = float(vals[8])
                if len(vals) > 9:
                    draw_entry["top4_pct"] = float(vals[9])
                draws.append(draw_entry)
            except (ValueError, IndexError):
                continue

        if draws:
            # Calculate average win rate for this race's distance/surface
            avg_win = sum(d["win_pct"] for d in draws) / len(draws) if draws else 0

            # Classify each draw: ✅有利 / ⚠️中性 / ❌不利
            for d in draws:
                if avg_win > 0:
                    ratio = d["win_pct"] / avg_win
                    if ratio >= 1.5:
                        d["verdict"] = "✅有利"
                    elif ratio <= 0.5:
                        d["verdict"] = "❌不利"
                    else:
                        d["verdict"] = "⚠️中性"
                else:
                    d["verdict"] = "⚠️中性"

            race_info["avg_win_pct"] = round(avg_win, 1)
            race_info["draws"] = draws
            result["races"].append(race_info)

    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape HKJC Draw Statistics")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args()

    html = fetch_html()
    result = parse_draw_tables(html)

    # Output
    script_dir = Path(__file__).parent
    out_path = Path(args.output) if args.output else script_dir / "hkjc_draw_stats.json"

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    n_races = len(result["races"])
    meeting = result["meta"].get("meeting", "N/A")
    print(f"[DONE] {meeting} — {n_races} races extracted → {out_path.name}")
    for r in result["races"][:3]:
        best = max(r["draws"], key=lambda d: d["win_pct"])
        worst = min(r["draws"], key=lambda d: d["win_pct"])
        print(f"  Race {r['race']} ({r.get('distance','')}m): "
              f"Best=Draw {best['draw']} ({best['win_pct']}%), "
              f"Worst=Draw {worst['draw']} ({worst['win_pct']}%)")


if __name__ == "__main__":
    main()
