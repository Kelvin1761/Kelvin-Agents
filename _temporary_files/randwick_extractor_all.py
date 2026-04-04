#!/usr/bin/env python3
"""
AU Race Extractor (Playwright) - Flemington 2026-03-28 Race 1
Intercepts Racenet API calls via Playwright network interception.
"""

import asyncio
import json
import os
import sys
import re
from datetime import datetime
from playwright.async_api import async_playwright
import lightpanda_utils

# ─── CONFIG ───────────────────────────────────────────────────────────────────
DATE_STR   = "2026-03-28"
VENUE_NAME = "Flemington"
RACE_SLUG  = "flemington-20260328"
TARGET_RACES = [1]
EVENT_SLUG = "tab-were-on-race-1"   # From the user-provided URL

BASE_DIR   = r"G:\.shortcut-targets-by-id\1hKLy5yBvy7czsQJKGZULAqAgYmUqKC3q\Antigravity"
PAGE_URL   = f"https://www.racenet.com.au/form-guide/horse-racing/{RACE_SLUG}/{EVENT_SLUG}/overview"

# ─── HELPERS ──────────────────────────────────────────────────────────────────

def money(val):
    if val is None: return "N/A"
    try: return f"${int(val):,}"
    except: return str(val)

def fmt_flucs(flucs):
    if not flucs: return "N/A"
    prices = [str(f.get("price", "")) for f in flucs if f.get("price")]
    return " ".join(f"${p}" for p in prices) if prices else "N/A"

def parse_positions(run):
    positions = []
    for i in [1, 2, 3, 4]:
        pos  = run.get(f"position{i}")
        dist = run.get(f"dist{i}")
        if pos and dist:
            positions.append(f"{pos}@{dist}m")
    return " ".join(positions) if positions else ""

def fmt_run(run):
    track    = run.get("venueName") or run.get("venueAbbrev") or "?"
    is_trial = str(run.get("class", "")).lower() == "trial"
    trial_tag= " **(TRIAL)**" if is_trial else ""
    race_num = run.get("raceNumber", "?")
    date_raw = run.get("date", "")
    try: date_fmt = datetime.strptime(date_raw[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except: date_fmt = date_raw[:10] if date_raw else "?"
    dist     = run.get("distance", "?")
    cond     = run.get("trackCondition", "?")
    prize    = money(run.get("prizeMoney"))
    jockey   = run.get("jockeyName", "?")
    barrier  = run.get("barrier", "?")
    weight   = run.get("weight", "?")
    open_p   = run.get("openingPrice", "?")
    sp_p     = run.get("startPrice", "?")
    win_time = run.get("winTime", "")
    pos_str  = parse_positions(run)
    finish   = run.get("finish", "?")
    margin   = run.get("marginToWinner", "")
    w1 = run.get("winner1Name", "?"); w1w = run.get("winner1Weight", "")
    w2 = run.get("winner2Name", "");  w2w = run.get("winner2Weight", ""); w2m = run.get("winner2Margin", "")
    w3 = run.get("winner3Name", "");  w3w = run.get("winner3Weight", ""); w3m = run.get("winner3Margin", "")
    video    = run.get("videoComment", "") or ""
    note     = run.get("note", "") or ""
    stewards = run.get("stewardsComment", "") or ""

    line1 = (f"{track}{trial_tag} R{race_num} {date_fmt} {dist}m "
             f"cond:{cond} {prize} {jockey} ({barrier}) {weight}kg "
             f"Flucs:${open_p} ${sp_p} {win_time} {pos_str}")
    w_line = f"1-{w1}({w1w}kg)"
    if w2: w_line += f", 2-{w2}({w2w}kg) {w2m}L"
    if w3: w_line += f", 3-{w3}({w3w}kg) {w3m}L"
    if margin: w_line += f"  [This horse: {finish}th, +{margin}L]"
    lines = [line1, w_line]
    if video:    lines.append(f"Video: {video}")
    if note:     lines.append(f"Note: {note}")
    if stewards: lines.append(f"Stewards: {stewards}")
    return "\n".join(lines)

def fmt_stat(d):
    if not d: return "0-0-0-0"
    return f"{d.get('first',0)}-{d.get('second',0)}-{d.get('third',0)}-{d.get('starts', d.get('runs',0))}"

def trainer_stat(t):
    if not t: return "N/A"
    s = t.get("stats") or {}
    return f"{s.get('wins',0)}W from {s.get('starts',0)}S"

def jockey_stat(j):
    if not j: return "N/A"
    s = j.get("stats") or {}
    return f"{s.get('wins',0)}W from {s.get('starts',0)}S"

def build_formguide_entry(sel):
    name    = sel.get("horseName") or sel.get("name", "?")
    num     = sel.get("number", "?")
    barrier = sel.get("barrier", "?")
    status  = sel.get("statusAbv", "")
    if status == "S":
        return f"[[{num}]] {name} ({barrier})\nstatus:Scratched\n"
    age     = sel.get("age", "?")
    sex     = sel.get("sexAbv", "?")
    colour  = sel.get("colour", "?")
    sire    = sel.get("sire") or {}
    dam     = sel.get("dam") or {}
    owners  = sel.get("owners", "") or ""
    flucs   = sel.get("flucOdds") or []
    trainer_obj = sel.get("trainer") or {}
    jockey_obj  = sel.get("jockey") or {}
    stats   = sel.get("stats") or {}
    forms   = sel.get("forms") or []

    sire_name = sire.get("name", "?") if sire else "?"
    dam_name  = dam.get("name", "?") if dam else "?"
    dam_sire  = dam.get("sireName", "") if dam else ""
    trainer_name = trainer_obj.get("name", "?") if trainer_obj else "?"
    jockey_name  = jockey_obj.get("name", "?") if jockey_obj else "?"

    career  = stats.get("career") or {}
    last10  = stats.get("last10") or {}
    prize_t = stats.get("totalPrizeMoney")
    career_str = f"{career.get('first',0)}-{career.get('second',0)}-{career.get('third',0)}-{career.get('starts',0)}"
    last10_str = f"{last10.get('first',0)}-{last10.get('second',0)}-{last10.get('third',0)}-{last10.get('starts',0)}"
    win_pct = f"{stats.get('winPct', 0):.1f}%" if stats else "0%"
    plc_pct = f"{stats.get('placePct', 0):.1f}%" if stats else "0%"
    roi     = f"{stats.get('roi', 0):.2f}" if stats else "0.00"

    going   = stats.get("going") or {}
    ups     = stats.get("upRuns") or {}
    seasonal= stats.get("seasonal") or {}
    fav_s   = stats.get("favourite") or {}

    lines = []
    lines.append(f"[[{num}]] {name} ({barrier})")
    lines.append(f"{age}yo{sex} {colour} | Sire: {sire_name} | Dam: {dam_name} ({dam_sire})")
    lines.append(f"Flucs: {fmt_flucs(flucs)}")
    lines.append(f"Owners: {owners}")
    lines.append(f"T: {trainer_name} (LY: {trainer_stat(trainer_obj)}) | J: {jockey_name} (LY: {jockey_stat(jockey_obj)})")
    lines.append("")
    lines.append(f"Career:    {career_str:<18} Last 10:   {last10_str:<18} Prize:     {money(prize_t)}")
    lines.append(f"Win %:     {win_pct:<18} Place %:   {plc_pct:<18} ROI:       {roi}")
    lines.append("")
    lines.append(f"Track:     {fmt_stat(stats.get('track')):<18} Distance:  {fmt_stat(stats.get('distance')):<18} Trk/Dist:  {fmt_stat(stats.get('trackAndDistance'))}")
    lines.append(f"Firm:      {fmt_stat(going.get('firm')):<18} Good:      {fmt_stat(going.get('good')):<18} Soft:      {fmt_stat(going.get('soft'))}")
    lines.append(f"Heavy:     {fmt_stat(going.get('heavy')):<18} Synth:     {fmt_stat(going.get('synthetic')):<18} Class:     {fmt_stat(stats.get('class'))}")
    lines.append("")
    lines.append(f"1st Up:    {fmt_stat(ups.get('first')):<18} 2nd Up:    {fmt_stat(ups.get('second')):<18} 3rd Up:    {fmt_stat(ups.get('third'))}")
    lines.append(f"Season:    {fmt_stat(seasonal.get('current')):<18} 12 Month:  {fmt_stat(seasonal.get('last12Months') or seasonal.get('lastYear')):<18} Fav:       {fmt_stat(fav_s)}")
    lines.append("")
    for run in forms:
        lines.append(fmt_run(run))
        lines.append("")
    return "\n".join(lines)

# ─── ASYNC MAIN ───────────────────────────────────────────────────────────────

async def main():
    print(f"\n{'='*60}")
    print(f"AU Race Extractor (Playwright) — {VENUE_NAME} {DATE_STR}")
    print(f"{'='*60}\n")
    print(f"Target URL: {PAGE_URL}\n")

    captured = {}   # Will store intercepted API responses

    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    
    try:
        async with async_playwright() as p:
            if use_lightpanda:
                browser = await p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else:
                browser = await p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-setuid-sandbox"]
                )
            context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-AU",
        )
        page = await context.new_page()

        # Intercept network responses to capture API data
        async def handle_response(response):
            url = response.url
            # Capture race-specific API calls
            if (f"{RACE_SLUG}" in url and 
                ("api" in url or "race" in url.lower()) and
                response.status == 200):
                try:
                    ct = response.headers.get("content-type", "")
                    if "json" in ct:
                        body = await response.json()
                        captured[url] = body
                        print(f"  [API] Captured: {url[:100]}")
                except Exception as e:
                    pass

        page.on("response", handle_response)

        print("[1] Navigating to Racenet page...")
        try:
            await page.goto(PAGE_URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  [WARN] Navigation timeout: {e}. Proceeding with captured data...")

        # Wait a bit more for API calls to settle
        await asyncio.sleep(3)

        print(f"\n[2] Captured {len(captured)} API responses")
        for url in list(captured.keys()):
            print(f"  - {url[:120]}")

        await browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

    # ── PARSE CAPTURED DATA ────────────────────────────────────────────────────
    
    # Find the most relevant race data
    race_data = None
    meeting_data = None

    for url, data in captured.items():
        # Look for selections / horses in response
        sel_check = (
            data.get("selections") or
            data.get("horses") or
            data.get("runners") or
            (isinstance(data.get("data"), dict) and (
                data["data"].get("selections") or
                data["data"].get("horses")
            ))
        )
        if sel_check and race_data is None:
            race_data = data
            print(f"\n  ✓ Using race data from: {url[:100]}")

        # Look for meeting-level data (track condition etc.)
        if (data.get("races") or data.get("events") or 
            (isinstance(data.get("data"), dict) and data["data"].get("races"))):
            meeting_data = data
            print(f"  ✓ Using meeting data from: {url[:100]}")

    # Drill into 'data' wrapper if needed
    if race_data and not race_data.get("selections") and isinstance(race_data.get("data"), dict):
        race_data = race_data["data"]

    if meeting_data and not meeting_data.get("races") and isinstance(meeting_data.get("data"), dict):
        meeting_data = meeting_data["data"]

    # If still nothing, try to find any data dict that has useful keys
    if not race_data:
        print("\n  [WARN] Could not find structured selections in captured data.")
        print("  Available data structures:")
        for url, data in captured.items():
            print(f"    {url[:80]}: keys={list(data.keys())[:5]}")
        # Try the first captured data as fallback
        if captured:
            first_url, first_data = next(iter(captured.items()))
            if isinstance(first_data.get("data"), dict):
                race_data = first_data["data"]
            else:
                race_data = first_data

    if not race_data:
        print("\nFATAL: No race data could be captured. Racenet may require additional bypass.")
        print("Dumping all captured data to debug file...")
        debug_path = os.path.join(BASE_DIR, "debug_captured.json")
        with open(debug_path, "w", encoding="utf-8") as f:
            json.dump(captured, f, indent=2, ensure_ascii=False)
        print(f"Debug saved: {debug_path}")
        sys.exit(1)

    # ── EXTRACT RACE INFO ──────────────────────────────────────────────────────
    print(f"\n[3] Race data keys: {list(race_data.keys())[:20]}")

    race_name  = race_data.get("name") or race_data.get("raceName") or "Race 1"
    distance   = race_data.get("distance") or "?"
    class_name = race_data.get("class") or race_data.get("raceClass") or "?"
    track_cond = race_data.get("trackCondition") or race_data.get("going") or "?"
    prize      = race_data.get("prizeMoney") or race_data.get("totalPrizeMoney") or "?"
    start_time = race_data.get("startTime") or race_data.get("time") or "?"
    rail_pos   = race_data.get("railPosition") or "?"
    weather    = race_data.get("weather") or "?"

    # Try meeting-level for track/weather/rail
    if meeting_data:
        track_cond = meeting_data.get("trackCondition") or track_cond
        weather    = meeting_data.get("weather") or weather
        rail_pos   = meeting_data.get("railPosition") or rail_pos

    selections = (race_data.get("selections") or 
                  race_data.get("horses") or 
                  race_data.get("runners") or [])
    print(f"  Selections: {len(selections)}")
    print(f"  Race Name : {race_name}")
    print(f"  Distance  : {distance}m")
    print(f"  Track Cond: {track_cond}")

    # ── SETUP OUTPUT DIR ───────────────────────────────────────────────────────
    race_num   = 1
    start_r    = race_num
    end_r      = race_num
    folder_name = f"{DATE_STR} {VENUE_NAME} Race {start_r}-{end_r}"
    target_dir  = os.path.join(BASE_DIR, folder_name)
    os.makedirs(target_dir, exist_ok=True)
    print(f"\n[4] Output folder: {target_dir}")

    # Meeting Summary
    summary_path = os.path.join(target_dir, "Meeting_Summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Meeting Summary — {VENUE_NAME} {DATE_STR}\n")
        f.write(f"{'='*50}\n")
        f.write(f"Track Condition : {track_cond}\n")
        f.write(f"Weather         : {weather}\n")
        f.write(f"Rail Position   : {rail_pos}\n")
        f.write(f"Extracted At    : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    print(f"  Saved: {summary_path}")

    # ── RACECARD ──────────────────────────────────────────────────────────────
    rc_lines = [
        f"{'='*70}",
        f"RACE {race_num}: {race_name}",
        f"Date: {DATE_STR}  |  Venue: {VENUE_NAME}  |  Distance: {distance}m",
        f"Class: {class_name}  |  Prize: {money(prize)}  |  Start: {start_time}",
        f"Track: {track_cond}  |  Rail: {rail_pos}  |  Weather: {weather}",
        f"{'='*70}",
        f"{'#':<4} {'Horse':<28} {'Bar':<5} {'Trainer':<25} {'Jockey':<22} {'Wt':>5} "
        f"{'Age':>4} {'Rtg':>4} {'Career':<16} {'Last10':<12} {'Win%':>5} {'Plc%':>5} LastRace",
        "-"*155,
    ]

    for sel in selections:
        num     = sel.get("number", "?")
        name    = sel.get("horseName") or sel.get("name", "?")
        barrier = sel.get("barrier", "?")
        status  = sel.get("statusAbv", "")
        if status == "S":
            rc_lines.append(f"{num:<4} {name:<28} SCRATCHED")
            continue
        trainer = (sel.get("trainer") or {}).get("name", "?")
        jockey  = (sel.get("jockey") or {}).get("name", "?")
        weight  = sel.get("weight", "?")
        age     = sel.get("age", "?")
        rating  = sel.get("rating", "?")
        sts     = sel.get("stats") or {}
        career  = sts.get("career") or {}
        last10  = sts.get("last10") or {}
        c_str   = f"{career.get('first',0)}-{career.get('second',0)}-{career.get('third',0)}-{career.get('starts',0)}"
        l_str   = f"{last10.get('first',0)}-{last10.get('second',0)}-{last10.get('third',0)}-{last10.get('starts',0)}"
        win_p   = f"{sts.get('winPct',0):.1f}%"
        plc_p   = f"{sts.get('placePct',0):.1f}%"
        forms   = sel.get("forms") or []
        last_r  = "N/A"
        if forms:
            lr = forms[0]
            last_r = (f"{lr.get('venueName','?')} {lr.get('date','?')[:10]} "
                      f"{lr.get('distance','?')}m {lr.get('finish','?')}th")
        rc_lines.append(
            f"{num:<4} {name:<28} {barrier:<5} {trainer:<25} {jockey:<22} "
            f"{weight:>5} {age:>4} {str(rating):>4} {c_str:<16} {l_str:<12} "
            f"{win_p:>5} {plc_p:>5} {last_r}"
        )

    # ── FORMGUIDE ─────────────────────────────────────────────────────────────
    fg_lines = [
        f"{'='*70}",
        f"RACE {race_num} FORMGUIDE: {race_name}",
        f"Date: {DATE_STR}  |  {distance}m  |  {class_name}",
        f"{'='*70}",
        "",
    ]

    for sel in selections:
        entry = build_formguide_entry(sel)
        fg_lines.append(entry)
        fg_lines.append("=" * 60)
        fg_lines.append("")

    # ── WRITE FILES ────────────────────────────────────────────────────────────
    date_tag = datetime.strptime(DATE_STR, "%Y-%m-%d").strftime("%m-%d")
    range_tag = str(race_num)

    rc_path = os.path.join(target_dir, f"{date_tag} Race {range_tag} Racecard.txt")
    fg_path = os.path.join(target_dir, f"{date_tag} Race {range_tag} Formguide.txt")

    with open(rc_path, "w", encoding="utf-8") as f:
        f.write("\n".join(rc_lines))
    print(f"\n[5] Saved Racecard:   {rc_path}")

    with open(fg_path, "w", encoding="utf-8") as f:
        f.write("\n".join(fg_lines))
    print(f"    Saved Formguide:  {fg_path}")

    # Also dump raw captured JSON for debugging
    raw_path = os.path.join(target_dir, "raw_api_capture.json")
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(captured, f, indent=2, ensure_ascii=False, default=str)
    print(f"    Saved Raw capture: {raw_path}")

    print(f"\n{'='*60}")
    print(f"✓ Extraction Complete!")
    print(f"  TARGET_DIR  : {target_dir}")
    print(f"  VENUE       : {VENUE_NAME}")
    print(f"  DATE        : {DATE_STR}")
    print(f"  Track Cond  : {track_cond}")
    print(f"{'='*60}\n")
    print("=== Meeting Summary ===")
    with open(summary_path, "r", encoding="utf-8") as f:
        print(f.read())

if __name__ == "__main__":
    asyncio.run(main())
