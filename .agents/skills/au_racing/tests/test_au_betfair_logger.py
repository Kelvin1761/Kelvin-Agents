"""EXP-20261106-02 Betfair 記錄器：唔連網，用假 rpc。鎖住：只讀、harness 剔走、窗口揀快照、密碼唔外洩。"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "au_betfair"
sys.path.insert(0, str(HERE))

import au_betfair_logger as lg  # noqa: E402
import au_ladbrokes as lb  # noqa: E402
import betfair_client as bf  # noqa: E402

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)          # 悉尼 15:00
START = "2026-11-07T05:00:00.000Z"


def fake_rpc(method, params):
    if method == "listMarketCatalogue":
        return [{"marketId": "1.1", "marketName": "R3 1200m Mdn", "marketStartTime": START,
                 "description": {"marketType": "WIN", "marketBaseRate": 10.0},
                 "event": {"id": "E1", "name": "Randwick (AUS) 7th Nov", "venue": "Randwick"},
                 "runners": [{"selectionId": 11, "runnerName": "1. A"}, {"selectionId": 12, "runnerName": "2. B"}]},
                {"marketId": "1.3", "marketName": "To Be Placed", "marketStartTime": START,
                 "description": {"marketType": "PLACE"}, "event": {"id": "E1", "venue": "Randwick"}, "runners": []},
                {"marketId": "1.2", "marketName": "R4 2138m Pace M", "marketStartTime": START,
                 "description": {"marketType": "WIN"}, "event": {"id": "E2"}, "runners": []},
                {"marketId": "1.4", "marketName": "To Be Placed", "marketStartTime": START,
                 "description": {"marketType": "PLACE"}, "event": {"id": "E2"}, "runners": []}]
    if method == "listMarketBook":
        if params["priceProjection"]["priceData"] == ["SP_TRADED"]:
            return [{"marketId": "1.1", "status": "CLOSED", "runners": [
                {"selectionId": 11, "status": "WINNER", "sp": {"actualSP": 3.4}},
                {"selectionId": 12, "status": "LOSER", "sp": {"actualSP": 1.6}}]}]
        return [{"marketId": m, "status": "OPEN", "inplay": False, "isMarketDataDelayed": True, "runners": [
            {"selectionId": 11, "status": "ACTIVE", "lastPriceTraded": 3.5,
             "ex": {"availableToBack": [{"price": 3.45, "size": 120}], "availableToLay": [{"price": 3.6, "size": 80}]}}]}
            for m in params["marketIds"]]
    raise AssertionError(method)


class LoggerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._root = lg.LOG_ROOT
        lg.LOG_ROOT = Path(self.tmp.name)
        self._lbget = lg.LADBROKES_GET
        lg.LADBROKES_GET = lambda params: {"next_to_go_ids": [], "race_summaries": {}}      # 測試唔准連網

    def tearDown(self) -> None:
        lg.LOG_ROOT = self._root
        lg.LADBROKES_GET = self._lbget
        self.tmp.cleanup()

    def test_snapshot_skips_harness_and_writes_best_prices(self) -> None:
        self.assertEqual(lg.cmd_snapshot(NOW, fake_rpc), 2)
        folder = lg.LOG_ROOT / "2026-11-07"
        cat = lg.read(folder / "catalogue.jsonl")
        # 純種馬 WIN + 佢嘅 PLACE；harness 嘅 WIN 同 PLACE（名冇 Pace 字眼）都剔走
        self.assertEqual([(c["market"], c["type"]) for c in cat], [("1.1", "WIN"), ("1.3", "PLACE")])
        self.assertEqual(cat[0]["mbr"], 10.0)                              # 佣金率記低
        snap = lg.read(folder / "snapshots.jsonl")[0]
        self.assertEqual(snap["runners"][0]["back"], 3.45)
        self.assertTrue(snap["delayed"])
        lg.cmd_snapshot(NOW, fake_rpc)
        self.assertEqual(len(lg.read(folder / "catalogue.jsonl")), 2)     # 目錄唔重覆寫

    def test_quiet_hours_do_not_call_api(self) -> None:
        night = datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)       # 悉尼 04:00
        self.assertEqual(lg.cmd_snapshot(night, lambda *a: (_ for _ in ()).throw(AssertionError("called"))), 0)

    def test_settle_and_usable_window(self) -> None:
        lg.cmd_snapshot(NOW, fake_rpc)
        self.assertEqual(lg.cmd_settle("2026-11-07", fake_rpc), 1)
        self.assertEqual(lg.market_type({}), "WIN")                                       # 舊目錄冇 type
        t0 = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc).timestamp() * 1000
        snaps = [{"ts": t0 - m * 60000, "status": "OPEN", "inplay": False} for m in (65, 16, 6)]
        self.assertIsNotNone(lg.usable_race(snaps, START))
        self.assertIsNone(lg.usable_race(snaps[:2], START))                               # 冇 T−5
        self.assertIsNone(lg.usable_race(snaps[:2] + [{"ts": t0 - 6 * 60000, "status": "OPEN", "inplay": True}], START))


class SettleWeightTests(unittest.TestCase):
    """Betfair 每次 listMarketBook 權重上限 200：SP_TRADED = 7。用 40 個市場一批 → TOO_MUCH_DATA。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._root = lg.LOG_ROOT
        lg.LOG_ROOT = Path(self.tmp.name)
        self._lbget = lg.LADBROKES_GET
        lg.LADBROKES_GET = lambda params: {"next_to_go_ids": [], "race_summaries": {}}      # 測試唔准連網

    def tearDown(self) -> None:
        lg.LOG_ROOT = self._root
        lg.LADBROKES_GET = self._lbget
        self.tmp.cleanup()

    def test_settle_batches_stay_under_weight_limit(self) -> None:
        folder = lg.LOG_ROOT / "2026-11-14"
        folder.mkdir()
        lg.append(folder / "catalogue.jsonl", [{"market": f"1.{i}", "type": "WIN"} for i in range(102)])
        sizes = []

        def rpc(method, params):
            if params["priceProjection"]["priceData"] == ["SP_TRADED"] and len(params["marketIds"]) * 7 > 200:
                raise bf.BetfairError("listMarketBook: TOO_MUCH_DATA")
            sizes.append(len(params["marketIds"]))
            return [{"marketId": m, "status": "CLOSED", "runners": []} for m in params["marketIds"]]

        self.assertEqual(lg.cmd_settle("2026-11-14", rpc), 102)
        self.assertLessEqual(max(sizes) * 7, 200)
        self.assertEqual(lg.cmd_settle("2026-11-14", rpc), 0)                 # 已結算唔再問


START_S = int(datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc).timestamp())


def lb_get(params):
    if params.startswith("method=nextraces"):
        summ = lambda rid, cat, country, start: {"race_id": rid, "category_id": cat, "venue_country": country,  # noqa: E731
                                                 "meeting_name": "Randwick", "venue_state": "NSW", "race_number": 3,
                                                 "advertised_start": {"seconds": start}}
        return {"next_to_go_ids": ["R1", "R2", "R3", "R4"], "race_summaries": {
            "R1": summ("R1", lb.THOROUGHBRED, "AUS", START_S),            # 60 分鐘後
            "R2": summ("R2", "greyhound", "AUS", START_S),
            "R3": summ("R3", lb.THOROUGHBRED, "MYS", START_S),
            "R4": summ("R4", lb.THOROUGHBRED, "AUS", START_S + 3 * 3600)}}  # 太遠
    if params == "method=racecard&id=R1":
        return {"markets": {"m": {"name": "Final Field", "entrant_ids": ["E1", "E2"], "num_winners": 1}},
                "entrants": {"E1": {"name": "A", "number": 1, "barrier": 4}, "E2": {"name": "B", "number": 2, "barrier": 1}},
                "prices": {f"E1:{lb.FIXED_WIN}:": {"odds": {"numerator": 27, "denominator": 10}},
                           f"E1:{lb.FIXED_PLACE}:": {"odds": {"numerator": 9, "denominator": 20}},
                           "E1:other-product:": {"odds": {"numerator": 99, "denominator": 1}},
                           f"E2:{lb.FIXED_WIN}:": {"odds": {}}},
                "price_fluctuations": {"E1": [4.0, 3.8, 3.7]}}
    raise AssertionError(params)


class LadbrokesTests(unittest.TestCase):
    def test_decimal(self) -> None:
        self.assertEqual(lb.decimal({"numerator": 27, "denominator": 10}), 3.7)
        self.assertIsNone(lb.decimal({"denominator": 1}))

    def test_only_au_thoroughbred_within_window(self) -> None:
        self.assertEqual([r["race_id"] for r in lb.upcoming(NOW, lb_get)], ["R1"])

    def test_race_row_maps_fixed_win_and_place(self) -> None:
        rows = lb.snapshot(datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc), get=lb_get, sleep=lambda s: None)
        e1, e2 = rows[0]["entrants"]
        self.assertEqual((e1["win"], e1["place"], e1["flucs"][-1]), (3.7, 1.45, 3.7))
        self.assertIsNone(e2["win"])
        self.assertEqual(rows[0]["win_missing"], 1)
        self.assertEqual(lb.mapping_health(rows), {"races": 1, "races_priced": 0})        # 1/2 有價 < 80%

    def test_sparse_until_last_20_minutes(self) -> None:
        far = {"minutes_to_start": 50}
        self.assertFalse(lb.due(far, datetime(2026, 11, 7, 4, 1, tzinfo=timezone.utc)))
        self.assertTrue(lb.due(far, datetime(2026, 11, 7, 4, 5, tzinfo=timezone.utc)))
        self.assertTrue(lb.due({"minutes_to_start": 12}, datetime(2026, 11, 7, 4, 1, tzinfo=timezone.utc)))


class SnapshotIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._root, self._get = lg.LOG_ROOT, lg.LADBROKES_GET
        lg.LOG_ROOT = Path(self.tmp.name)

    def tearDown(self) -> None:
        lg.LOG_ROOT, lg.LADBROKES_GET = self._root, self._get
        self.tmp.cleanup()

    def test_ladbrokes_failure_does_not_break_betfair(self) -> None:
        def broken(params):
            raise lb.LadbrokesError("down")
        lg.LADBROKES_GET = broken
        self.assertEqual(lg.cmd_snapshot(NOW, fake_rpc), 2)

    def test_betfair_failure_still_records_ladbrokes_then_raises(self) -> None:
        lg.LADBROKES_GET = lb_get
        orig, lb.PAUSE_S = lb.PAUSE_S, 0
        def bf_down(method, params):
            raise lg.bf.BetfairError("down")
        try:
            with self.assertRaises(lg.bf.BetfairError):
                lg.cmd_snapshot(NOW, bf_down)
        finally:
            lb.PAUSE_S = orig
        self.assertEqual(len(lg.read(lg.LOG_ROOT / "2026-11-07" / "ladbrokes.jsonl")), 1)


class ExternalDiskTests(unittest.TestCase):
    def test_unmounted_volume_stops_without_creating_local_folder(self) -> None:
        fake = Path("/Volumes/__wongchoi_test_not_mounted__/betfair-market-log")
        with self.assertRaises(lg.DiskOffline):
            lg.ensure_log_root(fake)
        self.assertFalse(Path("/Volumes/__wongchoi_test_not_mounted__").exists())

    def test_default_root_is_external_disk(self) -> None:
        self.assertTrue(str(lg.LOG_ROOT).startswith("/Volumes/Kelvin Hardisk 1/") or "WONGCHOI_BETFAIR_LOG_ROOT" in __import__("os").environ)


class ClientTests(unittest.TestCase):
    def test_write_methods_refused(self) -> None:
        with self.assertRaises(bf.BetfairError):
            bf.rpc("placeOrders", {})

    def test_login_error_never_contains_password(self) -> None:
        import os
        old = dict(os.environ)
        os.environ.update(BETFAIR_APP_KEY="k", BETFAIR_USERNAME="u", BETFAIR_PASSWORD="s3cr3t-pw")
        os.environ.pop("BETFAIR_CERT_FILE", None)
        orig = bf._post
        bf._post = lambda *a, **k: {"status": "FAIL", "error": "INVALID_USERNAME_OR_PASSWORD"}
        try:
            with self.assertRaises(bf.BetfairError) as ctx:
                bf.login()
            self.assertNotIn("s3cr3t-pw", str(ctx.exception))
        finally:
            bf._post = orig
            os.environ.clear(); os.environ.update(old)


if __name__ == "__main__":
    unittest.main()
