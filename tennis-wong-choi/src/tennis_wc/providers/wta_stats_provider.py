"""WTA per-match serve statistics from the official WTA site API.

Why this exists (2026-10-14): every WTA serve column in player_match_history
has been empty since 2026-06. The Sackmann WTA file froze on 2026-05-18,
TennisMyLife carries no WTA, and the two live WTA result sources (composite,
TennisExplorer) carry results only -- 6,000+ WTA rows since June, 0 with aces.

`api.wtatennis.com` is the JSON API behind wtatennis.com's public match
centre, the same host the rankings provider already reads
(`official_ranking_provider.WTA_RANKED_PLAYERS_API_URL`). No login, no
token, no CAPTCHA: the only headers are the site's own `account: wta` and
Origin/Referer. Measured 2026-10-14:

  * /tennis/tournaments/?from&to   lists WTA tour, WTA 125, Grand Slam AND
    ITF events (pageSize capped at 100);
  * /tennis/tournaments/{id}/{year}/matches   carries main draw AND
    qualifying for WTA/125/Slam events, and is EMPTY for ITF events -- so
    ITF women stay uncovered (no stats anywhere we can reach legitimately);
  * /tennis/tournaments/{id}/{year}/matches/{MatchID}/stats   per-set rows
    plus a `setnum = 0` match total: aces, DFs, serve points played/won,
    1st serves in/won, break points, service games. 16/16 sampled finished
    singles matches at a WTA 125 and at Roland Garros had it.

Polite by construction: callers pace requests (see ingest_wta_stats).
"""
from __future__ import annotations

from typing import Callable

from .http import get_json

BASE_URL = "https://api.wtatennis.com/tennis"
HEADERS = {
    "account": "wta",
    "Origin": "https://www.wtatennis.com",
    "Referer": "https://www.wtatennis.com/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    "Accept": "application/json",
}
PAGE_SIZE = 100          # the API silently caps larger requests at 100
MAX_PAGES = 20           # runaway guard; a 4.5-month window is 3 pages


class WtaStatsProvider:
    provider_name = "wta_official_stats"

    def __init__(self, getter: Callable[..., dict | list] | None = None):
        self._get = getter or (lambda url, params=None: get_json(url, HEADERS, params, timeout=30))

    def list_tournaments(self, start_date: str, end_date: str) -> list[dict]:
        out: list[dict] = []
        for page in range(MAX_PAGES):
            body = self._get(
                f"{BASE_URL}/tournaments/",
                {"page": page, "pageSize": PAGE_SIZE, "from": start_date, "to": end_date},
            )
            content = (body or {}).get("content") or [] if isinstance(body, dict) else []
            out.extend(content)
            if len(content) < PAGE_SIZE:
                break
        return out

    def fetch_matches(self, tournament_id: str | int, year: int) -> list[dict]:
        body = self._get(f"{BASE_URL}/tournaments/{tournament_id}/{year}/matches")
        if isinstance(body, dict):
            return list(body.get("matches") or [])
        return []

    def fetch_match_stats(self, tournament_id: str | int, year: int, match_id: str) -> dict | None:
        """The `setnum = 0` match-total row, or None when the API has none."""
        body = self._get(f"{BASE_URL}/tournaments/{tournament_id}/{year}/matches/{match_id}/stats")
        if not isinstance(body, list):
            return None
        for row in body:
            if isinstance(row, dict) and str(row.get("setnum")) == "0":
                return row
        return None
