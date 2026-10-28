"""Freeze installed Tennis runtime identity without exposing environment secrets."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess

from research.tennis_unified.warehouse import digest, write_new


LABELS = ('daily', 'card', 'preclose', 'recovery')
ENVIRONMENT_KEYS = ('DATABASE_URL', 'TENNIS_PYTHON_BIN', 'PYTHONPATH')


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def capture(output: Path, models: Path) -> dict:
    output.mkdir(exist_ok=False)
    agents, roots, databases, interpreters = [], set(), set(), set()
    for suffix in LABELS:
        label = 'com.antigravity.tennis-wong-choi.' + suffix
        path = Path.home() / 'Library/LaunchAgents' / (label + '.plist')
        raw = plistlib.loads(path.read_bytes())
        env = {key: raw.get('EnvironmentVariables', {}).get(key) for key in ENVIRONMENT_KEYS}
        if raw.get('Label') != label or not raw.get('WorkingDirectory'):
            raise ValueError('installed Tennis runtime identity incomplete')
        roots.add(Path(raw['WorkingDirectory']).resolve().parent)
        databases.add(env['DATABASE_URL'])
        interpreters.add(env['TENNIS_PYTHON_BIN'])
        state = subprocess.run(['launchctl', 'print', f'gui/{os.getuid()}/{label}'],
                               capture_output=True, text=True)
        if state.returncode:
            raise ValueError('installed scheduler is not loaded: ' + label)
        agents.append({'label': label, 'plist_path': str(path), 'plist_sha256': digest(path),
                       'working_directory': raw['WorkingDirectory'], 'environment_paths': env,
                       'program_arguments': raw['ProgramArguments'], 'loaded': True,
                       'state': [line.strip() for line in state.stdout.splitlines()
                                 if 'state =' in line or 'last exit code =' in line]})
    if len(roots) != 1 or len(databases) != 1 or len(interpreters) != 1 or None in databases or None in interpreters:
        raise ValueError('Tennis runtime paths disagree')
    root, database, interpreter = roots.pop(), databases.pop(), interpreters.pop()
    before = git(root, 'rev-parse', 'HEAD')
    files = []
    for source in sorted((root / 'tennis-wong-choi/src/tennis_wc').rglob('*')):
        if source.is_file() and source.suffix in ('.py', '.json') and '__pycache__' not in source.parts:
            relative = source.relative_to(root)
            destination = output / 'source' / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if digest(source) != digest(destination):
                raise ValueError('runtime source changed during capture')
            files.append({'path': str(relative), 'sha256': digest(destination)})
    after = git(root, 'rev-parse', 'HEAD')
    if before != after:
        raise ValueError('runtime commit changed during capture')
    registry = json.loads(models.read_text())['tennis']
    version = subprocess.check_output([interpreter, '-c',
        'import sys,numpy;print(sys.version);print("numpy="+numpy.__version__)'], text=True).strip()
    result = {'captured_at': datetime.now(timezone.utc).isoformat(), 'agents': agents,
              'runtime_root': str(root), 'runtime_commit': before,
              'runtime_status': git(root, 'status', '--porcelain'),
              'database_url': database, 'python': interpreter, 'versions': version,
              'registered_tennis_model': registry, 'model_inventory_sha256': digest(models),
              'source_files': files, 'promotion_eligible': False,
              'qualification': 'Runtime checkout and registered model identity are separate; neither proves prediction-time source provenance.'}
    write_new(output / 'runtime_manifest.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--models-json', type=Path, required=True)
    args = parser.parse_args()
    result = capture(args.output, args.models_json)
    print(json.dumps({k: result[k] for k in ('runtime_commit', 'registered_tennis_model', 'versions')}))


if __name__ == '__main__':
    main()
