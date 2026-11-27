"""EXP-20261127-41: frozen live MS2 versus legacy profit forward."""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / '.agents/skills/nba'))
from nba_engine import featured
from nba_engine.legs import MARKET

START = "2026-11-29"   # first MS2 target date
EXPERIMENT = 'EXP-20261127-41'
ROOT = Path.home() / 'WongChoiData/Wong Choi NBA Analysis'
LEDGER = Path.home() / 'WongChoiData/NBA_Market_Eval/ledger'
REPORTS = Path.home() / 'WongChoiData/NBA_Market_Eval/reports'
STATK = {v: k for k, v in MARKET.items()}
SETTLE_GRACE_DAYS = 3
CHECKPOINT = {'days': 28, 'bets': 600}


def day_folders(analysis=None):
    backend = REPO / 'Horse_Racing_Dashboard/backend'
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services.nba_tracking import _tracking_roots
    tracking = [Path(p) for p in _tracking_roots(REPO)]
    root = Path(analysis) if analysis is not None else None
    roots = list(dict.fromkeys(([root] if root is not None else []) +
                               (tracking if root is None or root in tracking else [])))
    folders = defaultdict(list)
    for base in roots:
        for folder in base.glob('????-??-?? NBA Analysis*'):
            if folder.is_dir():
                folders[folder.name[:10]].append(folder)
    return folders


def snapshot(day_dir, day):
    candidates = []
    directories = [day_dir] if isinstance(day_dir, Path) else day_dir
    for path in (p for directory in directories for p in (directory / '_prediction_snapshots').glob('*')):
        try:
            manifest = json.loads((path / 'manifest.json').read_text())
            if (manifest.get('snapshot_role') == 'production' and manifest.get('target_date') == day
                    and manifest.get('completeness') in ('complete', 'partial') and manifest.get('created_at')):
                candidates.append((datetime.fromisoformat(manifest['created_at'].replace('Z', '+00:00')).timestamp(), str(path), path))
        except (OSError, ValueError, TypeError):
            continue
    return min(candidates)[2] if candidates else None


def availability_for(root, day, legacy=False):
    backend = REPO / 'Horse_Racing_Dashboard/backend'
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    from services.nba_tracking import _withdrawn, _tracking_roots
    sources = day_folders(root).get(day, [])
    return _withdrawn(sources, legacy=legacy)


def settlements(ledger, day):
    out = {}
    path = Path(ledger) / f'{day}.jsonl'
    if path.exists():
        with path.open() as f:
            for line in f:
                if '"settlement"' not in line:
                    continue
                r = json.loads(line)
                if r.get('row_type') == 'settlement' and r.get('line') is not None:
                    out.setdefault((r['game_tag'], r['player'], r['market'], float(r['line'])), r)
    return out


def load(ledger=None, analysis=None, *, diagnostics=None):
    if START is None:
        return []
    root, ledger = Path(analysis or ROOT), Path(ledger or LEDGER)
    days = []
    diagnostics = diagnostics if diagnostics is not None else {}
    diagnostics.setdefault('skipped', [])
    diagnostics.setdefault('pending', [])
    directories = {day: folders for day, folders in day_folders(analysis).items() if day >= START}
    if not directories:
        return days
    current = date.fromisoformat(START)
    last = date.fromisoformat(max(directories))
    while current <= last:
        day = current.isoformat()
        current += timedelta(days=1)
        directory = directories.get(day)
        if directory is None:      # no NBA games that day: nothing to count, never blocks the window
            continue
        snap = snapshot(directory, day)
        if snap is None:
            if (date.today() - date.fromisoformat(day)).days <= SETTLE_GRACE_DAYS:
                diagnostics['pending'].append(day)
                break
            diagnostics['skipped'].append({'day': day, 'reason': 'missing production snapshot'})
            continue
        sidecars = sorted(snap.glob('*.market_legs.json'))
        if not sidecars or any('p_legacy' not in leg for path in sidecars
                               for leg in json.loads(path.read_text()).get('legs', [])):
            diagnostics['skipped'].append({'day': day, 'reason': 'production snapshot missing p_legacy'})
            continue
        settled = settlements(ledger, day)
        live_avail, live_pulled = availability_for(root, day)
        legacy_avail, legacy_pulled = availability_for(root, day, legacy=True)
        arms = {'live': [], 'shadow': []}
        cards = {'live': [], 'shadow': []}
        losses = []
        for side in sidecars:
            tag = side.name.split('_Full')[0].replace('Game_', '', 1)
            odds_path = snap / f'Sportsbet_Odds_{tag}.json'
            if not odds_path.exists():   # permanent gap in a frozen snapshot: skip the game, don't stall
                diagnostics['skipped'].append({'day': day, 'reason': f'missing odds {tag}'})
                continue
            sc, odds = json.loads(side.read_text()), json.loads(odds_path.read_text())
            leg_objs = []
            for leg in sc.get('legs', []):
                try:
                    stat, line = STATK[leg['market']], float(leg['line'])
                except (KeyError, TypeError, ValueError):
                    continue
                obj = SimpleNamespace(player=leg['player'], stat=stat, line=line, team=leg.get('team'),
                                      availability=leg.get('availability'), p_final=leg.get('p_final'),
                                      p_legacy=leg.get('p_legacy'))
                leg_objs.append(obj)
                row = settled.get((tag, obj.player, leg['market'], line), {})
                y = row.get('y')
                if row.get('outcome') != 'void' and y in (0, 1) and leg.get('p_ms2') is not None and obj.p_final is not None and obj.p_legacy is not None:
                    def loss(p):
                        p = min(max(float(p), 1e-15), 1 - 1e-15)
                        return -math.log(p if y else 1-p)
                    losses.append({'stat': stat, 'live': loss(obj.p_final), 'shadow': loss(obj.p_legacy)})
            # Sidecar probabilities are rounded to 4 dp for both primary arms.
            for arm, prob in (('live', 'p_final'), ('shadow', 'p_legacy')):
                picks = [dict(p, game_tag=tag) for p in featured.candidates(odds, leg_objs, prob)
                         if p['edge'] >= featured.MIN_EDGE and p['price'] <= featured.MAX_PRICE]
                arms[arm].extend(picks)
                cards[arm].extend(dict(p, game_tag=tag) for p in sc.get('featured' if arm == 'live' else 'featured_legacy', []))
        cards = {arm: featured.daily_top(picks) for arm, picks in cards.items()}
        cards['live'] = [p for p in cards['live'] if not live_avail.matches(live_pulled.get(p['game_tag']), p)]
        cards['shadow'] = [p for p in cards['shadow'] if not legacy_avail.matches(legacy_pulled.get(p['game_tag']), p)]
        all_picks = [p for group in (arms, cards) for picks in group.values() for p in picks]
        def unsettled(p):
            row = settled.get((p['game_tag'], p['player'], p['market'], float(p['milestone_line'])), {})
            return row.get('outcome') != 'void' and row.get('y') not in (0, 1)
        if any(unsettled(p) for p in all_picks):
            # Pre-registered (before any MS2 data): wait up to SETTLE_GRACE_DAYS for late settlements; after that
            # a still-unsettled pick is dropped from both counts (like a void) so one lost result cannot stall the test.
            if (date.today() - date.fromisoformat(day)).days <= SETTLE_GRACE_DAYS:
                diagnostics['pending'].append(day)
                break
            dropped = sum(unsettled(p) for p in all_picks)
            diagnostics['skipped'].append({'day': day, 'reason': f'{dropped} picks never settled (dropped)'})
        def settle(picks):
            out = []
            for p in picks:
                row = settled.get((p['game_tag'], p['player'], p['market'], float(p['milestone_line'])), {})
                y = row.get('y')
                if row.get('outcome') == 'void' or y not in (0, 1):
                    continue
                win = y == (1 if p['side'] == 'over' else 0)
                out.append({'pnl': p['price'] - 1 if win else -1.0, 'stat': p['market']})
            return out
        entry = {'day': day, 'live': settle(arms['live']), 'shadow': settle(arms['shadow']),
                 'card_live': settle(cards['live']), 'card_shadow': settle(cards['shadow']), 'losses': losses}
        if not entry['live'] and not entry['shadow']:
            diagnostics['skipped'].append({'day': day, 'reason': 'no bets'})
            continue
        days.append(entry)
    return days


def progress(days):
    used, bets = [], 0
    for day in days:
        used.append(day)
        bets += len(day['live'])
        if len(used) >= CHECKPOINT['days'] and bets >= CHECKPOINT['bets']:
            break
    return {'days': len(used), 'bets': bets, 'available_days': len(days),
            'available_bets': sum(len(d['live']) for d in days), 'checkpoint': CHECKPOINT.copy(),
            'ready': len(used) >= CHECKPOINT['days'] and bets >= CHECKPOINT['bets']}


def roi(days, arm):
    rows = [r['pnl'] for d in days for r in d[arm]]
    return sum(rows) / len(rows) if rows else None


def judge(days):
    # Stop at the first day both pre-registered thresholds are met.
    used = []
    for day in days:
        used.append(day)
        if progress(used)['ready']:
            break
    rnd = random.Random(20261127)
    draws = defaultdict(list)
    for _ in range(2000):
        sample = [rnd.choice(used) for _ in used]
        a, b = roi(sample, 'live'), roi(sample, 'shadow')
        if a is not None: draws['live'].append(a)
        if b is not None: draws['shadow'].append(b)
        if a is not None and b is not None: draws['delta'].append(a-b)
    def ci(key):
        v = sorted(draws[key])
        return [v[int(.025*len(v))], v[int(.975*len(v))-1]] if v else [None, None]
    a, b = roi(used, 'live'), roi(used, 'shadow')
    bounds = ci('delta')
    verdict = ('insufficient' if a is None or b is None else 'improved' if bounds[0] is not None and bounds[0] > 0 else
               'worse' if bounds[1] is not None and bounds[1] < 0 else 'no_difference')
    losses = [r for d in used for r in d['losses']]
    def loss_summary(rows):
        return {'n': len(rows), 'delta': sum(r['live']-r['shadow'] for r in rows)/len(rows) if rows else None}
    return {'days': len(used), 'n_bets': sum(len(d['live']) for d in used),
            'primary_delta': a-b if a is not None and b is not None else None, 'ci95': bounds,
            'verdict': verdict,
            'secondary': {'roi': {arm: {'n': sum(len(d[arm]) for d in used), 'roi': roi(used, arm), 'ci95': ci(arm)} for arm in ('live','shadow')},
                          'featured_roi': {arm: roi(used, 'card_'+arm) for arm in ('live','shadow')},
                          'logloss': loss_summary(losses),
                          'by_stat': {s: {'logloss': loss_summary([r for r in losses if r['stat'] == s]),
                                          'roi': {arm: roi([{arm: [r for r in d[arm] if r['stat'] == MARKET[s]]} for d in used], arm) for arm in ('live', 'shadow')}} for s in sorted(STATK.values())}}}


def status(ledger=None, analysis=None, *, days=None):
    details = {}
    loaded = load(ledger, analysis, diagnostics=details) if days is None else days
    return {'MP': {**progress(loaded), **details}}


def evaluate(ledger=None, analysis=None, out_dir=None, *, force=False, only=None, days=None):
    if only and only != 'MP': return {}
    path = Path(out_dir or REPORTS) / f'{EXPERIMENT}-MP-result.json'
    if path.is_file() and not force: return {'MP': json.loads(path.read_text())}
    days = load(ledger, analysis) if days is None else days
    state = progress(days)
    if not state['ready']: return {'MP': {'status': 'not_ready', 'progress': state}}
    result = {'experiment': EXPERIMENT, 'test': 'MP', 'evaluated_at': datetime.now(timezone.utc).isoformat(),
              'start': START, 'progress': state, **judge(days)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    return {'MP': result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('status', 'evaluate'))
    parser.add_argument('--out', type=Path)
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    print(json.dumps(status() if args.mode == 'status' else evaluate(out_dir=args.out, force=args.force), indent=1))

if __name__ == '__main__': main()
