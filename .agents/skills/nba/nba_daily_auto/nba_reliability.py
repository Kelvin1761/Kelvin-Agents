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
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import nba_market_ledger as ledger

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "nba_wong_choi" / "scripts"))
import nba_prob_layer

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


def current_model_id() -> str | None:
    return nba_prob_layer.probability_model_id()


def _section(root: Path, since: str, until: str, model_id: str | None = None) -> dict:
    report = ledger.evaluate(root=root, since=since, until=until)
    empty = {"legs": 0, "variants": {"p_final": {"calibration": []}}}
    if model_id is None:
        overall = report["overall"]
        picked = report["by_picked"].get("picked")
        by_market = report["by_market"]
    else:
        overall = report["by_probability_model"].get(model_id, empty)
        picked = overall.get("picked")
        by_market = overall.get("by_market", {})
    buckets = overall["variants"]["p_final"]["calibration"]
    return {
        "since": since, "until": until,
        "probability_model_id": model_id,
        "excluded_model_legs": report["overall"]["legs"] - overall["legs"],
        "models_seen": {identity: section["legs"] for identity, section in report["by_probability_model"].items()},
        "overall": _summ(buckets), "high_band": _high(buckets),
        "market_raw_close": _summ(overall.get("market_raw_close_calibration") or []),
        "picked": _summ(picked["variants"]["p_final"]["calibration"]) if picked else _summ([]),
        "by_stat": {MARKET_LABELS.get(m, m): _summ(sec["variants"]["p_final"]["calibration"])
                    for m, sec in by_market.items()},
        "buckets": buckets,
    }


def build(until: str, root: Path | None = None, window_days: int = WINDOW_DAYS,
          epoch: str = CALIBRATION_EPOCH) -> dict:
    """Choose the actual latest pre-tip observation first, then match its model identity."""
    root = root or ledger.ledger_root()
    since = (date.fromisoformat(until) - timedelta(days=window_days - 1)).isoformat()
    model_id = current_model_id()
    live = _section(root, max(since, epoch), until, model_id) if until >= epoch and model_id else None
    legacy_mixed = _section(root, since, until)
    cur = live or {"overall": _summ([]), "high_band": _summ([]), "market_raw_close": _summ([]),
                   "picked": _summ([]), "by_stat": {}, "buckets": [], "since": epoch, "until": until}
    total, high = cur["overall"], cur["high_band"]
    if model_id is None:
        status = "disabled"
    elif total["n"] < MIN_SETTLED:
        status = "insufficient_n"
    elif abs(total["gap"]) > ALERT_GAP or (high["n"] >= MIN_HIGH_BAND and abs(high["gap"]) > ALERT_GAP):
        status = "alert"
    else:
        status = "ok"
    return {
        "selection_health": selection_health(until, root),
        "until": until, "since": cur["since"], "window_days": window_days, "epoch": epoch, "status": status,
        "min_settled": MIN_SETTLED, "alert_gap": ALERT_GAP,
        "probability_model_id": model_id,
        "excluded_model_legs": cur.get("excluded_model_legs", 0),
        "models_seen": cur.get("models_seen", {}),
        "overall": total, "high_band": high, "market_raw_close": cur["market_raw_close"],
        "picked": cur["picked"], "by_stat": cur["by_stat"], "buckets": cur["buckets"],
        "all_engines_context": {k: legacy_mixed[k] for k in ("since", "overall", "high_band")},
        "note": "legs inside one game are correlated; n is legs, not independent clusters; "
                "alert uses only latest pre-tip observations matching the current coefficient identity; "
                "legacy and unversioned models remain context only",
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
    health_line = selection_message(report.get("selection_health") or {})
    head = f"📐 機率校準（現役模型，{report['since']} 起，已結算 {o['n']} 腿）"
    if report["status"] == "disabled":
        return [head, "校準層已刻意關閉；舊模型紀錄只作背景，唔會當成現役校準結果。"]
    if report["status"] == "insufficient_n":
        return [head, health_line, f"樣本未夠（要 ≥{report['min_settled']} 腿）先判斷；暫時只記錄，唔作結論。"]
    lines = [head, health_line, f"預測 {_pct(o['mean_p'])}／實際 {_pct(o['hit_rate'])}（差 {o['gap'] * 100:+.0f}pp）"
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
    return 3 if report["status"] == "alert" else 75 if report["status"] == "disabled" else 0



def selection_health(until: str, root: Path | None = None, window_days: int = 30) -> dict:
    """Zero-bankers is an operational audit signal, never a parameter trigger."""
    from collections import defaultdict
    root = root or ledger.ledger_root()
    since = max(CALIBRATION_EPOCH, (date.fromisoformat(until)-timedelta(days=window_days-1)).isoformat())
    identity = current_model_id()
    days = []
    for day in ledger._iter_dates(since, until, root):
        rows = ledger.read_rows(root, day)
        exclusions = ledger.no_prediction_exclusions(rows)
        rows = [r for r in rows if r.get('season_phase') != 'PRESEASON' and not ledger._excluded(r, exclusions)]
        models = defaultdict(list)
        expected = set()
        for row in rows:
            if row.get('row_type') == 'price_obs' and ledger._pre_tip(row):
                expected.add(row.get('game_tag'))
            if row.get('row_type') == 'model_obs':
                models[row.get('game_tag')].append(row)
        analysed, bankers = 0, 0
        for tag, candidates in models.items():
            chosen = ledger._choose_snapshot(candidates)
            selected = [r for r in candidates if chosen and r.get('snapshot_id') == chosen]
            if not selected or not identity or any(ledger.probability_model_id(r) != identity for r in selected):
                continue
            analysed += 1
            bankers += int(any('1' in [str(x) for x in r.get('picked_in', [])] for r in selected))
        complete = bool(expected) and analysed == len(expected)
        days.append({'date': day, 'analysed_games': analysed, 'expected_priced_games': len(expected),
                     'banker_games': bankers, 'coverage_complete': complete})
    streak = 0
    for day in reversed(days):
        if not day['coverage_complete'] or day['banker_games']:
            break
        streak += 1
    return {'status': 'review_required' if streak >= 3 else ('observing' if days else 'insufficient_data'),
            'zero_banker_runs': streak, 'alert_after_runs': 3, 'days': days,
            'probability_model_id': identity,
            'note': 'Complete priced-game coverage only; missing/legacy/warmup data breaks the streak. No parameter changes.'}


def selection_message(health: dict) -> str:
    if health.get('status') == 'review_required':
        return f"⚠️ 連續 {health['zero_banker_runs']} 個完整可評估賽日零穩膽：策略需審計，唔代表已證明成功避險。"
    if health.get('status') == 'insufficient_data':
        return '出手監察：正式逐日紀錄未足，唔判定策略正常或失效。'
    return f"出手監察：連續 {health.get('zero_banker_runs', 0)} 個完整可評估賽日零穩膽；達3日觸發審計提醒。"


if __name__ == "__main__":
    raise SystemExit(main())
