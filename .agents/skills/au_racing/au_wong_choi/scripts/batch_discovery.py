import os
import sys
import re
import json
import time
import argparse
from datetime import datetime
from playwright.sync_api import sync_playwright

def get_track_slug(track_name):
    """Normalize track name to Racenet slug format."""
    return track_name.lower().replace(" ", "-")

def discover_meetings(track_slug, start_date_str="2025-08-01"):
    """Discover all meeting URLs for a track since start_date."""
    url = f"https://www.racenet.com.au/results/horse-racing/{track_slug}"
    print(f"🔍 Searching meetings for {track_slug} at {url}...")
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
    meetings = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a more realistic browser context
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = context.new_page()
        
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            
            # Extract year links
            years_to_check = ["2026", "2025"]
            
            for year in years_to_check:
                print(f"  📅 Checking year {year}...")
                
                # Check if year is already active or needs clicking
                year_btn = page.locator(f"a:has-text('{year}'), button:has-text('{year}'), span:has-text('{year}')").first
                if year_btn.count() > 0:
                    try:
                        year_btn.click(timeout=5000)
                        page.wait_for_load_state("networkidle")
                        page.wait_for_timeout(2000)
                    except:
                        print(f"    ⚠️ Could not click year {year}, it might already be active.")
                
                # Debug: Save snapshot of the links area
                # page.screenshot(path=f".scratch/discovery_{track_slug}_{year}.png")
                
                # Get all links
                links = page.evaluate('''() => {
                    return Array.from(document.querySelectorAll('a'))
                        .map(a => a.href)
                        .filter(href => href.includes('/results/horse-racing/') && href.includes('/all-races'));
                }''')
                
                print(f"    🔎 Found {len(links)} raw links for {year}")
                
                if len(links) == 0:
                    html_dump = page.content()
                    with open(f".scratch/debug_{track_slug}_{year}.html", "w", encoding="utf-8") as f:
                        f.write(html_dump)
                    print(f"    ⚠️ No links found. HTML dumped to .scratch/debug_{track_slug}_{year}.html")
                
                for href in links:
                    # Pattern: /results/horse-racing/flemington-20260425/all-races
                    match = re.search(r'/([^/]+)-(\d{8})/all-races', href)
                    if match:
                        slug = match.group(1)
                        date_raw = match.group(2)
                        
                        # Validate track slug matches
                        if track_slug not in slug:
                            continue
                            
                        date_obj = datetime.strptime(date_raw, "%Y%m%d")
                        if date_obj >= start_date:
                            full_url = href if href.startswith('http') else f"https://www.racenet.com.au{href}"
                            if full_url not in [m['url'] for m in meetings]:
                                meetings.append({
                                    'track': track_slug,
                                    'date': date_obj.strftime("%Y-%m-%d"),
                                    'url': full_url
                                })
                                print(f"    ✅ Found: {date_obj.strftime('%Y-%m-%d')}")

        except Exception as e:
            print(f"  ❌ Error discoverying {track_slug}: {e}")
        finally:
            browser.close()
            
    return meetings

def main():
    parser = argparse.ArgumentParser(description="AU Meeting Discovery Script")
    parser.add_argument("--tracks", type=str, help="Comma-separated track slugs")
    parser.add_argument("--output", type=str, default="discovered_meetings.json", help="Output JSON file")
    args = parser.parse_args()

    target_tracks = [
        "randwick", "flemington", "warwick-farm", "cranbourne", 
        "pakenham", "ascot", "sale", "caulfield", "moonee-valley"
    ]
    if args.tracks:
        target_tracks = [t.strip() for t in args.tracks.split(",")]

    all_discovered = []
    for track in target_tracks:
        meetings = discover_meetings(track)
        all_discovered.extend(meetings)
        time.sleep(2) # Avoid aggressive crawling

    # Sort by date descending
    all_discovered.sort(key=lambda x: x['date'], reverse=True)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(all_discovered, f, indent=2)

    print(f"\n✨ Discovery complete! Total {len(all_discovered)} meetings found.")
    print(f"📂 List saved to: {args.output}")

if __name__ == "__main__":
    main()
