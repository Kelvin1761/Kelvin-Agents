#!/usr/bin/env python3
"""Recover blank AU result times from official evidence and dated formguides."""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import shutil
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from au_archive_calibrator import ARCHIVE_ROOT, HISTORICAL_RESULTS_CSV
from au_result_identity import normalize_venue_name
from au_results_ingest import result_identity, results_csv_lock

METRES_PER_LENGTH = 2.8  # EXP-20261127-10
FORM_LINE = re.compile(r'^\s*(?:[-*]\s*)?(.+?)\s+R(\d+)\s+(\d{4}-\d{2}-\d{2})\s+(\d+)m\b.*?\bWinningTime:((?:\d+:)?\d+(?:\.\d+)?)\b', re.I)
# 匹馬自己往績行嘅馬位差／名次。reflector 路徑嘅 CSV 行好多冇 margin（寫「—」），
# 2026-07 有 608 行係咁；formguide 嗰行就有（EXP-20261127-10）。
FORM_RUNNER = re.compile(r'\bmargin:([\d.]+)L\b.*?\bfinish:(\d+)/\d+')
FORM_HORSE = re.compile(r'^\[\d+\]\s+(.+?)(?:\s+\([^()]*\))?\s*$')


def identity(date, venue, race, horse):
    return result_identity({'Date': date, 'Track': normalize_venue_name(venue),
                            'Race': race, 'Horse': horse})


def _unambiguous(candidates):
    return {key: min(values) for key, values in candidates.items()
            if max(values) - min(values) <= 0.050000001}


def load_official_times(bundle_path):
    path = Path(bundle_path)
    if not path.exists():
        return {}
    candidates = defaultdict(list)
    for event in json.loads(path.read_text(encoding='utf-8')).get('events', []):
        for row in event.get('rows', []):
            key = row.get('key') or event.get('key') or []
            if len(key) != 4:
                continue
            try:
                value = float(row['time'])
            except (KeyError, TypeError, ValueError):
                continue
            if math.isfinite(value) and value > 0 and row.get('horse'):
                candidates[identity(key[1], key[0], key[2], row['horse'])].append(value)
    return _unambiguous(candidates)


def parse_winning_time(value):
    try:
        parts = str(value).strip().split(':')
        if len(parts) == 2:
            minutes, secs = float(parts[0]), float(parts[1])
            if not (minutes >= 0 and minutes.is_integer() and 0 <= secs < 60):
                return None  # 畸形 WT（例如 1:75.3）唔准入（Sol）
            result = minutes * 60 + secs
        elif len(parts) == 1:
            result = float(parts[0])
        else:
            return None
        return result if math.isfinite(result) and result > 0 else None
    except (ValueError, TypeError):
        return None


def load_form_runs(archive_root):
    """→ (winning, runners)。winning = {(date, venue, race): WT 秒}；
    runners = {identity: (pos, margin_L, distance)}，只收冇衝突嘅。"""
    candidates = defaultdict(list)
    runner_candidates = defaultdict(set)
    for path in Path(archive_root).rglob('*Formguide.md'):
        horse = None
        with path.open(encoding='utf-8', errors='replace') as handle:
            for line in handle:
                if line.startswith('['):
                    # 每個馬頭都重設身份；對唔到格式嘅馬頭 = 唔知係邊匹，唔准沿用上一匹（Sol）。
                    header = FORM_HORSE.match(line)
                    horse = header.group(1) if header else None
                    continue
                if line.startswith('='):
                    horse = None
                if 'WinningTime:' not in line:
                    continue
                match = FORM_LINE.search(line)
                if match:
                    venue, race, date, distance, raw_time = match.groups()
                    value = parse_winning_time(raw_time)
                    if value is not None:
                        candidates[(date, normalize_venue_name(venue), race)].append(value)
                    runner = FORM_RUNNER.search(line)
                    if runner and horse:
                        runner_candidates[identity(date, venue, race, horse)].add(
                            (runner.group(2), runner.group(1), distance))
    runners = {key: next(iter(values)) for key, values in runner_candidates.items()
               if len(values) == 1}
    return _unambiguous(candidates), runners


def load_winning_times(archive_root):
    return load_form_runs(archive_root)[0]


def derive_time(winning_s, margin, distance, pos):
    winning_s = parse_winning_time(winning_s)
    try:
        distance_text = str(distance).strip()
        if not re.fullmatch(r'\d+', distance_text) or int(distance_text) <= 0 or winning_s is None:
            return None
        distance_value = int(distance_text)
        pos_text = str(pos).strip()
        if not re.fullmatch(r'\d+', pos_text) or int(pos_text) < 1:
            return None
        if pos_text == '1':
            lengths = 0.0
        else:
            lengths = float(re.sub(r'[lL]$', '', str(margin).strip()))
            if not math.isfinite(lengths) or lengths < 0:
                return None
        result = winning_s + lengths * METRES_PER_LENGTH * winning_s / distance_value
        return result if 8 < distance_value / result < 22 else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def format_time(seconds):
    millis = round(seconds * 1000)
    minutes, remainder = divmod(millis, 60000)
    return f'{minutes:02d}:{remainder // 1000:02d}.{remainder % 1000:03d}'


def resolve_time(key, pos, margin, distance, official, winning, runners=None):
    if key in official:
        return format_time(official[key]), 'official'
    value = derive_time(winning.get(key[:3]), margin, distance, pos)
    form = (runners or {}).get(key)
    csv_distance = str(distance).strip()
    if value is None and form and str(form[0]) == str(pos).strip() and (
            not csv_distance or csv_distance == str(form[2])):
        # CSV 行冇 margin／距離：用匹馬自己往績行（名次要對得上先信）。
        value = derive_time(winning.get(key[:3]), form[1], distance if str(distance).strip() else form[2], pos)
    return (format_time(value), 'estimated') if value is not None else ('', None)


def fill_times(results_csv, archive_root, bundle_path, apply=False, report_path=None):
    results_csv = Path(results_csv)
    official = load_official_times(bundle_path)
    winning, runners = load_form_runs(archive_root)
    # 讀 → 補 → 換檔成段揸住同 ingest 共用嘅鎖（Sol）。
    with results_csv_lock(results_csv):
        return _fill_locked(results_csv, official, winning, runners, apply, report_path)


def _fill_locked(results_csv, official, winning, runners, apply, report_path):
    if report_path is not None and Path(report_path).resolve() == results_csv.resolve():
        raise ValueError('report must not overwrite results CSV')
    original = results_csv.read_bytes()
    with results_csv.open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if not fields or not {'Date', 'Track', 'Race', 'Horse', 'Pos', 'Margin', 'Distance', 'Time'} <= set(fields):
        raise ValueError('results CSV schema incomplete')
    monthly = defaultdict(lambda: {'blank': 0, 'official': 0, 'estimated': 0, 'remaining': 0})
    count = 0
    for row in rows:
        if str(row.get('Time') or '').strip():
            continue
        stats = monthly[str(row.get('Date') or '')[:7]]
        stats['blank'] += 1
        key = identity(row['Date'], row['Track'], row['Race'], row['Horse'])
        value, source = resolve_time(key, row['Pos'], row['Margin'], row['Distance'], official, winning, runners)
        if source:
            row['Time'] = value
            stats[source] += 1
            count += 1
        else:
            stats['remaining'] += 1
    backup = None
    if apply and count:
        if results_csv.read_bytes() != original:
            raise ValueError('results CSV changed during repair')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        backup = results_csv.with_suffix(f'.csv.bak_{stamp}')
        shutil.copy2(results_csv, backup)
        tmp_name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8', newline='', dir=results_csv.parent, delete=False) as handle:
                tmp_name = handle.name
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            # 換檔前再核一次：期間有人寫過（例如手動 ingest）就放棄，下晚再補（Sol）。
            if results_csv.read_bytes() != original:
                raise ValueError('results CSV changed during repair')
            os.replace(tmp_name, results_csv)
        finally:
            if tmp_name and os.path.exists(tmp_name):
                os.unlink(tmp_name)
    for month, stats in sorted(monthly.items()):
        print(f"{month}: 空白 {stats['blank']} / 官方填 {stats['official']} / 推算填 {stats['estimated']} / 仲空 {stats['remaining']}")
    print(f'times filled: {count}')
    if report_path is not None:
        Path(report_path).write_text(json.dumps({'mode': 'apply' if apply else 'dry_run', 'monthly': dict(monthly), 'times_filled': count, 'backup': str(backup) if backup else None}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return count


def main():
    from au_racing_engine.full_time_speed import default_bundle_path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--results-csv', type=Path, default=HISTORICAL_RESULTS_CSV)
    parser.add_argument('--archive-root', type=Path, default=ARCHIVE_ROOT)
    parser.add_argument('--bundle', type=Path, default=default_bundle_path())
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    fill_times(args.results_csv, args.archive_root, args.bundle, args.apply, args.report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
