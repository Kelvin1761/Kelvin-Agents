import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Claw Code Architecture: AU Racenet Crawler
Author: Antigravity

This crawler perfectly spoofs a browser using `curl_cffi` to quickly grab raw HTML (`__NUXT__`),
and evaluates it offline via a completely invisible local Playwright instance.
Bypasses Cloudflare unconditionally with zero visual popups.
"""
import io
import json
import re
import time
import argparse
from curl_cffi import requests
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

BASE_DIR = r"."

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
            meta['track_rating'] = str(rating)
            
    # Pre-parse HTML to extract PuntingForm advanced metrics
    try:
        with open("_temporary_files/temp.html", "r", encoding="utf-8") as f:
            html_text = f.read()
        soup = BeautifulSoup(html_text, 'lxml')
        details_blocks = soup.find_all('div', class_='racing-full-form-details')
        print(f"    [PF DEBUG] Found {len(details_blocks)} full form details blocks")
    except Exception as e:
        print(f"    [PF DEBUG] Error parsing HTML: {e}")
        details_blocks = []
        
    active_idx = -1

    for sel in selections:
        num = sel.get('competitorNumber', '?')
        comp = sel.get('competitor', {}) or {}
        name = comp.get('name', 'Unknown')
        
        status = sel.get('status')
        status_abv = sel.get('statusAbv')
        is_scratched = (status_abv in ['S', 'Scratched'] or status in ['S', 'Scratched', 'SCRATCHED'])
        
        if is_scratched:
            f_rc.write(f"{num}. {name} - status:Scratched\n")
            f_fg.write(f"{num}. {name} - status:Scratched\n\n")
            continue
            
        active_idx += 1
        html_block = details_blocks[active_idx] if active_idx < len(details_blocks) else None
        html_runs = html_block.find_all('div', class_='horse-racing-previous-runs-row') if html_block else []

        
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
        rating_off = sel.get('ratingOfficial', '?')
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
        f_rc.write(f"Trainer: {trainer} | Jockey: {jockey} | Weight: {effective_weight_str} | Age: {age} | Rating: {rating_off}\n")
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
        
        for r_idx, pr in enumerate(runs):
            track = pr.get('meetingName', '')
            date = pr.get('meetingDate', '')
            dist = pr.get('eventDistance', '')
            race_num_run = pr.get('eventNumber', '')
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
            
            run_margin = pr.get('margin')
            run_margin_str = f" margin:{run_margin}L" if run_margin is not None else ""
            
            hc = pr.get('handicapRating')
            hc_str = f" HC:{hc}" if hc is not None else ""
            
            # Extract PF metrics if available
            pf_str = ""
            if r_idx < len(html_runs):
                row_text = html_runs[r_idx].get_text(separator=' ', strip=True)
                pf_match = re.search(r'Last600:\s*([-\d.]+)[^R]*(Runner Time:\s*[-\d.]+)[^R]*(Race Time:\s*[-\d.]+)[^E]*(Early Runner Pace:\s*[^.]+\.)[^E]*(Early Race Pace:\s*[^.]+\.)[^R]*(RT Rating:\s*[-\d.]+)', row_text, re.IGNORECASE)
                if pf_match:
                    pf_str = f" PF[{pf_match.group(0).strip()}]"
                else:
                    # Fallback loose match
                    loose_pf = re.search(r'Last600:.*?(?=Full Results|$)', row_text, re.IGNORECASE)
                    if loose_pf:
                        clean_pf = loose_pf.group(0).replace(' .', ',').strip()
                        pf_str = f" PF[{clean_pf}]"
            
            f_fg.write(f"{track}{trial_str} R{race_num_run} {date} {dist}m cond:{cond} ${money:,} {p_jock} ({bar}) {wt}kg {run_flucs} {win_time} {positions.strip()}.{run_margin_str}{hc_str}{pf_str}\n")
            f_fg.write(f"{win_str}, {sec_str}, {thi_str}\n")
            if r_idx == 0 and pf_str:
                print(f"    [PF DEBUG] Extracted PF for Run 0: {pf_str}")
            elif r_idx == 0:
                print(f"    [PF DEBUG] No PF match for HTML Run 0")
            f_fg.write(f"Video: {pr.get('videoComment', '')}\n")
            f_fg.write(f"Note: {pr.get('videoNote', '')}\n")
            f_fg.write(f"Stewards: {pr.get('stewardsReport', '')}\n\n")
        f_fg.write("=" * 60 + "\n\n")
    return meta

def extract_race(meeting_slug, race_num, date_str, location, page, slug_override=None):
    print(f"\n=== Processing Race {race_num} ===", flush=True)
    
    url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={meeting_slug}&eventSlug={slug_override or f'race-{race_num}'}&printSlug=print-form"
    
    try:
        resp = requests.get(url, impersonate="chrome120")
        if resp.status_code != 200:
            print(f"  Race {race_num}: HTTP Error {resp.status_code}")
            return None
            
        os.makedirs("_temporary_files", exist_ok=True)
        with open("_temporary_files/temp.html", "w", encoding="utf-8") as f:
            f.write(resp.text)
            
        abs_path = os.path.abspath("_temporary_files/temp.html")
        page.goto(f"file://{abs_path}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        
        if not nuxt_data:
            print(f"  Race {race_num}: NUXT not found. Payload may be empty.")
            return None
            
        return nuxt_data
        
    except Exception as e:
        print(f"  Race {race_num}: ERROR - {e}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Claw Code Racenet Extractor")
    parser.add_argument("--date", type=str, required=True, help="Date in YYYY-MM-DD")
    parser.add_argument("--venue", type=str, required=True, help="Venue Name (e.g. 'Sandown Lakeside')")
    parser.add_argument("--slug", type=str, required=True, help="Meeting slug (e.g. 'sandown-lakeside-20260406')")
    parser.add_argument("--races", type=int, required=True, help="Number of races to extract")
    parser.add_argument("--slugs", type=str, default="", help="Comma separated list of slugs")
    args = parser.parse_args()

    output_dir = os.path.join(BASE_DIR, f"{args.date} {args.venue} Race 1-{args.races}")
    os.makedirs(output_dir, exist_ok=True)
    
    mm_dd = args.date[5:]
    index_file = os.path.join(output_dir, f"{mm_dd} Formguide_Index.md")
    
    first_meta = None
    rail = "Unknown"
    event_slugs = []
    
    with open(index_file, 'w', encoding='utf-8') as f_idx:
        f_idx.write(f"# AU Wong Choi Formguide Index\n")
        f_idx.write(f"Meeting: {args.venue} | Date: {args.date}\n\n")
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            if args.slugs:
                event_slugs = args.slugs.split(',')
                print(f"Using provided slugs: {event_slugs}")
            else:
                # Fallback logic
                initial_data = extract_race(args.slug, 1, args.date, args.venue, page, slug_override="race-1")
                if initial_data:
                    apollo = initial_data.get('apollo', {}).get('horseClient', {})
                    meeting_key = next((k for k in apollo.keys() if k.startswith("Meeting:")), None)
                    if meeting_key:
                        events = apollo[meeting_key].get('events', [])
                        for e in events:
                            if isinstance(e, dict) and '__ref' in e:
                                event_id = e['__ref']
                                event_obj = apollo.get(event_id, {})
                                seo = event_obj.get('seo', {})
                                slug = seo.get('eventSlug')
                                if slug:
                                    event_slugs.append(slug)
                                
                if not event_slugs:
                    print("Fetching exact slugs from overview page...")
                    try:
                        # Sometimes racenet requires a sample valid overview URL, try race-1 overview structure natively
                        import re
                        ov_r = requests.get(f"https://www.racenet.com.au/form-guide/horse-racing/{args.slug}/", impersonate="chrome120")
                        
                        # Use broad match if standard fails, we know it's /form-guide/horse-racing/.../slug-race-N
                        m_slugs = re.findall(rf"/form-guide/horse-racing/{args.slug}/([^/]+?race-\d+)", ov_r.text)
                        
                        # Actually racenet overview url is https://www.racenet.com.au/form-guide/horse-racing/cranbourne-20260410/race-1/overview but we can extract it from the payload
                        # Or it forwards.
                        if not m_slugs:
                             # Some overview pages need the race-1/overview suffix
                             ov_r = requests.get(f"https://www.racenet.com.au/form-guide/horse-racing/{args.slug}/race-1/overview", impersonate="chrome120")
                             m_slugs = re.findall(rf"/form-guide/horse-racing/{args.slug}/([^/]+?race-\d+)", ov_r.text)

                        found = list(dict.fromkeys(m_slugs))
                        found.sort(key=lambda s: int(re.search(r'race-(\d+)', s).group(1)) if re.search(r'race-(\d+)', s) else 0)
                        
                        if found:
                            event_slugs = found
                        else:
                            raise Exception("No slugs found in html")
                    except Exception as e:
                        print(f"Fallback to generic race-X slugs because {e}")
                        event_slugs = [f"race-{i}" for i in range(1, args.races + 1)]
                
            for i, genuine_slug in enumerate(event_slugs[:args.races]):
                race_num = i + 1
                rc_file = os.path.join(output_dir, f"{mm_dd} Race {race_num} Racecard.md")
                fg_file = os.path.join(output_dir, f"{mm_dd} Race {race_num} Formguide.md")
                
                nuxt_data = extract_race(args.slug, race_num, args.date, args.venue, page, slug_override=genuine_slug)
                if not nuxt_data:
                    continue
                
                # Fetch global apollo data
                if rail == "Unknown":
                    apollo = nuxt_data.get('apollo', {}).get('horseClient', {})
                    for k, v in apollo.items():
                        if k.startswith("Meeting:") and isinstance(v, dict):
                            rail = v.get('railPosition', 'Unknown')
                            break
                
                form_data = nuxt_data.get('fetch', {})
                form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
                event_data = form_data.get(form_key, {}) if form_key else {}
                
                apollo = nuxt_data.get("apollo", {}).get("defaultClient", {})
                event_cache = {}
                event_id = None
                
                for k, v in apollo.items():
                    if k.startswith("Event:") and isinstance(v, dict) and v.get("__typename") == "Event":
                        if v.get("eventNumber") == race_num:
                            st = v.get("startTime", "")
                            if (args.date in st) or (args.date[:-2] in st):
                                event_cache = v
                                event_id = k.split(":")[1]
                                break

                dist = event_cache.get("distance", "?")
                event_class = event_cache.get("eventClass") or event_cache.get("class") or ""
                prize = event_cache.get("racePrizeMoney") or event_cache.get("prizeMoney") or 0
                
                track_cond = "Unknown"
                weather = "Unknown"
                
                if event_id:
                    tc_cache = apollo.get(f"$Event:{event_id}.trackCondition", {})
                    we_cache = apollo.get(f"$Event:{event_id}.weather", {})
                    
                    if we_cache:
                        w_cond = we_cache.get("condition", "").title()
                        w_temp = we_cache.get("temperature", "")
                        weather = f"{w_cond} {w_temp}C".strip()
                        
                    if tc_cache:
                        overall = tc_cache.get("overall", "")
                        rating = tc_cache.get("rating", "")
                        track_cond = f"{overall} {rating}".strip()
                
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
                
                with open(rc_file, 'w', encoding='utf-8') as f_rc, open(fg_file, 'w', encoding='utf-8') as f_fg:
                    f_rc.write(f"{header_line}\n")
                    f_rc.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*60}\n")
                    
                    f_fg.write(f"{header_line}\n")
                    f_fg.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*60}\n")
                    
                    process_selections(nuxt_data, f_rc, f_fg)
                    
                # Active logic
                sels = event_data.get('selections', [])
                active = sum(1 for s in sels if s.get('status') not in ['S', 'Scratched', 'SCRATCHED'] and s.get('statusAbv') not in ['S', 'Scratched'])
                f_idx.write(f"- **Race {race_num}**: {dist_str} | Class: {event_class} | {active} Runners\n")
                f_idx.flush()
                print(f"  Race {race_num}: SUCCESS - {dist_str} {track_cond} ({active} runners)", flush=True)
            browser.close()

    summary_file = os.path.join(output_dir, "Meeting_Summary.md")
    if first_meta:
        with open(summary_file, 'w', encoding='utf-8') as f_sum:
            f_sum.write(f"Date: {args.date}\n")
            f_sum.write(f"Venue: {args.venue}\n")
            f_sum.write(f"Track Condition: {first_meta.get('track_condition', 'Unknown')}\n")
            f_sum.write(f"Weather: {first_meta.get('weather', 'Unknown')}\n")
            f_sum.write(f"Rails: {rail}\n")
            
    print(f"\n✅ All Done! Saved to: {output_dir}")

if __name__ == '__main__':
    main()
