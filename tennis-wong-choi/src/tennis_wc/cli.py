"""Manual commands. Scheduled runs use scripts/tennis_daily_schedule.py.

  tennis-wc init-db
  tennis-wc config-check | network-check
  tennis-wc price  --date YYYY-MM-DD     the full analysis for one date
  tennis-wc review --date YYYY-MM-DD     fetch results and settle
  tennis-wc featured --date D --label L  record 精選 for a date (no Telegram)
  tennis-wc record-live-prop-bet ...     record a wager Kelvin placed by hand
"""
from __future__ import annotations

import argparse
import json
from datetime import date


def _print(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


def _redacted(value: str | None) -> str:
    if not value:
        return "<missing>"
    return f"{value[:3]}...{value[-3:]}" if len(value) > 6 else "***"


def config_check(_args) -> None:
    from tennis_wc.config import get_settings

    s = get_settings()
    _print({"database_url": s.database_url, "tennis_provider": s.tennis_provider,
            "tennis_api_key": _redacted(s.tennis_api_key), "odds_provider": s.odds_provider,
            "sportsbet_source_mode": s.sportsbet_source_mode})


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="tennis-wc", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    def add(name, func, *arguments):
        p = sub.add_parser(name)
        for flags, kwargs in arguments:
            p.add_argument(*flags, **kwargs)
        p.set_defaults(func=func)

    def init_db(_args):
        from tennis_wc.store.migrations import init_db as run
        run()
        print("ok")

    def network_check(_args):
        from tennis_wc.diagnostics import run_network_check
        _print(run_network_check())

    def price(args):
        from tennis_wc.run import price_day
        _print(price_day(args.date, today=date.today().isoformat()))

    def review(args):
        from tennis_wc.run import review_day
        _print(review_day(args.date))

    def featured(args):
        from tennis_wc.store.db import get_connection
        from tennis_wc.select.featured import record
        with get_connection() as conn:
            _print(record(conn, args.date, args.label))

    def live_bet(args):
        from tennis_wc.store.live_bets import record_live_prop_bet
        _print(record_live_prop_bet(prop_id=args.prop_id, odds_taken=args.odds, stake_aud=args.stake_aud,
                                    placed_at=args.placed_at, notes=args.notes))

    day = (("--date",), {"required": True})
    add("init-db", init_db)
    add("config-check", config_check)
    add("network-check", network_check)
    add("price", price, day)
    add("review", review, day)
    add("featured", featured, day, (("--label",), {"default": "manual"}))
    add("record-live-prop-bet", live_bet,
        (("--prop-id",), {"required": True, "type": int}), (("--odds",), {"required": True, "type": float}),
        (("--stake-aud",), {"required": True, "type": float}), (("--placed-at",), {}), (("--notes",), {}))
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
