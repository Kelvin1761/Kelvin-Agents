"""EXP-20261009-13: baseline vs restored July outer weights, real engine, identical Logic.

usage: hkjc_weight_restore_ab.py  (cwd holds corpus-replay/, hkjc-history-fix/ = baseline
checkout and shape-wt/ = checkout with the candidate MATRIX_WEIGHTS)
"""
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, 'hkjc-history-fix/scratch'); sys.path.insert(0, 'hkjc-history-fix/.agents/skills/shared_racing')
import hkjc_history_alignment_corpus as h
from eval_metrics import race_metrics
from model_evaluation_decision import build_evaluation_input, evaluate_candidate
OUT = Path('shape-ab'); BASE = Path('hkjc-history-fix').resolve(); VAR = Path('shape-wt').resolve()
failed = set()
if not (OUT / 'done').exists():
    for m in sorted(Path('corpus-replay/candidate').iterdir()):
        print('==', m.name, flush=True)
        for arm, root in (('base', BASE), ('var', VAR)):
            d = OUT / arm / m.name; d.mkdir(parents=True)
            for p in m.glob('Race_*_Logic.json'):
                shutil.copy2(p, d / p.name)
            failed |= {(m.name, r) for r in h.score(root, d)}
    (OUT / 'done').write_text(json.dumps(sorted(map(list, failed))))
failed = {tuple(x) for x in json.loads((OUT / 'done').read_text())}
dates, B, C, venue, size = [], [], [], [], []
moved = 0
for m in sorted((OUT / 'base').iterdir()):
    b, c, res = h.ranks(m), h.ranks(OUT / 'var' / m.name), h.results(h.DATA_ROOT / m.name)
    for r in sorted(set(b) & set(c) & set(res)):
        if (m.name, r) in failed: continue
        pos = res[r]; t3 = [x for x, p in pos.items() if p <= 3]; rows = []
        for picks in (b[r], c[r]):
            mm = race_metrics([x for x in picks if x in pos], t3, actual_pos=pos, field_size=len(pos))
            mm['mean_top3_model_rank'] = mm.get('top3_mean_model_rank'); rows.append(mm)
        moved += b[r][:4] != c[r][:4]
        dates.append(m.name[:10]); B.append(rows[0]); C.append(rows[1])
        venue.append('HV' if 'Happy' in m.name else 'ST'); size.append(len(pos))
print('races', len(dates), 'engine-refused', len(failed), 'races with top-4 order changed', moved)
ev = build_evaluation_input(domain='hkjc', dates=dates, baseline_rows=B, candidate_rows=C, leakage_audit_passed=True,
                            ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5', 'mean_top3_model_rank'))
for g, dd in (('primary', ev.primary), ('ranking', ev.ranking)):
    for k, v in dd.items():
        print(f'{g} {k:24s} dev {v.development_delta:+.4f} term {v.terminal_delta:+.4f} CI [{v.terminal_ci_low:+.4f},{v.terminal_ci_high:+.4f}]')
mean = lambda rows, k, idx: sum(float(rows[i][k] or 0) for i in idx) / max(1, len(idx))
for name, sel in (('HV', lambda i: venue[i] == 'HV'), ('ST', lambda i: venue[i] == 'ST'),
                  ('field<=10', lambda i: size[i] <= 10), ('field>=11', lambda i: size[i] >= 11)):
    idx = [i for i in range(len(dates)) if sel(i)]
    print(f'cohort {name:9s} n={len(idx):3d} ' + ' '.join(f'{k} {mean(C,k,idx)-mean(B,k,idx):+.4f}' for k in ('gold','good_positional','top3_capture_at5')))
print('VERDICT', evaluate_candidate(ev))
