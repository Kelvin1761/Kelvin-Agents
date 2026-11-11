"""Write one game's analysis: Game_<tag>_Full_Analysis.md and its .market_legs.json sidecar.

The sidecar is the only machine contract: the dashboard, publication firewall, ledger, SGM
summary and reflector read only it (bound to the report by ``report_sha256``). The Markdown
is for people and free-form; nothing parses it.
Every probability shown is ``Leg.p_final`` (MS, or C when S is unavailable).
"""
from __future__ import annotations

import hashlib
import json
import math
import os

from . import model
from .legs import MARKET, Leg

SCHEMA = "nba-market-eval-legs/v1"
ENGINE_ID = "nba_engine:ms+b2"
STRATEGY_PROFILE = "banker-steady-b2-v1"   # the dashboard/ledger key for the formal banker line
STEADY_MARKER = f"正式穩膽政策：{STRATEGY_PROFILE}"
DISCLAIMER = ("正式穩膽 = steady（B2，EXP-20261027-21）：命中率產品線，模型預期 EV 為負；"
              "固定 $1 平注；累計 −10u 或 60 注後 ROI 上限 <0 自動暫停。")


def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def _round(x, digits=4):
    return None if x is None else round(x, digits)


def joint(combo) -> float:
    return math.prod(leg.p_final for leg in combo)


def leg_row(i: int, leg: Leg) -> str:
    p = leg.p_final
    return (f"| 🧩 {i} | {leg.desc} | @{leg.price:g} | {_pct(leg.hit_l10)} | {_pct(p)} | "
            f"{100 * (p - leg.market):+.1f}% | {100 * (p * leg.price - 1):+.1f}% | CoV {leg.cov:.2f} |")


def heading(combo, price) -> str:
    """Combo 1's title line; the sidecar carries it so nobody parses it from the Markdown."""
    return f"🛡️ 組合 1: Banker SGM（{len(combo)} Legs）— 組合賠率 @{price:g}"


def _featured_desc(pick: dict) -> str:
    from .featured import describe
    return describe(pick)


def render(odds, package, legs, combo, quote, diagnostics, paused=None) -> str:
    meta = package.get("meta") or {}
    out = [f"# 🏀 {odds['away_team']} @ {odds['home_team']} — NBA Wong Choi", "",
           f"> SPORTSBET_LIVE | 賠率擷取 {odds.get('extraction_time')} | 開賽 {odds.get('event_start_time')}",
           f"> season_phase: {meta.get('season_phase')} | roster_season: {meta.get('roster_season')} | "
           f"L10_ORDER:newest_first | SPORTSBET_MILESTONE_OVER_ONLY",
           f"> 引擎版本: {ENGINE_ID} | 機率 = 市場 + 季度產出率（MS，EXP-20261103-15）| 數據來源: ESPN", "",
           "## 🎰 SGM Parlay 組合 (Python Auto-Selection)", "",
           f"> 📌 {STEADY_MARKER} — {DISCLAIMER}"]
    if paused:
        out.append(f"> ⛔ 正式穩膽停損暫停中（{paused}）；今日 NO BET。")
    if meta.get("season_phase") == "PRESEASON":
        out.append("> ⛔ NO BET — PRESEASON SHADOW ONLY：季前賽只作分析，禁止投注。")
    out.append("")
    price = (quote or {}).get("decimal_odds")
    if combo and price:
        p = joint(combo)
        out += [f"### {heading(combo, price)}", "",
                f"揀法：{diagnostics.get('rule')} | 模型組合命中率 {_pct(p)} | 真實 SGM 報價 @{price:g} | "
                f"模型 EV {100 * (p * price - 1):+.1f}%" + ("（模型預期 EV 為負）" if p * price <= 1 else ""), "",
                "| # | 選項 | 賠率 | L10 命中 | 模型機率 | Edge | EV | 波幅 |",
                "|---|---|---|---|---|---|---|---|"]
        out += [leg_row(i, leg) for i, leg in enumerate(combo, 1)]
        out += ["", "固定 $1 平注。"]
    else:
        out += ["### 🛡️ 組合 1: NO BET", "", f"原因：{diagnostics.get('no_bet_reason', 'no_combo')}"]
    pick = diagnostics.get("featured")
    out += ["", "## ⭐ 大細盤精選（紙上盤，EXP-20261110-01）", "",
            "> 前向測試：未證實賺錢，唔好落真錢。每場一注、每日最多 10 注。", ""]
    if pick:
        out += [f"**{_featured_desc(pick)} @{pick['price']:g}** — 模型 {_pct(pick['p_model'])}｜"
                f"去水市場 {_pct(pick['p_fair'])}｜edge {100 * pick['edge']:+.1f}pp"]
    else:
        out += ["今場冇大細盤 edge ≥ 5pp。"]
    out += ["", "## 📊 全部盤口（按模型機率）", "",
            "| 選項 | 賠率 | 市場 | 模型 | 季度模型 S | L10 | L5 | 平均 | 分鐘 | 備註 |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for leg in sorted(legs, key=lambda l: -(l.p_final or 0))[:40]:
        notes = ", ".join(leg.flags + ([leg.availability] if leg.availability != "ok" else []))
        out.append(f"| {leg.desc} | @{leg.price:g} | {_pct(leg.market)} | {_pct(leg.p_final)} | {_pct(leg.p_s)} | "
                   f"{_pct(leg.hit_l10)} | {_pct(leg.hit_l5)} | {leg.avg:g} | {leg.minutes_l10:g} | {notes} |")
    skipped = ", ".join(f"{k} {v}" for k, v in sorted(diagnostics.get("skipped", {}).items()))
    out += ["", f"> 盤口 {diagnostics.get('candidates', len(legs))} 條；略過球員：{skipped or '無'}", "",
            "未填寫項目 殘留: 0", ""]
    return "\n".join(out)


# Contract strings the dashboard tracking reads (nba_tracking._research_card,
# nba_latest_analysis): candidate_id 'steady' and this version allow 2-4 legs.
RESEARCH_VERSION = "banker-ev-shadow-v1"


def research_record(proposal, quote, verified, paused=None) -> dict:
    """The B2 pick as an OBSERVE record, bet or not, with its real SGM quote."""
    p = joint(proposal)
    price = (quote or {}).get("decimal_odds") if verified else None
    reasons = ["穩膽研究記錄：同正式組合 1（steady／B2）同一套揀法，用嚟追蹤；停損暫停期間照記錄。正式注以組合 1 為準。"]
    if not verified:
        reasons.append("未取得有效 Sportsbet 組合報價。")
    elif price < 2.0:
        reasons.append("真實組合價低於穩膽最低2.0倍。")
    if paused:
        reasons.append(f"正式穩膽停損暫停中（{paused}）。")
    ev = round(p * price - 1, 6) if price else None
    if ev is not None and ev <= 0:
        reasons.append("按真實組合價計算模型 EV 非正：命中率產品線，見 EXP-20261027-21。")
    return {"candidate_id": "steady", "label": "穩膽研究記錄", "version": RESEARCH_VERSION,
            "analysis_only": True, "decision": "OBSERVE", "odds": price, "sgm_quote": quote or {},
            "quote_verified_at_generation": bool(verified), "model_probability": round(p, 6),
            "expected_value": ev, "reasons": reasons,
            "legs": [{"player": l.player, "team": l.team, "market": MARKET[l.stat], "category": l.label,
                      "line": l.line, "side": "over", "price": l.price, "odds": l.price, "selection": l.desc,
                      "model_probability": round(l.p_final, 4), "l10_hit_rate": l.hit_l10} for l in proposal]}


def sidecar(report_text, odds, package, legs, combo, quote, diagnostics) -> dict:
    diagnostics = dict(diagnostics)
    research = diagnostics.pop("research", None)
    meta = package.get("meta") or {}
    model_id = model.probability_model_id()
    picked = {(l.player, l.stat, l.line) for l in combo}
    combos = []
    if combo and quote and quote.get("status") == "ok":
        p = round(joint(combo), 10)
        combos.append({
            "combo_id": "1", "selection_rule": diagnostics.get("rule"),
            "heading": heading(combo, quote["decimal_odds"]),
            "legs": [{"market_type": "PLAYER_MILESTONE", "player": l.player, "team": l.team,
                      "market": MARKET[l.stat], "line": l.line, "side": "over", "price": l.price,
                      "p_final": round(l.p_final, 4), "desc": l.desc} for l in combo],
            "product_of_leg_prices": round(math.prod(l.price for l in combo), 4),
            "naive_joint_prob": p, "correlation_penalty": 0.0, "adjusted_joint_prob": p,
            "combo_ev_pct": round(100 * (p * quote["decimal_odds"] - 1), 2),
            "sportsbet_sgm_price": quote["decimal_odds"], "sportsbet_sgm_status": "ok", "sgm_quote": quote,
        })
    return {
        "schema_version": SCHEMA, "engine": ENGINE_ID,
        "report_sha256": hashlib.sha256(report_text.encode("utf-8")).hexdigest(),
        "odds_extraction_time": odds.get("extraction_time"),
        "sportsbet_event_id": odds.get("sportsbet_event_id"),
        "event_start_time": odds.get("event_start_time"),
        "game_date": meta.get("date"), "away": odds["away_team"], "home": odds["home_team"],
        "season_phase": meta.get("season_phase"), "strategy_profile": STRATEGY_PROFILE,
        "legs": [{"player": l.player, "team": l.team, "market": MARKET[l.stat], "line": l.line, "side": "over",
                  "price": l.price, "p_final": _round(l.p_final), "p_market": _round(l.market),
                  "p_c": _round(l.p_c), "p_s": _round(l.p_s), "p_ms": _round(l.p_ms),
                  "p_s2": _round(l.p_s2), "minutes_ratio": l.minutes_ratio,
                  "p_l10_base_rate": l.hit_l10, "hit_l5": l.hit_l5, "cov": l.cov, "availability": l.availability,
                  "flags": l.flags, "engine": ENGINE_ID, "probability_model_id": model_id,
                  "picked": (l.player, l.stat, l.line) in picked,
                  "picked_in": ["1"] if (l.player, l.stat, l.line) in picked else []} for l in legs],
        "combos": combos,
        "quote_attempts": {"1": quote} if quote else {},
        "review_candidates": [research] if research else [],
        "selection_diagnostics": diagnostics,
        "featured": [diagnostics["featured"]] if diagnostics.get("featured") else [],
        "availability": {"meta": dict(meta), "injuries": package.get("injuries") or {}},
    }


def write(output_path: str, report_text: str, payload: dict) -> None:
    for path, text in ((output_path, report_text),
                       (output_path + ".market_legs.json",
                        json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False))):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
