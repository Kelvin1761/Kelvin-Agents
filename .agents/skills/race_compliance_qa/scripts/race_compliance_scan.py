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
PLACEHOLDER_RE = re.compile(r'(\[AUTO\]|PLACEHOLDER|\{\{LLM_FILL\}\}|\[FILL\])')
ERROR_MARKERS = (
    'Error:',
    'Traceback',
    'Could not find racecard table',
    '沒有賽績紀錄',
    'Access Denied',
    'Cloudflare',
)


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
    picks.sort(key=lambda item: item[0])
    return [num for _, num in picks]


def parse_result_json(data: Any) -> dict[int, list[tuple[int, int, str]]]:
    if isinstance(data, dict) and isinstance(data.get('races'), dict):
        data = data['races']
    if isinstance(data, list):
        iterable = enumerate(data, start=1)
    elif isinstance(data, dict):
        iterable = data.items()
    else:
        return {}

    parsed: dict[int, list[tuple[int, int, str]]] = {}
    for key, race_data in iterable:
        if not isinstance(race_data, dict):
            continue
        race_no = parse_int(race_data.get('race_no', key))
        rows = []
        for item in race_data.get('results', []):
            if not isinstance(item, dict):
                continue
            pos = parse_int(item.get('pos') or item.get('position') or item.get('rank'))
            horse_no = parse_int(item.get('horse_no') or item.get('horse_number') or item.get('num'))
            if pos is None or horse_no is None:
                continue
            name = str(item.get('horse_name') or item.get('name') or '').strip()
            rows.append((pos, horse_no, name))
        if race_no is not None and rows:
            parsed[race_no] = sorted(rows, key=lambda row: row[0])
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
    for path in root.rglob('*.md'):
        if not ANALYSIS_RE.search(path.name):
            continue
        text = read_text(path)
        race_no = extract_race_no(path, text)
        top4 = parse_analysis_top4(text)
        if race_no is not None and top4:
            analyses[race_no] = (path, top4)

    for path in root.rglob('*.json'):
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
        if len(logic_top4) < 4:
            issues.append(Issue('CRITICAL', 'TOP4-002', str(path), f'Logic Top4 has fewer than 4 picks: {logic_top4}', race_no))
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
    for path in root.rglob('*'):
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
