"""Read-only archive identity audit. Never substitute later profiles into scoring."""
import collections
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.agents/scripts'))
import inject_hkjc_fact_anchors as facts


def main(root):
    counts = collections.Counter()
    issues = []
    sources = collections.defaultdict(list)
    for path in root.glob('*/.hkjc_cache/profile_cache.json'):
        for key, value in json.loads(path.read_text()).items():
            sources[key.rsplit('_', 1)[-1]].append((path, key, value))
    for meeting in sorted(root.iterdir()):
        files = list(meeting.glob('Race_*_Logic.json')) if meeting.is_dir() else []
        if not files:
            continue
        cache_file = meeting / '.hkjc_cache/profile_cache.json'
        cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
        by_brand = collections.defaultdict(list)
        for key, value in cache.items():
            by_brand[key.rsplit('_', 1)[-1]].append(value['data'])
        for file in files:
            data = json.loads(file.read_text())
            number = data['race_analysis']['race_number']
            guides = list(meeting.glob(f'* Race {number} 賽績.md'))
            old = data['horses']
            counts['races'] += 1
            counts['runner_records'] += len(old)
            if len(guides) != 1:
                counts['missing_guide_identity'] += len(old)
                continue
            # Only consult the racecard; never parse PDF or fetch the web.
            rows, changes = facts._reconcile_racecard(str(guides[0]), [
                {'num': int(n), 'name': h['horse_name'],
                 'brand_no': h.get('hkjc_horse_id') or h.get('horse_code', ''),
                 'races': []} for n, h in old.items()])
            counts['racecard_logic_name_conflicts'] += len(changes)
            counts['removed_runner_records'] += len(set(old) - {str(r['num']) for r in rows})
            for row in rows:
                hid = row.get('brand_no', '')
                candidates = by_brand.get(hid.rsplit('_', 1)[-1], [])
                matched = [p for p in candidates if p.get('name') == row['name']]
                if matched:
                    counts['racecard_id_and_name_matched'] += 1
                else:
                    counts['unresolved_racecard_id'] += 1
                    issues.append({'meeting': meeting.name, 'race': number,
                                   'number': row['num'], 'name': row['name'], 'id': hid,
                                   'reason': 'id_name_conflict' if candidates else 'id_not_in_meeting_cache'})
    recovery_counts = collections.Counter()
    recovery = []
    for issue in issues:
        cutoff = datetime.fromisoformat(issue['meeting'][:10]).replace(
            tzinfo=timezone(timedelta(hours=8))).timestamp()
        matches = [(p, k, v) for p, k, v in sources[issue['id'].rsplit('_', 1)[-1]]
                   if v.get('data', {}).get('name') == issue['name']]
        eligible = [(p, k, v) for p, k, v in matches if 0 < v.get('_ts', 0) < cutoff]
        if eligible:
            path, key, value = max(eligible, key=lambda item: item[2]['_ts'])
            recovery_counts['earlier_cache_candidate'] += 1
            recovery.append({**issue, 'source': str(path), 'cache_key': key,
                             'cached_at_epoch': value['_ts'],
                             'profile_sha256': hashlib.sha256(json.dumps(value['data'], sort_keys=True,
                                                                        ensure_ascii=False).encode()).hexdigest()})
        else:
            recovery_counts['only_later_or_undated' if matches else 'no_matching_cache'] += 1
    output = {'counts': dict(counts), 'issues': issues,
              'recovery_counts': dict(recovery_counts), 'recovery_candidates': recovery}
    if len(sys.argv) > 2:
        Path(sys.argv[2]).write_text(json.dumps(output, ensure_ascii=False, indent=2))
    print(json.dumps({'counts': dict(counts), 'recovery_counts': dict(recovery_counts), 'issue_reasons': dict(collections.Counter(i['reason'] for i in issues)),
                      'examples': issues[:5]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
