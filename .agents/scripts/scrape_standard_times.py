#!/usr/bin/env python3
"""
scrape_standard_times.py — Claw Code 標準時間抓取器

Usage:
    python3 scrape_standard_times.py [--output standard_times.json]

Extracts HKJC official standard times + reference sectionals from:
    https://racing.hkjc.com/zh-hk/local/page/racing-course-time

Strategy (Claw Code):
    1. curl_cffi GET → raw HTML (bypasses anti-bot)
    2. Playwright local file hydration → extract __next_f RSC chunks
    3. Parse sectionalData JSON → structured output
"""
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import re
import json
import argparse
import tempfile
from pathlib import Path
from datetime import datetime


URL = "https://racing.hkjc.com/zh-hk/local/page/racing-course-time"

# Venue mapping
VENUE_MAP = {
    "沙田草地跑道": ("沙田", "sha_tin_turf"),
    "跑馬地草地跑道": ("跑馬地", "happy_valley_turf"),
    "沙田全天候跑道": ("沙田AWT", "sha_tin_awt"),
}

# Class mapping
CLASS_MAP = {
    "GroupRace": "G", "分級賽": "G",
    "Class1": "C1", "第一班": "C1",
    "Class2": "C2", "第二班": "C2",
    "Class3": "C3", "第三班": "C3",
    "Class4": "C4", "第四班": "C4",
    "Class5": "C5", "第五班": "C5",
    "GriffinRace": "GR", "新馬賽": "GR",
}


def fetch_and_extract() -> dict:
    """Fetch HTML via curl_cffi, extract sectionalData via Playwright."""
    from curl_cffi import requests as cffi_requests
    from playwright.sync_api import sync_playwright

    # Step 1: curl_cffi fetch
    print(f"[Claw Code] Fetching {URL} ...")
    resp = cffi_requests.get(URL, impersonate="chrome120", timeout=30)
    resp.raise_for_status()
    html = resp.text
    print(f"[OK] Got {len(html)} bytes")

    # Step 2: Save to temp file for Playwright
    tmp = Path(tempfile.gettempdir()) / "hkjc_std_times.html"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(html)

    # Step 3: Playwright hydration — extract sectionalData from RSC
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{tmp}")
        page.wait_for_timeout(1500)

        # Extract the RSC chunk containing sectionalData
        raw = page.evaluate('''() => {
            if (!window.__next_f) return null;
            for (let item of window.__next_f) {
                if (item[0] === 1 && typeof item[1] === "string" && item[1].includes("sectionalData")) {
                    return item[1];
                }
            }
            return null;
        }''')
        browser.close()

    if not raw:
        raise ValueError("sectionalData not found in __next_f")

    # Step 4: Parse JSON from RSC chunk
    # The chunk format is: 26:["$","$L27","1",{"sectionalData":{...},...}]
    # We need to extract the sectionalData object
    idx = raw.find('"sectionalData":')
    if idx < 0:
        raise ValueError("sectionalData key not found in chunk")

    # Find the opening brace of sectionalData value
    brace_start = raw.index('{', idx + len('"sectionalData":'))

    # Bracket-match to find the complete object
    depth = 0
    for i in range(brace_start, len(raw)):
        if raw[i] == '{':
            depth += 1
        elif raw[i] == '}':
            depth -= 1
            if depth == 0:
                json_str = raw[brace_start:i + 1]
                return json.loads(json_str)

    raise ValueError("Unterminated sectionalData JSON")


def parse_time(s: str) -> float:
    """Convert 'M.SS.CC' to seconds. Returns 0 for '-' or empty."""
    if not s or s.strip() in ('-', ''):
        return 0.0
    m = re.match(r'^(\d+)\.(\d{2})\.(\d{2})$', s.strip())
    if m:
        return int(m.group(1)) * 60 + int(m.group(2)) + int(m.group(3)) / 100
    return 0.0


def build_output(data: dict) -> dict:
    """Convert sectionalData into structured JSON."""
    result = {
        "meta": {
            "source": URL,
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "standard_times": {},
        "reference_sectionals": {"venues": {}},
    }

    # Update date
    ts = data.get("updateDate", {}).get("dateValue", 0)
    if ts:
        result["meta"]["update_date"] = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")

    for venue_node in data.get("children", []):
        title = venue_node.get("displayTitle", {}).get("value", "")
        if title not in VENUE_MAP:
            continue
        venue_cn, venue_key = VENUE_MAP[title]
        ref_venue = result["reference_sectionals"]["venues"].setdefault(venue_key, {})

        for dist_node in venue_node.get("children", []):
            distance = dist_node.get("distance", {}).get("value", "")
            if not distance:
                continue
            ref_dist = ref_venue.setdefault(distance, {})

            for cls_node in dist_node.get("children", []):
                cls_info = cls_node.get("class", {}).get("targetItem", {})
                cls_val = cls_info.get("optionValue", {}).get("value", "")
                cls_key = CLASS_MAP.get(cls_val, "")
                if not cls_key:
                    continue

                # Standard time
                std = parse_time(cls_node.get("standardTimes", {}).get("value", "-"))
                if std > 0:
                    result["standard_times"][f"{venue_cn}_{distance}_{cls_key}"] = std

                # Sectional splits
                section_fields = [
                    ("start2000M", "2400-2000m"),
                    ("start201600M", "2000-1600m"),
                    ("start161200M", "1600-1200m"),
                    ("start12800M", "1200-800m"),
                    ("start8400M", "800-400m"),
                    ("start400M", "L400"),
                ]
                sections, labels = [], []
                for field, label in section_fields:
                    v = cls_node.get(field, {}).get("value", "")
                    if v and v != '-' and v != '':
                        try:
                            sections.append(float(v))
                            labels.append(label)
                        except ValueError:
                            pass

                entry = {}
                if std > 0:
                    entry["total"] = std
                if sections:
                    entry["sections"] = sections
                    entry["labels"] = labels
                if entry:
                    ref_dist[cls_key] = entry

    return result


def main():
    parser = argparse.ArgumentParser(description="Scrape HKJC Standard Times")
    parser.add_argument("--output", "-o", default=None)
    args = parser.parse_args()

    data = fetch_and_extract()
    print(f"[OK] Extracted {len(data.get('children', []))} venue groups")

    result = build_output(data)

    # Output paths
    script_dir = Path(__file__).parent
    out_path = Path(args.output) if args.output else script_dir / "hkjc_standard_times.json"
    ref_path = script_dir / "hkjc_reference_sectionals.json"

    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    with open(ref_path, 'w', encoding='utf-8') as f:
        json.dump(result["reference_sectionals"], f, ensure_ascii=False, indent=2)

    n = len(result["standard_times"])
    print(f"[DONE] {n} standard times → {out_path.name}")
    print(f"       Reference sectionals → {ref_path.name}")
    for k, v in list(result["standard_times"].items())[:5]:
        print(f"  {k}: {v}s")


if __name__ == "__main__":
    main()
