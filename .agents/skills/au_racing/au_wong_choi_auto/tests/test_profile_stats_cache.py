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


class TestFetchPriority:
    """`max_profiles` 令排隊次序 = 優先權。

    一個馬場有 60–95 個不重複騎練，但一次抽取只補得幾十個。以前排序係
    「邊個喺 Race 1 先出現」，所以一個得一隻馬嘅見習騎師可以霸咗 Ciaron Maher
    （逐場都有馬）個位 —— 實測 12 個馬場，缺失名單每一場都有佢。
    """

    def test_busiest_person_goes_first(self):
        wanted = ([("jockey", "a-rookie", "A Rookie")]
                  + [("trainer", "ciaron-maher", "Ciaron Maher")] * 9
                  + [("jockey", "tommy-berry", "Tommy Berry")] * 4)
        assert [t[2] for t in ps.stale_slugs(wanted, {}, ttl_days=21)] == [
            "Ciaron Maher", "Tommy Berry", "A Rookie"]

    def test_name_based_path_prioritises_too(self):
        wanted = [("jockey", "One Ride")] + [("trainer", "Busy Stable")] * 5
        assert ps.stale_keys(wanted, {}, ttl_days=21)[0][2] == "Busy Stable"

    def test_fresh_entries_drop_out_without_disturbing_order(self, cache):
        data, _ = cache
        wanted = ([("jockey", "james-mcdonald", "James Mcdonald")] * 20
                  + [("jockey", "brand-new", "Brand New")] * 2)
        assert [t[2] for t in ps.stale_slugs(wanted, data, ttl_days=21)] == ["Brand New"]


class TestJunkNamesNeverBurnASlot:
    """`Unknown` 真係出現喺 payload 入面。抓佢一定 404，但一樣食掉一個名額。"""

    @pytest.mark.parametrize("junk", ["Unknown", "", "  ", "N/A", "-", "TBA"])
    def test_placeholder_is_skipped(self, junk):
        assert ps.stale_slugs([("jockey", ps.slugify(junk), junk)], {}, ttl_days=21) == []

    def test_junk_does_not_crowd_out_real_people(self):
        wanted = [("jockey", "unknown", "Unknown")] * 30 + [("jockey", "real-one", "Real One")]
        assert [t[2] for t in ps.stale_slugs(wanted, {}, ttl_days=21)] == ["Real One"]


class TestNameAliasKeys:
    """抽取器用 payload 真 slug 存，但引擎手上只有顯示名，查嘅係 slugify(顯示名)。

    兩者唔一定一樣（`Braith Nock A` 存喺 `braith-nock`），咁就會「抓到咗但用唔到」。
    ⚠️ 呢個同 `name_mismatch` 係兩件唔同嘅事，唔好合埋 —— 見下面最後一個測試。
    """

    def test_alias_makes_name_lookup_work(self):
        data = {"jockey|braith-nock": {
            "name": "Braith Nock A", "fetched_at": stamp(1),
            "name_mismatch": False, "stats": {"placePercentage": 30}}}
        assert ps.lookup(data, "jockey", "Braith Nock A") is None, "未修之前應該查唔到"
        data["jockey|braith-nock-a"] = dict(data["jockey|braith-nock"],
                                            alias_of="jockey|braith-nock")
        assert ps.lookup(data, "jockey", "Braith Nock A")["placePercentage"] == 30

    def test_alias_is_not_refetched(self):
        data = {"trainer|p-moody-katherine-coleman": {
            "name": "P Moody & Katherine Coleman", "fetched_at": stamp(1),
            "alias_of": "trainer|peter-moody-katherine-coleman", "stats": {"roi": -3}}}
        assert ps.stale_keys([("trainer", "P Moody & Katherine Coleman")],
                             data, ttl_days=21) == []

    def test_alias_is_a_different_problem_from_name_mismatch(self):
        """`name_mismatch` 問「抓返嚟係咪同一個人」—— 呢兩個係，所以 False 係啱。
        別名問「人名查唔查得返」。實測 150 個記錄有 2 個 name_mismatch=False
        但引擎查唔到，就係因為當初把兩者當成同一件事。"""
        entry = {"name": "Braith Nock A", "fetched_at": stamp(1),
                 "name_mismatch": False, "stats": {"winPercentage": 9}}
        assert entry["name_mismatch"] is False
        assert ps.slugify(entry["name"]) != "braith-nock"
