from datetime import date

from research.tennis_unified.book_inventory import event_date, paired_columns, valid_pair


def test_roster_never_invents_a_book_from_opposite_columns_or_aggregate_prices():
    header = ['Winner', 'Loser', 'W1', 'L1', 'B365W', 'B365L', 'PSW', 'PSL', 'MaxW', 'MaxL', 'AvgW', 'AvgL', 'IWW']
    assert paired_columns(header) == ['B365', 'PS']
    assert not valid_pair(None, 2.)
    assert not valid_pair(float('nan'), 2.)
    assert not valid_pair(True, 2.)
    assert valid_pair(1.5, 2.8)


def test_event_dates_are_parsed_without_repairing_anomalous_years():
    assert event_date('2029-07-25') == date(2029, 7, 25)
    assert event_date('25/07/2026') == date(2026, 7, 25)
    assert event_date('RR') is None
