"""Create-only multi-book source inventory; never combine opposite books.

Historical quotes without capture clocks are training/development data only.
No prediction, strategy, price threshold or model parameter is selected here.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import urllib.error
import urllib.request

import openpyxl

from research.tennis_unified.warehouse import digest, storage_guard, write_new


YEARS = tuple(range(2020, 2026))


def paired_columns(header):
    names = set(header)
    # W1/L1 are set scores, and Max/Avg are aggregate prices, not bookmakers.
    return sorted(prefix for prefix in (name[:-1] for name in names if re.fullmatch(r'[A-Za-z0-9]{2,}W', name))
                  if prefix+'L' in names and prefix.lower() not in ('max', 'avg'))


def valid_pair(winner, loser):
    if isinstance(winner, bool) or isinstance(loser, bool):
        return False
    try:
        values = float(winner), float(loser)
    except (TypeError, ValueError):
        return False
    return all(math.isfinite(value) and value > 1 for value in values)


def event_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for pattern in ('%Y-%m-%d', '%d/%m/%Y'):
            try:
                return datetime.strptime(value, pattern).date()
            except ValueError:
                pass
    return None


def workbook_inventory(path, expected_year):
    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        iterator = book.active.iter_rows(values_only=True)
        header = [str(value).strip() if value is not None else '' for value in next(iterator)]
        pairs, statuses, invalid_dates, dates = Counter(), Counter(), [], []
        roster = paired_columns(header)
        count = 0
        for line, values in enumerate(iterator, start=2):
            if not any(value is not None for value in values):
                continue
            count += 1
            row = dict(zip(header, values))
            day = event_date(row.get('Date'))
            if day is None or day.year != expected_year:
                invalid_dates.append({'xlsx_row': line, 'raw_date': str(row.get('Date'))})
            else:
                dates.append(day.isoformat())
            statuses[str(row.get('Comment'))] += 1
            for prefix in roster:
                pairs[prefix] += valid_pair(row.get(prefix+'W'), row.get(prefix+'L'))
        return {'rows': count, 'columns': header, 'book_price_prefixes': roster,
                'valid_paired_prices': dict(pairs), 'invalid_or_wrong_year_dates': invalid_dates,
                'earliest_valid_event_date': min(dates) if dates else None,
                'latest_valid_event_date': max(dates) if dates else None,
                'status_counts': dict(statuses), 'quote_clock_verified': False,
                'quote_type': 'source column semantics must be verified; no blanket opening/closing claim'}
    finally:
        book.close()


def capture(cache, output):
    storage_guard(output)
    output.mkdir(exist_ok=False)
    sources = []
    for tour in ('atp', 'wta'):
        for year in YEARS:
            name = f'tennisdata_{tour}_{year}.xlsx'
            destination, cached = output/name, cache/name
            url = f'https://www.tennis-data.co.uk/{year}{"w" if tour == "wta" else ""}/{year}.xlsx'
            record = {'tour': tour.upper(), 'year': year, 'url': url,
                      'captured_at': datetime.now(timezone.utc).isoformat()}
            if cached.exists():
                shutil.copyfile(cached, destination)
                record.update(method='existing_frozen_cache_copy', cache_path=str(cached),
                              original_sha256=digest(cached))
            else:
                try:
                    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 tennis-wc-offline-research'})
                    with urllib.request.urlopen(request, timeout=60) as response:
                        raw = response.read(6*1024**2+1)
                    if len(raw) > 6*1024**2 or not raw.startswith(b'PK'):
                        raise ValueError('not a size-bounded XLSX archive')
                    with destination.open('xb') as stream:
                        stream.write(raw)
                except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                    record.update(status='MISSING_SOURCE', error=str(exc))
                    sources.append(record)
                    print(f'{tour} {year}: MISSING_SOURCE', flush=True)
                    continue
                record['method'] = 'new_immutable_download'
            record.update(status='captured', local_path=str(destination),
                          bytes=destination.stat().st_size, sha256=digest(destination),
                          inventory=workbook_inventory(destination, year))
            sources.append(record)
            print(f'{tour} {year}: captured', flush=True)
    payload = {'sources': sources, 'complete_requested_sources': all(row['status'] == 'captured' for row in sources),
               'split': 'SEEN_DEV', 'promotion_eligible': False, 'model_training_started': False,
               'implementation_sha256': digest(Path(__file__)),
               'qualification': 'All requested sources listed, including unavailable ones. Missing years do not silently shrink any experiment. '
                                'Paired prices are same-book columns; no Max/Avg or cross-book fallback. Unknown quote clocks remain unverified.'}
    write_new(output/'book_source_inventory.json', payload)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.cache, args.output)
    print(json.dumps({'complete_requested_sources': result['complete_requested_sources'], 'sources': len(result['sources'])}))


if __name__ == '__main__':
    main()
