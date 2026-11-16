#!/usr/bin/env python3
"""AU Betfair 自動落注（BSP）—— **預設完全關閂**。Kelvin 2026-11-16：「先整好，暫時唔用」。

⚠️ 未有任何策略證實賺錢。開關要一直關住，直至有策略過咗 model-regression-gate。
設定步驟：docs/operations/au-betfair-autobet-setup.md

    betfair_betting.py status                       # 四重開關邊個開邊個閂、今日用咗幾多額度
    betfair_betting.py plan [--strategy S] --date D --out bets.json   # 由策略產生候選注（預設策略 none = 冇注）
    betfair_betting.py dry-run --bets bets.json     # 照足所有檢查，記低「會送乜」，永遠唔 call placeOrders
    betfair_betting.py place --bets bets.json       # 四重開關全開先會真係落注
    betfair_betting.py settle --date D [--dry-run]  # 結算（真注：listClearedOrders；dry-run：用 BSP 估）
    betfair_betting.py funds                        # 帳戶餘額（要 live key）

四重開關（**全部**要開先會落真注；任何一個閂 = 只可以 dry-run）：
  1. `betting_config.json`：`"enabled": true` 而且 `"mode": "live"`（committed，要經 ./保存.sh 改）
  2. 環境變數 `WC_BETFAIR_BETTING=live`
  3. 環境變數 `BETFAIR_LIVE_APP_KEY` 有值（唔會用 delayed key `BETFAIR_APP_KEY` 頂替）
  4. 停止檔 `<WongChoiControl>/betfair-betting.STOP` **唔存在**（`touch` 佢 = 即刻停）

只落 BACK、只用 BSP（LIMIT_ON_CLOSE；MARKET_ON_CLOSE 預設唔准）、只限 AU 純種馬 WIN／PLACE、未開跑、未走地。
冇 cancel／replace／update —— 要取消就上 Betfair 網站。

帳本（append-only JSONL）：`<WongChoiControl>/betfair-betting/ledger.jsonl`（repo 外）。
`<WongChoiControl>` = `$WONGCHOI_CONTROL_STATE_ROOT` 或者 `~/WongChoiData/WongChoiControl`（同 ROI 板一樣）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import betfair_client as bf  # noqa: E402

REPO_ROOT = HERE.parents[3]
CONFIG_PATH = HERE / "betting_config.json"
SYDNEY = ZoneInfo("Australia/Sydney")
ENV_SWITCH = "WC_BETFAIR_BETTING"
LIVE_KEY_ENV = "BETFAIR_LIVE_APP_KEY"
ORDER_TYPES = ("LIMIT_ON_CLOSE", "MARKET_ON_CLOSE")
HARNESS = re.compile(r"\b(Pace|Trot|Pacers?|Trotters?)\b", re.I)
REQUIRED_LIMITS = ("min_stake", "max_stake_per_bet", "max_total_stake_per_day", "max_bets_per_day",
                   "daily_stop_loss", "max_exposure_per_race", "min_bsp", "max_bsp",
                   "min_minutes_before_start", "max_minutes_before_start", "min_available_funds")
# 帳本入面「已經送過／可能送咗」嘅狀態 —— 同一個 ref 有呢啲就永遠唔再送（unknown = 網絡斷咗，唔知有冇落到）。
LIVE_TAKEN = ("sent", "accepted", "rejected", "unknown")


class BettingRefused(RuntimeError):
    pass


# ── 路徑 ────────────────────────────────────────────────────────────────

def control_root() -> Path:
    root = os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl")
    return Path(root).expanduser()


def kill_file() -> Path:
    return control_root() / "betfair-betting.STOP"


def ledger_path() -> Path:
    return control_root() / "betfair-betting" / "ledger.jsonl"


# ── 設定同開關 ──────────────────────────────────────────────────────────

def load_config(path: Path | None = None) -> dict:
    return json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))


def config_problems(config: dict) -> list[str]:
    """設定唔齊／唔合理 = 唔准落真注（fail closed）。"""
    lim = config.get("limits") or {}
    out = []
    for k in REQUIRED_LIMITS:
        v = lim.get(k)
        if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0 or (v == 0 and k != "min_minutes_before_start"):
            out.append(f"limits.{k} 唔啱（{v!r}）")
    if not out:
        if lim["max_stake_per_bet"] < lim["min_stake"]:
            out.append("limits.max_stake_per_bet < min_stake")
        if lim["max_bsp"] <= lim["min_bsp"] or lim["min_bsp"] < 1.01:
            out.append("limits.min_bsp／max_bsp 唔啱")
    return out


def switches(config: dict | None = None, env: dict | None = None) -> dict:
    """四重開關，逐個講開定閂、點解。`all_on` 先可以落真注。"""
    env = os.environ if env is None else env
    if config is None:
        try:
            config = load_config()
        except (OSError, ValueError) as exc:
            config = {"_error": type(exc).__name__}
    layers = []
    cfg_on = config.get("enabled") is True and config.get("mode") == "live"
    layers.append({"name": "1. betting_config.json", "on": cfg_on,
                   "why": f"enabled={config.get('enabled')!r}, mode={config.get('mode')!r}"
                          + ("" if cfg_on else "（要 enabled=true 同 mode=\"live\"）")})
    env_on = env.get(ENV_SWITCH, "").strip() == "live"
    layers.append({"name": f"2. env {ENV_SWITCH}", "on": env_on,
                   "why": "=live" if env_on else f"未設成 live（而家：{'有值但唔係 live' if env.get(ENV_SWITCH) else '冇設'}）"})
    key_on = bool(env.get(LIVE_KEY_ENV, "").strip())
    layers.append({"name": f"3. env {LIVE_KEY_ENV}", "on": key_on,
                   "why": "有設（值唔會顯示）" if key_on else "冇設（唔會用 delayed key 頂替）"})
    kf = kill_file()
    stop_on = not kf.exists()
    layers.append({"name": "4. 停止檔", "on": stop_on, "why": f"{kf} {'唔存在' if stop_on else '存在 → 停'}"})
    problems = config_problems(config)
    if problems:
        layers.append({"name": "設定檢查", "on": False, "why": "；".join(problems)})
    blocking = [f"{x['name']}: {x['why']}" for x in layers if not x["on"]]
    return {"layers": layers, "all_on": not blocking, "blocking": blocking}


# ── 注單 ────────────────────────────────────────────────────────────────

_TICKS = [(2, 0.01), (3, 0.02), (4, 0.05), (6, 0.1), (10, 0.2), (20, 0.5), (30, 1), (50, 2), (100, 5), (1000, 10)]


def tick_up(price: float) -> float:
    """向上執到 Betfair 合法價位（最低可接受 BSP 向上執 = 更保守）。"""
    price = max(1.01, float(price))
    lo = 1.0
    for hi, step in _TICKS:
        if price <= hi + 1e-9:
            n = math.ceil(round((price - lo) / step, 6))
            return round(min(hi, lo + n * step), 2)
        lo = hi
    return 1000.0


def sydney_day(now: datetime) -> str:
    return now.astimezone(SYDNEY).strftime("%Y-%m-%d")


def strategy_ref(strategy: str) -> str:
    return ("wc-" + re.sub(r"[^A-Za-z0-9_-]", "", strategy))[:15]


def order_ref(bet: dict, day: str) -> str:
    """同一日、同策略、同市場、同馬、同方向 → 同一個 ref（注碼唔入 hash：改注碼重跑都唔會落多次）。"""
    raw = "|".join(str(x) for x in (day, bet["strategy"], bet["market_id"], bet["selection_id"], bet["side"],
                                    bet["order_type"]))
    return "wc" + hashlib.sha1(raw.encode()).hexdigest()[:30]


def normalize_bet(raw: dict) -> tuple[dict | None, str | None]:
    try:
        bet = {
            "market_id": str(raw["market_id"]).strip(),
            "selection_id": int(raw["selection_id"]),
            "side": str(raw.get("side", "BACK")).upper(),
            "stake": math.floor(float(raw["stake"]) * 100) / 100,
            "order_type": str(raw.get("order_type", "LIMIT_ON_CLOSE")).upper(),
            "min_price": None if raw.get("min_price") in (None, "") else float(raw["min_price"]),
            "strategy": str(raw.get("strategy") or "").strip(),
            "reason": str(raw.get("reason") or "").strip(),
            "label": str(raw.get("label") or "").strip(),
        }
    except (KeyError, TypeError, ValueError) as exc:
        return None, f"注單格式錯：{type(exc).__name__} {exc}"
    if not re.fullmatch(r"\d\.\d+", bet["market_id"]):
        return None, f"market_id 唔啱：{bet['market_id']}"
    if bet["side"] != "BACK":
        return None, "只准 BACK（唔做 LAY）"
    if bet["order_type"] not in ORDER_TYPES:
        return None, f"order_type 只准 {ORDER_TYPES}"
    if bet["order_type"] == "LIMIT_ON_CLOSE":
        if not bet["min_price"]:
            return None, "LIMIT_ON_CLOSE 一定要有 min_price（最低可接受 BSP）"
        bet["min_price"] = tick_up(bet["min_price"])
    if not bet["strategy"]:
        return None, "冇 strategy 名"
    if bet["stake"] <= 0:
        return None, "stake 要大過 0"
    return bet, None


def read_bets(path: Path) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("bets") or []
    if not isinstance(data, list):
        raise ValueError("bets 檔要係 list 或者 {\"bets\": [...]}")
    return data


# ── 帳本 ────────────────────────────────────────────────────────────────

def ledger_append(row: dict) -> None:
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def ledger_rows() -> list[dict]:
    try:
        lines = ledger_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _latest_by_ref(rows: list[dict], mode: str) -> dict[str, dict]:
    out = {}
    for r in rows:
        if r.get("mode") == mode and r.get("ref") and r.get("event") in (LIVE_TAKEN + ("would_send",)):
            out[r["ref"]] = r
    return out


def usage(day: str, mode: str, rows: list[dict] | None = None) -> dict:
    """今日（悉尼日）已用額度。live 計 sent/accepted/unknown（rejected 唔計注碼）；dry-run 計 would_send。"""
    rows = ledger_rows() if rows is None else rows
    taken = ("sent", "accepted", "unknown") if mode == "live" else ("would_send",)
    latest = {ref: r for ref, r in _latest_by_ref([r for r in rows if r.get("day") == day], mode).items()
              if r["event"] in taken}
    race = defaultdict(float)
    for r in latest.values():
        race[r.get("race_key") or r["bet"]["market_id"]] += r["bet"]["stake"]
    settled = [r for r in rows if r.get("mode") == mode and r.get("day") == day and r.get("event") == "settled"]
    pnl = sum(float(r.get("profit") or 0) - float(r.get("commission") or 0) for r in settled)
    return {"bets": len(latest), "stake": round(sum(r["bet"]["stake"] for r in latest.values()), 2),
            "race": dict(race), "realized_pnl": round(pnl, 2), "refs": set(latest)}


# ── 市場檢查 ────────────────────────────────────────────────────────────

def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def check_markets(market_ids: list[str], rpc, now: datetime, limits: dict) -> dict[str, dict]:
    """→ {market_id: {"ok", "why", ...}}。任何唔肯定（搵唔到、唔係 AU 純種馬、開咗跑、走地中）都當唔得。"""
    ids = sorted(set(market_ids))
    info = {m: {"ok": False, "why": "Betfair 搵唔到呢個市場"} for m in ids}
    if not ids:
        return info
    cat = rpc("listMarketCatalogue", {"filter": {"marketIds": ids}, "maxResults": len(ids),
                                      "marketProjection": ["EVENT_TYPE", "EVENT", "MARKET_START_TIME",
                                                           "MARKET_DESCRIPTION", "RUNNER_DESCRIPTION"]}) or []
    books = {b.get("marketId"): b for b in (rpc("listMarketBook", {
        "marketIds": ids, "priceProjection": {"priceData": ["SP_AVAILABLE"]}}) or [])}
    types = tuple(limits.get("market_types") or ("WIN", "PLACE"))
    country = limits.get("country") or "AU"
    for m in cat:
        mid = m.get("marketId")
        if mid not in info:
            continue
        ev, desc = m.get("event") or {}, m.get("description") or {}
        mtype = desc.get("marketType")
        start = m.get("marketStartTime")
        rec = {"ok": False, "type": mtype, "start": start, "event_id": ev.get("id"), "venue": ev.get("venue"),
               "name": m.get("marketName"), "base_rate": desc.get("marketBaseRate"),
               "race_key": f"{ev.get('id')}|{start}", "runners": {}}
        info[mid] = rec
        mins = (_parse_time(start) - now).total_seconds() / 60 if start else None
        if str((m.get("eventType") or {}).get("id")) != "7":
            rec["why"] = "唔係賽馬（eventType≠7）"
        elif ev.get("countryCode") != country:
            rec["why"] = f"唔係 {country}（{ev.get('countryCode')}）"
        elif mtype not in types:
            rec["why"] = f"市場類型 {mtype} 唔准"
        elif desc.get("bspMarket") is not True:
            rec["why"] = "唔係 BSP 市場"
        elif mins is None or mins < limits["min_minutes_before_start"]:
            rec["why"] = "已經開跑／太近開跑"
        elif mins > limits["max_minutes_before_start"]:
            rec["why"] = "離開跑太遠"
        elif not _is_thoroughbred(m, mtype, rpc):
            rec["why"] = "唔係純種馬（harness）或者確認唔到"
        else:
            book = books.get(mid) or {}
            if book.get("status") != "OPEN":
                rec["why"] = f"市場狀態 {book.get('status')}"
            elif book.get("inplay") is not False:
                rec["why"] = "走地中／狀態唔明"
            else:
                rec["ok"], rec["why"] = True, ""
                for r in book.get("runners") or []:
                    rec["runners"][int(r.get("selectionId"))] = {"status": r.get("status"),
                                                                 "near": (r.get("sp") or {}).get("nearPrice")}
    return info


def _is_thoroughbred(market: dict, mtype: str, rpc) -> bool:
    if mtype == "WIN":
        return not HARNESS.search(market.get("marketName") or "")
    # PLACE 市場名係「To Be Placed」冇 Pace／Trot 字眼 —— 一定要搵返同 event、同開跑時間嘅 WIN 市場確認
    ev = (market.get("event") or {}).get("id")
    if not ev:
        return False
    sib = rpc("listMarketCatalogue", {"filter": {"eventIds": [ev], "marketTypeCodes": ["WIN"]}, "maxResults": 50,
                                      "marketProjection": ["MARKET_START_TIME"]}) or []
    same = [s for s in sib if s.get("marketStartTime") == market.get("marketStartTime")]
    return bool(same) and not any(HARNESS.search(s.get("marketName") or "") for s in same)


# ── 帳戶 ────────────────────────────────────────────────────────────────

def day_window_utc(day: str) -> tuple[str, str]:
    start = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=SYDNEY)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (start.astimezone(timezone.utc).strftime(fmt),
            (start + timedelta(days=1)).astimezone(timezone.utc).strftime(fmt))


def cleared_pnl(rpc, day: str, strategy_refs: list[str]) -> float:
    """今日已結算盈虧（扣佣）—— 只計我哋嘅 customerStrategyRef。"""
    lo, hi = day_window_utc(day)
    out = rpc("listClearedOrders", {"betStatus": "SETTLED", "groupBy": "MARKET",
                                    "customerStrategyRefs": strategy_refs,
                                    "settledDateRange": {"from": lo, "to": hi}}) or {}
    return round(sum(float(o.get("profit") or 0) - float(o.get("commission") or 0)
                     for o in out.get("clearedOrders") or []), 2)


def current_order_keys(rpc, market_ids: list[str]) -> tuple[set, set]:
    """→ (我哋落過嘅 customerOrderRef, (market, selection))。"""
    out = rpc("listCurrentOrders", {"marketIds": sorted(set(market_ids)), "orderProjection": "ALL"}) or {}
    refs, pairs = set(), set()
    for o in out.get("currentOrders") or []:
        if o.get("customerOrderRef"):
            refs.add(o["customerOrderRef"])
        if str(o.get("customerStrategyRef") or "").startswith("wc-"):
            pairs.add((o.get("marketId"), int(o.get("selectionId") or 0)))
    return refs, pairs


# ── 主流程 ──────────────────────────────────────────────────────────────

def _notify_default(text: str) -> None:
    sys.path.insert(0, str(HERE.parent / "au_daily_auto"))
    import au_notify  # noqa: PLC0415

    au_notify.push(text, title="💸 Betfair 落注", audience="primary")


def _safe_notify(notify, text: str) -> None:
    try:
        (notify or _notify_default)(text)
    except Exception:  # noqa: BLE001 —— 通知失敗唔可以令落注流程出錯
        pass


def _fmt_bet(b: dict) -> str:
    price = f" ≥{b['min_price']:g}" if b.get("min_price") else " MOC"
    return f"{b.get('label') or b['market_id'] + '/' + str(b['selection_id'])} ${b['stake']:g}{price} [{b['strategy']}]"


def run(raw_bets: list[dict], *, mode: str, config: dict, market_rpc=None, account_rpc=None,
        now: datetime | None = None, notify=None, notify_dry_run: bool = False) -> dict:
    """mode = "dry_run" 或 "live"。dry_run **永遠唔會** call placeOrders。

    market_rpc：讀市場（listMarketCatalogue／listMarketBook）。None = 唔檢查市場（只限 dry-run）。
    account_rpc：讀帳戶 + live 落注（listCurrentOrders／listClearedOrders／getAccountFunds／placeOrders）。
    """
    if mode not in ("dry_run", "live"):
        raise ValueError(mode)
    now = now or datetime.now(timezone.utc)
    day = sydney_day(now)
    lim = config.get("limits") or {}
    live = mode == "live"
    report = {"mode": mode, "day": day, "would_send": [], "placed": [], "rejected": [], "blocked": [],
              "duplicate": [], "errors": [], "warnings": []}
    base = {"day": day, "mode": mode}

    def log(event: str, **kw) -> None:
        ledger_append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": event, **base, **kw})

    if live:
        sw = switches(config)
        if not sw["all_on"]:
            log("refused", reason=sw["blocking"])
            report["errors"].append("開關未全開：" + "；".join(sw["blocking"]))
            report["refused"] = True
            return report
        if market_rpc is None or account_rpc is None:
            raise BettingRefused("live 一定要有 market_rpc 同 account_rpc")
    elif config_problems(config):
        report["warnings"].append("設定有問題（live 會拒絕）：" + "；".join(config_problems(config)))

    bets = []
    for raw in raw_bets:
        bet, err = normalize_bet(raw if isinstance(raw, dict) else {})
        if err:
            report["blocked"].append({"bet": raw, "why": err})
            log("blocked", bet=raw, reason=err)
        else:
            bets.append(bet)
    if not bets:
        _finish(report, notify, notify_dry_run)
        return report

    allowed = set(config.get("allowed_strategies") or [])
    markets = {}
    if market_rpc is not None:
        try:
            markets = check_markets([b["market_id"] for b in bets], market_rpc, now, lim)
        except bf.BetfairError as exc:
            report["errors"].append(f"讀市場失敗：{exc}")
            log("error", reason=f"market check: {exc}")
            _finish(report, notify, notify_dry_run)
            return report
    else:
        report["warnings"].append("冇檢查市場（--offline）")

    # 帳戶狀態：live 必須讀到；dry-run 有 live key 先讀
    funds = pnl_api = None
    cur_refs, cur_pairs = set(), set()
    if account_rpc is not None:
        try:
            funds = float((account_rpc("getAccountFunds", {}) or {}).get("availableToBetBalance") or 0)
            cur_refs, cur_pairs = current_order_keys(account_rpc, [b["market_id"] for b in bets])
            refs = sorted({strategy_ref(b["strategy"]) for b in bets})
            pnl_api = cleared_pnl(account_rpc, day, refs)
        except bf.BetfairError as exc:
            report["errors"].append(f"讀帳戶失敗：{exc}")
            log("error", reason=f"account check: {exc}")
            if live:
                _finish(report, notify, notify_dry_run)
                return report
    elif not live:
        report["warnings"].append("冇讀帳戶（冇 live key）：餘額、現有注單、今日盈虧冇檢查")

    rows = ledger_rows()
    used = usage(day, mode, rows)
    taken = set(_latest_by_ref(rows, mode)) if live else used["refs"]
    pnl = pnl_api if pnl_api is not None else used["realized_pnl"]
    if live:
        pnl = min(pnl, used["realized_pnl"])            # 兩個來源取差嗰個
    report["usage_before"] = {k: v for k, v in used.items() if k not in ("refs", "race")}
    report["funds"], report["realized_pnl"] = funds, pnl

    for bet in bets:
        ref = order_ref(bet, day)
        mk = markets.get(bet["market_id"]) or {}
        race_key = mk.get("race_key") or bet["market_id"]
        entry = {"ref": ref, "bet": bet, "race_key": race_key, "base_rate": mk.get("base_rate")}
        why = _risk_check(bet, ref, mk, market_rpc is not None, lim, used, pnl, funds, live,
                          allowed, taken, cur_refs, cur_pairs, report)
        if why == "duplicate":
            report["duplicate"].append(entry)
            log("duplicate", **entry)
            continue
        if why:
            report["blocked"].append({**entry, "why": why})
            log("blocked", reason=why, **entry)
            continue
        used["bets"] += 1
        used["stake"] = round(used["stake"] + bet["stake"], 2)
        used["race"][race_key] = used["race"].get(race_key, 0) + bet["stake"]
        taken.add(ref)
        if funds is not None:
            funds -= bet["stake"]
        if not live:
            report["would_send"].append({**entry, "request": place_request(bet, ref)})
            log("would_send", request=place_request(bet, ref), **entry)
            continue
        # 送之前最後一次查開關（停止檔可以喺中途 touch）
        sw = switches(config)
        if not sw["all_on"]:
            report["errors"].append("中途停：" + "；".join(sw["blocking"]))
            log("refused", reason=sw["blocking"], **entry)
            break
        req = place_request(bet, ref)
        log("sent", request=req, **entry)
        try:
            resp = account_rpc("placeOrders", req) or {}
        except bf.BetfairError as exc:
            report["errors"].append(f"placeOrders 唔知結果（{exc}）—— 已鎖住呢注唔再送，請上 Betfair 確認")
            log("unknown", error=str(exc), **entry)
            continue
        ir = (resp.get("instructionReports") or [{}])[0]
        if resp.get("status") == "SUCCESS" and ir.get("status") == "SUCCESS":
            report["placed"].append({**entry, "bet_id": ir.get("betId")})
            log("accepted", bet_id=ir.get("betId"), placed=ir.get("placedDate"), **entry)
        else:
            code = ir.get("errorCode") or resp.get("errorCode") or resp.get("status")
            report["rejected"].append({**entry, "why": code})
            log("rejected", error=code, **entry)
    _finish(report, notify, notify_dry_run)
    return report


def _risk_check(bet, ref, mk, checked, lim, used, pnl, funds, live, allowed, taken, cur_refs, cur_pairs,
                report) -> str | None:
    if ref in taken or ref in cur_refs or (bet["market_id"], bet["selection_id"]) in cur_pairs:
        return "duplicate"
    if bet["strategy"] not in allowed:
        msg = f"策略 {bet['strategy']} 唔喺 allowed_strategies"
        if live:
            return msg
        if msg not in report["warnings"]:
            report["warnings"].append(msg + "（live 會攔）")
    if checked:
        if not mk.get("ok"):
            return f"市場：{mk.get('why') or '唔得'}"
        runner = (mk.get("runners") or {}).get(bet["selection_id"])
        if not runner or runner.get("status") != "ACTIVE":
            return "匹馬唔喺市場或者已退出"
        near = runner.get("near")
        if isinstance(near, (int, float)) and near > 0 and not (lim["min_bsp"] <= near <= lim["max_bsp"]):
            return f"預計 BSP {near:g} 唔喺 {lim['min_bsp']:g}–{lim['max_bsp']:g}"
    if bet["order_type"] == "MARKET_ON_CLOSE" and not lim.get("allow_market_on_close"):
        return "MARKET_ON_CLOSE 唔准（冇最低 BSP 保護）"
    if bet["stake"] < lim["min_stake"]:
        return f"注碼 {bet['stake']:g} < 最少 {lim['min_stake']:g}"
    if bet["stake"] > lim["max_stake_per_bet"]:
        return f"注碼 {bet['stake']:g} > 每注上限 {lim['max_stake_per_bet']:g}"
    if bet["min_price"] is not None and not (lim["min_bsp"] <= bet["min_price"] <= lim["max_bsp"]):
        return f"min_price {bet['min_price']:g} 唔喺 {lim['min_bsp']:g}–{lim['max_bsp']:g}"
    if pnl <= -lim["daily_stop_loss"]:
        return f"今日已蝕 {pnl:g}，到咗止蝕 {lim['daily_stop_loss']:g}"
    if used["bets"] + 1 > lim["max_bets_per_day"]:
        return f"今日注數上限 {lim['max_bets_per_day']}"
    if used["stake"] + bet["stake"] > lim["max_total_stake_per_day"] + 1e-9:
        return f"今日總注碼上限 {lim['max_total_stake_per_day']:g}（已用 {used['stake']:g}）"
    race_key = mk.get("race_key") or bet["market_id"]
    if used["race"].get(race_key, 0) + bet["stake"] > lim["max_exposure_per_race"] + 1e-9:
        return f"每場上限 {lim['max_exposure_per_race']:g}"
    if funds is not None:
        if funds < lim["min_available_funds"]:
            return f"可用餘額 {funds:g} < 底線 {lim['min_available_funds']:g}"
        if funds - bet["stake"] < 0:
            return "餘額唔夠"
    return None


def place_request(bet: dict, ref: str) -> dict:
    ins = {"selectionId": bet["selection_id"], "handicap": 0, "side": "BACK", "orderType": bet["order_type"],
           "customerOrderRef": ref}
    if bet["order_type"] == "LIMIT_ON_CLOSE":
        ins["limitOnCloseOrder"] = {"liability": bet["stake"], "price": bet["min_price"]}
    else:
        ins["marketOnCloseOrder"] = {"liability": bet["stake"]}
    return {"marketId": bet["market_id"], "instructions": [ins], "customerRef": ref,
            "customerStrategyRef": strategy_ref(bet["strategy"])}


def _finish(report: dict, notify, notify_dry_run: bool) -> None:
    if report["mode"] == "live":
        lines = []
        if report["placed"]:
            lines.append(f"✅ 落咗 {len(report['placed'])} 注（BSP）")
            lines += ["  " + _fmt_bet(p["bet"]) + f" #{p.get('bet_id')}" for p in report["placed"]]
        if report["rejected"]:
            lines.append(f"❌ 被拒 {len(report['rejected'])} 注")
            lines += ["  " + _fmt_bet(p["bet"]) + f"：{p['why']}" for p in report["rejected"]]
        limit_hits = [b for b in report["blocked"] if "上限" in b["why"] or "止蝕" in b["why"] or "餘額" in b["why"]]
        if limit_hits:
            lines.append(f"⛔ 觸發限額 {len(limit_hits)} 注")
            lines += ["  " + _fmt_bet(b["bet"]) + f"：{b['why']}" for b in limit_hits]
        if report["errors"] and not report.get("refused"):
            lines.append("⚠️ 錯誤")
            lines += ["  " + e for e in report["errors"]]
        if lines:
            _safe_notify(notify, f"💸 Betfair 自動落注 {report['day']}\n" + "\n".join(lines))
        return
    if not notify_dry_run:
        return
    rows = ledger_rows()
    if any(r.get("event") == "dry_run_summary_sent" and r.get("day") == report["day"] for r in rows):
        return
    text = (f"🧪 Betfair dry-run {report['day']}（冇落注）\n會送 {len(report['would_send'])} 注、"
            f"攔 {len(report['blocked'])}、重覆 {len(report['duplicate'])}"
            + "".join(f"\n  {_fmt_bet(w['bet'])}" for w in report["would_send"][:15]))
    _safe_notify(notify, text)
    ledger_append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "dry_run_summary_sent",
                   "day": report["day"], "mode": "dry_run"})


# ── 結算 ────────────────────────────────────────────────────────────────

def settle_live(day: str, rpc, notify=None) -> dict:
    rows = ledger_rows()
    accepted = {r["bet_id"]: r for r in rows if r.get("mode") == "live" and r.get("day") == day
                and r.get("event") == "accepted" and r.get("bet_id")}
    done = {r.get("bet_id") for r in rows if r.get("mode") == "live" and r.get("event") == "settled"}
    todo = [b for b in accepted if b not in done]
    out = {"day": day, "settled": 0, "stake": 0.0, "profit": 0.0, "commission": 0.0, "wins": 0}
    if not todo:
        return out
    bets = (rpc("listClearedOrders", {"betStatus": "SETTLED", "betIds": todo}) or {}).get("clearedOrders") or []
    if not bets:
        return out
    mkts = sorted({b.get("marketId") for b in bets})
    by_mkt = (rpc("listClearedOrders", {"betStatus": "SETTLED", "betIds": todo, "groupBy": "MARKET"}) or {})
    comm = {m.get("marketId"): float(m.get("commission") or 0) for m in by_mkt.get("clearedOrders") or []}
    first_in_mkt = set()
    for b in bets:
        src = accepted.get(b.get("betId")) or {}
        mid = b.get("marketId")
        c = comm.get(mid, 0.0) if mid not in first_in_mkt else 0.0     # 佣金係逐個市場計，記喺第一注
        first_in_mkt.add(mid)
        profit = float(b.get("profit") or 0)
        ledger_append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "settled",
                       "day": day, "mode": "live", "ref": src.get("ref"), "bet_id": b.get("betId"),
                       "market_id": mid, "outcome": b.get("betOutcome"), "bsp": b.get("priceMatched"),
                       "size_settled": b.get("sizeSettled"), "profit": profit, "commission": c})
        out["settled"] += 1
        out["stake"] += float(b.get("sizeSettled") or (src.get("bet") or {}).get("stake") or 0)
        out["profit"] += profit
        out["commission"] += c
        out["wins"] += b.get("betOutcome") in ("WON", "WIN")
    out["markets"] = len(mkts)
    _safe_notify(notify, _settle_text(out, "💸 Betfair 結算"))
    return out


def settle_dry_run(day: str, rpc, config: dict) -> dict:
    """dry-run 估算：用真實 BSP 計（LIMIT_ON_CLOSE：BSP < min_price 當冇成交），佣金按市場 marketBaseRate。"""
    rows = ledger_rows()
    sends = {r["ref"]: r for r in rows if r.get("mode") == "dry_run" and r.get("day") == day
             and r.get("event") == "would_send"}
    done = {r.get("ref") for r in rows if r.get("mode") == "dry_run" and r.get("event") == "settled"}
    todo = [r for ref, r in sends.items() if ref not in done]
    out = {"day": day, "settled": 0, "stake": 0.0, "profit": 0.0, "commission": 0.0, "wins": 0, "unmatched": 0}
    if not todo:
        return out
    ids = sorted({r["bet"]["market_id"] for r in todo})
    books = {}
    for i in range(0, len(ids), 40):
        for b in rpc("listMarketBook", {"marketIds": ids[i:i + 40],
                                        "priceProjection": {"priceData": ["SP_TRADED"]}}) or []:
            books[b.get("marketId")] = b
    by_mkt = defaultdict(list)
    for r in todo:
        book = books.get(r["bet"]["market_id"]) or {}
        if book.get("status") != "CLOSED":
            continue
        runner = next((x for x in book.get("runners") or [] if int(x.get("selectionId")) == r["bet"]["selection_id"]),
                      None)
        if runner is None:
            continue
        sp = (runner.get("sp") or {}).get("actualSP")
        bet = r["bet"]
        if not sp or runner.get("status") == "REMOVED" or (bet.get("min_price") and sp < bet["min_price"]):
            profit, outcome = 0.0, "UNMATCHED"
            out["unmatched"] += 1
        else:
            won = runner.get("status") == "WINNER"
            profit = round(bet["stake"] * (sp - 1), 2) if won else -bet["stake"]
            outcome = "WON" if won else "LOST"
        by_mkt[bet["market_id"]].append((r, profit, outcome, sp))
    default_pct = float((config.get("limits") or {}).get("default_commission_pct") or 10.0)
    for mid, items in by_mkt.items():
        rate = items[0][0].get("base_rate")
        rate = float(rate) if isinstance(rate, (int, float)) else default_pct
        comm = round(max(0.0, sum(p for _, p, _, _ in items)) * rate / 100, 2)
        for j, (r, profit, outcome, sp) in enumerate(items):
            c = comm if j == 0 else 0.0
            ledger_append({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "event": "settled",
                           "day": day, "mode": "dry_run", "ref": r["ref"], "market_id": mid, "outcome": outcome,
                           "bsp": sp, "profit": profit, "commission": c, "commission_pct": rate})
            out["settled"] += 1
            if outcome != "UNMATCHED":
                out["stake"] += r["bet"]["stake"]
            out["profit"] += profit
            out["commission"] += c
            out["wins"] += outcome == "WON"
    return out


def _settle_text(s: dict, title: str) -> str:
    net = s["profit"] - s["commission"]
    return (f"{title} {s['day']}\n注數 {s['settled']}（中 {s['wins']}）· 本金 ${s['stake']:.2f}\n"
            f"毛利 ${s['profit']:+.2f} · 佣金 ${s['commission']:.2f} · 淨 ${net:+.2f}")


# ── CLI ─────────────────────────────────────────────────────────────────

def _market_rpc_readonly():
    return bf.rpc                                            # delayed key，只讀（READ_ONLY_METHODS）


def _account_rpc_readonly():
    """dry-run 用：有 live key 先讀帳戶，而且包住唔准 placeOrders。"""
    if not os.environ.get(LIVE_KEY_ENV, "").strip():
        return None
    import betfair_trading as bt  # noqa: PLC0415

    def call(method: str, params: dict):
        if method in bt.WRITE:
            raise bf.BetfairError(f"{method} 唔准：dry-run")
        return bt.trading_rpc(method, params)
    return call


def cmd_status(config: dict) -> int:
    sw = switches(config)
    print("AU Betfair 自動落注 —— " + ("🟢 四重開關全開：會落真注" if sw["all_on"] else "🔴 唔會落真注"))
    for x in sw["layers"]:
        print(f"  {'✅' if x['on'] else '⛔'} {x['name']}: {x['why']}")
    print(f"  策略：{config.get('strategy')}；allowed_strategies：{config.get('allowed_strategies') or '（冇）'}")
    lim = config.get("limits") or {}
    print("  限額：" + "，".join(f"{k}={lim.get(k)}" for k in REQUIRED_LIMITS))
    day = sydney_day(datetime.now(timezone.utc))
    for mode in ("live", "dry_run"):
        u = usage(day, mode)
        print(f"  今日 {day} {mode}：{u['bets']} 注、${u['stake']:g}、已結算盈虧 {u['realized_pnl']:+g}")
    print(f"  帳本：{ledger_path()}")
    print(f"  停止檔：touch '{kill_file()}'")
    return 0


def _print_report(rep: dict) -> None:
    print(json.dumps({k: v for k, v in rep.items()}, ensure_ascii=False, indent=2, default=str))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    p = sub.add_parser("plan")
    p.add_argument("--strategy")
    p.add_argument("--date")
    p.add_argument("--bets-in", help="strategy=json 用：候選注 JSON")
    p.add_argument("--out")
    p = sub.add_parser("dry-run")
    p.add_argument("--bets", required=True)
    p.add_argument("--offline", action="store_true", help="唔連 Betfair（唔檢查市場）")
    p.add_argument("--notify", action="store_true", help="每日最多一條 Telegram 摘要（primary）")
    p = sub.add_parser("place")
    p.add_argument("--bets", required=True)
    p = sub.add_parser("settle")
    p.add_argument("--date", required=True)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-notify", action="store_true")
    sub.add_parser("funds")
    a = ap.parse_args(argv)
    config = load_config()
    try:
        if a.cmd == "status":
            return cmd_status(config)
        if a.cmd == "plan":
            import betting_strategies as bs  # noqa: PLC0415

            day = a.date or sydney_day(datetime.now(timezone.utc))
            bets, notes = bs.plan(a.strategy or config.get("strategy") or "none", day=day, config=config,
                                  rpc=_market_rpc_readonly(), bets_in=a.bets_in)
            for n in notes:
                print("  " + n, file=sys.stderr)
            text = json.dumps({"bets": bets}, ensure_ascii=False, indent=2)
            if a.out:
                Path(a.out).write_text(text + "\n", encoding="utf-8")
                print(f"{len(bets)} 注 → {a.out}")
            else:
                print(text)
            return 0
        if a.cmd == "dry-run":
            rep = run(read_bets(Path(a.bets)), mode="dry_run", config=config,
                      market_rpc=None if a.offline else _market_rpc_readonly(),
                      account_rpc=None if a.offline else _account_rpc_readonly(), notify_dry_run=a.notify)
            _print_report(rep)
            return 0
        if a.cmd == "place":
            sw = switches(config)
            if not sw["all_on"]:
                print("🔴 拒絕落注 —— 開關未全開：", file=sys.stderr)
                for b in sw["blocking"]:
                    print("  ⛔ " + b, file=sys.stderr)
                return 2
            import betfair_trading as bt  # noqa: PLC0415

            rep = run(read_bets(Path(a.bets)), mode="live", config=config,
                      market_rpc=bt.trading_rpc, account_rpc=bt.trading_rpc)
            _print_report(rep)
            return 1 if rep["errors"] or rep["rejected"] else 0
        if a.cmd == "settle":
            if a.dry_run:
                s = settle_dry_run(a.date, _market_rpc_readonly(), config)
                print(_settle_text(s, "🧪 dry-run 估算"))
                return 0
            import betfair_trading as bt  # noqa: PLC0415

            s = settle_live(a.date, bt.trading_rpc, notify=(lambda t: None) if a.no_notify else None)
            print(_settle_text(s, "💸 Betfair 結算"))
            return 0
        if a.cmd == "funds":
            import betfair_trading as bt  # noqa: PLC0415

            f = bt.trading_rpc("getAccountFunds", {}) or {}
            for k in ("availableToBetBalance", "exposure", "retainedCommission", "exposureLimit", "discountRate"):
                print(f"  {k}: {f.get(k)}")
            return 0
    except bf.BetfairError as exc:
        print(f"Betfair 錯誤：{exc}", file=sys.stderr)
        if a.cmd == "place" or (a.cmd == "settle" and not a.dry_run and not a.no_notify):
            _safe_notify(None, f"⚠️ Betfair 落注 module 錯誤（{a.cmd}）：{exc}")
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
