"""Compare removal and walk-forward rescaling of HKJC post-scoring signals."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

ROOT = Path(__file__).resolve().parents[4]
COMPARE = ROOT / '.agents/skills/hkjc_racing/hkjc_reflector/scripts/hkjc_replay_compare_v5.py'
LABELS = ('Δlog-loss（每匹）', 'Δ場內 AUC', 'Good', '頭二入面入頭三', 'v5.2 判決')


def season(date):
    return int(date[:4]) - (int(date[5:7]) < 9)


def load(path):
    with open(path, encoding='utf-8') as f:
        return [r for r in (json.loads(line) for line in f if line.strip()) if 'horses' in r]


def race_key(row):
    return row['meeting'], row['race']


def contributions(base, off):
    """Return race-centred base minus off values, aligned to base horse order."""
    index = {}
    for row in off:
        key = race_key(row)
        if key in index:
            raise ValueError(f'duplicate off race: {key}')
        horses = {h['n']: h['raw'] for h in row['horses']}
        if len(horses) != len(row['horses']):
            raise ValueError(f'duplicate off horse: {key}')
        index[key] = horses
    if len({race_key(row) for row in base}) != len(base):
        raise ValueError('duplicate base race')
    if set(index) != {race_key(row) for row in base}:
        raise ValueError('base and off races differ')
    result = []
    for row in base:
        horses = row['horses']
        ids = [h['n'] for h in horses]
        other = index[race_key(row)]
        if len(set(ids)) != len(ids) or set(ids) != set(other):
            raise ValueError(f'horse mismatch: {race_key(row)}')
        c = np.array([h['raw'] - other[h['n']] for h in horses], dtype=float)
        result.append(c - c.mean())
    return result


def fit_betas(rows, features):
    betas = {}
    for s in sorted({season(row['date']) for row in rows}):
        if s < 2020:
            continue
        raw, feat, labels = [], [], []
        for row, feature in zip(rows, features):
            if not 2019 <= season(row['date']) < s:
                continue
            horses = row['horses']
            r = np.array([h['raw'] for h in horses], dtype=float)
            r -= r.mean()
            for i, h in enumerate(horses):
                if h['pos']:
                    raw.append(r[i])
                    feat.append(feature[i])
                    labels.append(int(h['pos'] <= 3))
        if not raw or len(set(labels)) < 2:
            raise ValueError(f'insufficient training data for season {s}')
        r, z = np.asarray(raw), np.asarray(feat)
        rs, sd = r.std(), z.std()
        if not rs:
            raise ValueError(f'zero raw variance for season {s}')
        sd = sd or 1.0
        coef = LogisticRegression(C=0.1, max_iter=20000).fit(
            np.column_stack((r / rs, z / sd)), labels
        ).coef_[0]
        if abs(coef[0]) < 1e-12:
            raise ValueError(f'zero raw coefficient for season {s}')
        betas[s] = float((coef[1] / sd) / (coef[0] / rs))
    return betas


def rescale(rows, features, betas):
    output = []
    for row, feature in zip(rows, features):
        new = dict(row)
        s = season(row['date'])
        if s in betas:
            new['horses'] = [dict(h, raw=round(float(h['raw'] + betas[s] * c), 4))
                             for h, c in zip(row['horses'], feature)]
            new['picks'] = [h['n'] for h in sorted(new['horses'], key=lambda h: -h['raw'])]
        output.append(new)
    return output


def parse_compare(text):
    lines = text.splitlines()
    result = {}
    for label in LABELS:
        matches = [line for line in lines if line.startswith(label)]
        if len(matches) != 1:
            raise ValueError(f'expected one {label} line, got {len(matches)}')
        result[label] = matches[0]
    return result


def compare(base, candidate, target, window):
    result = subprocess.run([sys.executable, str(COMPARE), str(base), str(candidate),
                             '--window', window, '--null', '200'],
                            check=True, capture_output=True, text=True)
    target.write_text(result.stdout, encoding='utf-8')
    return parse_compare(result.stdout)


def summary_cell(parsed):
    return '<br>'.join(parsed[label].replace('|', '&#124;') for label in LABELS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base', type=Path)
    parser.add_argument('out_dir', type=Path)
    parser.add_argument('components', nargs='+')
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    rows = load(args.base)
    lines = ['| 組件 | 移除 dev | 移除 holdout | 每季 β | 重 fit dev | 重 fit holdout |',
             '|---|---|---|---|---|---|']
    for name in args.components:
        if not name.isidentifier():
            raise ValueError(f'invalid component: {name}')
        off = args.out_dir / f'off_{name}.jsonl'
        features = contributions(rows, load(off))
        betas = fit_betas(rows, features)
        candidate = args.out_dir / f'rescale_{name}.jsonl'
        with candidate.open('w', encoding='utf-8') as f:
            for row in rescale(rows, features, betas):
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        cells = []
        for prefix, path in (('', off), ('rescale_', candidate)):
            cells.append([summary_cell(compare(args.base, path,
                          args.out_dir / f'cmp_{prefix}{name}_{window}.txt', window))
                          for window in ('dev', 'holdout')])
        beta_text = ', '.join(f'{s}: {b:.6g}' for s, b in sorted(betas.items()))
        lines.append(f'| {name} | {cells[0][0]} | {cells[0][1]} | {beta_text} | '
                     f'{cells[1][0]} | {cells[1][1]} |')
    (args.out_dir / 'summary.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
