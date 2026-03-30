#!/usr/bin/env python3
"""
AU Race Extractor - Meydan 2026-03-28 Race 7 (Dubai Turf G1)
1811m Turf - 11 runners
"""
import asyncio, json, os, sys, re
from datetime import datetime
from curl_cffi import requests as cffi_requests
from playwright.async_api import async_playwright
import lightpanda_utils

sys.stdout.reconfigure(encoding='utf-8')

DATE_STR   = "2026-03-28"
VENUE_NAME = "Meydan"
RACE_NUM   = 7
BASE_DIR   = r"G:\.shortcut-targets-by-id\1hKLy5yBvy7czsQJKGZULAqAgYmUqKC3q\Antigravity\2026-03-28 Meydan"
OVERVIEW_URL = "https://www.racenet.com.au/form-guide/horse-racing/meydan-ae-20260328/race-7-dubai-turf-sponsored-by-dp-world-group-1-turf-race-7/overview"

def money(val):
    if val is None: return "N/A"
    try: return f"${int(val):,}"
    except: return str(val)

async def extract_nuxt_data(html_content):
    m = re.search(r'window\.__NUXT__\s*=\s*(.+?);\s*<\/script>', html_content, re.DOTALL)
    if not m: return None
    nuxt_script = m.group(1)
    
    # We pass the root directory of this script to find the lightpanda binary
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(ROOT_DIR)

    try:
        async with async_playwright() as p:
            if use_lightpanda:
                browser = await p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else:
                browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("about:blank")
            result = await page.evaluate(f"() => {{ try {{ const data = {nuxt_script}; return JSON.stringify(data); }} catch(e) {{ return JSON.stringify({{error: e.message}}); }} }}")
            await browser.close()
            try: return json.loads(result)
            except: return None
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

async def main():
    print(f"\n{'='*60}")
    print(f"AU Race Extractor - {VENUE_NAME} {DATE_STR} Race {RACE_NUM}")
    print(f"Dubai Turf (Group 1) - 1811m Turf")
    print(f"{'='*60}\n")

    print("[1] Fetching overview page via curl_cffi...")
    resp = cffi_requests.get(OVERVIEW_URL, impersonate="chrome")
    print(f"  Status: {resp.status_code}, {len(resp.text)} chars")

    print("\n[2] Extracting __NUXT__ data...")
    nuxt = await extract_nuxt_data(resp.text)
    if not nuxt:
        print("FATAL: Could not extract NUXT data")
        sys.exit(1)

    evt = nuxt['data'][0]['event']
    meeting = nuxt['data'][0].get('meeting', {})
    sels = evt['selections']

    race_name = evt.get('name', 'Race 7 - Dubai Turf')
    distance = str(evt.get('distance', 1811))
    track_type = evt.get('trackType', 'Turf')
    start_time = evt.get('startTime', '?')

    tc_obj = evt.get('trackCondition', {})
    track_cond = tc_obj.get('overall', '?') if isinstance(tc_obj, dict) else '?'
    track_surface = tc_obj.get('surface', track_type) if isinstance(tc_obj, dict) else track_type

    weather_obj = evt.get('weather', {})
    weather_cond = weather_obj.get('trackConditionOverall', '?') if isinstance(weather_obj, dict) else '?'

    prize_list = evt.get('prizeMoney', [])
    first_prize = money(prize_list[0].get('value')) if prize_list else '?'
    total_prize = money(sum(p.get('value', 0) for p in prize_list)) if prize_list else '?'

    rail_pos = meeting.get('railPosition') or 'N/A'

    print(f"\n  Race: {race_name}")
    print(f"  Distance: {distance}m | Surface: {track_surface}")
    print(f"  Track: {track_cond} | Weather: {weather_cond}")
    print(f"  Prize: {total_prize} | Horses: {len(sels)}")

    # Setup output folder (reuse the centrally managed Race 7 folder)
    folder_name = f"Race {RACE_NUM}"
    target_dir = os.path.join(BASE_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n[3] Output folder: {target_dir}")

    # Meeting Summary
    summary_path = os.path.join(target_dir, "Meeting_Summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Meeting Summary - {VENUE_NAME} {DATE_STR}\n")
        f.write(f"{'='*50}\n")
        f.write(f"Track Condition : {track_cond}\n")
        f.write(f"Surface         : {track_surface}\n")
        f.write(f"Weather         : {weather_cond}\n")
        f.write(f"Rail Position   : {rail_pos}\n")
        f.write(f"Race            : {race_name}\n")
        f.write(f"Distance        : {distance}m\n")
        f.write(f"1st Prize       : {first_prize}\n")
        f.write(f"Total Prize     : {total_prize}\n")
        f.write(f"Extracted At    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # --- RACECARD ---
    rc_lines = [
        f"{'='*80}",
        f"RACE {RACE_NUM}: {race_name}",
        f"Date: {DATE_STR}  |  Venue: {VENUE_NAME} (UAE)  |  Distance: {distance}m",
        f"Class: Group 1  |  Surface: {track_surface}  |  1st Prize: {first_prize}  |  Total: {total_prize}",
        f"Track: {track_cond}  |  Rail: {rail_pos}  |  Weather: {weather_cond}",
        f"{'='*80}",
        f"{'#':<4} {'Horse':<25} {'Bar':<5} {'Trainer':<24} {'Jockey':<24} {'Wt':>6} {'Rtg':>4} {'Career':<14} {'Last10Fig':<12} {'W%':>4} {'P%':>4} LastRun",
        "-"*160,
    ]
    for sel in sels:
        comp = sel.get('competitor', {})
        name = comp.get('name', '?') if isinstance(comp, dict) else '?'
        num = sel.get('competitorNumber', '?')
        bar = sel.get('barrierNumber', '?')
        status = sel.get('status', '')
        if status == 'Scratched':
            rc_lines.append(f"{num:<4} {name:<25} SCRATCHED")
            continue
        jock = sel.get('jockey', {});  jname = jock.get('name', '?') if isinstance(jock, dict) else '?'
        train = sel.get('trainer', {}); tname = train.get('name', '?') if isinstance(train, dict) else '?'
        weight = sel.get('weight', '?')
        stats = sel.get('stats', {})
        if not isinstance(stats, dict): stats = {}
        rating = stats.get('rating', '?'); career = stats.get('career', '?')
        last_fig = stats.get('lastTenFigure', '?'); win_pct = stats.get('winPercentage', '?')
        place_pct = stats.get('placePercentage', '?'); last_run = stats.get('lastRun', 'N/A')
        rc_lines.append(f"{num:<4} {name:<25} {bar:<5} {tname:<24} {jname:<24} {str(weight):>6} {str(rating):>4} {str(career):<14} {str(last_fig):<12} {str(win_pct):>4} {str(place_pct):>4} {last_run}")

    # --- FORMGUIDE ---
    fg_lines = [
        f"{'='*70}",
        f"RACE {RACE_NUM} FORMGUIDE: {race_name}",
        f"Date: {DATE_STR}  |  {distance}m  |  Group 1  |  {track_surface}",
        f"{'='*70}", "",
    ]
    for sel in sels:
        comp = sel.get('competitor', {})
        name = comp.get('name', '?') if isinstance(comp, dict) else '?'
        num = sel.get('competitorNumber', '?')
        bar = sel.get('barrierNumber', '?')
        status = sel.get('status', '')
        if status == 'Scratched':
            fg_lines.extend([f"[[{num}]] {name} ({bar})", "status:Scratched", "="*60, ""])
            continue
        jock = sel.get('jockey', {}); jname = jock.get('name', '?') if isinstance(jock, dict) else '?'
        train = sel.get('trainer', {}); tname = train.get('name', '?') if isinstance(train, dict) else '?'
        weight = sel.get('weight', '?')
        emergency = sel.get('isEmergency', False)
        gear_changes = sel.get('gearChanges', '')
        stats = sel.get('stats', {})
        if not isinstance(stats, dict): stats = {}

        fg_lines.append(f"[[{num}]] {name} ({bar})" + (" [EMERGENCY]" if emergency else ""))
        fg_lines.append(f"Weight: {weight}kg")
        fg_lines.append(f"T: {tname} | J: {jname}")
        if gear_changes: fg_lines.append(f"Gear Changes: {gear_changes}")
        fg_lines.append("")

        fg_lines.append(f"Career:    {str(stats.get('career','N/A')):<18} Last Year: {str(stats.get('lastYear','N/A')):<18} Prize:     {money(stats.get('totalPrizeMoney'))}")
        fg_lines.append(f"Season:    {str(stats.get('currentSeason','N/A')):<18} Win %:     {str(stats.get('winPercentage','N/A'))+'%' if stats.get('winPercentage') else 'N/A':<18} Place %:   {str(stats.get('placePercentage','N/A'))+'%' if stats.get('placePercentage') else 'N/A'}")
        fg_lines.append(f"ROI:       {str(stats.get('roi','N/A')):<18} Rating:    {str(stats.get('rating','N/A')):<18} Last Win:  {stats.get('lastWin','N/A')}")
        fg_lines.append(f"Avg Prize: {money(stats.get('averagePrizeMoney')):<18} Days Since:{str(stats.get('daysSinceLastRun','N/A')):<18} Win Range: {stats.get('winRange',[])}")
        fg_lines.append("")

        fg_lines.append(f"Distance:  {str(stats.get('distance','N/A')):<18} Track:     {str(stats.get('track','N/A')):<18} Trk/Dist:  {stats.get('trackDistance','N/A')}")
        fg_lines.append(f"Turf:      {str(stats.get('turf','N/A')):<18} Synthetic: {str(stats.get('synthetic','N/A')):<18} Dirt:      {stats.get('dirt','N/A')}")
        fg_lines.append("")

        fg_lines.append(f"Firm:      {str(stats.get('firm','N/A')):<18} Good:      {str(stats.get('good','N/A')):<18} Soft:      {stats.get('soft','N/A')}")
        fg_lines.append(f"Heavy:     {str(stats.get('heavy','N/A')):<18} Wet:       {str(stats.get('wet','N/A')):<18} Dry:       {stats.get('dry','N/A')}")
        fg_lines.append("")

        fg_lines.append(f"1st Up:    {str(stats.get('firstUp','N/A')):<18} 2nd Up:    {str(stats.get('secondUp','N/A')):<18} 3rd Up:    {stats.get('thirdUp','N/A')}")
        fg_lines.append("")

        fg_lines.append(f"Group 1:   {str(stats.get('group1','N/A')):<18} Group 2:   {str(stats.get('group2','N/A')):<18} Group 3:   {stats.get('group3','N/A')}")
        fg_lines.append(f"Listed:    {str(stats.get('listed','N/A')):<18} Class:     {str(stats.get('class','N/A')):<18}")
        fg_lines.append("")

        fg_lines.append(f"Fav:       {str(stats.get('fav','N/A')):<18} Night:     {str(stats.get('night','N/A')):<18} Clockwise: {stats.get('clockwise','N/A')}")
        fg_lines.append(f"T-J combo: {str(stats.get('trainerJockey','N/A')):<18} J-H combo: {str(stats.get('jockeyHorse','N/A')):<18} TJ Win%:   {stats.get('trainerJockeyWin','N/A')}")
        fg_lines.append("")

        fg_lines.append(f"Last 10 Fig: {stats.get('lastTenFigure','N/A')}")
        fg_lines.append(f"Last Run:    {stats.get('lastRun','N/A')}")
        fg_lines.append(f"Last SP:     ${stats.get('lastRunStartingPrice','N/A')}  Last Finish: {stats.get('lastRunFinishPosition','N/A')}")
        fg_lines.append(f"Win Distances: {', '.join(stats.get('winDistanceCount',[])) if isinstance(stats.get('winDistanceCount'), list) else stats.get('winDistanceCount','N/A')}")
        fg_lines.append("")
        fg_lines.append("=" * 60)
        fg_lines.append("")

    # Write files
    date_tag = "03-28"
    rc_path = os.path.join(target_dir, f"{date_tag} Race {RACE_NUM} Racecard.txt")
    fg_path = os.path.join(target_dir, f"{date_tag} Race {RACE_NUM} Formguide.txt")
    raw_path = os.path.join(target_dir, "raw_overview_nuxt.json")

    with open(rc_path, "w", encoding="utf-8") as f: f.write("\n".join(rc_lines))
    print(f"\n[4] Saved Racecard:   {rc_path}")
    with open(fg_path, "w", encoding="utf-8") as f: f.write("\n".join(fg_lines))
    print(f"    Saved Formguide:  {fg_path}")
    with open(raw_path, "w", encoding="utf-8") as f: json.dump(nuxt, f, indent=2, ensure_ascii=False, default=str)

    print(f"\n{'='*60}")
    print(f"EXTRACTION COMPLETE!")
    print(f"  TARGET_DIR  : {target_dir}")
    print(f"  VENUE       : {VENUE_NAME}")
    print(f"  DATE        : {DATE_STR}")
    print(f"  Track Cond  : {track_cond} ({track_surface})")
    print(f"  Horses      : {len(sels)}")
    print(f"{'='*60}\n")
    print("=== Meeting Summary ===")
    with open(summary_path, "r", encoding="utf-8") as f: print(f.read())

if __name__ == "__main__":
    asyncio.run(main())
