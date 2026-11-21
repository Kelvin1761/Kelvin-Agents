#!/usr/bin/env python3
"""EXP-20261121-35：AU log-loss 尺（照 HKJC v4，`hkjc_replay_compare_v4.py`）喺現有 08-05 起乾淨語料上驗證。

主指標：入頭三 log-loss（逐匹）。p = σ(a + α·(raw − 場均))；(a, α) baseline 同候選**各自** walk-forward fit
（每 7 日重 fit 一次，只用之前賽日；頭 20 個賽日只做訓練，唔計分）。
判法（同 HKJC v4）：
  1. Δlog-loss（候選 − baseline）95% CI 上界 < 0（賽日 bootstrap 2,000）
  2. 護欄：Gold、Good 各自 95% CI 下界 > −1.0pp
  3. Δlog-loss 好過 95% 場內洗牌 null（候選對 baseline 嘅 raw Δ 場內隨機排列，同幅度、冇資訊）
  另報 AUC、capture@5、頭二選有中。

  compare.py pairs BASE.json CAND.json [...]       逐個候選 v4 判決（null 100 次）
  compare.py null  BASE.json SIGMA SEEDS            純噪音候選誤判率（null 50 次）
  compare.py power BASE.json BUMP SHARE SEEDS [rank3to5]
"""
import json, random, sys
from collections import defaultdict
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[4]
SCRIPTS = W / ".agents/skills/au_racing/au_wong_choi_auto/scripts"
for p in (SCRIPTS, SCRIPTS.parents[2] / "shared_racing"):
    sys.path.insert(0, str(p))
from eval_metrics import race_metrics  # noqa: E402

WARMUP_DAYS, REFIT_EVERY = 20, 7


def load(path):
    races = [r for r in json.loads(Path(path).read_text())["races"] if r["date"] >= "2026-08-05"
             and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(races, key=lambda r: (r["date"], r["meeting"], r["race"]))


def xy(race, raws=None):
    r = np.array([x["ability"] for x in race["rows"]], float) if raws is None else raws
    return r - r.mean(), np.array([int(x["pos"] <= 3) for x in race["rows"]])


def fit(X, Y):
    a = b = 0.0
    for _ in range(50):
        z = np.clip(a + b * X, -30, 30); p = 1 / (1 + np.exp(-z)); w = p * (1 - p)
        g = np.array([(Y - p).sum(), ((Y - p) * X).sum()])
        H = np.array([[w.sum(), (w * X).sum()], [(w * X).sum(), (w * X * X).sum()]])
        step = np.linalg.solve(H, g); a, b = a + step[0], b + step[1]
        if np.abs(step).max() < 1e-9:
            break
    return a, b


def calibrations(races):
    """→ {date: (a, α)}，只用嗰日之前嘅賽日 fit；warm-up 日冇。"""
    days = sorted({r["date"] for r in races})
    by = defaultdict(list)
    for r in races:
        by[r["date"]].append(r)
    out, X, Y, cur = {}, [], [], None
    for i, d in enumerate(days):
        if i >= WARMUP_DAYS:
            if cur is None or (i - WARMUP_DAYS) % REFIT_EVERY == 0:
                cur = fit(np.concatenate(X), np.concatenate(Y))
            out[d] = cur
        for r in by[d]:
            x, y = xy(r); X.append(x); Y.append(y)
    return out


def nll(race, ab, raws=None):
    x, y = xy(race, raws)
    p = np.clip(1 / (1 + np.exp(-np.clip(ab[0] + ab[1] * x, -30, 30))), 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()), len(y)


def metrics(race):
    order = sorted(range(len(race["rows"])), key=lambda i: -race["rows"][i]["ability"])
    pos = {i: race["rows"][i]["pos"] for i in range(len(race["rows"]))}
    m = race_metrics(order, {i for i, p in pos.items() if p <= 3}, actual_pos=pos)
    return [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"])]


def judge(base, cand, nnull=100, seed=0):
    cb, cc = calibrations(base), calibrations(cand)
    rows = []
    for b, c in zip(base, cand):
        if b["date"] not in cb:
            continue
        lb, n = nll(b, cb[b["date"]]); lc, _ = nll(c, cc[c["date"]])
        rows.append((b, c, b["date"], lc - lb, n, np.array(metrics(c)) - np.array(metrics(b))))
    days = sorted({r[2] for r in rows}); by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r[2]].append(i)
    dl = np.array([r[3] for r in rows]); nn = np.array([r[4] for r in rows]); M = np.array([r[5] for r in rows])
    rng = np.random.default_rng(seed); bl, bm = [], []
    for _ in range(2000):
        ii = np.concatenate([by[days[j]] for j in rng.integers(0, len(days), len(days))])
        bl.append(dl[ii].sum() / nn[ii].sum()); bm.append(M[ii].mean(0))
    bl, bm = np.array(bl), np.array(bm)
    d = dl.sum() / nn.sum()
    null = []
    for _ in range(nnull):
        tot = 0.0
        for b, c, day, _dl, _n, _m in rows:
            delta = np.array([y["ability"] - x["ability"] for x, y in zip(b["rows"], c["rows"])])
            if not delta.any():
                continue
            raws = np.array([x["ability"] for x in b["rows"]]) + rng.permutation(delta)
            tot += nll(b, cc[day], raws)[0] - nll(b, cb[day])[0]
        null.append(tot / nn.sum())
    null = np.array(null)
    lo_m = np.percentile(bm, 2.5, axis=0) * 100
    p1 = np.percentile(bl, 97.5) < 0
    p2 = lo_m[0] > -1.0 and lo_m[1] > -1.0
    p3 = bool(len(null)) and (null > d).mean() >= 0.95
    return {"verdict": "PASS" if (p1 and p2 and p3) else "REJECT", "races": len(rows), "days": len(days),
            "dlogloss": [round(d, 6), round(float(np.percentile(bl, 2.5)), 6), round(float(np.percentile(bl, 97.5)), 6)],
            "beats_null": round(float((null > d).mean()), 3) if len(null) else None,
            "gold_pp": [round(M[:, 0].mean() * 100, 2), round(lo_m[0], 2)],
            "good_pp": [round(M[:, 1].mean() * 100, 2), round(lo_m[1], 2)],
            "capture5_pp": round(M[:, 2].mean() * 100, 2), "top2_any_pp": round(M[:, 3].mean() * 100, 2),
            "checks": {"ci_upper_below_0": bool(p1), "guardrail": bool(p2), "beats_null": bool(p3)}}


def pairs(base_path, cands):
    base = load(base_path); out = {"AA": judge(base, base, nnull=0)}
    print("AA", out["AA"]["verdict"], out["AA"]["dlogloss"], flush=True)
    for path in cands:
        cand = load(path)
        assert [(r["meeting"], r["race"]) for r in cand] == [(r["meeting"], r["race"]) for r in base], path
        out[Path(path).stem] = v = judge(base, cand)
        print(Path(path).stem, v["verdict"], v["dlogloss"], "null", v["beats_null"], "gold", v["gold_pp"], "good", v["good_pp"], flush=True)
    print(json.dumps(out, ensure_ascii=False))


def _noise(base, sigma, seed):
    rng = random.Random(seed)
    return [dict(r, rows=[dict(x, ability=x["ability"] + rng.gauss(0, sigma)) for x in r["rows"]]) for r in base]


def _bump(base, bump, share, seed, target):
    rng = random.Random(1000 + seed); out = []
    for r in base:
        order = sorted(range(len(r["rows"])), key=lambda i: -r["rows"][i]["ability"])
        rk = {i: k + 1 for k, i in enumerate(order)}
        out.append(dict(r, rows=[dict(x, ability=x["ability"] + (bump if x["pos"] <= 3 and (target == "all" or 3 <= rk[i] <= 5)
                                                                   and rng.random() < share else 0.0))
                                 for i, x in enumerate(r["rows"])]))
    return out


def null_mode(base_path, sigma, seeds):
    base = load(base_path); res = []
    for s in range(int(seeds)):
        v = judge(base, _noise(base, float(sigma), s), nnull=50, seed=s); res.append(v["verdict"])
        print(s, v["verdict"], v["dlogloss"], v["beats_null"], flush=True)
    print(json.dumps({"pass": sum(x == "PASS" for x in res), "n": len(res)}))


def power_mode(base_path, bump, share, seeds, target="all"):
    base = load(base_path); res = []
    for s in range(int(seeds)):
        v = judge(base, _bump(base, float(bump), float(share), s, target), nnull=50, seed=s); res.append(v["verdict"])
        print(s, v["verdict"], v["dlogloss"], v["beats_null"], flush=True)
    print(json.dumps({"pass": sum(x == "PASS" for x in res), "n": len(res)}))


if __name__ == "__main__":
    {"pairs": lambda: pairs(sys.argv[2], sys.argv[3:]), "null": lambda: null_mode(*sys.argv[2:5]),
     "power": lambda: power_mode(*sys.argv[2:7])}[sys.argv[1]]()
