"""Bind an anonymous Sportsbet SGM quote to the exact event and outcome set."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import os
import sys

from nba_availability import aware_time

QUOTE_MAX_AGE_SECONDS = 300


class QuotedCombo(list):
    def __init__(self, legs, quote):
        super().__init__(legs)
        self.quote = quote
        self.selection_rule = getattr(legs, "selection_rule", None)


def quote_legs(legs):
    markets = {"PTS": "pts", "REB": "reb", "AST": "ast", "3PM": "fg3m"}
    result = []
    for leg in legs:
        try:
            line = float(leg.get("line", leg.get("line_val")))
        except (ValueError, TypeError):
            line = None
        result.append({"player": leg.get("player"), "market": leg.get("market", markets.get(leg.get("category"))),
                       "line": line, "side": leg.get("side", "over")})
    return result


def legs_identity(legs):
    return hashlib.sha256(json.dumps(sorted(quote_legs(legs), key=lambda x: json.dumps(x, sort_keys=True)),
                                     sort_keys=True).encode()).hexdigest()


def request_identity(body):
    body = dict(body)
    body["outcomesExternalIds"] = sorted(body["outcomesExternalIds"], key=lambda row: json.dumps(row, sort_keys=True))
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def quote_valid(quote, odds, legs, *, now=None):
    from nba_daily_auto.nba_market_ledger import sgm_price_request
    normalized = quote_legs(legs)
    if (len(normalized) < 2 or any(leg['side'] != 'over' or leg['line'] is None
            or not math.isfinite(leg['line']) or leg['line'] <= 0 for leg in normalized)
            or len({json.dumps(leg, sort_keys=True) for leg in normalized}) != len(normalized)):
        return False
    body, _ = sgm_price_request(odds, normalized)
    if not isinstance(quote, dict) or body is None:
        return False
    now = now or datetime.now(timezone.utc)
    captured = aware_time(quote.get("captured_at"))
    tip = aware_time(odds.get("event_start_time"))
    price = quote.get("decimal_odds")
    expires = aware_time(quote.get("expires_at"))
    return bool(quote.get("status") == "ok" and quote.get("source") == "sportsbet_sgm_pricer"
                and isinstance(quote.get("quote_id"), str) and quote["quote_id"]
                and quote.get("request_sha256") == request_identity(body)
                and quote.get("legs_sha256") == legs_identity(legs)
                and isinstance(price, (int, float)) and not isinstance(price, bool)
                and math.isfinite(price) and price > 1
                and captured and expires and tip and now < min(tip, expires)
                and expires == captured + timedelta(seconds=QUOTE_MAX_AGE_SECONDS)
                and 0 <= (now - captured).total_seconds() < QUOTE_MAX_AGE_SECONDS)


def requote_sidecar(report_path, odds, *, post=None, now=None):
    """Renew a report's expired SGM quotes in place when the price is unchanged.

    Regenerating a report to reprice it takes 1-5 minutes, so on a 9-game slate
    the first repriced report had expired again before the release validator
    reached it (2026-10-28: FW-13 blocked the 21:00 run three times running).
    The report text is bound to the quoted price, so a fresh quote at the same
    price only needs a new quote record. Any price move or failed quote returns
    False and writes nothing; the caller must then regenerate the report.
    """
    sidecar_path = str(report_path) + ".market_legs.json"
    try:
        with open(report_path, encoding="utf-8") as source:
            report_sha = hashlib.sha256(source.read().encode()).hexdigest()
        with open(sidecar_path, encoding="utf-8") as source:
            sidecar = json.load(source)
        if sidecar.get("report_sha256") != report_sha:
            return False
        renewed = []
        for row in sidecar["combos"]:
            fresh = quote_combo(odds, row["legs"], post=post, now=now).quote
            if (fresh.get("decimal_odds") != (row.get("sgm_quote") or {}).get("decimal_odds")
                    or not quote_valid(fresh, odds, row["legs"], now=now)):
                return False
            renewed.append(fresh)
        for row, fresh in zip(sidecar["combos"], renewed):
            row["sgm_quote"] = fresh
        temporary = sidecar_path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as target:
            json.dump(sidecar, target, ensure_ascii=False)
        os.replace(temporary, sidecar_path)
        return True
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def quote_combo(odds, legs, *, post=None, now=None):
    from nba_daily_auto.nba_market_ledger import sgm_price_request, _default_sgm_post
    captured = now or datetime.now(timezone.utc)
    normalized = quote_legs(legs)
    body, status = sgm_price_request(odds, normalized)
    quote = {"status": status, "source": "sportsbet_sgm_pricer", "captured_at": captured.isoformat(),
             "expires_at": (captured + timedelta(seconds=QUOTE_MAX_AGE_SECONDS)).isoformat(),
             "decimal_odds": None, "quote_id": None, "legs_sha256": legs_identity(legs)}
    if len({json.dumps(leg, sort_keys=True) for leg in normalized}) != len(legs) or any(leg["side"] != "over" for leg in normalized):
        quote["status"] = "invalid_or_duplicate_legs"
        return QuotedCombo(legs, quote)
    tip = aware_time(odds.get("event_start_time"))
    if not tip or captured >= tip:
        quote["status"] = "event_start_unverified_or_started"
        return QuotedCombo(legs, quote)
    if body is None:
        return QuotedCombo(legs, quote)
    quote["request_sha256"] = request_identity(body)
    if post is None:
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            quote["status"] = "network_disabled_under_tests"
            return QuotedCombo(legs, quote)
        post = _default_sgm_post
    try:
        http, payload = post(body)
        value = payload.get("price") if isinstance(payload, dict) else None
        if any(isinstance(value[key], bool) for key in ("numerator", "denominator")):
            raise ValueError("boolean price")
        num, den = float(value["numerator"]), float(value["denominator"])
        price = 1 + num / den
        if http != 200 or not all(math.isfinite(x) for x in (num, den, price)) or num <= 0 or den <= 0 or not value.get("quoteId"):
            raise ValueError("invalid quote")
        quote.update(status="ok", decimal_odds=price, quote_id=str(value["quoteId"]))
    except Exception as exc:
        quote["status"] = f"quote_failed:{type(exc).__name__}"
    return QuotedCombo(legs, quote)
