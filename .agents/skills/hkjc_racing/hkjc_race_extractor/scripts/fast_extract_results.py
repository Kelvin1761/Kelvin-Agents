#!/usr/bin/env python3
"""
HKJC Fast Race Results Extractor — Claw Code Architecture (curl_cffi + BS4).

Uses curl_cffi with TLS impersonation to bypass anti-bot protections and
BeautifulSoup to parse the server-side rendered HTML. No Playwright or
headless browser needed — HKJC embeds full race data in SSR HTML.

Architecture:
  1. curl_cffi (chrome120 impersonation) → download raw HTML rapidly
  2. BS4 → parse structured data from SSR tables
  3. Output JSON + Markdown

Usage:
    python fast_extract_results.py --date 2026/04/19 --venue ST --races "1-11" --output_dir "/path/to/output"
    python fast_extract_results.py --base_url "URL" --races "1-11" --output_dir "/path/to/output"
"""
import os
import sys
import re
import json
import argparse
import time
from urllib.parse import urlparse, parse_qs

# Ensure UTF-8 output
os.environ.setdefault('PYTHONUTF8', '1')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def fetch_page_html(url):
    """Download raw HTML using curl_cffi to bypass anti-bot (Claw Code Step 1)."""
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30)
        if resp.status_code == 200:
            return resp.text
        else:
            print(f"  ⚠️ curl_cffi returned status {resp.status_code}", file=sys.stderr)
    except ImportError:
        print("  ⚠️ curl_cffi not available, falling back to urllib", file=sys.stderr)
    except Exception as e:
        print(f"  ⚠️ curl_cffi failed: {e}, falling back to urllib", file=sys.stderr)

    # Fallback: standard urllib with browser-like headers
    import urllib.request
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                       'AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode('utf-8')


def extract_race_data(html_text, race_no):
    """
    Extract all structured data from HKJC SSR HTML (Claw Code Step 2).

    HKJC race results page contains 6 tables:
      Table 0: Venue/track config
      Table 1: Race info (class, distance, going, times)
      Table 2: Results table (positions, horses, jockeys, etc.)
      Table 3: Dividends/payouts
      Table 4: Incident reports (競賽事件報告)
      Table 5: Bloodline info
    """
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html_text, 'html.parser')

    result = {
        'race_no': race_no,
        'class_info': '',
        'distance': '',
        'race_name': '',
        'going': '',
        'track': '',
        'win_time': '',
        'sectional_times': '',
        'cumulative_times': '',
        'results': [],
        'dividends': [],
        'incident_report': [],
        'bloodline': '',
    }

    tables = soup.find_all('table')
    if len(tables) < 3:
        print(f"  ⚠️ Race {race_no}: Only {len(tables)} tables found (expected ≥5)", file=sys.stderr)
        return result

    # ── Table 1: Race Info ──────────────────────────────────────────
    if len(tables) >= 2:
        info_text = tables[1].get_text(separator='\n', strip=True)

        # Class and distance
        class_match = re.search(r'(第[一二三四五]班|公開賽|新馬賽|獅子山錦標|[一二三]級賽)', info_text)
        if class_match:
            result['class_info'] = class_match.group(1)

        dist_match = re.search(r'(\d+)米', info_text)
        if dist_match:
            result['distance'] = dist_match.group(1) + '米'

        # Race name
        name_match = re.search(r'([\u4e00-\u9fff]+(?:讓賽|盃賽|錦標|大賽|邀請賽|挑戰賽|盃|系列賽))', info_text)
        if name_match:
            result['race_name'] = name_match.group(1)

        # Going
        going_match = re.search(r'場地狀況\s*[:：]\s*(.+?)(?:\n|$)', info_text)
        if going_match:
            result['going'] = going_match.group(1).strip()

        # Track
        track_match = re.search(r'賽道\s*[:：]\s*(.+?)(?:\n|$)', info_text)
        if track_match:
            result['track'] = track_match.group(1).strip()

        # Cumulative times e.g. (13.85) (37.29) (1:01.97)
        cum_times = re.findall(r'\(([\d:.]+)\)', info_text)
        if cum_times:
            result['cumulative_times'] = ' | '.join(f'({t})' for t in cum_times[:10])
            # Last cumulative time = win time
            if cum_times:
                result['win_time'] = cum_times[-1]

        # Sectional times
        sect_match = re.search(r'分段時間\s*[:：]\s*(.+?)(?:\n|$)', info_text)
        if sect_match:
            sect_raw = sect_match.group(1).strip()
            sect_times = re.findall(r'[\d.]+', sect_raw)
            if sect_times:
                result['sectional_times'] = ' '.join(sect_times)

    # ── Table 2: Results ────────────────────────────────────────────
    if len(tables) >= 3:
        results_table = tables[2]
        rows = results_table.find_all('tr')
        for row in rows:
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]

            # Skip header rows (first cell not a digit)
            if not cell_texts or not cell_texts[0].isdigit():
                continue

            if len(cell_texts) >= 12:
                entry = {
                    'pos': cell_texts[0],
                    'horse_no': cell_texts[1],
                    'horse_name': cell_texts[2],
                    'jockey': cell_texts[3],
                    'trainer': cell_texts[4],
                    'actual_weight': cell_texts[5],
                    'declared_weight': cell_texts[6],
                    'draw': cell_texts[7],
                    'margin': cell_texts[8],
                    'running_positions': cell_texts[9],
                    'finish_time': cell_texts[10],
                    'win_odds': cell_texts[11],
                }
                result['results'].append(entry)

    # ── Table 3: Dividends ──────────────────────────────────────────
    if len(tables) >= 4:
        div_table = tables[3]
        div_text = div_table.get_text(separator='\n', strip=True)
        # Extract dividend info as raw text (structured enough for reports)
        result['dividends_raw'] = div_text

    # ── Table 4: Incident Report (競賽事件報告) ─────────────────────
    if len(tables) >= 5:
        incident_table = tables[4]
        inc_rows = incident_table.find_all('tr')
        for row in inc_rows:
            cells = row.find_all(['td', 'th'])
            cell_texts = [c.get_text(strip=True) for c in cells]

            # Skip header rows
            if not cell_texts or not cell_texts[0].isdigit():
                continue

            if len(cell_texts) >= 4:
                incident = {
                    'pos': cell_texts[0],
                    'horse_no': cell_texts[1],
                    'horse_name': cell_texts[2],
                    'comment': cell_texts[3],
                }
                result['incident_report'].append(incident)

    # ── Table 5: Bloodline ──────────────────────────────────────────
    if len(tables) >= 6:
        blood_text = tables[5].get_text(separator='\n', strip=True)
        result['bloodline'] = blood_text

    return result


def format_race_markdown(data):
    """Format a single race result into markdown."""
    lines = [
        f"## 第 {data['race_no']} 場",
        f"- **班次:** {data.get('class_info', '')}",
        f"- **路程:** {data.get('distance', '')}",
        f"- **賽事名稱:** {data.get('race_name', '')}",
        f"- **場地狀況:** {data.get('going', '')}",
        f"- **賽道:** {data.get('track', '')}",
        f"- **完成時間:** {data.get('win_time', '')}",
        f"- **分段時間:** {data.get('sectional_times', '')}",
        f"- **累計時間:** {data.get('cumulative_times', '')}",
        "",
        "### 📊 賽果",
        "",
        "| 名次 | 馬號 | 馬名 | 騎師 | 練馬師 | 負磅 | 體重 | 檔位 | 距離 | 走位 | 時間 | 賠率 |",
        "|:---:|:---:|:---|:---|:---|:---:|:---:|:---:|:---:|:---|:---:|:---:|",
    ]

    for r in data.get('results', []):
        lines.append(
            f"| {r.get('pos','')} "
            f"| {r.get('horse_no','')} "
            f"| {r.get('horse_name','')} "
            f"| {r.get('jockey','')} "
            f"| {r.get('trainer','')} "
            f"| {r.get('actual_weight','')} "
            f"| {r.get('declared_weight','')} "
            f"| {r.get('draw','')} "
            f"| {r.get('margin','')} "
            f"| {r.get('running_positions','')} "
            f"| {r.get('finish_time','')} "
            f"| {r.get('win_odds','')} |"
        )

    # Incident report
    if data.get('incident_report'):
        lines.extend(["", "### 📋 競賽事件報告", ""])
        lines.append("| 名次 | 馬號 | 馬名 | 事件 |")
        lines.append("|:---:|:---:|:---|:---|")
        for inc in data['incident_report']:
            comment = inc.get('comment', '')
            # Truncate very long comments for readability
            if len(comment) > 200:
                comment = comment[:200] + '...'
            lines.append(
                f"| {inc.get('pos','')} "
                f"| {inc.get('horse_no','')} "
                f"| {inc.get('horse_name','')} "
                f"| {comment} |"
            )

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description="HKJC Fast Race Results Extractor (Claw Code)")
    parser.add_argument("--base_url", help="Full HKJC results URL (auto-detect date/venue)")
    parser.add_argument("--date", help="Race date in YYYY/MM/DD format")
    parser.add_argument("--venue", default="ST", help="ST (Sha Tin) or HV (Happy Valley)")
    parser.add_argument("--races", required=True, help="Race range e.g. '1-11' or '1,3,5'")
    parser.add_argument("--output_dir", required=True, help="Output directory")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests (seconds)")
    args = parser.parse_args()

    # Determine date and venue
    if args.base_url:
        parsed = urlparse(args.base_url)
        qs = parse_qs(parsed.query)
        date = qs.get('racedate', [args.date])[0] if 'racedate' in qs else args.date
        venue = qs.get('Racecourse', [args.venue])[0] if 'Racecourse' in qs else args.venue
    else:
        date = args.date
        venue = args.venue

    if not date:
        print("❌ Must provide either --base_url or --date", file=sys.stderr)
        sys.exit(1)

    # Parse race range
    r_match = re.match(r'(\d+)-(\d+)', args.races)
    if r_match:
        race_list = list(range(int(r_match.group(1)), int(r_match.group(2)) + 1))
    else:
        race_list = [int(r.strip()) for r in args.races.split(',')]

    os.makedirs(args.output_dir, exist_ok=True)

    venue_cn = '沙田' if venue == 'ST' else '跑馬地'
    date_parts = date.split('/')
    date_prefix = f"{date_parts[1]}-{date_parts[2]}" if len(date_parts) == 3 else "00-00"

    print(f"🏇 Claw Code Extractor: {date} {venue_cn} (Races {args.races})")
    print(f"   Architecture: curl_cffi (chrome120) + BS4")
    print()

    all_results = {}
    success_count = 0

    for race_no in race_list:
        url = (
            f"https://racing.hkjc.com/zh-hk/local/information/localresults"
            f"?racedate={date}&Racecourse={venue}&RaceNo={race_no}"
        )
        print(f"  📥 Race {race_no}...", end=" ", flush=True)

        try:
            html_text = fetch_page_html(url)

            if not html_text:
                print("❌ Empty response")
                continue

            result = extract_race_data(html_text, race_no)

            if result and result.get('results'):
                all_results[race_no] = result
                success_count += 1
                n_runners = len(result['results'])
                n_incidents = len(result.get('incident_report', []))
                winner = result['results'][0]['horse_name'] if result['results'] else '?'
                print(f"✅ {n_runners} runners | Winner: {winner} | {n_incidents} incidents")
            else:
                print("⚠️ No result data extracted")

            # Polite delay between requests
            if race_no != race_list[-1]:
                time.sleep(args.delay)

        except Exception as e:
            print(f"❌ Error: {e}")

    # ── Write Output Files ──────────────────────────────────────────
    if not all_results:
        print("\n❌ No races extracted successfully!")
        sys.exit(1)

    # 1. JSON output (for reflector_auto_stats.py)
    json_file = os.path.join(args.output_dir, f"{date_prefix}_{venue_cn}_全日賽果.json")
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    # 2. Markdown output (for human review)
    md_file = os.path.join(args.output_dir, f"{date_prefix}_{venue_cn}_全日賽果.md")
    with open(md_file, 'w', encoding='utf-8') as f:
        f.write(f"# 🏇 HKJC 賽果報告\n")
        f.write(f"**日期:** {date} | **馬場:** {venue_cn}\n\n")

        for rno in sorted(all_results.keys()):
            f.write(format_race_markdown(all_results[rno]))
            f.write("\n\n---\n\n")

    # 3. Individual race result files (for reflector pipeline compatibility)
    for rno in sorted(all_results.keys()):
        race_file = os.path.join(
            args.output_dir,
            f"{date_prefix}_{venue_cn}_Race_{rno}_Results.md"
        )
        with open(race_file, 'w', encoding='utf-8') as f:
            f.write(format_race_markdown(all_results[rno]))

    print(f"\n📊 提取完成: {success_count}/{len(race_list)} 場")
    print(f"   JSON: {json_file}")
    print(f"   Markdown: {md_file}")
    print(f"   個別賽果: {args.output_dir}/{date_prefix}_{venue_cn}_Race_*_Results.md")


if __name__ == "__main__":
    main()
