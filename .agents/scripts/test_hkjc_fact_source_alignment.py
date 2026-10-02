"""Regression tests for racecard-authoritative HKJC Facts identities."""
from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("inject_hkjc_fact_anchors.py")
SPEC = importlib.util.spec_from_file_location("inject_hkjc_fact_anchors_test", SCRIPT)
inject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inject)


def _runner(number: int, name: str, horse_id: str) -> str:
    return (
        f"馬號: {number}\n"
        f"馬名: {name}\n"
        f"烙號: {horse_id.rsplit('_', 1)[-1]}\n"
        f"HKJC馬匹ID: {horse_id}\n"
        f"負磅: 133\n騎師: 希威森\n檔位: {number}\n"
        f"練馬師: 沈集成\n排位體重: 1117\n配備: TT\n"
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
    assert inject.profile_ids_by_number([], "HK_2024_K111,,HK_2024_K333") == {
        1: "HK_2024_K111",
        3: "HK_2024_K333",
    }


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
