"""Read-only $1 model tracking from verified, immutable NBA publications.

One first formal or steady research candidate per date/game. Never reprice a record.
The market ledger supplies only verified final outcomes, never recommendations.
"""
from datetime import datetime, timezone
import json
import math
import os
import re
from pathlib import Path
import sys

from .nba_published_analysis import verified_published_reports


TRACKING_START_DATE = "2026-10-25"
STEADY_POLICY = "banker-steady-b2-v1"  # mirrors nba_steady_policy.POLICY


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _verified_settlement(row):
    try:
        settled = datetime.fromisoformat(str(row.get('settled_at')).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return False
    return (settled.tzinfo is not None and settled <= datetime.now(timezone.utc)
            and re.fullmatch(r'[0-9a-f]{64}', str(row.get('results_sha256') or '')) is not None
            and (row.get('outcome') == 'void' or _number(row.get('actual'))))


def _key(tag, leg):
    market = str(leg.get('stat') or leg.get('market') or '').lower().replace('3pm', 'fg3m')
    line = leg.get('line')
    return (tag, leg.get('player'), market, float(line) if _number(line) else None, leg.get('side') or 'over')


def _research_card(sidecar, odds, day, tag, published):
    from .nba_latest_analysis import _review_price
    import hashlib
    for candidate in sidecar.get('review_candidates', []):
        if (not isinstance(candidate, dict) or candidate.get('candidate_id') != 'steady'
                or not isinstance(candidate.get('version'), str) or not candidate['version'].strip()
                or candidate.get('analysis_only') is not True or candidate.get('decision') != 'OBSERVE'):
            continue
        legs = candidate.get('legs')
        if (not isinstance(legs, list) or not 2 <= len(legs) <= 4
                or any(not isinstance(l, dict) or not l.get('player') or not _number(l.get('line'))
                       or l['line'] <= 0 or not (l.get('market') or l.get('category')) for l in legs)):
            continue
        price, _ = _review_price(candidate, odds)
        quote = candidate.get('sgm_quote') or {}
        try:
            captured = datetime.fromisoformat(str(quote.get('captured_at')).replace('Z', '+00:00'))
            if captured > datetime.fromisoformat(published):
                price = None
        except (TypeError, ValueError):
            price = None
        identity = hashlib.sha256(json.dumps(legs, sort_keys=True).encode()).hexdigest()[:16]
        return {'id':f'nba:{day}:{tag}:research:{identity}', 'event_name':tag.replace('_', ' @ '),
                'odds':price, 'tracking_kind':'research', 'model_version':candidate['version'],
                'model_probability':candidate.get('model_probability'),
                'legs':[{**l, 'stat':l.get('category') or str(l.get('market')).upper()} for l in legs]}
    return None


FEATURED_START_DATE = "2026-11-11"   # EXP-20261110-01: first forward target date


def _valid_pick(pick):
    return (isinstance(pick, dict) and pick.get('side') in ('over', 'under') and pick.get('player')
            and pick.get('market') in ('pts', 'reb', 'ast', 'fg3m') and _number(pick.get('ou_line'))
            and not float(pick['ou_line']).is_integer() and _number(pick.get('price')) and pick['price'] > 1
            and _number(pick.get('edge')))


def _daily_top(picks):
    nba = Path(__file__).resolve().parents[3] / '.agents' / 'skills' / 'nba'
    if str(nba) not in sys.path:
        sys.path.insert(0, str(nba))
    from nba_engine.featured import daily_top
    return daily_top(picks)


def _featured_records(day, day_picks, actuals):
    """First verified publication per game, then the same-day cap; settled from the box score."""
    if day < FEATURED_START_DATE or not day_picks:
        return []
    meta = {id(p): (tag, report, odds, published) for p, tag, report, odds, published in day_picks}
    out = []
    for pick in _daily_top([{**p, 'game_tag': tag} for p, tag, *_ in day_picks]):
        tag = pick['game_tag']
        _, report, odds, published = next(v for k, v in meta.items() if v[0] == tag)
        row = actuals.get((tag, pick['player'], pick['market']), {})
        if row.get('outcome') == 'void':
            state, actual = 'void', 'void'
        elif _number(row.get('actual')):
            actual = row['actual']
            won = actual > pick['ou_line'] if pick['side'] == 'over' else actual < pick['ou_line']
            state = 'won' if won else 'lost'
        else:
            state, actual = 'pending', None
        profit = round(pick['price'] - 1, 2) if state == 'won' else -1 if state == 'lost' else None
        out.append({'id': f'nba:{day}:{tag}:featured', 'day': day, 'event_name': tag.replace('_', ' @ '),
                    'game_tag': tag, 'start_time_utc': odds.get('event_start_time'), 'published_at': published,
                    'snapshot_id': report.parent.name, 'odds': pick['price'], 'stake': 1,
                    'tracking_kind': 'featured', 'rule': pick.get('rule'),
                    'edge': pick['edge'], 'p_model': pick.get('p_model'), 'p_fair': pick.get('p_fair'),
                    'state': state, 'profit': profit,
                    'legs': [{'player': pick['player'], 'team': pick.get('team') or '', 'market': pick['market'],
                              'stat': pick.get('stat'), 'ou_line': pick['ou_line'], 'side': pick['side'],
                              'price': pick['price'], 'state': state, 'actual': actual,
                              'settled_at': row.get('settled_at')}],
                    'settled_at': row.get('settled_at')})
    return out


def build_tracking(roots, ledger_root, firewall):
    from .multisport_exporter import nba_combos, nba_report_sidecar
    ledger_root = Path(ledger_root)
    folders = {}
    warnings = []
    for root in roots:
        for folder in Path(root).glob('????-??-?? NBA Analysis*'):
            day = folder.name[:10]
            try:
                datetime.strptime(day, '%Y-%m-%d')
            except ValueError:
                continue
            if day >= TRACKING_START_DATE:
                folders.setdefault(day, []).append(folder)
    records, featured_records = [], []
    for day, sources in sorted(folders.items()):
        settlements, actuals, excluded = {}, {}, set()
        path = ledger_root / 'ledger' / f'{day}.jsonl'
        try:
            # Stream large all-market ledgers; only small settlement rows survive.
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    row = json.loads(line)
                    if row.get('target_date') != day:
                        continue
                    if row.get('row_type') == 'no_prediction':
                        excluded.add(row.get('game_tag'))
                    elif (row.get('row_type') == 'settlement' and row.get('outcome') in {'hit','miss','void'}
                          and _verified_settlement(row)):
                        settlements.setdefault(_key(row.get('game_tag'), row), row)
                        actuals.setdefault(_key(row.get('game_tag'), row)[:3], row)
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append(f'settlement_unavailable:{day}')
            settlements, actuals = {}, {}
        if None in excluded:
            continue
        publications = []
        for folder in sources:
            publications.extend(verified_published_reports(folder, day, firewall, all_publications=True))
        selected, featured_seen, day_picks = set(), set(), []
        for tag, report, odds_path, published in sorted(publications, key=lambda r:(r[3],str(r[1]))):
            if tag in excluded or (tag in selected and tag in featured_seen):
                continue
            try:
                sidecar = json.loads(Path(str(report)+'.market_legs.json').read_text())
                odds = json.loads(odds_path.read_text())
                if tag not in featured_seen and nba_report_sidecar(report):
                    featured_seen.add(tag)
                    for pick in sidecar.get('featured') or []:
                        if _valid_pick(pick):
                            day_picks.append((pick, tag, report, odds, published))
                if tag in selected:
                    continue
                # Formal combos only from a sidecar bound to this exact report.
                cards = nba_combos(sidecar, day, tag, []) if nba_report_sidecar(report) else []
                # EXP-20261027-21: under the steady policy combo 1 IS the B2
                # selection and carries a disclosed negative EV.
                steady = sidecar.get('strategy_profile') == STEADY_POLICY
                card = next((c for c in cards if c['id'].endswith(':combo:1')
                             and c.get('decision') == 'BET' and c.get('odds_status') == 'sportsbet_sgm_quoted'
                             and _number(c.get('odds')) and c['odds'] >= 2
                             and _number(c.get('metrics',{}).get('expected_value'))
                             and (steady or c['metrics']['expected_value'] > 0)), None)
                if card:
                    card['tracking_kind'] = 'formal'
                # Track the steady research arm when no steady formal combo was
                # published (legacy EV-gated days, or a stop-loss pause).
                if not (steady and card):
                    card = _research_card(sidecar, odds, day, tag, published) or card
                if not card:
                    continue
                legs = []
                teams = {leg.get('player'):leg.get('team') for leg in sidecar.get('legs',[]) if isinstance(leg,dict)}
                # Team comes from the verified game-data/sidecar leg, not market family keys.
                raw = next((c for c in sidecar.get('combos',[]) if str(c.get('combo_id'))=='1'), {})
                for leg in card['legs']:
                    result = settlements.get(_key(tag,leg), {})
                    team_match = next((l.get('team') for l in raw.get('legs',[])
                                       if l.get('player')==leg.get('player')), None)
                    team = team_match or teams.get(leg.get('player'))
                    if team not in tag.split('_'):
                        team = ''
                    legs.append({**leg, 'team':team, 'state':{'hit':'won','miss':'lost','void':'void'}.get(result.get('outcome'),'pending'),
                                 'actual':result.get('actual'), 'settled_at':result.get('settled_at')})
                states = [leg['state'] for leg in legs]
                if not states:
                    continue
                # Any void leg makes the whole slip 作廢, even beside a lost leg: kept
                # as a record, never counted as a bet (no assumed refund, no repriced
                # win) — Kelvin 2026-11-03.
                state = ('unpriced' if not _number(card.get('odds')) else 'void' if 'void' in states
                         else 'lost' if 'lost' in states else 'pending' if 'pending' in states else 'won')
                profit = round(card['odds']-1, 2) if state=='won' else -1 if state=='lost' else None
                records.append({'id':card['id'], 'day':day, 'event_name':card['event_name'], 'game_tag':tag,
                                'start_time_utc':odds.get('event_start_time'), 'published_at':published,
                                'snapshot_id':report.parent.name, 'odds':card['odds'], 'stake':1,
                                'tracking_kind':card['tracking_kind'], 'model_version':card.get('model_version'),
                                # Stop-loss scope (EXP-20261027-21) is the formal policy in force at publication.
                                'strategy_profile':sidecar.get('strategy_profile'),
                                'model_probability':card.get('model_probability', card.get('metrics',{}).get('model_probability')),
                                'state':state, 'profit':profit, 'legs':legs,
                                'settled_at':max((l.get('settled_at') or '' for l in legs),default='') or None})
                selected.add(tag)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                warnings.append(f'publication_unavailable:{day}:{tag}')
        featured_records.extend(_featured_records(day, day_picks, actuals))
    return {'schema_version':2, 'inception_date':TRACKING_START_DATE, 'basis':'first_verified_formal_or_steady_research', 'stake_dollars':1,
            'status':'valid' if folders else 'unavailable', 'generated_at':datetime.now(timezone.utc).isoformat(),
            'covered_dates':sorted(folders), 'records':records,
            # EXP-20261110-01 大細盤精選 paper bets: kept apart so the ROI board, the steady
            # stop-loss and the SGM views (which all read `records`) never see them.
            'featured_records':featured_records, 'featured_inception_date':FEATURED_START_DATE,
            'warnings':sorted(set(warnings))}


def export_tracking(repo_root):
    """Locate installed runtime and archives, never production data during tests."""
    roots = [Path(repo_root)]
    ledger = os.environ.get('WONGCHOI_NBA_MARKET_LEDGER_ROOT')
    if 'pytest' in sys.modules:
        return build_tracking(roots, ledger, _firewall()) if ledger else {
            'schema_version':1,'status':'unavailable','records':[], 'warnings':['test_isolation']}
    added = str(Path(repo_root)/'.agents'/'skills')
    sys.path.insert(0, added)
    try:
        from shared_wong_choi.release_automation import production_roots
        runtime = production_roots().get('nba')
        if runtime:
            roots.append(runtime)
        # Local primary is shared with the existing unattended NBA installer.
        roots.append(Path(os.environ.get('WONGCHOI_NBA_DATA_ROOT') or Path.home()/'WongChoiData'/'Wong Choi NBA Analysis'))
        return build_tracking(list(dict.fromkeys(roots)), ledger or Path.home()/'WongChoiData'/'NBA_Market_Eval', _firewall())
    finally:
        sys.path.remove(added)


def _firewall():
    from .multisport_exporter import nba_publication_firewall
    return nba_publication_firewall
