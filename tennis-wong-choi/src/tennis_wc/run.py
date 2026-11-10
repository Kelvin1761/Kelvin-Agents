"""The daily pipeline, in-process. Three jobs:

``price_day(date)``   refresh sources -> features -> match model -> props -> report
``review_day(date)``  fetch results -> settle props -> 精選 performance
``weekly(date)``      精選 timing / coverage review (Sundays)

Every stage is timed; a failing *source* stage is recorded and the run goes on,
because a card priced from yesterday's rankings beats no card. A failure that
leaves nothing to price is caught by ``readiness``.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from tennis_wc.store.db import get_connection
from tennis_wc.model.features.common import utc_now

CRITICAL_SOURCES = {"prop_pricing", "odds", "event_markets", "event_markets_check", "upcoming_matches"}


class Stages:
    """Runs stages, keeps timings, collects source errors and degradations."""

    def __init__(self) -> None:
        self.timings: list[dict] = []
        self.errors: list[dict] = []
        self.warnings: list[dict] = []

    def run(self, label: str, step, *, source: bool = True):
        started = time.perf_counter()
        status = "ok"
        try:
            result = step()
        except Exception as exc:  # noqa: BLE001 - recorded, run continues
            status = "failed"
            if not source:
                raise
            self.errors.append({"source": label, "error": f"{type(exc).__name__}: {exc}"})
            return None
        finally:
            self.timings.append({"stage": label, "status": status,
                                 "seconds": round(time.perf_counter() - started, 3)})
        self.warnings.extend(_degradations(label, result))
        return result


def _degradations(label: str, result) -> list[dict]:
    """A stage that returned on cached or partial data still says so."""
    warnings: list[dict] = []
    if label in ("rankings_atp", "rankings_wta"):
        from tennis_wc.sources.ingest_rankings import rankings_cache_fallback

        fallback = rankings_cache_fallback(label.split("_", 1)[1].upper())
        if fallback:
            warnings.append({"source": label, "warning": "rankings_cache_fallback",
                             "cached_latest_ranking_date": fallback.get("cached_latest_ranking_date"),
                             "error": fallback.get("error")})
    if isinstance(result, dict):
        for err in result.get("errors") or []:
            if isinstance(err, dict):
                warnings.append({"source": label, "warning": str(err.get("error") or "error"),
                                 **{k: v for k, v in err.items() if k != "error"}})
    return warnings


# --------------------------------------------------------------------------- price

def refresh_sources(match_date: str, stages: Stages) -> None:
    from tennis_wc.sources.confirmed_metadata import backfill_confirmed_metadata_for_date
    from tennis_wc.sources.ingest_matches import ingest_default_history, ingest_upcoming_matches
    from tennis_wc.sources.ingest_odds import enrich_sportsbet_event_markets, ingest_odds
    from tennis_wc.sources.ingest_rankings import ingest_rankings
    from tennis_wc.sources.ingest_sackmann import ingest_tml_low_tier_history
    from tennis_wc.sources.ingest_tournaments import ingest_tournaments
    from tennis_wc.model.elo_builder import build_sackmann_elo

    year = int(match_date[:4])
    for label, step in (
        ("tournaments", lambda: ingest_tournaments(match_date, match_date)),
        ("rankings_atp", lambda: ingest_rankings("ATP", match_date)),
        ("rankings_wta", lambda: ingest_rankings("WTA", match_date)),
        ("history", lambda: ingest_default_history(match_date)),
        ("history_lowtier", lambda: ingest_tml_low_tier_history(year, year)),
        ("elo_rebuild", build_sackmann_elo),
        ("upcoming_matches", lambda: ingest_upcoming_matches(match_date)),
        ("odds", lambda: ingest_odds(match_date)),
        ("event_markets", lambda: enrich_sportsbet_event_markets(match_date)),
        ("metadata_backfill", lambda: backfill_confirmed_metadata_for_date(match_date)),
    ):
        stages.run(label, step)
    # A day with only match-winner odds means the per-event pages failed.
    with get_connection() as conn:
        rows, markets = conn.execute("""
            SELECT COUNT(*), COUNT(DISTINCT mo.market_key)
            FROM market_odds_snapshots mo JOIN matches m ON m.id = mo.match_id
            WHERE m.match_date = ? AND mo.source_provider = 'sportsbet'""", (match_date,)).fetchone()
    if rows and markets <= 1:
        stages.errors.append({"source": "event_markets",
                              "error": "only_match_winner_odds_captured__multi_market_enrichment_incomplete"})


def merge_identities() -> dict:
    """Apply only the merges the identity planner is confident about."""
    from tennis_wc.sources.identity import apply_merges, ensure_identity_schema, plan_merges

    with get_connection() as conn:
        ensure_identity_schema(conn)
        plans = plan_merges(conn)
        confident = [plan for plan in plans if plan.reason == "merge"]
        if not confident:
            return {"groups": 0, "refused": len(plans)}
        summary = apply_merges(conn, confident)
        summary["refused"] = len(plans) - len(confident)
        return summary


def _started(start) -> bool:
    if isinstance(start, dict):
        start = start.get("value")
    if not start:
        return False
    parsed = datetime.fromisoformat(str(start).replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("match_start_missing_timezone")
    return parsed <= datetime.now(timezone.utc)


def predict_matches(match_date: str, stages: Stages) -> dict:
    """Feature snapshots -> match-win probability -> ``predictions`` (props read it)."""
    from tennis_wc.model.features.feature_builder import build_sportsbet_feature_snapshots_for_date
    from tennis_wc.model.match_pricing import price_match_snapshot
    from tennis_wc.store.predictions import store_prediction

    skipped: list[dict] = []
    snapshots = stages.run("feature_snapshots",
                           lambda: build_sportsbet_feature_snapshots_for_date(match_date, skipped=skipped),
                           source=False)
    stored = 0
    for snapshot in snapshots:
        match_id = snapshot["match_id"]["value"]
        start = (snapshot.get("match_context") or {}).get("start_time_utc")
        try:
            if _started(start):
                skipped.append({"match_id": match_id, "reason": "match_already_started_at_pricing"})
                continue
        except ValueError as exc:
            skipped.append({"match_id": match_id, "reason": str(exc)})
            continue
        pricing = price_match_snapshot(snapshot)
        if _started(start):
            skipped.append({"match_id": match_id, "reason": "match_started_during_pricing"})
            continue
        store_prediction(match_id, snapshot["feature_set_version"], pricing)
        stored += 1
    valid = sum(1 for s in snapshots if s["data_quality"]["is_valid"])
    return {"matches_analysed": len(snapshots), "valid_feature_snapshots": valid,
            "predictions": stored, "pregame_skipped": skipped}


def price_props(match_date: str) -> int:
    from tennis_wc.pricing.props import price_date
    from tennis_wc.settle.props import settle_props
    from tennis_wc.store.ledger import record_rows

    with get_connection() as conn:
        settle_props(conn)  # grade anything newly settleable first
        now = utc_now()
        return record_rows(conn, price_date(conn, match_date, now), now)


def price_day(match_date: str, *, today: str) -> dict:
    """The whole analysis for one date. Returns the health payload."""
    from tennis_wc.model.features.feature_builder import odds_coverage_for_date
    from tennis_wc.publish.report import write_report
    from tennis_wc.sources.slate_audit import audit_current_slate

    stages = Stages()
    stages.run("settlement_backlog", lambda: settle_backlog(match_date))
    refresh_sources(match_date, stages)
    stages.run("identity_merge", merge_identities)
    with get_connection() as conn:
        slate = audit_current_slate(conn, match_date, apply=True)
    if slate["held"]:
        stages.warnings.append({"source": "slate_integrity",
                                "warning": f"held fixtures (excluded from card): {slate['held']}"})
    model = predict_matches(match_date, stages)
    props = stages.run("prop_pricing", lambda: price_props(match_date))
    with get_connection() as conn:
        from tennis_wc import monitor

        stages.warnings += (monitor.silent_prop_families(conn, match_date)
                            + monitor.market_group_coverage(conn, match_date)
                            + monitor.stale_serve_history(conn, match_date))
    report = stages.run("daily_report", lambda: write_report(match_date), source=False)
    payload = {
        "date": match_date, **model,
        "props_priced": props,
        "odds_coverage": odds_coverage_for_date(match_date),
        "report_path": str(report),
        "source_errors": stages.errors, "source_warnings": stages.warnings,
        "slate_integrity": slate, "stage_timings": stages.timings,
    }
    payload["readiness"] = readiness(payload, horizon=horizon(match_date, today))
    _record_run(match_date, payload)
    return payload


def publish_day(match_date: str, payload: dict) -> dict:
    """After 精選 are recorded: rewrite the report, freeze it as evidence, deploy.

    Runs after the picks so the dashboard and the evidence carry them; the
    deploy is still gated by the analysis readiness.
    """
    from tennis_wc.publish.dashboard import deploy, record_evidence
    from tennis_wc.publish.report import write_report

    out: dict = {}
    try:
        report = write_report(match_date)
        out["prediction_evidence"] = record_evidence(match_date, Path(report))
    except Exception as exc:  # noqa: BLE001 - evidence never blocks the dashboard
        out["prediction_evidence"] = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
    out["cloudflare_deploy"] = deploy(match_date, payload)
    return out


def _record_run(match_date: str, payload: dict) -> None:
    from tennis_wc.sources.raw_response_store import store_raw_response

    store_raw_response("tennis_wc_pipeline", "/run-daily/source-errors", {"date": match_date},
                       {"mode": "live_full", "errors": payload["source_errors"],
                        "warnings": payload["source_warnings"]},
                       207 if payload["source_errors"] else 200, "run_daily_source_errors", match_date)


# --------------------------------------------------------------------------- readiness

MIN_PRICED_RATIO = 0.35
MIN_FIXTURES_FOR_RATIO_CHECK = 10


def horizon(match_date: str, today: str) -> str:
    if match_date > today:
        return "next_day"
    return "past" if match_date < today else "same_day"


def readiness(payload: dict, *, horizon: str) -> dict:
    """ok / expected_empty (tomorrow's book not open) / retry / error."""
    coverage = payload.get("odds_coverage") or {}
    fixtures = int(coverage.get("fixtures") or 0)
    priced = int(coverage.get("priced_matches") or 0)
    book = int(coverage.get("book_fixtures") or 0) or fixtures
    early: list[str] = []
    if fixtures == 0 and priced == 0 and not payload.get("confirmed_empty_slate"):
        early.append("zero fixtures and odds without a confirmed empty slate")
    elif fixtures > 0 and priced == 0:
        early.append(f"zero Sportsbet-priced matches across {fixtures} fixtures")
    if book >= MIN_FIXTURES_FOR_RATIO_CHECK and priced / book < MIN_PRICED_RATIO:
        early.append(f"only {priced}/{book} Sportsbet fixtures priced -- book likely not open yet")
    elif fixtures >= MIN_FIXTURES_FOR_RATIO_CHECK and book < MIN_FIXTURES_FOR_RATIO_CHECK:
        early.append(f"Sportsbet listed only {book} of {fixtures} fixtures -- book likely not open yet")

    analysed = int(payload.get("matches_analysed") or 0)
    errors = payload.get("source_errors") or []
    broken: list[str] = []
    critical = [e for e in errors if str(e.get("source") or "") in CRITICAL_SOURCES or not e.get("source")]
    if analysed == 0 and (critical or (errors and priced > 0)):
        broken.append("zero matches after source failures")
    elif analysed == 0 and priced > 0:
        broken.append(f"{priced} priced matches produced zero model snapshots")
    elif analysed > 0 and int(payload.get("valid_feature_snapshots") or 0) == 0:
        broken.append("all feature snapshots are invalid")
    broken += [f"{e['source']}: {e.get('error') or 'unknown error'}" for e in errors
               if str(e.get("source") or "") in CRITICAL_SOURCES]

    observed = list(dict.fromkeys(early + broken))
    if broken:
        severity = "error"
    elif not early:
        severity = "ok"
    elif horizon == "next_day":
        severity = "expected_empty"
    else:
        severity = "error" if priced == 0 else "retry"
    return {"horizon": horizon, "severity": severity, "observed": observed,
            "reasons": [] if severity in ("ok", "expected_empty") else observed}


# --------------------------------------------------------------------------- review

def settle_backlog(before_date: str, lookback_days: int = 30, max_dates: int = 10) -> dict:
    """Fetch results for recent dates that still hold PENDING props, then settle."""
    from tennis_wc.settle.props import settle_props
    from tennis_wc.settle.results import fetch_results_for_date

    with get_connection() as conn:
        dates = [r[0] for r in conn.execute("""
            SELECT DISTINCT match_date FROM prop_tracker
            WHERE result_status = 'PENDING' AND match_date < ?
              AND match_date >= date(?, ?) ORDER BY match_date DESC""",
            (before_date, before_date, f"-{lookback_days} days"))]
    summary: dict = {"dates": {}, "skipped_dates": dates[max_dates:]}
    for day in dates[:max_dates]:
        try:
            summary["dates"][day] = fetch_results_for_date(day)
        except Exception as exc:  # noqa: BLE001
            summary["dates"][day] = {"error": str(exc)}
    with get_connection() as conn:
        summary["props"] = settle_props(conn)
    return summary


def review_day(match_date: str) -> dict:
    """Results for ``match_date`` (and neighbours), then settle every PENDING prop."""
    from tennis_wc.settle.props import settle_props
    from tennis_wc.settle.results import fetch_results_for_date

    results = fetch_results_for_date(match_date)
    with get_connection() as conn:
        settled = settle_props(conn)
        pending = conn.execute("SELECT COUNT(*) FROM prop_tracker WHERE match_date=? AND result_status='PENDING'",
                               (match_date,)).fetchone()[0]
    return {"date": match_date, "results": results, "settlement": settled,
            "pending_for_date": pending}


FINISHED_AFTER_MINUTES = 90   # a best-of-three is rarely over sooner
TICK_GIVES_UP_AFTER_HOURS = 12  # later than this the 09:00 / 18:00 runs take over


def due_featured(conn, now: datetime) -> list[dict]:
    """PENDING 精選 whose match (at its current start time) should be finished."""
    from tennis_wc.select.featured import ensure_schema

    ensure_schema(conn)
    due = []
    for r in conn.execute(
        """SELECT f.prop_id, m.match_date, p.match_date AS prop_date, m.start_time_utc
           FROM featured_picks f
           JOIN prop_tracker p ON p.id = f.prop_id
           JOIN matches m ON m.id = f.match_id
           WHERE p.result_status = 'PENDING' AND m.start_time_utc IS NOT NULL"""
    ).fetchall():
        try:
            start = datetime.fromisoformat(str(r["start_time_utc"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if start.tzinfo is None:
            continue
        minutes = (now - start).total_seconds() / 60
        if FINISHED_AFTER_MINUTES <= minutes <= TICK_GIVES_UP_AFTER_HOURS * 60:
            # Also the UTC day the match started on: a 01:00 Sydney start is the
            # previous day in Europe, and TennisExplorer files it there. On
            # 2026-11-11 seven of ten picks waited for the 09:00 run because
            # only the Sydney date was fetched.
            due.append({"prop_id": int(r["prop_id"]),
                        "dates": {d for d in (r["match_date"], r["prop_date"],
                                              start.astimezone(timezone.utc).date().isoformat()) if d}})
    return due


def settle_finished_featured(now: datetime | None = None, *, fetch=None) -> dict:
    """Hourly tick: fetch results and settle, only when a 精選 match should be over.

    Before 2026-11-10 results were read at 09:00 / 18:00 / 21:00 / 23:00 only:
    40 picks settled a median 8.1h after the start (1.7h to 16h). No network
    call is made when nothing is due. Selection, prices and the forward-test
    verdict are untouched: this only runs the existing settlement sooner.
    """
    from tennis_wc.settle.props import settle_props

    now = now or datetime.now(timezone.utc)
    with get_connection() as conn:
        due = due_featured(conn, now)
    summary: dict = {"due": len(due), "dates": [], "settled": 0, "errors": []}
    if not due:
        return summary
    if fetch is None:
        from tennis_wc.settle.results import fetch_results_for_date as fetch
    summary["dates"] = sorted(set().union(*(d["dates"] for d in due)))
    for day in summary["dates"]:
        try:
            fetch(day)
        except Exception as exc:  # noqa: BLE001 - one bad date must not stop the others
            summary["errors"].append(f"{day}: {type(exc).__name__}: {exc}")
    ids = [d["prop_id"] for d in due]
    with get_connection() as conn:
        settle_props(conn)
        marks = ",".join("?" for _ in ids)
        still = conn.execute(
            f"SELECT COUNT(*) FROM prop_tracker WHERE result_status = 'PENDING' AND id IN ({marks})", ids
        ).fetchone()[0]
    summary["settled"] = len(ids) - int(still)
    summary["latest_date"] = summary["dates"][-1]
    return summary


def results_extracted(review: dict) -> bool:
    """Did the review see any result at all (or have nothing left to settle)?"""
    results = review.get("results") or {}
    seen = (results.get("imported"), results.get("winners_seen"), results.get("lookup_winners_seen"),
            (results.get("tennismylife") or {}).get("results_imported"),
            (results.get("tennisexplorer") or {}).get("imported"),
            (review.get("settlement") or {}).get("graded"))
    return any(int(v or 0) > 0 for v in seen) or int(review.get("pending_for_date") or 0) == 0
