#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
claw_profile_scraper.py — Racenet Profile (Form) Scraper
======================================================
Inputs: Comma-separated list of horse slugs or names
Outputs: JSON representing the 'SelectionResult' runs for each horse.

Uses curl_cffi to bypass Cloudflare and a single Playwright instance
to decode __NUXT__ state for rapid offline evaluation.

V2 Update (2026-04-08):
  - Graceful dependency handling (curl_cffi, playwright)
  - Adds placing data (Top-3 detection) to output
  - Adds venue-based class inference (Metro/Provincial)
"""

import io
import json
import argparse
import re
from pathlib import Path

# Graceful dependency check
_DEPS_OK = True
_DEP_ERROR = ""
try:
    from curl_cffi import requests as cffi_requests
except ImportError:
    _DEPS_OK = False
    _DEP_ERROR = "curl_cffi not installed (pip install curl-cffi)"

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    _DEPS_OK = False
    _DEP_ERROR = "playwright not installed (pip install playwright && playwright install chromium)"

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Metro venue set for class inference
METRO_VENUES = {
    'randwick', 'rosehill', 'flemington', 'caulfield', 'moonee valley',
    'eagle farm', 'doomben', 'sandown', 'canterbury', 'warwick farm',
    'cranbourne', 'morphettville', 'ascot', 'belmont'
}


def build_slug(name: str) -> str:
    """Safely convert 'Hot Sand' to 'hot-sand'"""
    clean_name = re.sub(r'\s*\([^)]+\)', '', name)
    return re.sub(r'[^a-z0-9]+', '-', clean_name.lower().strip()).strip('-')


def infer_class(venue: str) -> str:
    """Infer race class from venue name (Metro vs Provincial)."""
    if not venue:
        return '-'
    v_lower = venue.lower().strip()
    for metro in METRO_VENUES:
        if metro in v_lower:
            return 'Metro'
    return '省賽'


def scrape_profiles(slugs: list[str]) -> dict:
    if not _DEPS_OK:
        return {slug: {"error": _DEP_ERROR} for slug in slugs}

    results = {}
    temp_html_path = os.path.abspath('temp_profile.html')
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for slug in slugs:
                if not slug:
                    continue
                    
                url = f"https://www.racenet.com.au/horse/{slug}"
                try:
                    res = cffi_requests.get(url, impersonate="chrome110", timeout=15)
                except Exception as e:
                    results[slug] = {"error": f"HTTP request failed: {e}"}
                    continue
                
                if res.status_code != 200:
                    results[slug] = {"error": f"HTTP {res.status_code}"}
                    continue
                    
                with open(temp_html_path, 'w', encoding='utf-8') as f:
                    f.write(res.text)
                    
                try:
                    page.goto(f"file://{temp_html_path}")
                    nuxt = page.evaluate("() => window.__NUXT__")
                    if not nuxt:
                        results[slug] = {"error": "No NUXT state found"}
                        continue
                        
                    apollo = nuxt.get('apollo', {}).get('defaultClient', {})
                    
                    runs = []
                    for k, v in apollo.items():
                        if k.startswith("SelectionResult:"):
                            r_date = v.get('meetingDate', '')
                            if r_date:
                                finish = v.get('finishPosition', None)
                                venue = v.get('meetingName', '')
                                runs.append({
                                    'date': r_date[:10],
                                    'date_full': r_date,
                                    'venue': venue,
                                    'finish': finish,
                                    'starters': v.get('eventStarters', None),
                                    'is_placed': finish is not None and 1 <= finish <= 3,
                                    'class': infer_class(venue),
                                })
                                
                    runs.sort(key=lambda x: x['date'], reverse=True)
                    results[slug] = {"runs": runs}
                    
                except Exception as e:
                    results[slug] = {"error": str(e)}
                    
            browser.close()
    except Exception as e:
        # Playwright launch failure
        return {slug: {"error": f"Playwright launch failed: {e}"} for slug in slugs}
        
    if os.path.exists(temp_html_path):
        os.remove(temp_html_path)
        
    return results

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--slugs', required=False, help="Comma separated horse slugs")
    parser.add_argument('--names', required=False, help="Comma separated horse names (will be auto-slugified)")
    args = parser.parse_args()
    
    target_slugs = []
    if args.slugs:
        target_slugs.extend([s.strip() for s in args.slugs.split(',') if s.strip()])
    if args.names:
        target_slugs.extend([build_slug(n) for n in args.names.split(',') if n.strip()])
        
    if not target_slugs:
        print(json.dumps({"error": "No slugs provided"}))
        sys.exit(1)
        
    out = scrape_profiles(target_slugs)
    print(json.dumps(out, ensure_ascii=False))
