from copy import deepcopy
from datetime import date

import pytest

from .prices import (book_alias, event_signature, identity_candidates, resolve_observations,
                     source_aliases, source_stage, validate_outcome)
from .market_cohort import isolate
from .features import make_features
from .test_history_features import row, PRIORS


def fixture():
    source = {'key': 'one', 'a': 1, 'b': 2, 'date': '2024-12-30', 'surface': 'Hard',
              'best_of': 3, 'round': 'R32', 'y': 1, 'sets': [[6, 2], [6, 3]]}
    book = {'Round': '1st Round', 'Surface': 'Hard', 'Best of': 3, 'Tournament': 'Brisbane International',
            'Location': 'Brisbane', 'W1': 6, 'L1': 2, 'W2': 6, 'L2': 3}
    metadata = {'one': {'draw_size': '32', 'tourney_name': 'Brisbane'}}
    return source, book, metadata


def test_aliases_accents_hyphens_and_multiword_surname():
    assert book_alias('Bautista Agut R.') in source_aliases('Roberto Bautista Agut')
    assert book_alias('Osorio Serrano M.C.') in source_aliases('Maria Camila Osorio Serrano')
    assert book_alias('Parrizas Diaz N.') in source_aliases('Nuria Parrizas-Diaz')


def test_round_normalisation_uses_draw_size_not_just_pair_and_date():
    assert source_stage('R64', '128') == '2'
    assert source_stage('R64', '96') == '2'
    assert source_stage('R64', '64') == '1'
    assert source_stage('R32', None) is None


def test_identity_is_unordered_and_selected_before_labels():
    source, book, metadata = fixture()
    assert identity_candidates(book, date(2025, 1, 1), 2, 1, [source], metadata) == [source]
    assert validate_outcome(book, source, 2) == 'winner_conflict'
    changed = dict(source, y=0, sets=[[0, 6], [0, 6]])
    assert identity_candidates(book, date(2025, 1, 1), 1, 2, [source, changed], metadata) == [source, changed]


@pytest.mark.parametrize('field,value', [('Round', 'The Final'), ('Best of', 5), ('Surface', 'Clay'), ('Location', 'Elsewhere')])
def test_identity_checks_real_event_and_contract(field, value):
    source, book, metadata = fixture()
    if field == 'Location':
        book['Tournament'] = 'Other event'
    book[field] = value
    assert identity_candidates(book, date(2025, 1, 1), 1, 2, [source], metadata) == []


def test_missing_event_name_cannot_match_empty_location():
    source, book, metadata = fixture()
    metadata['one']['tourney_name'] = ''
    book['Location'] = ''
    assert identity_candidates(book, date(2025, 1, 1), 1, 2, [source], metadata) == []


def test_source_calendar_context_is_not_relabelled_from_sheet_year():
    source, book, metadata = fixture()
    assert identity_candidates(book, date(2024, 12, 31), 1, 2, [source], metadata)
    assert not identity_candidates(book, date(2024, 12, 29), 1, 2, [source], metadata)
    assert not identity_candidates(book, date(2025, 1, 20), 1, 2, [source], metadata)


def test_label_score_validation_happens_after_unique_identity():
    source, book, _ = fixture()
    assert validate_outcome(book, source, 1) is None
    book['W1'] = 7
    assert validate_outcome(book, source, 1) == 'score_conflict'


def test_differing_unclocked_rows_are_held_not_best_price_selected():
    row = {'key': 'one', 'book_event_date': '2025-01-01', 'locator': {'file': 'a', 'row': 2},
           'quotes': [{'book': 'B365', 'odds_a': 2., 'odds_b': 1.8}]}
    second = deepcopy(row)
    second['locator']['row'] = 3
    selected, held, collapsed = resolve_observations([row, second], set())
    assert len(selected) == len(collapsed) == 1 and not held
    second['quotes'][0]['odds_a'] = 2.1
    selected, held, collapsed = resolve_observations([row, second], set())
    assert not selected and len(held) == 2
    assert not resolve_observations([row], {'one'})[0]


def test_slam_event_alias_is_explicit():
    assert event_signature('Roland Garros') == event_signature('French Open')


def test_disputed_event_removed_from_history_not_only_scoring_target():
    rows = [dict(row('2020-12-01', key='warm'), raw_id=1, ordinal=0),
            dict(row('2021-01-01', y=0, key='bad'), raw_id=1, ordinal=1),
            dict(row('2021-03-01', key='target'), raw_id=1, ordinal=2)]
    data = {'rows': rows, 'raw_rows': 3, 'excluded': [], 'duplicate_observations': 0}
    clean = isolate(data, {'conflicted_match_keys': ['bad'], 'rows': [{'key': 'target'}]})
    assert len(clean['rows']) == 2 and clean['excluded_counts']['new_cross_source_dispute'] == 1
    before = make_features(rows, PRIORS)[0][-1]
    after = make_features(clean['rows'], PRIORS)[0][-1]
    assert 'bad' in before['a_history_keys'] and 'bad' not in after['a_history_keys']
    assert before['x']['elo'] != after['x']['elo']
