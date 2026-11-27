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
        if leg.get("picked"):
            coh.append("picked:SGM 揀中嘅腿")
        rows.append(_row(d, f"{tag}|{player}|{market}|{line}|{side}", p, m, leg["y"], coh, game=tag, player=player,
                         market=mk, line=line, side=side, minutes=_minutes(leg.get("minutes")), picked=leg.get("picked"),
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


def nba_classify(minutes: float | None, p: float | None, m: float | None, raw: float | None = None) -> str:
    if minutes is not None and minutes < LOW_MINUTES:
        return "上陣時間（冇上陣／<15 分鐘）"
    if m is not None:
        return "市場都估錯" if m >= MARKET_AGREE else "模型判錯"
    if raw is not None and raw >= MARKET_AGREE + RAW_VIG:
        return "市場都估錯（未去水）"
    return "模型判錯"


def nba_review(day: str, trail: int = TRAIL_DAYS, root: Path | None = None) -> dict:
    rows, meta = nba_rows(day, trail, root)
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
    notable = [c for c in rv["cohorts"] if c.get("trail_model_ci_pp") and "跨日同方向" in c.get("reading", "")][:3]
    if notable:
        lines.append("跨日都見到（描述，未判）：")
        lines += [f"・{c['label']}：今日 {c['today_resid_pp']:+.0f}pp，跨日 {c['trail_model_resid_pp']:+.1f}pp" for c in notable]
    return "\n".join(lines)


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
