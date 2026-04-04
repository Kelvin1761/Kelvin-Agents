import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import json
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
MEETING_SLUG = "randwick-20260404"
DATE_STR = "2026-04-04"
VENUE_NAME = "Randwick"

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
    
    meta = {
        'distance': event_data.get('distance', '?'),
        'event_class': event_data.get('eventClass', event_data.get('class', '')),
        'prize': event_data.get('racePrizeMoney', event_data.get('prizeMoney', 0)) or 0,
        'weather': 'Unknown',
        'track_condition': 'Unknown',
        'track_rating': ''
    }
    
    weather_obj = event_data.get('weather')
    if isinstance(weather_obj, dict):
        cond = weather_obj.get('condition', '')
        if cond:
            meta['weather'] = cond.title()
    
    tc_obj = event_data.get('trackCondition')
    if isinstance(tc_obj, dict):
        overall = tc_obj.get('overall', '')
        rating = tc_obj.get('rating', '')
        if overall:
            meta['track_condition'] = f"{overall} {rating}".strip()
            meta['track_rating'] = rating
    
    for sel in selections:
        num = sel.get('competitorNumber', '?')
        comp = sel.get('competitor', {}) or {}
        name = comp.get('name', 'Unknown')
        
        status = sel.get('status')
        status_abv = sel.get('statusAbv')
        if status_abv in ['S', 'Scratched'] or status in ['S', 'Scratched', 'SCRATCHED']:
            f_rc.write(f"{num}. {name} - status:Scratched\n")
            f_fg.write(f"[{num}] {name}\nstatus:Scratched\n\n")
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
                effective_weight_str = f"{base_wt + claim_wt:g}kg (+{claim_wt})"
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
            last_race = f"{lr.get('finishPosition')}/{lr.get('eventStarters')} {lr.get('eventDistance')}m"
        
        # RACECARD
        f_rc.write(f"{num}. {name} ({barrier})\n")
        f_rc.write(f"Trainer: {trainer} | Jockey: {jockey} | Weight: {effective_weight_str} | Age: {age} | Rating: {rating}\n")
        f_rc.write(f"Career: {career} | Last 10: {last10} | Win: {win_pct}% | Place: {plc_pct}% | Last: {last_race}\n")
        f_rc.write("-" * 40 + "\n")
        
        # FORMGUIDE
        sire_name = comp.get('sire', 'Unknown')
        dam_name = comp.get('dam', 'Unknown')
        sire_of_dam = comp.get('sireOfDam', 'Unknown')
        owner = comp.get('owner', 'Unknown')
        
        trainer_name = trainer_obj.get('name', 'Unknown')
        trainer_ly = trainer_obj.get('stats', {}).get('lastYear', '-') if isinstance(trainer_obj.get('stats'), dict) else '-'
        jockey_name = jockey_obj.get('name', 'Unknown')
        jockey_ly = jockey_obj.get('stats', {}).get('lastYear', '-') if isinstance(jockey_obj.get('stats'), dict) else '-'
        
        f_fg.write(f"[[{num}]] {name} ({barrier})\n")
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
            race_num_hist = pr.get('eventNumber', '')
            cond = pr.get('trackConditionRating', '?')
            money = pr.get('racePrizeMoney') or 0
            wt = pr.get('weightCarried', '')
            bar = pr.get('barrier', '')
            p_jock = pr.get('jockey', {}).get('name', 'Unknown') if isinstance(pr.get('jockey'), dict) else 'Unknown'
            run_flucs = f"Flucs:${pr.get('openPrice', '-')} ${pr.get('startingWinPriceDecimal', '-')}"
            win_time = pr.get('winnerTime', '')
            
            positions = ""
            for pref in pr.get('competitorPositionSummary', []):
                if isinstance(pref, dict) and pref.get('positionText'):
                    positions += f"{pref.get('positionText')}@{pref.get('distanceText')} "
            
            win_str = f"1-{pr.get('winnerName', '')} ({pr.get('winnerWeightCarried', '')}kg)"
            sec_str = f"2-{pr.get('secondName', '')} ({pr.get('secondWeightCarried', '')}kg)"
            thi_str = f"3-{pr.get('thirdName', '')} ({pr.get('thirdWeightCarried', '')}kg)"
            
            trial_str = " **(TRIAL)**" if pr.get('isTrial') else ""
            
            f_fg.write(f"{track}{trial_str} R{race_num_hist} {date} {dist}m cond:{cond} ${money:,} {p_jock} ({bar}) {wt}kg {run_flucs} {win_time} {positions.strip()}\n")
            f_fg.write(f"{win_str}, {sec_str}, {thi_str}\n")
            if pr.get('videoComment'): f_fg.write(f"Video: {pr.get('videoComment')}\n")
            if pr.get('videoNote'): f_fg.write(f"Note: {pr.get('videoNote')}\n")
            if pr.get('stewardsReport'): f_fg.write(f"Stewards: {pr.get('stewardsReport')}\n")
            f_fg.write("\n")
        f_fg.write("=" * 60 + "\n\n")
    return meta

def main():
    print(f"\n============================================================")
    print(f"AU Race Extractor (Playwright) — {VENUE_NAME} {DATE_STR}")
    print(f"============================================================\n")

    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    
    try:
        with sync_playwright() as p:
            if use_lightpanda:
                browser = p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else:
                browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
            
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            # Step 1: Navigate to Meeting overview to fetch race slugs
            meeting_url = f"https://www.racenet.com.au/form-guide/horse-racing/{MEETING_SLUG}"
            print(f"[1] Navigating to Meeting Root: {meeting_url}")
            
            try:
                page.goto(meeting_url, wait_until='domcontentloaded', timeout=45000)
            except Exception as e:
                print(f"  [Error] Failed to load meeting root: {e}")
                
            nuxt_data = None
            for i in range(15):
                time.sleep(1)
                try:
                    nuxt_data = page.evaluate("() => window.__NUXT__")
                    if nuxt_data: break
                except Exception:
                    pass
            
            slugs_to_process = []
            if nuxt_data:
                apollo = nuxt_data.get('apollo', {}).get('horseClient', {})
                for k, v in apollo.items():
                    if k.startswith("Meeting:") and isinstance(v, dict):
                        events = v.get("events", [])
                        for ev in events:
                            ref = ev.get("__ref", "")
                            event_data = apollo.get(ref, {})
                            slug = event_data.get("slug")
                            race_num = event_data.get("number")
                            if slug and race_num:
                                slugs_to_process.append((race_num, slug))
            
            slugs_to_process.sort(key=lambda x: x[0])
            
            if not slugs_to_process:
                print("\n  [FATAL] Could not find race slugs for this meeting. Cloudflare block or invalid date.")
                browser.close()
                return

            print(f"  ✓ Found {len(slugs_to_process)} races for {MEETING_SLUG}")
            
            start_race = slugs_to_process[0][0]
            end_race = slugs_to_process[-1][0]
            
            output_dir = os.path.join(BASE_DIR, f"{DATE_STR} {VENUE_NAME} Race {start_race}-{end_race}")
            os.makedirs(output_dir, exist_ok=True)
            
            mm_dd = DATE_STR[5:]
            rc_file = os.path.join(output_dir, f"{mm_dd} Race {start_race}-{end_race} Racecard.md")
            fg_file = os.path.join(output_dir, f"{mm_dd} Race {start_race}-{end_race} Formguide.md")
            
            with open(rc_file, 'w', encoding='utf-8') as f_rc, open(fg_file, 'w', encoding='utf-8') as f_fg:
                for race_num, slug in slugs_to_process:
                    print(f"\n[2] Processing Race {race_num} ({slug})...")
                    print_url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={MEETING_SLUG}&eventSlug={slug}&printSlug=print-form"
                    
                    try:
                        page.goto(print_url, wait_until='domcontentloaded', timeout=40000)
                        
                        event_nuxt = None
                        for i in range(15):
                            time.sleep(1)
                            try:
                                event_nuxt = page.evaluate("() => window.__NUXT__")
                                if event_nuxt: break
                            except Exception:
                                pass
                        
                        if not event_nuxt:
                            print(f"  [WARN] NUXT not found for Race {race_num}")
                            continue

                        meta = process_selections(event_nuxt, f_rc, f_fg)
                        f_rc.flush(); f_fg.flush()
                        
                        if meta:
                            print(f"  ✓ Race {race_num} Extracted. ({meta['distance']}m)")
                            
                    except Exception as e:
                        print(f"  [ERROR] Race {race_num} Failed: {e}")
            
            browser.close()
            print(f"\n[✓] Done! Check output folder: {output_dir}")
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

if __name__ == '__main__':
    main()
