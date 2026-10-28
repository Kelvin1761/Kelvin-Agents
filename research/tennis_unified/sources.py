"""Transfer pinned CSVs with Git-blob verification, then audit source schemas.

GitHub connector supplies repository/tree metadata. This byte-transfer fallback
is needed for CSVs its Contents reader returns empty above the file-size limit.
No downloaded source code or model is executed.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import csv
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request

from research.tennis_unified.warehouse import digest, storage_guard, write_new


def verified_bytes(raw: bytes, expected_size: int, blob_sha: str) -> None:
    if len(raw) != expected_size:
        raise ValueError('source size mismatch')
    actual = hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
    if actual != blob_sha:
        raise ValueError('Git blob SHA mismatch')


def download(spec: dict, output: Path) -> dict:
    storage_guard(output)
    output.mkdir(exist_ok=False)
    results = []
    for item in spec['files']:
        relative = PurePosixPath(item['path'])
        if relative.is_absolute() or '..' in relative.parts or item['bytes'] > 30 * 1024**2:
            raise ValueError('unsafe path or source exceeds predeclared transfer budget')
        if len(item['commit']) != 40:
            raise ValueError('immutable commit required')
        url = f"https://raw.githubusercontent.com/{item['repo']}/{item['commit']}/{item['path']}"
        started = datetime.now(timezone.utc).isoformat()
        request = urllib.request.Request(url, headers={'User-Agent': 'WongChoi-offline-source-audit'})
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(item['bytes'] + 1)
        verified_bytes(raw, item['bytes'], item['blob_sha'])
        destination = output / item['repo'] / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb') as stream:
            stream.write(raw)
        results.append({**item, 'url': url, 'started_at': started,
                        'retrieved_at': datetime.now(timezone.utc).isoformat(),
                        'local_path': str(destination), 'sha256': digest(destination)})
        print('verified ' + item['path'], flush=True)
    manifest = {**spec, 'files': results, 'implementation_sha256': digest(Path(__file__)),
                'commercial_clearance': 'NOT_ESTABLISHED; NC-SA attribution recorded; research capture only',
                'model_training_started': False, 'promotion_eligible': False}
    write_new(output / 'source_manifest.json', manifest)
    return manifest


def csv_rows(path: Path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def qualify_metadata(rows):
    valid, held = [], []
    for line, row in enumerate(rows, start=2):
        reasons = []
        if None in row or any(value is None for value in row.values()):
            reasons.append('column_count_mismatch')
        try:
            value = row.get('Date', '')
            parsed = datetime.strptime(value, '%Y%m%d')
            if len(value) != 8 or parsed.strftime('%Y%m%d') != value:
                raise ValueError('noncanonical date')
        except (ValueError, TypeError):
            reasons.append('invalid_event_date')
        if row.get('Surface') not in ('Hard', 'Clay', 'Grass', 'Carpet'):
            reasons.append('invalid_surface')
        if row.get('Best of') not in ('3', '5'):
            reasons.append('invalid_match_format')
        if not row.get('Player 1') or not row.get('Player 2') or row.get('Player 1') == row.get('Player 2'):
            reasons.append('invalid_participants')
        if reasons:
            held.append({'csv_line': line, 'match_id': row.get('match_id'), 'reasons': reasons,
                         'raw_values': {str(k): v for k, v in row.items()}})
        else:
            valid.append(row)
    return valid, held


def audit(manifest: dict) -> dict:
    paths = {item['path']: Path(item['local_path']) for item in manifest['files']}
    for item in manifest['files']:
        if digest(Path(item['local_path'])) != item['sha256']:
            raise ValueError('captured source changed')
    result = {'scope': manifest['scope'], 'mcp': {}, 'slam_sample': {},
              'unavailable': manifest['unavailable'], 'model_training_started': False,
              'promotion_eligible': False, 'publication_clock_verified': False}
    for tour, prefix in [('ATP', 'm'), ('WTA', 'w')]:
        raw_metadata = csv_rows(paths[f'charting-{prefix}-matches.csv'])
        metadata, held = qualify_metadata(raw_metadata)
        overview = csv_rows(paths[f'charting-{prefix}-stats-Overview.csv'])
        match_ids = Counter(row['match_id'] for row in metadata)
        stat_ids = {row['match_id'] for row in overview}
        dates = [row['Date'] for row in metadata if row.get('Date')]
        result['mcp'][tour] = {'raw_metadata_rows': len(raw_metadata),
            'typed_metadata_rows': len(metadata), 'held_rows': held, 'unique_matches': len(match_ids),
            'duplicate_match_keys': sum(n-1 for n in match_ids.values()), 'overview_rows': len(overview),
            'overview_columns': list(overview[0]) if overview else [],
            'metadata_without_overview': len(set(match_ids)-stat_ids),
            'overview_without_metadata': len(stat_ids-set(match_ids)),
            'earliest_event_date': min(dates) if dates else None,
            'latest_event_date': max(dates) if dates else None,
            'surfaces': dict(Counter(row.get('Surface') or 'MISSING' for row in metadata)),
            'rounds': dict(Counter(row.get('Round') or 'MISSING' for row in metadata)),
            'missing_time': sum(not row.get('Time') for row in metadata),
            'missing_player_names': sum(not row.get('Player 1') or not row.get('Player 2') for row in metadata),
            'identity_join': 'names/date/tournament/round require canonical reconciliation before use',
            'availability': 'event Date/Time is not chart submission/publication time',
            'sampling': 'crowdsourced charting selection; population coverage not yet measured against frozen match corpus'}
    matches = csv_rows(paths['slam_pointbypoint/2024-usopen-matches.csv'])
    points = csv_rows(paths['slam_pointbypoint/2024-usopen-points.csv'])
    match_ids = Counter(row['match_id'] for row in matches)
    point_ids = Counter((row['match_id'], row.get('PointNumber')) for row in points)
    point_matches = {row['match_id'] for row in points}
    result['slam_sample'] = {'event': '2024 US Open only', 'metadata_rows': len(matches),
        'unique_match_ids': len(match_ids), 'point_rows': len(points),
        'duplicate_match_keys': sum(n-1 for n in match_ids.values()),
        'duplicate_match_point_keys': sum(n-1 for n in point_ids.values()),
        'metadata_without_points': len(set(match_ids)-point_matches),
        'points_without_metadata': len(point_matches-set(match_ids)),
        'metadata_columns': list(matches[0]) if matches else [],
        'point_columns': list(points[0]) if points else [],
        'blank_metadata_fields': {key: sum(not row.get(key) for row in matches) for key in matches[0]} if matches else {},
        'point_server_values': dict(Counter(row.get('PointServer', 'MISSING') for row in points)),
        'point_winner_values': dict(Counter(row.get('PointWinner', 'MISSING') for row in points)),
        'qualification': 'Paired-schema sample only; parser/terminal-state/full-corpus/retirement audit remains required'}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    transfer = sub.add_parser('download')
    transfer.add_argument('--spec', type=Path, required=True)
    transfer.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('audit')
    check.add_argument('--manifest', type=Path, required=True)
    check.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'download':
        result = download(json.loads(args.spec.read_text()), args.output)
        print(json.dumps({'verified_files': len(result['files'])}))
    else:
        result = audit(json.loads(args.manifest.read_text()))
        write_new(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
