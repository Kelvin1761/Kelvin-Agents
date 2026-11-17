"""au_betfair_prices：dashboard 落注格底嘅 Betfair 細灰字來源。唔連網，用假 rpc。

鎖住：按馬名對（Betfair AU runnerName 冇馬號）；場地前綴配對要唯一；harness／非 OPEN／走地／非 ACTIVE 唔收；
同名出現兩場唔貼；env 檔唔覆蓋已有值；任何寫入 method 依然被 client 拒絕。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / "au_betfair"
sys.path.insert(0, str(HERE))

import au_betfair_prices as P  # noqa: E402
import betfair_client as bf  # noqa: E402


def market(mid, venue, runners, name="R1 1200m Mdn"):
    return {"marketId": mid, "marketName": name, "event": {"venue": venue},
            "runners": [{"selectionId": s, "runnerName": n} for s, n in runners]}


def make_rpc(win, place, books):
    calls = []

    def rpc(method, params):
        calls.append((method, params))
        if method == "listMarketCatalogue":
            return win if params["filter"]["marketTypeCodes"] == ["WIN"] else place
        if method == "listMarketBook":
            return [b for b in books if b["marketId"] in params["marketIds"]]
        raise AssertionError(method)
    rpc.calls = calls
    return rpc


def book(mid, runners, status="OPEN", inplay=False):
    return {"marketId": mid, "status": status, "inplay": inplay, "runners": [
        {"selectionId": s, "status": st, "ex": {"availableToBack": [{"price": p}] if p else []}}
        for s, p, st in runners]}


class VenuePricesTests(unittest.TestCase):
    def test_matches_by_name_with_venue_prefix(self):
        rpc = make_rpc(
            [market("1.1", "Sandown", [(11, "Don't Back Down"), (12, "Iron Rebel")]),
             market("1.9", "Sandown", [(91, "Trotter")], name="R2 2100m Pace"),
             market("1.5", "Gawler", [(51, "Other")])],
            [market("1.2", "Sandown", [(11, "Don't Back Down"), (12, "Iron Rebel")], name="To Be Placed")],
            [book("1.1", [(11, 4.2, "ACTIVE"), (12, 9.0, "REMOVED")]),
             book("1.2", [(11, 1.8, "ACTIVE"), (12, 2.9, "ACTIVE")]),
             book("1.9", [(91, 3.0, "ACTIVE")]), book("1.5", [(51, 2.0, "ACTIVE")])])
        out = P.venue_prices(date(2026, 11, 18), "Sandown Lakeside", rpc)
        self.assertEqual(out, {"dontbackdown": {"win": 4.2, "place": 1.8},
                               "ironrebel": {"place": 2.9}})          # 退出咗嘅贏盤唔收
        asked = {m for meth, p in rpc.calls if meth == "listMarketBook" for m in p["marketIds"]}
        self.assertEqual(asked, {"1.1", "1.2"})                         # harness 同其他場地唔問價

    def test_ambiguous_venue_gives_nothing(self):
        rpc = make_rpc([market("1.1", "Sandown", [(1, "A")]), market("1.2", "Sandown Hillside", [(2, "B")])],
                       [], [])
        self.assertEqual(P.venue_prices(date(2026, 11, 18), "Sandown", rpc), {})

    def test_inplay_closed_and_duplicate_names_dropped(self):
        rpc = make_rpc(
            [market("1.1", "Gawler", [(1, "Twin"), (2, "Solo")]), market("1.3", "Gawler", [(3, "Twin")], name="R2"),
             market("1.4", "Gawler", [(4, "Running")], name="R3")],
            [],
            [book("1.1", [(1, 3.0, "ACTIVE"), (2, 5.0, "ACTIVE")]), book("1.3", [(3, 6.0, "ACTIVE")]),
             book("1.4", [(4, 2.0, "ACTIVE")], inplay=True)])
        self.assertEqual(P.venue_prices(date(2026, 11, 18), "Gawler", rpc), {"solo": {"win": 5.0}})

    def test_day_window_is_sydney_midnight(self):
        self.assertEqual(P._day_window(date(2026, 11, 18)),
                         ("2026-11-17T13:00:00Z", "2026-11-18T13:00:00Z"))   # AEDT +11


class EnvTests(unittest.TestCase):
    def test_env_file_loaded_without_overriding(self):
        keep = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("BETFAIR_")}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                f = Path(tmp) / "bf.env"
                f.write_text("# c\nexport BETFAIR_APP_KEY='abc'\nBETFAIR_USERNAME=u\nOTHER=x\n")
                self.assertTrue(P.load_env_file(f))
                self.assertEqual(os.environ["BETFAIR_APP_KEY"], "abc")
                self.assertNotIn("OTHER", {k for k in os.environ if k == "OTHER" and os.environ[k] == "x"})
                os.environ["BETFAIR_APP_KEY"] = "already"
                f.write_text("BETFAIR_APP_KEY=new\n")
                self.assertTrue(P.load_env_file(f))
                self.assertEqual(os.environ["BETFAIR_APP_KEY"], "already")
                os.environ.pop("BETFAIR_APP_KEY")
                self.assertFalse(P.load_env_file(Path(tmp) / "missing.env"))
        finally:
            for k in [k for k in os.environ if k.startswith("BETFAIR_")]:
                os.environ.pop(k)
            os.environ.update(keep)

    def test_client_still_read_only(self):
        with self.assertRaises(bf.BetfairError):
            bf.rpc("placeOrders", {})


if __name__ == "__main__":
    unittest.main()
