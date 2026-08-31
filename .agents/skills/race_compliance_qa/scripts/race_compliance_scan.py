#!/usr/bin/env python3
"""Shared HKJC/AU racing compliance scanner.

Checks deterministic pipeline gates:
- raw extraction file validity
- Logic JSON Top4 vs Analysis Markdown Top4 drift
- result JSON parseability
- unresolved placeholders
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
from typing import Any


RAW_NAME_RE = re.compile(r'(排位表|賽績|racecard|formguide|results?|賽果)', re.IGNORECASE)
ANALYSIS_RE = re.compile(r'analysis.*\.md$|分析.*\.md$', re.IGNORECASE)
LOGIC_RE = re.compile(r'logic.*\.json$', re.IGNORECASE)
RACE_NO_RE = re.compile(r'(?:Race|R|第)\s*[_ -]?(\d+)', re.IGNORECASE)
TOP4_BLOCK_RE = re.compile(
    r'([🥇🥈🥉🏅])\s*\*\*第[一二三四]選\*\*.*?'
    r'(?:馬號及馬名|Horse(?:\s+No\.?)?)[：:]*\*?\*?\s*\[?#?(\d+)\]?',
    re.DOTALL,
)
TOP4_NUMBERED_BLOCK_RE = re.compile(
    r'\*\*第([1-4])選\*\*.*?'
    r'(?:馬號及馬名|Horse(?:\s+No\.?)?)[：:]*\*?\*?\s*\[?#?(\d+)\]?',
    re.DOTALL,
)
PLACEHOLDER_RE = re.compile(r'(\[AUTO\]|PLACEHOLDER|\{\{LLM_FILL\}\}|\[FILL\])')
ERROR_MARKERS = (
    'Error:',
    'Traceback',
    'Could not find racecard table',
    '沒有賽績紀錄',
    'Access Denied',
    'Cloudflare',
)


# Subtrees that hold FROZEN or BACKUP copies of pipeline artifacts, not live ones.
#
# `_prediction_snapshots/` is the immutable pre-race snapshot: it is SUPPOSED to
# disagree with the current Logic once a meeting is re-scored.  Walking it made
# TOP4-001 fire on every morning refresh — 2026-08-30 failed all six AU meetings
# with rc=1 while the run still recorded `status: ok` / `errors: []`.  Worse, the
# analyses map is keyed by race number, so a snapshot copy could overwrite the
# live file and the check would compare the wrong pair — a real live drift could
# be masked by a stale snapshot that happened to match.
FROZEN_DIRNAMES = frozenset({
    '_prediction_snapshots',
    '_pre_v52_backup',
    'quarantine',
})


def is_frozen_path(path: pathlib.Path, root: pathlib.Path) -> bool:
    """True if `path` lives under a frozen/backup subtree of `root`."""
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        parts = path.parts
    # The final component is the file itself; only directories gate the walk.
    for part in parts[:-1]:
        if part in FROZEN_DIRNAMES or part.startswith('.') or 'backup' in part.lower():
            return True
    return False


def iter_live_files(root: pathlib.Path, pattern: str = '*'):
    """`root.rglob(pattern)` with frozen/backup subtrees pruned.

    Sorted shallowest-first so the live artifact is always seen before any
    same-named copy deeper in the tree.
    """
    paths = [p for p in root.rglob(pattern) if not is_frozen_path(p, root)]
    paths.sort(key=lambda p: (len(p.parts), str(p)))
    return paths


class Issue:
    def __init__(self, severity: str, code: str, path: str, detail: str, race: int | None = None):
        self.severity = severity
        self.code = code
        self.path = path
        self.detail = detail
        self.race = race

    def to_dict(self) -> dict[str, Any]:
        return {
            'severity': self.severity,
            'code': self.code,
            'path': self.path,
            'detail': self.detail,
            'race': self.race,
        }


def read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='utf-8', errors='replace')


def extract_race_no(path: pathlib.Path, text: str = '') -> int | None:
    match = RACE_NO_RE.search(path.name)
    if match:
        return int(match.group(1))
    match = re.search(r'"?race_number"?\s*[:：]\s*"?(\d+)"?', text)
    if match:
        return int(match.group(1))
    return None


def parse_logic_top4(data: dict[str, Any]) -> list[str]:
    verdict = data.get('python_auto_verdict')
    if not isinstance(verdict, dict):
        verdict = data.get('race_analysis', {}).get('verdict', {})
    top4 = verdict.get('top4', []) if isinstance(verdict, dict) else []
    nums = []
    for item in top4:
        if not isinstance(item, dict):
            continue
        raw = item.get('horse_number', item.get('horse_num', item.get('num', '')))
        value = str(raw).strip()
        if value:
            nums.append(value)
    return nums


def parse_analysis_top4(text: str) -> list[str]:
    picks = []
    rank_order = {'🥇': 1, '🥈': 2, '🥉': 3, '🏅': 4}
    for match in TOP4_BLOCK_RE.finditer(text):
        picks.append((rank_order.get(match.group(1), len(picks) + 1), match.group(2)))
    for match in TOP4_NUMBERED_BLOCK_RE.finditer(text):
        picks.append((int(match.group(1)), match.group(2)))
    picks.sort(key=lambda item: item[0])
    deduped: dict[int, str] = {}
    for rank, number in picks:
        deduped.setdefault(rank, number)
    return [deduped[rank] for rank in sorted(deduped)]


# Field aliases across the results-JSON dialects we have to read. The
# `finish_position` / `competitor_number` spelling is the archive dialect (see
# parse_result_json) — every real AU Race_Results_*.json uses it.
_POS_KEYS = ('pos', 'position', 'rank', 'finish_position', 'placing')
_HORSE_NO_KEYS = ('horse_no', 'horse_number', 'num', 'competitor_number')
_NAME_KEYS = ('horse_name', 'name')


def _first_present(item: dict, keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = item.get(key)
        if value is not None and value != '':
            return value
    return None


def parse_result_rows(items: Any) -> list[tuple[int, int, str]]:
    """Parse one race's finisher rows into sorted (pos, horse_no, name)."""
    rows: list[tuple[int, int, str]] = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        # Scratched runners carry finish_position -1 in the archive dialect, and
        # parse_int() digit-scrapes that to 1 — which would invent a phantom
        # winner. Drop them before parsing, and belt-and-braces reject pos <= 0.
        if item.get('is_scratched'):
            continue
        pos = parse_int(_first_present(item, _POS_KEYS))
        horse_no = parse_int(_first_present(item, _HORSE_NO_KEYS))
        if pos is None or horse_no is None or pos <= 0:
            continue
        name = str(_first_present(item, _NAME_KEYS) or '').strip()
        rows.append((pos, horse_no, name))
    return sorted(rows, key=lambda row: row[0])


def parse_result_json(data: Any) -> dict[int, list[tuple[int, int, str]]]:
    if isinstance(data, dict) and isinstance(data.get('races'), dict):
        data = data['races']

    # Archive dialect:
    #   {"meeting": {...}, "events": {"1": {...}}, "results": {"1": [row, ...]}}
    # i.e. a top-level `results` MAPPING of race number -> finisher list. All 35
    # real AU Race_Results_*.json files (4401 rows) use this shape — note some
    # meeting folders nest a second copy of the same folder name, so search
    # recursively if you re-audit this. The generic
    # walk below cannot read it — it treats "meeting"/"events"/"results" as race
    # keys, finds no race number in them, and returns {}. That made
    # check_results_json() emit RESULT-002 ("did not yield race/position/horse
    # number rows") for every genuine results file. Handle it first.
    if isinstance(data, dict) and isinstance(data.get('results'), dict):
        parsed_archive: dict[int, list[tuple[int, int, str]]] = {}
        for key, items in data['results'].items():
            race_no = parse_int(key)
            rows = parse_result_rows(items)
            if race_no is not None and rows:
                parsed_archive[race_no] = rows
        # Only claim the archive shape if it actually produced rows; otherwise
        # fall through so an unrelated dict that happens to have a `results`
        # key still gets the generic treatment.
        if parsed_archive:
            return parsed_archive

    if isinstance(data, list):
        iterable = enumerate(data, start=1)
    elif isinstance(data, dict):
        iterable = data.items()
    else:
        return {}

    parsed: dict[int, list[tuple[int, int, str]]] = {}
    for key, race_data in iterable:
        if isinstance(race_data, list):
            match = re.search(r'(?:RaceNo=|Race[_ -]?)(\d+)', str(key), re.IGNORECASE)
            race_no = int(match.group(1)) if match else parse_int(key)
            rows = parse_result_rows(race_data)
            if race_no is not None and rows:
                parsed[race_no] = rows
            continue
        if not isinstance(race_data, dict):
            continue
        race_no = parse_int(race_data.get('race_no', key))
        rows = parse_result_rows(race_data.get('results', []))
        if race_no is not None and rows:
            parsed[race_no] = rows
    return parsed


def parse_int(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r'\d+', str(value))
    return int(match.group(0)) if match else None


def check_raw_file(path: pathlib.Path, min_size: int) -> list[Issue]:
    if not RAW_NAME_RE.search(path.name):
        return []
    issues = []
    size = path.stat().st_size
    if size < min_size:
        issues.append(Issue('CRITICAL', 'RAW-001', str(path), f'raw file suspiciously small ({size} bytes)'))
    if path.suffix.lower() in {'.md', '.txt', '.json'}:
        text = read_text(path)
        first_line = text.strip().splitlines()[0] if text.strip() else ''
        if first_line.startswith('Error:'):
            issues.append(Issue('CRITICAL', 'RAW-002', str(path), f'raw file starts with error: {first_line[:120]}'))
        for marker in ERROR_MARKERS:
            if marker in text:
                issues.append(Issue('CRITICAL', 'RAW-003', str(path), f'raw file contains error marker: {marker}'))
                break
    return issues


def check_placeholders(path: pathlib.Path) -> list[Issue]:
    if path.suffix.lower() not in {'.md', '.json', '.txt'}:
        return []
    if not (ANALYSIS_RE.search(path.name) or LOGIC_RE.search(path.name)):
        return []
    text = read_text(path)
    # Current deterministic Logic keeps the legacy scaffold for traceability,
    # but final scoring/rendering is owned by python_auto + python_auto_verdict.
    # Scan only that canonical layer when present; otherwise every valid modern
    # file is falsely rejected for dormant legacy [FILL]/[AUTO] fields.
    if LOGIC_RE.search(path.name) and path.suffix.lower() == '.json':
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return []  # LOGIC-001 is emitted by check_top4_drift.
        if isinstance(data.get('python_auto_verdict'), dict):
            canonical = {
                'python_auto_verdict': data['python_auto_verdict'],
                'horses': {
                    number: horse.get('python_auto')
                    for number, horse in (data.get('horses') or {}).items()
                    if isinstance(horse, dict)
                },
            }
            text = json.dumps(canonical, ensure_ascii=False)
    match = PLACEHOLDER_RE.search(text)
    if not match:
        return []
    return [Issue('CRITICAL', 'PLACEHOLDER-001', str(path), f'unresolved marker remains: {match.group(1)}')]


def check_results_json(path: pathlib.Path) -> list[Issue]:
    if path.suffix.lower() != '.json' or not RAW_NAME_RE.search(path.name):
        return []
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        return [Issue('CRITICAL', 'RESULT-001', str(path), f'invalid JSON: {exc}')]
    if not parse_result_json(data):
        return [Issue('CRITICAL', 'RESULT-002', str(path), 'results JSON did not yield race/position/horse number rows')]
    return []


def check_top4_drift(root: pathlib.Path) -> list[Issue]:
    issues = []
    analyses: dict[int, tuple[pathlib.Path, list[str]]] = {}
    for path in iter_live_files(root, '*.md'):
        if not ANALYSIS_RE.search(path.name):
            continue
        text = read_text(path)
        race_no = extract_race_no(path, text)
        top4 = parse_analysis_top4(text)
        if race_no is None or not top4:
            continue
        if race_no in analyses:
            # Two LIVE analyses for one race is itself a defect, but the first
            # (shallowest) one stays canonical so the drift check keeps comparing
            # the real pair instead of whichever file the walk happened to end on.
            seen_path, seen_top4 = analyses[race_no]
            if top4[:4] != seen_top4[:4]:
                issues.append(Issue(
                    'WARNING',
                    'TOP4-003',
                    str(path),
                    f'duplicate live Analysis for race {race_no}; '
                    f'keeping {seen_path.name} ({seen_top4[:4]}) over {top4[:4]}',
                    race_no,
                ))
            continue
        analyses[race_no] = (path, top4)

    for path in iter_live_files(root, '*.json'):
        if not LOGIC_RE.search(path.name):
            continue
        text = read_text(path)
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            issues.append(Issue('CRITICAL', 'LOGIC-001', str(path), f'invalid Logic JSON: {exc}'))
            continue
        race_no = extract_race_no(path, text)
        logic_top4 = parse_logic_top4(data)
        verdict = data.get('python_auto_verdict')
        ranking = verdict.get('ranking') if isinstance(verdict, dict) else None
        horses = data.get('horses')
        field_size = (
            len(ranking)
            if isinstance(ranking, list) and ranking
            else len(horses) if isinstance(horses, dict) else 4
        )
        expected_picks = min(4, field_size)
        if len(logic_top4) < expected_picks:
            issues.append(Issue(
                'CRITICAL',
                'TOP4-002',
                str(path),
                f'Logic Top4 has fewer than {expected_picks} picks: {logic_top4}',
                race_no,
            ))
            continue
        if race_no is None or race_no not in analyses:
            continue
        analysis_path, analysis_top4 = analyses[race_no]
        if analysis_top4[:4] != logic_top4[:4]:
            issues.append(Issue(
                'CRITICAL',
                'TOP4-001',
                str(analysis_path),
                f'Analysis Top4 {analysis_top4[:4]} != Logic Top4 {logic_top4[:4]}',
                race_no,
            ))
    return issues


def scan(root: pathlib.Path, min_size: int) -> list[Issue]:
    issues: list[Issue] = []
    for path in iter_live_files(root):
        if not path.is_file():
            continue
        issues.extend(check_raw_file(path, min_size))
        issues.extend(check_placeholders(path))
        issues.extend(check_results_json(path))
    issues.extend(check_top4_drift(root))
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description='Shared HKJC/AU race compliance scanner')
    parser.add_argument('--root', required=True, help='Meeting/report directory to scan')
    parser.add_argument('--platform', choices=['hkjc', 'au', 'auto'], default='auto')
    parser.add_argument('--min-size', type=int, default=100)
    parser.add_argument('--json', action='store_true', help='Output machine-readable JSON')
    args = parser.parse_args()

    root = pathlib.Path(args.root)
    if not root.exists():
        print(f'Root not found: {root}', file=sys.stderr)
        return 2

    issues = scan(root, args.min_size)
    critical = [issue for issue in issues if issue.severity == 'CRITICAL']
    status = 'failed' if critical else ('conditional' if issues else 'passed')

    if args.json:
        print(json.dumps({
            'status': status,
            'platform': args.platform,
            'root': str(root),
            'issues': [issue.to_dict() for issue in issues],
        }, ensure_ascii=False, indent=2))
    else:
        label = '❌ RACE QA FAILED' if critical else ('⚠️ RACE QA CONDITIONAL PASS' if issues else '✅ RACE QA PASSED')
        print(f'{label} — {args.platform} {root}')
        for issue in issues:
            race = f' R{issue.race}' if issue.race is not None else ''
            print(f'- [{issue.severity}] {issue.code}{race}: {issue.path} — {issue.detail}')
    return 1 if critical else 0


if __name__ == '__main__':
    raise SystemExit(main())
