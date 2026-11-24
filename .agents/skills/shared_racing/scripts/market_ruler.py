#!/usr/bin/env python3
"""市場尺：模型喺收市價以外有冇額外資訊（docs/model-evaluation-contract.md「市場尺」；EXP-20261124-90）。

排名尺（AU log-loss v2、HKJC 回放 v5）問「排名準唔準」；呢把尺問「準得過市場嗎」。
模型排名可以改善好多次，但如果改善嘅資訊收市價已經有，落注都係蝕抽水（EXP-20261124-23／-60）。

方法（Benter 式，同 EXP-20261124-60 Q1 一樣，只係改做標準工具）：
  市場機率 p_m = (1/收市價) 場內正規化；模型 z = 場內標準化 ability。
  獨贏（主）：條件 logit 頭馬  s = α·log p_m + β·z      vs 淨市場 s = α·log p_m
  入頭三（輔）：逐匹 logistic  logit P = c + α·logit q_m + β·z  vs 冇 β；q_m = Harville 由 p_m 推嘅入頭三機率
  walk-forward：每 7 個賽日重 fit，只用之前賽日；頭 20 個賽日只訓練唔計分。
  每場 Δll = ll(市場＋模型) − ll(淨市場)；正 = 模型有市場冇嘅資訊。賽日 bootstrap 2,000。
  賠率只係**評估基準**，唔入模型、唔揀注（AGENTS.md「賠率唔准做隱藏 proxy」唔受影響）。

兩個問題：
  A. 單一模型（arm）：Δll 95% CI 下界 > 0 → 「有市場以外資訊」（落真錢嘅必要條件，唔係充分條件）。
  B. 候選對 baseline（配對）：ΔΔ = Δll(候選) − Δll(baseline)。
     市場尺 PASS = 獨贏 ΔΔ CI 下界 > 0、入頭三 ΔΔ 點估計 ≥ 0、三個時間塊至少兩個 ΔΔ > 0。

    python3 market_ruler.py --platform au BASE.json [CAND.json] [--price sp|bsp] [--out result.json]

AU：`--price sp`（預設）= dump 每匹嘅 `sp`（賽果 SP，任何 dump 都有）；
    `--price bsp` = Betfair BSP（`au_bsp.py`：記錄器＋公開 CSV，EXP-20261124-92），較 sharp；配唔齊 BSP 嘅場會剔走並報數。
HKJC：未接駁 —— 回放語料冇當日最終賠率（下一步）。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit

WARMUP_DAYS = 20
REFIT_EVERY = 7
BOOTSTRAP = 2000
BLOCKS = 3
MIN_DAYS = 30        # 配對判決最少計分賽日（Sol 覆核：太少日 bootstrap CI 會退化）
TOP3_MIN_FIELD = 4   # 入頭三：≤3 匹嘅場個個入三甲，冇資訊，唔計
VERSION = "m1"
SINCE = {"au": "2026-08-05"}   # 同 au_logloss_ruler.CLEAN_SINCE：之前嘅場次唔係乾淨 point-in-time


# ---------------------------------------------------------------- 準備

def prepare(races, *, price_key="sp", ability_key="ability"):
    """→ (場次 list, 統計)。只留有頭馬、每匹都有合法價（>1）同 ability 嘅場；按日期排。"""
    out, skipped = [], defaultdict(int)
    keys = defaultdict(int)
    for r in races:
        keys[(r["date"], r.get("meeting", ""), r["race"])] += 1
    for r in sorted(races, key=lambda r: (r["date"], r.get("meeting", ""), r["race"])):
        if keys[(r["date"], r.get("meeting", ""), r["race"])] > 1:
            skipped["duplicate_key"] += 1
            continue
        rows = r["rows"]
        if len(rows) < 3:
            skipped["field_lt3"] += 1
            continue
        prices = [x.get(price_key) for x in rows]
        if any(not isinstance(p, (int, float)) or not p or p <= 1 for p in prices):
            skipped["missing_price"] += 1
            continue
        pos = np.array([int(x["pos"]) for x in rows])
        if (pos == 1).sum() != 1:
            skipped["no_single_winner"] += 1
            continue
        ab = np.array([float(x[ability_key]) for x in rows])
        pm = 1 / np.array(prices, float)
        pm = pm / pm.sum()
        sd = ab.std()
        out.append({
            "key": (r["date"], r.get("meeting", ""), r["race"]),
            "date": r["date"],
            "logp": np.log(pm),
            "q3": harville_top3(pm),
            "z": (ab - ab.mean()) / sd if sd > 0 else np.zeros(len(ab)),
            "win": int(np.argmax(pos == 1)),
            "top3": (pos <= 3).astype(float),
            # 配對時驗證兩邊係同一場：馬名、名次、價（ability 可以唔同）
            "sig": tuple(sorted((str(x.get("name", x.get("n", i))), int(x["pos"]), round(float(x[price_key]), 4))
                                for i, x in enumerate(rows))),
        })
    return out, dict(skipped)


def harville_top3(p):
    """Harville：由獨贏機率推入頭三機率（精確，O(N³)）。"""
    n = len(p)
    q = p.copy()
    for i in range(n):
        for j in range(n):
            if j == i:
                continue
            pj = p[j]
            d1 = 1 - pj
            q[i] += pj * p[i] / d1                      # j 第一、i 第二
            for k in range(n):
                if k in (i, j):
                    continue
                q[i] += pj * p[k] / d1 * p[i] / (1 - pj - p[k])   # j、k 頭二，i 第三
    return np.clip(q, 1e-6, 1 - 1e-6)


# ---------------------------------------------------------------- 模型

def _win_nll(theta, races, use_model):
    a, b = theta[0], (theta[1] if use_model else 0.0)
    nll, ga, gb = 0.0, 0.0, 0.0
    for r in races:
        s = a * r["logp"] + b * r["z"]
        s = s - s.max()
        e = np.exp(s)
        p = e / e.sum()
        w = r["win"]
        nll -= s[w] - math.log(e.sum())
        ga -= r["logp"][w] - p @ r["logp"]
        gb -= r["z"][w] - p @ r["z"]
    return nll, (np.array([ga, gb]) if use_model else np.array([ga]))


def _place_design(r, use_model):
    lq = np.log(r["q3"] / (1 - r["q3"]))
    cols = [np.ones(len(lq)), lq] + ([r["z"]] if use_model else [])
    return np.column_stack(cols)


def _place_nll(theta, races, use_model):
    nll, g = 0.0, np.zeros(len(theta))
    for r in races:
        X = _place_design(r, use_model)
        s = X @ theta
        y = r["top3"]
        # 穩定寫法：−log σ(s) = log(1+e^−s)；−log(1−σ(s)) = log(1+e^s)
        nll += float((y * np.logaddexp(0, -s) + (1 - y) * np.logaddexp(0, s)).sum())
        g -= X.T @ (y - expit(s))
    return nll, g


MARKETS = {
    "win": (_win_nll, [1.0, 0.0], [1.0]),
    "top3": (_place_nll, [0.0, 1.0, 0.0], [0.0, 1.0]),
}


FIT_FAILURES = []


def _fit(fn, x0, races, use_model):
    k = max(len(races), 1)

    def obj(t):   # 除以場數：大訓練集嘅總和 NLL 令 BFGS 報 precision loss
        v, g = fn(t, races, use_model)
        return v / k, g / k

    res = minimize(obj, np.array(x0, float), jac=True, method="BFGS", options={"gtol": 1e-7})
    if not res.success:
        FIT_FAILURES.append(str(res.message))
    return res.x


def walk_forward(R, market):
    """→ (每場 Δll list（同 R 對齊，warm-up 場 = None）, 最後一次 fit 嘅 θ（有模型）)。"""
    fn, x0m, x0b = MARKETS[market]
    days = sorted({r["date"] for r in R})
    by_day = defaultdict(list)
    for i, r in enumerate(R):
        if market == "top3" and len(r["z"]) < TOP3_MIN_FIELD:
            continue
        by_day[r["date"]].append(i)
    out = [None] * len(R)
    th_m = th_b = None
    for j, d in enumerate(days):
        if j < WARMUP_DAYS:
            continue
        if th_m is None or (j - WARMUP_DAYS) % REFIT_EVERY == 0:
            train = [R[i] for dd in days[:j] for i in by_day[dd]]
            th_m = _fit(fn, x0m, train, True)
            th_b = _fit(fn, x0b, train, False)
        for i in by_day[d]:
            out[i] = fn(th_b, [R[i]], False)[0] - fn(th_m, [R[i]], True)[0]
    return out, [float(v) for v in th_m] if th_m is not None else None


# ---------------------------------------------------------------- 統計

def _by_day(R, vals):
    d = defaultdict(list)
    for r, v in zip(R, vals):
        if v is not None:
            d[r["date"]].append(v)
    return d


def bootstrap_mean(by_day, seed=0, n=BOOTSTRAP):
    days = sorted(by_day)
    if not days:
        return None, None
    sums = np.array([sum(by_day[d]) for d in days])
    cnts = np.array([len(by_day[d]) for d in days])
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(days), (n, len(days)))
    bs = sums[idx].sum(1) / cnts[idx].sum(1)
    return float(sums.sum() / cnts.sum()), [float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]


def blocks(by_day, k=BLOCKS):
    days = sorted(by_day)
    out = []
    for c in np.array_split(np.arange(len(days)), k):
        if len(c) == 0:
            continue
        vals = [v for i in c for v in by_day[days[i]]]
        out.append({"from": days[c[0]], "to": days[c[-1]], "races": len(vals),
                    "mean": float(np.mean(vals)) if vals else None})
    return out


def summarise(R, vals):
    bd = _by_day(R, vals)
    m, ci = bootstrap_mean(bd)
    return {"races": sum(len(v) for v in bd.values()), "days": len(bd), "dll_per_race": m, "ci": ci,
            "blocks": blocks(bd)}


# ---------------------------------------------------------------- 判決

def judge_arm(arm):
    """→ {"win": bool, "top3": bool}：嗰個市場 Δll CI 下界 > 0。"""
    return {k: bool(arm[k]["ci"] and arm[k]["ci"][0] > 0) for k in MARKETS}


def judge_pair(pair):
    w, p = pair["win"], pair["top3"]
    positive_blocks = sum(1 for b in w["blocks"] if (b["mean"] or 0) > 0)
    checks = {
        "enough_days": w["days"] >= MIN_DAYS and len([b for b in w["blocks"] if b["races"]]) == BLOCKS,
        "win_ci_lower_gt_0": bool(w["ci"] and w["ci"][0] > 0),
        "top3_point_ge_0": bool(p["dll_per_race"] is not None and p["dll_per_race"] >= 0),
        "win_blocks_2_of_3": positive_blocks >= 2,
    }
    return {"verdict": "PASS" if all(checks.values()) else "FAIL", "checks": checks,
            "win_positive_blocks": positive_blocks}


def evaluate(base_races, cand_races=None, *, price_key="sp", since=None):
    FIT_FAILURES.clear()
    if since:
        base_races = [r for r in base_races if str(r.get("date") or "") >= since]
        cand_races = None if cand_races is None else [r for r in cand_races if str(r.get("date") or "") >= since]
    RB, skip_b = prepare(base_races, price_key=price_key)
    result = {"version": VERSION, "price": price_key, "since": since, "skipped": {"baseline": skip_b}}
    arms = {"baseline": RB}
    if cand_races is not None:
        RC, skip_c = prepare(cand_races, price_key=price_key)
        result["skipped"]["candidate"] = skip_c
        cmap = {r["key"]: r for r in RC}
        pairs, mismatch = [], 0
        for rb in RB:
            rc = cmap.get(rb["key"])
            if rc is None:
                continue
            if rc["sig"] != rb["sig"]:
                mismatch += 1       # 同 key 但馬／名次／價唔同 = 唔係同一場，唔准配對
                continue
            pairs.append((rb, rc))
        RB = [b for b, _ in pairs]
        RC = [c for _, c in pairs]
        arms = {"baseline": RB, "candidate": RC}
        result["common_races"] = len(pairs)
        result["mismatched_races"] = mismatch
    per = {}
    for name, R in arms.items():
        per[name] = {"_vals": {}}
        for mk in MARKETS:
            vals, theta = walk_forward(R, mk)
            per[name]["_vals"][mk] = vals
            per[name][mk] = summarise(R, vals) | {"theta_last": theta}
        per[name]["has_info_beyond_market"] = judge_arm(per[name])
    if "candidate" in per:
        pair = {}
        for mk in MARKETS:
            dd = [None if a is None or b is None else a - b
                  for a, b in zip(per["candidate"]["_vals"][mk], per["baseline"]["_vals"][mk])]
            pair[mk] = summarise(arms["baseline"], dd)
        result["paired"] = pair | judge_pair(pair)
    for name in per:
        per[name].pop("_vals")
    result["arms"] = per
    result["fit_failures"] = list(FIT_FAILURES)
    return result


# ---------------------------------------------------------------- CLI

def _fmt(s):
    if s["dll_per_race"] is None:
        return "（冇數據）"
    lo, hi = s["ci"]
    return f"{s['dll_per_race']:+.5f} [{lo:+.5f}, {hi:+.5f}]（{s['races']} 場／{s['days']} 日）"


def _load(path, platform):
    if platform != "au":
        sys.exit(f"--platform {platform} 未接駁：HKJC 回放語料冇當日最終賠率，見 docs/model-evaluation-contract.md「市場尺」")
    return json.loads(Path(path).read_text(encoding="utf-8"))["races"]


def attach_bsp(*arms):
    """AU：將 BSP 寫入每匹 row["bsp"]；→ 每個 arm 嘅配對統計。"""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "au_racing" / "au_wong_choi_auto" / "scripts"))
    import au_bsp
    index = au_bsp.load_all()
    return [au_bsp.attach(races, index) for races in arms if races is not None]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--platform", required=True, choices=["au", "hkjc"])
    ap.add_argument("base")
    ap.add_argument("cand", nargs="?")
    ap.add_argument("--price", choices=["sp", "bsp"], default="sp")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    base = _load(a.base, a.platform)
    cand = _load(a.cand, a.platform) if a.cand else None
    since = SINCE.get(a.platform)
    match = None
    if a.price == "bsp":
        base = [r for r in base if not since or r["date"] >= since]
        cand = None if cand is None else [r for r in cand if not since or r["date"] >= since]
        match = attach_bsp(base, cand)
        print(f"BSP 配對：{match}")
    res = evaluate(base, cand, price_key=a.price, since=since)
    if match:
        res["bsp_match"] = match
    for name, arm in res["arms"].items():
        print(f"== {name}：模型對收市價（{res['price']}）有冇額外資訊（每場 Δlog-lik，正 = 有）")
        for mk in MARKETS:
            print(f"   {mk:5s} {_fmt(arm[mk])}  β={arm[mk]['theta_last']}")
        print(f"   有市場以外資訊：{arm['has_info_beyond_market']}")
    if "paired" in res:
        p = res["paired"]
        print("== 候選 − baseline（配對）")
        for mk in MARKETS:
            print(f"   {mk:5s} {_fmt(p[mk])}  時間塊 {[round(b['mean'] or 0, 5) for b in p[mk]['blocks']]}")
        print(f"   市場尺 {VERSION}：{p['verdict']}  {p['checks']}")
        if res.get("mismatched_races"):
            print(f"   ⚠️ {res['mismatched_races']} 場同 key 但馬／名次／價唔同，冇配對")
    if res["fit_failures"]:
        print(f"⚠️ {len(res['fit_failures'])} 次 fit 未收斂：{sorted(set(res['fit_failures']))}")
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
