"""Banker-only publication and isolated forward experiments; no real ledger/network."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import sys

AUTO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AUTO))
sys.path.insert(0, str(AUTO.parent))
sys.path.insert(0, str(AUTO.parent/'nba_wong_choi/scripts'))
import generate_nba_reports as report
import nba_market_ledger as ledger
import nba_reliability as reliability
import nba_combo_roi as roi
from nba_review_candidates import banker_funnel, build_banker_shadow, banker_shadow_review
from nba_sgm_quote import QuotedCombo, legs_identity


def leg(name, *, edge=-20, probability=20, hit=90, cov=.3):
    return {'market_type': report.PLAYER_MARKET, 'player': name, 'team': 'BOS', 'category': 'REB',
            'line_val': 4, 'avg': 8, 'l3_avg': 8, 'hit_l10': hit, 'hit_l5': hit, 'edge': edge,
            'estimated_prob': probability, 'odds': 1.5, 'cov': cov, 'season_phase': 'MID_SEASON',
            'desc': name+' REB 4+'}


def test_no_ev_shadow_can_exist_without_becoming_formal_bet_or_mutating_inputs():
    pool = [leg('A'), leg('B'), leg('C')]
    original = deepcopy(pool)
    calls = []
    def quote(_, legs):
        calls.append(len(legs))
        return QuotedCombo(legs, {'status': 'ok', 'decimal_odds': 2.1})
    def metrics(combo):
        p = math.prod(c['estimated_prob']/100 for c in combo)
        return {'adjusted_joint_prob': p, 'product_of_leg_prices': math.prod(c['odds'] for c in combo),
                'combo_ev_pct': (p*getattr(combo, 'quote', {}).get('decimal_odds', 2.1)-1)*100}
    rows = build_banker_shadow(pool, {}, select=report.select_combo_1, quote=quote,
                               valid_quote=lambda *a: True, evaluate=metrics)
    assert [r['eligible'] for r in rows] == [False, False, True]
    assert all(r['decision'] == 'OBSERVE' and r['analysis_only'] for r in rows)
    assert rows[2]['expected_value'] < 0 and rows[2]['sportsbet_sgm_price'] == 2.1
    assert report.select_combo_1(pool) == [] and pool == original
    public = banker_shadow_review(rows)
    assert len(public) == 1 and public[0]['candidate_id'] == 'steady'
    assert 'EV 非正' in ' '.join(public[0]['reasons'])


def test_formal_default_and_explicit_ev_flags_are_identical_with_real_winning_pools():
    cases = ([leg('A', edge=20, probability=95), leg('B', edge=20, probability=95), leg('C', edge=20, probability=95)],
             [leg('A', edge=20, probability=95, hit=70, cov=.7), leg('B', edge=20, probability=95, hit=70, cov=.7), leg('C', edge=20, probability=95, hit=70, cov=.7)])
    for pool in cases:
        a = report.select_combo_1(deepcopy(pool))
        b = report.select_combo_1(deepcopy(pool), require_leg_ev=True, require_combo_ev=True)
        assert a and [c['desc'] for c in a] == [c['desc'] for c in b]
        assert a.selection_rule == b.selection_rule


def test_shadow_unverified_or_below_two_price_never_counts_as_trade():
    pool = [leg('A'), leg('B'), leg('C')]
    def metrics(_):
        return {'adjusted_joint_prob': .8, 'combo_ev_pct': 20, 'product_of_leg_prices': 3.375}
    for price, valid, reason in [(1.9, True, 'actual_price_below_2'), (3, False, 'quote_unverified')]:
        rows = build_banker_shadow(pool, {}, select=report.select_combo_1,
                                   quote=lambda _, legs: QuotedCombo(legs, {'decimal_odds': price}),
                                   valid_quote=lambda *a: valid, evaluate=metrics)
        assert not rows[2]['eligible'] and reason in rows[2]['reasons']
        if not valid:
            assert rows[2]['sportsbet_sgm_price'] is None and rows[2]['expected_value'] is None


def test_funnel_separates_hit_rate_and_edge_bottlenecks_without_mutation():
    pool = [leg('A'), leg('B', edge=10, hit=30), leg('C', edge=10, hit=90)]
    saved = deepcopy(pool)
    counts = banker_funnel(pool, playoff=lambda *a: True, reflector=lambda *a: True)['strict']
    assert counts['remaining']['recent_hits'] == 2
    assert counts['remaining']['nonnegative_edge'] == 1
    assert counts['independent_failures']['recent_hits'] == 1
    assert counts['independent_failures']['nonnegative_edge'] == 1
    assert pool == saved


def _day(root, day, *, picked=False, missing=False, warmup=False):
    identity = reliability.current_model_id()
    rows = []
    for tag in ('AAA_BBB', 'CCC_DDD'):
        base = {'game_tag': tag, 'snapshot_id': day, 'snapshot_role': 'warmup' if warmup else 'production',
                'snapshot_created_at': day+'T10:00:00Z', 'season_phase': 'EARLY_REGULAR',
                'post_tip': False, 'late_write': False, 'tip_unknown': False}
        rows.append(dict(base, row_type='price_obs', player='A', market='reb', line=4, price=1.5,
                         captured_at=day+'T10:00:00Z'))
        if missing and tag == 'CCC_DDD':
            continue
        rows.append(dict(base, row_type='model_obs', player='A', market='reb', line=4,
                         probability_model_id=identity, picked_in=['1'] if picked else []))
    ledger.append_rows(root, day, rows)


def test_three_complete_zero_runs_trigger_review_and_a_bet_resets_it(tmp_path):
    for day in ('2026-10-23', '2026-10-24', '2026-10-25'):
        _day(tmp_path, day)
    health = reliability.selection_health('2026-10-25', tmp_path)
    assert health['status'] == 'review_required' and health['zero_banker_runs'] == 3
    assert '策略需審計' in reliability.selection_message(health)
    _day(tmp_path, '2026-10-26', picked=True)
    assert reliability.selection_health('2026-10-26', tmp_path)['zero_banker_runs'] == 0


def test_missing_or_warmup_coverage_breaks_zero_streak(tmp_path):
    _day(tmp_path, '2026-10-23')
    _day(tmp_path, '2026-10-24', missing=True)
    _day(tmp_path, '2026-10-25')
    assert reliability.selection_health('2026-10-25', tmp_path)['zero_banker_runs'] == 1
    _day(tmp_path, '2026-10-26', warmup=True)
    assert reliability.selection_health('2026-10-26', tmp_path)['zero_banker_runs'] == 0


def test_formal_report_never_calls_retired_selectors(monkeypatch):
    def retired(*a, **k):
        raise AssertionError('retired formal selector was called')
    for name in ('select_combo_2', 'select_combo_3', 'select_combo_x_value_bomb'):
        monkeypatch.setattr(report, name, retired)
    text = report.gen_full_report({}, {}, {}, {}, {}, [], 'fixture')
    assert '只保留穩膽' in text
    assert '組合 2:' not in text and '組合 3:' not in text and '組合 X:' not in text


def test_shadow_roi_is_separate_uses_frozen_price_and_latest_no_trade_overrides_old(tmp_path):
    identity = reliability.current_model_id()
    day = '2026-10-25'
    legs = [{'player': 'A', 'market': 'reb', 'line': 4, 'side': 'over', 'price': 1.5},
            {'player': 'B', 'market': 'reb', 'line': 4, 'side': 'over', 'price': 1.5}]
    base = {'target_date': day, 'game_tag': 'AAA_BBB', 'snapshot_id': 's1', 'snapshot_role': 'production',
            'snapshot_created_at': day+'T10:00:00Z', 'season_phase': 'EARLY_REGULAR',
            'post_tip': False, 'late_write': False, 'tip_unknown': False, 'probability_model_id': identity}
    rows = [dict(base, row_type='model_obs', player='A', market='reb', line=4)]
    for arm in ('B0', 'B1', 'B2'):
        rows.append(dict(base, row_type='banker_shadow_obs', version='banker-ev-shadow-v1', arm=arm,
                         eligible=arm == 'B2', legs=legs, sportsbet_sgm_status='ok', sportsbet_sgm_price=2.1,
                         sgm_quote={'status': 'ok', 'decimal_odds': 2.1, 'legs_sha256': legs_identity(legs)}))
    rows += [dict(row_type='settlement', game_tag='AAA_BBB', outcome='hit', **leg) for leg in legs]
    ledger.append_rows(tmp_path, day, rows)
    shadow = roi.banker_shadow(day, tmp_path)
    assert shadow['arms']['B2']['sgm']['profit_units'] == 1.1
    assert shadow['arms']['B0']['sgm']['roi'] is None
    assert not shadow['promotion_allowed'] and shadow['paired_roi_delta_ci95']['B1_minus_B0'] is None
    assert roi.daily(day, tmp_path)['total']['combos'] == 0
    # The latest run says NO TRADE: never cherry-pick the earlier winning one.
    newer = [dict(row, snapshot_id='s2', snapshot_created_at=day+'T11:00:00Z', eligible=False)
             for row in rows if row.get('row_type') in ('model_obs', 'banker_shadow_obs')]
    ledger.append_rows(tmp_path, day, newer)
    assert roi.banker_shadow(day, tmp_path)['arms']['B2']['sgm']['n'] == 0


def test_snapshot_records_shadow_separately_with_quote_identity_and_idempotency(tmp_path):
    from nba_sgm_quote import quote_combo
    now = datetime(2026, 10, 25, 1, tzinfo=timezone.utc)
    for case in ('valid', 'tampered', 'future', 'warmup'):
        folder = tmp_path/case/'snapshot'
        folder.mkdir(parents=True)
        source = {'target_analysis_date': '2026-10-25', 'event_start_time': (now+timedelta(hours=2)).isoformat(),
                  'extraction_time': now.isoformat(), 'player_props': {'rebounds': {name: {'lines': {'4': '1.5'}} for name in ('A', 'B')}},
                  'sgm_pricing': {'class_external_id': 16, 'competition_external_id': 1, 'event_external_id': 2,
                                  'outcomes': {'rebounds': {name: {'4': {'market_external_id': i+10, 'outcome_external_id': i+20}} for i, name in enumerate(('A', 'B'))}}}}
        legs = [{'player': name, 'market': 'reb', 'line': 4, 'price': 1.5, 'p_final': .8,
                 'probability_model_id': reliability.current_model_id()} for name in ('A', 'B')]
        captured = now+timedelta(seconds=1) if case == 'future' else now
        quoted = quote_combo(source, legs, now=captured,
                             post=lambda _: (200, {'price': {'numerator': 1.1, 'denominator': 1, 'quoteId': 'fixture'}}))
        if case == 'tampered':
            quoted.quote['request_sha256'] = 'bad'
        body = 'synthetic report'
        (folder/'Game_AAA_BBB_Full_Analysis.md').write_text(body)
        (folder/'Sportsbet_Odds_AAA_BBB.json').write_text(json.dumps(source))
        (folder/'manifest.json').write_text(json.dumps({'snapshot_role': 'warmup' if case == 'warmup' else 'production',
            'created_at': now.isoformat(), 'season_context': {'season_phase': 'EARLY_REGULAR'}}))
        (folder/'Game_AAA_BBB_Full_Analysis.md.market_legs.json').write_text(json.dumps({
            'report_sha256': hashlib.sha256(body.encode()).hexdigest(), 'odds_extraction_time': now.isoformat(),
            'legs': legs, 'combos': [], 'banker_shadow': [{'version': 'banker-ev-shadow-v1', 'arm': arm,
                'eligible': True, 'legs': legs, 'sportsbet_sgm_price': 2.1, 'sgm_quote': quoted.quote} for arm in ('B0', 'B1', 'B2')]}))
        root = tmp_path/case/'ledger-root'
        ledger.record_snapshot(folder, '2026-10-25', now=now, root=root)
        assert ledger.record_snapshot(folder, '2026-10-25', now=now, root=root)['appended'] == 0
        rows = ledger.read_rows(root, '2026-10-25')
        research = [r for r in rows if r['row_type'] == 'banker_shadow_obs']
        assert len(research) == 3 and all(r['analysis_only'] and r['decision'] == 'OBSERVE' for r in research)
        assert all(r['eligible'] == (case in ('valid', 'warmup')) for r in research)
        assert not any(r['row_type'] == 'sgm_obs' for r in rows)
        if case == 'warmup':
            assert roi.banker_shadow('2026-10-25', root)['recorded_game_opportunities'] == 0


def test_no_bet_card_explains_real_funnel_and_zero_run_signal():
    import nba_daily_schedule as schedule
    message = schedule.nba_betting_message('2026-10-25', {
        'validation_status': 'blocked', 'warnings': ['no_validated_nba_combos'], 'recommendations': [],
        'selection_health': {'status': 'review_required', 'zero_banker_runs': 3},
        'latest_analysis': {'coverage': {'analysed_games': 8, 'scheduled_games': 8}, 'games': [{
            'diagnostics': {'banker_funnel': {'fallback': {'remaining': {'recent_hits': 12, 'nonnegative_edge': 0}}}}}]}})
    assert '8/8' in message and '合格 12 腿' in message and '非負 edge 0 腿' in message
    assert '策略需審計' in message and '真實 SGM 價 ≥2.0' in message
    assert '紀律：' not in message


def test_frozen_previous_commit_banker_vectors_are_unchanged():
    fixture = json.loads((Path(__file__).parent/'fixtures/banker_86082fda.json').read_text())
    for case in fixture['cases']:
        selected = report.select_combo_1(deepcopy(case['pool']))
        assert [c['desc'] for c in selected] == case['expected_descriptions'], case['case']
        assert selected.selection_rule == case['selection_rule'], case['case']
