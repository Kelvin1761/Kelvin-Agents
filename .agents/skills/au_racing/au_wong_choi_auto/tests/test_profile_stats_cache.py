#!/usr/bin/env python3
"""騎練 profile 統計 TTL cache 嘅回歸測試（`au_racing/au_profile_stats.py`）。

呢個 module 令每次抽取都攞到夠新嘅 winPercentage / placePercentage / ROI，
唔使自己養一個會過時嘅資料庫。測試唔會發任何網絡請求。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest  # noqa: E402

import au_profile_stats as ps  # noqa: E402


def stamp(days_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")


@pytest.fixture()
def cache(tmp_path):
    data = {
        "jockey|james-mcdonald": {"name": "James Mcdonald", "fetched_at": stamp(1),
                                  "stats": {"winPercentage": 21, "placePercentage": 49,
                                            "roi": -6}},
        "jockey|old-timer": {"name": "Old Timer", "fetched_at": stamp(99),
                             "stats": {"winPercentage": 5}},
        "trainer|wrong-person": {"name": "Someone Else", "fetched_at": stamp(1),
                                 "name_mismatch": True, "stats": {"winPercentage": 30}},
    }
    path = tmp_path / "cache.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return data, path


class TestSlugify:
    @pytest.mark.parametrize("name,expected", [
        ("Chris Waller", "chris-waller"),
        ("Ben, Will & Jd Hayes", "ben-will-jd-hayes"),
        ("Annabel & Rob Archibald", "annabel-rob-archibald"),
        ("Gai Waterhouse & Adrian Bott", "gai-waterhouse-adrian-bott"),
        ("O'Brien", "obrien"),
        ("", ""),
        (None, ""),
    ])
    def test_matches_racenet_format(self, name, expected):
        """對得上 Racenet 索引頁見到嘅真實 slug。"""
        assert ps.slugify(name) == expected


class TestFreshness:
    def test_fresh_entry_is_not_refetched(self, cache):
        data, _ = cache
        assert ps.stale_keys([("jockey", "James Mcdonald")], data, ttl_days=21) == []

    def test_expired_entry_is_refetched(self, cache):
        data, _ = cache
        todo = ps.stale_keys([("jockey", "Old Timer")], data, ttl_days=21)
        assert [t[1] for t in todo] == ["old-timer"]

    def test_unknown_person_is_fetched(self, cache):
        data, _ = cache
        todo = ps.stale_keys([("jockey", "Brand New")], data, ttl_days=21)
        assert [t[1] for t in todo] == ["brand-new"]

    def test_duplicates_collapse(self, cache):
        """一個 meeting 同一個騎師出現十次，只應該抓一次。"""
        data, _ = cache
        wanted = [("jockey", "Brand New")] * 10
        assert len(ps.stale_keys(wanted, data, ttl_days=21)) == 1

    def test_missing_timestamp_counts_as_stale(self):
        data = {"jockey|x": {"name": "X", "stats": {"winPercentage": 1}}}
        assert len(ps.stale_keys([("jockey", "X")], data, ttl_days=21)) == 1

    def test_exact_slugs_bypass_name_derivation(self, cache):
        """payload 嘅真 slug 同人名推導唔一定一樣（例 Ciaron Maher →
        `ciaron-maher-david-eustace`），所以要支援直接餵 slug。"""
        data, _ = cache
        todo = ps.stale_slugs([("trainer", "ciaron-maher-david-eustace", "Ciaron Maher")],
                              data, ttl_days=21)
        assert [t[1] for t in todo] == ["ciaron-maher-david-eustace"]


class TestLookup:
    def test_returns_stats(self, cache):
        data, _ = cache
        assert ps.lookup(data, "jockey", "James Mcdonald")["winPercentage"] == 21

    def test_unknown_returns_none(self, cache):
        data, _ = cache
        assert ps.lookup(data, "jockey", "Nobody") is None

    def test_name_mismatch_is_withheld(self, cache):
        """slug 撞錯人嘅記錄寧可當冇數據，都好過餵錯數據落評分。"""
        data, _ = cache
        assert ps.lookup(data, "trainer", "Wrong Person") is None


class TestLoadCache:
    def test_missing_file_is_empty(self, tmp_path):
        assert ps.load_cache(tmp_path / "nope.json") == {}

    def test_corrupt_file_is_empty_not_fatal(self, tmp_path):
        """cache 壞咗唔可以令抽取死；當空處理，下次重抓。"""
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert ps.load_cache(path) == {}

    def test_roundtrip(self, cache):
        data, path = cache
        assert ps.load_cache(path) == data


class TestRefreshGuards:
    def test_nothing_stale_makes_no_network_call(self, cache, monkeypatch):
        """全部新鮮就要即刻返回 —— 唔可以無謂噏 Racenet。"""
        data, path = cache

        def explode(*a, **k):
            raise AssertionError("唔應該開瀏覽器")

        monkeypatch.setattr(ps, "_extract_stats", explode)
        out = ps.refresh([("jockey", "James Mcdonald")], path=path, verbose=False)
        assert out == data
