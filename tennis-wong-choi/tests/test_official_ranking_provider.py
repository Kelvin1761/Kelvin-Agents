from __future__ import annotations

import pytest

from tennis_wc.providers.official_ranking_provider import (
    OfficialRankingFetchError,
    _normalise_wta_name,
    _parse_atp_uts_rankings,
    _parse_wta_api_rankings,
    _parse_wta_rankings_html,
    _parse_wta_numeric_pdf_text,
)


def test_parse_wta_numeric_pdf_text():
    text = """
WTA Singles Rankings
As of: 15 June 2026
Rank Prior Name Nat Points # Trn Added Off 18th 19th
1 (1) SABALENKA, ARYNA 9090 19 195 195 65
2 (2) RYBAKINA, ELENA KAZ 8143 22 108 108 120 108
31 (42) RADUCANU, EMMA GBR 1458 20 325 1 1
"""

    rows = _parse_wta_numeric_pdf_text(text, "2026-06-21")

    assert len(rows) == 3
    assert rows[0]["player_id"] == "wta:aryna-sabalenka"
    assert rows[0]["player_name"] == "Aryna Sabalenka"
    assert rows[0]["ranking_date"] == "2026-06-15"
    assert rows[0]["rank"] == 1
    assert rows[0]["ranking_points"] == 9090
    assert rows[1]["raw"]["nationality"] == "KAZ"
    assert rows[2]["player_name"] == "Emma Raducanu"


def test_wta_numeric_pdf_rejects_future_ranking_date():
    text = """
WTA Singles Rankings
As of: 15 June 2026
1 (1) SABALENKA, ARYNA 9090 19 195 195 65
"""

    with pytest.raises(OfficialRankingFetchError):
        _parse_wta_numeric_pdf_text(text, "2026-06-01")


def test_normalise_wta_name_reorders_surname_first_names():
    assert _normalise_wta_name("BOUZAS MANEIRO, JESSICA") == "Jessica Bouzas Maneiro"


def test_parse_atp_uts_rankings():
    payload = {
        "rows": [
            {
                "rank": 1,
                "playerId": 50810,
                "name": "Jannik Sinner",
                "country": {"id": "ITA", "name": "Italy"},
                "points": 11830,
            }
        ]
    }

    rows = _parse_atp_uts_rankings(payload, "2026-06-23")

    assert rows == [
        {
            "player_id": "uts:50810",
            "name": "Jannik Sinner",
            "player_name": "Jannik Sinner",
            "tour": "ATP",
            "ranking_date": "2026-06-23",
            "rank": 1,
            "ranking_points": 11830,
            "raw": {
                "source": "ultimate_tennis_statistics",
                "player_id": 50810,
                "country": "ITA",
            },
        }
    ]


def test_parse_wta_rankings_html():
    html = """
<html><body>
<div>Rankings as of June 15, 2026</div>
<table>
<tr class="player-row" data-player-id="320760" data-player-name="Aryna Sabalenka">
  <td><span class="player-row__rank">1</span></td>
  <td class="player-row__cell player-row__cell--points">9,090</td>
</tr>
</table>
</body></html>
"""

    rows = _parse_wta_rankings_html(html, "2026-06-23")

    assert len(rows) == 1
    assert rows[0]["player_id"] == "wta:320760"
    assert rows[0]["player_name"] == "Aryna Sabalenka"
    assert rows[0]["ranking_date"] == "2026-06-15"
    assert rows[0]["rank"] == 1
    assert rows[0]["ranking_points"] == 9090
    assert rows[0]["raw"]["source"] == "wta_rankings_html"


def test_parse_wta_api_rankings():
    payload = [
        {
            "player": {
                "id": 320760,
                "firstName": "Aryna",
                "lastName": "Sabalenka",
                "fullName": "Aryna Sabalenka",
                "countryCode": "BLR",
            },
            "ranking": 1,
            "points": 9090,
            "tournamentsPlayed": 18,
            "movement": 0,
            "rankedAt": "2026-06-22T00:00:00Z",
        }
    ]

    rows = _parse_wta_api_rankings(payload, "2026-06-23")

    assert rows == [
        {
            "player_id": "wta:320760",
            "name": "Aryna Sabalenka",
            "player_name": "Aryna Sabalenka",
            "tour": "WTA",
            "ranking_date": "2026-06-22",
            "rank": 1,
            "ranking_points": 9090,
            "raw": {
                "source": "wta_ranked_players_api",
                "player_id": 320760,
                "country": "BLR",
                "tournaments_played": 18,
                "movement": 0,
            },
        }
    ]
