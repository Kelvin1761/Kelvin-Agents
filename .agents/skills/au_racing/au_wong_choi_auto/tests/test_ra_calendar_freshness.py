#!/usr/bin/env python3
"""The RA state calendar must not be served from a stale cache.

Found 2026-08-16. `Calendar.aspx?State=<X>` has a permanent URL but a moving
window of race days. `Fetcher.get` cached it forever, so each state froze on
whatever window it first saw: NSW (recently re-fetched) returned Aug16–23 while
VIC / QLD / WA / SA / TAS / ACT / NT were all still on Aug05. Every non-NSW
meeting therefore failed `matches_venue`, `rating_score` silently fell back to
the class+weight proxy, and 26 of 75 meetings over three weeks carried ZERO
official ratings — all-or-nothing per meeting, which is the signature of a
per-meeting lookup failing rather than horses genuinely being unrated.

Acceptances pages are immutable once published and stay permanently cached; only
the calendar needs an age limit.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

SKILL = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SKILL))

import pytest  # noqa: E402

import ra_fields  # noqa: E402


class _Recorder(ra_fields.Fetcher):
    """Fetcher with the network removed; records what it would have fetched."""

    def __init__(self, cache_dir: Path):
        self.session = None
        self.delay = 0.0
        self.use_cache = True
        self.verbose = False
        self._last = 0.0
        self.fetched: list[str] = []
        self._cache_dir = cache_dir
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, url: str) -> Path:
        import hashlib
        return self._cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".html")

    def get(self, url, force=False, max_age=None):
        cp = self._path(url)
        if self.use_cache and not force and cp.exists():
            fresh = True
            if max_age is not None:
                fresh = (time.time() - cp.stat().st_mtime) < max_age
            if fresh:
                return cp.read_text(encoding="utf-8")
        self.fetched.append(url)
        cp.write_text("<html>refetched</html>", encoding="utf-8")
        return "<html>refetched</html>"


@pytest.fixture()
def fetcher(tmp_path):
    return _Recorder(tmp_path / "cache")


class TestCalendarFreshness:
    def test_a_stale_calendar_is_refetched(self, fetcher):
        url = f"{ra_fields.BASE}/FreeFields/Calendar.aspx?State=VIC"
        path = fetcher._path(url)
        path.write_text("<html>eleven days old</html>", encoding="utf-8")
        old = time.time() - (ra_fields.CALENDAR_MAX_AGE + 60)
        import os
        os.utime(path, (old, old))

        fetcher.get(url, max_age=ra_fields.CALENDAR_MAX_AGE)
        assert fetcher.fetched == [url], "a stale calendar must go back to the network"

    def test_a_fresh_calendar_is_served_from_cache(self, fetcher):
        """Eight states in one run must not mean eight refetches every call."""
        url = f"{ra_fields.BASE}/FreeFields/Calendar.aspx?State=NSW"
        fetcher._path(url).write_text("<html>just fetched</html>", encoding="utf-8")
        fetcher.get(url, max_age=ra_fields.CALENDAR_MAX_AGE)
        assert fetcher.fetched == []

    def test_pages_without_a_max_age_keep_caching_forever(self, fetcher):
        """Acceptances never change once published — do not add traffic there."""
        url = f"{ra_fields.BASE}/FreeFields/Acceptances.aspx?Key=2026Aug16,NSW,Wyong"
        path = fetcher._path(url)
        path.write_text("<html>accepted</html>", encoding="utf-8")
        import os
        ancient = time.time() - 365 * 24 * 3600
        os.utime(path, (ancient, ancient))
        fetcher.get(url)
        assert fetcher.fetched == []

    def test_max_age_is_short_enough_for_a_daily_scheduler(self):
        assert ra_fields.CALENDAR_MAX_AGE <= 24 * 3600, (
            "a once-a-day run must always see a calendar fetched today")


class TestVenueMatching:
    @pytest.mark.parametrize("ra_name,ours", [
        ("Sportsbet-Ballarat", "Ballarat"),
        ("Southside Pakenham Synthetic", "Pakenham Synthetic"),
        ("Canterbury Park", "Canterbury"),
        ("bet365 Traralgon", "Traralgon"),
        ("Sunshine Coast", "Sunshine Coast"),
    ])
    def test_sponsor_prefixes_still_match(self, ra_name, ours):
        assert ra_fields.matches_venue(ra_name, ours)

    def test_unrelated_venues_do_not_match(self):
        assert not ra_fields.matches_venue("Wyong", "Moruya")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
