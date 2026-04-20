import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import json
import re
from curl_cffi import requests
from playwright.sync_api import sync_playwright
import platform

def get_base_path():
    """Cross-platform base path for Antigravity workspace."""
    if platform.system() == 'Windows':
        return r"g:\我的雲端硬碟\Antigravity Shared\Antigravity"
    else:
        return "."

def generate_print_url(url):
    # E.g. https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview
    # To: https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug=caulfield-heath-20260304&eventSlug=briga-fliedner-2026-lady-of-racing-finalist-race-1&printSlug=print-form
    match = re.search(r'form-guide/horse-racing/([^/]+)/([^/]+)/', url)
    if not match:
        raise ValueError("Invalid Racenet URL. Format should be .../meeting-slug/event-slug/...")
    
    meeting_slug = match.group(1)
    event_slug = match.group(2)
    return f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={meeting_slug}&eventSlug={event_slug}&printSlug=print-form"

def fetch_nuxt_data(url):
    print(f"Fetching {url} with curl_cffi...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    resp = requests.get(url, impersonate="chrome120", headers=headers, timeout=30)
    resp.raise_for_status()
    
    import time
    temp_html = os.path.abspath(f"racenet_temp_{int(time.time())}.html")
    with open(temp_html, 'w') as f:
        f.write(resp.text)
    
    print("Evaluating Nuxt payload with Playwright locally...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{temp_html}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        browser.close()
        
    if os.path.exists(temp_html):
        os.remove(temp_html)
    return nuxt_data

def extract_meeting_weather(nuxt_data):
    """Extract weather & track condition from the overview page's Apollo cache.
    
    The overview page stores weather/track at $Event:{first_event_id}.weather
    and $Event:{first_event_id}.trackCondition. This is Meeting-level data
    that applies to all races but is not available in the print page payload.
    Returns a dict with weather/track info for use as fallback.
    """
    apollo = nuxt_data.get('apollo', {}).get('defaultClient', nuxt_data.get('apollo', {}).get('horseClient', {}))
    meeting_meta = {
        'weather': 'Unknown', 'weather_detail': {},
        'track_condition': 'Unknown', 'track_rating': '', 'track_surface': ''
    }
    
    # Scan for $Event:*.weather and $Event:*.trackCondition in overview Apollo cache
    for key, val in apollo.items():
        if key.endswith('.weather') and key.startswith('$Event:') and isinstance(val, dict):
            condition = val.get('condition', '')
            temp = val.get('temperature', '')
            wind = val.get('wind', '')
            humidity = val.get('humidity', '')
            if condition:
                weather_str = condition.title()
                if temp:
                    weather_str += f" {temp}°C"
                meeting_meta['weather'] = weather_str
                meeting_meta['weather_detail'] = {
                    'condition': condition,
                    'temperature': temp,
                    'feelsLike': val.get('feelsLike', ''),
                    'wind': wind,
                    'humidity': humidity,
                    'icon': val.get('conditionIcon', ''),
                    'trackConditionRating': val.get('trackConditionRating', ''),
                    'trackConditionOverall': val.get('trackConditionOverall', ''),
                }
                print(f"  🌦️ [Overview] Weather extracted: {weather_str} | Wind: {wind} | Humidity: {humidity}")
                break  # Use first event's weather (same for all races)
    
    for key, val in apollo.items():
        if key.endswith('.trackCondition') and key.startswith('$Event:') and isinstance(val, dict):
            overall = val.get('overall', '')
            rating = val.get('rating', '')
            surface = val.get('surface', '')
            if overall:
                meeting_meta['track_condition'] = f"{overall} {rating}".strip()
                meeting_meta['track_rating'] = rating
                meeting_meta['track_surface'] = surface
                print(f"  🏟️ [Overview] Track condition extracted: {overall} {rating} ({surface})")
                break  # Use first event's track condition
    
    return meeting_meta

def extract_event_metadata(nuxt_data, event_id, race_num=None, meeting_meta=None):
    """Extract distance, weather, track condition from Event-level Apollo data.
    
    Uses Event:{event_id} first, then falls back to scanning all Event:* keys
    matching by eventNumber. Falls back to meeting_meta for weather/track if
    the print page doesn't have that data. Raises ValueError if distance not found.
    """
    apollo = nuxt_data.get('apollo', {}).get('defaultClient', nuxt_data.get('apollo', {}).get('horseClient', {}))
    meta = {'distance': '?', 'distance_unit': 'm', 'event_class': '', 'prize': 0,
            'weather': 'Unknown', 'track_condition': 'Unknown', 'track_rating': ''}
    
    # Primary lookup: Event:{event_id}
    v = apollo.get(f"Event:{event_id}", {}) if event_id else {}
    
    # Fallback: scan ALL Event:* keys matching race_num
    if (not v or v.get('distance') is None) and race_num is not None:
        for k, val in apollo.items():
            if k.startswith('Event:') and isinstance(val, dict):
                if val.get('eventNumber') == race_num:
                    v = val
                    resolved_id = k.replace('Event:', '')
                    if not event_id:
                        event_id = resolved_id
                    print(f"  🔍 [Fallback] Event:{event_id} 搵唔到，用 {k} (eventNumber={race_num}) 代替")
                    break
    
    if v:
        meta['distance'] = v.get('distance', '?')
        meta['distance_unit'] = v.get('distanceUnit', 'metres')
        meta['event_class'] = v.get('eventClass', '')
        meta['prize'] = v.get('racePrizeMoney', 0) or 0
    
    # STRICT: if distance is still missing, raise error
    if meta['distance'] == '?' or meta['distance'] is None:
        print(f"\n❌ [FATAL] Race {race_num}: 無法從 Apollo cache 提取距離！")
        print(f"   event_id={event_id}")
        print(f"   Apollo keys containing 'Event': {[k for k in apollo.keys() if 'Event' in k][:20]}")
        raise ValueError(f"Race {race_num}: distance extraction failed — Apollo cache 無 Event 距離數據")
        
    v_weather = apollo.get(f"$Event:{event_id}.weather", {})
    if v_weather:
        condition = v_weather.get('condition', '')
        temp = v_weather.get('temperature', '')
        wind = v_weather.get('wind', '')
        if condition:
            meta['weather'] = condition.title()
            if temp:
                meta['weather'] += f" {temp}°C"

    v_track = apollo.get(f"$Event:{event_id}.trackCondition", {})
    if v_track:
        overall = v_track.get('overall', '')
        rating = v_track.get('rating', '')
        if overall:
            meta['track_condition'] = f"{overall} {rating}".strip()
            meta['track_rating'] = rating
    
    # Fallback to meeting-level metadata from overview page
    if meeting_meta:
        if meta['weather'] == 'Unknown' and meeting_meta.get('weather', 'Unknown') != 'Unknown':
            meta['weather'] = meeting_meta['weather']
            print(f"  🌦️ [Fallback→Overview] Weather: {meta['weather']}")
        if meta['track_condition'] == 'Unknown' and meeting_meta.get('track_condition', 'Unknown') != 'Unknown':
            meta['track_condition'] = meeting_meta['track_condition']
            meta['track_rating'] = meeting_meta.get('track_rating', '')
            print(f"  🏟️ [Fallback→Overview] Track: {meta['track_condition']}")
            
    return meta

def process_race(nuxt_data, f_rc, f_fg, race_num=None):
    form_data = nuxt_data.get('fetch', {})
    form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
    if not form_key:
         print("No FormGuidePrint data found for race.")
         return None
         
    selections = form_data.get(form_key, {}).get('selections', [])
    if not selections:
         return None
    
    event_id = ''
    match = re.search(r'\d+', form_key)
    if match:
        event_id = match.group(0)
    
    # Extract event metadata
    meta = extract_event_metadata(nuxt_data, event_id, race_num=race_num)
         
    for sel in selections:
        num = sel.get('competitorNumber', '?')
        # Look up horse name from competitor ref if needed, or sel has it?
        # sel didn't have name previously, we need to find it in Apollo cache
        c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else sel.get('competitor', {}).get('__ref', '').replace('Competitor:', '')
        
        # The selections object has a lot of data but name might be in apollo
        apollo = nuxt_data.get('apollo', {}).get('defaultClient', nuxt_data.get('apollo', {}).get('horseClient', {}))
        comp = apollo.get(f"Competitor:{c_id}", {})
        name = comp.get('name', 'Unknown')
        
        if name == 'Unknown':
             # fallback, name sometimes in selection
             name = sel.get('name', 'Unknown')
             
        # Format Racecard
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
        
        # Calculate Effective Weight
        weight_str = str(sel.get('weight', '?'))
        claim_str = str(sel.get('jockeyWeightClaim', ''))
        
        effective_weight_str = weight_str
        if claim_str and claim_str not in ['None', 'null', '0', '0.0', '']:
            try:
                base_wt = float(weight_str)
                claim_wt = float(claim_str)
                effective_wt = base_wt + claim_wt # claim_str usually usually comes as negative e.g. "-2"
                effective_weight_str = f"{effective_wt:g}kg (Base {base_wt:g}kg, Claim {claim_wt:g}kg)"
            except ValueError:
                pass
                
        age = comp.get('age', '?')
        rating = sel.get('ratingOfficial', '?')
        
        career = sel.get('stats', {}).get('career', '')
        if isinstance(career, dict):
            career = f"{career.get('starts', 0)}:{career.get('wins', 0)}-{career.get('seconds', 0)}-{career.get('thirds', 0)}"
        last10 = sel.get('stats', {}).get('lastTenFigure', '')
        win_pct = sel.get('stats', {}).get('winPercentage', 0)
        plc_pct = sel.get('stats', {}).get('placePercentage', 0)
        
        # Last race string
        last_race = ""
        runs = sel.get('forms', [])
        if runs:
             lr = runs[0]
             last_race = f"{lr.get('finishPosition')}/{lr.get('eventStarters')} {lr.get('eventDistance')}m {lr.get('meetingName', '')}"
        
        # Write row
        f_rc.write(f"{num}. {name} ({barrier})\n")
        f_rc.write(f"Trainer: {trainer} | Jockey: {jockey} | Weight: {effective_weight_str} | Age: {age} | Rating: {rating}\n")
        f_rc.write(f"Career: {career} | Last 10: {last10} | Win: {win_pct}% | Place: {plc_pct}% | Last: {last_race}\n")
        f_rc.write("-" * 40 + "\n")
        
        # --- Complex Stats Object Parsing ---
        stats = sel.get('stats', {})
        def fmt_stat(stat_key):
             s = stats.get(stat_key, '')
             if isinstance(s, dict):
                 return f"{s.get('starts', 0)}:{s.get('wins', 0)}-{s.get('seconds', 0)}-{s.get('thirds', 0)}"
             return s if s else "0:0-0-0"
             
        sire_name = comp.get('sire', 'Unknown')
        dam_name = comp.get('dam', 'Unknown')
        sire_of_dam = comp.get('sireOfDam', 'Unknown')
        
        trainer_obj = sel.get('trainer') or {}
        trainer_name = trainer_obj.get('name', 'Unknown')
        trainer_ly = trainer_obj.get('stats', {})
        trainer_ly = trainer_ly.get('lastYear', '-') if isinstance(trainer_ly, dict) else '-'
        
        jockey_obj = sel.get('jockey') or {}
        jockey_name = jockey_obj.get('name', 'Unknown')
        jockey_ly = jockey_obj.get('stats', {})
        jockey_ly = jockey_ly.get('lastYear', '-') if isinstance(jockey_ly, dict) else '-'
        
        # Formatting nicely
        f_fg.write(f"[{num}] {name} ({barrier})\n")
        
        sire_info = f"Sire: {sire_name} | Dam: {dam_name} ({sire_of_dam})"
        flucs_list = [str(f.get('value')) for f in sel.get('flucOdds', []) if isinstance(f, dict) and 'value' in f]
        flucs_str = f"Flucs: ${' $'.join(flucs_list)}" if flucs_list else "Flucs: -"
        owners = comp.get('owner', 'Unknown')
        f_fg.write(f"{age}yo{comp.get('sexShort', '?')} {comp.get('colour', '?')} | {sire_info}\n")
        f_fg.write(f"{flucs_str}\n")
        f_fg.write(f"Owners: {owners}\n")
        f_fg.write(f"T: {trainer_name} (LY: {trainer_ly}) | J: {jockey_name} (LY: {jockey_ly})\n\n")
        
        # Align stats
        prize_money = stats.get('totalPrizeMoney') or 0
        f_fg.write(f"{'Career:':<10} {fmt_stat('career'):<15} {'Last 10:':<10} {str(stats.get('lastTenFigure') or '-'):<15} {'Prize:':<10} ${prize_money:,<14}\n")
        f_fg.write(f"{'Win %:':<10} {str(stats.get('winPercentage') or 0):<15} {'Place %:':<10} {str(stats.get('placePercentage') or 0):<15} {'ROI:':<10} {str(stats.get('roi') or 0):<15}\n\n")
        
        f_fg.write(f"{'Track:':<10} {fmt_stat('track'):<15} {'Distance:':<10} {fmt_stat('distance'):<15} {'Trk/Dist:':<10} {fmt_stat('trackDistance'):<15}\n")
        f_fg.write(f"{'Firm:':<10} {fmt_stat('firm'):<15} {'Good:':<10} {fmt_stat('good'):<15} {'Soft:':<10} {fmt_stat('soft'):<15}\n")
        f_fg.write(f"{'Heavy:':<10} {fmt_stat('heavy'):<15} {'Synth:':<10} {fmt_stat('synthetic'):<15} {'Class:':<10} {fmt_stat('class'):<15}\n\n")
        
        f_fg.write(f"{'1st Up:':<10} {fmt_stat('firstUp'):<15} {'2nd Up:':<10} {fmt_stat('secondUp'):<15} {'3rd Up:':<10} {fmt_stat('thirdUp'):<15}\n")
        f_fg.write(f"{'Season:':<10} {fmt_stat('currentSeason'):<15} {'12 Month:':<10} {fmt_stat('lastYear'):<15} {'Fav:':<10} {fmt_stat('fav'):<15}\n\n")

        # --- Past Runs ---
        for pr in runs:
             date = pr.get('meetingDate', '')
             track = pr.get('meetingName', '')
             dist = pr.get('eventDistance', '')
             race_num = pr.get('eventNumber', '')
             pos = f"{pr.get('finishPosition')}/{pr.get('eventStarters')}"
             cond = pr.get('trackConditionRating', '?')
             money = pr.get('racePrizeMoney') or 0
             wt = pr.get('weightCarried', '')
             bar = pr.get('barrier', '')
             p_jock = pr.get('jockey', {}).get('name', 'Unknown') if isinstance(pr.get('jockey'), dict) else 'Unknown'
             
             run_flucs = f"Flucs:${pr.get('openPrice', '-')} ${pr.get('startingWinPriceDecimal', '-')}"
             time = pr.get('winnerTime', '')
             
             # Positions
             positions = ""
             for pref in pr.get('competitorPositionSummary', []):
                 if isinstance(pref, dict):
                     pos_str = pref.get('positionText')
                     dist_str = pref.get('distanceText')
                     if pos_str and dist_str:
                         positions += f"{pos_str}@{dist_str} "
                     elif pref.get('time'):
                         positions += f"({dist_str}/{pref.get('time')}) "
                     
             # Results strings
             win_str = f"1-{pr.get('winnerName', '')} ({pr.get('winnerWeightCarried', '')}kg)"
             sec_str = f"2-{pr.get('secondName', '')} ({pr.get('secondWeightCarried', '')}kg) {pr.get('secondMarginDecimal', '')}L"
             thi_str = f"3-{pr.get('thirdName', '')} ({pr.get('thirdWeightCarried', '')}kg) {pr.get('thirdMarginDecimal', '')}L"
             
             # Advanced sectionals if present in apollo (the new RT style)
             sect_str = f"Last600: {pr.get('last600', '-')} RT Rating: {pr.get('rtRating', '-')}"
             
             trial_str = " **(TRIAL)**" if pr.get('isTrial') else ""
             
             f_fg.write(f"{track}{trial_str} R{race_num} {date} {dist}m cond:{cond} ${money:,} {p_jock} ({bar}) {wt}kg {run_flucs} {time} {positions.strip()}.\n")
             f_fg.write(f"{win_str}, {sec_str}, {thi_str}\n")
             f_fg.write(f"Video: {pr.get('videoComment', '')}\n")
             f_fg.write(f"Note: {pr.get('videoNote', '')}\n")
             f_fg.write(f"Stewards: {pr.get('stewardsReport', '')}\n\n")
        f_fg.write("=" * 60 + "\n\n")
    return meta

def process_meeting(overview_url, date_str, location):
    # 1. Fetch overview page to get meeting events
    print("Extracting Meeting Overview...")
    nuxt_overview = fetch_nuxt_data(overview_url)
    apollo = nuxt_overview.get('apollo', {}).get('defaultClient', nuxt_overview.get('apollo', {}).get('horseClient', {}))
    
    match = re.search(r'form-guide/horse-racing/([^/]+)', overview_url)
    if not match:
         print("Invalid meeting URL")
         return
    meeting_slug = match.group(1)
    
    meeting_key = None
    for k, v in apollo.items():
         if k.startswith("Meeting:") and v.get('slug') == meeting_slug:
             meeting_key = k
             break
             
    if not meeting_key:
         print(f"Could not find meeting {meeting_slug} in Nuxt payload")
         return
         
    events = apollo[meeting_key].get('events', [])
    race_slugs = []
    for e in events:
         e_id = e.get('id')
         if e_id and e_id in apollo:
             race_slugs.append((apollo[e_id].get('eventNumber'), apollo[e_id].get('slug')))
             
    race_slugs.sort(key=lambda x: x[0] if x[0] else 99)
    print(f"Found {len(race_slugs)} races for {location}")
    
    start_race = race_slugs[0][0] if race_slugs else 1
    end_race = race_slugs[-1][0] if race_slugs else len(race_slugs)
    
    # Check if a specific race is targeted
    global target_race
    if target_race and target_race != 'all':
        try:
             if '-' in str(target_race):
                 start_r, end_r = map(int, str(target_race).split('-'))
                 race_slugs = [r for r in race_slugs if r[0] is not None and start_r <= r[0] <= end_r]
                 start_race = start_r
                 end_race = end_r
                 print(f"Filtering to Race {start_r}-{end_r}.")
             else:
                 target_num = int(target_race)
                 race_slugs = [r for r in race_slugs if r[0] == target_num]
                 start_race = target_num
                 end_race = target_num
                 print(f"Filtering to Race {target_num} only.")
        except ValueError:
             pass
             
    base = get_base_path()
    output_dir = os.path.join(base, f"{date_str} {location} Race {start_race}-{end_race}")
    os.makedirs(output_dir, exist_ok=True)
    
    rail = apollo[meeting_key].get('railPosition', 'Unknown')
    mm_dd = date_str[5:]
    
    # Extract meeting-level weather/track from overview page (the print page often lacks this)
    meeting_meta = extract_meeting_weather(nuxt_overview)
    print(f"\n📋 Meeting-level metadata: Weather={meeting_meta['weather']}, Track={meeting_meta['track_condition']}")
    
    # Track metadata for index generation
    race_index = []
    first_meta = None
    
    for race_num, slug in race_slugs:
        print(f"\nProcessing Race {race_num}...")
        
        print_url = f"https://www.racenet.com.au/form-guide/horse-racing/print?meetingSlug={meeting_slug}&eventSlug={slug}&printSlug=print-form"
        race_nuxt = fetch_nuxt_data(print_url)
        
        # Extract per-race metadata
        form_data = race_nuxt.get('fetch', {})
        form_key = next((k for k in form_data.keys() if k.startswith('FormGuidePrint')), None)
        event_id = ''
        if form_key:
            match_ev = re.search(r'\d+', form_key)
            if match_ev:
                event_id = match_ev.group(0)
        
        # Also try extracting event_id from Apollo __ref in fetch data
        if form_key and not event_id:
            sel_data = form_data.get(form_key, {})
            if isinstance(sel_data, dict):
                ev_ref = sel_data.get('event', {}).get('__ref', '')
                if ev_ref.startswith('Event:'):
                    event_id = ev_ref.replace('Event:', '')
        
        meta = extract_event_metadata(race_nuxt, event_id, race_num=race_num, meeting_meta=meeting_meta)
        if first_meta is None:
            first_meta = meta
        
        dist_str = f"{meta['distance']}m" if meta['distance'] != '?' else ''
        track_cond = meta.get('track_condition', 'Unknown')
        weather = meta.get('weather', 'Unknown')
        event_class = meta.get('event_class', '')
        prize = meta.get('prize', 0)
        
        header_line = f"RACE {race_num}"
        if dist_str:
            header_line += f" — {dist_str}"
        if event_class:
            header_line += f" | {event_class}"
        if prize:
            header_line += f" | ${prize:,}"
        
        # Collect horse names for index
        selections = form_data.get(form_key, {}).get('selections', []) if form_key else []
        horse_list = []
        for sel in selections:
            num = sel.get('competitorNumber', '?')
            c_id = sel.get('competitor', {}).get('id') if isinstance(sel.get('competitor'), dict) else ''
            apollo_race = race_nuxt.get('apollo', {}).get('defaultClient', race_nuxt.get('apollo', {}).get('horseClient', {}))
            comp = apollo_race.get(f"Competitor:{c_id}", {})
            h_name = comp.get('name', sel.get('name', 'Unknown'))
            scratched = sel.get('statusAbv') in ['S', 'Scratched'] or sel.get('status') in ['S', 'Scratched', 'SCRATCHED']
            horse_list.append((num, h_name, scratched))
        
        active_count = sum(1 for _, _, s in horse_list if not s)
        
        # Write per-race files (split output)
        rc_file = os.path.join(output_dir, f"{mm_dd} Race {race_num} Racecard.md")
        fg_file = os.path.join(output_dir, f"{mm_dd} Race {race_num} Formguide.md")
        
        with open(rc_file, 'w', encoding='utf-8') as f_rc, \
             open(fg_file, 'w', encoding='utf-8') as f_fg:
            f_rc.write(f"{header_line}\n")
            f_rc.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*20}\n")
            f_rc.flush()
            
            f_fg.write(f"{header_line}\n")
            f_fg.write(f"Track: {track_cond} | Weather: {weather} | Rail: {rail}\n{'='*20}\n")
            
            process_race(race_nuxt, f_rc, f_fg, race_num=race_num)
        
        race_index.append({
            'race_num': race_num,
            'distance': dist_str,
            'class': event_class,
            'horses': active_count,
            'total': len(horse_list),
            'horse_list': horse_list,
            'fg_file': f"{mm_dd} Race {race_num} Formguide.md",
            'rc_file': f"{mm_dd} Race {race_num} Racecard.md",
        })
    
    # Generate Formguide Index (lightweight file for Smart Slice Protocol)
    index_file = os.path.join(output_dir, f"{mm_dd} Formguide_Index.md")
    with open(index_file, 'w', encoding='utf-8') as f_idx:
        f_idx.write(f"# {date_str} {location} — Formguide Index\n\n")
        f_idx.write("| Race | Distance | Class | Runners | Formguide | Racecard |\n")
        f_idx.write("|------|----------|-------|---------|-----------|----------|\n")
        for ri in race_index:
            f_idx.write(f"| R{ri['race_num']} | {ri['distance']} | {ri['class']} | {ri['horses']}/{ri['total']} | {ri['fg_file']} | {ri['rc_file']} |\n")
        
        f_idx.write("\n## Horse Quick Reference\n\n")
        for ri in race_index:
            f_idx.write(f"### Race {ri['race_num']} ({ri['distance']})\n")
            for num, name, scratched in ri['horse_list']:
                status = " ❌SCR" if scratched else ""
                f_idx.write(f"- [{num}] {name}{status}\n")
            f_idx.write("\n")
    
    # Write Meeting Summary (use meeting_meta which has rich weather detail)
    summary_file = os.path.join(output_dir, "Meeting_Summary.md")
    final_weather = meeting_meta.get('weather', first_meta.get('weather', 'Unknown') if first_meta else 'Unknown')
    final_track = meeting_meta.get('track_condition', first_meta.get('track_condition', 'Unknown') if first_meta else 'Unknown')
    final_surface = meeting_meta.get('track_surface', '')
    weather_detail = meeting_meta.get('weather_detail', {})
    
    with open(summary_file, 'w', encoding='utf-8') as f_sum:
        f_sum.write(f"Date: {date_str}\n")
        f_sum.write(f"Track Condition: {final_track}\n")
        if final_surface:
            f_sum.write(f"Surface: {final_surface}\n")
        f_sum.write(f"Weather: {final_weather}\n")
        if weather_detail:
            f_sum.write(f"Wind: {weather_detail.get('wind', 'N/A')}\n")
            f_sum.write(f"Humidity: {weather_detail.get('humidity', 'N/A')}\n")
            f_sum.write(f"Feels Like: {weather_detail.get('feelsLike', 'N/A')}°C\n")
        f_sum.write(f"Rails: {rail}\n")
    
    print(f"\nGenerated per-race files in: {output_dir}")
    for ri in race_index:
        print(f"  R{ri['race_num']}: {ri['fg_file']} ({ri['horses']} runners)")
    print(f"  Index: {mm_dd} Formguide_Index.md")
    print(f"OUTPUT DIRECTORY: {output_dir}")

target_race = "all"
if __name__ == '__main__':
    url = "https://www.racenet.com.au/form-guide/horse-racing/caulfield-heath-20260304/briga-fliedner-2026-lady-of-racing-finalist-race-1/overview"
    if len(sys.argv) > 1:
        url = sys.argv[1]
    if len(sys.argv) > 2:
        target_race = sys.argv[2]
        
    match = re.search(r'form-guide/horse-racing/([^/]+)', url)
    if match is None:
        print("Invalid URL format.")
        sys.exit(1)
        
    meeting_slug = str(match.group(1))
    parts = meeting_slug.split('-')
    
    # Extract date from the end of the slug if available
    date_str = ""
    location = ""
    if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) == 8:
        date_raw = str(parts[-1])
        date_str = f"{date_raw[0:4]}-{date_raw[4:6]}-{date_raw[6:8]}"  # YYYY-MM-DD
        location = " ".join(parts[:-1]).title()
    else:
        import datetime
        date_str = datetime.datetime.now().strftime("%Y-%m-%d")
        location = " ".join(parts).title()
        
    process_meeting(url, date_str, location)
