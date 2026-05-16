import os
import json
import re
import asyncio
import sys
import argparse
from playwright.async_api import async_playwright

# Ensure UTF-8 output for Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

CACHE_PATH = 'scratch/horse_metadata_cache.json'
BASE_DIR = 'archive race analysis'
CONCURRENCY = 2  # Reduced for stability on local machine during search flow
REQUIRED_FIELDS = ("sire", "dam", "dam_sire", "origin", "import_type")

def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8-sig') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_known(value):
    if value is None:
        return False
    return str(value).strip() not in {"", "Unknown", "None", "null"}


def has_complete_metadata(meta):
    if not isinstance(meta, dict):
        return False
    if meta.get('status') == 'no_data':
        return True
    return all(is_known(meta.get(field)) for field in REQUIRED_FIELDS)


def load_debut_horse_ids():
    import csv

    path = 'archive race analysis/comprehensive_stats/Full/race_results_Full.csv'
    first_seen = {}
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = sorted(
            csv.DictReader(f),
            key=lambda row: (
                row.get('Date', ''),
                int(row.get('RaceNo', '0') or 0),
                row.get('HorseID', ''),
            ),
        )
    for row in rows:
        horse_id = (row.get('HorseID') or '').strip()
        if horse_id and horse_id not in first_seen:
            first_seen[horse_id] = True
    return set(first_seen.keys())


def parse_text_field(text, patterns):
    for pattern in patterns:
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            value = match.group(1).strip()
            if is_known(value):
                return value
    return None

async def fetch_horse_meta(context, horse_id):
    # Use the search page to find the horse by brand number
    search_url = "https://racing.hkjc.com/zh-hk/local/information/selecthorse"
    page = await context.new_page()
    
    try:
        await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")
        
        # Fill the brand number in the "烙號" box
        try:
            await page.wait_for_selector('input[type="text"]', timeout=10000)
            
            # Use evaluate to find the correct input more reliably
            await page.evaluate("""(hid) => {
                const cells = Array.from(document.querySelectorAll('td'));
                for (const cell of cells) {
                    if (cell.innerText.includes('烙號')) {
                        const radio = cell.querySelector('input[type="radio"][value="1"]') || 
                                      Array.from(cell.querySelectorAll('input[type="radio"]'))[1];
                        const textbox = cell.querySelector('input[name="brandno"]') || 
                                        Array.from(cell.querySelectorAll('input[type="text"]'))[1];
                        const btn = cell.querySelector('input[type="button"], button, .search_button');
                        
                        if (radio) radio.click();
                        if (textbox) textbox.value = hid;
                        if (btn) btn.click();
                        return;
                    }
                }
            }""", horse_id)
            
        except Exception as e:
            print(f"[{horse_id}] Search input failed: {str(e)[:50]}")
            await page.close()
            return None

        # Wait for redirect and data table
        try:
            # Wait for either the horse profile table or "No data"
            await page.wait_for_function("""() => {
                return document.querySelector('table.horse_coreinfo') || 
                       document.body.innerText.includes('沒有相關資料');
            }""", timeout=15000)
        except:
            pass
            
        content = await page.content()
        page_text = await page.locator("body").inner_text()
        if "沒有相關資料" in content or "沒有相關資料" in page_text:
            print(f"[{horse_id}] No data found (Search result).")
            await page.close()
            return {'id': horse_id, 'status': 'no_data'}

        if '父系' not in page_text and '外祖父' not in page_text:
            horseid_match = re.search(
                rf'horseid=(HK_\d{{4}}_{re.escape(horse_id)})',
                content,
                re.IGNORECASE,
            )
            if horseid_match:
                profile_url = (
                    "https://racing.hkjc.com/zh-hk/local/information/"
                    f"performance?horseid={horseid_match.group(1)}"
                )
                await page.goto(profile_url, timeout=60000, wait_until="domcontentloaded")
                content = await page.content()
                page_text = await page.locator("body").inner_text()

        meta = {
            'id': horse_id,
            'origin': parse_text_field(page_text, [
                r'出生地\s*/\s*馬齡\s*:\s*([^\n/]+)',
                r'出生地\s*:\s*([^\n]+)',
            ]),
            'import_type': parse_text_field(page_text, [
                r'進口類別\s*:\s*([^\n]+)',
            ]),
            'sire': parse_text_field(page_text, [
                r'父系\s*:\s*([^\n]+)',
            ]),
            'dam': parse_text_field(page_text, [
                r'母系\s*:\s*([^\n]+)',
            ]),
            'dam_sire': parse_text_field(page_text, [
                r'外祖父\s*:\s*([^\n]+)',
            ]),
        }

        await page.close()
        if has_complete_metadata(meta):
            print(f"[{horse_id}] Found: {meta.get('sire')}", flush=True)
            return meta
        else:
            compact = {k: v for k, v in meta.items() if k != 'id' and is_known(v)}
            print(f"[{horse_id}] Found profile but incomplete metadata: {compact}", flush=True)
            return meta
            
    except Exception as e:
        print(f"[{horse_id}] Error: {str(e)[:50]}...", flush=True)
        await page.close()
        return None

async def sync_all():
    parser = argparse.ArgumentParser(description="Sync HKJC horse pedigree/origin metadata.")
    parser.add_argument('--debut-only', action='store_true', help='Only fetch metadata for debut horses from Full race results.')
    parser.add_argument('--limit', type=int, default=0, help='Optional max number of horses to fetch this run.')
    parser.add_argument('--concurrency', type=int, default=CONCURRENCY, help='Concurrent browser pages.')
    parser.add_argument('--force-refresh', action='store_true', help='Refresh even if cache entry looks complete.')
    parser.add_argument('--horse-id', action='append', default=[], help='Specific horse ID(s) to refresh.')
    args = parser.parse_args()

    cache = load_json(CACHE_PATH)
    all_horse_ids = set()

    if args.horse_id:
        all_horse_ids.update(hid.strip().upper() for hid in args.horse_id if hid.strip())
        print(f"Using {len(all_horse_ids)} horse IDs passed via --horse-id.", flush=True)
    elif args.debut_only:
        print("Loading debut horse IDs from Full race results...", flush=True)
        all_horse_ids = load_debut_horse_ids()
        print(f"Found {len(all_horse_ids)} debut horse IDs.", flush=True)
    else:
        print("Scanning race results for horse IDs...", flush=True)
        for root, dirs, files in os.walk(BASE_DIR):
            if 'comprehensive_stats' in root:
                continue
            for file in files:
                if file.endswith('.json'):
                    path = os.path.join(root, file)
                    try:
                        data = load_json(path)
                        for race in data.values():
                            for h in race.get('results', []):
                                name = h.get('horse_name', '')
                                match = re.search(r'\(([A-Z]\d+)\)', name)
                                if match:
                                    all_horse_ids.add(match.group(1))
                    except Exception:
                        pass
        print(f"Found {len(all_horse_ids)} unique horses in archives.", flush=True)

    if args.force_refresh:
        missing = sorted(all_horse_ids)
    else:
        missing = sorted(
            hid for hid in all_horse_ids
            if hid not in cache or not has_complete_metadata(cache.get(hid))
        )

    if args.limit and args.limit > 0:
        missing = missing[:args.limit]
    print(f"Missing or incomplete metadata for {len(missing)} horses.", flush=True)

    if not missing:
        print("Metadata cache is up to date.", flush=True)
        return

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        chunk_size = max(1, args.concurrency)
        for i in range(0, len(missing), chunk_size):
            chunk = missing[i:i + chunk_size]
            tasks = [fetch_horse_meta(context, hid) for hid in chunk]
            results = await asyncio.gather(*tasks)

            for hid, meta in zip(chunk, results):
                if meta:
                    cache[hid] = meta

            # Save every chunk
            save_json(CACHE_PATH, cache)
            print(f"Progress: {i + len(chunk)}/{len(missing)} horses processed.", flush=True)
            # Small break between chunks
            await asyncio.sleep(0.5)

        await browser.close()

    print(f"✅ Sync Complete. Total cache size: {len(cache)}", flush=True)

if __name__ == '__main__':
    asyncio.run(sync_all())
