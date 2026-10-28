import pytest

from research.tennis_unified.slam_points import PointReplay, elapsed_seconds, replay, set_rule
from research.tennis_unified.slam_qualification import format_code


@pytest.mark.parametrize('event,year,trigger,target', [
    ('ausopen', 2018, None, None), ('ausopen', 2019, 6, 10),
    ('frenchopen', 2021, None, None), ('frenchopen', 2022, 6, 10),
    ('wimbledon', 2018, None, None), ('wimbledon', 2019, 12, 7),
    ('wimbledon', 2021, 12, 7), ('wimbledon', 2022, 6, 10),
    ('usopen', 2021, 6, 7), ('usopen', 2022, 6, 10)])
def test_historical_deciding_rules_are_not_modern_backfills(event, year, trigger, target):
    for best in (3, 5):
        r = set_rule(event, year, best, best)
        assert (r['tiebreak_games'], r['tiebreak_points']) == (trigger, target)
        assert set_rule(event, year, best, best - 1) == {'tiebreak_games': 6, 'tiebreak_points': 7}


def test_unknown_event_or_year_has_no_default_rule():
    for event, year in [('usopen', 2010), ('usopen', 2025), ('olympics', 2024)]:
        with pytest.raises(ValueError, match='UNKNOWN'):
            set_rule(event, year, 3, 3)


def test_advantage_game_and_wrong_server_cannot_be_repaired_from_scoreboard():
    p = PointReplay('usopen', 2024, 3)
    for winner in (1, 1, 1, 2, 2, 2):
        r = p.step(1, winner)
    assert (r['P1Score'], r['P2Score']) == ('40', '40')
    assert p.step(1, 2)['P2Score'] == 'AD'
    assert p.step(1, 1)['P1Score'] == '40'
    p.step(1, 1)
    r = p.step(1, 1)
    assert (r['GameWinner'], r['P1GamesWon'], r['P1Score'], r['P2Score']) == ('1', '1', '0', '0')
    with pytest.raises(ValueError, match='service_order'):
        p.step(1, 1)


def deciding_state(event, year, games):
    p = PointReplay(event, year, 3)
    p.sets = [1, 1]
    p.set_scores = [[6, 0], [0, 6]]
    p.games = games
    p.next_server = 1
    return p


def test_ten_point_decider_does_not_stop_at_seven_and_rejects_postterminal_points():
    p = deciding_state('ausopen', 2019, [6, 6])
    servers = [1, 2, 2, 1, 1, 2, 2, 1, 1, 2]
    for server in servers[:7]:
        p.step(server, 1)
    assert not p.winner and p.points == [7, 0]
    for server in servers[7:]:
        last = p.step(server, 1)
    assert p.winner == 1 and p.set_scores[-1] == [7, 6]
    assert last['SetWinner'] == '1'
    with pytest.raises(ValueError, match='after_terminal'):
        p.step(2, 1)


def test_wimbledon_2018_advantage_and_2019_twelve_all_distinct():
    old = deciding_state('wimbledon', 2018, [12, 12])
    for _ in range(4):
        old.step(1, 1)
    assert old.games == [13, 12] and not old.winner
    for _ in range(4):
        old.step(2, 1)
    assert old.winner == 1 and old.set_scores[-1] == [14, 12]
    new = deciding_state('wimbledon', 2019, [12, 12])
    for server in [1, 2, 2, 1, 1, 2, 2]:
        new.step(server, 1)
    assert new.winner == 1 and new.set_scores[-1] == [13, 12]


def test_tiebreak_first_receiver_serves_next_set_even_when_last_server_same_receiver():
    p = PointReplay('usopen', 2024, 3)
    p.games, p.next_server = [6, 6], 1
    for server in [1, 2, 2, 1, 1, 2, 2]:
        p.step(server, 1)
    assert p.next_server == 2 and p.sets == [1, 0]
    assert p.step(2, 1)['SetNo'] == '2'


def test_nonplay_markers_do_not_add_points_and_missing_points_are_not_interpolated():
    marker = {'PointNumber': '0X', 'PointServer': '0', 'PointWinner': '0',
              'P1Score': '0', 'P2Score': '0', 'P1GamesWon': '0', 'P2GamesWon': '0'}
    row = {'PointNumber': '2', 'PointServer': '1', 'PointWinner': '1', 'ElapsedTime': '0:00:20'}
    r = replay([marker, row], 'usopen', 2024, 3)
    assert r['numeric_points_replayed'] == 0 and r['nonplay_markers'] == ['0X']
    assert r['errors'] == {'nonconsecutive_point_number': 1, 'no_terminal_match': 1}


def test_zero_initial_marker_and_absent_scoreboard_are_not_played_points_or_forged_zeroes():
    marker = {'PointNumber': '0', 'PointServer': '0', 'PointWinner': '0',
              'P1Score': '0', 'P2Score': '0', 'P1GamesWon': '0', 'P2GamesWon': '0'}
    row = {'PointNumber': '1', 'PointServer': '2', 'PointWinner': '1', 'ElapsedTime': '',
           'SetNo': '1', 'GameNo': '1', 'P1Score': '15', 'P2Score': '0'}
    result = replay([marker, row], 'ausopen', 2018, 3)
    assert result['numeric_points_replayed'] == 1 and result['nonplay_markers'] == ['0']
    assert result['errors'] == {'no_terminal_match': 1}
    assert result['missing_scoreboard_counts']['GameWinner'] == 1
    assert not result['full_scoreboard_verified']


def test_elapsed_duration_is_not_wallclock_and_bad_values_stay_missing():
    assert elapsed_seconds('2:23:57') == 8637
    assert elapsed_seconds('0:60:01') is None
    assert elapsed_seconds('') is None


def test_two_documented_id_shapes_and_explicit_metadata_conflict():
    assert format_code({'match_num': '1701', 'event_name': "Men's Singles", 'round': 'Final'}) == ('ATP', 5, 'F', True)
    assert format_code({'match_num': 'WS101'}) == ('WTA', 3, 'R128', False)
    assert format_code({'match_num': '1501', 'round': 'Quarters'})[2] == 'QF'
    assert format_code({'match_num': '2601', 'round': 'round_6'})[2] == 'SF'
    with pytest.raises(ValueError, match='event_name'):
        format_code({'match_num': '1101', 'event_name': "Women's Singles"})


def test_infosys_game_token_is_checked_and_not_treated_as_a_missing_number():
    rows = [{'PointNumber': str(i), 'PointServer': '1', 'PointWinner': '1',
             'SetNo': '1', 'GameNo': '1', 'P1Score': score, 'P2Score': '0'}
            for i, score in enumerate(('15', '30', '40', 'GAME'), 1)]
    correct = replay(rows, 'frenchopen', 2020, 3)
    assert correct['errors'] == {'no_terminal_match': 1}
    rows[-1]['P1Score'] = '0'
    assert replay(rows, 'frenchopen', 2020, 3)['errors']['P1Score_postpoint_conflict'] == 1


def test_cumulative_game_number_schema_crosses_set_boundary_explicitly():
    rows = []
    for game in range(7):
        server = 1 if game % 2 == 0 else 2
        for point, score in enumerate(('15', '30', '40', '0')):
            rows.append({'PointNumber': str(game * 4 + point + 1), 'PointServer': str(server),
                'PointWinner': '1', 'SetNo': '1' if game < 6 else '2', 'GameNo': str(game + 1),
                'P1Score': score, 'P2Score': '0'})
    assert replay(rows, 'ausopen', 2020, 3)['errors'] == {'no_terminal_match': 1}
    assert replay(rows, 'usopen', 2020, 3)['errors']['GameNo_postpoint_conflict'] == 4
