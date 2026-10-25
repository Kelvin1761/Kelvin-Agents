#!/usr/bin/env python3
"""Daily + cumulative ROI of the published NBA SGM combos, by combo type.

Reads only the append-only market ledger (``sgm_obs`` / ``sgm_price_obs`` /
``settlement``); it never changes a projection, pick or combo.

Combo type = the report slot (``combo_id``): 1 穩膽, 2 價值膽, 3 高倍率, X Value Bomb.
(``combo_risk_tier`` BANKER/VALUE is an EV band, not the slot, so it is not used.)

Staking: flat 1 unit per combo.  A combo wins when every leg hits, loses on any
miss, is ``pending`` while any leg is unsettled, and is ``void`` (stake back,
excluded from ROI) when any leg is void/DNP — the bookmaker would reprice, so
the profit is unknowable.

Two prices are reported side by side and never mixed:
  * ``sgm`` — Sportsbet's own SGM quote taken pre-tip (what you could actually bet);
  * ``product`` — product of leg prices, which ignores correlation and, on
    observed quotes, overstates the payout.
Snapshots taken at/after tip-off (``post_tip`` / ``late_write``) are flagged
``clean=False`` and reported separately.  ROI on small n is not evidence of edge.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

NBA_SKILL = Path(__file__).resolve().parents[1]
if str(NBA_SKILL) not in sys.path:
    sys.path.insert(0, str(NBA_SKILL))

import nba_market_ledger as ledger

COMBO_LABELS = {"1": "穩膽", "2": "價值膽", "3": "高倍率", "X": "Value Bomb"}
LABEL_ORDER = ("1", "2", "3", "X")


def _leg_key(game_tag: Any, leg: Mapping[str, Any]) -> tuple:
    line = leg.get("line")
    return (game_tag, leg.get("player"), leg.get("market"),
            float(line) if line is not None else None, leg.get("side") or "over")


def _clean(row: Mapping[str, Any]) -> bool:
    return not (row.get("post_tip") or row.get("late_write") or row.get("tip_unknown"))


def _price(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 1.0 else None


def _combo_rows(rows: list[dict]) -> list[dict]:
    """One sgm_obs row per (game, combo): the latest clean published snapshot, else latest."""
    exclusions = ledger.no_prediction_exclusions(rows)
    best: dict[tuple, dict] = {}
    for row in rows:
        if row.get("row_type") != "sgm_obs" or row.get("snapshot_role") == "warmup":
            continue
        if ledger._excluded(row, exclusions):
            continue
        key = (row.get("game_tag"), str(row.get("combo_id")))
        rank = (_clean(row), str(row.get("snapshot_created_at") or ""),
                ledger.ROLE_PRIORITY.get(str(row.get("snapshot_role")), 0))
        if key not in best or rank > best[key][0]:
            best[key] = (rank, row)
    return [item[1] for item in best.values()]


def _sgm_price(rows: list[dict], combo: Mapping[str, Any]) -> float | None:
    """Latest clean Sportsbet SGM quote for this very snapshot/combo, else None."""
    # New reports select against this frozen quote. A later observation must
    # never rewrite the price used for the published recommendation.
    quote = combo.get("sgm_quote") or {}
    if combo.get("sportsbet_sgm_status") == "ok" and quote.get("status") == "ok":
        from nba_sgm_quote import legs_identity
        if (quote.get("legs_sha256") == legs_identity(combo.get("legs") or [])
                and _price(quote.get("decimal_odds")) == _price(combo.get("sportsbet_sgm_price"))):
            return _price(quote.get("decimal_odds"))
    quotes = [
        r for r in rows
        if r.get("row_type") == "sgm_price_obs" and r.get("status") == "ok"
        and r.get("snapshot_id") == combo.get("snapshot_id")
        and r.get("game_tag") == combo.get("game_tag")
        and str(r.get("combo_id")) == str(combo.get("combo_id"))
        and _clean(r) and _price(r.get("sportsbet_sgm_price"))
    ]
    if not quotes:
        return None
    return _price(max(quotes, key=lambda r: str(r.get("captured_at") or "")).get("sportsbet_sgm_price"))


def settle_combos(rows: list[dict]) -> list[dict]:
    outcomes: dict[tuple, str] = {}
    for row in rows:
        if row.get("row_type") == "settlement":
            outcomes.setdefault(_leg_key(row.get("game_tag"), row), str(row.get("outcome")))
    out = []
    for combo in _combo_rows(rows):
        results = [outcomes.get(_leg_key(combo.get("game_tag"), leg), "unresolved")
                   for leg in combo.get("legs") or []]
        if not results:
            continue
        # A settled miss means the selection lost whatever the other legs did.
        # Checking void first dropped known losses from ROI (bias upward). This
        # assumes void legs are resettled on the remaining legs, not that one void
        # refunds the whole SGM (Sportsbet's exact SGM void wording not yet verified).
        if any(r == "miss" for r in results):
            state = "loss"
        elif any(r == "void" for r in results):
            state = "void"
        elif any(r == "unresolved" for r in results):
            state = "pending"
        elif all(r == "hit" for r in results):
            state = "win"
        else:
            state = "loss"
        out.append({
            "target_date": combo.get("target_date"), "game_tag": combo.get("game_tag"),
            "combo_id": str(combo.get("combo_id")),
            "label": COMBO_LABELS.get(str(combo.get("combo_id")), str(combo.get("combo_id"))),
            "legs": len(results), "legs_hit": sum(r == "hit" for r in results),
            "state": state, "clean": _clean(combo),
            "product_price": _price(combo.get("product_of_leg_prices")),
            "sgm_price": _sgm_price(rows, combo),
            "model_joint_prob": combo.get("sim_joint_prob") or combo.get("adjusted_joint_prob"),
        })
    return out


def _bucket(items: Iterable[dict]) -> dict:
    items = list(items)
    decided = [i for i in items if i["state"] in ("win", "loss")]
    wins = sum(i["state"] == "win" for i in decided)
    result = {
        "combos": len(items), "settled": len(decided), "wins": wins,
        "pending": sum(i["state"] == "pending" for i in items),
        "void": sum(i["state"] == "void" for i in items),
        "hit_rate": round(wins / len(decided), 4) if decided else None,
        "avg_legs_hit_fraction": (round(sum(i["legs_hit"] / i["legs"] for i in decided) / len(decided), 4)
                                  if decided else None),
    }
    for basis, field in (("sgm", "sgm_price"), ("product", "product_price")):
        priced = [i for i in decided if i[field]]
        profit = sum((i[field] - 1.0) if i["state"] == "win" else -1.0 for i in priced)
        result[basis] = {
            "n": len(priced), "wins": sum(i["state"] == "win" for i in priced),
            "profit_units": round(profit, 3),
            "roi": round(profit / len(priced), 4) if priced else None,
        }
    return result


def summarise(combos: list[dict]) -> dict:
    by_type = {cid: _bucket(c for c in combos if c["combo_id"] == cid) for cid in LABEL_ORDER
               if any(c["combo_id"] == cid for c in combos)}
    return {
        "total": _bucket(combos),
        "total_clean": _bucket(c for c in combos if c["clean"]),
        "by_type": by_type,
        "by_type_clean": {cid: _bucket(c for c in combos if c["combo_id"] == cid and c["clean"])
                          for cid in by_type},
    }


def daily(target_date: str, root: Path | None = None) -> dict:
    root = root or ledger.ledger_root()
    combos = settle_combos(ledger.read_rows(root, target_date))
    return {"target_date": target_date, **summarise(combos), "rows": combos}


def cumulative(root: Path | None = None, until: str | None = None) -> dict:
    root = root or ledger.ledger_root()
    combos: list[dict] = []
    dates = ledger._iter_dates(None, until, root)
    for date in dates:
        combos.extend(settle_combos(ledger.read_rows(root, date)))
    return {"dates": dates, **summarise(combos), "rows": combos}


def write_reports(target_date: str, root: Path | None = None) -> dict:
    root = root or ledger.ledger_root()
    day, total = daily(target_date, root), cumulative(root, until=target_date)
    out = root / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"combo_roi_{target_date}.json").write_text(
        json.dumps(day, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "combo_roi_cumulative.json").write_text(
        json.dumps(total, ensure_ascii=False, indent=2), encoding="utf-8")
    shadow = banker_shadow(target_date, root)
    (out / "banker_shadow_latest.json").write_text(json.dumps(shadow, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"daily": day, "cumulative": total, "banker_shadow": shadow}


def _roi(b: Mapping[str, Any], basis: str) -> str:
    x = b.get(basis) or {}
    if x.get("roi") is None:
        return "N/A"
    return f"{x['roi'] * 100:+.0f}%（{x['profit_units']:+.2f}u／{x['n']}注）"


def _line(name: str, b: Mapping[str, Any]) -> str:
    if not b.get("settled"):
        pend = f"｜待結算 {b['pending']}" if b.get("pending") else ""
        return f"{name}：未有已結算組合{pend}"
    return (f"{name}：{b['wins']}/{b['settled']} 中｜ROI（Sportsbet SGM 價）{_roi(b, 'sgm')}"
            f"｜ROI（單腿價相乘）{_roi(b, 'product')}")


def message_lines(reports: Mapping[str, Any]) -> list[str]:
    lines = ["📊 組合 ROI（每注 1u；樣本細，唔等於有 edge）"]
    for scope, title in (("daily", "今日"), ("cumulative", "累計")):
        data = reports[scope]
        lines.append(_line(f"{title}合共", data["total"]))
        for cid in LABEL_ORDER:
            if cid in data["by_type"]:
                lines.append("  " + _line(COMBO_LABELS[cid], data["by_type"][cid]))
    unclean = reports["cumulative"]["total"]["combos"] - reports["cumulative"]["total_clean"]["combos"]
    if unclean:
        lines.append(f"⚠️ 累計入面 {unclean} 個組合嚟自開賽後快照（唔係賽前價），ROI 只供參考。")
    lines.append("SGM 價未必每注都有；冇賽前 SGM 價嘅組合唔計入「Sportsbet SGM 價」一欄。")
    shadow = reports.get("banker_shadow")
    if shadow:
        lines.append(f"🧪 穩膽 EV 影子比較：{shadow['opportunity_days']} 日；未驗證盈利，唔計正式 ROI。")
        for arm, summary in shadow['arms'].items():
            lines.append(f"  {arm}：真價已結算 {summary['sgm']['n']} 注，ROI {_roi(summary, 'sgm')}。")
    return lines


def banker_shadow(until: str, root: Path | None = None, *, model_id: str | None = None) -> dict:
    """Forward research only; reuse settlement/real-price ROI without adding BETs."""
    import random
    if model_id is None:
        from nba_reliability import current_model_id
        model_id = current_model_id()
    root = root or ledger.ledger_root()
    arms = ('B0', 'B1', 'B2')
    items, opportunities, incomplete = [], [], 0
    for day in ledger._iter_dates(None, until, root):
        rows = ledger.read_rows(root, day)
        exclusions = ledger.no_prediction_exclusions(rows)
        rows = [r for r in rows if not ledger._excluded(r, exclusions) and r.get('season_phase') != 'PRESEASON']
        models = defaultdict(list)
        for row in rows:
            if row.get('row_type') == 'model_obs':
                models[row.get('game_tag')].append(row)
        chosen = {}
        for tag, observations in models.items():
            snap = ledger._choose_snapshot(observations)
            current = [r for r in observations if snap and r.get('snapshot_id') == snap]
            if current and model_id and all(ledger.probability_model_id(r) == model_id for r in current):
                chosen[tag] = snap
        experiments = defaultdict(dict)
        for row in rows:
            if (row.get('row_type') == 'banker_shadow_obs' and row.get('version') == 'banker-ev-shadow-v1'
                    and row.get('snapshot_id') == chosen.get(row.get('game_tag'))
                    and row.get('probability_model_id') == model_id and ledger._pre_tip(row)):
                experiments[row['game_tag']][row['arm']] = row
        view = [r for r in rows if r.get('row_type') == 'settlement']
        for tag, found in experiments.items():
            if set(found) != set(arms):
                incomplete += 1
                continue
            opportunities.append((day, tag))
            for arm, row in found.items():
                if row.get('eligible'):
                    view.append(dict(row, row_type='sgm_obs', combo_id=arm))
        items.extend(settle_combos(view))
    clean = [r for r in items if r['clean']]
    by_arm = {arm: _bucket(r for r in clean if r['combo_id'] == arm) for arm in arms}
    daily_returns = {arm: defaultdict(lambda: [0.0, 0]) for arm in arms}
    for item in clean:
        if item['state'] in ('win', 'loss') and item['sgm_price']:
            values = daily_returns[item['combo_id']][item['target_date']]
            values[0] += item['sgm_price']-1 if item['state'] == 'win' else -1
            values[1] += 1
    days = sorted({day for day, _ in opportunities})
    def interval(left, right=None):
        if (sum(daily_returns[left][d][1] > 0 for d in days) < 2
                or (right and sum(daily_returns[right][d][1] > 0 for d in days) < 2)):
            return None
        rng, values = random.Random(24), []
        for _ in range(2000):
            sampled = rng.choices(days, k=len(days))
            def roi(arm):
                profit = sum(daily_returns[arm][d][0] for d in sampled)
                stakes = sum(daily_returns[arm][d][1] for d in sampled)
                return profit/stakes if stakes else None
            a = roi(left)
            b = roi(right) if right else 0
            if a is not None and b is not None:
                values.append(a-b)
        if not values:
            return None
        values.sort()
        return [round(values[int(.025*(len(values)-1))], 4), round(values[int(.975*(len(values)-1))], 4)]
    for arm, bucket in by_arm.items():
        bucket['sgm_roi_ci95'] = interval(arm)
        running, peak, drawdown = 0.0, 0.0, 0.0
        for day in days:
            running += daily_returns[arm][day][0]
            peak = max(peak, running)
            drawdown = max(drawdown, peak-running)
        bucket['end_of_day_drawdown_units'] = round(drawdown, 4)
    return {'version': 'banker-ev-shadow-v1', 'until': until, 'probability_model_id': model_id,
            'status': 'NEEDS_MORE_TESTING', 'promotion_allowed': False,
            'recorded_game_opportunities': len(opportunities), 'opportunity_days': len(days),
            'incomplete_games': incomplete, 'arms': by_arm,
            'paired_roi_delta_ci95': {'B1_minus_B0': interval('B1', 'B0'), 'B2_minus_B1': interval('B2', 'B1')},
            'note': 'Diagnostic intervals only. No-bet ROI is undefined (not zero); absent comparisons remain null. '
                    'No automatic promotion; independent power assessment and Holm adjustment required before any adoption.'}


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="NBA combo ROI by type")
    parser.add_argument("--date", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--shadow", action="store_true", help="read-only banker EV forward experiment")
    args = parser.parse_args(argv)
    if args.shadow:
        print(json.dumps(banker_shadow(args.date), ensure_ascii=False, indent=2))
        return 0
    reports = write_reports(args.date) if args.write else {
        "daily": daily(args.date), "cumulative": cumulative(until=args.date)}
    print("\n".join(message_lines(reports)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
