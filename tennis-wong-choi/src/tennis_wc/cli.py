from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.diagnostics import run_network_check
from tennis_wc.features.data_quality import validate_data_freshness
from tennis_wc.features.feature_builder import (
    build_feature_snapshots_for_date,
    build_sportsbet_feature_snapshots_for_date,
    odds_coverage_for_date,
)
from tennis_wc.ingestion.ingest_matches import ingest_default_history, ingest_upcoming_matches
from tennis_wc.ingestion.ingest_odds import (
    enrich_sportsbet_event_markets,
    ingest_event_odds,
    ingest_odds,
    probe_sportsbet_event_markets,
)
from tennis_wc.ingestion.confirmed_metadata import backfill_confirmed_metadata_for_date, metadata_audit_for_date
from tennis_wc.ingestion.ingest_player_stats import ingest_player_stats
from tennis_wc.ingestion.ingest_rankings import ingest_rankings
from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.ingestion.ingest_sackmann import ingest_sackmann_history, ingest_tml_low_tier_history
from tennis_wc.ingestion.ingest_tennismylife import ingest_tennismylife_results
from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments
from tennis_wc.betting.bet_filter import apply_bet_filter
from tennis_wc.betting.ledger import (
    combo_roi_summary,
    fetch_closing_odds_for_date,
    ledger_summary,
    record_bet as record_bet_entry,
    review_date as review_date_entry,
    settle_bets_for_date,
    settle_pending_backlog,
    sync_clv_tracker_for_date,
    sync_combo_tracker_for_date,
    tier_roi_summary,
)
from tennis_wc.agents.runner import run_agents as run_agent_reviews
from tennis_wc.modelling.backtester import run_backtest
from tennis_wc.modelling.calibration import calibrate_sackmann_elo
from tennis_wc.modelling.elo_builder import build_sackmann_elo
from tennis_wc.modelling.ml_baseline import train_ml_baseline
from tennis_wc.modelling.prediction_store import store_prediction
from tennis_wc.modelling.pricing import price_match_snapshot
from tennis_wc.providers import get_news_provider, get_odds_provider, get_tennis_provider
from tennis_wc.reports.daily_report import analysis_output_dir, clear_pipeline_source_errors, generate_daily_report
from tennis_wc.reports.calibration_report import banker_calibration_summary
from tennis_wc.reports.match_report import render_match_report
from tennis_wc.reports.market_validation_report import aces_prop_sanity_for_date, market_validation_summary
from tennis_wc.reports.performance_report import prediction_summary
from tennis_wc.config import get_settings
from tennis_wc.pipeline_readiness import analysis_retry_reasons

REPO_ROOT = Path(__file__).resolve().parents[3]
SHARED_HOOK_DIR = REPO_ROOT / ".agents" / "skills" / "shared_racing" / "post_success_hooks" / "scripts"
sys.path.insert(0, str(SHARED_HOOK_DIR))
from cloudflare_deploy_hook import run_post_success_cloudflare_deploy

SHARED_SKILLS_DIR = REPO_ROOT / ".agents" / "skills"
sys.path.insert(0, str(SHARED_SKILLS_DIR))
from shared_wong_choi.contracts import Domain
from shared_wong_choi.domain_evidence import (
    record_prediction_decision_if_configured,
    record_settlement_for_event,
)
from shared_wong_choi.evidence import DecisionState
from shared_wong_choi.immutable_snapshot import create_immutable_snapshot


def _print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def provider_healthcheck(_: argparse.Namespace) -> None:
    checks = {
        "tennis": _safe_healthcheck(get_tennis_provider),
        "odds": _safe_healthcheck(get_odds_provider),
        "news": _safe_healthcheck(get_news_provider),
    }
    _print_json(checks)


def network_check(_: argparse.Namespace) -> None:
    _print_json(run_network_check())


def _safe_healthcheck(factory) -> bool:
    try:
        return bool(factory().healthcheck())
    except Exception:
        return False


def config_check(_: argparse.Namespace) -> None:
    settings = get_settings()
    _print_json(
        {
            "database_url": settings.database_url,
            "tennis_provider": settings.tennis_provider,
            "tennis_api_key": _redacted(settings.tennis_api_key),
            "tennis_api_base_url": settings.tennis_api_base_url,
            "odds_provider": settings.odds_provider,
            "sportsbet_source_mode": settings.sportsbet_source_mode,
            "sportsbet_api_key": _redacted(settings.sportsbet_api_key),
            "sportsbet_api_base_url": settings.sportsbet_api_base_url,
            "sportsbet_allowed_scrape_fallback": settings.sportsbet_allowed_scrape_fallback,
        }
    )


def provider_smoke(args: argparse.Namespace) -> None:
    result = {"provider": args.provider, "ok": False, "samples": {}, "error": None}
    try:
        if args.provider == "tennis":
            provider = get_tennis_provider()
            result["healthcheck"] = provider.healthcheck()
            rankings = provider.fetch_rankings(args.tour, args.date)
            tournaments = provider.fetch_tournaments(args.date, args.date)
            matches = provider.fetch_upcoming_matches(args.date)
            result["samples"] = {
                "rankings_count": len(rankings),
                "rankings_first": rankings[0] if rankings else None,
                "tournaments_count": len(tournaments),
                "tournaments_first": tournaments[0] if tournaments else None,
                "matches_count": len(matches),
                "matches_first": matches[0] if matches else None,
            }
        elif args.provider == "odds":
            provider = get_odds_provider()
            result["healthcheck"] = provider.healthcheck()
            if hasattr(provider, "fetch_upcoming_odds_for_date"):
                odds = provider.fetch_upcoming_odds_for_date(args.date)
            else:
                odds = provider.fetch_upcoming_odds("tennis", ["au"], ["match_winner"])
            result["samples"] = {"odds_count": len(odds), "odds_first": odds[0] if odds else None}
        else:
            raise ValueError(f"Unsupported provider smoke target: {args.provider}")
        result["ok"] = True
    except Exception as exc:
        result["error"] = str(exc)
    _print_json(result)


def fetch_upcoming_matches(args: argparse.Namespace) -> None:
    print(ingest_upcoming_matches(args.date))


def fetch_tournaments(args: argparse.Namespace) -> None:
    print(len(ingest_tournaments(args.start, args.end)))


def fetch_rankings(args: argparse.Namespace) -> None:
    print(ingest_rankings(args.tour, args.date))


def fetch_player_stats(args: argparse.Namespace) -> None:
    print(ingest_player_stats(args.player_id))


def bootstrap_sackmann_history(args: argparse.Namespace) -> None:
    tours = args.tours.split(",") if args.tours else None
    _print_json(ingest_sackmann_history(args.start_year, args.end_year, tours))


def bootstrap_lowtier_history(args: argparse.Namespace) -> None:
    _print_json(
        ingest_tml_low_tier_history(
            args.start_year, args.end_year, include_quali=not args.no_quali
        )
    )


def ingest_tennismylife(args: argparse.Namespace) -> None:
    start = args.start or args.date
    end = args.end or args.date
    if not start:
        raise SystemExit("Provide --date or --start/--end.")
    _print_json(ingest_tennismylife_results(start, end))


def build_elo(args: argparse.Namespace) -> None:
    _print_json(build_sackmann_elo(args.initial_rating, args.k_factor))


def calibrate_elo(args: argparse.Namespace) -> None:
    _print_json(calibrate_sackmann_elo(args.start, args.end, args.initial_rating, args.k_factor))


def fetch_odds(args: argparse.Namespace) -> None:
    print(ingest_odds(args.date))


def sportsbet_urls(args: argparse.Namespace) -> None:
    provider = get_odds_provider()
    if not hasattr(provider, "fetch_upcoming_odds_for_date"):
        raise SystemExit("Configured odds provider cannot list dated Sportsbet URLs.")
    rows = provider.fetch_upcoming_odds_for_date(args.date)
    _print_json(
        {
            "date": args.date,
            "count": len(rows),
            "matches": [
                {
                    "start_time_utc": row.get("start_time_utc"),
                    "competition": row.get("competition"),
                    "match": f"{row.get('player_a_name')} v {row.get('player_b_name')}",
                    "player_a_odds": row.get("player_a_odds"),
                    "player_b_odds": row.get("player_b_odds"),
                    "url": row.get("event_url"),
                    "event_id": row.get("event_id"),
                }
                for row in rows
            ],
        }
    )


def fetch_event_odds(args: argparse.Namespace) -> None:
    try:
        count = ingest_event_odds(args.event_id, args.match_id)
        _print_json({"event_id": args.event_id, "match_id": args.match_id, "odds_snapshots": count})
    except Exception as exc:
        _print_json({"event_id": args.event_id, "match_id": args.match_id, "odds_snapshots": 0, "error": str(exc)})


def enrich_event_markets(args: argparse.Namespace) -> None:
    _print_json(enrich_sportsbet_event_markets(args.date))


def probe_event_markets(args: argparse.Namespace) -> None:
    _print_json(probe_sportsbet_event_markets(args.date, args.limit))


def build_features(args: argparse.Namespace) -> None:
    snapshots = build_feature_snapshots_for_date(args.date)
    _print_json({"date": args.date, "snapshots": len(snapshots), "data_quality": [s["data_quality"] for s in snapshots]})


def backfill_metadata(args: argparse.Namespace) -> None:
    _print_json(backfill_confirmed_metadata_for_date(args.date))


def metadata_audit(args: argparse.Namespace) -> None:
    _print_json(metadata_audit_for_date(args.date))


def validate_provenance(args: argparse.Namespace) -> None:
    snapshots = build_feature_snapshots_for_date(args.date)
    _print_json([validate_data_freshness(snapshot) for snapshot in snapshots])


def predict_daily(args: argparse.Namespace) -> None:
    snapshots = build_sportsbet_feature_snapshots_for_date(args.date)
    predictions = []
    for snapshot in snapshots:
        pricing = price_match_snapshot(snapshot)
        filter_result = apply_bet_filter(snapshot, pricing)
        prediction_id = store_prediction(
            snapshot["match_id"]["value"],
            snapshot["feature_set_version"],
            pricing,
            filter_result,
        )
        predictions.append(
            {
                "prediction_id": prediction_id,
                "match_id": snapshot["match_id"]["value"],
                "selection": pricing.get("selection_name"),
                "current_odds": pricing.get("current_market_odds"),
                "model_probability": pricing.get("model_probability"),
                "fair_odds": pricing.get("fair_odds"),
                "no_vig_market_probability": pricing.get("no_vig_market_probability"),
                "edge": pricing.get("edge"),
                "minimum_acceptable_odds": pricing.get("minimum_acceptable_odds"),
                "decision": filter_result["decision"],
                "decision_band": filter_result["decision_band"],
                "stake_units": filter_result["stake_units"],
                "confidence": filter_result["confidence"],
                "risk": filter_result["risk"],
                "hard_no_bet_reasons": filter_result["hard_no_bet_reasons"],
            }
        )
    _print_json({"date": args.date, "predictions": predictions})


def run_agents_command(args: argparse.Namespace) -> None:
    snapshots = build_sportsbet_feature_snapshots_for_date(args.date)
    outputs = []
    for snapshot in snapshots:
        pricing = price_match_snapshot(snapshot)
        filter_result = apply_bet_filter(snapshot, pricing)
        agent_output = run_agent_reviews(snapshot, pricing, filter_result)
        outputs.append(
            {
                "match_id": snapshot["match_id"]["value"],
                "selection": pricing.get("selection_name"),
                "decision": filter_result["decision"],
                "final_decision": agent_output["final_decision"],
                "reviews": agent_output["reviews"],
            }
        )
    _print_json({"date": args.date, "agent_runs": outputs})


def generate_report(args: argparse.Namespace) -> None:
    if args.match_id is not None:
        print(render_match_report(args.match_id))
        return
    output_path = generate_daily_report(args.date)
    _print_json({"date": args.date, "report_path": str(output_path), "analysis_dir": str(analysis_output_dir(args.date))})


def prune_raw_responses(args: argparse.Namespace) -> None:
    from tennis_wc.database.maintenance import prune_raw_response_bodies, vacuum

    with get_connection() as conn:
        result = prune_raw_response_bodies(
            conn, keep_days=args.keep_days, dry_run=args.dry_run
        )
        if args.vacuum and not args.dry_run:
            result["vacuum"] = vacuum(conn)
    _print_json(result)


def performance_report(_: argparse.Namespace) -> None:
    _print_json({"predictions": prediction_summary(), "ledger": ledger_summary()})


def record_bet(args: argparse.Namespace) -> None:
    bet_id = record_bet_entry(args.prediction_id, args.odds, args.stake)
    _print_json({"bet_id": bet_id, "prediction_id": args.prediction_id})


def record_live_prop_bet_command(args: argparse.Namespace) -> None:
    """Record a wager already placed manually; this command cannot place one."""
    from tennis_wc.props.live_bets import record_live_prop_bet

    _print_json(record_live_prop_bet(
        prop_id=args.prop_id,
        odds_taken=args.odds,
        stake_aud=args.stake_aud,
        placed_at=args.placed_at,
        notes=args.notes,
    ))


def fetch_closing_odds(args: argparse.Namespace) -> None:
    count = fetch_closing_odds_for_date(args.date)
    _print_json({"date": args.date, "closing_odds_snapshots": count})


def settle_bets(args: argparse.Namespace) -> None:
    result = settle_bets_for_date(args.date)
    result["prediction_evidence"] = record_settlement_for_event(
        domain=Domain.TENNIS,
        event_id=args.date,
        evidence_root=Path(
            os.environ.get(
                "WC_EVIDENCE_ROOT",
                "~/WongChoiData/WongChoiControl/evidence",
            )
        ).expanduser(),
        summary=result,
    )
    _print_json(result)


def settle_backlog(args: argparse.Namespace) -> None:
    _print_json(
        settle_pending_backlog(
            args.date, lookback_days=args.lookback_days, max_dates=args.max_dates
        )
    )


def sync_clv_tracker(args: argparse.Namespace) -> None:
    _print_json(sync_clv_tracker_for_date(args.date))


def sync_combo_tracker(args: argparse.Namespace) -> None:
    _print_json(sync_combo_tracker_for_date(args.date))


def build_lowtier_corpus(args: argparse.Namespace) -> None:
    """Walk the TennisExplorer scoreboard into player_match_history.

    The Sackmann/TennisMyLife files carry no ITF at all, so without this Elo
    reaches 1.2% of ITF fixtures while ITF is ~85% of the board we price.
    """
    from tennis_wc.ingestion.ingest_tennisexplorer_history import (
        ingest_tennisexplorer_history,
    )

    summary = ingest_tennisexplorer_history(args.start, args.end)
    _print_json(summary)


def validate_data(args: argparse.Namespace) -> None:
    """Report every warehouse check; exit non-zero when a critical one fails."""
    from tennis_wc.database.db import get_connection
    from tennis_wc.validation import checks

    conn = get_connection()
    results = checks.run_checks(conn)
    payload = {
        "checks": [
            {"name": r.name, "passed": r.passed, "severity": r.severity,
             "detail": r.detail, "count": r.count}
            for r in results
        ],
        "critical_failures": [r.name for r in checks.critical_failures(results)],
    }
    _print_json(payload)
    if payload["critical_failures"] and getattr(args, "strict", False):
        raise SystemExit(1)


def settle_props(args: argparse.Namespace) -> None:
    from tennis_wc.database.db import get_connection
    from tennis_wc.props.settlement import (
        settle_props as _settle, prop_roi_report, model_vs_market_scorecard,
    )
    conn = get_connection()
    graded = _settle(conn)
    _print_json({
        "graded": graded,
        "scorecard": model_vs_market_scorecard(conn),
        "roi": prop_roi_report(conn),
    })


def weekly_review(args: argparse.Namespace) -> None:
    from tennis_wc.reports.weekly_review import generate_weekly_review, render_weekly_review

    if getattr(args, "print", False):
        print(render_weekly_review(args.date))
        return
    path = generate_weekly_review(args.date)
    print(render_weekly_review(args.date))
    print(f"\nwritten: {path}")


def tier_roi(_: argparse.Namespace) -> None:
    _print_json(tier_roi_summary())


def combo_roi(_: argparse.Namespace) -> None:
    _print_json(combo_roi_summary())


def calibration_report(args: argparse.Namespace) -> None:
    _print_json(banker_calibration_summary(args.min_samples))


def market_validation_report(args: argparse.Namespace) -> None:
    _print_json(market_validation_summary(args.min_samples))


def aces_prop_sanity(args: argparse.Namespace) -> None:
    _print_json(aces_prop_sanity_for_date(args.date, args.min_history))


def train_ml(_: argparse.Namespace) -> None:
    _print_json(train_ml_baseline())


def review_date(args: argparse.Namespace) -> None:
    _print_json(review_date_entry(args.date))


def backtest(args: argparse.Namespace) -> None:
    _print_json(run_backtest(args.start, args.end))


def external_backtest(args: argparse.Namespace) -> None:
    from tennis_wc.modelling.external_backtest import run_match_winner_backtest

    years = [int(y) for y in str(args.years).split(",") if y.strip()]
    tours = tuple(t.strip().upper() for t in str(args.tours).split(",") if t.strip())
    _print_json(
        run_match_winner_backtest(
            years,
            tours=tours,
            k_factor=None if args.flat_k is None else float(args.flat_k),
            min_edge=args.min_edge,
        )
    )


def _distinct_market_keys_for_date(match_date: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT mo.market_key)
            FROM market_odds_snapshots mo
            JOIN matches m ON m.id = mo.match_id
            WHERE m.match_date = ?
            """,
            (match_date,),
        ).fetchone()
    return int(row[0] or 0)


def _sportsbet_odds_rows_for_date(match_date: str) -> int:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*)
            FROM odds_snapshots o
            JOIN matches m ON m.id = o.match_id
            WHERE m.match_date = ?
              AND o.source_provider = 'sportsbet'
            """,
            (match_date,),
        ).fetchone()
    return int(row[0] or 0)


def _publish_daily_dashboard(args: argparse.Namespace, payload: dict) -> dict:
    """Apply the shared completeness gate, then publish a ready daily card."""
    # Which day this analysis is FOR decides how an empty board reads: on a
    # next-day warm pass the book simply is not open, on the same day it means
    # we have lost sight of it. One definition of that, shared with the
    # scheduler, because the two disagreeing is how the distinction went
    # missing for three days.
    from tennis_wc.pipeline_readiness import analysis_readiness, horizon_for

    readiness = analysis_readiness(payload, horizon=horizon_for(args.date))
    retry_reasons = readiness["reasons"]
    payload["readiness"] = {
        # `status` keeps its two-word vocabulary because the report renderer
        # reads it; `severity` is the new information, carried alongside.
        "status": "ready" if readiness["publishable"] else "incomplete",
        "severity": readiness["severity"],
        "horizon": readiness["horizon"],
        "reasons": retry_reasons,
        "observed": readiness["observed"],
    }
    if retry_reasons:
        payload["cloudflare_deploy"] = {
            "attempted": False,
            "status": "blocked_by_completeness_gate",
        }
        print(
            "⏭️ Cloudflare deploy blocked: analysis completeness gate failed — "
            + "; ".join(retry_reasons)
        )
        return payload

    try:
        deployed = run_post_success_cloudflare_deploy(
            source="Tennis Wong Choi",
            target_dir=analysis_output_dir(args.date),
            skip=args.skip_cloudflare_deploy,
            # Dashboard publication is downstream of the completed card. On
            # 2026-08-13 a Google Drive permission error here erased a valid
            # 65/89-priced scheduled card before HEALTH_JSON could be written.
            allow_failure=True,
        )
    except Exception as exc:  # noqa: BLE001 - deploy is explicitly non-fatal
        payload["cloudflare_deploy"] = {
            "attempted": not args.skip_cloudflare_deploy,
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        print(
            "⚠️ Cloudflare deploy failed after a complete analysis; "
            f"card remains valid: {type(exc).__name__}: {exc}"
        )
        return payload
    payload["cloudflare_deploy"] = {
        "attempted": not args.skip_cloudflare_deploy,
        "status": (
            "skipped" if args.skip_cloudflare_deploy
            else "deployed" if deployed
            else "failed"
        ),
    }
    return payload


def _record_daily_evidence(
    args: argparse.Namespace,
    payload: dict,
    report_path: Path,
    predictions: list[dict],
) -> dict:
    """Freeze the priced card and link its decision before publication."""
    # The report path is the canonical local artifact returned by
    # ``generate_daily_report``.  ``analysis_output_dir`` may point at the
    # Google Drive mirror, whose FileProvider inode can raise EDEADLK during an
    # immediate read-back even after the best-effort copy succeeded.  Evidence
    # must therefore freeze the local source, never the mirror.
    output_dir = report_path.expanduser().resolve().parent
    snapshot = create_immutable_snapshot(
        output_dir,
        domain=Domain.TENNIS.value,
        event_id=args.date,
        patterns=[Path(report_path).name],
        recommendations=predictions,
    )
    evidence_root = Path(
        os.environ.get(
            "WC_EVIDENCE_ROOT",
            "~/WongChoiData/WongChoiControl/evidence",
        )
    ).expanduser()
    decision_state = (
        DecisionState.RECOMMEND
        if any(
            str(item.get("final_decision") or "").upper() == "BET"
            for item in predictions
        )
        else DecisionState.NO_BET
    )
    evidence = record_prediction_decision_if_configured(
        domain=Domain.TENNIS,
        event_id=args.date,
        snapshot=snapshot,
        evidence_root=evidence_root,
        decision_state=decision_state,
        recommendations=predictions,
    )
    payload["prediction_snapshot"] = str(snapshot)
    payload["prediction_evidence"] = evidence
    return evidence


def run_daily(args: argparse.Namespace) -> None:
    provider_healthcheck(args)
    source_errors = []
    stage_timings: list[dict] = []
    clear_pipeline_source_errors(args.date)
    # Settle any past dates still holding PENDING tracker rows BEFORE today's
    # report, so the prop scorecard/ROI blocks reflect the freshest sample.
    # Kept inside run-daily (not only the scheduler wrapper) so a manual run
    # also records + settles — the 06-19..07-08 tracking gap must not recur.
    settlement_backlog: dict = {}
    try:
        settlement_backlog = _run_timed_stage(
            "settlement_backlog",
            lambda: settle_pending_backlog(args.date),
            stage_timings,
        )
    except Exception as exc:  # noqa: BLE001
        source_errors.append({"source": "settlement_backlog", "error": str(exc)})
    if args.mvp_snapshot:
        os.environ["DATA_MAX_STALENESS_MINUTES_ODDS"] = str(24 * 60)
        try:
            _run_timed_stage(
                "metadata_backfill",
                lambda: backfill_confirmed_metadata_for_date(args.date),
                stage_timings,
            )
        except Exception as exc:
            source_errors.append({"source": "metadata_backfill", "error": str(exc)})
    else:
        current_year = int(args.date[:4])
        for label, step in (
            ("tournaments", lambda: ingest_tournaments(args.date, args.date)),
            ("rankings_atp", lambda: ingest_rankings("ATP", args.date)),
            ("rankings_wta", lambda: ingest_rankings("WTA", args.date)),
            ("history", lambda: ingest_default_history(args.date)),
            # TML challenger/quali season files are live-updated: re-pull the
            # current year daily (upsert dedup) so Challenger players keep a
            # fresh history, then rebuild Elo so today's ratings include it
            # (previously Elo only advanced when build-sackmann-elo was run by
            # hand — ratings were frozen at the last manual build).
            ("history_lowtier", lambda: ingest_tml_low_tier_history(current_year, current_year)),
            ("elo_rebuild", lambda: build_sackmann_elo()),
            ("upcoming_matches", lambda: ingest_upcoming_matches(args.date)),
            ("odds", lambda: ingest_odds(args.date)),
            ("event_markets", lambda: enrich_sportsbet_event_markets(args.date)),
            ("metadata_backfill", lambda: backfill_confirmed_metadata_for_date(args.date)),
        ):
            try:
                _run_timed_stage(label, step, stage_timings)
            except Exception as exc:
                source_errors.append({"source": label, "error": str(exc)})
        # Guard: confirm the per-event enrichment actually captured multi-market
        # odds. If a day ends up with only match-winner, combos collapse — make it
        # a loud, surfaced warning rather than a silent gap.
        try:
            odds_rows = _sportsbet_odds_rows_for_date(args.date)
            market_keys = _distinct_market_keys_for_date(args.date)
            if odds_rows > 0 and market_keys <= 1:
                source_errors.append(
                    {
                        "source": "event_markets",
                        "error": "only_match_winner_odds_captured__multi_market_enrichment_incomplete",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            source_errors.append({"source": "event_markets_check", "error": str(exc)})

    store_raw_response(
        "tennis_wc_pipeline",
        "/run-daily/source-errors",
        {"date": args.date},
        {"mode": "mvp_snapshot" if args.mvp_snapshot else "live_full", "errors": source_errors},
        207 if source_errors else 200,
        "run_daily_source_errors",
        args.date,
    )
    # Fold split identities together BEFORE features are built, because features
    # are what read a player's history and a split player has none to read.
    #
    # The machinery for this existed, fully written and fully tested, with
    # safeguards that refuse to merge two ids that faced each other or whose
    # records sit on different tours -- and nothing in the codebase called it.
    # Measured 2026-08-25: 936 groups were waiting, and 76 players had a
    # FIXTURE or a priced prop sitting on a brand-new id with zero history
    # while a sibling id held 80 to 261 matches. Alexander Ritschard was priced
    # as a player with no record at all against his own 261-match history.
    #
    # Idempotent, so running it daily costs nothing once the backlog is gone.
    # Failure is non-fatal: a merge that cannot run is worth a source error,
    # not a lost card.
    try:
        _run_timed_stage(
            "identity_merge",
            lambda: _merge_player_identities(),
            stage_timings,
        )
    except Exception as exc:  # noqa: BLE001
        source_errors.append({"source": "identity_merge", "error": str(exc)})
    snapshots = _run_timed_stage(
        "feature_snapshots",
        lambda: build_sportsbet_feature_snapshots_for_date(args.date),
        stage_timings,
    )
    valid = [snapshot for snapshot in snapshots if snapshot["data_quality"]["is_valid"]]

    def price_and_review() -> list[dict]:
        output = []
        for snapshot in snapshots:
            pricing = price_match_snapshot(snapshot)
            filter_result = apply_bet_filter(snapshot, pricing)
            prediction_id = store_prediction(
                snapshot["match_id"]["value"], snapshot["feature_set_version"],
                pricing, filter_result,
            )
            agent_output = run_agent_reviews(snapshot, pricing, filter_result)
            output.append(
                {
                    "id": prediction_id,
                    "decision": filter_result["decision"],
                    "final_decision": agent_output["final_decision"],
                    "edge": pricing.get("edge"),
                }
            )
        return output

    predictions = _run_timed_stage(
        "pricing_and_review", price_and_review, stage_timings
    )
    report_path = _run_timed_stage(
        "daily_report", lambda: generate_daily_report(args.date), stage_timings
    )
    # Record today's recommendations in the trackers as part of the pipeline
    # itself. Previously only the scheduler wrapper did this, so manual runs
    # left no CLV/combo rows behind (nothing to settle or measure later).
    tracker_sync: dict = {}
    try:
        tracker_sync = _run_timed_stage(
            "tracker_sync",
            lambda: {
                "clv": sync_clv_tracker_for_date(args.date),
                "combo": sync_combo_tracker_for_date(args.date),
            },
            stage_timings,
        )
    except Exception as exc:  # noqa: BLE001
        source_errors.append({"source": "tracker_sync", "error": str(exc)})
    payload = {
        "date": args.date,
        "matches_analysed": len(snapshots),
        "valid_feature_snapshots": len(valid),
        "invalid_due_to_data_issue": len(snapshots) - len(valid),
        "odds_coverage": odds_coverage_for_date(args.date),
        "predictions": predictions,
        "analysis_dir": str(analysis_output_dir(args.date)),
        "report_path": str(report_path),
        "source_errors": source_errors,
        "settlement_backlog": settlement_backlog,
        "tracker_sync": tracker_sync,
        "stage_timings": stage_timings,
        "stage": "7",
        "mode": "mvp_snapshot" if args.mvp_snapshot else "live_full",
    }
    try:
        _run_timed_stage(
            "prediction_evidence",
            lambda: _record_daily_evidence(
                args, payload, Path(report_path), predictions
            ),
            stage_timings,
        )
    except Exception as exc:  # noqa: BLE001 - evidence failure must block publish
        payload["prediction_evidence"] = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
        }
        source_errors.append(
            {
                "source": "prediction_evidence",
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    _run_timed_stage(
        "dashboard_publish",
        lambda: _publish_daily_dashboard(args, payload),
        stage_timings,
    )
    _print_json(payload)


def _merge_player_identities() -> dict:
    """Apply every merge the identity planner is confident about.

    The planner is the authority on what is safe: it refuses ids that played
    each other and ids whose derived tours differ, and it picks the canonical id
    by history depth so the richest record wins. This only executes what it
    already decided.
    """
    from tennis_wc.database.db import get_connection
    from tennis_wc.identity.player_identity import (
        apply_merges, ensure_identity_schema, plan_merges,
    )

    with get_connection() as conn:
        ensure_identity_schema(conn)
        plans = plan_merges(conn)
        confident = [plan for plan in plans if plan.reason == "merge"]
        if not confident:
            return {"groups": 0, "refused": len(plans)}
        summary = apply_merges(conn, confident)
        summary["refused"] = len(plans) - len(confident)
        return summary


def _run_timed_stage(label: str, step, timings: list[dict], *, clock=time.perf_counter):
    """Run one pipeline stage and always append a machine-readable duration."""
    started = clock()
    status = "ok"
    try:
        return step()
    except Exception:
        status = "failed"
        raise
    finally:
        timings.append({
            "stage": label,
            "status": status,
            "seconds": round(max(0.0, clock() - started), 3),
        })


def init_db_command(_: argparse.Namespace) -> None:
    init_db()
    print("ok")


def _not_built(args: argparse.Namespace) -> None:
    raise SystemExit(f"{args.command} belongs to a later stage and is not built in Stage 1-3.")


def _redacted(value: str) -> str:
    if not value:
        return "<missing>"
    if len(value) <= 6:
        return "<set>"
    return f"{value[:3]}...{value[-3:]}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tennis-wc")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db").set_defaults(func=init_db_command)
    sub.add_parser("provider-healthcheck").set_defaults(func=provider_healthcheck)
    sub.add_parser("network-check").set_defaults(func=network_check)
    sub.add_parser("config-check").set_defaults(func=config_check)

    p = sub.add_parser("provider-smoke")
    p.add_argument("--provider", required=True, choices=["tennis", "odds"])
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--tour", default="ATP", choices=["ATP", "WTA"])
    p.set_defaults(func=provider_smoke)

    p = sub.add_parser("fetch-upcoming-matches")
    p.add_argument("--date", required=True)
    p.set_defaults(func=fetch_upcoming_matches)

    p = sub.add_parser("fetch-tournaments")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.set_defaults(func=fetch_tournaments)

    p = sub.add_parser("fetch-rankings")
    p.add_argument("--tour", required=True, choices=["ATP", "WTA"])
    p.add_argument("--date")
    p.set_defaults(func=fetch_rankings)

    p = sub.add_parser("fetch-player-stats")
    p.add_argument("--player-id", required=True)
    p.set_defaults(func=fetch_player_stats)

    p = sub.add_parser("bootstrap-sackmann-history")
    p.add_argument("--start-year", required=True, type=int)
    p.add_argument("--end-year", required=True, type=int)
    p.add_argument("--tours", default="ATP,WTA")
    p.set_defaults(func=bootstrap_sackmann_history)

    p = sub.add_parser("bootstrap-lowtier-history")
    p.add_argument("--start-year", required=True, type=int)
    p.add_argument("--end-year", required=True, type=int)
    p.add_argument("--no-quali", action="store_true")
    p.set_defaults(func=bootstrap_lowtier_history)

    p = sub.add_parser("ingest-tennismylife-results")
    p.add_argument("--date")
    p.add_argument("--start")
    p.add_argument("--end")
    p.set_defaults(func=ingest_tennismylife)

    p = sub.add_parser("build-sackmann-elo")
    p.add_argument("--initial-rating", type=float, default=1500.0)
    p.add_argument("--k-factor", type=float, default=32.0)
    p.set_defaults(func=build_elo)

    p = sub.add_parser("calibrate-sackmann-elo")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--initial-rating", type=float, default=1500.0)
    p.add_argument("--k-factor", type=float, default=32.0)
    p.set_defaults(func=calibrate_elo)

    p = sub.add_parser("fetch-odds")
    p.add_argument("--date", required=True)
    p.set_defaults(func=fetch_odds)

    p = sub.add_parser("sportsbet-urls")
    p.add_argument("--date", required=True)
    p.set_defaults(func=sportsbet_urls)

    p = sub.add_parser("fetch-event-odds")
    p.add_argument("--event-id", required=True)
    p.add_argument("--match-id", type=int)
    p.set_defaults(func=fetch_event_odds)

    p = sub.add_parser("enrich-event-markets")
    p.add_argument("--date", required=True)
    p.set_defaults(func=enrich_event_markets)

    p = sub.add_parser("probe-event-markets")
    p.add_argument("--date", required=True)
    p.add_argument("--limit", type=int)
    p.set_defaults(func=probe_event_markets)

    p = sub.add_parser("build-features")
    p.add_argument("--date", required=True)
    p.set_defaults(func=build_features)

    p = sub.add_parser("backfill-metadata")
    p.add_argument("--date", required=True)
    p.set_defaults(func=backfill_metadata)

    p = sub.add_parser("metadata-audit")
    p.add_argument("--date", required=True)
    p.set_defaults(func=metadata_audit)

    p = sub.add_parser("validate-provenance")
    p.add_argument("--date", required=True)
    p.set_defaults(func=validate_provenance)

    p = sub.add_parser("run-daily")
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--mvp-snapshot", action="store_true", help="Use existing Sportsbet/local snapshots without live source refresh.")
    p.add_argument("--skip-cloudflare-deploy", action="store_true", help="Do not refresh the Cloudflare dashboard after a successful daily run.")
    p.set_defaults(func=run_daily)

    p = sub.add_parser("predict-daily")
    p.add_argument("--date", required=True)
    p.set_defaults(func=predict_daily)

    p = sub.add_parser("run-agents")
    p.add_argument("--date", required=True)
    p.set_defaults(func=run_agents_command)

    p = sub.add_parser("generate-report")
    p.add_argument("--date", required=True)
    p.add_argument("--match-id", type=int)
    p.set_defaults(func=generate_report)

    sub.add_parser("performance-report").set_defaults(func=performance_report)

    p = sub.add_parser("record-bet")
    p.add_argument("--prediction-id", required=True, type=int)
    p.add_argument("--odds", required=True, type=float)
    p.add_argument("--stake", required=True, type=float)
    p.set_defaults(func=record_bet)

    p = sub.add_parser(
        "record-live-prop-bet",
        help="Record a player-prop wager already placed by hand; never places it.",
    )
    p.add_argument("--prop-id", required=True, type=int)
    p.add_argument("--odds", required=True, type=float)
    p.add_argument("--stake-aud", required=True, type=float)
    p.add_argument("--placed-at")
    p.add_argument("--notes")
    p.set_defaults(func=record_live_prop_bet_command)

    p = sub.add_parser("fetch-closing-odds")
    p.add_argument("--date", required=True)
    p.set_defaults(func=fetch_closing_odds)

    p = sub.add_parser("settle-bets")
    p.add_argument("--date", required=True)
    p.set_defaults(func=settle_bets)

    p = sub.add_parser("settle-backlog")
    p.add_argument("--date", required=True, help="Settle PENDING rows on dates before this one.")
    p.add_argument("--lookback-days", type=int, default=30)
    p.add_argument("--max-dates", type=int, default=10)
    p.set_defaults(func=settle_backlog)

    p = sub.add_parser("sync-clv-tracker")
    p.add_argument("--date", required=True)
    p.set_defaults(func=sync_clv_tracker)

    p = sub.add_parser("sync-combo-tracker")
    p.add_argument("--date", required=True)
    p.set_defaults(func=sync_combo_tracker)

    sub.add_parser("tier-roi").set_defaults(func=tier_roi)
    sub.add_parser("combo-roi").set_defaults(func=combo_roi)
    sub.add_parser("settle-props").set_defaults(func=settle_props)

    p = sub.add_parser("build-lowtier-corpus")
    p.add_argument("--start", required=True, help="First scoreboard date, YYYY-MM-DD.")
    p.add_argument("--end", help="Last date (default: same as --start).")
    p.set_defaults(func=build_lowtier_corpus)

    p = sub.add_parser("validate-data")
    p.add_argument("--strict", action="store_true",
                   help="Exit non-zero when any critical check fails.")
    p.set_defaults(func=validate_data)

    p = sub.add_parser(
        "prune-raw-responses",
        help="Blank superseded full-replacement API payloads (keeps the rows).",
    )
    p.add_argument("--keep-days", type=int, default=7,
                   help="Never blank a body fetched within this window (default 7).")
    p.add_argument("--dry-run", action="store_true",
                   help="Report what would be freed and change nothing.")
    p.add_argument("--vacuum", action="store_true",
                   help="Rebuild the file afterwards to return the pages to disk. "
                        "Needs free space for a second copy of the database.")
    p.set_defaults(func=prune_raw_responses)

    p = sub.add_parser("weekly-review")
    p.add_argument("--date", required=True, help="As-of date; report lands in that date's analysis folder.")
    p.add_argument("--print", action="store_true", help="Print only, do not write the file.")
    p.set_defaults(func=weekly_review)

    p = sub.add_parser("calibration-report")
    p.add_argument("--min-samples", type=int, default=10)
    p.set_defaults(func=calibration_report)

    p = sub.add_parser("market-validation-report")
    p.add_argument("--min-samples", type=int, default=20)
    p.set_defaults(func=market_validation_report)

    p = sub.add_parser("aces-prop-sanity")
    p.add_argument("--date", required=True)
    p.add_argument("--min-history", type=int, default=10)
    p.set_defaults(func=aces_prop_sanity)

    sub.add_parser("train-ml-baseline").set_defaults(func=train_ml)

    p = sub.add_parser("review-date")
    p.add_argument("--date", required=True)
    p.set_defaults(func=review_date)

    p = sub.add_parser("backtest")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.set_defaults(func=backtest)

    p = sub.add_parser("external-backtest", help="Walk-forward match-winner backtest vs tennis-data.co.uk Pinnacle closing odds")
    p.add_argument("--years", default="2022,2023,2024", help="comma-separated seasons")
    p.add_argument("--tours", default="ATP,WTA")
    p.add_argument("--min-edge", type=float, default=0.03)
    p.add_argument("--flat-k", type=float, default=None, help="force a flat Elo K (omit for production decayed-K)")
    p.set_defaults(func=external_backtest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
