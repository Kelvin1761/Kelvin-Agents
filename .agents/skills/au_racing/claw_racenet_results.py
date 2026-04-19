import os
os.environ.setdefault('PYTHONUTF8', '1')
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
"""
Claw Code Architecture: AU Racenet Results Crawler
Author: Antigravity

Extracts race results from Racenet results pages using the same
curl_cffi + Playwright Hybrid SSR State Extraction pattern as
claw_racenet_scraper.py.

Outputs a structured results file (.md) compatible with
reflector_auto_stats.py and reflector_report_skeleton.py.

Usage:
  python claw_racenet_results.py --url "https://www.racenet.com.au/results/horse-racing/cranbourne-20260417/all-races"
  python claw_racenet_results.py --url "..." --output_dir "/path/to/meeting_dir"
  python claw_racenet_results.py --url "..." --json   # Output JSON instead of markdown
"""
import sys
import io
import os
import json
import re
import argparse
from curl_cffi import requests
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ──────────────────────────────────────────────
# Apollo Cache Resolver
# ──────────────────────────────────────────────

def resolve_ref(apollo, ref_obj):
    """Resolve a single Apollo __ref to its cached object."""
    if isinstance(ref_obj, dict):
        ref_id = ref_obj.get('__ref') or ref_obj.get('id')
        if ref_id and ref_id in apollo:
            return apollo[ref_id]
        # Sometimes id is in generated format like $Selection:X.result
        gen_id = ref_obj.get('id')
        if gen_id and gen_id in apollo:
            return apollo[gen_id]
    return ref_obj


def resolve_refs(apollo, ref_list):
    """Resolve a list of Apollo __ref objects."""
    if not isinstance(ref_list, list):
        return []
    return [resolve_ref(apollo, r) for r in ref_list]


# ──────────────────────────────────────────────
# Data Extraction
# ──────────────────────────────────────────────

def extract_meeting(apollo):
    """Extract meeting-level info."""
    for k, v in apollo.items():
        if k.startswith("Meeting:") and isinstance(v, dict):
            return {
                'id': v.get('id'),
                'name': v.get('name', 'Unknown'),
                'slug': v.get('slug', ''),
                'rail': v.get('railPosition', 'Unknown'),
                'date_utc': v.get('meetingDateUtc', ''),
                'date_local': v.get('meetingDateLocal', ''),
                'track_comments': v.get('trackComments', ''),
            }
    return {}


def extract_events(apollo):
    """Extract all events (races) and their data."""
    events = {}
    for k, v in apollo.items():
        if k.startswith("Event:") and not k.startswith("$") and isinstance(v, dict):
            eid = v.get('id', k.split(':')[1])
            event_num = v.get('eventNumber')
            if event_num is None:
                continue

            # Track condition
            tc_key = f"$Event:{eid}.trackCondition"
            tc = apollo.get(tc_key, {})
            track_cond = f"{tc.get('overall', '')} {tc.get('rating', '')}".strip() or 'Unknown'

            # Weather
            we_key = f"$Event:{eid}.weather"
            we = apollo.get(we_key, {})
            weather = we.get('condition', 'Unknown')

            events[event_num] = {
                'id': eid,
                'event_number': event_num,
                'name': v.get('name', ''),
                'slug': v.get('slug', ''),
                'distance': v.get('distance', '?'),
                'event_class': v.get('eventClass', ''),
                'prize_money': v.get('racePrizeMoney', 0) or 0,
                'winning_time': v.get('winningTime', ''),
                'track_type': v.get('trackType', ''),
                'track_condition': track_cond,
                'weather': weather,
                'starters': v.get('starters', 0),
                'is_resulted': v.get('isResulted', False),
                'pace': v.get('pace'),
                'selections_refs': v.get('selections', []),
            }
    return events


def extract_race_results(apollo, event):
    """Extract full results for a single race event."""
    results = []
    sel_refs = event.get('selections_refs', [])

    for sel_ref in sel_refs:
        sel_id = None
        if isinstance(sel_ref, dict):
            sel_id = sel_ref.get('id', '').replace('Selection:', '')
        if not sel_id:
            continue

        sel_key = f"Selection:{sel_id}"
        sel = apollo.get(sel_key, {})
        if not sel or not isinstance(sel, dict):
            continue

        # Skip scratched
        status = sel.get('status', '')
        status_abv = sel.get('statusAbv', '')
        is_scratched = status_abv in ('S', 'LR') or 'scratch' in status.lower()

        # Get result
        result_key = f"$Selection:{sel_id}.result"
        result = apollo.get(result_key, {})

        finish_pos = result.get('finishPosition', 99) if result else 99
        margin = result.get('margin', None) if result else None
        finish_time = result.get('finishTime', '') if result else ''

        # Competitor info
        comp_ref = sel.get('competitor', {})
        comp = resolve_ref(apollo, comp_ref) if isinstance(comp_ref, dict) else {}

        # Jockey info
        jockey_ref = sel.get('jockey', {})
        jockey = resolve_ref(apollo, jockey_ref) if isinstance(jockey_ref, dict) else {}

        # Trainer info
        trainer_ref = sel.get('trainer', {})
        trainer = resolve_ref(apollo, trainer_ref) if isinstance(trainer_ref, dict) else {}

        # Position summaries
        pos_summaries = []
        if result and result.get('competitorPositionSummary'):
            for ps_ref in result['competitorPositionSummary']:
                ps = resolve_ref(apollo, ps_ref)
                if isinstance(ps, dict):
                    pos_summaries.append({
                        'distance': ps.get('distanceText', ''),
                        'position': ps.get('positionText', ''),
                    })

        entry = {
            'competitor_number': sel.get('competitorNumber', '?'),
            'barrier': sel.get('barrierNumber', '?'),
            'horse_name': comp.get('name', 'Unknown') if isinstance(comp, dict) else 'Unknown',
            'age': comp.get('age', '?') if isinstance(comp, dict) else '?',
            'sex': comp.get('sexShort', '?') if isinstance(comp, dict) else '?',
            'sire': comp.get('sire', '') if isinstance(comp, dict) else '',
            'dam': comp.get('dam', '') if isinstance(comp, dict) else '',
            'jockey': jockey.get('name', 'Unknown') if isinstance(jockey, dict) else 'Unknown',
            'trainer': trainer.get('name', 'Unknown') if isinstance(trainer, dict) else 'Unknown',
            'weight': sel.get('weight', '?'),
            'starting_price': sel.get('startingPrice', None),
            'finish_position': finish_pos,
            'margin': margin,
            'finish_time': finish_time,
            'position_summaries': pos_summaries,
            'is_scratched': is_scratched,
            'status': status,
            'comments': sel.get('comments', ''),
        }
        results.append(entry)

    # Sort by finish position
    results.sort(key=lambda x: (x['is_scratched'], x['finish_position'] if isinstance(x['finish_position'], int) else 99))
    return results


def extract_exotic_results(apollo, event_id):
    """Extract exotic results (quinella, trifecta etc) for an event."""
    # ExoticResults are not directly linked to events in the Apollo cache
    # We collect all and match by context
    exotics = []
    for k, v in apollo.items():
        if k.startswith("ExoticResult:") and isinstance(v, dict):
            exotics.append({
                'tote': v.get('tote', ''),
                'market': v.get('exoticMarket', ''),
                'amount': v.get('amount', ''),
                'results': v.get('results', ''),
            })
    return exotics


# ──────────────────────────────────────────────
# Output Formatters
# ──────────────────────────────────────────────

def format_markdown(meeting, events, all_results):
    """Format results as markdown compatible with reflector_auto_stats.py."""
    lines = []
    date_str = meeting.get('date_local', meeting.get('date_utc', ''))[:10]
    venue = meeting.get('name', 'Unknown')

    lines.append(f"# {venue} — Race Results ({date_str})")
    lines.append(f"**Rail:** {meeting.get('rail', 'Unknown')}")
    lines.append(f"**Track Comments:** {meeting.get('track_comments', 'N/A')}")
    lines.append("")

    for race_num in sorted(events.keys()):
        ev = events[race_num]
        results = all_results.get(race_num, [])
        active_results = [r for r in results if not r['is_scratched']]

        lines.append(f"---")
        lines.append(f"## Race {race_num}: {ev['name']}")
        lines.append(f"**Distance:** {ev['distance']}m | **Class:** {ev['event_class']} | "
                      f"**Prize:** ${ev['prize_money']:,} | **Starters:** {ev['starters']}")
        lines.append(f"**Track:** {ev['track_condition']} | **Weather:** {ev['weather']} | "
                      f"**Track Type:** {ev['track_type']}")
        if ev['winning_time']:
            lines.append(f"**Winning Time:** {ev['winning_time']}")
        lines.append("")

        # Results table
        lines.append("| Pos | # | Horse | Barrier | Jockey | Trainer | Weight | Margin | SP | Time |")
        lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|")

        for r in active_results:
            pos = r['finish_position']
            pos_str = str(pos) if isinstance(pos, int) and pos < 99 else 'DNF'
            margin_str = f"{r['margin']}L" if r['margin'] is not None and r['margin'] > 0 else '—'
            sp_str = f"${r['starting_price']:.2f}" if r['starting_price'] else '—'
            time_str = r['finish_time'] or '—'

            lines.append(f"| {pos_str} | {r['competitor_number']} | {r['horse_name']} | "
                          f"{r['barrier']} | {r['jockey']} | {r['trainer']} | "
                          f"{r['weight']}kg | {margin_str} | {sp_str} | {time_str} |")

        # Scratched
        scratched = [r for r in results if r['is_scratched']]
        if scratched:
            sc_names = ", ".join([f"#{r['competitor_number']} {r['horse_name']}" for r in scratched])
            lines.append(f"\n**Scratched:** {sc_names}")

        # In-running positions for top 3
        lines.append("")
        lines.append("**In-Running (Top 3):**")
        for r in active_results[:3]:
            if r['position_summaries']:
                pos_str = " → ".join([f"{ps['position']}@{ps['distance']}" for ps in r['position_summaries']])
                lines.append(f"- #{r['competitor_number']} {r['horse_name']}: {pos_str}")

        lines.append("")

    return "\n".join(lines)


def format_reflector_results(meeting, events, all_results):
    """Format results in the exact format expected by reflector_auto_stats.py.

    The reflector pipeline expects a simple format with:
      ## Race N
      1st: #X HorseName
      2nd: #X HorseName
      3rd: #X HorseName
    """
    lines = []
    date_str = meeting.get('date_local', meeting.get('date_utc', ''))[:10]
    venue = meeting.get('name', 'Unknown')

    lines.append(f"# {venue} Race Results — {date_str}")
    lines.append("")

    for race_num in sorted(events.keys()):
        results = all_results.get(race_num, [])
        active = [r for r in results if not r['is_scratched'] and isinstance(r['finish_position'], int) and r['finish_position'] < 99]

        lines.append(f"## Race {race_num}")
        ordinals = {1: '1st', 2: '2nd', 3: '3rd', 4: '4th'}
        for r in active[:4]:
            pos_label = ordinals.get(r['finish_position'], f"{r['finish_position']}th")
            margin_str = f" ({r['margin']}L)" if r['margin'] is not None and r['margin'] > 0 else ""
            sp_str = f" SP${r['starting_price']:.2f}" if r['starting_price'] else ""
            lines.append(f"{pos_label}: #{r['competitor_number']} {r['horse_name']}{margin_str}{sp_str}")
        lines.append("")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def fetch_and_extract(url):
    """Fetch the results page and extract __NUXT__ data."""
    print(f"🔍 Fetching: {url}", flush=True)
    resp = requests.get(url, impersonate="chrome120")
    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code} — trying without /all-races...")
        # Try stripping /all-races
        alt_url = url.rstrip('/').rsplit('/', 1)[0] if '/all-races' in url else url + '/race-1'
        resp = requests.get(alt_url, impersonate="chrome120")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch results page: HTTP {resp.status_code}")

    print(f"✅ HTTP 200 — {len(resp.text)} bytes", flush=True)

    # Save temp HTML
    os.makedirs("_temporary_files", exist_ok=True)
    temp_path = os.path.abspath("_temporary_files/temp_results.html")
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(resp.text)

    # Extract __NUXT__ via Playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"file://{temp_path}")
        nuxt_data = page.evaluate("() => window.__NUXT__")
        browser.close()

    if not nuxt_data:
        raise RuntimeError("__NUXT__ payload not found in page")

    print("✅ __NUXT__ extracted successfully", flush=True)
    return nuxt_data


def process_nuxt(nuxt_data):
    """Process extracted NUXT data into structured results."""
    apollo = nuxt_data.get('apollo', {}).get('defaultClient', {})
    if not apollo:
        raise RuntimeError("No Apollo defaultClient data found")

    meeting = extract_meeting(apollo)
    events = extract_events(apollo)
    all_results = {}

    for race_num, event in sorted(events.items()):
        results = extract_race_results(apollo, event)
        all_results[race_num] = results
        active = [r for r in results if not r['is_scratched']]
        print(f"  Race {race_num}: {len(active)} runners | "
              f"Winner: #{active[0]['competitor_number']} {active[0]['horse_name']}" if active else
              f"  Race {race_num}: No results", flush=True)

    return meeting, events, all_results


def main():
    parser = argparse.ArgumentParser(description="Claw Code Racenet Results Extractor")
    parser.add_argument("--url", type=str, required=True,
                        help="Racenet results URL (e.g. .../cranbourne-20260417/all-races)")
    parser.add_argument("--output_dir", type=str, default=None,
                        help="Directory to save results (default: same dir as script)")
    parser.add_argument("--json", action="store_true",
                        help="Also output raw JSON data")
    parser.add_argument("--reflector", action="store_true", default=True,
                        help="Generate reflector-compatible results file (default: True)")
    args = parser.parse_args()

    # Extract
    nuxt_data = fetch_and_extract(args.url)
    meeting, events, all_results = process_nuxt(nuxt_data)

    if not events:
        print("❌ No events found in data")
        sys.exit(2)

    # Determine output dir
    output_dir = args.output_dir or "."
    os.makedirs(output_dir, exist_ok=True)

    venue = meeting.get('name', 'Unknown')
    date_str = meeting.get('date_local', meeting.get('date_utc', ''))[:10]

    # === Write full results markdown ===
    full_md = format_markdown(meeting, events, all_results)
    full_path = os.path.join(output_dir, f"Race_Results_{venue.replace(' ', '_')}_{date_str}.md")
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(full_md)
    print(f"\n📄 Full results saved: {full_path}")

    # === Write reflector-compatible results ===
    if args.reflector:
        refl_md = format_reflector_results(meeting, events, all_results)
        refl_path = os.path.join(output_dir, f"Race_Results_Reflector.md")
        with open(refl_path, 'w', encoding='utf-8') as f:
            f.write(refl_md)
        print(f"📄 Reflector results saved: {refl_path}")

    # === Write JSON (optional) ===
    if args.json:
        json_data = {
            'meeting': meeting,
            'events': {str(k): v for k, v in events.items()},
            'results': {str(k): v for k, v in all_results.items()},
        }
        # Remove non-serializable refs
        for ev in json_data['events'].values():
            ev.pop('selections_refs', None)
        json_path = os.path.join(output_dir, f"Race_Results_{venue.replace(' ', '_')}_{date_str}.json")
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2, default=str)
        print(f"📄 JSON results saved: {json_path}")

    print(f"\n✅ Done! {len(events)} races extracted for {venue} ({date_str})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
