#!/usr/bin/env python3
"""AU 主判決尺：入頭三 log-loss（Kelvin 2026-11-21 決定；docs/model-evaluation-contract.md「AU log-loss 尺」）。

同 HKJC v4（`hkjc_replay_compare_v4.py`）一樣嘅判法，但 AU 冇長歷史回放（賽前輸入重砌唔到，EXP-20261121-35），
所以用 2026-08-05 起乾淨 point-in-time 語料，校準 walk-forward：

  p = σ(a + α·(raw − 場均))；(a, α) baseline 同候選**各自** fit，每 7 個賽日重 fit 一次，只用之前賽日；
  頭 20 個賽日只做訓練，唔計分。

判法（三樣都過 = PASS）：
  1. Δlog-loss（候選 − baseline，每匹）95% CI 上界 < 0（賽日 bootstrap 2,000）
  2. 護欄：Gold、Good 各自 95% CI 下界 > −1.0pp
  3. Δlog-loss 好過 95% 場內洗牌 null（候選對 baseline 嘅分數差喺場內隨機排列）
另報 Gold、Good、capture@5、頭二選有中（唔係閘）。

驗證（EXP-20261121-35）：A/A REJECT；純噪音 0/40；人工真改善 20/20；13 個舊候選冇翻案。

輸入同 `au_eval` dump 一樣：races = [{"date", "meeting", "race", "rows": [{"ability", "pos"}, ...]}]，
baseline 同候選要同一批場次、同一個次序。fit 類候選嘅 dump 本身要係 walk-forward 預測（同 v3 規矩）。

    python3 au_logloss_ruler.py BASE.json CAND.json [--null 200]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "shared_racing"))
from eval_metrics import race_metrics  # noqa: E402

CLEAN_SINCE = "2026-08-05"
WARMUP_DAYS = 20
REFIT_EVERY = 7
BOOTSTRAP = 2000
GUARDRAIL_PP = -1.0
NULL_SHARE = 0.95


def eligible(races):
    """乾淨語料、有頭馬兼 ≥ 3 匹入三甲；按日期排。"""
    out = [r for r in races if str(r.get("date") or "") >= CLEAN_SINCE
           and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(out, key=lambda r: (r["date"], r["meeting"], r["race"]))


def _xy(race, raws=None):
    r = np.array([x["ability"] for x in race["rows"]], float) if raws is None else raws
    return r - r.mean(), np.array([int(x["pos"] <= 3) for x in race["rows"]])


def _fit(X, Y):
    a = b = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(a + b * X, -30, 30)))
        w = p * (1 - p)
        g = np.array([(Y - p).sum(), ((Y - p) * X).sum()])
        H = np.array([[w.sum(), (w * X).sum()], [(w * X).sum(), (w * X * X).sum()]])
        step = np.linalg.solve(H, g)
        a, b = a + step[0], b + step[1]
        if np.abs(step).max() < 1e-9:
            break
    return a, b


def calibrations(races):
    """→ {賽日: (a, α)}，只用嗰日之前嘅賽日；warm-up 日冇（唔計分）。"""
    days = sorted({r["date"] for r in races})
    by = defaultdict(list)
    for r in races:
        by[r["date"]].append(r)
    out, X, Y, cur = {}, [], [], None
    for i, d in enumerate(days):
        if i >= WARMUP_DAYS:
            if cur is None or (i - WARMUP_DAYS) % REFIT_EVERY == 0:
                cur = _fit(np.concatenate(X), np.concatenate(Y))
            out[d] = cur
        for r in by[d]:
            x, y = _xy(r)
            X.append(x)
            Y.append(y)
    return out


def _nll(race, ab, raws=None):
    x, y = _xy(race, raws)
    p = np.clip(1 / (1 + np.exp(-np.clip(ab[0] + ab[1] * x, -30, 30))), 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()), len(y)


def _metrics(race):
    order = sorted(range(len(race["rows"])), key=lambda i: -race["rows"][i]["ability"])
    pos = {i: race["rows"][i]["pos"] for i in range(len(race["rows"]))}
    m = race_metrics(order, {i for i, p in pos.items() if p <= 3}, actual_pos=pos)
    return [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"])]


def evaluate(baseline, candidate, *, nnull=200, seed=0):
    """→ {"verdict": PASS|REJECT, "reason", 數字…}。baseline／candidate 係已經 `eligible` 過、同次序嘅場次。"""
    if [(r["meeting"], r["race"]) for r in baseline] != [(r["meeting"], r["race"]) for r in candidate]:
        raise ValueError("baseline／candidate 場次唔一致")
    cb, cc = calibrations(baseline), calibrations(candidate)
    rows = []
    for b, c in zip(baseline, candidate):
        if b["date"] not in cb:
            continue
        lb, n = _nll(b, cb[b["date"]])
        lc, _ = _nll(c, cc[c["date"]])
        rows.append((b, c, b["date"], lc - lb, n, np.array(_metrics(c)) - np.array(_metrics(b))))
    if not rows:
        return {"verdict": "REJECT", "reason": "no_scored_races", "races": 0}
    days = sorted({r[2] for r in rows})
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r[2]].append(i)
    dl = np.array([r[3] for r in rows])
    nn = np.array([r[4] for r in rows])
    M = np.array([r[5] for r in rows])
    rng = np.random.default_rng(seed)
    bl, bm = [], []
    for _ in range(BOOTSTRAP):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))])
        bl.append(dl[ii].sum() / nn[ii].sum())
        bm.append(M[ii].mean(0))
    bl, bm = np.array(bl), np.array(bm)
    d = dl.sum() / nn.sum()
    null = []
    for _ in range(nnull):
        tot = 0.0
        for b, c, day, *_ in rows:
            delta = np.array([y["ability"] - x["ability"] for x, y in zip(b["rows"], c["rows"])])
            if not delta.any():
                continue
            raws = np.array([x["ability"] for x in b["rows"]]) + rng.permutation(delta)
            tot += _nll(b, cc[day], raws)[0] - _nll(b, cb[day])[0]
        null.append(tot / nn.sum())
    null = np.array(null)
    lo = np.percentile(bm, 2.5, axis=0) * 100
    checks = {"logloss_ci_upper_below_0": bool(np.percentile(bl, 97.5) < 0),
              "gold_good_guardrail": bool(lo[0] > GUARDRAIL_PP and lo[1] > GUARDRAIL_PP),
              "beats_null": bool(len(null) and (null > d).mean() >= NULL_SHARE)}
    failed = [k for k, ok in checks.items() if not ok]
    return {"verdict": "REJECT" if failed else "PASS", "reason": failed[0] if failed else "logloss_supported_gain",
            "checks": checks, "races": len(rows), "days": len(days),
            "dlogloss": [d, float(np.percentile(bl, 2.5)), float(np.percentile(bl, 97.5))],
            "beats_null_share": float((null > d).mean()) if len(null) else None,
            "gold_pp": [float(M[:, 0].mean() * 100), float(lo[0])], "good_pp": [float(M[:, 1].mean() * 100), float(lo[1])],
            "capture5_pp": float(M[:, 2].mean() * 100), "top2_any_hit_pp": float(M[:, 3].mean() * 100)}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    nnull = int(argv[argv.index("--null") + 1]) if "--null" in argv else 200
    load = lambda p: eligible(json.loads(Path(p).read_text())["races"])  # noqa: E731
    print(json.dumps(evaluate(load(argv[0]), load(argv[1]), nnull=nnull), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
