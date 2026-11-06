"""Betfair Exchange API 最細 client（只用標準庫）—— EXP-20261106-02 市場走勢記錄用，**唔落注**。

登入資料由 `~/.wongchoi_betfair.env`（repo 外，用戶自己寫，chmod 600）經環境變數提供：

    BETFAIR_APP_KEY=...        # delayed key 就夠（免費；冇成交量、價延遲 1–180 秒）
    BETFAIR_USERNAME=...
    BETFAIR_PASSWORD=...       # 或者用證書登入（下面兩行），就唔使密碼
    BETFAIR_CERT_FILE=~/.betfair/client-2048.crt
    BETFAIR_KEY_FILE=~/.betfair/client-2048.key

⚠️ 呢個 module **永遠唔會**將密碼、session token 寫入 log、例外訊息或者輸出；錯誤只報 HTTP 狀態同 Betfair 錯誤碼。
Session token 快取喺 `~/.wongchoi_betfair_session.json`（chmod 600），過期自動重新登入。
冇任何落注 method（placeOrders 等）—— 呢度只讀市場。
"""
from __future__ import annotations

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

LOGIN_URL = os.environ.get("BETFAIR_LOGIN_URL", "https://identitysso.betfair.com.au/api/login")
CERT_LOGIN_URL = os.environ.get("BETFAIR_CERT_LOGIN_URL", "https://identitysso-cert.betfair.com.au/api/certlogin")
KEEPALIVE_URL = os.environ.get("BETFAIR_KEEPALIVE_URL", "https://identitysso.betfair.com.au/api/keepAlive")
BETTING_URL = os.environ.get("BETFAIR_BETTING_URL", "https://api.betfair.com/exchange/betting/json-rpc/v1")
SESSION_FILE = Path(os.environ.get("BETFAIR_SESSION_FILE", str(Path.home() / ".wongchoi_betfair_session.json")))
SESSION_MAX_AGE_S = 4 * 3600          # Betfair AU session 預設 4 小時冇活動就過期；我哋 3.5 小時就 keepAlive
READ_ONLY_METHODS = frozenset({"listMarketCatalogue", "listMarketBook", "listEventTypes", "listEvents"})


class BetfairError(RuntimeError):
    """只帶安全資訊（method、HTTP 狀態、Betfair 錯誤碼），唔帶 credential。"""


def _app_key() -> str:
    key = os.environ.get("BETFAIR_APP_KEY", "").strip()
    if not key:
        raise BetfairError("BETFAIR_APP_KEY 未設定（~/.wongchoi_betfair.env）")
    return key


def _post(url: str, data: bytes, headers: dict, context: ssl.SSLContext | None = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=context) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise BetfairError(f"HTTP {exc.code} @ {urllib.parse.urlparse(url).path}") from None
    except urllib.error.URLError as exc:
        raise BetfairError(f"network error @ {urllib.parse.urlparse(url).path}: {type(exc.reason).__name__}") from None


def _save_session(token: str) -> None:
    SESSION_FILE.write_text(json.dumps({"token": token, "at": time.time()}))
    os.chmod(SESSION_FILE, 0o600)


def login() -> str:
    """→ session token。有證書就用證書登入，否則用戶名＋密碼。"""
    user = os.environ.get("BETFAIR_USERNAME", "").strip()
    password = os.environ.get("BETFAIR_PASSWORD", "")
    if not user or not password:
        raise BetfairError("BETFAIR_USERNAME／BETFAIR_PASSWORD 未設定（~/.wongchoi_betfair.env）")
    body = urllib.parse.urlencode({"username": user, "password": password}).encode()
    headers = {"X-Application": _app_key(), "Accept": "application/json",
               "Content-Type": "application/x-www-form-urlencoded"}
    cert, key = os.environ.get("BETFAIR_CERT_FILE"), os.environ.get("BETFAIR_KEY_FILE")
    if cert and key:
        ctx = ssl.create_default_context()
        ctx.load_cert_chain(os.path.expanduser(cert), os.path.expanduser(key))
        out = _post(CERT_LOGIN_URL, body, headers, context=ctx)
        token, status = out.get("sessionToken"), out.get("loginStatus")
    else:
        out = _post(LOGIN_URL, body, headers)
        token, status = out.get("token"), out.get("status")
    if not token or status not in ("SUCCESS", None):
        raise BetfairError(f"login failed: {status or out.get('error') or 'unknown'}")
    _save_session(token)
    return token


def session_token() -> str:
    try:
        cached = json.loads(SESSION_FILE.read_text())
    except (OSError, ValueError):
        return login()
    age = time.time() - float(cached.get("at") or 0)
    if age < 3.5 * 3600:
        return cached["token"]
    if age < SESSION_MAX_AGE_S:
        try:
            out = _post(KEEPALIVE_URL, b"", {"X-Application": _app_key(), "X-Authentication": cached["token"],
                                               "Accept": "application/json"})
            if out.get("status") == "SUCCESS":
                _save_session(cached["token"])
                return cached["token"]
        except BetfairError:
            pass
    return login()


def rpc(method: str, params: dict, *, retry_login: bool = True) -> object:
    """JSON-RPC 呼叫（只准 READ_ONLY_METHODS）。"""
    if method not in READ_ONLY_METHODS:
        raise BetfairError(f"{method} 唔准：呢個 client 只讀市場，唔落注")
    payload = json.dumps({"jsonrpc": "2.0", "method": f"SportsAPING/v1.0/{method}", "params": params, "id": 1}).encode()
    headers = {"X-Application": _app_key(), "X-Authentication": session_token(),
               "Content-Type": "application/json", "Accept": "application/json"}
    out = _post(BETTING_URL, payload, headers)
    err = out.get("error")
    if err:
        code = ((err.get("data") or {}).get("APINGException") or {}).get("errorCode") or err.get("message")
        if retry_login and code in ("INVALID_SESSION_INFORMATION", "NO_SESSION"):
            try:
                SESSION_FILE.unlink()
            except OSError:
                pass
            return rpc(method, params, retry_login=False)
        raise BetfairError(f"{method}: {code}")
    return out.get("result")
