from research.tennis_unified.mcp_qualification import identity, total_pair


META = {'Player 1': 'Alpha One', 'Player 2': 'Beta Two', 'Date': '20240103',
        'Round': 'R32', 'Surface': 'Hard', 'Best of': '3', 'Tournament': 'Test Open'}
SOURCE = {'key': 'k', 'a': 1, 'b': 2, 'date': '20240101', 'surface': 'Hard', 'round': 'R32',
          'best_of': 3, 'event_name': 'Test Open'}
NAMES = {('ATP', 'alphaone'): {1}, ('ATP', 'betatwo'): {2}}


def test_identity_uses_unordered_pair_before_any_statistics_or_winner():
    source = {**SOURCE, 'date': '2024-01-01'}
    assert identity(META, 'ATP', NAMES, [source]) == (source, None)
    swapped = {**META, 'Player 1': META['Player 2'], 'Player 2': META['Player 1']}
    assert identity(swapped, 'ATP', NAMES, [source]) == (source, None)
    assert identity(META, 'ATP', NAMES, [source, {**source, 'key': 'other'}])[0] is None


def test_unknown_surface_is_retained_as_ambiguity_not_silently_removed():
    source = {**SOURCE, 'date': '2024-01-01'}
    unknown = {**source, 'key': 'other', 'surface': ''}
    assert identity(META, 'ATP', NAMES, [source, unknown])[0] is None
    assert identity(META, 'ATP', NAMES, [unknown])[1] == 'source_surface_unknown'


def totals():
    return [{'set': 'Total', 'player': name, 'serve_pts': '10', 'first_in': '6', 'first_won': '4',
             'second_in': '4', 'second_won': '2', 'return_pts': '10', 'return_pts_won': '4',
             'aces': '1', 'dfs': '1'} for name in ('Alpha One', 'Beta Two')]


def test_per_set_rows_are_not_added_to_Total_and_duplicates_held():
    rows = totals()
    assert total_pair(META, rows + [{**rows[0], 'set': '1'}])[1] is None
    assert total_pair(META, rows + [rows[0]])[1] == 'missing_or_duplicate_Total_rows'


def test_point_denominators_and_opponent_conservation_not_only_rate_bounds():
    rows = totals()
    rows[0]['return_pts_won'] = '3'
    assert total_pair(META, rows)[1] == 'opponent_point_conservation_conflict'
    rows = totals()
    rows[0]['first_won'] = '7'
    assert total_pair(META, rows)[1] == 'invalid_Total_point_domain'
