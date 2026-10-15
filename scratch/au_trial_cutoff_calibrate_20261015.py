"""Calibrate field health from fresh candidate scores, never old live outputs."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.agents/skills/shared_racing/scripts'))
import data_contract  # noqa: E402

source = Path('/private/tmp/au-trial-cutoff-6.json')
destination = Path('/private/tmp/au-trial-cutoff-calibration')
for race in json.loads(source.read_text())['races']:
    if race['date'] < '2026-08-05':
        continue
    directory = destination / race['meeting']
    directory.mkdir(parents=True, exist_ok=True)
    horses = {}
    for row in race['rows']:
        horses[str(row['n'])] = {'python_auto': {
            'feature_scores': row['features'],
            'wet_form_feature': row['wet'],
            'proven_class_feature': row['proven_class'],
            'race_context': {'going': row.get('going')},
        }}
    (directory / f"Race_{race['race']}_Logic.json").write_text(json.dumps({'horses': horses}))
data_contract.resolve_root = lambda platform: destination if platform == 'au' else None
raise SystemExit(data_contract.main(['--platform', 'au', '--calibrate', '--since', '2026-08-05', '--limit', '2000']))
