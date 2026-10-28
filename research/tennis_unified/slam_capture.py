"""Pinned singles archive transfer, with verified resumable per-file receipts."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import urllib.request

from .sources import verified_bytes
from .warehouse import digest, storage_guard, write_new


def capture(spec_path, output, previous_manifest):
    storage_guard(output)
    spec = json.loads(spec_path.read_text())
    if spec['repo'] != 'AngieXuAU/tennis-point-by-point-archive' or len(spec['commit']) != 40:
        raise ValueError('unexpected source/commit')
    files = spec['files']
    paths = [r['path'] for r in files]
    if len(paths) != len(set(paths)) or len(files) != spec['expected_files']:
        raise ValueError('duplicate/incomplete source roster')
    if sum(r['bytes'] for r in files) != spec['expected_bytes']:
        raise ValueError('source transfer budget changed')
    for p in paths:
        if not re.fullmatch(r'slam_pointbypoint/\d{4}-[a-z]+-(matches|points)\.csv', p):
            raise ValueError('non-singles path')
        if p.replace('-matches.csv', '-points.csv') not in paths or p.replace('-points.csv', '-matches.csv') not in paths:
            raise ValueError('unpaired event')
    output.mkdir(parents=True, exist_ok=True)
    locked = output / 'source-spec.json'
    if locked.exists():
        if locked.read_text() != spec_path.read_text():
            raise ValueError('source roster changed on resume')
    else:
        with locked.open('x') as s:
            s.write(spec_path.read_text())
    previous = json.loads(previous_manifest.read_text())
    reuse = {(r['repo'], r['commit'], r['path']): r for r in previous['files']}
    results = []
    for item in files:
        if not 0 <= item['bytes'] <= 30 * 1024**2:
            raise ValueError('per-file budget exceeded')
        relative = PurePosixPath(item['path'])
        cached = reuse.get((spec['repo'], spec['commit'], item['path']))
        destination = Path(cached['local_path']) if cached else output / relative
        receipt = output / 'receipts' / (relative.name + '.json')
        url = f"https://raw.githubusercontent.com/{spec['repo']}/{spec['commit']}/{item['path']}"
        retrieved_at = cached['retrieved_at'] if cached else None
        if destination.exists():
            raw = destination.read_bytes()
            verified_bytes(raw, item['bytes'], item['blob_sha'])
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            request = urllib.request.Request(url, headers={'User-Agent': 'WongChoi-offline-source-audit'})
            with urllib.request.urlopen(request, timeout=90) as response:
                raw = response.read(item['bytes'] + 1)
            retrieved_at = datetime.now(timezone.utc).isoformat()
            verified_bytes(raw, item['bytes'], item['blob_sha'])
            with destination.open('xb') as s:
                s.write(raw)
        result = {**item, 'repo': spec['repo'], 'commit': spec['commit'], 'url': url,
                  'local_path': str(destination), 'sha256': digest(destination),
                  'reused_original_capture': bool(cached), 'retrieved_at': retrieved_at}
        receipt.parent.mkdir(exist_ok=True)
        if receipt.exists():
            saved = json.loads(receipt.read_text())
            if any(saved[k] != result[k] for k in result if k != 'retrieved_at'):
                raise ValueError('receipt facts changed')
            result = saved
        else:
            result['verified_at'] = datetime.now(timezone.utc).isoformat()
            write_new(receipt, result)
        results.append(result)
        print(json.dumps({'verified': relative.name, 'bytes': item['bytes'], 'reused': bool(cached)}), flush=True)
    write_new(output / 'source_manifest.json', {**spec, 'files': results, 'spec_sha256': digest(locked),
              'method_sha256': digest(Path(__file__)), 'publication_clock_verified': False,
              'commercial_clearance': 'NOT_ESTABLISHED; Sackmann/Tennis Abstract NC-SA attribution; research audit only',
              'promotion_eligible': False})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--spec', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--previous-manifest', type=Path, required=True)
    a = p.parse_args()
    capture(a.spec, a.output, a.previous_manifest)


if __name__ == '__main__':
    main()
