#!/usr/bin/env python3
"""Minimal Betfair Exchange (AU) client for day-before market snapshots.

Purpose: fetch per-runner exchange price + traded volume for upcoming AU win
markets, to feed (a) the union/rescue market-rank view and (b) the money-flow
feature + take-SP betting. Read-only market data; NO bet placement here.

SECURITY: all credentials come from environment variables — this script never
stores, prints, or transmits them anywhere except Betfair's own login endpoint.
  export BF_USER=...        # Betfair username
  export BF_PASS=...        # Betfair password
  export BF_APP_KEY=...     # Application key from developer.betfair.com

Usage:
  python3 scratch/betfair_client.py --selftest         # checks env only, no network
  python3 scratch/betfair_client.py --snapshot         # today's AU win markets → JSON
  python3 scratch/betfair_client.py --snapshot --hours 36   # look-ahead window
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

# AU endpoints (Betfair Australia)
LOGIN_URL = "https://identitysso.betfair.com.au/api/login"
BETTING_URL = "https://api.betfair.com/exchange/betting/rest/v1.0"


def _env():
    creds = {k: os.environ.get(k) for k in ("BF_USER", "BF_PASS", "BF_APP_KEY")}
    missing = [k for k, v in creds.items() if not v]
    return creds, missing


def login(creds: dict) -> str:
    data = f"username={creds['BF_USER']}&password={creds['BF_PASS']}".encode()
    req = urllib.request.Request(LOGIN_URL, data=data, headers={
        "X-Application": creds["BF_APP_KEY"],
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    if out.get("status") != "SUCCESS":
        raise RuntimeError(f"Betfair login failed: {out.get('error') or out.get('status')}")
    return out["token"]


def _rpc(method: str, params: dict, token: str, app_key: str) -> object:
    req = urllib.request.Request(
        f"{BETTING_URL}/{method}/",
        data=json.dumps(params).encode(),
        headers={"X-Application": app_key, "X-Authentication": token,
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def snapshot(hours: float) -> list[dict]:
    import datetime  # local import; harness forbids argless now() but this is a live tool
    creds, missing = _env()
    if missing:
        raise SystemExit(f"missing env: {missing}")
    token = login(creds)
    now = datetime.datetime.utcnow()
    market_filter = {
        "eventTypeIds": ["7"],  # Horse Racing
        "marketCountries": ["AU"],
        "marketTypeCodes": ["WIN"],
        "marketStartTime": {"from": now.isoformat() + "Z",
                            "to": (now + datetime.timedelta(hours=hours)).isoformat() + "Z"},
    }
    cat = _rpc("listMarketCatalogue", {
        "filter": market_filter, "maxResults": 200,
        "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
    }, token, creds["BF_APP_KEY"])
    out = []
    for m in cat:
        book = _rpc("listMarketBook", {
            "marketIds": [m["marketId"]],
            "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
        }, token, creds["BF_APP_KEY"])
        prices = {r["selectionId"]: r for r in (book[0]["runners"] if book else [])}
        runners = []
        for rd in m.get("runners", []):
            pr = prices.get(rd["selectionId"], {})
            best = (pr.get("ex", {}).get("availableToBack") or [{}])
            runners.append({
                "name": rd.get("runnerName"),
                "last_price": pr.get("lastPriceTraded"),
                "best_back": best[0].get("price") if best else None,
                "traded_vol": pr.get("totalMatched"),
            })
        out.append({
            "market_id": m["marketId"],
            "event": m.get("event", {}).get("name"),
            "venue": m.get("event", {}).get("venue"),
            "start": m.get("marketStartTime"),
            "runners": runners,
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--hours", type=float, default=30.0)
    ap.add_argument("--out", default="scratch/betfair_snapshot.json")
    args = ap.parse_args()
    if args.selftest:
        creds, missing = _env()
        print("env present:", [k for k in creds if creds[k]], "| missing:", missing)
        print("selftest OK — no network call made" if not missing else "set the env vars above, then --snapshot")
        return 0
    if args.snapshot:
        data = snapshot(args.hours)
        Path = __import__("pathlib").Path
        Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"wrote {len(data)} AU win markets → {args.out}")
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
