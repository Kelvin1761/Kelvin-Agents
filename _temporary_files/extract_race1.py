import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import os
import time
from playwright.sync_api import sync_playwright
import lightpanda_utils

BASE_DIR = r"/Users/imac/Library/CloudStorage/GoogleDrive-kelvin1761@gmail.com/我的雲端硬碟/Antigravity Shared/Antigravity"
MEETING_SLUG = "randwick-20260404"
EVENT_SLUG = "widden-kindergarten-stakes-race-1"
RACE_NUM = 1
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
        if cond: meta['weather'] = cond.title()
    
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
                effective_weight_str = f"{float(weight_str) + float(claim_str):g}kg (+{float(claim_str)})"
            except: pass
        
        age = comp.get('age', '?')
        sex_short = comp.get('sexShort', '?')
        colour = comp.get('colour', '?')
        rating = sel.get('ratingOfficial', '?')
        stats = sel.get('stats', {}) or {}
        
        def fmt_stat(k):
            s = stats.get(k, '')
            if isinstance(s, dict): return f"{s.get('starts',0)}:{s.get('wins',0)}-{s.get('seconds',0)}-{s.get('thirds',0)}"
            return s if s else "0:0-0-0"
        
        career = fmt_stat('career')
        last10 = stats.get('lastTenFigure', '') or '-'
        win_pct = stats.get('winPercentage', 0) or 0
        plc_pct = stats.get('placePercentage', 0) or 0
        
        runs = sel.get('forms', []) or []
        last_race = f"{runs[0].get('finishPosition')}/{runs[0].get('eventStarters')} {runs[0].get('eventDistance')}m" if runs else ""
        
        # RACECARD
        f_rc.write(f"{num}. {name} ({barrier})\n")
        f_rc.write(f"Trainer: {trainer} | Jockey: {jockey} | Weight: {effective_weight_str} | Age: {age} | Rating: {rating}\n")
        f_rc.write(f"Career: {career} | Last 10: {last10} | Win: {win_pct}% | Place: {plc_pct}% | Last: {last_race}\n")
        f_rc.write("-" * 40 + "\n")
        
        # FORMGUIDE
        sire = comp.get('sire', 'Unknown')
        dam = comp.get('dam', 'Unknown')
        sire_dam = comp.get('sireOfDam', 'Unknown')
        owner = comp.get('owner', 'Unknown')
        t_ly = trainer_obj.get('stats', {}).get('lastYear', '-') if isinstance(trainer_obj.get('stats'), dict) else '-'
        j_ly = jockey_obj.get('stats', {}).get('lastYear', '-') if isinstance(jockey_obj.get('stats'), dict) else '-'
        
        f_fg.write(f"[[{num}]] {name} ({barrier})\n")
        f_fg.write(f"{age}yo{sex_short} {colour} | Sire: {sire} | Dam: {dam} ({sire_dam})\n")
        flucs = [str(f.get('value')) for f in sel.get('flucOdds', []) if isinstance(f, dict) and 'value' in f]
        f_fg.write(f"Flucs: ${' $'.join(flucs)}" if flucs else "Flucs: -\n")
        f_fg.write(f"\nOwners: {owner}\n")
        f_fg.write(f"T: {trainer} (LY: {t_ly}) | J: {jockey} (LY: {j_ly})\n\n")
        
        prize = stats.get('totalPrizeMoney') or 0
        f_fg.write(f"{'Career:':<10} {fmt_stat('career'):<15} {'Last 10:':<10} {str(last10):<15} {'Prize:':<10} ${prize:<14,}\n")
        f_fg.write(f"{'Win %:':<10} {str(win_pct):<15} {'Place %:':<10} {str(plc_pct):<15} {'ROI:':<10} {str(stats.get('roi',0)):<15}\n\n")
        
        f_fg.write(f"{'Track:':<10} {fmt_stat('track'):<15} {'Distance:':<10} {fmt_stat('distance'):<15} {'Trk/Dist:':<10} {fmt_stat('trackDistance'):<15}\n")
        f_fg.write(f"{'Firm:':<10} {fmt_stat('firm'):<15} {'Good:':<10} {fmt_stat('good'):<15} {'Soft:':<10} {fmt_stat('soft'):<15}\n")
        f_fg.write(f"{'Heavy:':<10} {fmt_stat('heavy'):<15} {'Synth:':<10} {fmt_stat('synthetic'):<15} {'Class:':<10} {fmt_stat('class'):<15}\n\n")
        
        f_fg.write(f"{'1st Up:':<10} {fmt_stat('firstUp'):<15} {'2nd Up:':<10} {fmt_stat('secondUp'):<15} {'3rd Up:':<10} {fmt_stat('thirdUp'):<15}\n")
        f_fg.write(f"{'Season:':<10} {fmt_stat('currentSeason'):<15} {'12 Month:':<10} {fmt_stat('lastYear'):<15} {'Fav:':<10} {fmt_stat('fav'):<15}\n\n")
        
        for pr in runs:
            track_name = pr.get('meetingName', '')
            r_date = pr.get('meetingDate', '')
            r_dist = pr.get('eventDistance', '')
            r_num = pr.get('eventNumber', '')
            cond = pr.get('trackConditionRating', '?')
            money = pr.get('racePrizeMoney') or 0
            wt = pr.get('weightCarried', '')
            bar = pr.get('barrier', '')
            p_j = pr.get('jockey', {}).get('name', 'Unknown') if isinstance(pr.get('jockey'), dict) else 'Unknown'
            run_flucs = f"Flucs:${pr.get('openPrice', '-')} ${pr.get('startingWinPriceDecimal', '-')}"
            w_time = pr.get('winnerTime', '')
            
            p_str = "".join([f"{p.get('positionText')}@{p.get('distanceText')} " for p in pr.get('competitorPositionSummary', []) if isinstance(p, dict) and p.get('positionText')])
            w1 = f"1-{pr.get('winnerName', '')} ({pr.get('winnerWeightCarried', '')}kg)"
            w2 = f"2-{pr.get('secondName', '')} ({pr.get('secondWeightCarried', '')}kg)"
            w3 = f"3-{pr.get('thirdName', '')} ({pr.get('thirdWeightCarried', '')}kg)"
            
            trial = " **(TRIAL)**" if pr.get('isTrial') else ""
            f_fg.write(f"{track_name}{trial} R{r_num} {r_date} {r_dist}m cond:{cond} ${money:,} {p_j} ({bar}) {wt}kg {run_flucs} {w_time} {p_str.strip()}\n")
            f_fg.write(f"{w1}, {w2}, {w3}\n")
            if pr.get('videoComment'): f_fg.write(f"Video: {pr.get('videoComment')}\n")
            if pr.get('videoNote'): f_fg.write(f"Note: {pr.get('videoNote')}\n")
            if pr.get('stewardsReport'): f_fg.write(f"Stewards: {pr.get('stewardsReport')}\n")
            f_fg.write("\n")
        f_fg.write("=" * 60 + "\n\n")
    return meta

def main():
    print(f"\n============================================================")
    print(f"AU Race Extractor (Race 1 Only) — {VENUE_NAME} {DATE_STR}")
    print(f"============================================================\n")

    use_lightpanda, lp_proc = lightpanda_utils.start_lightpanda(BASE_DIR)
    
    try:
        with sync_playwright() as p:
            if use_lightpanda: browser = p.chromium.connect_over_cdp("ws://127.0.0.1:9222")
            else: browser = p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
            
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            
            output_dir = os.path.join(BASE_DIR, "Architeve Race Analysis", f"{DATE_STR} {VENUE_NAME} Race 1-1")
            os.makedirs(output_dir, exist_ok=True)
            mm_dd = DATE_STR[5:]
            rc_file = os.path.join(output_dir, f"{mm_dd} Race 1-1 Racecard.md")
            fg_file = os.path.join(output_dir, f"{mm_dd} Race 1-1 Formguide.md")
            
            with open(rc_file, 'w', encoding='utf-8') as f_rc, open(fg_file, 'w', encoding='utf-8') as f_fg:
                print(f"[1] Processing Race {RACE_NUM} ({EVENT_SLUG})...")
                print_url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={MEETING_SLUG}&eventSlug={EVENT_SLUG}&printSlug=print-form"
                print(f"URL: {print_url}")
                
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
                        print(f"  [ERROR] NUXT not found! Cloudflare blocked or URL invalid.")
                    else:
                        meta = process_selections(event_nuxt, f_rc, f_fg)
                        if meta: print(f"  ✓ Race {RACE_NUM} Extracted. ({meta['distance']}m)")
                except Exception as e:
                    print(f"  [ERROR] Extraction failed: {e}")
            
            browser.close()
            print(f"\n[✓] Finished processing. Target: {output_dir}")
    finally:
        lightpanda_utils.stop_lightpanda(lp_proc)

if __name__ == '__main__':
    main()
