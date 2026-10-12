from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

AU_RACING = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AU_RACING))
import sb_people_stats as people_stats  # noqa: E402

HTML = '''<table><thead><tr><th class="title">Overall Stats</th></tr></thead>
<tbody><tr><td class="title">12 Months</td><td class="starts">20</td>
<td class="wins">3</td><td class="seconds">2</td><td class="thirds">1</td>
<td class="win-rate">15%</td><td class="place-rate">30%</td></tr></tbody></table>'''


class CachedFetcher:
    def __init__(self, html_path, fail_on=None):
        self.html_path = html_path
        self.fail_on = fail_on
        self.calls = []

    def _cache_path(self, url):
        return self.html_path

    def get(self, url):
        self.calls.append(url)
        if self.fail_on and self.fail_on in url:
            raise OSError("fixture interrupted fetch")
        return self.html_path.read_text()


def test_refresh_keeps_legacy_and_context_independent_and_persists_both(tmp_path):
    html = tmp_path / "person.html"
    html.write_text(HTML)
    cache_path = tmp_path / "people.json"
    with patch.object(people_stats, "parse_person_tables", wraps=people_stats.parse_person_tables) as parser:
        cache = people_stats.refresh(
            [("Jockey", "1", "Fixture Rider")], fetcher=CachedFetcher(html),
            ttl_days=0, path=cache_path, verbose=False, cache_only=True,
        )
    entry = cache["jockey|1"]
    stored = json.loads(cache_path.read_text())
    snapshot = json.loads(people_stats.snapshot_path(cache_path).read_text())
    assert entry["ly"] == "20:3-2-1"
    assert stored["jockey|1"]["stats"] == snapshot["stats"] == entry["stats"]
    assert stored["jockey|1"]["contextual_stats"] == snapshot["contextual_stats"]
    assert parser.call_count == 1
    entry["stats"]["12 Months"]["starts"] = 99
    assert entry["contextual_stats"]["Overall Stats"]["default"]["12 Months"]["starts"] == 20
    assert json.loads(cache_path.read_text()) == stored


def test_second_fetch_failure_retains_first_person_checkpoint(tmp_path):
    html = tmp_path / "person.html"
    html.write_text(HTML)
    cache_path = tmp_path / "people.json"
    fetcher = CachedFetcher(html, fail_on="/2/")
    with pytest.raises(OSError, match="interrupted fetch"):
        people_stats.refresh(
            [("Jockey", "1", "First"), ("Trainer", "2", "Second")],
            fetcher=fetcher, ttl_days=0, path=cache_path, verbose=False,
            cache_only=True,
        )
    assert list(json.loads(cache_path.read_text())) == ["jockey|1"]
    snapshots = people_stats.snapshot_path(cache_path).read_text().splitlines()
    assert len(snapshots) == 1
    assert json.loads(snapshots[0])["name"] == "First"


def test_duplicate_limit_empty_page_and_cache_miss_preserve_skip_behavior(tmp_path):
    html = tmp_path / "person.html"
    html.write_text(HTML)
    path = tmp_path / "people.json"
    fetcher = CachedFetcher(html)
    cache = people_stats.refresh(
        [("Jockey", "1", "First"), ("Jockey", "1", "Duplicate"),
         ("Trainer", "2", "Second")],
        fetcher=fetcher, ttl_days=0, max_people=1, path=path,
        verbose=False, cache_only=True,
    )
    assert list(cache) == ["jockey|1"]
    assert cache["jockey|1"]["name"] == "First"
    assert len(fetcher.calls) == 1
    original = path.read_bytes()
    html.write_text("<html>no stats</html>")
    assert people_stats.refresh(
        [("Trainer", "2", "Second")], fetcher=CachedFetcher(html),
        ttl_days=0, path=path, verbose=False, cache_only=True,
    ) == cache
    assert path.read_bytes() == original
    html.unlink()
    missing_fetcher = CachedFetcher(html)
    assert people_stats.refresh(
        [("Trainer", "2", "Second")], fetcher=missing_fetcher,
        ttl_days=0, path=path, verbose=False, cache_only=True,
    ) == cache
    assert not missing_fetcher.calls
    assert path.read_bytes() == original
