"""Verify frozen recovery candidates and materialize isolated evidence, not scores."""
import collections
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/scripts'))
import inject_hkjc_fact_anchors as facts


def verify(item, cached):
    data = cached.get('data', {})
    digest = hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    cutoff = datetime.fromisoformat(item['meeting'][:10]).replace(tzinfo=timezone(timedelta(hours=8)))
    errors = []
    if digest != item['profile_sha256']:
        errors.append('profile_hash_changed')
    if cached.get('_ts') != item['cached_at_epoch'] or not 0 < cached.get('_ts', 0) < cutoff.timestamp():
        errors.append('invalid_or_changed_fetch_time')
    brand = item['id'].rsplit('_', 1)[-1]
    if item['cache_key'].rsplit('_', 1)[-1] != brand or data.get('name') != item['name']:
        errors.append('identity_mismatch')
    if data.get('horse_id') and data['horse_id'].rsplit('_', 1)[-1] != brand:
        errors.append('payload_identity_mismatch')
    undated = future = unknown = 0
    for entry in data.get('entries', []):
        date = facts._profile_entry_datetime(entry)
        if not date:
            undated += 1
        elif date.date() >= cutoff.date():
            future += 1
        if int(entry.get('placing') or 0) <= 0 and not entry.get('placing_raw'):
            unknown += 1
    if undated:
        errors.append('undated_history')
    if future:
        errors.append('same_day_or_future_history')
    return {'errors': errors, 'history_rows': len(data.get('entries', [])),
            'unknown_finish_status_rows': unknown}


def main(manifest_path, output):
    manifest = json.loads(manifest_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    counts = collections.Counter()
    reports = []
    caches = {}
    guides = {}
    # This audit does not need PDF extraction or any network enrichment.
    facts.get_pdf_path = lambda path: None
    for item in manifest['recovery_candidates']:
        source = Path(item['source'])
        if source not in caches:
            caches[source] = json.loads(source.read_text())
        cached = caches[source].get(item['cache_key'], {})
        result = verify(item, cached)
        meeting = source.parents[2] / item['meeting']
        key = (meeting, item['race'])
        if key not in guides:
            paths = list(meeting.glob(f'* Race {item["race"]} 賽績.md'))
            guides[key] = facts.parse_hkjc_formguide(str(paths[0]))['horses'] if len(paths) == 1 else []
        horses = [h for h in guides[key] if h['num'] == item['number'] and h['name'] == item['name']]
        result['history_gap_risk'] = True
        if len(horses) == 1:
            dates = [r['date_dt'] for r in horses[0]['races'] if r.get('date_dt')]
            # A cache older than every rich row may miss the intervening history.
            fetched = datetime.fromtimestamp(item['cached_at_epoch'], timezone(timedelta(hours=8))).date()
            result['history_gap_risk'] = not dates or fetched < min(dates).date()
        else:
            result['errors'].append('archived_form_identity_missing')
        status = 'rejected' if result['errors'] else 'identity_time_verified'
        counts[status] += 1
        if status != 'rejected':
            if result['history_gap_risk']:
                counts['verified_but_history_gap_risk'] += 1
            if result['unknown_finish_status_rows']:
                counts['verified_but_unknown_status'] += 1
            destination = output / item['meeting'] / f'R{item["race"]}_H{item["number"]}.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps({'provenance': item, 'checks': result,
                                               'profile': cached['data']}, ensure_ascii=False, indent=2))
        reports.append({**item, **result, 'status': status})
    report = {'counts': dict(counts), 'records': reports,
              'scope': 'identity/time verification only; not a model promotion or full history certification'}
    (output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report['counts'], ensure_ascii=False))


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
