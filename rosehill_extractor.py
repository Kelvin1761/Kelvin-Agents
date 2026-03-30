"""
Rosehill Gardens 2026-03-28 Extractor v2
Fixed: horse names from sel['competitor']['name'], metadata from inline objects
Uses Playwright headed browser to bypass Cloudflare.
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import json
import re
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"g:\我的雲端硬碟\Antigravity Shared\Antigravity"
MEETING_SLUG = "rosehill-gardens-20260328"

RACE_SLUGS = [
    (1, "midway-handicap-race-1"),
    (2, "asahi-super-dry-neville-sellwood-stakes-race-2"),
    (3, "drinkwise-baillieu-race-3"),
    (4, "quayclean-handicap-race-4"),
    (5, "toyota-forklifts-tulloch-stakes-race-5"),
    (6, "vinery-stud-stakes-race-6"),
    (7, "schweppes-emancipation-stakes-race-7"),
    (8, "kia-tancred-stakes-race-8"),
    (9, "racing-and-sports-doncaster-prelude-race-9"),
    (10, "e-security-group-star-kingdom-stakes-race-10"),
]

def process_selections(nuxt_data, f_rc, f_fg):
    form_data = nuxt_data.get('fetch', {})
    form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
    if not form_key:
        print("  WARNING: No FormGuidePrint data found")
        return None
    
    event_data = form_data.get(form_key, {})
    selections = event_data.get('selections', [])
    if not selections:
        print("  WARNING: No selections found")
        return None
    
    # Extract event-level metadata from the fetch payload
    meta = {
        'distance': event_data.get('distance', '?'),
        'event_class': event_data.get('eventClass', event_data.get('class', '')),
        'prize': event_data.get('racePrizeMoney', event_data.get('prizeMoney', 0)) or 0,
        'weather': 'Unknown',
        'track_condition': 'Unknown',
        'track_rating': ''
    }
    
    # Try to get weather/track from event data
    weather_obj = event_data.get('weather')
    if isinstance(weather_obj, dict):
        cond = weather_obj.get('condition', '')
        temp = weather_obj.get('temperature', '')
        if cond:
            meta['weather'] = cond.title()
            if temp:
                meta['weather'] += f" {temp}C"
    
    tc_obj = event_data.get('trackCondition')
    if isinstance(tc_obj, dict):
        overall = tc_obj.get('overall', '')
        rating = tc_obj.get('rating', '')
        if overall:
            meta['track_condition'] = f"{overall} {rating}".strip()
            meta['track_rating'] = rating
    
    for sel in selections:
        num = sel.get('competitorNumber', '?')
        
        # Get horse name from inline competitor object
        comp = sel.get('competitor', {}) or {}
        name = comp.get('name', 'Unknown')
        
        # Check scratched status
        status = sel.get('status')
        status_abv = sel.get('statusAbv')
        if status_abv in ['S', 'Scratched'] or status in ['S', 'Scratched', 'SCRATCHED']:
            f_rc.write(f"{num}. {name} - status:Scratched\n")
            f_fg.write(f"{num}. {name} - status:Scratched\n\n")
            continue
        
        barrier = sel.get('barrierNumber', '?')
        trainer_obj = sel.get('trainer') or {}
        trainer = trainer_obj.get('name', 'Unknown')
        jockey_obj = sel.get('jockey') or {}
        jockey = jockey_obj.get('name', 'Unknown')
        
        weight_str = str(sel.get('weight', '?'))
        claim_str = str(sel.get('jockeyWeightClaim') or '')
        effective_weight_str = weight_str
        if claim_str and claim_str not in ['None', 'null', '0', '0.0', '']:
            try:
                base_wt = float(weight_str)
                claim_wt = float(claim_str)
                effective_wt = base_wt + claim_wt
                effective_weight_str = f"{effective_wt:g}kg (Base {base_wt:g}kg, Claim {claim_wt:g}kg)"
            except ValueError:
                pass
        
        age = comp.get('age', '?')
        sex_short = comp.get('sexShort', '?')
        colour = comp.get('colour', '?')
        rating = sel.get('ratingOfficial', '?')
        stats = sel.get('stats', {}) or {}
        
        def fmt_stat(stat_key):
            s = stats.get(stat_key, '')
            if isinstance(s, dict):
                return f"{s.get('starts', 0)}:{s.get('wins', 0)}-{s.get('seconds', 0)}-{s.get('thirds', 0)}"
            return s if s else "0:0-0-0"
        
        career = fmt_stat('career')
        last10 = stats.get('lastTenFigure', '') or '-'
        win_pct = stats.get('winPercentage', 0) or 0
        plc_pct = stats.get('placePercentage', 0) or 0
        
        last_race = ""
        runs = sel.get('forms', []) or []
        if runs:
            lr = runs[0]
            last_race = f"{lr.get('finishPosition')}/{lr.get('eventStarters')} {lr.get('eventDistance')}m {lr.get('meetingName', '')}"
        
        # === RACECARD ===
        f_rc.write(f"{num}. {name} ({barrier})\n")
        f_rc.write(f"Trainer: {trainer} | Jockey: {jockey} | Weight: {effective_weight_str} | Age: {age} | Rating: {rating}\n")
        f_rc.write(f"Career: {career} | Last 10: {last10} | Win: {win_pct}% | Place: {plc_pct}% | Last: {last_race}\n")
        f_rc.write("-" * 40 + "\n")
        
        # === FORMGUIDE ===
        sire_name = comp.get('sire', 'Unknown')
        dam_name = comp.get('dam', 'Unknown')
        sire_of_dam = comp.get('sireOfDam', 'Unknown')
        owner = comp.get('owner', 'Unknown')
        
        trainer_name = trainer_obj.get('name', 'Unknown')
        trainer_stats = trainer_obj.get('stats', {})
        trainer_ly = trainer_stats.get('lastYear', '-') if isinstance(trainer_stats, dict) else '-'
        
        jockey_name = jockey_obj.get('name', 'Unknown')
        jockey_stats = jockey_obj.get('stats', {})
        jockey_ly = jockey_stats.get('lastYear', '-') if isinstance(jockey_stats, dict) else '-'
        
        f_fg.write(f"[{num}] {name} ({barrier})\n")
        f_fg.write(f"{age}yo{sex_short} {colour} | Sire: {sire_name} | Dam: {dam_name} ({sire_of_dam})\n")
        
        flucs_list = [str(f.get('value')) for f in sel.get('flucOdds', []) if isinstance(f, dict) and 'value' in f]
        flucs_str = f"Flucs: ${' $'.join(flucs_list)}" if flucs_list else "Flucs: -"
        f_fg.write(f"{flucs_str}\n")
        f_fg.write(f"Owners: {owner}\n")
        f_fg.write(f"T: {trainer_name} (LY: {trainer_ly}) | J: {jockey_name} (LY: {jockey_ly})\n\n")
        
        prize_money = stats.get('totalPrizeMoney') or 0
        f_fg.write(f"{'Career:':<10} {fmt_stat('career'):<15} {'Last 10:':<10} {str(last10):<15} {'Prize:':<10} ${prize_money:<14,}\n")
        f_fg.write(f"{'Win %:':<10} {str(win_pct):<15} {'Place %:':<10} {str(plc_pct):<15} {'ROI:':<10} {str(stats.get('roi', 0)):<15}\n\n")
        
        f_fg.write(f"{'Track:':<10} {fmt_stat('track'):<15} {'Distance:':<10} {fmt_stat('distance'):<15} {'Trk/Dist:':<10} {fmt_stat('trackDistance'):<15}\n")
        f_fg.write(f"{'Firm:':<10} {fmt_stat('firm'):<15} {'Good:':<10} {fmt_stat('good'):<15} {'Soft:':<10} {fmt_stat('soft'):<15}\n")
        f_fg.write(f"{'Heavy:':<10} {fmt_stat('heavy'):<15} {'Synth:':<10} {fmt_stat('synthetic'):<15} {'Class:':<10} {fmt_stat('class'):<15}\n\n")
        
        f_fg.write(f"{'1st Up:':<10} {fmt_stat('firstUp'):<15} {'2nd Up:':<10} {fmt_stat('secondUp'):<15} {'3rd Up:':<10} {fmt_stat('thirdUp'):<15}\n")
        f_fg.write(f"{'Season:':<10} {fmt_stat('currentSeason'):<15} {'12 Month:':<10} {fmt_stat('lastYear'):<15} {'Fav:':<10} {fmt_stat('fav'):<15}\n\n")
        
        for pr in runs:
            track = pr.get('meetingName', '')
            date = pr.get('meetingDate', '')
            dist = pr.get('eventDistance', '')
            race_num = pr.get('eventNumber', '')
            cond = pr.get('trackConditionRating', '?')
            money = pr.get('racePrizeMoney') or 0
            wt = pr.get('weightCarried', '')
            bar = pr.get('barrier', '')
            p_jock = pr.get('jockey', {}).get('name', 'Unknown') if isinstance(pr.get('jockey'), dict) else 'Unknown'
            
            run_flucs = f"Flucs:${pr.get('openPrice', '-')} ${pr.get('startingWinPriceDecimal', '-')}"
            win_time = pr.get('winnerTime', '')
            
            positions = ""
            for pref in pr.get('competitorPositionSummary', []):
                if isinstance(pref, dict):
                    pos_str = pref.get('positionText')
                    dist_str = pref.get('distanceText')
                    if pos_str and dist_str:
                        positions += f"{pos_str}@{dist_str} "
            
            win_str = f"1-{pr.get('winnerName', '')} ({pr.get('winnerWeightCarried', '')}kg)"
            sec_str = f"2-{pr.get('secondName', '')} ({pr.get('secondWeightCarried', '')}kg) {pr.get('secondMarginDecimal', '')}L"
            thi_str = f"3-{pr.get('thirdName', '')} ({pr.get('thirdWeightCarried', '')}kg) {pr.get('thirdMarginDecimal', '')}L"
            
            trial_str = " **(TRIAL)**" if pr.get('isTrial') else ""
            
            f_fg.write(f"{track}{trial_str} R{race_num} {date} {dist}m cond:{cond} ${money:,} {p_jock} ({bar}) {wt}kg {run_flucs} {win_time} {positions.strip()}.\n")
            f_fg.write(f"{win_str}, {sec_str}, {thi_str}\n")
            f_fg.write(f"Video: {pr.get('videoComment', '')}\n")
            f_fg.write(f"Note: {pr.get('videoNote', '')}\n")
            f_fg.write(f"Stewards: {pr.get('stewardsReport', '')}\n\n")
        f_fg.write("=" * 60 + "\n\n")
    return meta

def main():
    date_str = "2026-03-28"
    location = "Rosehill Gardens"
    start_race = 1
    end_race = 10
    
    output_dir = os.path.join(BASE_DIR, f"{date_str} {location} Race {start_race}-{end_race}")
    os.makedirs(output_dir, exist_ok=True)
    
    mm_dd = date_str[5:]
    rc_file = os.path.join(output_dir, f"{mm_dd} Race {start_race}-{end_race} Racecard.md")
    fg_file = os.path.join(output_dir, f"{mm_dd} Race {start_race}-{end_race} Formguide.md")
    
    first_meta = None
    rail = "Unknown"
    
    ROOT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in globals() else os.getcwd()
    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(ROOT_DIR)
    
    try:
        with sync_playwright() as p:
            print("Launching browser...")
            if use_lightpanda:
                browser = p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else:
                browser = p.chromium.launch(
                    headless=False,
                    args=['--ignore-certificate-errors', '--disable-blink-features=AutomationControlled']
                )
        context = browser.new_context(ignore_https_errors=True)
        page = context.new_page()
        
        with open(rc_file, 'w', encoding='utf-8') as f_rc, open(fg_file, 'w', encoding='utf-8') as f_fg:
            for race_num, slug in RACE_SLUGS:
                print(f"\n=== Processing Race {race_num} ({slug}) ===")
                
                print_url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={MEETING_SLUG}&eventSlug={slug}&printSlug=print-form"
                
                try:
                    page.goto(print_url, wait_until='domcontentloaded', timeout=30000)
                    
                    # Poll for __NUXT__ up to 15s
                    nuxt_data = None
                    for i in range(15):
                        time.sleep(1)
                        nuxt_data = page.evaluate("() => window.__NUXT__")
                        if nuxt_data:
                            break
                    
                    if not nuxt_data:
                        print(f"  Race {race_num}: NUXT not found after 15s, skipping")
                        continue
                    
                    # Try to get rail from Apollo Meeting data
                    if rail == "Unknown":
                        apollo = nuxt_data.get('apollo', {}).get('horseClient', {})
                        for k, v in apollo.items():
                            if k.startswith("Meeting:") and isinstance(v, dict):
                                rail = v.get('railPosition', 'Unknown')
                                break
                    
                    # Try to get event metadata from fetch payload
                    form_data = nuxt_data.get('fetch', {})
                    form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
                    event_data = form_data.get(form_key, {}) if form_key else {}
                    
                    dist = event_data.get('distance', '?')
                    event_class = event_data.get('eventClass', event_data.get('class', ''))
                    prize = event_data.get('racePrizeMoney', 0) or 0
                    
                    # Weather/Track from event data or Apollo
                    track_cond = 'Unknown'
                    weather = 'Unknown'
                    
                    tc_obj = event_data.get('trackCondition')
                    if isinstance(tc_obj, dict):
                        overall = tc_obj.get('overall', '')
                        rating_val = tc_obj.get('rating', '')
                        if overall:
                            track_cond = f"{overall} {rating_val}".strip()
                    
                    w_obj = event_data.get('weather')
                    if isinstance(w_obj, dict):
                        cond = w_obj.get('condition', '')
                        temp = w_obj.get('temperature', '')
                        if cond:
                            weather = cond.title()
                            if temp:
                                weather += f" {temp}C"
                    
                    if first_meta is None:
                        first_meta = {'track_condition': track_cond, 'weather': weather}
                    
                    dist_str = f"{dist}m" if dist and dist != '?' else ''
                    header_line = f"RACE {race_num}"
                    if dist_str:
                        header_line += f" -- {dist_str}"
                    if event_class:
                        header_line += f" | {event_class}"
                    if prize:
                        header_line += f" | ${prize:,}"
                    
                    f_rc.write(f"{header_line}\n")
                    f_rc.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*60}\n")
                    f_rc.flush()
                    
                    f_fg.write(f"{header_line}\n")
                    f_fg.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*60}\n")
                    
                    process_selections(nuxt_data, f_rc, f_fg)
                    f_fg.flush()
                    
                    # Count selections for summary
                    sels = event_data.get('selections', [])
                    active = sum(1 for s in sels if s.get('status') not in ['S', 'Scratched', 'SCRATCHED'] and s.get('statusAbv') not in ['S', 'Scratched'])
                    scratched = len(sels) - active
                    
                    print(f"  Race {race_num}: SUCCESS - {dist_str} {track_cond} ({active} runners, {scratched} scratched)")
                    
                except Exception as e:
                    print(f"  Race {race_num}: ERROR - {e}")
                    continue
        
        browser.close()
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)
    
    # Write Meeting Summary
    summary_file = os.path.join(output_dir, "Meeting_Summary.md")
    if first_meta:
        with open(summary_file, 'w', encoding='utf-8') as f_sum:
            f_sum.write(f"Date: {date_str}\n")
            f_sum.write(f"Venue: {location}\n")
            f_sum.write(f"Track Condition: {first_meta.get('track_condition', 'Unknown')}\n")
            f_sum.write(f"Weather: {first_meta.get('weather', 'Unknown')}\n")
            f_sum.write(f"Rails: {rail}\n")
    
    print(f"\nDone! Output: {output_dir}")

if __name__ == '__main__':
    main()
