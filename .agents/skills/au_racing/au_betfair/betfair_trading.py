"""Betfair 落注 client —— **只畀 `betfair_betting.py` 用**，預設係關閂嘅。

同只讀嘅 `betfair_client.py` 分開，原因：
  * 只讀 client 鎖死 `READ_ONLY_METHODS`，測試會攔住佢放寬。落注權限唔可以「順手」加落去。
  * 落注一定要用 **live app key**（`BETFAIR_LIVE_APP_KEY`），**永遠唔會**退返去 delayed key
    （`BETFAIR_APP_KEY`）。冇 live key = 呢個 client 乜都唔做。
  * 用另一個 session 檔（`~/.wongchoi_betfair_trading_session.json`），唔會同記錄器嘅 session 撈埋。

准用嘅 method：
  * 讀：listMarketCatalogue、listMarketBook、listCurrentOrders、listClearedOrders、getAccountFunds
  * 寫：**只有 placeOrders**。冇 cancelOrders／replaceOrders／updateOrders —— 要取消就上 Betfair 網站手動做。

`placeOrders` 喺送出前會**再查一次**四重開關（`betfair_betting.switches()`），就算有人直接 call 呢個
function、跳過咗上層嘅檢查，開關唔齊都會拒絕。

登入、錯誤處理沿用 `betfair_client`：密碼、session token、app key 永遠唔會入 log／例外訊息。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import betfair_client as bf

LIVE_KEY_ENV = "BETFAIR_LIVE_APP_KEY"
ACCOUNT_URL = os.environ.get("BETFAIR_ACCOUNT_URL", "https://api.betfair.com/exchange/account/json-rpc/v1")
TRADING_SESSION_FILE = Path(os.environ.get("BETFAIR_TRADING_SESSION_FILE",
                                           str(Path.home() / ".wongchoi_betfair_trading_session.json")))

BETTING_READ = frozenset({"listMarketCatalogue", "listMarketBook", "listCurrentOrders", "listClearedOrders"})
ACCOUNT_READ = frozenset({"getAccountFunds"})
WRITE = frozenset({"placeOrders"})
ALLOWED = BETTING_READ | ACCOUNT_READ | WRITE
# 明文列出永遠唔准嘅 method，測試會鎖住。
FORBIDDEN = frozenset({"cancelOrders", "replaceOrders", "updateOrders"})


def live_app_key() -> str:
    """只讀 `BETFAIR_LIVE_APP_KEY`。冇就拋錯 —— 唔會用 `BETFAIR_APP_KEY`（delayed）頂替。"""
    key = os.environ.get(LIVE_KEY_ENV, "").strip()
    if not key:
        raise bf.BetfairError(f"{LIVE_KEY_ENV} 未設定 —— 落注 client 唔會用 delayed key 頂替")
    return key


def trading_rpc(method: str, params: dict, *, retry_login: bool = True) -> object:
    if method in FORBIDDEN or method not in ALLOWED:
        raise bf.BetfairError(f"{method} 唔准：落注 client 只准 {sorted(ALLOWED)}")
    if method in WRITE:
        # 防線：上層漏咗都好，呢度再查一次四重開關。
        import betfair_betting as bb  # noqa: PLC0415 —— 避免循環 import

        sw = bb.switches()
        if not sw["all_on"]:
            raise bf.BetfairError(f"{method} 拒絕：開關未全開（{'; '.join(sw['blocking'])}）")
    key = live_app_key()
    if method in ACCOUNT_READ:
        url, api = ACCOUNT_URL, "AccountAPING"
    else:
        url, api = bf.BETTING_URL, "SportsAPING"
    payload = json.dumps({"jsonrpc": "2.0", "method": f"{api}/v1.0/{method}", "params": params, "id": 1}).encode()
    headers = {"X-Application": key,
               "X-Authentication": bf.session_token(app_key=key, session_file=TRADING_SESSION_FILE),
               "Content-Type": "application/json", "Accept": "application/json"}
    out = bf._post(url, payload, headers)
    err = out.get("error")
    if err:
        code = ((err.get("data") or {}).get("APINGException") or {}).get("errorCode") \
            or ((err.get("data") or {}).get("AccountAPINGException") or {}).get("errorCode") or err.get("message")
        if retry_login and code in ("INVALID_SESSION_INFORMATION", "NO_SESSION") and method not in WRITE:
            try:
                TRADING_SESSION_FILE.unlink()
            except OSError:
                pass
            return trading_rpc(method, params, retry_login=False)
        raise bf.BetfairError(f"{method}: {code}")
    return out.get("result")
