"""AU Betfair 自動落注：全部用假 rpc，唔連網、唔推 Telegram。

鎖住：四重開關逐個都攔得住、限額攔得住、重跑唔會落多次、dry-run 永遠唔 call placeOrders、
只讀 client 仍然拒絕寫入、credential 唔會出現喺錯誤／帳本／輸出。
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parents[1] / "au_betfair"
sys.path.insert(0, str(HERE))

import betfair_betting as bb  # noqa: E402
import betfair_client as bf  # noqa: E402
import betfair_trading as bt  # noqa: E402
import betting_strategies as bs  # noqa: E402

NOW = datetime(2026, 11, 21, 3, 0, tzinfo=timezone.utc)          # 悉尼 14:00
START = (NOW + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
SECRET_KEY = "LIVEKEY-s3cr3t-9f8e"
SECRET_PW = "pw-s3cr3t-7a6b"


def live_config(**over) -> dict:
    cfg = json.loads((HERE / "betting_config.json").read_text(encoding="utf-8"))
    cfg.update({"enabled": True, "mode": "live", "allowed_strategies": ["test"]})
    for k, v in over.items():
        if k in cfg["limits"]:
            cfg["limits"][k] = v
        else:
            cfg[k] = v
    return cfg


def bet(market="1.10", sel=11, stake=5, price=2.0, **kw) -> dict:
    return {"market_id": market, "selection_id": sel, "side": "BACK", "stake": stake,
            "order_type": "LIMIT_ON_CLOSE", "min_price": price, "strategy": "test", "reason": "unit", **kw}


def _mkt(mid, mtype, name, event="E1", start=START, country="AU", etype="7", bsp=True):
    return {"marketId": mid, "marketName": name, "marketStartTime": start,
            "eventType": {"id": etype}, "description": {"marketType": mtype, "bspMarket": bsp, "marketBaseRate": 8.0},
            "event": {"id": event, "venue": "Randwick", "countryCode": country},
            "runners": [{"selectionId": 11, "runnerName": "1. Alpha"}, {"selectionId": 12, "runnerName": "2. Beta"}]}


class FakeRpc:
    def __init__(self, *, funds=1000.0, cleared_pnl=0.0, current=None, inplay=False, near=4.0,
                 place_raises=False):
        self.calls = []
        self.funds, self.cleared, self.current = funds, cleared_pnl, current or []
        self.inplay, self.near, self.place_raises = inplay, near, place_raises
        self.markets = {
            "1.10": _mkt("1.10", "WIN", "R3 1200m Mdn"),
            "1.11": _mkt("1.11", "PLACE", "To Be Placed"),
            "1.20": _mkt("1.20", "WIN", "R4 2138m Pace M", event="E2"),
            "1.21": _mkt("1.21", "PLACE", "To Be Placed", event="E2"),
            "1.30": _mkt("1.30", "WIN", "R1 1000m", event="E3", country="NZ"),
            "1.40": _mkt("1.40", "WIN", "R5 1400m", event="E4",
                         start=(NOW - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")),
            "1.50": _mkt("1.50", "WIN", "R6 1600m", event="E5"),
        }
        self.bet_n = 0

    def names(self):
        return [c[0] for c in self.calls]

    def __call__(self, method, params):
        self.calls.append((method, json.loads(json.dumps(params))))
        if method == "listMarketCatalogue":
            f = params["filter"]
            if "marketIds" in f:
                return [self.markets[m] for m in f["marketIds"] if m in self.markets]
            if "eventIds" in f:
                return [m for m in self.markets.values() if m["event"]["id"] in f["eventIds"]
                        and m["description"]["marketType"] in f.get("marketTypeCodes", ["WIN"])]
            return list(self.markets.values())
        if method == "listMarketBook":
            return [{"marketId": m, "status": "OPEN", "inplay": self.inplay if m != "1.50" else True,
                     "runners": [{"selectionId": 11, "status": "ACTIVE", "sp": {"nearPrice": self.near}},
                                 {"selectionId": 12, "status": "REMOVED", "sp": {}}]}
                    for m in params["marketIds"]]
        if method == "getAccountFunds":
            return {"availableToBetBalance": self.funds}
        if method == "listCurrentOrders":
            return {"currentOrders": self.current}
        if method == "listClearedOrders":
            if params.get("groupBy") == "MARKET" and "settledDateRange" in params:
                return {"clearedOrders": [{"profit": self.cleared, "commission": 0}]}
            return {"clearedOrders": []}
        if method == "placeOrders":
            if self.place_raises:
                raise bf.BetfairError("placeOrders: network error @ /exchange: TimeoutError")
            self.bet_n += 1
            return {"status": "SUCCESS", "instructionReports": [
                {"status": "SUCCESS", "betId": f"B{self.bet_n}", "placedDate": "2026-11-21T03:00:01Z"}]}
        raise AssertionError(f"unexpected {method}")


class Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = mock.patch.dict(os.environ, {
            "WONGCHOI_CONTROL_STATE_ROOT": str(self.root),
            "WC_BETFAIR_BETTING": "live", "BETFAIR_LIVE_APP_KEY": SECRET_KEY,
            "BETFAIR_APP_KEY": "delayed-key", "BETFAIR_USERNAME": "user", "BETFAIR_PASSWORD": SECRET_PW,
            "WC_NOTIFY_TELEGRAM_TOKEN": "", "WC_NOTIFY_NTFY_TOPIC": ""})
        self.env.start()
        self.msgs: list[str] = []

    def tearDown(self) -> None:
        self.env.stop()
        self.tmp.cleanup()

    def notify(self, text):
        self.msgs.append(text)

    def live(self, bets, rpc=None, config=None, now=NOW):
        rpc = rpc or FakeRpc()
        rep = bb.run(bets, mode="live", config=config or live_config(), market_rpc=rpc, account_rpc=rpc,
                     now=now, notify=self.notify)
        return rep, rpc


class SwitchTests(Base):
    def test_all_on_places_one_bsp_order(self) -> None:
        rep, rpc = self.live([bet()])
        self.assertEqual(len(rep["placed"]), 1, rep)
        place = [p for m, p in rpc.calls if m == "placeOrders"]
        self.assertEqual(len(place), 1)
        req = place[0]
        ins = req["instructions"][0]
        self.assertEqual(ins["orderType"], "LIMIT_ON_CLOSE")
        self.assertEqual(ins["limitOnCloseOrder"], {"liability": 5.0, "price": 2.0})
        self.assertEqual(ins["side"], "BACK")
        self.assertLessEqual(len(req["customerStrategyRef"]), 15)
        self.assertLessEqual(len(ins["customerOrderRef"]), 32)
        self.assertEqual(req["customerRef"], ins["customerOrderRef"])
        self.assertTrue(self.msgs and "落咗 1 注" in self.msgs[0])

    def _assert_refused(self, config=None, env=None) -> None:
        env = env or {}
        with mock.patch.dict(os.environ, {k: v for k, v in env.items() if v is not None}):
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
            rep, rpc = self.live([bet()], config=config)
        self.assertTrue(rep.get("refused"), rep)
        self.assertNotIn("placeOrders", rpc.names())
        self.assertEqual(rpc.calls, [])

    def test_switch1_config_disabled(self) -> None:
        self._assert_refused(config=live_config(enabled=False))

    def test_switch1_config_mode_dry_run(self) -> None:
        self._assert_refused(config=live_config(mode="dry_run"))

    def test_switch2_env_missing_or_wrong(self) -> None:
        self._assert_refused(env={"WC_BETFAIR_BETTING": None})
        self._assert_refused(env={"WC_BETFAIR_BETTING": "1"})

    def test_switch3_live_key_missing_no_fallback_to_delayed(self) -> None:
        self._assert_refused(env={"BETFAIR_LIVE_APP_KEY": None})
        with mock.patch.dict(os.environ, {"BETFAIR_LIVE_APP_KEY": ""}):
            with self.assertRaises(bf.BetfairError):
                bt.live_app_key()

    def test_switch4_kill_file(self) -> None:
        bb.kill_file().parent.mkdir(parents=True, exist_ok=True)
        bb.kill_file().touch()
        self._assert_refused()

    def test_kill_file_mid_run_stops_remaining(self) -> None:
        rpc = FakeRpc()
        orig = rpc.__call__

        def touching(method, params):
            out = orig(method, params)
            if method == "placeOrders":
                bb.kill_file().touch()
            return out
        rep = bb.run([bet(), bet(market="1.11")], mode="live", config=live_config(), market_rpc=touching,
                     account_rpc=touching, now=NOW, notify=self.notify)
        self.assertEqual(len(rep["placed"]), 1)
        self.assertEqual(rpc.names().count("placeOrders"), 1)

    def test_bad_config_fails_closed(self) -> None:
        cfg = live_config()
        del cfg["limits"]["daily_stop_loss"]
        self.assertFalse(bb.switches(cfg)["all_on"])
        self._assert_refused(config=cfg)

    def test_committed_config_is_off(self) -> None:
        cfg = bb.load_config()
        self.assertIs(cfg["enabled"], False)
        self.assertEqual(cfg["mode"], "dry_run")
        self.assertEqual(cfg["strategy"], "none")
        self.assertEqual(cfg["allowed_strategies"], [])
        self.assertFalse(bb.switches(cfg)["all_on"])          # env 全開都唔得
        self.assertEqual(bs.plan("none", day="2026-11-21", config=cfg)[0], [])

    def test_trading_client_rechecks_switches_before_place(self) -> None:
        with mock.patch.object(bb, "CONFIG_PATH", HERE / "betting_config.json"), \
                mock.patch.object(bf, "_post", side_effect=AssertionError("network")):
            with self.assertRaises(bf.BetfairError) as ctx:
                bt.trading_rpc("placeOrders", {})
        self.assertIn("開關未全開", str(ctx.exception))

    def test_trading_client_never_allows_cancel_replace_update(self) -> None:
        for m in ("cancelOrders", "replaceOrders", "updateOrders", "transferFunds"):
            with mock.patch.object(bf, "_post", side_effect=AssertionError("network")):
                with self.assertRaises(bf.BetfairError):
                    bt.trading_rpc(m, {})

    def test_read_only_client_still_refuses_writes(self) -> None:
        for m in ("placeOrders", "cancelOrders", "replaceOrders", "updateOrders", "listCurrentOrders"):
            with self.assertRaises(bf.BetfairError):
                bf.rpc(m, {})
        self.assertEqual(bf.READ_ONLY_METHODS,
                         frozenset({"listMarketCatalogue", "listMarketBook", "listEventTypes", "listEvents"}))

    def test_cli_place_refuses_with_committed_config(self) -> None:
        f = self.root / "bets.json"
        f.write_text(json.dumps([bet()]))
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = bb.main(["place", "--bets", str(f)])
        self.assertEqual(code, 2)
        self.assertIn("betting_config.json", err.getvalue())


class DryRunTests(Base):
    def test_dry_run_never_calls_place_even_with_all_switches_on(self) -> None:
        rpc = FakeRpc()
        rep = bb.run([bet(), bet(market="1.11")], mode="dry_run", config=live_config(), market_rpc=rpc,
                     account_rpc=rpc, now=NOW, notify=self.notify)
        self.assertEqual(len(rep["would_send"]), 2)
        self.assertNotIn("placeOrders", rpc.names())
        self.assertEqual(self.msgs, [])                      # 冇 --notify 就唔推
        events = [r["event"] for r in bb.ledger_rows()]
        self.assertEqual(events.count("would_send"), 2)
        self.assertEqual(rep["would_send"][0]["request"]["instructions"][0]["limitOnCloseOrder"]["price"], 2.0)

    def test_dry_run_offline_and_one_summary_per_day(self) -> None:
        for _ in range(3):
            bb.run([bet()], mode="dry_run", config=bb.load_config(), now=NOW, notify=self.notify,
                   notify_dry_run=True)
        self.assertEqual(len(self.msgs), 1)
        self.assertIn("dry-run", self.msgs[0])

    def test_dry_run_settle_estimates_with_bsp_and_commission(self) -> None:
        rpc = FakeRpc()
        bb.run([bet(), bet(market="1.11", price=5.0)], mode="dry_run", config=live_config(), market_rpc=rpc,
               account_rpc=None, now=NOW, notify=self.notify)

        def closed(method, params):
            return [{"marketId": m, "status": "CLOSED", "runners": [
                {"selectionId": 11, "status": "WINNER", "sp": {"actualSP": 3.0}}]} for m in params["marketIds"]]
        s = bb.settle_dry_run("2026-11-21", closed, live_config())
        self.assertEqual(s["settled"], 2)
        self.assertEqual(s["unmatched"], 1)                  # PLACE 要 ≥5.0，BSP 3.0 → 冇成交
        self.assertAlmostEqual(s["profit"], 10.0)
        self.assertAlmostEqual(s["commission"], 0.8)          # marketBaseRate 8%
        self.assertEqual(bb.settle_dry_run("2026-11-21", closed, live_config())["settled"], 0)


class LimitTests(Base):
    def _why(self, bets, rpc=None, config=None):
        rep, rpc = self.live(bets, rpc=rpc, config=config)
        return rep, [b["why"] for b in rep["blocked"]], rpc

    def test_max_stake_per_bet(self) -> None:
        rep, why, rpc = self._why([bet(stake=6)])
        self.assertIn("每注上限", why[0])
        self.assertNotIn("placeOrders", rpc.names())

    def test_min_stake(self) -> None:
        self.assertIn("最少", self._why([bet(stake=1)])[1][0])

    def test_max_bets_per_day(self) -> None:
        rep, why, _ = self._why([bet(), bet(market="1.11")], config=live_config(max_bets_per_day=1))
        self.assertEqual(len(rep["placed"]), 1)
        self.assertIn("注數上限", why[0])

    def test_daily_total_includes_earlier_runs(self) -> None:
        cfg = live_config(max_total_stake_per_day=8, max_exposure_per_race=100)
        self.live([bet()], config=cfg)
        rep, why, _ = self._why([bet(market="1.11")], config=cfg)
        self.assertIn("總注碼上限", why[0])

    def test_race_exposure_win_and_place_share_a_race(self) -> None:
        rep, why, _ = self._why([bet(), bet(market="1.11")], config=live_config(max_exposure_per_race=9))
        self.assertEqual(len(rep["placed"]), 1)
        self.assertIn("每場上限", why[0])

    def test_daily_stop_loss_from_cleared_orders(self) -> None:
        rep, why, rpc = self._why([bet()], rpc=FakeRpc(cleared_pnl=-30.0))
        self.assertIn("止蝕", why[0])
        self.assertNotIn("placeOrders", rpc.names())
        self.assertTrue(any("限額" in m for m in self.msgs))

    def test_funds_floor(self) -> None:
        self.assertIn("底線", self._why([bet()], rpc=FakeRpc(funds=50))[1][0])

    def test_bsp_limits(self) -> None:
        self.assertIn("min_price", self._why([bet(price=1.2)])[1][0])
        self.assertIn("min_price", self._why([bet(price=40)])[1][0])
        self.assertIn("預計 BSP", self._why([bet()], rpc=FakeRpc(near=55.0))[1][0])

    def test_market_on_close_refused_by_default(self) -> None:
        self.assertIn("MARKET_ON_CLOSE", self._why([bet(order_type="MARKET_ON_CLOSE", min_price=None)])[1][0])

    def test_market_filters(self) -> None:
        _, why, _ = self._why([bet(market="1.20"), bet(market="1.21"), bet(market="1.30"), bet(market="1.40"),
                               bet(market="1.50"), bet(market="1.99"), bet(sel=12)],
                              config=live_config(max_exposure_per_race=100, max_total_stake_per_day=100))
        self.assertIn("harness", why[0])                     # WIN Pace
        self.assertIn("harness", why[1])                     # 同場 PLACE（名冇 Pace）
        self.assertIn("唔係 AU", why[2])
        self.assertIn("開跑", why[3])
        self.assertIn("走地", why[4])
        self.assertIn("搵唔到", why[5])
        self.assertIn("退出", why[6])

    def test_lay_and_unknown_strategy_refused(self) -> None:
        self.assertIn("BACK", self._why([bet(side="LAY")])[1][0])
        self.assertIn("allowed_strategies", self._why([bet(strategy="other")])[1][0])


class IdempotencyTests(Base):
    def test_rerun_never_doubles(self) -> None:
        rpc = FakeRpc()
        self.live([bet()], rpc=rpc)
        rep, _ = self.live([bet(stake=5)], rpc=rpc)
        self.assertEqual(len(rep["duplicate"]), 1)
        self.assertEqual(rpc.names().count("placeOrders"), 1)

    def test_existing_betfair_order_counts_as_duplicate(self) -> None:
        ref = bb.order_ref(bb.normalize_bet(bet())[0], "2026-11-21")
        rep, rpc = self.live([bet()], rpc=FakeRpc(current=[{"marketId": "1.10", "selectionId": 11,
                                                             "customerOrderRef": ref}]))
        self.assertEqual(len(rep["duplicate"]), 1)
        self.assertNotIn("placeOrders", rpc.names())

    def test_unknown_result_is_never_retried(self) -> None:
        rep, rpc = self.live([bet()], rpc=FakeRpc(place_raises=True))
        self.assertTrue(rep["errors"])
        self.assertTrue(any("唔知結果" in m for m in self.msgs))
        rep2, rpc2 = self.live([bet()])
        self.assertEqual(len(rep2["duplicate"]), 1)
        self.assertNotIn("placeOrders", rpc2.names())

    def test_settle_live_is_idempotent(self) -> None:
        self.live([bet()])

        def cleared(method, params):
            if params.get("groupBy") == "MARKET":
                return {"clearedOrders": [{"marketId": "1.10", "commission": 0.64}]}
            return {"clearedOrders": [{"betId": "B1", "marketId": "1.10", "betOutcome": "WON", "priceMatched": 2.6,
                                       "sizeSettled": 5.0, "profit": 8.0}]}
        s = bb.settle_live("2026-11-21", cleared, notify=self.notify)
        self.assertEqual((s["settled"], s["wins"]), (1, 1))
        self.assertAlmostEqual(s["commission"], 0.64)
        self.assertEqual(bb.settle_live("2026-11-21", cleared, notify=self.notify)["settled"], 0)
        self.assertEqual(bb.usage("2026-11-21", "live")["realized_pnl"], 7.36)


class SecretTests(Base):
    def test_credentials_never_in_errors_ledger_or_status(self) -> None:
        sess = self.root / "sess.json"
        with mock.patch.object(bt, "TRADING_SESSION_FILE", sess), \
                mock.patch.object(bf, "_post", return_value={"status": "FAIL", "error": "INVALID_USERNAME_OR_PASSWORD"}):
            os.environ.pop("BETFAIR_CERT_FILE", None)
            with self.assertRaises(bf.BetfairError) as ctx:
                bt.trading_rpc("getAccountFunds", {})
        for secret in (SECRET_KEY, SECRET_PW):
            self.assertNotIn(secret, str(ctx.exception))
        self.live([bet()])
        self.live([bet()], rpc=FakeRpc(place_raises=True))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            bb.main(["status"])
        blob = bb.ledger_path().read_text() + out.getvalue() + "\n".join(self.msgs)
        for secret in (SECRET_KEY, SECRET_PW):
            self.assertNotIn(secret, blob)

    def test_trading_login_uses_live_key_not_delayed(self) -> None:
        seen = []

        def fake_post(url, data, headers, **kw):
            seen.append(headers.get("X-Application"))
            if "login" in url:
                return {"token": "T", "status": "SUCCESS"}
            return {"result": {"availableToBetBalance": 1}}
        with mock.patch.object(bt, "TRADING_SESSION_FILE", self.root / "s.json"), \
                mock.patch.object(bf, "_post", side_effect=fake_post):
            os.environ.pop("BETFAIR_CERT_FILE", None)
            bt.trading_rpc("getAccountFunds", {})
        self.assertEqual(set(seen), {SECRET_KEY})


class HelperTests(unittest.TestCase):
    def test_tick_up(self) -> None:
        self.assertEqual(bb.tick_up(2.013), 2.02)
        self.assertEqual(bb.tick_up(3.01), 3.05)
        self.assertEqual(bb.tick_up(2.0), 2.0)
        self.assertEqual(bb.tick_up(10.1), 10.5)

    def test_au_betting_adapter_maps_to_betfair_ids(self) -> None:
        rpc = FakeRpc()
        rpc.markets["1.10"]["event"]["venue"] = "Royal Randwick"

        class FakeAB:
            MODE, MORNING_TAGS = "place", ("morning-refresh",)
            _folders = staticmethod(lambda day: [Path("2026-11-21 Royal Randwick Race 1-9")])
            _venue = staticmethod(lambda name: "Royal Randwick")
            meeting_bets = staticmethod(lambda folder, which: (
                [{"race": 3, "picks": [], "bets": [(1, "Alpha", 2.4), (7, "Ghost", 3.1)], "watch": []}],
                [], ["morning-refresh"]))
        rpc.markets["1.11"]["event"]["venue"] = "Royal Randwick"
        with mock.patch.dict(sys.modules, {"au_betting": FakeAB}):
            bets, notes = bs.au_betting_place("2026-11-21", live_config(), rpc=rpc)
        self.assertEqual([(b["market_id"], b["selection_id"]) for b in bets], [("1.11", 11)])
        self.assertEqual(bets[0]["order_type"], "LIMIT_ON_CLOSE")
        self.assertTrue(any("#7" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
