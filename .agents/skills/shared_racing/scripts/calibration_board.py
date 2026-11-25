#!/usr/bin/env python3
"""校準板（SHADOW，EXP-20261125-07）：我哋講「X% 機會」嘅時候，實際係咪真係 X%？只寫 JSON，未上 dashboard。

輸出 `<WongChoiControl>/calibration_board.json`，逐個 domain：
  * 10pp 分桶：平均預測機率、實際命中率、Wilson 95% CI、n（n < 50 標 `low_n`）
  * 整體 log-loss；有市場價嘅就喺**同一批**馬／注上計去水市場 log-loss 做對照

Domain：
  AU／HKJC  機率 = `model_probability.py` 嘅公式，喺賽前已發佈分數上 walk-forward（每個賽日只用之前賽日 fit，
            頭 20 個賽日只訓練）；跨咗模型版本（混埋舊模型），所以係「呢條公式喺已發佈分數上準唔準」，
            唔係單一模型版本嘅成績。`live_record_exclusions` 場次唔計。
            市場：獨贏 = 收市 SP／最終獨贏賠率用 `devig.power` 去水（AU 獨贏標準，HKJC 跟同一個方法）；
            入頭三 = 由去水獨贏機率用 Harville 推（`market_ruler.harville_top3`）—— 我哋冇位置賠率，所以
            唔可以用 odds_ratio 去位置水；記低喺 `market.method`。賠率只係對照，唔入模型。
  NBA       直接讀 `~/WongChoiData/NBA_Market_Eval/reports/reliability_latest.json`（唔重計），只補 Wilson CI。
  Tennis    `prop_tracker` 已結算（WON／LOST）：all = 每個定價 prop 嘅 `model_prob_raw`；featured = 精選凍結嗰刻嘅
            `featured_picks.model_prob`。市場 = 同一行嘅 `market_prob_fair`。

    python3 calibration_board.py [--refit au|hkjc ...] [--domains au,hkjc,nba,tennis] [--output PATH]

`--refit` 會順手（同一次讀數據）重 fit 嗰個平台嘅 `<平台>_Prob_Calibration.json`。排程每晚用呢個入口，
失敗只 warn，永遠唔會令 run 失敗。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import model_probability as MP  # noqa: E402

BOARD_NAME = "calibration_board.json"
LOW_N = 50
WIDTH = 0.1
NBA_RELIABILITY = Path.home() / "WongChoiData" / "NBA_Market_Eval" / "reports" / "reliability_latest.json"
TENNIS_DB_POINTER = Path.home() / ".wongchoi_tennis_db"
EPS = 1e-6


def control_root() -> Path:
    return Path(os.environ.get("WONGCHOI_CONTROL_STATE_ROOT") or (Path.home() / "WongChoiData" / "WongChoiControl"))


# ---------------------------------------------------------------- 統計

def wilson(k: float, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def buckets(pairs, width: float = WIDTH) -> list[dict]:
    """pairs = [(預測機率, 0/1)] → 10pp 分桶（[0,0.1)…[0.9,1.0]）；空桶都列出（n=0）。"""
    k = int(round(1 / width))
    acc = [[0, 0.0, 0] for _ in range(k)]
    for p, y in pairs:
        i = min(int(p / width), k - 1) if p >= 0 else 0
        acc[i][0] += 1
        acc[i][1] += p
        acc[i][2] += int(y)
    out = []
    for i, (n, sp, hits) in enumerate(acc):
        lo, hi = round(i * width, 4), round((i + 1) * width, 4)
        out.append({"bucket": f"{lo:.1f}-{hi:.1f}", "lo": lo, "hi": hi, "n": n,
                    "mean_p": round(sp / n, 4) if n else None, "hit_rate": round(hits / n, 4) if n else None,
                    "ci": wilson(hits, n), "low_n": n < LOW_N})
    return out


def logloss(pairs) -> float | None:
    n = 0
    s = 0.0
    for p, y in pairs:
        p = min(max(float(p), EPS), 1 - EPS)
        s -= math.log(p) if y else math.log(1 - p)
        n += 1
    return round(s / n, 5) if n else None


def summary(pairs) -> dict:
    pairs = list(pairs)
    n = len(pairs)
    hits = sum(int(y) for _, y in pairs)
    return {"n": n, "mean_p": round(sum(p for p, _ in pairs) / n, 4) if n else None,
            "hit_rate": round(hits / n, 4) if n else None, "ci": wilson(hits, n), "low_n": n < LOW_N,
            "logloss": logloss(pairs), "buckets": buckets(pairs)}


# ---------------------------------------------------------------- 賽馬

def _market(race: dict):
    """→ (去水獨贏, Harville 入頭三) 或 None（有一匹冇合法價就成場唔比）。"""
    from devig import UnderroundError, InvalidOddsError, power
    from market_ruler import harville_top3

    odds = [x.get("sp") for x in race["rows"]]
    if any(o is None or o <= 1 for o in odds):
        return None
    try:
        pw = np.array(power(odds).probabilities, float)
    except (UnderroundError, InvalidOddsError, ValueError):
        return None
    return pw, harville_top3(pw)


def racing_domain(platform: str, races: list[dict]) -> dict:
    cal = MP.walk_forward(races, platform)
    pairs = {"top3": [], "win": []}
    mkt = {"top3": ([], []), "win": ([], [])}
    used, days, mraces = 0, set(), 0
    for r in MP.eligible(races, platform):
        prm = cal.get(r["date"])
        if prm is None:
            continue
        ab = [x["ability"] for x in r["rows"]]
        p3 = MP.top3_probs(ab, prm, platform)
        pw = MP.win_probs(ab, prm["beta_win"])
        y3 = [int(x["pos"] <= 3) for x in r["rows"]]
        yw = [int(x["pos"] == 1) for x in r["rows"]]
        single_winner = sum(yw) == 1
        pairs["top3"].extend(zip(p3.tolist(), y3))
        if single_winner:
            pairs["win"].extend(zip(pw.tolist(), yw))
        used += 1
        days.add(r["date"])
        m = _market(r)
        if m is not None:
            mraces += 1
            mkt["top3"][0].extend(zip(p3.tolist(), y3))
            mkt["top3"][1].extend(zip(m[1].tolist(), y3))
            if single_winner:
                mkt["win"][0].extend(zip(pw.tolist(), yw))
                mkt["win"][1].extend(zip(m[0].tolist(), yw))
    out = {"source": "walk-forward on published pre-race scores (daily refit on prior days; warm-up "
                     f"{MP.WARMUP_DAYS} days; mixed model versions)",
           "races": used, "days": len(days),
           "first_day": min(days) if days else None, "last_day": max(days) if days else None}
    for k in ("top3", "win"):
        out[k] = summary(pairs[k])
        mm, mk = mkt[k]
        out[k]["market"] = {
            "method": "devig.power on SP/final win odds" if k == "win"
            else "Harville from devig.power win probabilities (no place odds available)",
            "races": mraces, "n": len(mm), "logloss_model": logloss(mm), "logloss_market": logloss(mk),
        }
    return out


# ---------------------------------------------------------------- NBA／Tennis

def nba_domain(path: Path = NBA_RELIABILITY) -> dict:
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    d = json.loads(path.read_text(encoding="utf-8"))
    bks = []
    for b in d.get("buckets") or []:
        n, hr = int(b.get("n") or 0), b.get("hit_rate")
        bks.append({**b, "ci": wilson(round(hr * n), n) if hr is not None else None, "low_n": n < LOW_N})
    pick = lambda k: d.get(k) if isinstance(d.get(k), dict) else None  # noqa: E731
    return {"status": d.get("status"), "source": str(path), "recomputed": False, "since": d.get("since"),
            "until": d.get("until"), "probability_model_id": d.get("probability_model_id"),
            "overall": pick("overall"), "market_raw_close": pick("market_raw_close"), "picked": pick("picked"),
            "buckets": bks, "logloss": None, "note": d.get("note")}


def tennis_db_path() -> Path | None:
    try:
        p = Path(TENNIS_DB_POINTER.read_text(encoding="utf-8").strip())
    except OSError:
        p = MP.REPO / "tennis-wong-choi" / "tennis_wc.db"
    return p if p.is_file() else None


def tennis_domain(db: Path | None = None) -> dict:
    db = db or tennis_db_path()
    if db is None:
        return {"status": "missing"}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=30)
    try:
        q_all = ("SELECT model_prob_raw, market_prob_fair, result_status FROM prop_tracker "
                 "WHERE result_status IN ('WON','LOST') AND model_prob_raw IS NOT NULL")
        q_feat = ("SELECT f.model_prob, p.market_prob_fair, p.result_status FROM featured_picks f "
                  "JOIN prop_tracker p ON p.id = f.prop_id "
                  "WHERE p.result_status IN ('WON','LOST') AND f.model_prob IS NOT NULL")
        out = {"status": "ok", "source": str(db)}
        for name, q in (("all", q_all), ("featured", q_feat)):
            try:
                rows = conn.execute(q).fetchall()
            except sqlite3.Error as exc:
                out[name] = {"status": "error", "detail": str(exc)}
                continue
            pairs = [(float(m), int(s == "WON")) for m, _f, s in rows]
            both = [(float(m), float(f), int(s == "WON")) for m, f, s in rows if f is not None]
            out[name] = summary(pairs)
            out[name]["market"] = {"method": "prop_tracker.market_prob_fair", "n": len(both),
                                   "logloss_model": logloss((m, y) for m, _f, y in both),
                                   "logloss_market": logloss((f, y) for _m, f, y in both)}
        out["all"]["probability"] = "prop_tracker.model_prob_raw"
        out["featured"]["probability"] = "featured_picks.model_prob (frozen at feature time)"
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------- main

def build_board(domains, *, refit=(), roots=None, write_params=True) -> dict:
    board = {"experiment": MP.EXPERIMENT, "shadow": True, "dashboard": False,
             "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "low_n": LOW_N,
             "bucket_width": WIDTH, "domains": {}}
    for d in domains:
        try:
            if d in ("au", "hkjc"):
                root = (roots or {}).get(d) or MP.default_root(d)
                races, sources = MP.collect(d, root)
                board["domains"][d] = {**racing_domain(d, races), "sources": sources}
                if d in refit:
                    target = MP.default_target(d)
                    params_path = root / MP.OUTPUT_NAMES[d]
                    prev = None
                    if params_path.is_file():
                        try:
                            prev = json.loads(params_path.read_text(encoding="utf-8"))
                        except (OSError, ValueError):
                            prev = None
                    payload = MP.build(d, [r for r in races if r["date"] < target], target,
                                       mid=MP.model_id(d), epoch=MP.au_model_epoch() if d == "au" else None,
                                       previous=prev, sources=sources)
                    if write_params:
                        tmp = params_path.with_suffix(".tmp")
                        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                        tmp.replace(params_path)
                    board["domains"][d]["params"] = {k: payload.get(k) for k in (
                        "status", "model_id", "fit_until", "n_races", "n_days", "a", "alpha", "gamma", "beta_win")}
            elif d == "nba":
                board["domains"][d] = nba_domain()
            elif d == "tennis":
                board["domains"][d] = tennis_domain()
        except Exception as exc:  # noqa: BLE001 —— 一個 domain 壞唔好拖死其他
            board["domains"][d] = {"status": "error", "detail": f"{type(exc).__name__}: {exc}"}
    return board


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--domains", default="au,hkjc,nba,tennis")
    ap.add_argument("--refit", action="append", default=[], choices=("au", "hkjc"))
    ap.add_argument("--output", default=None)
    args = ap.parse_args(argv)
    board = build_board([d.strip() for d in args.domains.split(",") if d.strip()], refit=tuple(args.refit))
    out = Path(args.output) if args.output else control_root() / BOARD_NAME
    prev = {}
    if out.is_file() and args.domains != "au,hkjc,nba,tennis":
        try:  # 只重建部分 domain 時保留其他 domain 上一版
            prev = json.loads(out.read_text(encoding="utf-8")).get("domains") or {}
        except (OSError, ValueError):
            prev = {}
    board["domains"] = {**prev, **board["domains"]}
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(board, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(out)
    brief = {}
    for d, v in board["domains"].items():
        if d in ("au", "hkjc") and "top3" in v:
            brief[d] = {"races": v["races"], "top3_ll": v["top3"]["logloss"], "win_ll": v["win"]["logloss"],
                        "win_mkt": [v["win"]["market"]["logloss_model"], v["win"]["market"]["logloss_market"]],
                        "params": (v.get("params") or {}).get("status")}
        else:
            brief[d] = v.get("status")
    print(json.dumps({"output": str(out), **brief}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
