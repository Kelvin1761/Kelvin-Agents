#!/usr/bin/env python3
"""Flatten NBA ledger legs. Production is the top-level snapshot_role.

For O/U prices ou_line is the actual line; fall back to line when absent.
Select the latest eligible quote per O/U line, then the most balanced line.
"""
import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

LEDGER = Path('~/WongChoiData/NBA_Market_Eval/ledger').expanduser()
FIELDS = 'target_date game_tag player market line recorded_at odds_captured_at price_at_model p_market p_c p_s p_s2 p_final picked minutes_ratio y actual minutes ou_line ou_over_price ou_under_price ou_fair_over'.split()


def key(r):
    return (r['target_date'], r['game_tag'], r['player'], r['market'], float(r['line']))


def build(path):
    models, settlements, quotes = {}, {}, defaultdict(lambda: defaultdict(list))
    with path.open(encoding='utf-8') as stream:
        for text in stream:
            if '"model_obs"' in text:
                r = json.loads(text)
                if r.get('row_type') != 'model_obs' or r.get('snapshot_role') != 'production' or r.get('post_tip') is True or r.get('p_final') is None:
                    continue
                k = key(r)
                if k not in models or r['recorded_at'] < models[k]['recorded_at']:
                    models[k] = r
            elif '"settlement"' in text:
                r = json.loads(text)
                if r.get('row_type') == 'settlement':
                    settlements[key(r)] = r
            elif '"ou_two_way"' in text:
                r = json.loads(text)
                if r.get('row_type') != 'price_obs' or r.get('price_source') != 'ou_two_way' or r.get('post_tip') is True or r.get('tip_unknown') is True:
                    continue
                line = r.get('ou_line') if r.get('ou_line') is not None else r.get('line')
                if line is None or r.get('side') not in ('over', 'under') or not r.get('captured_at'):
                    continue
                over, under = (r.get('price'), r.get('complement_price')) if r['side'] == 'over' else (r.get('complement_price'), r.get('price'))
                if over is None or under is None or float(over) <= 0 or float(under) <= 0:
                    continue
                quotes[key(r)[:4]][float(line)].append((r['captured_at'], float(over), float(under)))
    for k, model in models.items():
        settlement = settlements.get(k)
        if not settlement or settlement.get('outcome') == 'void' or settlement.get('y') is None:
            continue
        row = {field: model.get(field) for field in FIELDS}
        row.update({field: settlement.get(field) for field in ('y', 'actual', 'minutes')})
        row['picked'] = int(bool(model.get('picked')))
        choices = []
        for line, observations in quotes[k[:4]].items():
            eligible = [q for q in observations if model.get('odds_captured_at') and q[0] <= model['odds_captured_at']]
            _, over, under = max(eligible) if eligible else min(observations)
            choices.append((abs(1 / over - 1 / under), line, over, under))
        if choices:
            _, line, over, under = min(choices)
            row.update(ou_line=line, ou_over_price=over, ou_under_price=under, ou_fair_over=(1 / over) / (1 / over + 1 / under))
        yield row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--since', default='2026-10-29', type=date.fromisoformat)
    parser.add_argument('--until', default=date.today(), type=date.fromisoformat)
    parser.add_argument('--out', type=Path, default=Path('~/WongChoiData/NBA_Research/ms_recal/legs.csv').expanduser())
    args = parser.parse_args()
    if args.since > args.until:
        parser.error('--since must not be after --until')
    args.out = args.out.expanduser()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    daily, markets, sums, counts = Counter(), Counter(), Counter(), Counter()
    total = ou_count = 0
    with args.out.open('w', newline='', encoding='utf-8') as output:
        writer = csv.DictWriter(output, fieldnames=FIELDS)
        writer.writeheader()
        for path in sorted(LEDGER.glob('????-??-??.jsonl')):
            try:
                day = date.fromisoformat(path.stem)
            except ValueError:
                continue
            if not args.since <= day <= args.until:
                continue
            daily[path.stem] = 0
            for row in build(path):
                writer.writerow(row)
                total += 1
                daily[path.stem] += 1
                markets[row['market']] += 1
                ou_count += row.get('ou_line') is not None
                for field in ('y', 'p_final', 'p_market'):
                    if row.get(field) is not None:
                        sums[field] += float(row[field])
                        counts[field] += 1
    print('每日行數:')
    for day, count in sorted(daily.items()):
        print(f'  {day}: {count}')
    print(f'總行數: {total}')
    print(f'O/U 資料比例: {ou_count}/{total} ({ou_count / total:.2%})' if total else 'O/U 資料比例: 0/0 (N/A)')
    print('各 market 行數:', ', '.join(f'{k}={v}' for k, v in sorted(markets.items())))
    for field in ('y', 'p_final', 'p_market'):
        print(f'{field} 平均: {sums[field] / counts[field]:.6f} (n={counts[field]})' if counts[field] else f'{field} 平均: N/A (n=0)')
    print(f'輸出: {args.out}')


if __name__ == '__main__':
    main()
