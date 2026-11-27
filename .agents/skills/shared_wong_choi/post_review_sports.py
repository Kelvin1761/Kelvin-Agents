#!/usr/bin/env python3
"""NBA／網球每日自動覆盤（自學循環 L1，Kelvin 2026-11-26「NBA／網球每日覆盤 … great value with self learn」）。

同賽馬 `shared_racing/scripts/post_review.py` 同一個做法、同一個輸出位置（`<WongChoiControl>/reviews/<domain>/<日>.json/.md`），
跨日組別描述直接用佢嘅 `_cohorts`（實際 − 模型機率；按日 cluster bootstrap；只描述唔判決）。

NBA（target_date = 悉尼賽日）
  * 逐腿：`nba_market_ledger.evaluate(return_legs=True)` —— 同官方評估同一套揀快照（最後一份賽前已發佈）、收盤價、去水。
    模型 = `p_final`；市場 = 收盤**雙邊去水**（`market_devig_close`；只有部分腿有）。單邊 1/價含抽水，唔拎嚟比 log-loss；
    失手分類冇去水價就用單邊 1/價，門檻加 5pp（≥65%）抵銷抽水，標「未去水」。
  * 精選（大細盤紙上盤）：dashboard tracking `featured_records`（同 ROI 板同一份）；中／唔中、模型 vs 落注時去水價、CLV。
  * 失手分類（精選＋模型 ≥70% 嘅腿）：冇上陣／上陣 <15 分鐘 → 「上陣時間」；去水市場都 ≥60% → 「市場都估錯」；
    其餘 → 「模型判錯」。
網球（match_date）
  * 逐注：`prop_tracker` 已結算（WON／LOST）；模型 = `model_prob_raw`（未向市場收縮嘅模型；同校準板）；市場 = `market_prob_fair`。
    （`model_prob` 係向市場收縮後嘅版本，有啲盤口 temper_strength = 1 即係等於市場，唔可以當模型。）
  * 精選：`featured_picks`（凍結價、凍結 `model_prob`）join 結果；中／唔中、紙上盤盈虧。
  * 失手分類（精選＋模型 ≥70%）：去水市場都 ≥60% → 「市場都估錯」；資料質素 <50 → 「輸入資料薄」；其餘 → 「模型判錯」。
組別（賽前資訊）：NBA 項目／大細方向／模型機率段／模型減市場差距段／精選；網球盤口類別／賽事級別（`pricing.props.tier_of`）／
熱門冷門（市場）／差距段／資料質素段／精選。

只描述，唔會改模型；篩選每季、Holm、預先登記 forward（設計 docs/plans/2026-11-26-self-learning-loop.md）。

    python3 post_review_sports.py --domain nba|tennis --date YYYY-MM-DD [--trail-days 30] [--telegram]
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import date as Date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
RACING = REPO / ".agents" / "skills" / "shared_racing" / "scripts"
NBA_AUTO = REPO / ".agents" / "skills" / "nba" / "nba_daily_auto"
TENNIS_SRC = REPO / "tennis-wong-choi" / "src"
for _p in (str(RACING), str(HERE), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import post_review as PR  # noqa: E402  （輸出位置、_cohorts、_atomic、_short、output_dir）

VERSION = "post-review-sports-v1"
TRAIL_DAYS = 30
CONFIDENT = 0.70            # 「模型有信心」= ≥70%（失手分類用；預先寫死）
MARKET_AGREE = 0.60         # 去水市場 ≥60% = 市場都睇好
LOW_MINUTES = 15
RAW_VIG = 0.05              # 單邊 1/價冇得去水：門檻加 5pp
TENNIS_LOW_DQ = 50


def _days(day: str, n: int) -> tuple[str, str]:
    d = Date.fromisoformat(day)
    return (d - timedelta(days=n)).isoformat(), day


def _ll(p, y):
    p = min(max(float(p), 1e-9), 1 - 1e-9)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _band(p: float) -> str:
    return "≥80%" if p >= 0.8 else "60–80%" if p >= 0.6 else "40–60%" if p >= 0.4 else "<40%"


def _gap_band(d: float) -> str:
    return "模型高過市場 ≥10pp" if d >= 0.10 else "模型高過市場 5–10pp" if d >= 0.05 else \
        "模型低過市場 ≥5pp" if d <= -0.05 else "同市場 ±5pp"


def _gap_band_open(d: float) -> str:
    return _gap_band(d).replace("市場", "模型時隱含")


def _row(day, key, p, m, y, cohorts, **extra):
    """同 post_review._cohorts 嘅欄位對齊：hit3 = 中／唔中、p_top3 = 模型、m_top3 = 市場（冇就 None）。"""
    return {"date": day, "key": key, "p_top3": float(p), "m_top3": None if m is None else float(m), "hit3": int(y),
            "cohorts": cohorts, "tags": [], **extra}


def _minutes(v) -> float | None:
    if v in (None, ""):
        return None
    s = str(v)
    try:
        if ":" in s:
            mm, ss = s.split(":", 1)
            return int(mm) + int(ss) / 60
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------- NBA

MARKET_ZH = {"pts": "得分", "reb": "籃板", "ast": "助攻", "3pm": "三分", "fg3m": "三分", "stl": "抄截", "blk": "封阻"}


def nba_rows(day: str, trail: int, root: Path | None = None) -> tuple[list[dict], dict]:
    sys.path.insert(0, str(NBA_AUTO))
    import nba_market_ledger as L
    lo, hi = _days(day, trail)
    rep = L.evaluate(root=root, since=lo, until=hi, return_legs=True)
    rows = []
    for leg in rep.get("legs") or []:
        if leg.get("y") is None or leg.get("p_final") is None:
            continue
        d, tag, player, market, line, side = leg["key"]
        p, m = float(leg["p_final"]), leg.get("market_devig_close")
        mk = MARKET_ZH.get(market, market)
        coh = [f"market:{mk}", f"side:{'大' if side == 'over' else '細'}", f"band:模型 {_band(p)}"]
        try:
            decision_price = float(leg.get("price_at_model"))
        except (TypeError, ValueError):
            decision_price = 0
        if math.isfinite(decision_price) and decision_price > 1:
            coh.append(f"gap:{_gap_band_open(p - 1 / decision_price)}")
        rows.append(_row(d, f"{tag}|{player}|{market}|{line}|{side}", p, m, leg["y"], coh, game=tag, player=player,
                         market=mk, line=line, side=side, minutes=_minutes(leg.get("minutes")),
                         raw_close=leg.get("market_raw_close")))
    return rows, {"counts": rep.get("counts"), "window": [lo, hi]}


def _leg_key(game, player, market, line, side) -> tuple:
    """精選 ↔ ledger 腿配對：盤口線統一做 float（5 同 5.0 一樣）、名去頭尾空格。"""
    try:
        line = float(line)
    except (TypeError, ValueError):
        pass
    return (str(game or ""), str(player or "").strip(), str(market or ""), line, str(side or "over"))


def nba_featured(day: str) -> list[dict]:
    sys.path.insert(0, str(REPO / "Horse_Racing_Dashboard" / "backend"))
    from services.nba_tracking import export_tracking
    return [r for r in export_tracking(REPO).get("featured_records") or [] if r.get("day") == day]


def nba_sgm_records() -> list[dict]:
    """由 dashboard tracker 讀 SGM 記錄；pytest 唔經注入唔會觸及 export_tracking。"""
    if os.environ.get("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return []
    backend = str(REPO / "Horse_Racing_Dashboard" / "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from services import nba_tracking
    return list(nba_tracking.export_tracking(REPO).get("records") or [])


_SGM_CODE_ALIASES = {
    "pts": "pts", "points": "pts", "得分": "pts",
    "reb": "reb", "rebounds": "reb", "籃板": "reb",
    "ast": "ast", "assists": "ast", "助攻": "ast",
    "3pm": "fg3m", "fg3m": "fg3m", "threes": "fg3m", "threes_made": "fg3m", "三分": "fg3m",
    "stl": "stl", "steals": "stl", "抄截": "stl",
    "blk": "blk", "blocks": "blk", "封阻": "blk",
}
_CODE_TO_ZH = {"pts": "得分", "reb": "籃板", "ast": "助攻", "fg3m": "三分", "stl": "抄截", "blk": "封阻"}


def _num_val(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _sgm_market_raw(leg) -> str:
    if isinstance(leg, dict):
        raw = leg.get("market") or leg.get("category") or leg.get("stat") or ""
    else:
        raw = leg or ""
    return re.sub(r"\bplayer\b", "", str(raw).lower()).strip()


def _sgm_market_code(leg) -> str:
    s = _sgm_market_raw(leg)
    return _SGM_CODE_ALIASES.get(s, s)


def _sgm_market_zh(leg) -> str:
    code = _sgm_market_code(leg)
    return _CODE_TO_ZH.get(code, MARKET_ZH.get(code, code))


def _lookup_sgm_ledger(legs_by_key: dict, rec_day: str | None, game_tag: str | None, leg: dict) -> dict | None:
    if not legs_by_key:
        return None
    player = leg.get("player")
    line = leg.get("line") if leg.get("line") is not None else leg.get("ou_line")
    side = leg.get("side") or "over"
    code = _sgm_market_code(leg)
    zh = _sgm_market_zh(leg)
    cands = [zh, code]
    if code == "fg3m":
        cands.append("3pm")
    for mk in dict.fromkeys(c for c in cands if c):
        base = _leg_key(game_tag, player, mk, line, side)
        if rec_day is not None and (rec_day, *base) in legs_by_key:
            return legs_by_key[(rec_day, *base)]
        entry = legs_by_key.get(base)
        if entry is not None and entry.get("date") in (None, rec_day):
            return entry
    return None


def _sgm_leg_sig(leg: dict) -> tuple:
    return (str(leg.get("player") or "").strip(), _sgm_market_code(leg),
            _num_val(leg.get("line") if leg.get("line") is not None else leg.get("ou_line")),
            str(leg.get("side") or "over"))


def _eval_21h_legs(rec: dict, from_legs: list[dict], day_game_legs: list[dict], legs_by_key: dict) -> bool | None:
    """用同日同場記錄或 ledger 結算 21:00 原版各腿，回傳原本會唔會中（資料不足或有 void 回傳 None）。"""
    if not from_legs:
        return None
    rec_day, tag = rec.get("day"), rec.get("game_tag")
    by_exact = {}
    by_pm = {}
    for l in day_game_legs:
        sig = _sgm_leg_sig(l)
        by_exact.setdefault(sig, l)
        by_pm.setdefault((sig[0], sig[1]), l)
    outcomes = []
    for fl in from_legs:
        sig = _sgm_leg_sig(fl)
        line = sig[2]
        side = sig[3]
        matched = by_exact.get(sig)
        if matched and matched.get("state") in ("won", "lost", "void"):
            outcomes.append(matched["state"])
            continue
        led = _lookup_sgm_ledger(legs_by_key, rec_day, tag, fl)
        if led is not None and led.get("hit3") in (0, 1):
            outcomes.append("won" if led["hit3"] == 1 else "lost")
            continue
        pm_leg = by_pm.get((sig[0], sig[1]))
        if pm_leg:
            if pm_leg.get("state") == "void" or pm_leg.get("actual") == "void":
                outcomes.append("void")
                continue
            actual = _num_val(pm_leg.get("actual"))
            if actual is not None and line is not None:
                hit = actual >= line if side == "over" else actual < line
                outcomes.append("won" if hit else "lost")
                continue
        return None
    if "void" in outcomes:
        return None
    return all(o == "won" for o in outcomes)


def _sgm_p_band(p: float | None) -> str:
    if p is None:
        return "未知"
    if p >= 0.80:
        return "≥80%"
    if p >= 0.70:
        return "70–80%"
    return "<70%"


def _build_sgm_combo(rec: dict, legs_by_key: dict, same_day_game_legs: list[dict]) -> dict:
    rec_day = rec.get("day")
    tag = rec.get("game_tag")
    kind = rec.get("tracking_kind") or "research"
    kind_label = "正式" if kind == "formal" else "紙上"
    odds = _num_val(rec.get("odds"))
    model_p = _num_val(rec.get("model_probability"))
    implied_p = round(1.0 / odds, 4) if odds is not None and odds > 0 else None
    ev = round(model_p * odds - 1.0, 4) if model_p is not None and odds is not None else None
    leg_rows = []
    leg_prices = []
    for leg in rec.get("legs") or []:
        why = leg.get("why") if isinstance(leg.get("why"), dict) else {}
        expect = why.get("expect") if isinstance(why.get("expect"), dict) else {}
        led = _lookup_sgm_ledger(legs_by_key, rec_day, tag, leg)
        mk_code = _sgm_market_code(leg)
        mk_zh = _sgm_market_zh(leg)
        line_val = _num_val(leg.get("line") if leg.get("line") is not None else leg.get("ou_line"))
        side = str(leg.get("side") or "over")
        actual = _num_val(leg.get("actual"))
        margin = round(actual - line_val, 2) if actual is not None and line_val is not None else None
        l_state = leg.get("state") or "pending"
        l_model_p = _num_val(leg.get("model_probability"))
        if l_model_p is None:
            l_model_p = _num_val(why.get("p_final"))
        price = _num_val(leg.get("price"))
        if price is None:
            price = _num_val(leg.get("odds"))
        if price is None:
            price = _num_val(why.get("price"))
        if price is not None and price > 0:
            leg_prices.append(price)
        l_implied_p = round(1.0 / price, 4) if price is not None and price > 0 else None
        l10_rate = _num_val(leg.get("l10_hit_rate"))
        if l10_rate is None:
            l10_rate = _num_val(why.get("p_l10_base_rate"))
        exp_min = _num_val(expect.get("minutes"))
        act_min = _num_val(led.get("minutes")) if led else None
        min_ratio = round(act_min / exp_min, 3) if act_min is not None and exp_min is not None and exp_min > 0 else None
        player = leg.get("player")
        team = leg.get("team") or ""
        stat = leg.get("stat") or leg.get("category") or mk_code.upper()
        line_lbl = "" if line_val is None else f" {line_val:g}+"
        selection = leg.get("selection") or f"{player} ({team}) {stat}{line_lbl}".replace(" () ", " ")
        miss = None
        if l_state == "lost":
            # why.p_market 係單邊 1/price（含抽水），只可以入「未去水」門檻；去水市場機率只用 ledger 雙邊收盤
            # （Hydrogen 2026-11-27：之前當咗去水用，令斷纜腿幾乎全部被標「市場都估錯」）
            m_arg = led.get("m_top3") if led else None
            raw_arg = (led.get("raw_close") if led else None)
            if raw_arg is None:
                raw_arg = _num_val(why.get("p_market"))
            if raw_arg is None:
                raw_arg = l_implied_p
            miss = nba_classify(act_min, l_model_p, m_arg, raw_arg)
        leg_rows.append({
            "selection": selection, "player": player, "team": team,
            "market": mk_zh, "market_code": mk_code, "line": line_val, "side": side,
            "actual": leg.get("actual") if leg.get("actual") == "void" else actual,
            "margin": margin, "state": l_state, "model_p": l_model_p, "price": price,
            "implied_p": l_implied_p, "l10_rate": l10_rate,
            "exp_minutes": exp_min, "act_minutes": act_min, "minutes_ratio": min_ratio,
            "joined": led is not None,
            **({"miss": miss} if miss is not None else {}),
        })
    raw_legs = rec.get("legs") or []
    product_prices = round(math.prod(leg_prices), 4) if len(leg_prices) == len(raw_legs) and leg_prices else None
    corr_discount = round(odds / product_prices, 4) if odds is not None and product_prices and product_prices > 0 else None
    state = rec.get("state") or "pending"
    profit = _num_val(rec.get("profit"))
    busted = [l for l in leg_rows if l["state"] == "lost"]
    busted_count = len(busted)
    one_leg_away = state == "lost" and busted_count == 1
    with_p = [l for l in leg_rows if l["model_p"] is not None]
    weakest = min(with_p, key=lambda l: l["model_p"]) if with_p else None
    weakest_view = ({"selection": weakest["selection"], "player": weakest["player"], "market": weakest["market"],
                     "line": weakest["line"], "model_p": weakest["model_p"], "state": weakest["state"]}
                    if weakest else None)
    if busted_count == 0:
        bust_was_weakest = None
    elif weakest is None:
        bust_was_weakest = None
    else:
        min_p = weakest["model_p"]
        bust_was_weakest = any(l["model_p"] == min_p for l in busted if l["model_p"] is not None)
    mu = rec.get("morning_update") if isinstance(rec.get("morning_update"), dict) else None
    mu_from = mu.get("from") if mu and isinstance(mu.get("from"), dict) else None
    if mu and mu.get("cancelled"):
        morning_changed = True
    elif mu_from is not None:
        morning_changed = sorted(_sgm_leg_sig(l) for l in raw_legs) != sorted(
            _sgm_leg_sig(l) for l in (mu_from.get("legs") or []))
    else:
        morning_changed = False
    would_21h = (_eval_21h_legs(rec, mu_from.get("legs") or [], same_day_game_legs, legs_by_key)
                 if morning_changed and mu_from else None)
    return {
        "id": rec.get("id"),
        "event": rec.get("event_name") or str(tag or "").replace("_", " @ "),
        "game_tag": tag,
        "tracking_kind": kind,
        "kind_label": kind_label,
        "odds": odds,
        "model_p": model_p,
        "implied_p": implied_p,
        "ev": ev,
        "product_leg_prices": product_prices,
        "correlation_discount": corr_discount,
        "state": state,
        "profit": profit,
        "legs": leg_rows,
        "diagnosis": {
            "busted_legs": busted_count,
            "busted_selections": [l["selection"] for l in busted],
            "one_leg_away": one_leg_away,
            "weakest_link": weakest_view,
            "bust_was_weakest_link": bust_was_weakest,
            "morning_update_changed": morning_changed,
            "would_21h_version_have_won": would_21h,
        },
    }


def _sgm_summary_block(combos: list[dict]) -> dict:
    won = sum(1 for c in combos if c["state"] == "won")
    lost = sum(1 for c in combos if c["state"] == "lost")
    void = sum(1 for c in combos if c["state"] == "void")
    pending = sum(1 for c in combos if c["state"] not in ("won", "lost", "void"))
    settled = [c for c in combos if c["state"] in ("won", "lost")]
    n_set = len(settled)
    hit_rate = round(won / n_set, 4) if n_set else None
    mp = [c["model_p"] for c in settled if c["model_p"] is not None]
    ip = [c["implied_p"] for c in settled if c["implied_p"] is not None]
    mean_mp = round(float(np.mean(mp)), 4) if mp else None
    mean_ip = round(float(np.mean(ip)), 4) if ip else None
    cal_gap = round(hit_rate - mean_mp, 4) if hit_rate is not None and mean_mp is not None else None
    pnl = 0.0
    for c in settled:
        if c["profit"] is not None:
            pnl += c["profit"]
        elif c["state"] == "won" and c["odds"] is not None:
            pnl += c["odds"] - 1.0
        elif c["state"] == "lost":
            pnl -= 1.0
    pnl = round(pnl, 2)
    roi = round(pnl / n_set, 4) if n_set else None
    ola = sum(1 for c in settled if c["diagnosis"]["one_leg_away"])
    ola_share = round(ola / lost, 4) if lost else None
    bust_legs = [l for c in settled for l in c["legs"] if l["state"] == "lost"]
    bust_market = Counter(l["market"] for l in bust_legs)
    bust_miss = Counter(l.get("miss") or "未知" for l in bust_legs)
    bust_band = {"<70%": 0, "70–80%": 0, "≥80%": 0}
    for l in bust_legs:
        b = _sgm_p_band(l["model_p"])
        bust_band[b] = bust_band.get(b, 0) + 1
    corrs = [c["correlation_discount"] for c in settled if c["correlation_discount"] is not None]
    evs = [c["ev"] for c in settled if c["ev"] is not None]
    return {
        "combos": len(combos), "settled": n_set, "won": won, "lost": lost, "void": void, "pending": pending,
        "hit_rate": hit_rate, "mean_model_p": mean_mp, "mean_implied_p": mean_ip, "calibration_gap": cal_gap,
        "pnl_units": pnl, "roi": roi, "one_leg_away": ola, "one_leg_away_share": ola_share,
        "bust_legs_total": len(bust_legs),
        "bust_by_market": dict(bust_market),
        "bust_by_miss_class": dict(bust_miss),
        "bust_by_p_band": bust_band,
        "bust_p80_plus": bust_band["≥80%"],
        "mean_correlation_discount": round(float(np.mean(corrs)), 4) if corrs else None,
        "mean_ev": round(float(np.mean(evs)), 4) if evs else None,
    }


def _sgm_summary_with_kinds(combos: list[dict]) -> dict:
    out = _sgm_summary_block(combos)
    out["formal"] = _sgm_summary_block([c for c in combos if c["tracking_kind"] == "formal"])
    out["research"] = _sgm_summary_block([c for c in combos if c["tracking_kind"] != "formal"])
    return out


def nba_sgm_review(day: str, records: list[dict], legs_by_key: dict, trail_days: int = TRAIL_DAYS) -> dict:
    """NBA SGM 組合覆盤（只診斷，唔改模型或停損）。"""
    lo, hi = _days(day, trail_days)
    recs = list(records or [])
    by_day_game = defaultdict(list)
    for r in recs:
        for l in r.get("legs") or []:
            by_day_game[(r.get("day"), r.get("game_tag"))].append(l)
    window_recs = [r for r in recs if r.get("day") and lo <= r["day"] <= hi]
    built_window = [_build_sgm_combo(r, legs_by_key, by_day_game[(r.get("day"), r.get("game_tag"))])
                    for r in window_recs]
    day_combos = [c for r, c in zip(window_recs, built_window) if r.get("day") == day]
    all_day_legs = [l for c in day_combos for l in c["legs"]]
    joined_n = sum(1 for l in all_day_legs if l["joined"])
    total_n = len(all_day_legs)
    return {
        "day": day,
        "window": [lo, hi],
        "trail_days": trail_days,
        "join": {
            "joined_legs": joined_n,
            "total_legs": total_n,
            "join_rate": round(joined_n / total_n, 4) if total_n else None,
        },
        "combos": day_combos,
        "day_summary": _sgm_summary_with_kinds(day_combos),
        "trailing_summary": _sgm_summary_with_kinds(built_window),
    }


def nba_classify(minutes: float | None, p: float | None, m: float | None, raw: float | None = None) -> str:
    if minutes is not None and minutes < LOW_MINUTES:
        return "上陣時間（冇上陣／<15 分鐘）"
    if m is not None:
        return "市場都估錯" if m >= MARKET_AGREE else "模型判錯"
    if raw is not None and raw >= MARKET_AGREE + RAW_VIG:
        return "市場都估錯（未去水）"
    return "模型判錯"


def nba_review(day: str, trail: int = TRAIL_DAYS, root: Path | None = None, sgm_loader=None) -> dict:
    rows, meta = nba_rows(day, trail, root)
    records = list(sgm_loader()) if sgm_loader is not None else nba_sgm_records()
    sgm_leg_keys = set()
    for rec in records:
        rday, tag = rec.get("day"), rec.get("game_tag")
        for leg in rec.get("legs") or []:
            mk = _sgm_market_zh(leg)
            line = leg.get("line") if leg.get("line") is not None else leg.get("ou_line")
            sgm_leg_keys.add((rday, *_leg_key(tag, leg.get("player"), mk, line, leg.get("side") or "over")))
    if sgm_leg_keys:
        rows = [
            dict(x, cohorts=[*x["cohorts"], "picked:SGM 組合腿"])
            if (x["date"], *_leg_key(x["game"], x["player"], x["market"], x["line"], x["side"])) in sgm_leg_keys
            and "picked:SGM 組合腿" not in x["cohorts"]
            else x
            for x in rows
        ]
    today = [x for x in rows if x["date"] == day]
    feats = nba_featured(day)
    window = sorted({x["date"] for x in rows if x["date"] < day})
    rng = np.random.default_rng(7)
    devig = [x for x in today if x["m_top3"] is not None]
    summary = {
        "legs": len(today), "hit_rate": _rate(today, "hit3"), "mean_p": _mean(today, "p_top3"),
        "model_logloss": _mean_ll(today, "p_top3"),
        "devig_legs": len(devig), "model_logloss_devig": _mean_ll(devig, "p_top3"),
        "market_logloss_devig": _mean_ll(devig, "m_top3"),
        "by_market": {mk: {"legs": len(xs), "hit_rate": _rate(xs, "hit3"), "mean_p": _mean(xs, "p_top3")}
                      for mk, xs in _group(today, "market").items()},
    }
    by_leg = {_leg_key(x["game"], x["player"], x["market"], x["line"], x["side"]): x for x in today}
    sgm_legs = dict(by_leg)
    sgm_legs.update({(x["date"], *_leg_key(x["game"], x["player"], x["market"], x["line"], x["side"])): x for x in rows})
    sgm = nba_sgm_review(day, records, sgm_legs, trail_days=trail)
    feat_rows = []
    for f in feats:
        leg = (f.get("legs") or [{}])[0]
        key = _leg_key(f.get("game_tag"), leg.get("player"), MARKET_ZH.get(str(leg.get("market")), leg.get("market")),
                       leg.get("ou_line"), leg.get("side"))
        led = by_leg.get(key) or {}
        state = f.get("state")
        clv = f.get("clv") or {}
        entry = {"event": f.get("event_name"), "pick": f"{leg.get('player')} {leg.get('stat') or leg.get('market')} "
                 f"{'大' if leg.get('side') == 'over' else '細'} {leg.get('ou_line')}", "odds": f.get("odds"),
                 "p_model": f.get("p_model"), "p_fair": f.get("p_fair"), "state": state, "profit": f.get("profit"),
                 "actual": leg.get("actual"), "clv": clv.get("clv_pp") if isinstance(clv, dict) else None,
                 "minutes": led.get("minutes")}
        if state == "lost":
            entry["miss"] = nba_classify(led.get("minutes"), f.get("p_model"), f.get("p_fair"))
        feat_rows.append(entry)
    misses = [dict(_leg_view(x), miss=nba_classify(x.get("minutes"), x["p_top3"], x["m_top3"], x.get("raw_close")))
              for x in today if x["p_top3"] >= CONFIDENT and not x["hit3"]]
    return {"version": VERSION, "domain": "nba", "date": day,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary, "featured": feat_rows,
            "featured_summary": _feat_summary(feat_rows),
            "sgm": sgm,
            "confident_misses": sorted(misses, key=lambda x: -x["p"])[:25],
            "confident_miss_classes": dict(Counter(m["miss"] for m in misses)),
            "confident_total": sum(1 for x in today if x["p_top3"] >= CONFIDENT),
            "cohorts": _relabel(PR._cohorts(rows, day, window, rng)),
            "window": {"days": window, "n_days": len(window)}, "meta": meta,
            "reconciliation": {"ok": bool(today) or not feats, "legs_settled": len(today),
                               "featured_unsettled": sum(1 for f in feat_rows if f["state"] not in ("won", "lost", "void")),
                               "note": "legs_settled = 當日有賽前模型＋賽果嘅腿；精選未結算會列出"},
            "rules": "描述唔係判決：唔會據此改模型；篩選每季做（Holm），判決經預先登記 forward。"}


def _leg_view(x: dict) -> dict:
    return {"game": x.get("game"), "player": x.get("player"), "market": x.get("market"), "line": x.get("line"),
            "side": "大" if x.get("side") == "over" else "細", "p": round(x["p_top3"], 3),
            "m": None if x["m_top3"] is None else round(x["m_top3"], 3), "minutes": x.get("minutes")}


# ---------------------------------------------------------------- 網球

def tennis_db() -> Path:
    ptr = Path.home() / ".wongchoi_tennis_db"
    try:
        p = Path(ptr.read_text(encoding="utf-8").strip())
        if p.exists():
            return p
    except OSError:
        pass
    return REPO / "tennis-wong-choi" / "tennis_wc.db"


def _family(market_key: str) -> str:
    k = str(market_key or "")
    while True:
        k2 = re.sub(r"_\d+(?:\.\d+)?$", "", k)
        if k2 == k:
            return k
        k = k2


FAMILY_ZH = {"total_games": "全場總局數", "player_set_handicap": "盤數讓分", "player_game_handicap": "局數讓分",
             "player_first_set_game_handicap": "首盤局數讓分", "first_set_winner": "首盤勝出",
             "total_aces_ladder": "Ace 數", "match_winner": "勝負"}


def tennis_rows(day: str, trail: int, db: Path | None = None, meta: dict | None = None) -> list[dict]:
    if str(TENNIS_SRC) not in sys.path:
        sys.path.insert(0, str(TENNIS_SRC))
    from tennis_wc.pricing.props import tier_of
    lo, hi = _days(day, trail)
    con = sqlite3.connect(f"file:{db or tennis_db()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    q = """SELECT p.id, p.match_date, p.match_label, p.market_key, p.line, p.selection, p.decimal_odds,
                  p.model_prob_raw AS model_prob, fp.model_prob AS featured_prob, fp.odds AS featured_odds,
                  p.market_prob_fair, p.is_point_in_time, p.result_status, p.profit_loss_units, p.pricing_evidence_json,
                  t.name AS tournament, fp.id AS featured_id
           FROM prop_tracker p
           LEFT JOIN matches m ON m.id = p.match_id
           LEFT JOIN tournaments t ON t.id = m.tournament_id
           LEFT JOIN featured_picks fp ON fp.id = (SELECT MIN(f2.id) FROM featured_picks f2 WHERE f2.prop_id = p.id)
           WHERE p.match_date BETWEEN ? AND ? AND p.result_status IN ('WON', 'LOST')
             AND p.model_prob_raw IS NOT NULL"""
    # 冇 model_prob_raw 嘅注唔計（Sol 2026-11-26：唔准退返收縮後嘅 model_prob，嗰個可能等於市場）；
    # 精選一個 prop 多過一行都只計一次（MIN id），賠率用凍結嗰刻嘅 featured_picks.odds。
    rows = []
    excluded = 0
    for r in con.execute(q, (lo, hi)):
        if r["is_point_in_time"] != 1:
            excluded += 1
            continue
        p, m, y = float(r["model_prob"]), r["market_prob_fair"], int(r["result_status"] == "WON")
        try:
            dq = (json.loads(r["pricing_evidence_json"] or "{}") or {}).get("data_quality_score")
        except ValueError:
            dq = None
        fam = _family(r["market_key"])
        tier = tier_of(r["tournament"])
        coh = [f"family:{FAMILY_ZH.get(fam, fam)}", f"tier:{tier}"]
        if m is not None and r["is_point_in_time"] == 1:
            coh += [f"fav:{'市場熱門（≥50%）' if m >= 0.5 else '市場冷門（<50%）'}", f"gap:{_gap_band(p - float(m))}"]
        if dq is not None:
            coh.append(f"dq:資料質素 {'<50' if dq < 50 else '50–69' if dq < 70 else '≥70'}")
        if r["featured_id"]:
            coh.append("featured:精選")
        rows.append(_row(r["match_date"], int(r["id"]), p, m, y, coh, label=r["match_label"], selection=r["selection"],
                         line=r["line"], odds=r["decimal_odds"], family=FAMILY_ZH.get(fam, fam), tier=tier, dq=dq,
                         featured=bool(r["featured_id"]), featured_prob=r["featured_prob"],
                         featured_odds=r["featured_odds"], pnl=r["profit_loss_units"]))
    con.close()
    if meta is not None:
        meta["excluded_non_point_in_time"] = excluded
    return rows


def tennis_classify(p: float, m: float | None, dq) -> str:
    if m is not None and m >= MARKET_AGREE:
        return "市場都估錯"
    if dq is not None and dq < TENNIS_LOW_DQ:
        return "輸入資料薄"
    return "模型判錯"


def tennis_review(day: str, trail: int = TRAIL_DAYS, db: Path | None = None) -> dict:
    meta = {}
    rows = tennis_rows(day, trail, db, meta=meta)
    today = [x for x in rows if x["date"] == day]
    window = sorted({x["date"] for x in rows if x["date"] < day})
    mk = [x for x in today if x["m_top3"] is not None]
    feats = [x for x in today if x.get("featured")]
    feat_rows = [{"event": x["label"], "pick": f"{x['family']}：{x['selection']}",
                  "odds": x.get("featured_odds") or x["odds"], "p_model": round(float(x.get("featured_prob") or x["p_top3"]), 3),
                  "p_fair": None if x["m_top3"] is None else round(x["m_top3"], 3),
                  "state": "won" if x["hit3"] else "lost",
                  "profit": round((float(x.get("featured_odds") or x["odds"]) - 1) if x["hit3"] else -1.0, 2),
                  "tier": x["tier"],
                  **({} if x["hit3"] else {"miss": tennis_classify(float(x.get("featured_prob") or x["p_top3"]), x["m_top3"], x["dq"])})}
                 for x in feats]
    misses = [{"event": x["label"], "pick": f"{x['family']}：{x['selection']}", "tier": x["tier"], "p": round(x["p_top3"], 3),
               "m": None if x["m_top3"] is None else round(x["m_top3"], 3), "dq": x["dq"],
               "miss": tennis_classify(x["p_top3"], x["m_top3"], x["dq"])}
              for x in today if x["p_top3"] >= CONFIDENT and not x["hit3"]]
    summary = {"props": len(today), "hit_rate": _rate(today, "hit3"), "mean_p": _mean(today, "p_top3"),
               "model_logloss": _mean_ll(mk, "p_top3"), "market_logloss": _mean_ll(mk, "m_top3"), "market_props": len(mk),
               "by_family": {k: {"props": len(v), "hit_rate": _rate(v, "hit3"), "mean_p": _mean(v, "p_top3")}
                             for k, v in _group(today, "family").items()},
               "by_tier": {k: {"props": len(v), "hit_rate": _rate(v, "hit3"), "mean_p": _mean(v, "p_top3")}
                           for k, v in _group(today, "tier").items()}}
    return {"version": VERSION, "domain": "tennis", "date": day,
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "summary": summary, "meta": meta, "featured": feat_rows, "featured_summary": _feat_summary(feat_rows),
            "confident_misses": sorted(misses, key=lambda x: -x["p"])[:25],
            "confident_miss_classes": dict(Counter(m["miss"] for m in misses)),
            "confident_total": sum(1 for x in today if x["p_top3"] >= CONFIDENT),
            "cohorts": _relabel(PR._cohorts(rows, day, window, np.random.default_rng(7))),
            "window": {"days": window, "n_days": len(window)},
            "reconciliation": {"ok": True, "props_settled": len(today),
                               "note": "只計已結算（WON／LOST）；未結算／作廢唔入"},
            "rules": "描述唔係判決：唔會據此改模型；篩選每季做（Holm），判決經預先登記 forward。"}


# ---------------------------------------------------------------- 共用

def _rate(xs, k):
    return None if not xs else round(sum(x[k] for x in xs) / len(xs), 4)


def _mean(xs, k):
    return None if not xs else round(float(np.mean([x[k] for x in xs])), 4)


def _mean_ll(xs, k):
    xs = [x for x in xs if x.get(k) is not None]
    return None if not xs else round(float(np.mean([_ll(x[k], x["hit3"]) for x in xs])), 4)


def _group(xs, k):
    g = defaultdict(list)
    for x in xs:
        g[x.get(k)].append(x)
    return dict(g)


def _feat_summary(rows: list[dict]) -> dict:
    settled = [r for r in rows if r.get("state") in ("won", "lost")]
    pnl = sum(float(r.get("profit") or 0) for r in settled)
    return {"picks": len(rows), "settled": len(settled), "won": sum(r["state"] == "won" for r in settled),
            "pnl_units": round(pnl, 2), "roi": round(pnl / len(settled), 4) if settled else None}


def _relabel(cohorts: list[dict]) -> list[dict]:
    """post_review._cohorts 嘅讀法用「入位」字眼；呢度改做「中」。"""
    for c in cohorts:
        c["label"] = c["cohort"].split(":", 1)[-1]
    return cohorts


def _pct(v):
    return "—" if v is None else f"{100 * v:.1f}%"


def render_md(rv: dict) -> str:
    s, dom = rv["summary"], rv["domain"]
    L = [f"# {'NBA' if dom == 'nba' else '網球'} 自動覆盤 {rv['date']}", ""]
    if dom == "nba":
        L += [f"- 已結算腿：{s['legs']}；實際中 {_pct(s['hit_rate'])}、模型平均 {_pct(s['mean_p'])}；log-loss {s['model_logloss']}",
              f"- 同去水收盤比（{s['devig_legs']} 條有雙邊盤）：模型 {s['model_logloss_devig']} vs 市場 {s['market_logloss_devig']}（越細越準）"]
        L += ["", "| 項目 | 腿 | 實際中 | 模型平均 |", "|---|---|---|---|"]
        L += [f"| {k} | {v['legs']} | {_pct(v['hit_rate'])} | {_pct(v['mean_p'])} |" for k, v in sorted(s["by_market"].items())]
    else:
        L += [f"- 已結算 prop：{s['props']}；實際中 {_pct(s['hit_rate'])}、模型平均 {_pct(s['mean_p'])}",
              f"- 同去水市場比（{s['market_props']} 注）：模型 log-loss {s['model_logloss']} vs 市場 {s['market_logloss']}（越細越準）"]
        L += ["", "| 盤口 | 注 | 實際中 | 模型平均 |", "|---|---|---|---|"]
        L += [f"| {k} | {v['props']} | {_pct(v['hit_rate'])} | {_pct(v['mean_p'])} |" for k, v in sorted(s["by_family"].items())]
        L += ["", "| 級別 | 注 | 實際中 | 模型平均 |", "|---|---|---|---|"]
        L += [f"| {k} | {v['props']} | {_pct(v['hit_rate'])} | {_pct(v['mean_p'])} |" for k, v in sorted(s["by_tier"].items())]
    fs = rv["featured_summary"]
    L += ["", f"## 精選（紙上盤）：{fs['won']}/{fs['settled']} 中，{fs['pnl_units']:+.2f}u", ""]
    if rv["featured"]:
        L += ["| 賽事 | 精選 | 賠率 | 模型 | 去水市場 | 結果 | 失手分類 |", "|---|---|---|---|---|---|---|"]
        for f in rv["featured"]:
            res = {"won": "✅ 中", "lost": "❌", "void": "作廢"}.get(f.get("state"), f.get("state") or "—")
            L.append(f"| {f['event']} | {f['pick']} | {f.get('odds')} | {_pct(f.get('p_model'))} | {_pct(f.get('p_fair'))} | "
                     f"{res} | {f.get('miss') or '—'} |")
    if dom == "nba" and rv.get("sgm"):
        L += _render_sgm_md(rv["sgm"])
    cm = rv["confident_miss_classes"]
    L += ["", f"## 模型 ≥70% 但唔中：{sum(cm.values())}/{rv['confident_total']}（" +
          ("、".join(f"{k} {v}" for k, v in sorted(cm.items())) or "—") + "）", ""]
    if rv["confident_misses"]:
        if dom == "nba":
            L += ["| 場 | 球員 | 盤 | 模型 | 去水市場 | 上陣分鐘 | 分類 |", "|---|---|---|---|---|---|---|"]
            L += [f"| {m['game']} | {m['player']} | {m['market']} {m['side']} {m['line']} | {_pct(m['p'])} | {_pct(m['m'])} | "
                  f"{'—' if m['minutes'] is None else round(m['minutes'])} | {m['miss']} |" for m in rv["confident_misses"][:15]]
        else:
            L += ["| 賽事 | 盤 | 級別 | 模型 | 去水市場 | 資料質素 | 分類 |", "|---|---|---|---|---|---|---|"]
            L += [f"| {PR._short(m['event'], 40)} | {m['pick']} | {m['tier']} | {_pct(m['p'])} | {_pct(m['m'])} | "
                  f"{m['dq'] if m['dq'] is not None else '—'} | {m['miss']} |" for m in rv["confident_misses"][:15]]
    if rv["cohorts"]:
        L += ["", f"## 今日嘅組別，同之前 {rv['window']['n_days']} 日比（描述，唔係判決）", "",
              "| 組別 | 今日 | 今日殘差 | 跨日模型殘差 [95% CI] | 跨日市場殘差 | 讀法 |", "|---|---|---|---|---|---|"]
        for c in rv["cohorts"][:12]:
            ci = c.get("trail_model_ci_pp")
            tm = f"{c['trail_model_resid_pp']:+.1f}pp [{ci[0]:+.1f}, {ci[1]:+.1f}]（n={c['trail_n']}）" if ci else f"—（n={c['trail_n']}）"
            km = f"{c['trail_market_resid_pp']:+.1f}pp" if c.get("trail_market_resid_pp") is not None else "—"
            L.append(f"| {c['label']} | {c['today_hits']}/{c['today_n']} 中（模型預 {c['today_model_expected']}） | "
                     f"{c['today_resid_pp']:+.1f}pp | {tm} | {km} | {c['reading']} |")
        L += ["", "殘差 = 實際 − 賽前模型機率；正 = 模型低估。跨日市場殘差只計有去水價嘅注。" + rv["rules"]]
    return "\n".join(L) + "\n"


def telegram_text(rv: dict) -> str:
    s, dom, fs = rv["summary"], rv["domain"], rv["featured_summary"]
    head = "🏀 NBA" if dom == "nba" else "🎾 網球"
    n = s["legs"] if dom == "nba" else s["props"]
    lines = [f"📋 {head} 自動覆盤 {rv['date']}（{n} {'條腿' if dom == 'nba' else '注'}）",
             f"實際中 {_pct(s['hit_rate'])}・模型平均 {_pct(s['mean_p'])}",
             f"精選 {fs['won']}/{fs['settled']} 中（{fs['pnl_units']:+.2f}u）"]
    cm = rv["confident_miss_classes"]
    if cm:
        lines.append(f"模型 ≥70% 唔中 {sum(cm.values())}/{rv['confident_total']}：" +
                     "、".join(f"{k} {v}" for k, v in sorted(cm.items())))
    notable = [c for c in rv["cohorts"]
               if not str(c.get("cohort", "")).startswith("picked:")
               and c.get("trail_model_ci_pp") and "跨日同方向" in c.get("reading", "")][:3]
    if notable:
        lines.append("跨日都見到（描述，未判）：")
        lines += [f"・{c['label']}：今日 {c['today_resid_pp']:+.0f}pp，跨日 {c['trail_model_resid_pp']:+.1f}pp" for c in notable]
    return "\n".join(lines)


def _render_sgm_md(sgm: dict) -> list[str]:
    L = ["", "## SGM 組合覆盤（正式停損中＝紙上）", ""]
    ds, ts = sgm["day_summary"], sgm["trailing_summary"]
    if not ds["combos"] and not ts["combos"]:
        return L + ["今日同近窗口都冇 SGM 組合記錄。"]
    L += [
        "| 範圍 | 類別 | 組合 | 贏/輸/作廢 | 實際命中 | 模型平均 | 報價隱含 | 紙上盈虧 | ROI | 差一關 | 80%+ 斷纜腿 | 平均相關折讓 | 平均 EV |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    def _row_md(scope: str, label: str, b: dict) -> str:
        ev_s = "—" if b["mean_ev"] is None else f"{100 * b['mean_ev']:+.1f}%"
        corr_s = "—" if b["mean_correlation_discount"] is None else f"{b['mean_correlation_discount']:.3f}"
        ola_s = f"{b['one_leg_away']}/{b['lost']}（{_pct(b['one_leg_away_share'])}）" if b["lost"] else "0/0"
        return (f"| {scope} | {label} | {b['combos']} | {b['won']}/{b['lost']}/{b['void']} | "
                f"{_pct(b['hit_rate'])} | {_pct(b['mean_model_p'])} | {_pct(b['mean_implied_p'])} | "
                f"{b['pnl_units']:+.2f}u | {_pct(b['roi'])} | {ola_s} | {b['bust_p80_plus']} | {corr_s} | {ev_s} |")

    for scope, blk in (("今日", ds), (f"近 {sgm['trail_days']} 日", ts)):
        L.append(_row_md(scope, "合計", blk))
        if blk["formal"]["combos"]:
            L.append(_row_md(scope, "正式", blk["formal"]))
        if blk["research"]["combos"]:
            L.append(_row_md(scope, "紙上", blk["research"]))
    jn = sgm["join"]
    L += ["", f"- Ledger 分鐘配對率：{jn['joined_legs']}/{jn['total_legs']}（{_pct(jn['join_rate'])}）"]
    for scope, blk in (("今日", ds), (f"近 {sgm['trail_days']} 日", ts)):
        if blk["bust_legs_total"]:
            mk = "、".join(f"{k} {v}" for k, v in sorted(blk["bust_by_market"].items()))
            mc = "、".join(f"{k} {v}" for k, v in sorted(blk["bust_by_miss_class"].items()))
            pb = "、".join(f"{k} {v}" for k, v in blk["bust_by_p_band"].items() if v)
            L.append(f"- {scope}斷纜腿（{blk['bust_legs_total']} 條）：項目【{mk}】｜失手【{mc}】｜模型段【{pb}】")
        if blk["calibration_gap"] is not None and blk["settled"]:
            L.append(f"- {scope}校準差：實際 {_pct(blk['hit_rate'])} vs 模型 {_pct(blk['mean_model_p'])}（{100 * blk['calibration_gap']:+.1f}pp）"
                     + (f"；⚠️ 有 {blk['bust_p80_plus']} 條 ≥80% 穩膽腿照斷" if blk["bust_p80_plus"] else ""))
    for c in sgm["combos"]:
        res = {"won": "✅ 中", "lost": "❌ 唔中", "void": "⚪ 作廢"}.get(c["state"], f"⏳ {c['state']}")
        L += ["", f"### {c['event']}（{c['kind_label']}・{res}）"]
        odds_s = "—" if c["odds"] is None else f"{c['odds']}"
        prod_s = "—" if c["product_leg_prices"] is None else f"{c['product_leg_prices']:.2f}"
        corr_s = "—" if c["correlation_discount"] is None else f"{c['correlation_discount']:.3f}"
        ev_s = "—" if c["ev"] is None else f"{100 * c['ev']:+.1f}%"
        pnl_s = "—" if c["profit"] is None else f"{c['profit']:+.2f}u"
        L.append(f"- 報價 {odds_s}（隱含 {_pct(c['implied_p'])}）｜模型 {_pct(c['model_p'])}｜EV {ev_s}｜"
                 f"單腿積 {prod_s}（折讓 {corr_s}）｜盈虧 {pnl_s}")
        d = c["diagnosis"]
        if d["morning_update_changed"]:
            w21 = {True: "21:00 原版原本會中", False: "21:00 原版一樣唔中"}.get(d["would_21h_version_have_won"], "21:00 原版未夠賽果判斷")
            L.append(f"- 🔄 朝早重刷改過腿：{w21}")
        for l in c["legs"]:
            ico = {"won": "✓", "lost": "✗", "void": "⚪"}.get(l["state"], "⏳")
            act_s = "—" if l["actual"] is None else f"{l['actual']}"
            line_s = "—" if l["line"] is None else f"{l['line']:g}"
            mar_s = "" if l["margin"] is None else f"（差 {l['margin']:+.1f}）"
            exp_s = "—" if l["exp_minutes"] is None else f"{l['exp_minutes']:.1f}"
            actm_s = "—" if l["act_minutes"] is None else f"{l['act_minutes']:.1f}"
            rat_s = "" if l["minutes_ratio"] is None else f"（{l['minutes_ratio']:.2f}x）"
            pr_s = "—" if l["price"] is None else f"{l['price']}"
            miss_s = f"｜失手：{l['miss']}" if l.get("miss") else ""
            L.append(f"- {ico} {l['selection']}｜實 {act_s} vs 線 {line_s}{mar_s}｜"
                     f"模型 {_pct(l['model_p'])} vs 單腿 {_pct(l['implied_p'])}（{pr_s}）｜L10 {_pct(l['l10_rate'])}｜"
                     f"分鐘 {exp_s}→{actm_s}{rat_s}{miss_s}")
        if c["state"] == "won":
            verdict = "結論：全關過關。"
        elif c["state"] == "void":
            verdict = "結論：有腿作廢，整張作廢唔計。"
        elif c["state"] == "lost":
            names = "、".join(d["busted_selections"])
            verdict = (f"結論：差一關飲恨（斷喺 {names}）" if d["one_leg_away"]
                       else f"結論：斷 {d['busted_legs']} 關（{names}）")
            wl = d["weakest_link"]
            if wl:
                if d["bust_was_weakest_link"]:
                    verdict += f"；正係最弱一關（{wl['player']} 模型 {_pct(wl['model_p'])}）出事。"
                else:
                    verdict += f"；反而爆冷斷喺高信心腿（最弱一關 {wl['player']} {_pct(wl['model_p'])} 過咗）。"
            if any(l["state"] == "lost" and l["model_p"] is not None and l["model_p"] >= 0.80 for l in c["legs"]):
                verdict += " 【≥80% 穩膽腿照斷，要睇清楚係上陣定高估】"
        else:
            verdict = f"結論：{c['state']}。"
        L.append(f"- {verdict}")
    return L


def latest_settled(domain: str, cutoff: str) -> str | None:
    """健康.sh：最近一個（≤ cutoff）有已結算數據嘅日子。"""
    if domain == "nba":
        sys.path.insert(0, str(NBA_AUTO))
        import nba_market_ledger as L
        days = sorted(p.stem for p in Path(L.ledger_root()).glob("????-??-??.jsonl") if p.stem <= cutoff)
        for d in reversed(days):
            with open(Path(L.ledger_root()) / f"{d}.jsonl", encoding="utf-8") as fh:
                if any('"row_type": "settlement"' in line for line in fh):
                    return d
        return None
    con = sqlite3.connect(f"file:{tennis_db()}?mode=ro", uri=True)
    try:
        row = con.execute("SELECT MAX(match_date) FROM prop_tracker WHERE result_status IN ('WON','LOST') "
                          "AND match_date <= ?", (cutoff,)).fetchone()
    finally:
        con.close()
    return row[0] if row else None


def build(domain: str, day: str, trail: int = TRAIL_DAYS) -> dict:
    return nba_review(day, trail) if domain == "nba" else tennis_review(day, trail)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domain", choices=["nba", "tennis"], required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--trail-days", type=int, default=TRAIL_DAYS)
    ap.add_argument("--output-dir")
    ap.add_argument("--telegram", action="store_true", help="發 content 摘要（每日一次）")
    a = ap.parse_args(argv)
    rv = build(a.domain, a.date, a.trail_days)
    out = Path(a.output_dir) if a.output_dir else PR.output_dir(a.domain)
    PR._atomic(out / f"{a.date}.json", json.dumps(rv, ensure_ascii=False, indent=1, default=str))
    PR._atomic(out / f"{a.date}.md", render_md(rv))
    n = rv["summary"].get("legs", rv["summary"].get("props"))
    print(f"{out / (a.date + '.md')}：{n} 條")
    marker = out / f".{a.date}.telegram-sent"
    if a.telegram and n and not marker.exists():
        import racing_telegram as T
        res = T.send_message(telegram_text(rv), audience="content")
        if isinstance(res, dict) and res.get("ok"):
            PR._atomic(marker, datetime.now(timezone.utc).isoformat())
    if a.telegram and n:   # 排程先開 AI 解讀（L2，背景）
        import review_ai
        review_ai.spawn_daily(a.domain, a.date)
    return 0


if __name__ == "__main__":
    sys.exit(main())
