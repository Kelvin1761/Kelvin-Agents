#!/usr/bin/env python3
"""Forward-only NBA model-vs-market evaluation ledger.

Infrastructure only: this module observes prices and probabilities that the
pipeline already produced.  It never changes a projection, pick or SGM.

Layout (append-only JSONL, one file per Sydney analysis date)::

    <root>/ledger/<YYYY-MM-DD>.jsonl
    <root>/reports/evaluation_latest.json

``<root>`` is ``$WONGCHOI_NBA_MARKET_LEDGER_ROOT`` or
``~/WongChoiData/NBA_Market_Eval`` (local disk; launchd cannot read Drive).

Row types
---------
``price_obs``      one Sportsbet price for one milestone leg at one capture time
``model_obs``      every evaluated leg's model probabilities in one snapshot
``sgm_obs``        every rendered combo in one snapshot, with the N1 shadow
                   joint probability (one simulated game, shared pace /
                   margin-blowout / team-scoring / player-role factors)
``model_missing``  a snapshot that had no market-eval sidecar for a game
``settlement``     box-score outcome for one leg (first write wins)
``sgm_price_obs``  Sportsbet's own SGM price for one published combo at one
                   quote time (public multi-pricer, no login)
``no_prediction``  a date (``game_tag`` null) or game written off as "no
                   prediction" (no snapshot frozen pre-tip; see
                   ``nba_no_prediction``).  Every other row for that date/game
                   is excluded from settlement and evaluation.

Point-in-time rules
-------------------
* ``captured_at`` is when Sportsbet was read; ``recorded_at`` is when the row
  was written.  ``post_tip`` = captured at/after tip-off; ``late_write`` =
  written at/after tip-off.  Both are excluded from every pre-tip metric and
  never silently mixed.  A missed pre-tip capture is reported as missed; this
  module has no backfill path (running it late only produces ``late_write``
  rows).
* "close" is the latest *observed* pre-tip capture.  The scheduler scrapes at
  19:00 / 21:00 / 21:45 / 06:30 Sydney, i.e. hours before tip, so it is not the true
  closing line.

Market probability
------------------
Every evaluated leg is a Sportsbet milestone ("X+").  Milestone ladders are
one-sided (player names only, no Under), so a milestone price can never be
de-vigged per line; its comparator is the raw ``1/price`` (vig-inclusive),
which overstates the hit probability and *flatters the model*.

Sportsbet also prices "{Player} - Points" Over/Under at X.5 on both sides.
Over X.5 is the same event as milestone X+0.5, so the extractor's
``player_props_two_way`` block is recorded as ``price_source="ou_two_way"``
price rows on the equivalent milestone line, with ``complement_price`` = the
Under.  ``market_devig_close`` uses the latest pre-tip two-way pair with
``devig_two_way_proportional`` (tennis X1 found proportional best for two-way
markets).  Raw close and CLV keep using the milestone price only, so the two
price sources are never mixed.  De-vig coverage is therefore limited to legs
whose milestone line matches the player's O/U line.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
from zoneinfo import ZoneInfo


SCHEMA = "nba-market-ledger/v1"
ENV_ROOT = "WONGCHOI_NBA_MARKET_LEDGER_ROOT"
SIDECAR_SUFFIX = ".market_legs.json"
SYDNEY = ZoneInfo("Australia/Sydney")
HERE = Path(__file__).resolve().parent
NBA_SKILL = HERE.parent

MARKET_KEYS = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes_made": "fg3m"}
MODEL_VARIANTS = ("p_final", "p_hit_rate_10f", "p_ml", "p_monte_carlo")
ROLE_PRIORITY = {"final_refresh": 3, "production": 2, "warmup": 1}

# Power estimate defaults.  The mean is an ASSUMPTION, never the observed mean:
# solving n from an observed mean is circular (it is exactly the quantity whose
# existence is in question).
ASSUMED_BRIER_IMPROVEMENT = 0.002
ASSUMED_PAIRED_SD = 0.05
POWER_Z = 1.96


class LedgerIsolationError(RuntimeError):
    """Raised when a test run would otherwise write the production ledger."""


# ── paths / io ──────────────────────────────────────────────────────────────

def ledger_root() -> Path:
    override = os.environ.get(ENV_ROOT, "").strip()
    if override:
        return Path(override).expanduser()
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        # Default defence: a test that forgot to isolate must never reach the
        # real ledger (tennis once wrote its production ledger from a test).
        raise LedgerIsolationError(f"{ENV_ROOT} must be set under tests")
    return Path.home() / "WongChoiData" / "NBA_Market_Eval"


def ledger_path(root: Path, target_date: str) -> Path:
    date.fromisoformat(target_date)
    return root / "ledger" / f"{target_date}.jsonl"


def _aware(value: Any, *, naive_tz: ZoneInfo | None = None) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        if naive_tz is None:
            return None
        parsed = parsed.replace(tzinfo=naive_tz)
    return parsed


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat() if value else None


def read_rows(root: Path, target_date: str) -> list[dict]:
    path = ledger_path(root, target_date)
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _row_key(row: Mapping[str, Any]) -> tuple:
    kind = row.get("row_type")
    leg = (row.get("game_tag"), row.get("player"), row.get("market"), row.get("line"), row.get("side"))
    if kind == "price_obs":
        if row.get("price_source") == "ou_two_way":
            return (kind, *leg, row.get("captured_at"), row.get("price"),
                    "ou_two_way", row.get("complement_price"))
        return (kind, *leg, row.get("captured_at"), row.get("price"))
    if kind == "model_obs":
        return (kind, row.get("snapshot_id"), *leg)
    if kind == "sgm_obs":
        return (kind, row.get("snapshot_id"), row.get("game_tag"), row.get("combo_id"))
    if kind in {"banker_shadow_obs", "selection_obs"}:
        return (kind, row.get("snapshot_id"), row.get("game_tag"), row.get("arm"))
    if kind == "model_missing":
        return (kind, row.get("snapshot_id"), row.get("game_tag"))
    if kind == "settlement":
        return (kind, *leg)
    if kind == "sgm_price_obs":
        return (kind, row.get("snapshot_id"), row.get("game_tag"), row.get("combo_id"),
                row.get("captured_at"))
    if kind == "no_prediction":
        return (kind, row.get("game_tag"))
    return (kind, json.dumps(row, sort_keys=True))


def append_rows(root: Path, target_date: str, rows: Iterable[dict]) -> int:
    """Append rows not already present (idempotent).  Never rewrites a line."""
    path = ledger_path(root, target_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(".lock")
    with lock_path.open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        seen = {_row_key(row) for row in read_rows(root, target_date)}
        fresh = []
        for row in rows:
            key = _row_key(row)
            if key in seen:
                continue
            seen.add(key)
            fresh.append(row)
        if fresh:
            with path.open("a", encoding="utf-8") as handle:
                for row in fresh:
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
    return len(fresh)


# ── recording ───────────────────────────────────────────────────────────────

def _tag_for(odds_path: Path) -> str:
    sys.path.insert(0, str(NBA_SKILL))
    from nba_schedule import canonical_game_tag

    return canonical_game_tag(odds_path.stem.removeprefix("Sportsbet_Odds_"))


def _tip(tag: str, odds: Mapping[str, Any], event_starts: Mapping[str, datetime] | None) -> tuple[datetime | None, str]:
    if event_starts and tag in event_starts:
        start = _aware(event_starts[tag])
        if start:
            return start, "official_schedule"
    start = _aware(odds.get("event_start_time"))
    return (start, "sportsbet_event_start") if start else (None, "unknown")


def _flags(tip: datetime | None, captured: datetime | None, recorded: datetime) -> dict:
    return {
        "tip_off": _iso(tip),
        "tip_unknown": tip is None,
        "post_tip": bool(tip and captured and captured >= tip),
        "late_write": bool(tip and recorded >= tip),
    }


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def price_rows_from_odds(
    odds_path: Path,
    target_date: str,
    *,
    event_starts: Mapping[str, datetime] | None,
    recorded_at: datetime,
    context: str,
    season_phase: str | None = None,
) -> list[dict]:
    raw = odds_path.read_bytes()
    odds = json.loads(raw)
    if not isinstance(odds, dict) or odds.get("target_analysis_date") != target_date:
        return []
    tag = _tag_for(odds_path)
    tip, tip_source = _tip(tag, odds, event_starts)
    # The extractor writes a naive local wall-clock time; the scheduler host
    # runs on Sydney time.  Fall back to the file mtime when it is absent.
    captured = _aware(odds.get("extraction_time"), naive_tz=SYDNEY)
    capture_source = "extraction_time"
    if captured is None:
        captured = datetime.fromtimestamp(odds_path.stat().st_mtime, tz=timezone.utc)
        capture_source = "file_mtime"
    sha = hashlib.sha256(raw).hexdigest()
    rows = []
    for category, players in (odds.get("player_props") or {}).items():
        market = MARKET_KEYS.get(category)
        if not market or not isinstance(players, dict):
            continue
        for player, payload in players.items():
            for line, price in ((payload or {}).get("lines") or {}).items():
                line_value, price_value = _float(line), _float(price)
                if line_value is None or price_value is None or price_value <= 1.0:
                    continue
                if not line_value.is_integer():
                    continue  # only milestone "X+" legs are evaluated
                rows.append({
                    "row_type": "price_obs", "schema": SCHEMA, "target_date": target_date,
                    "game_tag": tag, "player": player, "market": market,
                    "line": line_value, "side": "over", "price": price_value,
                    "complement_price": None,
                    "captured_at": _iso(captured), "capture_source": capture_source,
                    "recorded_at": _iso(recorded_at), "tip_source": tip_source,
                    "sportsbet_event_id": odds.get("sportsbet_event_id"),
                    "source_sha256": sha, "context": context,
                    "season_phase": season_phase,
                    "price_source": "milestone_one_sided",
                    **_flags(tip, captured, recorded_at),
                })
    for category, players in (odds.get("player_props_two_way") or {}).items():
        market = MARKET_KEYS.get(category)
        if not market or not isinstance(players, dict):
            continue
        for player, lines in players.items():
            for line, pair in (lines or {}).items():
                ou_line = _float(line)
                over = _float((pair or {}).get("over"))
                under = _float((pair or {}).get("under"))
                if ou_line is None or over is None or under is None:
                    continue
                if over <= 1.0 or under <= 1.0 or (ou_line - 0.5) != int(ou_line - 0.5):
                    continue
                rows.append({
                    "row_type": "price_obs", "schema": SCHEMA, "target_date": target_date,
                    "game_tag": tag, "player": player, "market": market,
                    # Over 24.5 == milestone 25+ for integer box-score stats.
                    "line": ou_line + 0.5, "side": "over", "price": over,
                    "complement_price": under, "ou_line": ou_line,
                    "captured_at": _iso(captured), "capture_source": capture_source,
                    "recorded_at": _iso(recorded_at), "tip_source": tip_source,
                    "sportsbet_event_id": odds.get("sportsbet_event_id"),
                    "source_sha256": sha, "context": context,
                    "season_phase": season_phase,
                    "price_source": "ou_two_way",
                    **_flags(tip, captured, recorded_at),
                })
    return rows


def _season_phase(target_date: str) -> str | None:
    try:
        sys.path.insert(0, str(NBA_SKILL))
        from nba_season import classify_nba_season

        return classify_nba_season(target_date).get("season_phase")
    except Exception:  # noqa: BLE001
        return None


def record_prices(
    folder: Path,
    target_date: str,
    *,
    event_starts: Mapping[str, datetime] | None = None,
    context: str,
    now: datetime | None = None,
    root: Path | None = None,
) -> int:
    root = root or ledger_root()
    now = now or datetime.now(timezone.utc)
    phase = _season_phase(target_date)
    rows: list[dict] = []
    for path in sorted(Path(folder).glob("Sportsbet_Odds_*.json")):
        try:
            rows.extend(price_rows_from_odds(
                path, target_date, event_starts=event_starts, recorded_at=now,
                context=context, season_phase=phase,
            ))
        except (OSError, ValueError):
            continue
    return append_rows(root, target_date, rows)


def record_snapshot(
    snapshot: Path,
    target_date: str,
    *,
    event_starts: Mapping[str, datetime] | None = None,
    now: datetime | None = None,
    root: Path | None = None,
) -> dict:
    """Record prices, model probabilities and combos from one immutable snapshot."""
    root = root or ledger_root()
    now = now or datetime.now(timezone.utc)
    snapshot = Path(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    role = manifest.get("snapshot_role")
    snapshot_id = snapshot.name
    phase = (manifest.get("season_context") or {}).get("season_phase") or _season_phase(target_date)
    rows: list[dict] = []
    counts = {"price_obs": 0, "model_obs": 0, "sgm_obs": 0, "model_missing": 0}
    for odds_path in sorted(snapshot.glob("Sportsbet_Odds_*.json")):
        try:
            odds = json.loads(odds_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if odds.get("target_analysis_date") != target_date:
            continue
        tag = _tag_for(odds_path)
        tip, tip_source = _tip(tag, odds, event_starts)
        rows.extend(price_rows_from_odds(
            odds_path, target_date, event_starts=event_starts, recorded_at=now,
            context=f"snapshot:{role}", season_phase=phase,
        ))
        report = snapshot / f"Game_{tag}_Full_Analysis.md"
        sidecar = snapshot / f"Game_{tag}_Full_Analysis.md{SIDECAR_SUFFIX}"
        base = {
            "schema": SCHEMA, "target_date": target_date, "game_tag": tag,
            "snapshot_id": snapshot_id, "snapshot_role": role,
            "snapshot_created_at": manifest.get("created_at"),
            "model_commit": manifest.get("model_commit"),
            "recorded_at": _iso(now), "tip_source": tip_source, "season_phase": phase,
        }
        reason = None
        payload: dict = {}
        if not sidecar.is_file():
            reason = "sidecar_absent"
        else:
            try:
                payload = json.loads(sidecar.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                reason = "sidecar_unreadable"
            else:
                report_sha = hashlib.sha256(report.read_bytes()).hexdigest() if report.is_file() else None
                if payload.get("report_sha256") != report_sha:
                    reason = "sidecar_report_mismatch"
        if reason:
            rows.append({"row_type": "model_missing", "reason": reason, **base,
                         **_flags(tip, None, now)})
            continue
        model_captured = _aware(payload.get("odds_extraction_time"), naive_tz=SYDNEY)
        flags = _flags(tip, model_captured, now)
        if payload.get("selection_diagnostics"):
            rows.append({"row_type": "selection_obs", **base, **flags,
                         "strategy_profile": payload.get("strategy_profile"),
                         "diagnostics": payload["selection_diagnostics"],
                         "snapshot_completeness": manifest.get("completeness"),
                         "banker_formal": any(str(c.get("combo_id")) == "1" for c in payload.get("combos", []))})
        for experiment in payload.get("banker_shadow") or []:
            if experiment.get("version") != "banker-ev-shadow-v1" or experiment.get("arm") not in {"B0", "B1", "B2"}:
                continue
            sys.path.insert(0, str(NBA_SKILL))
            from nba_sgm_quote import quote_valid
            quote = experiment.get("sgm_quote") or {}
            captured = _aware(quote.get("captured_at"))
            legs = experiment.get("legs") or []
            verified = bool(captured and captured <= now and quote_valid(quote, odds, legs, now=captured))
            identities = {leg.get("probability_model_id") for leg in payload.get("legs", [])}
            identity = next(iter(identities)) if len(identities) == 1 else None
            price = _float(experiment.get("sportsbet_sgm_price"))
            rows.append({**experiment, **base, **_flags(tip, captured, now),
                         "row_type": "banker_shadow_obs", "analysis_only": True, "decision": "OBSERVE",
                         "odds_captured_at": _iso(captured), "probability_model_id": identity,
                         "eligible": bool(experiment.get("eligible") and verified and identity
                                          and 2 <= len(legs) <= 4
                                          and price == _float(quote.get("decimal_odds")) and price >= 2.0),
                         "sportsbet_sgm_status": "ok" if verified else "unverified"})
        for leg in payload.get("legs") or []:
            line = _float(leg.get("line"))
            price = _float(leg.get("price"))
            if line is None or price is None:
                continue
            rows.append({
                "row_type": "model_obs", **base, **flags,
                "player": leg.get("player"), "team": leg.get("team"),
                "market": leg.get("market"), "line": line, "side": leg.get("side") or "over",
                "price_at_model": price, "odds_captured_at": _iso(model_captured),
                **{name: _float(leg.get(name)) for name in (*MODEL_VARIANTS, "p_l10_base_rate")},
                "engine": leg.get("engine"),
                "mc_model_version": leg.get("mc_model_version"),
                "probability_model_id": leg.get("probability_model_id"),
                # SHADOW fit layer: recorded for forward evidence, deliberately
                # not in MODEL_VARIANTS so evaluate() is untouched.
                "shadow_fit_prob_A": _float(leg.get("shadow_fit_prob_A")),
                "shadow_fit_version": leg.get("shadow_fit_version"),
                "shadow_fit_status": leg.get("shadow_fit_status"),
                "shadow_fit_inputs": leg.get("shadow_fit_inputs"),
                "picked": bool(leg.get("picked")), "picked_in": leg.get("picked_in") or [],
            })
        for combo in payload.get("combos") or []:
            rows.append({
                "row_type": "sgm_obs", **base, **flags,
                "odds_captured_at": _iso(model_captured),
                "combo_id": str(combo.get("combo_id")),
                "legs": combo.get("legs") or [],
                "product_of_leg_prices": _float(combo.get("product_of_leg_prices")),
                "naive_joint_prob": _float(combo.get("naive_joint_prob")),
                "adjusted_joint_prob": _float(combo.get("adjusted_joint_prob")),
                "correlation_penalty": _float(combo.get("correlation_penalty")),
                "sportsbet_sgm_price": _float(combo.get("sportsbet_sgm_price")),
                "sportsbet_sgm_status": combo.get("sportsbet_sgm_status") or "not_scraped",
                "sgm_quote": combo.get("sgm_quote"),
                # N1 shadow: same-simulation joint probability (never used to pick).
                "sim_status": combo.get("sim_status") or "absent",
                "sim_model_version": combo.get("sim_model_version"),
                "sim_seed": combo.get("sim_seed"),
                "sim_n": combo.get("sim_n"),
                "sim_joint_prob": _float(combo.get("sim_joint_prob")),
                "sim_independent_prob": _float(combo.get("sim_independent_prob")),
                "sim_correlation_lift": _float(combo.get("sim_correlation_lift")),
                "sim_scaled_joint_prob": _float(combo.get("sim_scaled_joint_prob")),
            })
    for row in rows:
        counts[row["row_type"]] = counts.get(row["row_type"], 0) + 1
    counts["appended"] = append_rows(root, target_date, rows)
    return counts


# ── Sportsbet SGM price capture ─────────────────────────────────────────────

# The same endpoint sportsbet.com.au's own bet slip calls to price a Same Game
# Multi; it answers anonymous POSTs (verified 2026-10-14).  Only the combos
# already rendered in a snapshot are priced; nothing is placed or bet.
SGM_PRICER_URL = "https://www.sportsbet.com.au/apigw/multi-pricer/combinations/price"
_MARKET_TO_CATEGORY = {market: category for category, market in MARKET_KEYS.items()}


def _line_key(line: float) -> str:
    return f"{line:g}"


def sgm_price_request(odds: Mapping[str, Any], legs: list[dict]) -> tuple[dict | None, str]:
    """Build the multi-pricer body for one combo, or (None, reason)."""
    pricing = odds.get("sgm_pricing") or {}
    event = {
        "classExternalId": pricing.get("class_external_id"),
        "competitionExternalId": pricing.get("competition_external_id"),
        "eventExternalId": pricing.get("event_external_id"),
    }
    if not all(event.values()):
        return None, "event_ids_missing"
    if len(legs) < 2:
        return None, "single_leg"
    outcomes = []
    for leg in legs:
        category = _MARKET_TO_CATEGORY.get(leg.get("market"))
        line = _float(leg.get("line"))
        ids = (((pricing.get("outcomes") or {}).get(category) or {}).get(leg.get("player")) or {}).get(
            _line_key(line) if line is not None else "")
        if not ids:
            return None, "leg_ids_missing"
        outcomes.append({"marketExternalId": ids["market_external_id"],
                         "outcomeExternalId": ids["outcome_external_id"]})
    return {**event, "outcomesExternalIds": outcomes}, "ok"


def _default_sgm_post(body: dict) -> tuple[int, Any]:
    from curl_cffi import requests  # same TLS impersonation as the extractor

    session = requests.Session(impersonate="chrome120")
    response = session.post(
        SGM_PRICER_URL, json=body, timeout=15,
        headers={"Content-Type": "application/json", "Accept": "application/json",
                 "Origin": "https://www.sportsbet.com.au", "Referer": "https://www.sportsbet.com.au/"},
    )
    try:
        payload = response.json()
    except ValueError:
        payload = None
    return response.status_code, payload


def record_sgm_prices(
    snapshot: Path,
    target_date: str,
    *,
    event_starts: Mapping[str, datetime] | None = None,
    now: datetime | None = None,
    root: Path | None = None,
    post=None,
) -> dict:
    """Quote Sportsbet's SGM price for every combo rendered in ``snapshot``.

    Observation only: the combos are already chosen; a quote never changes
    them.  Every attempt is a row (ok or why not), so missing prices are
    visible instead of silently absent.
    """
    root = root or ledger_root()  # isolation check happens before any request
    if post is None:
        if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
            raise LedgerIsolationError("network SGM pricing is disabled under tests")
        post = _default_sgm_post
    snapshot = Path(snapshot)
    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    counts: dict[str, int] = defaultdict(int)
    for odds_path in sorted(snapshot.glob("Sportsbet_Odds_*.json")):
        try:
            odds = json.loads(odds_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if odds.get("target_analysis_date") != target_date:
            continue
        tag = _tag_for(odds_path)
        sidecar = snapshot / f"Game_{tag}_Full_Analysis.md{SIDECAR_SUFFIX}"
        try:
            combos = json.loads(sidecar.read_text(encoding="utf-8")).get("combos") or []
        except (OSError, ValueError):
            continue
        tip, tip_source = _tip(tag, odds, event_starts)
        for combo in combos:
            captured = now or datetime.now(timezone.utc)
            body, status = sgm_price_request(odds, combo.get("legs") or [])
            price = quote_id = None
            http_status = None
            if body is not None:
                try:
                    http_status, payload = post(body)
                except Exception as exc:  # noqa: BLE001
                    status = f"request_failed:{type(exc).__name__}"
                else:
                    quoted = (payload or {}).get("price") if isinstance(payload, dict) else None
                    num = _float((quoted or {}).get("numerator"))
                    den = _float((quoted or {}).get("denominator"))
                    if http_status == 200 and num is not None and den:
                        price = round(1 + num / den, 4)
                        quote_id = quoted.get("quoteId")
                        status = "ok"
                    else:
                        status = f"http_{http_status}"
            counts[status] += 1
            rows.append({
                "row_type": "sgm_price_obs", "schema": SCHEMA, "target_date": target_date,
                "game_tag": tag, "snapshot_id": snapshot.name,
                "snapshot_role": manifest.get("snapshot_role"),
                "combo_id": str(combo.get("combo_id")), "legs": len(combo.get("legs") or []),
                "status": status, "http_status": http_status,
                "sportsbet_sgm_price": price, "quote_id": quote_id,
                "product_of_leg_prices": _float(combo.get("product_of_leg_prices")),
                "captured_at": _iso(captured), "recorded_at": _iso(captured),
                "tip_source": tip_source,
                **_flags(tip, captured, captured),
            })
    return {**dict(counts), "appended": append_rows(root, target_date, rows)}


# ── settlement ──────────────────────────────────────────────────────────────

def _match_game(tag: str, games: list[dict]) -> dict | None:
    sys.path.insert(0, str(NBA_SKILL))
    from nba_schedule import canonical_team_abbr

    away, _, home = tag.partition("_")
    for game in games:
        if (
            canonical_team_abbr((game.get("away") or {}).get("team")) == canonical_team_abbr(away)
            and canonical_team_abbr((game.get("home") or {}).get("team")) == canonical_team_abbr(home)
        ):
            return game
    return None


def record_no_prediction(
    target_date: str,
    *,
    game_tags: Iterable[str] | None,
    reason: str,
    marked_by: str,
    marked_at: str,
    now: datetime | None = None,
    root: Path | None = None,
) -> int:
    """Append the exclusion row(s) for a no-prediction date or games (idempotent)."""
    root = root or ledger_root()
    now = now or datetime.now(timezone.utc)
    base = {
        "row_type": "no_prediction", "schema": SCHEMA, "target_date": target_date,
        "reason": reason, "marked_by": marked_by, "marked_at": marked_at,
        "recorded_at": _iso(now),
    }
    tags = sorted(set(game_tags)) if game_tags else [None]
    return append_rows(root, target_date, [{**base, "game_tag": tag} for tag in tags])


def no_prediction_exclusions(rows: Iterable[Mapping[str, Any]]) -> set[tuple]:
    """``(date, None)`` for a whole date, ``(date, tag)`` for one game."""
    return {
        (row.get("target_date"), row.get("game_tag"))
        for row in rows
        if row.get("row_type") == "no_prediction"
    }


def _excluded(row: Mapping[str, Any], exclusions: set[tuple]) -> bool:
    day = row.get("target_date")
    return (day, None) in exclusions or (day, row.get("game_tag")) in exclusions


def settle(
    target_date: str,
    results_path: Path,
    *,
    now: datetime | None = None,
    root: Path | None = None,
) -> dict:
    """Settle every leg the ledger knows about from the reflector's box scores."""
    sys.path.insert(0, str(NBA_SKILL))
    from nba_reflector.scripts.verify_props_hits import verify_legs

    root = root or ledger_root()
    now = now or datetime.now(timezone.utc)
    raw = Path(results_path).read_bytes()
    brief = json.loads(raw)
    if brief.get("_version") != "RESULTS_BRIEF_V1":
        raise ValueError("unsupported NBA results brief")
    rows = read_rows(root, target_date)
    exclusions = no_prediction_exclusions(rows)
    if (target_date, None) in exclusions:
        return {"status": "no_prediction", "candidates": 0, "appended": 0}
    settled = {_row_key(row)[1:] for row in rows if row.get("row_type") == "settlement"}
    wanted: dict[tuple, dict] = {}
    for row in rows:
        if _excluded(row, exclusions):
            continue
        if row.get("row_type") == "model_obs":
            legs = [row]
        elif row.get("row_type") == "sgm_obs":
            legs = [{**leg, "game_tag": row.get("game_tag")} for leg in row.get("legs") or []]
        else:
            continue
        for leg in legs:
            if leg.get("market") not in MARKET_KEYS.values() or _float(leg.get("line")) is None:
                continue
            key = (row.get("game_tag"), leg.get("player"), leg.get("market"), float(leg["line"]), leg.get("side") or "over")
            if key not in settled:
                wanted[key] = leg
    games = brief.get("games") or []
    sha = hashlib.sha256(raw).hexdigest()
    out = []
    for key, _leg in sorted(wanted.items(), key=lambda item: tuple(str(v) for v in item[0])):
        tag, player, market, line, side = key
        game = _match_game(tag, games)
        if game is None:
            continue  # game not in this brief yet; retry on a later run
        status = str(game.get("status") or "").strip().lower()
        # Results_Brief uses Final, Final/OT, or Final (<verified source>).
        # Missing status and arbitrary text containing "final" are not proof.
        if not re.fullmatch(r"final(?:/\d*ot|\s+\([^()]+\))?", status):
            continue
        verified = verify_legs([{"player": player, "stat": market, "line": line}], game)[0]
        cleared = verified.get("cleared")
        outcome = (
            "void" if verified.get("outcome") == "void"
            else "hit" if cleared is True
            else "miss" if cleared is False
            else "unresolved"
        )
        # A missing player/stat is a retryable observation, not a settlement.
        # Appending it would occupy the immutable first-write-wins key forever.
        if outcome == "unresolved":
            continue
        out.append({
            "row_type": "settlement", "schema": SCHEMA, "target_date": target_date,
            "game_tag": tag, "player": player, "market": market, "line": line, "side": side,
            "actual": verified.get("actual"), "minutes": verified.get("minutes"),
            "outcome": outcome, "y": 1 if outcome == "hit" else 0 if outcome == "miss" else None,
            "verify_status": verified.get("status"),
            "results_path": Path(results_path).name, "results_sha256": sha,
            "settled_at": _iso(now),
        })
    return {"candidates": len(wanted), "appended": append_rows(root, target_date, out)}


# ── metrics ─────────────────────────────────────────────────────────────────

def devig_two_way_proportional(price: float, complement_price: float) -> float:
    """Proportional (multiplicative) two-way de-vig of the first selection."""
    a, b = 1.0 / price, 1.0 / complement_price
    return a / (a + b)


def required_n(sd: float, mean: float, z: float = POWER_Z) -> int:
    """n such that a z-sigma interval on the mean excludes zero: (z·sd/mean)²."""
    if mean <= 0 or sd <= 0:
        raise ValueError("power estimate needs a positive assumed mean and sd")
    return math.ceil((z * sd / mean) ** 2)


def _brier(p: list[float], y: list[int]) -> float:
    return sum((pi - yi) ** 2 for pi, yi in zip(p, y)) / len(p)


def _logloss(p: list[float], y: list[int]) -> float:
    eps = 1e-6
    total = 0.0
    for pi, yi in zip(p, y):
        q = min(1 - eps, max(eps, pi))
        total -= yi * math.log(q) + (1 - yi) * math.log(1 - q)
    return total / len(p)


def _sd(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def calibration_buckets(p: list[float], y: list[int], bins: int = 10) -> list[dict]:
    out = []
    for index in range(bins):
        low, high = index / bins, (index + 1) / bins
        members = [(pi, yi) for pi, yi in zip(p, y) if low <= pi < high or (index == bins - 1 and pi == 1.0)]
        if members:
            out.append({
                "bucket": f"{low:.1f}-{high:.1f}", "n": len(members),
                "mean_p": round(sum(m[0] for m in members) / len(members), 4),
                "hit_rate": round(sum(m[1] for m in members) / len(members), 4),
            })
    return out


def _pre_tip(row: Mapping[str, Any]) -> bool:
    return not row.get("post_tip") and not row.get("late_write") and not row.get("tip_unknown")


def _leg_key(row: Mapping[str, Any]) -> tuple:
    return (row.get("target_date"), row.get("game_tag"), row.get("player"), row.get("market"),
            row.get("line"), row.get("side") or "over")


def _choose_snapshot(rows: list[dict]) -> str | None:
    """Latest pre-tip published snapshot (final_refresh > production; warmup is unpublished)."""
    eligible = [r for r in rows if _pre_tip(r) and r.get("snapshot_role") != "warmup"]
    if not eligible:
        return None
    best = max(eligible, key=lambda r: (str(r.get("snapshot_created_at") or ""),
                                        ROLE_PRIORITY.get(str(r.get("snapshot_role")), 0)))
    return best.get("snapshot_id")


def probability_model_id(row: Mapping[str, Any]) -> str:
    identity = row.get("probability_model_id")
    if identity:
        return str(identity)
    engine = str(row.get("engine") or "unknown")
    # A historical engine label cannot establish which coefficients were used.
    return "calibrated:unversioned" if engine.startswith("calibrated(") else f"legacy:{engine}"


def _compare(pairs: list[tuple[float, float, int]], assumed_mean: float, assumed_sd: float) -> dict:
    model = [p for p, _, _ in pairs]
    market = [m for _, m, _ in pairs]
    y = [yy for _, _, yy in pairs]
    if not pairs:
        return {"n": 0}
    diffs = [(p - yy) ** 2 - (m - yy) ** 2 for p, m, yy in pairs]
    observed_sd = _sd(diffs)
    sd_for_power = observed_sd if observed_sd and len(diffs) >= 30 else assumed_sd
    return {
        "n": len(pairs),
        "brier_model": round(_brier(model, y), 5),
        "brier_market": round(_brier(market, y), 5),
        "logloss_model": round(_logloss(model, y), 5),
        "logloss_market": round(_logloss(market, y), 5),
        "mean_brier_diff_model_minus_market": round(sum(diffs) / len(diffs), 5),
        "paired_sd": round(observed_sd, 5) if observed_sd is not None else None,
        "n_required": required_n(sd_for_power, assumed_mean),
        "n_required_basis": {
            "assumed_mean_improvement": assumed_mean,
            "sd": round(sd_for_power, 5),
            "sd_source": "observed" if sd_for_power is observed_sd else "assumed",
        },
    }


def _iter_dates(since: str | None, until: str | None, root: Path) -> list[str]:
    folder = root / "ledger"
    dates = sorted(p.stem for p in folder.glob("*.jsonl")) if folder.is_dir() else []
    return [d for d in dates if (not since or d >= since) and (not until or d <= until)]


def evaluate(
    *,
    root: Path | None = None,
    since: str | None = None,
    until: str | None = None,
    include_preseason: bool = False,
    assumed_mean: float = ASSUMED_BRIER_IMPROVEMENT,
    assumed_sd: float = ASSUMED_PAIRED_SD,
) -> dict:
    root = root or ledger_root()
    rows = [row for day in _iter_dates(since, until, root) for row in read_rows(root, day)]
    exclusions = no_prediction_exclusions(rows)
    kept = [r for r in rows if r.get("row_type") != "no_prediction" and not _excluded(r, exclusions)]
    excluded_rows = len(rows) - len(kept) - sum(r.get("row_type") == "no_prediction" for r in rows)
    rows = kept
    if not include_preseason:
        rows = [r for r in rows if r.get("season_phase") != "PRESEASON"]

    prices: dict[tuple, list[dict]] = defaultdict(list)
    models: dict[tuple, list[dict]] = defaultdict(list)
    settlements: dict[tuple, dict] = {}
    sgms: dict[tuple, list[dict]] = defaultdict(list)
    sgm_quotes: dict[tuple, list[dict]] = defaultdict(list)
    counts = defaultdict(int)
    if exclusions:
        counts["excluded_no_prediction_rows"] = excluded_rows
    for row in rows:
        kind = row.get("row_type")
        counts[f"rows_{kind}"] += 1
        if kind in {"price_obs", "model_obs", "sgm_obs"} and not _pre_tip(row):
            counts[f"excluded_{kind}_post_tip_or_late"] += 1
        if kind == "price_obs":
            prices[_leg_key(row)].append(row)
        elif kind == "model_obs":
            models[_leg_key(row)].append(row)
        elif kind == "settlement":
            settlements.setdefault(_leg_key(row), row)
        elif kind == "sgm_obs":
            sgms[(row.get("target_date"), row.get("game_tag"))].append(row)
        elif kind == "model_missing":
            counts["model_missing_snapshots"] += 1
        elif kind == "sgm_price_obs" and row.get("status") == "ok" and _pre_tip(row):
            sgm_quotes[(row.get("snapshot_id"), row.get("game_tag"), row.get("combo_id"))].append(row)

    legs = []
    for key, model_rows in models.items():
        snapshot_id = _choose_snapshot(model_rows)
        if snapshot_id is None:
            counts["legs_without_pretip_model"] += 1
            continue
        model = next(r for r in model_rows if r.get("snapshot_id") == snapshot_id)
        pre_tip_prices = [r for r in prices.get(key, []) if _pre_tip(r)]
        observed = sorted((r for r in pre_tip_prices if r.get("price_source") != "ou_two_way"),
                          key=lambda r: r["captured_at"])
        two_way = sorted((r for r in pre_tip_prices
                          if r.get("price_source") == "ou_two_way" and r.get("complement_price")),
                         key=lambda r: r["captured_at"])
        if not observed:
            counts["legs_missed_pretip_price"] += 1
        earliest, close = (observed[0], observed[-1]) if observed else (None, None)
        settlement = settlements.get(key)
        y = settlement.get("y") if settlement else None
        if settlement is None:
            counts["legs_unsettled"] += 1
        elif y is None:
            counts[f"legs_{settlement.get('outcome')}"] += 1
        devig_close = two_way[-1] if two_way else (close if close and close.get("complement_price") else None)
        legs.append({
            "key": key, "market": key[3], "picked": bool(model.get("picked")), "y": y,
            "probability_model_id": probability_model_id(model),
            **{name: model.get(name) for name in MODEL_VARIANTS},
            "price_at_model": model.get("price_at_model"),
            "earliest_price": earliest.get("price") if earliest else None,
            "earliest_at": earliest.get("captured_at") if earliest else None,
            "close_price": close.get("price") if close else None,
            "close_at": close.get("captured_at") if close else None,
            "market_raw_close": 1.0 / close["price"] if close else None,
            "market_devig_close": (
                devig_two_way_proportional(devig_close["price"], devig_close["complement_price"])
                if devig_close else None
            ),
            "devig_source": devig_close.get("price_source") if devig_close else None,
            "devig_at": devig_close.get("captured_at") if devig_close else None,
        })

    def section(subset: list[dict]) -> dict:
        settled = [leg for leg in subset if leg["y"] is not None]
        out: dict[str, Any] = {"legs": len(subset), "settled": len(settled), "variants": {}}
        for variant in MODEL_VARIANTS:
            entry = {}
            for comparator in ("market_raw_close", "market_devig_close"):
                pairs = [(leg[variant], leg[comparator], leg["y"]) for leg in settled
                         if leg[variant] is not None and leg[comparator] is not None]
                entry[comparator] = _compare(pairs, assumed_mean, assumed_sd)
            with_p = [(leg[variant], leg["y"]) for leg in settled if leg[variant] is not None]
            entry["calibration"] = calibration_buckets([p for p, _ in with_p], [yy for _, yy in with_p])
            out["variants"][variant] = entry
        raw = [(leg["market_raw_close"], leg["y"]) for leg in settled if leg["market_raw_close"] is not None]
        out["market_raw_close_calibration"] = calibration_buckets([p for p, _ in raw], [yy for _, yy in raw])
        clv = [leg["earliest_price"] / leg["close_price"] - 1 for leg in subset
               if leg["earliest_price"] and leg["close_price"] and leg["earliest_at"] != leg["close_at"]]
        model_clv = [leg["price_at_model"] / leg["close_price"] - 1 for leg in subset
                     if leg["price_at_model"] and leg["close_price"]]
        out["clv_earliest_vs_close"] = {
            "n": len(clv), "mean": round(sum(clv) / len(clv), 5) if clv else None,
            "share_positive": round(sum(c > 0 for c in clv) / len(clv), 4) if clv else None,
        }
        out["clv_model_price_vs_close"] = {
            "n": len(model_clv), "mean": round(sum(model_clv) / len(model_clv), 5) if model_clv else None,
        }
        out["settled_event_clusters"] = len({leg["key"][:2] for leg in settled if leg["p_final"] is not None})
        out["settled_clusters_player_game_market"] = len({leg["key"][:4] for leg in settled})
        devigged_settled = [leg for leg in settled if leg["market_devig_close"] is not None]
        out["devig_coverage"] = {
            "legs_with_two_way_price": sum(leg["market_devig_close"] is not None for leg in subset),
            "settled_with_two_way_price": len(devigged_settled),
            "settled_clusters_with_two_way_price": len({leg["key"][:4] for leg in devigged_settled}),
        }
        return out

    by_market = {m: section([leg for leg in legs if leg["market"] == m]) for m in sorted({l["market"] for l in legs})}
    by_picked = {name: section([leg for leg in legs if leg["picked"] is flag])
                 for name, flag in (("picked", True), ("not_picked", False))}
    by_model = {
        identity: {
            **section([leg for leg in legs if leg["probability_model_id"] == identity]),
            "by_market": {market: section([leg for leg in legs if leg["probability_model_id"] == identity and leg["market"] == market])
                          for market in by_market},
            "picked": section([leg for leg in legs if leg["probability_model_id"] == identity and leg["picked"]]),
            "picked_by_market": {market: section([leg for leg in legs if leg["probability_model_id"] == identity
                                                  and leg["picked"] and leg["market"] == market]) for market in by_market},
        }
        for identity in sorted({leg["probability_model_id"] for leg in legs})
    }

    # SGMs: one chosen pre-tip snapshot per game.
    sgm_pairs = {"model_naive": [], "model_adjusted": [], "model_sim_joint": [], "model_sim_scaled": [],
                 "product_of_legs_implied": [], "sportsbet_sgm_implied": []}
    sgm_counts = defaultdict(int)
    for (_day, _tag), combo_rows in sgms.items():
        snapshot_id = _choose_snapshot(combo_rows)
        for combo in (r for r in combo_rows if r.get("snapshot_id") == snapshot_id):
            sgm_counts["combos"] += 1
            outcomes = []
            for leg in combo.get("legs") or []:
                key = (combo["target_date"], combo["game_tag"], leg.get("player"), leg.get("market"),
                       _float(leg.get("line")), leg.get("side") or "over")
                settlement = settlements.get(key)
                outcomes.append(settlement.get("y") if settlement else None)
            if not outcomes or any(o is None for o in outcomes):
                sgm_counts["unresolved"] += 1
                continue
            realised = int(all(outcomes))
            sgm_counts["settled"] += 1
            quotes = sorted(sgm_quotes.get((combo.get("snapshot_id"), combo.get("game_tag"),
                                            combo.get("combo_id")), []),
                            key=lambda r: r["captured_at"])
            # Close = latest pre-tip quote of this exact combo.
            sgm_price = combo.get("sportsbet_sgm_price") or (
                quotes[-1]["sportsbet_sgm_price"] if quotes else None)
            if sgm_price:
                sgm_counts["settled_with_sportsbet_price"] += 1
            for name, value in (
                ("model_naive", combo.get("naive_joint_prob")),
                ("model_adjusted", combo.get("adjusted_joint_prob")),
                ("model_sim_joint", combo.get("sim_joint_prob")),
                ("model_sim_scaled", combo.get("sim_scaled_joint_prob")),
                ("product_of_legs_implied",
                 1.0 / combo["product_of_leg_prices"] if combo.get("product_of_leg_prices") else None),
                ("sportsbet_sgm_implied", 1.0 / sgm_price if sgm_price else None),
            ):
                if value is not None:
                    sgm_pairs[name].append((value, realised))
    sgm = {
        "counts": dict(sgm_counts),
        "sportsbet_sgm_price_status": (
            "sgm_price_obs rows: latest pre-tip public multi-pricer quote per combo "
            "(vig-inclusive, one-sided; cannot be de-vigged); combos without a quote "
            "fall back to product_of_legs_implied only"
        ),
    }
    for name, pairs in sgm_pairs.items():
        sgm[name] = {
            "n": len(pairs),
            "brier": round(_brier([p for p, _ in pairs], [y for _, y in pairs]), 5) if pairs else None,
            "mean_p": round(sum(p for p, _ in pairs) / len(pairs), 4) if pairs else None,
            "realised_rate": round(sum(y for _, y in pairs) / len(pairs), 4) if pairs else None,
        }

    overall = section(legs)
    headline = overall["variants"]["p_final"]["market_raw_close"]
    devigged = overall["variants"]["p_final"]["market_devig_close"]
    # The de-vigged comparison only covers legs with a two-way O/U price, so
    # its power is judged on those clusters, not on every settled leg.
    clusters = overall["devig_coverage"]["settled_clusters_with_two_way_price"]
    if not devigged.get("n"):
        verdict = "market_not_devigged"
    elif clusters < (devigged.get("n_required") or math.inf):
        verdict = "insufficient_n"
    else:
        verdict = "n_adequate_pending_review"
    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window": {"since": since, "until": until, "include_preseason": include_preseason},
        "verdict_status": verdict,
        "by_probability_model": by_model,
        "verdict_note": (
            "No model-vs-market verdict is valid yet. Comparisons against raw 1/price are "
            "biased in the model's favour (vig-inclusive, one-sided milestone markets). "
            "Legs within a game are correlated, so the effective n is the settled "
            "player-game-market cluster count, not the leg count."
        ),
        "headline_p_final_vs_raw_close": headline,
        "no_prediction_exclusions": [
            {"target_date": day, "game_tag": tag}
            for day, tag in sorted(exclusions, key=lambda item: (str(item[0]), str(item[1] or "")))
        ],
        "counts": dict(counts),
        "overall": overall,
        "by_market": by_market,
        "by_picked": by_picked,
        "sgm": sgm,
    }


def write_evaluation(report: dict, *, root: Path | None = None) -> Path:
    root = root or ledger_root()
    destination = root / "reports" / "evaluation_latest.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)
    return destination


def results_brief_for(folder: Path, target_date: str) -> Path:
    us_date = (date.fromisoformat(target_date) - timedelta(days=1)).isoformat()
    return Path(folder) / f"Results_Brief_{us_date}.json"


# ── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="NBA forward market-evaluation ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    snap = sub.add_parser("record-snapshot", help="record one prediction snapshot (late runs are flagged)")
    snap.add_argument("--snapshot", required=True)
    snap.add_argument("--date", required=True)
    settle_cmd = sub.add_parser("settle")
    settle_cmd.add_argument("--date", required=True)
    settle_cmd.add_argument("--results", required=True)
    report = sub.add_parser("evaluate")
    report.add_argument("--since")
    report.add_argument("--until")
    report.add_argument("--include-preseason", action="store_true")
    report.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "record-snapshot":
        print(json.dumps(record_snapshot(Path(args.snapshot), args.date)))
    elif args.command == "settle":
        print(json.dumps(settle(args.date, Path(args.results))))
    else:
        result = evaluate(since=args.since, until=args.until, include_preseason=args.include_preseason)
        if args.write:
            write_evaluation(result)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
