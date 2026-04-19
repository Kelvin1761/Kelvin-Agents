#!/usr/bin/env python3
import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
crawl_hkjc_jockey_trainer.py — HKJC Jockey & Trainer Stats Crawler

Claw Code architecture:
1. curl_cffi to bypass anti-bot and fetch raw HTML
2. BeautifulSoup to parse server-rendered tables
3. Fallback: Playwright local hydration for __NEXT_DATA__

Output: jockey_trainer_stats.json

Usage:
  python3 crawl_hkjc_jockey_trainer.py [--output <path>] [--season Current]

Version: 1.0.0
"""
import os, sys, io, json, re, argparse, tempfile

if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── Claw Code: curl_cffi fetch ──
def fetch_html(url, temp_dir=None):
    """Download raw HTML using curl_cffi (Claw Code pattern)."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-HK,zh;q=0.9,en;q=0.8',
        'Referer': 'https://racing.hkjc.com/',
    }
    
    try:
        from curl_cffi import requests as cffi_requests
        resp = cffi_requests.get(url, impersonate="chrome120", timeout=30, headers=headers)
        if resp.status_code == 200:
            html = resp.text
            if temp_dir:
                path = os.path.join(temp_dir, "page.html")
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(html)
                return html, path
            return html, None
        else:
            print(f"  ⚠️ HTTP {resp.status_code} for {url}")
    except ImportError:
        print("  ⚠️ curl_cffi not available, falling back to urllib")
    
    # Fallback: urllib
    import urllib.request
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            html = resp.read().decode('utf-8')
            if temp_dir:
                path = os.path.join(temp_dir, "page.html")
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(html)
                return html, path
            return html, None
    except Exception as e:
        print(f"  ❌ Fetch failed: {e}")
        return None, None


def parse_ranking_table_bs4(html, entity_type='jockey'):
    """Parse ranking table from raw HTML using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("  ⚠️ BeautifulSoup not available")
        return []
    
    soup = BeautifulSoup(html, 'html.parser')
    results = []
    
    # HKJC ranking tables typically have structured table format
    tables = soup.find_all('table')
    
    for table in tables:
        text = table.get_text()
        # Look for ranking indicators
        if any(marker in text for marker in ['Rides', '出賽次數', 'Wins', '頭馬', 'Win %', '勝出率']):
            rows = table.find_all('tr')
            header_found = False
            
            for row in rows:
                cells = row.find_all(['td', 'th'])
                cell_texts = [c.get_text(strip=True) for c in cells]
                
                # Skip header rows
                if any(h in ' '.join(cell_texts) for h in ['Rank', 'Name', '名次', '姓名']):
                    header_found = True
                    continue
                
                if not header_found:
                    continue
                
                # Parse data row — HKJC format: Rank, Name, Rides, 1st, 2nd, 3rd, 4th, Total Stakes
                if len(cell_texts) >= 5 and cell_texts[0].isdigit():
                    entry = {
                        'rank': int(cell_texts[0]),
                        'name': cell_texts[1],
                        'type': entity_type,
                    }
                    
                    # Try to extract numeric fields
                    nums = []
                    for ct in cell_texts[2:]:
                        cleaned = ct.replace(',', '').replace('$', '').replace('%', '')
                        try:
                            nums.append(float(cleaned))
                        except ValueError:
                            nums.append(0)
                    
                    if len(nums) >= 4:
                        entry['rides'] = int(nums[0])
                        entry['wins'] = int(nums[1])
                        entry['seconds'] = int(nums[2])
                        entry['thirds'] = int(nums[3])
                        if entry['rides'] > 0:
                            entry['win_rate'] = round(entry['wins'] / entry['rides'] * 100, 1)
                            entry['place_rate'] = round((entry['wins'] + entry['seconds'] + entry['thirds']) / entry['rides'] * 100, 1)
                        else:
                            entry['win_rate'] = 0.0
                            entry['place_rate'] = 0.0
                    
                    if len(nums) >= 5:
                        entry['fourths'] = int(nums[4]) if nums[4] < 1000 else 0
                    if len(nums) >= 6:
                        entry['total_stakes'] = int(nums[-1])
                    
                    results.append(entry)
            
            if results:
                break
    
    return results


def extract_via_next_data(html):
    """Try to extract data from __NEXT_DATA__ embedded in the page."""
    match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            return data
        except json.JSONDecodeError:
            pass
    return None


def extract_via_playwright_local(html_path, entity_type):
    """Fallback: Load local HTML in Playwright to extract JS-rendered data."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []
    
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{html_path}", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        
        # Try __NEXT_DATA__ first
        next_data = page.evaluate("""() => {
            if (window.__NEXT_DATA__) return window.__NEXT_DATA__;
            return null;
        }""")
        
        if next_data:
            browser.close()
            return next_data
        
        # Extract table data from rendered page
        table_data = page.evaluate("""() => {
            const results = [];
            const tables = document.querySelectorAll('table');
            for (const table of tables) {
                const text = table.textContent;
                if (text.includes('Rides') || text.includes('出賽') || text.includes('勝出')) {
                    const rows = table.querySelectorAll('tr');
                    for (const row of rows) {
                        const cells = Array.from(row.querySelectorAll('td'));
                        const texts = cells.map(c => c.textContent.trim());
                        if (texts.length >= 5 && /^\\d+$/.test(texts[0])) {
                            results.push(texts);
                        }
                    }
                }
            }
            return results;
        }""")
        
        browser.close()
        
        if table_data:
            for row in table_data:
                if len(row) >= 5:
                    try:
                        rides = int(row[2].replace(',', ''))
                        wins = int(row[3].replace(',', ''))
                        entry = {
                            'rank': int(row[0]),
                            'name': row[1],
                            'type': entity_type,
                            'rides': rides,
                            'wins': wins,
                            'win_rate': round(wins / rides * 100, 1) if rides > 0 else 0.0,
                        }
                        if len(row) >= 6:
                            entry['seconds'] = int(row[4].replace(',', ''))
                        if len(row) >= 7:
                            entry['thirds'] = int(row[5].replace(',', ''))
                        results.append(entry)
                    except (ValueError, IndexError):
                        continue
    
    return results


def crawl_rankings(entity_type='jockey', season='Current', racecourse='ALL'):
    """Crawl jockey or trainer rankings from HKJC."""
    # Try both old and new URL formats
    urls = [
        f"https://racing.hkjc.com/racing/information/english/{entity_type}/{entity_type.capitalize()}Ranking.aspx?Season={season}&View=Numbers&Racecourse={racecourse}",
        f"https://racing.hkjc.com/en-us/local/info/{entity_type}-ranking?season={season}&view=Numbers&racecourse={racecourse}",
    ]
    
    print(f"\n🏇 Crawling HKJC {entity_type} rankings (Season: {season})...")
    
    with tempfile.TemporaryDirectory() as temp_dir:
        for url in urls:
            print(f"  📥 Trying: {url}")
            html, html_path = fetch_html(url, temp_dir)
            
            if not html:
                continue
            
            # Method 1: Try __NEXT_DATA__ extraction
            next_data = extract_via_next_data(html)
            if next_data:
                print(f"  ✅ Found __NEXT_DATA__ structure")
                # Parse the Next.js data structure
                try:
                    page_props = next_data.get('props', {}).get('pageProps', {})
                    ranking_data = page_props.get('rankingData') or page_props.get('data', [])
                    if ranking_data:
                        results = []
                        for i, entry in enumerate(ranking_data):
                            results.append({
                                'rank': i + 1,
                                'name': entry.get('name', entry.get('jockeyName', entry.get('trainerName', '?'))),
                                'type': entity_type,
                                'rides': entry.get('rides', entry.get('starters', 0)),
                                'wins': entry.get('wins', entry.get('firsts', 0)),
                                'seconds': entry.get('seconds', 0),
                                'thirds': entry.get('thirds', 0),
                                'win_rate': entry.get('winPercentage', 0),
                                'total_stakes': entry.get('totalStakes', 0),
                            })
                        return results
                except Exception as e:
                    print(f"  ⚠️ __NEXT_DATA__ parse error: {e}")
            
            # Method 2: BS4 table parsing
            results = parse_ranking_table_bs4(html, entity_type)
            if results:
                print(f"  ✅ Extracted {len(results)} {entity_type}s via BS4")
                return results
            
            # Method 3: Playwright local hydration
            if html_path:
                print(f"  🔄 Trying Playwright local hydration...")
                pw_data = extract_via_playwright_local(html_path, entity_type)
                if isinstance(pw_data, dict):
                    # It's __NEXT_DATA__ from Playwright
                    try:
                        page_props = pw_data.get('props', {}).get('pageProps', {})
                        ranking_data = page_props.get('rankingData') or page_props.get('data', [])
                        if ranking_data:
                            return [{
                                'rank': i + 1,
                                'name': e.get('name', '?'),
                                'type': entity_type,
                                'rides': e.get('rides', 0),
                                'wins': e.get('wins', 0),
                                'win_rate': e.get('winPercentage', 0),
                            } for i, e in enumerate(ranking_data)]
                    except Exception:
                        pass
                elif isinstance(pw_data, list) and pw_data:
                    print(f"  ✅ Extracted {len(pw_data)} {entity_type}s via Playwright")
                    return pw_data
    
    print(f"  ❌ Failed to extract {entity_type} rankings from all URLs")
    return []


def build_lookup(jockey_data, trainer_data):
    """Build name → stats lookup dictionaries."""
    jockey_lookup = {}
    for j in jockey_data:
        name = j.get('name', '').strip()
        if name:
            jockey_lookup[name] = {
                'rank': j.get('rank', 0),
                'rides': j.get('rides', 0),
                'wins': j.get('wins', 0),
                'win_rate': j.get('win_rate', 0),
                'seconds': j.get('seconds', 0),
                'thirds': j.get('thirds', 0),
                'place_rate': j.get('place_rate', 0),
            }
    
    trainer_lookup = {}
    for t in trainer_data:
        name = t.get('name', '').strip()
        if name:
            trainer_lookup[name] = {
                'rank': t.get('rank', 0),
                'rides': t.get('rides', 0),
                'wins': t.get('wins', 0),
                'win_rate': t.get('win_rate', 0),
                'seconds': t.get('seconds', 0),
                'thirds': t.get('thirds', 0),
                'place_rate': t.get('place_rate', 0),
            }
    
    return jockey_lookup, trainer_lookup


def main():
    parser = argparse.ArgumentParser(description='HKJC Jockey & Trainer Stats Crawler (Claw Code)')
    parser.add_argument('--output', default='jockey_trainer_stats.json', help='Output JSON path')
    parser.add_argument('--season', default='Current', help='Season (Current or year)')
    parser.add_argument('--racecourse', default='ALL', help='Racecourse filter (ALL, ST, HV)')
    args = parser.parse_args()
    
    print("=" * 60)
    print("🐾 HKJC Jockey & Trainer Stats Crawler (Claw Code)")
    print("=" * 60)
    
    # Crawl jockeys
    jockey_data = crawl_rankings('jockey', args.season, args.racecourse)
    
    # Crawl trainers
    trainer_data = crawl_rankings('trainer', args.season, args.racecourse)
    
    # Build lookup
    jockey_lookup, trainer_lookup = build_lookup(jockey_data, trainer_data)
    
    # Output
    output = {
        'season': args.season,
        'racecourse': args.racecourse,
        'jockeys': jockey_data,
        'trainers': trainer_data,
        'jockey_lookup': jockey_lookup,
        'trainer_lookup': trainer_lookup,
        'jockey_count': len(jockey_data),
        'trainer_count': len(trainer_data),
    }
    
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"✅ 爬取完成")
    print(f"   騎師: {len(jockey_data)} 人")
    print(f"   練馬師: {len(trainer_data)} 人")
    print(f"   輸出: {args.output}")
    print(f"{'='*60}")
    
    # Print top 5 preview
    if jockey_data:
        print(f"\n📊 騎師 Top 5:")
        for j in jockey_data[:5]:
            print(f"   {j['rank']}. {j['name']} — {j.get('wins', '?')}/{j.get('rides', '?')} ({j.get('win_rate', '?')}%)")
    
    if trainer_data:
        print(f"\n📊 練馬師 Top 5:")
        for t in trainer_data[:5]:
            print(f"   {t['rank']}. {t['name']} — {t.get('wins', '?')}/{t.get('rides', '?')} ({t.get('win_rate', '?')}%)")


if __name__ == '__main__':
    main()
