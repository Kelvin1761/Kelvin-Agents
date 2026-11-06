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
import betfair_client as bf  # noqa: E402

NOW = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)          # 悉尼 15:00
START = "2026-11-07T05:00:00.000Z"


def fake_rpc(method, params):
    if method == "listMarketCatalogue":
        return [{"marketId": "1.1", "marketName": "R3 1200m Mdn", "marketStartTime": START,
                 "event": {"name": "Randwick (AUS) 7th Nov", "venue": "Randwick"},
                 "runners": [{"selectionId": 11, "runnerName": "1. A"}, {"selectionId": 12, "runnerName": "2. B"}]},
                {"marketId": "1.2", "marketName": "R4 2138m Pace M", "marketStartTime": START, "event": {}, "runners": []}]
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

    def tearDown(self) -> None:
        lg.LOG_ROOT = self._root
        self.tmp.cleanup()

    def test_snapshot_skips_harness_and_writes_best_prices(self) -> None:
        self.assertEqual(lg.cmd_snapshot(NOW, fake_rpc), 1)
        folder = lg.LOG_ROOT / "2026-11-07"
        cat = lg.read(folder / "catalogue.jsonl")
        self.assertEqual([c["market"] for c in cat], ["1.1"])
        snap = lg.read(folder / "snapshots.jsonl")[0]
        self.assertEqual(snap["runners"][0]["back"], 3.45)
        self.assertTrue(snap["delayed"])
        lg.cmd_snapshot(NOW, fake_rpc)
        self.assertEqual(len(lg.read(folder / "catalogue.jsonl")), 1)     # 目錄唔重覆寫

    def test_quiet_hours_do_not_call_api(self) -> None:
        night = datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)       # 悉尼 04:00
        self.assertEqual(lg.cmd_snapshot(night, lambda *a: (_ for _ in ()).throw(AssertionError("called"))), 0)

    def test_settle_and_usable_window(self) -> None:
        lg.cmd_snapshot(NOW, fake_rpc)
        self.assertEqual(lg.cmd_settle("2026-11-07", fake_rpc), 1)
        t0 = datetime(2026, 11, 7, 5, 0, tzinfo=timezone.utc).timestamp() * 1000
        snaps = [{"ts": t0 - m * 60000, "status": "OPEN", "inplay": False} for m in (65, 16, 6)]
        self.assertIsNotNone(lg.usable_race(snaps, START))
        self.assertIsNone(lg.usable_race(snaps[:2], START))                               # 冇 T−5
        self.assertIsNone(lg.usable_race(snaps[:2] + [{"ts": t0 - 6 * 60000, "status": "OPEN", "inplay": True}], START))


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
