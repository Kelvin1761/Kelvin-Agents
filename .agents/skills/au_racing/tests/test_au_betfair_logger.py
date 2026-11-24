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
        data = params["priceProjection"]["priceData"]
        if "SP_TRADED" in data or "SP_AVAILABLE" in data:
            # 同真 API 一樣：淨係 SP_AVAILABLE 先有 `sp` 欄（11-24 實測；以前個假 rpc 遮住咗呢個 bug）
            sp = (lambda v: {"sp": {"actualSP": v}}) if "SP_AVAILABLE" in data else (lambda v: {})
            return [{"marketId": "1.1", "status": "CLOSED", "runners": [
                {"selectionId": 11, "status": "WINNER", **sp(3.4)},
                {"selectionId": 12, "status": "LOSER", **sp(1.6)},
                {"selectionId": 13, "status": "REMOVED", **sp("NaN")}]}]
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
        row = lg.latest_settle(lg.LOG_ROOT / "2026-11-07")["1.1"]
        self.assertEqual([r["bsp"] for r in row["runners"]], [3.4, 1.6, None])       # 退出馬 "NaN" → None
        asked = []
        lg.cmd_settle("2026-11-07", lambda m, p: asked.extend(p["marketIds"]) or [])
        self.assertNotIn("1.1", asked)                                                # 有 BSP 就唔再問
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

    def tearDown(self) -> None:
        lg.LOG_ROOT = self._root
        self.tmp.cleanup()

    def test_settle_batches_stay_under_weight_limit(self) -> None:
        folder = lg.LOG_ROOT / "2026-11-14"
        folder.mkdir()
        lg.append(folder / "catalogue.jsonl", [{"market": f"1.{i}", "type": "WIN"} for i in range(102)])
        sizes = []

        def rpc(method, params):
            if len(params["marketIds"]) * 7 > 200:
                raise bf.BetfairError("listMarketBook: TOO_MUCH_DATA")
            sizes.append(len(params["marketIds"]))
            return [{"marketId": m, "status": "CLOSED", "runners": []} for m in params["marketIds"]]

        self.assertEqual(lg.cmd_settle("2026-11-14", rpc), 102)
        self.assertLessEqual(max(sizes) * 7, 200)
        self.assertEqual(lg.cmd_settle("2026-11-14", rpc), 0)                 # 已結算唔再問


class BspBackfillTests(unittest.TestCase):
    """11-06 → 11-24 嘅舊結算行 bsp 全 null：要重新結算，而且讀嘅時候攞最後一行。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self._root = lg.LOG_ROOT
        lg.LOG_ROOT = Path(self.tmp.name)
        self.folder = lg.LOG_ROOT / "2026-11-07"
        self.folder.mkdir()
        lg.append(self.folder / "catalogue.jsonl", [{"market": "1.1", "type": "WIN"}])
        lg.append(self.folder / "settle.jsonl", [{"market": "1.1", "status": "CLOSED", "runners": [
            {"id": 11, "status": "WINNER", "bsp": None}, {"id": 12, "status": "LOSER", "bsp": None}]}])

    def tearDown(self) -> None:
        lg.LOG_ROOT = self._root
        self.tmp.cleanup()

    def test_null_bsp_rows_are_resettled(self) -> None:
        self.assertEqual(lg.cmd_settle("2026-11-07", fake_rpc), 1)
        self.assertEqual(len(lg.read(self.folder / "settle.jsonl")), 2)
        self.assertEqual(lg.latest_settle(self.folder)["1.1"]["runners"][0]["bsp"], 3.4)
        self.assertEqual(lg.collect_counts(lg.LOG_ROOT)["settled_markets_with_bsp"], 1)

    def test_alert_when_no_bsp_at_all(self) -> None:
        pushed = []
        fake = type(sys)("au_notify")
        fake.push = lambda msg, **kw: pushed.append((msg, kw))
        sys.modules["au_notify"] = fake
        try:
            self.assertFalse(lg.check_bsp_present("2026-11-07"))
            self.assertEqual(pushed[0][1]["audience"], "primary")
            lg.cmd_settle("2026-11-07", fake_rpc)
            self.assertTrue(lg.check_bsp_present("2026-11-07"))
            self.assertEqual(len(pushed), 1)
        finally:
            sys.modules.pop("au_notify", None)


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
