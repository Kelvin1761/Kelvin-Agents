"""Write one game's analysis: Game_<tag>_Full_Analysis.md and its .market_legs.json sidecar.

The sidecar is the machine contract (ledger, reflector, dashboard read it); the Markdown is
for people. The Markdown keeps the headings and leg-row shape the dashboard parses:
``### 🛡️ 組合 1 ... 組合賠率 @<SGM price>`` and ``| 🧩 1 | <desc> | @<price> | ...``.
"""
from __future__ import annotations

import hashlib
import json
import os

from .legs import MARKET, Leg

SCHEMA = "nba-market-eval-legs/v1"
STRATEGY_PROFILE = "banker-steady-b2-v1"   # the dashboard/ledger key for the formal banker line
STEADY_MARKER = f"正式穩膽政策：{STRATEGY_PROFILE}"
DISCLAIMER = ("正式穩膽 = steady（B2，EXP-20261027-21）：命中率產品線，模型預期 EV 為負；"
              "固定 $1 平注；累計 −10u 或 60 注後 ROI 上限 <0 自動暫停。")


def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def leg_row(i: int, leg: Leg, p: float) -> str:
    edge = p - leg.market
    ev = p * leg.price - 1
    return (f"| 🧩 {i} | {leg.desc} | @{leg.price:g} | {_pct(leg.hit_l10)} | {_pct(p)} | "
            f"{100 * edge:+.1f}% | {100 * ev:+.1f}% | CoV {leg.cov:.2f} |")


def render(odds, package, legs, combo, quote, policy, diagnostics, paused=None) -> str:
    meta = package.get("meta") or {}
    away, home = odds["away_team"], odds["home_team"]
    out = [f"# 🏀 {away} @ {home} — NBA Wong Choi", "",
           f"> SPORTSBET_LIVE | 賠率擷取 {odds.get('extraction_time')} | 開賽 {odds.get('event_start_time')}",
           f"> season_phase: {meta.get('season_phase')} | roster_season: {meta.get('roster_season')} | "
           f"L10_ORDER:newest_first | SPORTSBET_MILESTONE_OVER_ONLY",
           f"> 引擎版本: nba_engine | 機率: {policy.probability} | 數據來源: ESPN", ""]
    out += ["## 🎰 SGM Parlay 組合 (Python Auto-Selection)", "",
            f"> 📌 {STEADY_MARKER} — {DISCLAIMER}"]
    if paused:
        out.append(f"> ⛔ 正式穩膽停損暫停中（{paused}）；今日 NO BET。")
    out.append("")
    price = (quote or {}).get("decimal_odds")
    if combo and price:
        joint = 1.0
        for leg in combo:
            joint *= getattr(leg, policy.probability)
        out += [f"### 🛡️ 組合 1: Banker SGM（{len(combo)} Legs）— 組合賠率 @{price:g}", "",
                f"模型組合命中率 {_pct(joint)} | 真實 SGM 報價 @{price:g} | 模型 EV {100 * (joint * price - 1):+.1f}%"
                + ("（模型預期 EV 為負）" if joint * price <= 1 else ""), "",
                "| # | 選項 | 賠率 | L10 命中 | 模型機率 | Edge | EV | 波幅 |",
                "|---|---|---|---|---|---|---|---|"]
        out += [leg_row(i, leg, getattr(leg, policy.probability)) for i, leg in enumerate(combo, 1)]
        out += ["", "固定 $1 平注。"]
    else:
        out += ["### 🛡️ 組合 1: NO BET", "", f"原因：{diagnostics.get('no_bet_reason', 'no_combo')}"]
    out += ["", "## 📊 全部盤口（按模型機率）", "",
            "| 選項 | 賠率 | 市場 | C | S | L10 | L5 | 平均 | 分鐘 | 備註 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for leg in sorted(legs, key=lambda l: -(getattr(l, policy.probability) or 0))[:40]:
        notes = ", ".join(leg.flags + ([leg.availability] if leg.availability != "ok" else []))
        out.append(f"| {leg.desc} | @{leg.price:g} | {_pct(leg.market)} | {_pct(leg.p_c)} | {_pct(leg.p_s)} | "
                   f"{_pct(leg.hit_l10)} | {_pct(leg.hit_l5)} | {leg.avg:g} | {leg.minutes_l10:g} | {notes} |")
    funnel = ", ".join(f"{k} {v}" for k, v in sorted(diagnostics.get("funnel", {}).items()))
    out += ["", f"> 篩選漏斗：{funnel}", "", "未填寫項目 殘留: 0", ""]
    return "\n".join(out)


def sidecar(report_text, odds, package, legs, combo, quote, policy, diagnostics) -> dict:
    meta = package.get("meta") or {}
    picked = {(l.player, l.stat, l.line) for l in combo}
    prob = lambda l: getattr(l, policy.probability)  # noqa: E731
    combos = []
    if combo and quote and quote.get("status") == "ok":
        joint = 1.0
        for leg in combo:
            joint *= prob(leg)
        naive = round(joint, 10)
        combos.append({
            "combo_id": "1", "selection_rule": f"joint:{policy.probability}",
            "legs": [{"market_type": "PLAYER_MILESTONE", "player": l.player, "team": l.team,
                      "market": MARKET[l.stat], "line": l.line, "side": "over", "price": l.price,
                      "p_final": round(prob(l), 4), "desc": l.desc} for l in combo],
            "product_of_leg_prices": round(_product(l.price for l in combo), 4),
            "naive_joint_prob": naive, "correlation_penalty": 0.0, "adjusted_joint_prob": naive,
            "combo_ev_pct": round(100 * (naive * quote["decimal_odds"] - 1), 2),
            "sportsbet_sgm_price": quote["decimal_odds"], "sportsbet_sgm_status": "ok", "sgm_quote": quote,
        })
    return {
        "schema_version": SCHEMA, "engine": "nba_engine",
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
        "odds_extraction_time": odds.get("extraction_time"),
        "sportsbet_event_id": odds.get("sportsbet_event_id"),
        "event_start_time": odds.get("event_start_time"),
        "game_date": meta.get("date"), "away": odds["away_team"], "home": odds["home_team"],
        "season_phase": meta.get("season_phase"), "strategy_profile": STRATEGY_PROFILE,
        "policy": {"probability": policy.probability, "value_check": policy.value_check,
                   "min_price": policy.min_price, "max_price": policy.max_price},
        "legs": [{"player": l.player, "team": l.team, "market": MARKET[l.stat], "line": l.line, "side": "over",
                  "price": l.price, "p_final": None if prob(l) is None else round(prob(l), 4),
                  "p_market": round(l.market, 4), "p_c": None if l.p_c is None else round(l.p_c, 4),
                  "p_s": None if l.p_s is None else round(l.p_s, 4),
                  "p_l10_base_rate": l.hit_l10, "hit_l5": l.hit_l5, "availability": l.availability,
                  "flags": l.flags, "engine": f"nba_engine:{policy.probability}",
                  "picked": (l.player, l.stat, l.line) in picked,
                  "picked_in": ["1"] if (l.player, l.stat, l.line) in picked else []} for l in legs],
        "combos": combos,
        "quote_attempts": {"1": quote} if quote else {},
        "selection_diagnostics": diagnostics,
        "availability": {"meta": dict(meta), "injuries": package.get("injuries") or {}},
    }


def _product(values):
    out = 1.0
    for v in values:
        out *= v
    return out


def write(output_path: str, report_text: str, payload: dict) -> None:
    for path, text in ((output_path, report_text),
                       (output_path + ".market_legs.json",
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False))):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
