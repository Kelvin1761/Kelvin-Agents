#!/usr/bin/env python3
"""Rolling reliability (calibration) of the live probability, from the market ledger.

Monitoring only: it reads settled legs, never changes a projection or pick.
A window with too few settled legs reports `insufficient_n`, not "ok".

Why it exists: EXP-20261022-03 found the old engine said ~88% where ~60% came
true, and the calibration layer that replaced it was fitted on playoff data only.
This is the daily check that the fix keeps holding on live legs.

Alert rule (fixed, not tuned): overall |mean(p) - hit rate| > 10pp, or the
p >= 0.8 band off by > 10pp with >= 30 legs, once >= 100 legs are settled.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import nba_market_ledger as ledger

WINDOW_DAYS = 30
# First analysis date whose ledger rows carry the calibrated probability layer
# (EXP-20261022-03, commit bc5b1d2a, merged 2026-10-22 23:07 +11).  Older rows come
# from the legacy engine (the one that said ~88% for ~60%); judging the live layer on
# them would alarm forever.  Changing this date changes what the alert means.
CALIBRATION_EPOCH = "2026-10-23"
MIN_SETTLED = 100
HIGH_BAND = 0.8
MIN_HIGH_BAND = 30
ALERT_GAP = 0.10
MARKET_LABELS = {"pts": "PTS", "reb": "REB", "ast": "AST", "3pm": "3PM", "fg3m": "3PM", "threes_made": "3PM", "stl": "STL", "blk": "BLK"}


def _summ(buckets: list[dict]) -> dict:
    n = sum(b["n"] for b in buckets)
    if not n:
        return {"n": 0, "mean_p": None, "hit_rate": None, "gap": None}
    mean_p = sum(b["mean_p"] * b["n"] for b in buckets) / n
    hit = sum(b["hit_rate"] * b["n"] for b in buckets) / n
    return {"n": n, "mean_p": round(mean_p, 4), "hit_rate": round(hit, 4), "gap": round(mean_p - hit, 4)}


def _high(buckets: list[dict]) -> dict:
    return _summ([b for b in buckets if float(b["bucket"].split("-")[0]) >= HIGH_BAND])


def _section(root: Path, since: str, until: str) -> dict:
    report = ledger.evaluate(root=root, since=since, until=until)
    overall = report["overall"]
    buckets = overall["variants"]["p_final"]["calibration"]
    picked = report["by_picked"].get("picked")
    return {
        "since": since, "until": until,
        "overall": _summ(buckets), "high_band": _high(buckets),
        "market_raw_close": _summ(overall.get("market_raw_close_calibration") or []),
        "picked": _summ(picked["variants"]["p_final"]["calibration"]) if picked else _summ([]),
        "by_stat": {MARKET_LABELS.get(m, m): _summ(sec["variants"]["p_final"]["calibration"])
                    for m, sec in report["by_market"].items()},
        "buckets": buckets,
    }


def build(until: str, root: Path | None = None, window_days: int = WINDOW_DAYS,
          epoch: str = CALIBRATION_EPOCH) -> dict:
    """Alert status comes from the calibrated-layer epoch only; the all-engine window is context."""
    root = root or ledger.ledger_root()
    since = (date.fromisoformat(until) - timedelta(days=window_days - 1)).isoformat()
    live = _section(root, max(since, epoch), until) if until >= epoch else None
    legacy_mixed = _section(root, since, until)
    cur = live or {"overall": _summ([]), "high_band": _summ([]), "market_raw_close": _summ([]),
                   "picked": _summ([]), "by_stat": {}, "buckets": [], "since": epoch, "until": until}
    total, high = cur["overall"], cur["high_band"]
    if total["n"] < MIN_SETTLED:
        status = "insufficient_n"
    elif abs(total["gap"]) > ALERT_GAP or (high["n"] >= MIN_HIGH_BAND and abs(high["gap"]) > ALERT_GAP):
        status = "alert"
    else:
        status = "ok"
    return {
        "until": until, "since": cur["since"], "window_days": window_days, "epoch": epoch, "status": status,
        "min_settled": MIN_SETTLED, "alert_gap": ALERT_GAP,
        "overall": total, "high_band": high, "market_raw_close": cur["market_raw_close"],
        "picked": cur["picked"], "by_stat": cur["by_stat"], "buckets": cur["buckets"],
        "all_engines_context": {k: legacy_mixed[k] for k in ("since", "overall", "high_band")},
        "note": "legs inside one game are correlated; n is legs, not independent clusters; "
                "alert uses only rows from the calibrated layer epoch",
    }


def write(report: dict, root: Path | None = None) -> Path:
    root = root or ledger.ledger_root()
    out = root / "reports"
    out.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (out / f"reliability_{report['until']}.json").write_text(text, encoding="utf-8")
    latest = out / "reliability_latest.json"
    latest.write_text(text, encoding="utf-8")
    return latest


def _pct(x: Any) -> str:
    return "N/A" if x is None else f"{x * 100:.0f}%"


def message_lines(report: dict) -> list[str]:
    o, h, m = report["overall"], report["high_band"], report["market_raw_close"]
    head = f"📐 機率校準（校準層上線後 {report['since']} 起，已結算 {o['n']} 腿）"
    if report["status"] == "insufficient_n":
        return [head, f"樣本未夠（要 ≥{report['min_settled']} 腿）先判斷；暫時只記錄，唔作結論。"]
    lines = [head, f"預測 {_pct(o['mean_p'])}／實際 {_pct(o['hit_rate'])}（差 {o['gap'] * 100:+.0f}pp）"
             f"｜市場隱含 {_pct(m['mean_p'])}"]
    if h["n"]:
        lines.append(f"p≥80% 區：預測 {_pct(h['mean_p'])}／實際 {_pct(h['hit_rate'])}（{h['n']} 腿，差 {h['gap'] * 100:+.0f}pp）")
    stats = "｜".join(f"{k} {_pct(v['mean_p'])}→{_pct(v['hit_rate'])}" for k, v in report["by_stat"].items() if v["n"] >= 20)
    if stats:
        lines.append("按 stat（預測→實際）：" + stats)
    if report["status"] == "alert":
        lines.append("⚠️ 校準警報：預測同實際差超過 10pp。先查數據管線，唔好即刻調模型。")
    return lines


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="NBA rolling reliability")
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build(args.date)
    if args.write:
        write(report)
    print("\n".join(message_lines(report)))
    return 0 if report["status"] != "alert" else 3


if __name__ == "__main__":
    raise SystemExit(main())
