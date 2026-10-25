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
                or candidate.get('version') != 'banker-ev-shadow-v1'
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
                'legs':[{**l, 'stat':l.get('category') or str(l.get('market')).upper()} for l in legs]}
    return None


def build_tracking(roots, ledger_root, firewall):
    from .multisport_exporter import _parse_nba_combos, _hydrate_nba_quotes
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
            folders.setdefault(day, []).append(folder)
    records = []
    for day, sources in sorted(folders.items()):
        settlements, excluded = {}, set()
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
        except FileNotFoundError:
            pass
        except (OSError, ValueError, TypeError, AttributeError):
            warnings.append(f'settlement_unavailable:{day}')
            settlements = {}
        if None in excluded:
            continue
        publications = []
        for folder in sources:
            publications.extend(verified_published_reports(folder, day, firewall, all_publications=True))
        selected = set()
        for tag, report, odds_path, published in sorted(publications, key=lambda r:(r[3],str(r[1]))):
            if tag in selected or tag in excluded:
                continue
            try:
                text = report.read_text(encoding='utf-8')
                sidecar = json.loads(Path(str(report)+'.market_legs.json').read_text())
                odds = json.loads(odds_path.read_text())
                cards = _parse_nba_combos(text, day, tag, [])
                _hydrate_nba_quotes(cards, text, sidecar)
                card = next((c for c in cards if c['id'].endswith(':combo:1')
                             and c.get('decision') == 'BET' and c.get('odds_status') == 'sportsbet_sgm_quoted'
                             and _number(c.get('odds')) and c['odds'] >= 2
                             and _number(c.get('metrics',{}).get('expected_value'))
                             and c['metrics']['expected_value'] > 0), None)
                if card:
                    card['tracking_kind'] = 'formal'
                # Track the current steady research arm when published alongside
                # a legacy formal combo; one model selection per game, frozen.
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
                state = ('unpriced' if not _number(card.get('odds')) or 'void' in states else 'lost' if 'lost' in states
                         else 'pending' if 'pending' in states else 'won')
                profit = round(card['odds']-1, 2) if state=='won' else -1 if state=='lost' else None
                records.append({'id':card['id'], 'day':day, 'event_name':card['event_name'], 'game_tag':tag,
                                'start_time_utc':odds.get('event_start_time'), 'published_at':published,
                                'snapshot_id':report.parent.name, 'odds':card['odds'], 'stake':1,
                                'tracking_kind':card['tracking_kind'], 'model_version':card.get('model_version'),
                                'state':state, 'profit':profit, 'legs':legs,
                                'settled_at':max((l.get('settled_at') or '' for l in legs),default='') or None})
                selected.add(tag)
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                warnings.append(f'publication_unavailable:{day}:{tag}')
    return {'schema_version':2, 'basis':'first_verified_formal_or_steady_research', 'stake_dollars':1,
            'status':'valid' if folders else 'unavailable', 'generated_at':datetime.now(timezone.utc).isoformat(),
            'covered_dates':sorted(folders), 'records':records, 'warnings':sorted(set(warnings))}


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
