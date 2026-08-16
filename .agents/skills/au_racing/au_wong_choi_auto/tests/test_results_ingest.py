#!/usr/bin/env python3
"""Regression tests for the reflector -> canonical results CSV ingester.

Context: the canonical `AU_Historical_Raw_Race_Results.csv` silently stopped at
2026-07-08 when Racenet was removed — `sb_results.py` kept writing per-meeting
`Race_Results_Reflector.md` but nothing folded them back. These lock the properties
that make re-running the fold safe: additive, idempotent, and format-compatible with
the rows already in the file.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(SCRIPTS / "racing_engine"))

import pytest  # noqa: E402

from au_results_ingest import (  # noqa: E402
    FIELDNAMES,
    collect,
    existing_keys,
    parse_reflector,
)

REFLECTOR = """# Rosehill Gardens Race Results — 2026-08-15

## Race 1
1st: #5 Attractiveness SP$1.80
2nd: #1 Cuban Cigar (0.07L) SP$6.50
3rd: #9 Motoscafo (1.06L) SP$15.00
4th: #16 Channelling (3.03L) SP$31.00

## Race 2
1st: #3 Steel Will SP$1.65
2nd: #7 Savvy Diamond (0.34L) SP$13.00
"""

FORMGUIDE = """RACE 1 — 1200m | Class 2 | $50,000
Track: Good 4 | Weather: Clear
====================
[1] Cuban Cigar (4)
"""

SCORING = """race_number,horse_number,horse_name,jockey,trainer,ability_score
1,5,Attractiveness,J Smith,T Jones,72.5
1,1,Cuban Cigar,A Brown,B White,70.1
1,9,Motoscafo,C Green,D Black,66.0
1,16,Channelling,E Grey,F Blue,61.2
"""


@pytest.fixture()
def meeting(tmp_path):
    root = tmp_path / "AU_Racing"
    md = root / "2026-08-15 Rosehill Race 1-10"
    md.mkdir(parents=True)
    (md / "Race_Results_Reflector.md").write_text(REFLECTOR, encoding="utf-8")
    (md / "08-15 Race 1 Formguide.md").write_text(FORMGUIDE, encoding="utf-8")
    (md / "Meeting_Auto_Scoring.csv").write_text(SCORING, encoding="utf-8")
    return root


class TestParseReflector:
    def test_reads_venue_date_and_places(self, meeting):
        venue, date, races = parse_reflector(
            meeting / "2026-08-15 Rosehill Race 1-10" / "Race_Results_Reflector.md")
        assert venue == "Rosehill Gardens"      # full venue, not the dir's short name
        assert date == "2026-08-15"
        assert [r["pos"] for r in races["1"]] == [1, 2, 3, 4]
        assert races["1"][1]["horse"] == "Cuban Cigar"
        assert races["1"][1]["margin"] == "0.07"
        assert races["1"][0]["margin"] == ""     # the winner has none

    def test_horse_name_survives_optional_margin_and_sp(self, meeting):
        _v, _d, races = parse_reflector(
            meeting / "2026-08-15 Rosehill Race 1-10" / "Race_Results_Reflector.md")
        assert races["1"][0]["horse"] == "Attractiveness"
        assert races["1"][0]["sp"] == "1.80"


class TestCollect:
    def test_thin_races_are_skipped_not_half_written(self, meeting):
        rows, stats = collect(meeting, min_finishers=4)
        # race 1 has 4 finishers and is kept; race 2 has 2 and is dropped
        assert {r["Race"] for r in rows} == {"1"}
        assert stats["races_ingested"] == 1
        assert stats["races_too_thin"] == 1

    def test_enriches_from_formguide_and_scoring_csv(self, meeting):
        rows, _ = collect(meeting, min_finishers=4)
        winner = next(r for r in rows if r["Pos"] == 1)
        assert winner["Distance"] == "1200"
        assert winner["Condition"] == "Good 4"
        assert winner["Jockey"] == "J Smith"
        assert winner["Trainer"] == "T Jones"

    def test_margin_and_sp_match_the_existing_csv_conventions(self, meeting):
        """A second convention in the same column breaks string-parsing consumers."""
        rows, _ = collect(meeting, min_finishers=4)
        by_pos = {r["Pos"]: r for r in rows}
        assert by_pos[1]["Margin"] == "—"        # winner, as the legacy rows do
        assert by_pos[2]["Margin"] == "0.07L"    # trailing L
        assert by_pos[2]["SP"] == "$6.50"        # leading $

    def test_emits_exactly_the_canonical_schema(self, meeting):
        rows, _ = collect(meeting, min_finishers=4)
        assert set(rows[0]) == set(FIELDNAMES)


class TestIdempotence:
    def test_rows_already_present_are_not_re_added(self, meeting, tmp_path):
        rows, _ = collect(meeting, min_finishers=4)
        csv_path = tmp_path / "results.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        known, count = existing_keys(csv_path)
        assert count == len(rows)
        from source_alignment import normalize_horse_name
        fresh = [r for r in rows
                 if (r["Date"], str(r["Race"]), normalize_horse_name(r["Horse"])) not in known]
        assert fresh == []

    def test_key_is_date_race_horse_so_two_tracks_can_share_a_race_number(self, tmp_path):
        csv_path = tmp_path / "results.csv"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerow({k: "" for k in FIELDNAMES} |
                            {"Date": "2026-08-15", "Race": "1", "Horse": "Alpha"})
        known, _ = existing_keys(csv_path)
        assert ("2026-08-15", "1", "alpha") in known
        assert ("2026-08-15", "1", "beta") not in known


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
