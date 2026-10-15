#!/usr/bin/env python3
"""Read-only official Tasracing time-source feasibility audit. No live writes."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import statistics
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

from au_neutral_speed_20261015 import ROOT
from au_racing_engine import full_time_speed as live

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}


def workbook(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        strings = [''.join(si.itertext()) for si in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        sheets = [n for n in archive.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)]
        if len(sheets) != 1:
            raise ValueError('expected one meeting sheet')
        rows = []
        for row in ET.fromstring(archive.read(sheets[0])).findall('.//m:row', NS):
            cells = {}
            for c in row:
                v = c.find('m:v', NS)
                if v is None:
                    continue
                value = v.text
                if c.get('t') == 's':
                    value = strings[int(value)]
                cells[re.sub(r'\d+', '', c.get('r'))] = value
            rows.append(cells)
        return rows


def parse(raw, meeting, races, attachment):
    rows = workbook(raw)
    # Daily Sectionals includes populated row 2/3; retain actual XML row indices below.
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        root = ET.fromstring(z.read('xl/worksheets/sheet1.xml'))
        indices = [int(r.get('r')) for r in root.findall('.//m:row', NS)]
    indexed = dict(zip(indices, rows))
    sheet_date = (datetime(1899, 12, 30)+timedelta(days=float(indexed[2]['C']))).date().isoformat()
    sheet_venue = indexed[3]['C']
    if sheet_date != meeting['meetDate'][:10]:
        raise ValueError('workbook date mismatch')
    api_venue = meeting['track']['venueName']
    venue = live.normalize_venue_name(api_venue)
    if venue == 'devonport' and sheet_venue == 'Devonport Tapeta Synthetic':
        venue = 'devonportsynthetic'
    elif live.normalize_venue_name(sheet_venue) != venue:
        raise ValueError('unverified workbook/API venue binding: '+sheet_venue+'/'+api_venue)
    metadata = {int(r['raceNumber']): r for r in races['race']}
    sections, number, header = {}, None, False
    counts = Counter()
    for r in rows:
        match = re.fullmatch(r'RACE\s+(\d+)', str(r.get('A', '')).strip())
        if match:
            number, header = int(match[1]), False
            sections.setdefault(number, [])
            continue
        if r.get('E') == 'IVRTIME':
            header = all(str(r.get(c, '')).replace(' ', '') == label for c, label in
                         [('B', 'DISTANCE'), ('C', 'Winner'), ('H', 'TO800M'), ('K', 'L800')])
            continue
        if not number or not header or not r.get('C') or not r.get('E'):
            continue
        try:
            if int(float(r.get('A', '0'))) <= 0:
                counts['non_finisher'] += 1
                continue
            distance, total, early, l800 = int(float(r['B'])), float(r['E']), float(r['H']), float(r['K'])
            splits = [float(r[c]) for c in ('X', 'Y', 'Z', 'AA')]
            if (distance <= 800 or not 8 < distance/total < 22 or early <= 0
                    or any(v <= 0 for v in splits) or abs(total-early-l800) > .035
                    or abs(sum(splits)-l800) > .045):
                counts['invalid_time_identity'] += 1
                continue
            sections[number].append({'horse': live.norm(r['C']), 'distance': distance,
                'time': total, 'early': early, 'l800': l800, 'source': attachment['url']})
        except (ValueError, KeyError, ZeroDivisionError):
            counts['invalid_runner'] += 1
    events = []
    for number, rr in sections.items():
        meta = metadata.get(number, {})
        if len(rr) < 3 or len({r['horse'] for r in rr}) != len(rr):
            counts['insufficient_or_duplicate_runners'] += 1
            continue
        if any(r['distance'] != meta.get('raceDistance') for r in rr):
            counts['race_distance_mismatch'] += 1
            continue
        timing = meta.get('raceTiming') or {}
        going_raw = (timing.get('trackCondition') or {}).get('value', '')
        going = live.condition_key(going_raw)
        if going not in ('good', 'soft', 'heavy', 'firm', 'synthetic'):
            counts['unknown_going'] += 1
            continue
        if venue == 'devonportsynthetic' and going != 'synthetic':
            counts['unverified_synthetic'] += 1
            continue
        distance = rr[0]['distance']
        key = (venue, sheet_date, number, distance)
        for r in rr:
            r['key'] = key
        published = max(attachment['date'], attachment.get('modified', attachment['date']))
        events.append({'key': key, 'track': venue, 'date': sheet_date, 'distance': distance,
            'going': going, 'rating': str((timing.get('trackCondition') or {}).get('numericTrackRating') or 'unknown'),
            'rail': 'unknown', 'rail_raw': str(indexed.get(6, {}).get('C', 'unknown')),
            'class': live.class_key('RaceClass:['+str(meta.get('nameRaceForm', ''))+']'),
            'rows': rr, 'total': statistics.median(r['time'] for r in rr),
            'early': statistics.median(r['early'] for r in rr),
            'source_provider': 'tasracing_daily_sectionals_video', 'source_url': attachment['url'],
            'published_at_utc': published.replace(' ', 'T')+'Z',
            'historical_capture_certified': False,
            'workbook_track_rating': indexed.get(7, {}).get('C'),
            'meeting_code': meeting['meetCode']})
    counts['accepted_races'] = len(events)
    counts['accepted_runners'] = sum(len(e['rows']) for e in events)
    return events, counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    receipts = []
    def fetch(url):
        path = args.cache/(hashlib.sha256(url.encode()).hexdigest()+('.xlsx' if url.endswith('.xlsx') else '.json'))
        if not path.exists():
            for attempt in range(3):
                try:
                    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=45) as response:
                        raw = response.read(5_000_001)
                    if len(raw) > 5_000_000:
                        raise ValueError('source exceeds 5MB limit')
                    path.write_bytes(raw)
                    path.with_suffix(path.suffix+'.capture').write_text(datetime.now(timezone.utc).isoformat())
                    break
                except Exception:
                    if attempt == 2:
                        raise
                    time.sleep(attempt+1)
        raw = path.read_bytes()
        receipts.append({'url': url, 'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                         'captured_at': path.with_suffix(path.suffix+'.capture').read_text()})
        return raw
    meetings = []
    for month in range(1, 11):
        data = json.loads(fetch(f'https://stride.racing-api.com/meeting/all/calendar?Month={month}&Year=2026'))
        meetings.extend(m for m in data['meeting'] if m['meetType'] == 'Thoroughbred'
                        and not m['isTrial'] and m['meetDate'][:10] <= '2026-10-14')
    def one(meeting):
        code = meeting['meetCode']
        try:
            reports = json.loads(fetch(f'https://test.tasracing.com.au/wp-json/wp/v2/report?meetingcode={code}'))
            attachments = [r['acf']['thoroughbred_sectionals_csv'] for r in reports
                           if (r.get('acf') or {}).get('thoroughbred_sectionals_csv')]
            if len(attachments) != 1:
                return [], {'meeting': code, 'status': 'no_unique_xlsx', 'attachments': len(attachments)}
            attachment = attachments[0]
            if not re.fullmatch(r'https://test\.tasracing\.com\.au/wp-content/uploads/[^?#]+\.xlsx', attachment['url']):
                return [], {'meeting': code, 'status': 'unsupported_format'}
            races = json.loads(fetch(f'https://stride.racing-api.com/meeting/races/{code}'))
            events, counts = parse(fetch(attachment['url']), meeting, races, attachment)
            return events, {'meeting': code, 'date': meeting['meetDate'][:10], 'status': 'parsed', **counts}
        except Exception as exc:
            return [], {'meeting': code, 'status': 'error', 'error': str(exc)}
    events, audit = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        for ee, aa in pool.map(one, meetings):
            events.extend(ee)
            audit.append(aa)
            print(aa, flush=True)
    args.out.write_text(json.dumps({'events': events, 'meetings': audit, 'receipts': receipts}, indent=2))
    print('TOTAL', len(meetings), len(events), sum(len(e['rows']) for e in events), flush=True)


if __name__ == '__main__':
    main()
