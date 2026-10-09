"""Regression tests for racecard-authoritative HKJC Facts identities."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("inject_hkjc_fact_anchors.py")
SPEC = importlib.util.spec_from_file_location("inject_hkjc_fact_anchors_test", SCRIPT)
inject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inject)


def test_profile_join_uses_date_not_position():
    entries = [
        {'date': '20/05/26', 'placing': 0, 'finish_time_raw': '--'},
        {'date': '15/04/26', 'placing': 6, 'finish_time_raw': '1.40.00'},
        {'date': '25/03/26', 'placing': 7, 'finish_time_raw': '1.41.00'},
    ]
    assert inject._profile_for_race({'date': '15/04/2026'}, entries) == entries[1]
    assert inject._profile_for_race({'date': '01/01/2026'}, entries) == {}
    assert inject._profile_for_race({'date': '15/04/2026'}, entries + [entries[1]]) == {}


def test_stats_exclude_unknown_zero_and_future_with_audit():
    entries = [
        {'date': '08/10/26', 'placing': 1, 'distance': 1650},
        {'date': '07/10/26', 'placing': 1, 'distance': 1650},
        {'date': '20/05/26', 'placing': 0, 'distance': 1650},
        {'date': '15/04/26', 'placing': 6, 'distance': 1650},
    ]
    stats = inject.compute_stats([], '跑馬地', 1650, '2026-10-07', profile_entries=entries)
    assert stats['recent_6'] == [6]
    assert stats['days_since_last'] == 175
    assert len(stats['history_exclusions']) == 3


def test_non_finish_status_is_retained_not_invented_as_last_place():
    entries = [
        {'date': '20/05/26', 'placing': 0, 'placing_raw': 'DNF', 'distance': 1650},
        {'date': '15/04/26', 'placing': 6, 'distance': 1650},
    ]
    stats = inject.compute_stats([], '跑馬地', 1650, '2026-10-07', profile_entries=entries)
    assert stats['recent_6'] == [6]
    assert stats['history_exclusions'][0]['status_raw'] == 'DNF'


def test_rendered_history_does_not_shift_after_non_finish():
    horse = {'num': 2, 'name': 'test', 'jockey': 'j', 'weight': 130,
             'barrier': 6, 'races': [{'date': '15/04/2026', 'distance': 1650,
                                     'venue': '跑馬地', 'finish': 6,
                                     'sectionals': {}, 'energy': 0}]}
    profile = {'entries': [
        {'date': '20/05/26', 'placing': 0, 'distance': 1650},
        {'date': '15/04/26', 'placing': 6, 'distance': 1650,
         'running_positions': [3, 3, 4, 6], 'margin_raw': '4-1/2'},
    ]}
    block = inject.generate_horse_block(horse, '跑馬地', 1650,
                                        profile_data=profile, race_date='2026-10-07')
    row = next(line for line in block.splitlines() if line.startswith('| 1 |'))
    assert '15/04/2026' in row and '3-3-4-6' in row and '4-1/2' in row


def _runner(number: int, name: str, horse_id: str) -> str:
    return (
        f"馬號: {number}\n"
        f"馬名: {name}\n"
        f"烙號: {horse_id.rsplit('_', 1)[-1]}\n"
        f"HKJC馬匹ID: {horse_id}\n"
        f"負磅: 133\n騎師: 希威森\n檔位: {number}\n"
        f"練馬師: 沈集成\n排位體重: 1117\n配備: TT\n"
    )


def _withdrawn_runner(number: int, name: str, horse_id: str) -> str:
    return (
        f"馬號: {number}\n"
        f"馬名: {name} (退出)\n"
        f"烙號: {horse_id.rsplit('_', 1)[-1]}\n"
        f"HKJC馬匹ID: {horse_id}\n"
        "負磅: 0\n騎師: -\n檔位: 0\n"
        "練馬師: 沈集成\n排位體重: 0\n配備: TT\n"
    )


def _form_runner(number: int, name: str) -> str:
    return (
        f"馬號: {number}\n馬名: {name}\n檔位: {number}\n"
        "騎師: 希威森\n負磅: 133\n排位體重: 1117\n\n"
        "往績紀錄:\n  (mock form)\n"
    )


def test_standby_runner_cannot_replace_declared_runner(tmp_path: Path) -> None:
    form = tmp_path / "10-04 Race 2 賽績.md"
    card = tmp_path / "10-04 Race 2 排位表.md"
    card.write_text(
        _runner(1, "十分愛", "HK_2024_K111")
        + "\n" + _runner(2, "狼來了", "HK_2024_K353"),
        encoding="utf-8",
    )
    form.write_text(
        _form_runner(1, "十分愛") + "\n" + _form_runner(2, "御登"),
        encoding="utf-8",
    )

    data = inject.parse_hkjc_formguide(str(form))

    assert [horse["name"] for horse in data["horses"]] == ["十分愛", "狼來了"]
    wolf = data["horses"][1]
    assert wolf["brand_no"] == "HK_2024_K353"
    assert wolf["races"] == [], "唔可以將御登往績嫁接當成狼來了"
    assert data["source_reconciliations"] == [{
        "horse_num": 2,
        "racecard_name": "狼來了",
        "formguide_name": "御登",
    }]


def test_withdrawn_racecard_runner_is_not_emitted_to_facts_field(tmp_path: Path) -> None:
    form = tmp_path / "10-04 Race 9 賽績.md"
    card = tmp_path / "10-04 Race 9 排位表.md"
    card.write_text(
        _runner(1, "皇龍飛將", "HK_2022_H111")
        + "\n" + _withdrawn_runner(3, "堅有利", "HK_2021_G462"),
        encoding="utf-8",
    )
    form.write_text(
        _form_runner(1, "皇龍飛將") + "\n" + _form_runner(3, "堅有利"),
        encoding="utf-8",
    )

    data = inject.parse_hkjc_formguide(str(form))

    assert [horse["num"] for horse in data["horses"]] == [1]
    assert all(horse["name"] != "堅有利" for horse in data["horses"])


def test_missing_profile_id_does_not_shift_later_horses() -> None:
    horses = [
        {"num": 1, "brand_no": "HK_2024_K111"},
        {"num": 2, "brand_no": ""},
        {"num": 3, "brand_no": "HK_2024_K333"},
    ]
    assert inject.profile_ids_by_number(horses) == {
        1: "HK_2024_K111",
        3: "HK_2024_K333",
    }


def test_cli_profile_override_preserves_empty_position() -> None:
    # Explicit num:ID pairs are the unambiguous form.
    assert inject.profile_ids_by_number([], "1:HK_2024_K111,3:HK_2024_K333") == {
        1: "HK_2024_K111",
        3: "HK_2024_K333",
    }
    # A positional list maps onto the declared numbers, in order; an empty
    # slot stays empty instead of shifting the next ID forward.
    declared = [{"num": 1, "name": "a"}, {"num": 2, "name": "b"}, {"num": 4, "name": "c"}]
    assert inject.profile_ids_by_number(declared, "HK_2024_K111,,HK_2024_K444") == {
        1: "HK_2024_K111",
        4: "HK_2024_K444",
    }


def test_cli_positional_ids_that_do_not_line_up_are_rejected() -> None:
    import pytest
    declared = [{"num": 1, "name": "a"}, {"num": 2, "name": "b"}, {"num": 4, "name": "c"}]
    # Old convention: slot 3 left blank for scratched horse 3 -> four slots,
    # three runners. Ambiguous, so refuse instead of guessing.
    with pytest.raises(ValueError, match="positional IDs"):
        inject.profile_ids_by_number(declared, "K111,K222,,K444")


def test_cli_ids_conflicting_with_formguide_brand_are_rejected() -> None:
    import pytest
    declared = [{"num": 1, "name": "a", "brand_no": "K111"}]
    with pytest.raises(ValueError, match="formguide says"):
        inject.profile_ids_by_number(declared, "1:HK_2024_K999")


def test_profile_history_adapter_prevents_false_debut() -> None:
    races = inject.profile_entries_as_races([{
        "date": "01/04/26",
        "venue_track": "沙田全天候",
        "distance": 1200,
        "going": "好",
        "barrier": 4,
        "declared_weight": 1106,
        "weight_carried": 134,
        "jockey": "潘頓",
        "placing": 6,
        "running_positions": [4, 5, 6],
    }])
    assert races[0]["date"] == "01/04/2026"
    assert races[0]["venue"] == "沙田"
    assert races[0]["finish"] == 6
    assert races[0]["positions"] == [4, 5, 6]
    stats = inject.compute_stats(races, "沙田", 1200, "2026-10-04")
    assert stats["recent_6"] == [6]
    assert stats["days_since_last"] == 186


def test_status_classification() -> None:
    assert inject.classify_finish_status(3) == "finished"
    assert inject.classify_finish_status(0, "PU") == "started_no_finish"
    assert inject.classify_finish_status(0, "wv-a") == "withdrawn"
    assert inject.classify_finish_status(0, "") == "unknown"


def test_dnf_ends_a_layoff_but_withdrawal_and_unknown_do_not() -> None:
    base = {'date': '15/04/26', 'placing': 6, 'distance': 1650}
    def days(raw):
        entries = [{'date': '20/05/26', 'placing': 0, 'placing_raw': raw, 'distance': 1650}, base]
        return inject.compute_stats([], '跑馬地', 1650, '2026-10-07', profile_entries=entries)
    pulled_up = days('PU')
    assert pulled_up['days_since_last'] == 140
    assert pulled_up['recent_6'] == [6]
    assert pulled_up['history_exclusions'][0]['reason'] == 'started_no_finish_not_a_finish'
    assert days('WV')['days_since_last'] == 175
    unknown = days('')
    assert unknown['days_since_last'] == 175
    assert unknown['history_exclusions'][0]['reason'] == 'unknown_not_a_finish'


def test_missing_race_date_refuses_instead_of_leaking_later_runs() -> None:
    import pytest
    entries = [{'date': '15/04/26', 'placing': 6, 'distance': 1650}]
    with pytest.raises(ValueError, match="race_date"):
        inject.compute_stats([], '跑馬地', 1650, '', profile_entries=entries)
    with pytest.raises(ValueError, match="race_date"):
        inject.filter_profile_as_of({'entries': entries}, '')


def test_unverified_replacement_is_flagged_not_rendered_as_debut() -> None:
    data = {'source_reconciliations': [{'horse_num': 2}],
            'horses': [{'num': 1, 'name': 'a', 'races': []},
                       {'num': 2, 'name': 'b', 'races': []}]}
    assert inject.mark_unverified_reconciled_runners(data, {1: {'entries': []}}) == [2]
    assert data['horses'][1]['history_unverified'] is True
    assert 'history_unverified' not in data['horses'][0]
    assert inject.mark_unverified_reconciled_runners(data | {'horses': [{'num': 2}]},
                                                     {2: {'entries': []}}) == []
    horse = {'num': 2, 'name': 'b', 'jockey': 'j', 'weight': 130, 'barrier': 6,
             'races': [], 'history_unverified': True}
    block = inject.generate_horse_block(horse, '跑馬地', 1650, race_date='2026-10-07')
    assert '`HISTORY_UNVERIFIED`' in block
    assert '無往績記錄' not in block


def test_habitual_early_position_is_pre_race_and_needs_two_runs(monkeypatch) -> None:
    monkeypatch.setattr(inject, "_PAST_FIELD_SIZES", {("2026-09-01", 3): 11})
    entries = [
        {"date": "08/10/26", "race_no": 1, "running_positions": [1, 1, 1]},   # race day: excluded
        {"date": "01/09/26", "race_no": 3, "running_positions": [6, 5, 4]},   # field 11 → 0.5
        {"date": "15/08/26", "race_no": 2, "running_positions": [12, 12]},    # fallback 12 → 1.0
        {"date": "01/08/26", "race_no": 2, "running_positions": []},          # unusable
    ]
    assert inject.habitual_early_position(entries, "2026-10-08") == (0.75, 2)
    assert inject.habitual_early_position(entries[:2], "2026-10-08") == (None, 1)
