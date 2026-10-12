from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

AU_RACING = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AU_RACING))

from sb_people_stats import (  # noqa: E402
    append_snapshot,
    parse_person,
    parse_person_tables,
    snapshot_path,
)


def _table(section, window, label, starts, wins, seconds, thirds):
    return f"""
    <table><thead><tr><th class="title">{section}<br>
      <span class="subtitle">{window}</span></th></tr></thead>
      <tbody><tr><td class="title">{label}</td>
      <td class="starts">{starts}</td><td class="wins">{wins}</td>
      <td class="seconds">{seconds}</td><td class="thirds">{thirds}</td>
      <td class="win-rate">10%</td><td class="place-rate">30%</td>
      <td class="avg-win-odds">$5.50</td><td class="roi">-45%</td>
      </tr></tbody></table>
    """


class PeopleContextParserTest(unittest.TestCase):
    HTML = (
        _table("Overall Stats", "", "Career", 100, 10, 11, 9)
        + _table("Overall Stats", "", "12 Months", 20, 3, 2, 1)
        + _table("Track Conditions", "Career", "Good", 80, 8, 7, 6)
        + _table("Track Conditions", "Last 12 Months", "Good", 15, 3, 2, 1)
        + _table("Distance", "Last 12 Months", "1201-1400m", 12, 2, 1, 1)
        + _table("Field Size", "Last 12 Months", "13+", 9, 1, 2, 0)
    )

    def test_duplicate_labels_stay_separated_by_window(self):
        tables = parse_person_tables(self.HTML)
        self.assertEqual(tables["Track Conditions"]["Career"]["Good"]["starts"], 80)
        self.assertEqual(
            tables["Track Conditions"]["Last 12 Months"]["Good"]["starts"], 15
        )
        self.assertEqual(tables["Distance"]["Last 12 Months"]["1201-1400m"]["starts"], 12)
        self.assertEqual(tables["Field Size"]["Last 12 Months"]["13+"]["starts"], 9)

    def test_legacy_stats_contract_still_uses_overall_and_career(self):
        stats = parse_person(self.HTML)
        self.assertEqual(stats["Career"]["starts"], 100)
        self.assertEqual(stats["12 Months"]["1st"], 3)
        self.assertEqual(stats["Good"]["starts"], 80)

    def test_snapshots_append_instead_of_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "people.json"
            for timestamp in ("2026-08-09T10:00:00+00:00", "2026-08-10T10:00:00+00:00"):
                append_snapshot(
                    cache,
                    key="jockey|987",
                    name="Test Rider",
                    kind="jockey",
                    person_id="987",
                    fetched_at=timestamp,
                    stats={"12 Months": {"starts": 20}},
                    contextual_stats={"Distance": {}},
                )
            records = [
                json.loads(line)
                for line in snapshot_path(cache).read_text(encoding="utf-8").splitlines()
            ]
        self.assertEqual([row["captured_at"] for row in records], [
            "2026-08-09T10:00:00+00:00",
            "2026-08-10T10:00:00+00:00",
        ])


class PeopleNamePreservationTest(unittest.TestCase):
    """個人頁冇名；以前每次 TTL 重抓都用 `""` 覆寫，2,554 人有 2,191 個名被洗走。"""

    def test_refresh_keeps_known_name_when_caller_has_none(self):
        import sb_people_stats as sps

        class FakeFetcher:
            def _cache_path(self, url):
                return Path(__file__)  # 存在即可

            def get(self, url):
                return PeopleContextParserTest.HTML

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "people.json"
            path.write_text(json.dumps({"jockey|42": {
                "name": "Nash Rawiller", "id": "42", "kind": "jockey", "stats": {},
                "fetched_at": "2000-01-01T00:00:00+00:00"}}), encoding="utf-8")
            sps.refresh([("Jockey", "42", "")], fetcher=FakeFetcher(), path=path,
                        verbose=False, cache_only=True)
            cache = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(cache["jockey|42"]["name"], "Nash Rawiller")

    def test_race_page_link_title_supplies_the_name(self):
        from claw_sportsbet_form import parse_race
        html = ('<a class="detail-links cjockey" rel="facebox" href="/Jockey/1273/" '
                'title="Nash Rawiller  - Career Statistics">Nash Rawiller</a>')
        meta = parse_race(html)["meta"]
        self.assertEqual(meta["people_names"][("Jockey", "1273")], "Nash Rawiller")


if __name__ == "__main__":
    unittest.main()
