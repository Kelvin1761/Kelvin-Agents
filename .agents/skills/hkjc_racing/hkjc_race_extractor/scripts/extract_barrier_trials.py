"""Incrementally collect HKJC trial results; archive import is explicitly opt-in."""
import argparse
import datetime as dt
import gzip
import json
import os
from pathlib import Path
import sys
import tempfile
import time

AUTO = Path(__file__).resolve().parents[2] / 'hkjc_wong_choi_auto' / 'scripts'
if str(AUTO) not in sys.path:
    sys.path.insert(0, str(AUTO))
from hkjc_racing_engine import barrier_trial, live_priors
from extract_trackwork import fetch_url

RECHECK_DAYS = 7
URL = 'https://racing.hkjc.com/zh-hk/local/information/btresult?Date={}'


def add_day(table, day, html):
    groups = barrier_trial.parse_trial_page(html)
    if not any(__import__('re').search(r'第\s*1\s*組', g['group']) for g in groups):
        if day not in table['empty']:
            table['empty'].append(day)
    else:
        if day in table['empty']:
            table['empty'].remove(day)
        for group in groups:
            for row in group['rows']:
                if row['time'] is None:
                    continue
                margin = row['margin']
                record = [day, min(margin, 15) if margin is not None else None]
                entries = table['trials'].setdefault(row['code'], [])
                if record not in entries:
                    entries.append(record)
    if day not in table['scraped']:
        table['scraped'].append(day)


def atomic_write(path, table):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, delete=False) as f:
            name = f.name
            json.dump(table, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def update(path, archive=None, today=None):
    path = Path(path)
    table = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'trials': {}, 'scraped': [], 'empty': []}
    if archive:
        archive = Path(archive)
        for file in sorted(archive.glob('*.html.gz')):
            with gzip.open(file, 'rt', encoding='utf-8') as f:
                add_day(table, file.name[:10], f.read())
        empty = archive / 'empty.txt'
        if empty.exists():
            for day in empty.read_text().splitlines():
                day = day.strip()
                if day:
                    if day not in table['empty']:
                        table['empty'].append(day)
                    if day not in table['scraped']:
                        table['scraped'].append(day)
        atomic_write(path, table)
        return
    if not table['scraped'] and not table['empty']:
        print('⚠️ 試閘表未初始化；請先匯入 archive')
        return
    today = today or live_priors.hk_today()
    # 試閘頁當日稍後先出、或者一時出錯頁 —— 最近 RECHECK_DAYS 日每次都重抓，唔會因為一次「冇第 1 組」永久當冇試閘。
    latest = dt.date.fromisoformat(max(table['scraped'] + table['empty'])) + dt.timedelta(days=1)
    day = min(latest, today - dt.timedelta(days=RECHECK_DAYS))
    count = 0
    while day <= today and count < 45:
        if count:
            time.sleep(1.5)
        html = fetch_url(URL.format(day.strftime('%Y/%m/%d')), timeout=30, retries=2)
        add_day(table, day.isoformat(), html)
        atomic_write(path, table)
        day += dt.timedelta(days=1)
        count += 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--import-archive')
    args = parser.parse_args()
    try:
        import wongchoi_paths
        update(Path(wongchoi_paths.HK_RACING) / 'HKJC_Sections' / 'barrier_trials.json', args.import_archive)
    except Exception as exc:
        print(f'⚠️ 試閘抓取失敗：{exc}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
