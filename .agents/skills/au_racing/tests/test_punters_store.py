"""Punters 段速 store：解析、sentinel、分段長度、as-of 守衛、場地配對。"""
import sys
from pathlib import Path

import pytest

PUNTERS = Path(__file__).resolve().parents[1] / "punters"
sys.path.insert(0, str(PUNTERS))

import punters_backfill as backfill  # noqa: E402
import punters_store as store  # noqa: E402


def _form(fid, date, l600=(11.7, 61.54), finish=(12.0, 60.0), l800=(25.0, 57.6)):
    seg = lambda v: None if v is None else {"split": v[0], "speed": v[1]}  # noqa: E731
    return {"id": fid, "finishPosition": 3, "eventStarters": 10, "meetingDate": date + "T00:00:00",
            "eventDistance": 1200, "eventNumber": 4, "trackCondition": "Good",
            "trackConditionRating": 4, "venue": {"name": "Kilcoy"},
            "sectionalTimeSummary": {"earlySpeed": 57.6, "midSpeed": 61.0, "lateSpeed": finish[1] if finish else None,
                                     "averageSpeed": 59.5, "averageTime": 14.2},
            "sectionalTime": {"l800": seg(l800), "l600": seg(l600), "l400": seg((11.9, 60.5)),
                              "l200": seg((11.8, 61.02)), "finish": seg(finish)}}


def _payload(anchor, forms):
    return {"data": {"competitorForms": [{"count": len(forms), "selectionId": anchor, "forms": forms}]}}


@pytest.fixture
def con(tmp_path):
    return store.connect(tmp_path / "p.sqlite")


def test_segments_parse_and_sentinel_is_missing(con):
    store.ingest_forms(con, _payload("s1", [_form("f1", "2026-07-01"),
                                            _form("f2", "2026-06-01", finish=(999.0, 0.72))]),
                       {"s1": "2026-08-10"})
    rows = dict(con.execute("SELECT form_id, finish_split FROM forms"))
    assert rows["f1"] == 12.0
    assert rows["f2"] is None            # 999 = 冇計時，唔可以當 999 秒


def test_as_of_guard_raises_on_form_after_anchor(con):
    store.ingest_forms(con, _payload("s1", [_form("f1", "2026-08-10")]), {"s1": "2026-08-10"})
    with pytest.raises(AssertionError):
        store.check_as_of(con)


def test_as_of_guard_passes_on_prior_forms(con):
    store.ingest_forms(con, _payload("s1", [_form("f1", "2026-08-09")]), {"s1": "2026-08-10"})
    assert store.check_as_of(con) == 0


def test_segment_length_flags_from_start_chunks():
    assert store.is_200m(11.7, 61.54)          # 真 200m 段
    assert not store.is_200m(25.0, 57.6)        # 1200m 賽事嘅起步→800m（≈400m）
    assert not store.is_200m(None, 60.0)


def test_keys_normalise_entities_and_suffixes():
    assert store.horse_key("Jack &amp; Jill (NZ)") == store.horse_key("Jack & Jill")
    assert store.venue_key("Pakenham Synthetic") == "pakenhamsynthetic"


def test_match_meetings_skips_trials_and_foreign():
    payload = {"data": {"meetings": [
        {"slug": "dubbo-20260810", "venue": {"name": "Dubbo"}},
        {"slug": "dubbo-20260810-bt", "venue": {"name": "Dubbo"}},
        {"slug": "canterbury-park-us-20260810", "venue": {"name": "Canterbury Park"}},
    ]}}
    matched, missing = backfill.match_meetings(payload, {"Dubbo", "Canterbury"})
    assert matched["Dubbo"]["slug"] == "dubbo-20260810"
    assert "Canterbury" in missing            # 唔可以錯配去美國 Canterbury Park


def test_v3_fields_and_trials_are_stored(con):
    f = _form("f1", "2026-07-01")
    f.update({"isTrial": True, "margin": 0.4, "videoComment": "Began well", "startingWinPriceDecimal": 2.2,
              "jockey": {"id": "1", "name": "Michael Dee"}, "formLine": {"places": []}})
    store.ingest_forms(con, _payload("s1", [f]), {"s1": "2026-08-10"})
    row = con.execute("SELECT is_trial, margin, video_comment, sp_win, jockey FROM forms").fetchone()
    assert row == (1, 0.4, "Began well", 2.2, "Michael Dee")


def test_rebuild_skips_cache_from_older_query_version(tmp_path, con):
    import json
    cache = tmp_path / "cache"
    cache.mkdir()
    meets = {"_query_version": 2, "data": {"meetings": [{"slug": "kilcoy-20260810", "venue": {"name": "Kilcoy"}, "events": [
        {"id": "e1", "eventNumber": 1, "selections": [{"id": "s1", "competitor": {"name": "A"}}]}]}]}}
    (cache / "meetingsIndexByStartEndTime_x.json").write_text(json.dumps(meets))
    old = _payload("s1", [_form("f_old", "2026-07-01")])            # 冇 _query_version = v1
    (cache / "getSectionalsBySelectionIds_old.json").write_text(json.dumps(old))
    out = store.rebuild_from_cache(con, cache)
    assert out["skipped_old_version"] == 1 and out["forms"] == 0


def test_venue_alias_murray_bridge():
    assert store.venue_key("Murray Bdge") == store.venue_key("Murray Bridge")
