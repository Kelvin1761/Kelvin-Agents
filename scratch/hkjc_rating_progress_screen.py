"""Rating-progress candidate (EXP-20261009-02): backfill + offline screen.

Pre-registration is in docs/experiments/EXP-20261009-02-hkjc-rating-progress.md.
Reads a scored corpus produced by hkjc_history_alignment_corpus.py (its candidate arm).

usage (from the repo root, cwd = directory holding corpus-replay/):
  hkjc_rating_progress_screen.py dev        # dev selection only; terminal sealed
  hkjc_rating_progress_screen.py terminal W # opens terminal once for the selected W
Forward observation: rerun on a corpus containing only meetings after 2026-10-09.
"""
import csv, json, math, re, sys
from pathlib import Path

WT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / '.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts'))
sys.path.insert(0, str(WT / '.agents/skills/shared_racing'))
import hkjc_auto_orchestrator as orch  # noqa: E402
from eval_metrics import race_metrics  # noqa: E402
from model_evaluation_decision import build_evaluation_input, evaluate_candidate  # noqa: E402

ROOT = Path('/Users/imac/WongChoiData/Wong Choi Horse Race Analysis/HK_Racing')
CAND = Path('corpus-replay/candidate')
TERMINAL_FROM = '2026-09-16'
GRID = (0.5, 1.0, 2.0)
failed = {(a['meeting'], a['race']) for a in json.load(open('corpus-replay/summary.json'))['races_engine_failed']}


def season_start(entries, race_date):
    ents = [e for e in entries if (d := orch._profile_entry_date(e.get('date'))) is not None and d < race_date]
    seasons = sorted({s for s in (orch._profile_season_key(e.get('date')) for e in ents) if s}, reverse=True)
    if not seasons:
        return None
    cur = [e['rating'] for e in ents if orch._profile_season_key(e.get('date')) == seasons[0]
           and isinstance(e.get('rating'), int) and e['rating'] > 0]
    return cur[-1] if cur else None


def build():
    races, cov = [], [0, 0]
    for meet in sorted(CAND.iterdir()):
        race_date = orch._profile_entry_date(f"{meet.name[8:10]}/{meet.name[5:7]}/{meet.name[2:4]}")
        cache = json.loads((ROOT / meet.name / '.hkjc_cache/profile_cache.json').read_text())
        res = json.loads(next((ROOT / meet.name).glob('*全日賽果.json')).read_text())
        scores = {}
        for row in csv.DictReader((meet / 'HKJC_Auto_Scoring.csv').open(encoding='utf-8')):
            scores.setdefault(int(row['race_number']), {})[row['horse_number']] = (
                int(row['rank']), float(row['ability_score']))
        for rn, horses in scores.items():
            if (meet.name, rn) in failed or str(rn) not in res:
                continue
            card = next((ROOT / meet.name).glob(f'* Race {rn} 排位表.md'), None)
            if card is None:
                continue
            _, info = orch._parse_racecard_meta(card.read_text(encoding='utf-8'))
            logic = json.loads((meet / f'Race_{rn}_Logic.json').read_text())
            pos = {}
            for x in res[str(rn)].get('results', []):
                m = re.match(r'(\d+)', str(x.get('pos', '')))
                if m:
                    pos[str(x['horse_no'])] = int(m.group(1))
            runners = []
            for no, (rank, ability) in horses.items():
                if no not in pos:
                    continue
                h = logic['horses'].get(no, {})
                card_row = info.get(no) or {}
                cur = card_row.get('rating')
                # Identity from the racecard (archived Logic often lacks the ID);
                # the cached profile must still carry the same name.
                cached = None
                for key in (card_row.get('hkjc_horse_id'), card_row.get('horse_code'), h.get('hkjc_horse_id')):
                    if key and (cache.get(key) or cache.get(str(key).rsplit('_', 1)[-1])):
                        cached = cache.get(key) or cache.get(str(key).rsplit('_', 1)[-1])
                        break
                ss = None
                if cached and cached['data'].get('name') == h.get('horse_name'):
                    ss = season_start(cached['data'].get('entries') or [], race_date)
                prog = (cur - ss) if isinstance(cur, int) and ss else None
                cov[0] += prog is not None; cov[1] += 1
                runners.append({'no': no, 'rank': rank, 'ability': ability, 'prog': prog, 'pos': pos[no]})
            vals = [r['prog'] for r in runners if r['prog'] is not None]
            if len(vals) >= 4:
                mu = sum(vals) / len(vals)
                sd = math.sqrt(sum((v - mu) ** 2 for v in vals) / len(vals))
                for r in runners:
                    r['z'] = (r['prog'] - mu) / sd if r['prog'] is not None and sd > 0 else 0.0
            else:
                for r in runners:
                    r['z'] = 0.0
            races.append({'date': meet.name[:10], 'venue': 'HV' if 'Happy' in meet.name else 'ST',
                          'runners': runners})
    print(f'races {len(races)}; runner coverage {cov[0]}/{cov[1]} = {cov[0]/cov[1]:.1%}')
    return races


def metrics(race, w):
    rs = race['runners']
    order = sorted(rs, key=lambda r: (-(r['ability'] + w * r['z']), r['rank']))
    pos = {r['no']: r['pos'] for r in rs}
    m = race_metrics([r['no'] for r in order], [n for n, p in pos.items() if p <= 3],
                     actual_pos=pos, field_size=len(pos))
    m['mean_top3_model_rank'] = m.get('top3_mean_model_rank')
    return m


def mean(rows, k):
    v = [float(r[k]) for r in rows if r.get(k) is not None]
    return sum(v) / len(v) if v else 0.0


def dev(races):
    devr = [r for r in races if r['date'] < TERMINAL_FROM]
    dates = sorted({r['date'] for r in devr})
    blocks = [set(dates[i * len(dates) // 5:(i + 1) * len(dates) // 5]) for i in range(5)]
    print(f'dev races {len(devr)}, dates {len(dates)}; terminal SEALED')
    base = [metrics(r, 0.0) for r in devr]
    chosen = None
    for w in GRID:
        cand = [metrics(r, w) for r in devr]
        d = {k: mean(cand, k) - mean(base, k) for k in
             ('gold', 'good_positional', 'top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5')}
        blk = []
        for b in blocks:
            idx = [i for i, r in enumerate(devr) if r['date'] in b]
            blk.append(all(mean([cand[i] for i in idx], k) - mean([base[i] for i in idx], k) >= -1e-12
                           for k in ('gold', 'good_positional')))
        rank_pos = sum(d[k] > 1e-12 for k in ('top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5'))
        moved = sum(1 for i in range(len(devr)) if base[i]['pick_positions'] != cand[i]['pick_positions'])
        ok = d['gold'] >= 0 and d['good_positional'] >= 0 and sum(blk) >= 3 and rank_pos >= 2
        print(f"w={w}: " + ' '.join(f'{k} {v:+.4f}' for k, v in d.items())
              + f" | blocks ok {sum(blk)}/5 | ranking+ {rank_pos}/3 | races top3 changed {moved} | eligible {ok}")
        if ok and chosen is None:
            chosen = w
    print('SELECTED' if chosen else 'REJECT_DEV — terminal stays closed', chosen)


def terminal(races, w):
    dates = [r['date'] for r in races]
    base = [metrics(r, 0.0) for r in races]
    cand = [metrics(r, w) for r in races]
    ev = build_evaluation_input(domain='hkjc', dates=dates, baseline_rows=base, candidate_rows=cand,
                                leakage_audit_passed=True,
                                ranking_metrics=('top3_capture_at5', 'ndcg_at5', 'competitive_recall_at5'))
    for grp, dd in (('primary', ev.primary), ('ranking', ev.ranking)):
        for k, v in dd.items():
            print(f'{grp} {k:24s} dev {v.development_delta:+.4f} term {v.terminal_delta:+.4f} '
                  f'CI [{v.terminal_ci_low:+.4f},{v.terminal_ci_high:+.4f}]')
    for name, sel in (('HV', lambda r: r['venue'] == 'HV'), ('ST', lambda r: r['venue'] == 'ST'),
                      ('field<=10', lambda r: len(r['runners']) <= 10), ('field>=11', lambda r: len(r['runners']) >= 11)):
        idx = [i for i, r in enumerate(races) if sel(r) and r['date'] >= TERMINAL_FROM]
        print(f'terminal cohort {name} n={len(idx)}: ' + ' '.join(
            f"{k} {mean([cand[i] for i in idx], k) - mean([base[i] for i in idx], k):+.4f}"
            for k in ('gold', 'good_positional', 'top3_capture_at5')))
    print('VERDICT', evaluate_candidate(ev))


if __name__ == '__main__':
    data = build()
    if sys.argv[1] == 'dev':
        dev(data)
    else:
        terminal(data, float(sys.argv[2]))
