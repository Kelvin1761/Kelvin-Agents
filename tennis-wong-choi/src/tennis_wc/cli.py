from __future__ import annotations

import argparse
import json
import os
from datetime import date

from tennis_wc.database.db import get_connection
from tennis_wc.database.migrations import init_db
from tennis_wc.diagnostics import run_network_check
from tennis_wc.features.data_quality import validate_data_freshness
from tennis_wc.features.feature_builder import build_feature_snapshots_for_date, build_sportsbet_feature_snapshots_for_date
from tennis_wc.ingestion.ingest_matches import ingest_default_history, ingest_upcoming_matches
from tennis_wc.ingestion.ingest_odds import (
    enrich_sportsbet_event_markets,
    ingest_event_odds,
    ingest_odds,
    probe_sportsbet_event_markets,
)
from tennis_wc.ingestion.ingest_player_stats import ingest_player_stats
from tennis_wc.ingestion.ingest_rankings import ingest_rankings
from tennis_wc.ingestion.raw_response_store import store_raw_response
from tennis_wc.ingestion.ingest_sackmann import ingest_sackmann_history
from tennis_wc.ingestion.ingest_tournaments import ingest_tournaments
from tennis_wc.betting.bet_filter import apply_bet_filter
from tennis_wc.betting.ledger import (
    fetch_closing_odds_for_date,
    ledger_summary,
    record_bet as record_bet_entry,
    settle_bets_for_date,
)
from tennis_wc.agents.runner import run_agents as run_agent_reviews
from tennis_wc.modelling.backtester import run_backtest
from tennis_wc.modelling.calibration import calibrate_sackmann_elo
from tennis_wc.modelling.elo_builder import build_sackmann_elo
from tennis_wc.modelling.prediction_store import store_prediction
from tennis_wc.modelling.pricing import price_match_snapshot
from tennis_wc.providers import get_news_provider, get_odds_provider, get_tennis_provider
from tennis_wc.reports.daily_report import analysis_output_dir, clear_pipeline_source_errors, generate_daily_report
from tennis_wc.reports.match_report import render_match_report
from tennis_wc.reports.performance_report import prediction_summary
from tennis_wc.config import get_settings


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


def performance_report(_: argparse.Namespace) -> None:
    _print_json({"predictions": prediction_summary(), "ledger": ledger_summary()})


def record_bet(args: argparse.Namespace) -> None:
    bet_id = record_bet_entry(args.prediction_id, args.odds, args.stake)
    _print_json({"bet_id": bet_id, "prediction_id": args.prediction_id})


def fetch_closing_odds(args: argparse.Namespace) -> None:
    count = fetch_closing_odds_for_date(args.date)
    _print_json({"date": args.date, "closing_odds_snapshots": count})


def settle_bets(args: argparse.Namespace) -> None:
    _print_json(settle_bets_for_date(args.date))


def backtest(args: argparse.Namespace) -> None:
    _print_json(run_backtest(args.start, args.end))


def run_daily(args: argparse.Namespace) -> None:
    provider_healthcheck(args)
    source_errors = []
    clear_pipeline_source_errors(args.date)
    if args.mvp_snapshot:
        os.environ["DATA_MAX_STALENESS_MINUTES_ODDS"] = str(24 * 60)
    else:
        for label, step in (
            ("tournaments", lambda: ingest_tournaments(args.date, args.date)),
            ("rankings_atp", lambda: ingest_rankings("ATP", args.date)),
            ("rankings_wta", lambda: ingest_rankings("WTA", args.date)),
            ("history", lambda: ingest_default_history(args.date)),
            ("upcoming_matches", lambda: ingest_upcoming_matches(args.date)),
            ("odds", lambda: ingest_odds(args.date)),
            ("event_markets", lambda: enrich_sportsbet_event_markets(args.date)),
        ):
            try:
                step()
            except Exception as exc:
                source_errors.append({"source": label, "error": str(exc)})
    
    store_raw_response(
        "tennis_wc_pipeline",
        "/run-daily/source-errors",
        {"date": args.date},
        source_errors,
        207 if source_errors else 200,
        "run_daily_source_errors",
        args.date,
    )
    snapshots = build_sportsbet_feature_snapshots_for_date(args.date)
    valid = [snapshot for snapshot in snapshots if snapshot["data_quality"]["is_valid"]]
    predictions = []
    for snapshot in snapshots:
        pricing = price_match_snapshot(snapshot)
        filter_result = apply_bet_filter(snapshot, pricing)
        prediction_id = store_prediction(snapshot["match_id"]["value"], snapshot["feature_set_version"], pricing, filter_result)
        agent_output = run_agent_reviews(snapshot, pricing, filter_result)
        predictions.append(
            {
                "id": prediction_id,
                "decision": filter_result["decision"],
                "final_decision": agent_output["final_decision"],
                "edge": pricing.get("edge"),
            }
        )
    report_path = generate_daily_report(args.date)
    _print_json(
        {
            "date": args.date,
            "matches_analysed": len(snapshots),
            "valid_feature_snapshots": len(valid),
            "invalid_due_to_data_issue": len(snapshots) - len(valid),
            "predictions": predictions,
            "analysis_dir": str(analysis_output_dir(args.date)),
            "report_path": str(report_path),
            "source_errors": source_errors,
            "stage": "7",
            "mode": "mvp_snapshot" if args.mvp_snapshot else "live_full",
        }
    )


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

    p = sub.add_parser("validate-provenance")
    p.add_argument("--date", required=True)
    p.set_defaults(func=validate_provenance)

    p = sub.add_parser("run-daily")
    p.add_argument("--date", default=date.today().isoformat())
    p.add_argument("--mvp-snapshot", action="store_true", help="Use existing Sportsbet/local snapshots without live source refresh.")
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

    p = sub.add_parser("fetch-closing-odds")
    p.add_argument("--date", required=True)
    p.set_defaults(func=fetch_closing_odds)

    p = sub.add_parser("settle-bets")
    p.add_argument("--date", required=True)
    p.set_defaults(func=settle_bets)

    p = sub.add_parser("backtest")
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.set_defaults(func=backtest)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
