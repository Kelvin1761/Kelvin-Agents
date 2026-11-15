#!/usr/bin/env python3
"""EXP-20261116-01：AU 上仗賠率（HKJC EXP-20261115-07 嘅 AU 版），幅度 walk-forward 擬合。

    python3 scratch/au_prior_odds_20261116.py BASE.json OUTDIR [--coverage-only]

特徵（逐匹，只用日期**嚴格早過**今仗嘅正式賽往績；試閘唔計；今仗 Flucs 永遠唔讀）：
  x1 = log(上仗最後賠率) − 場均（冇上仗價嘅馬用場均填，即 0）
  x2 = 冇正式賽往績（1/0）− 場均
綜合分 += β1·x1 + β2·x2。β 每個賽日用之前賽日嘅賽果 walk-forward 擬合：
  logistic 入位 ~ a + b·(綜合分 − 場均) + c1·x1 + c2·x2，β = c/b（b ≤ 0 → β = 0），夾喺 [−10, 10]。
arm：P（兩樣）、P1（只 x1）、P2（只 x2）。判決用 EXP-20261113-41 嘅 judge（walk_forward_oos）＋上仗相隔分層。
"""
import collections
import copy
import glob
import json
import math
import os
import re
import statistics
import subprocess
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
ROOT = open(W / ".wongchoi_au_data_root").read().strip()
START, WARMUP, CLIP = "2026-08-05", 20, 10.0
ARMS = {"P": (1, 1), "P1": (1, 0), "P2": (0, 1)}

DIRS = {os.path.basename(d): d for d in glob.glob(ROOT + "/20*") + glob.glob(ROOT + "/Archive/**/20*", recursive=True)}
HEAD = re.compile(r"^\[(\d+)\]\s+(.+?)\s+\(\d+\)\s*$")
RUN = re.compile(r"^(?P<venue>.+?)\s+R\d+\s+(?P<date>\d{4}-\d{2}-\d{2})\s")
FLUC = re.compile(r"Flucs:([$\d\s.\-]+)")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def parse_form(path):
    """→ {saddle_no: (name, [(date, price or None), ...] 正式賽)}。"""
    out, cur = {}, None
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        h = HEAD.match(line)
        if h:
            cur = int(h.group(1)); out[cur] = (h.group(2), [])
            continue
        if cur is None:
            continue
        m = RUN.match(line)
        if not m or "(TRIAL)" in line or "Barrier Trial" in line:
            continue
        price = None
        f = FLUC.search(line)
        if f:
            vals = [float(v) for v in re.findall(r"\$(\d+(?:\.\d+)?)", f.group(1))]
            price = vals[-1] if vals and vals[-1] > 1.0 else None
        out[cur][1].append((m.group("date"), price))
    return out


def features(race):
    """→ {row n: (log_price or None, has_prior bool)}；搵唔到 Formguide → None。"""
    d = DIRS.get(race["meeting"])
    fs = glob.glob(f"{d}/* Race {race['race']} Formguide.md") if d else []
    if not fs:
        return None
    form = parse_form(fs[0])
    out = {}
    for x in race["rows"]:
        rec = form.get(x["n"])
        if rec is None or norm(rec[0]) != norm(x["name"]):
            rec = next((v for v in form.values() if norm(v[0]) == norm(x["name"])), None)
        if rec is None:
            out[x["n"]] = None
            continue
        prior = [r for r in rec[1] if r[0] < race["date"]]  # 嚴格早過今仗
        if not prior:
            out[x["n"]] = (None, False)
            continue
        last = max(prior, key=lambda r: r[0])
        out[x["n"]] = (math.log(last[1]) if last[1] else None, True)
    return out


def centred(race, feats, use1, use2):
    """→ {n: (x1, x2)}，場內置中。冇資料嘅馬兩項都係 0（中性）。"""
    rows = [x for x in race["rows"] if feats.get(x["n"]) is not None]
    lp = [feats[x["n"]][0] for x in rows if feats[x["n"]][0] is not None]
    m1 = statistics.mean(lp) if lp else 0.0
    ind = [0.0 if feats[x["n"]][1] else 1.0 for x in rows]
    m2 = statistics.mean(ind) if ind else 0.0
    out = {}
    for x in race["rows"]:
        f = feats.get(x["n"])
        if f is None:
            out[x["n"]] = (0.0, 0.0)
            continue
        x1 = (f[0] - m1) if (use1 and f[0] is not None) else 0.0
        x2 = ((0.0 if f[1] else 1.0) - m2) if use2 else 0.0
        out[x["n"]] = (x1, x2)
    return out


def solve(M, v):
    n = len(v); A = [row[:] + [v[i]] for i, row in enumerate(M)]
    for i in range(n):
        piv = max(range(i, n), key=lambda r: abs(A[r][i]))
        if abs(A[piv][i]) < 1e-12:
            raise ZeroDivisionError
        A[i], A[piv] = A[piv], A[i]
        for r in range(n):
            if r != i:
                k = A[r][i] / A[i][i]
                A[r] = [a - k * b for a, b in zip(A[r], A[i])]
    return [A[i][n] / A[i][i] for i in range(n)]


def fit(samples, use1, use2):
    """samples: (ability−mean, x1, x2, y)。→ (β1, β2, coef)。"""
    idx = [0, 1] + ([2] if use1 else []) + ([3] if use2 else [])
    k = len(idx); w = [0.0] * k
    for _ in range(60):
        g = [0.0] * k; H = [[0.0] * k for _ in range(k)]
        for s in samples:
            v = [1.0, s[0], s[1], s[2]]; v = [v[i] for i in idx]
            z = sum(a * b for a, b in zip(w, v)); p = 1 / (1 + math.exp(-max(-30, min(30, z)))); q = p * (1 - p)
            for i in range(k):
                g[i] += (s[3] - p) * v[i]
                for j in range(k):
                    H[i][j] += q * v[i] * v[j]
        try:
            step = solve(H, g)
        except ZeroDivisionError:
            return 0.0, 0.0, None
        w = [a + b for a, b in zip(w, step)]
        if max(abs(s) for s in step) < 1e-8:
            break
    else:
        return 0.0, 0.0, None
    b = w[1]
    if b <= 0:
        return 0.0, 0.0, w
    c = dict(zip(idx[2:], w[2:]))
    clip = lambda v: max(-CLIP, min(CLIP, v))  # noqa: E731
    return clip(c.get(2, 0.0) / b), clip(c.get(3, 0.0) / b), w


def main():
    base_path, out = Path(sys.argv[1]), Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True)
    data = json.loads(base_path.read_text())
    races = [r for r in data["races"] if r["date"] >= START]
    feats = {}
    cov = collections.Counter()
    for r in races:
        f = features(r)
        feats[(r["meeting"], r["race"])] = f
        if f is None:
            cov["race_no_form"] += 1; cov["horse_no_form"] += len(r["rows"]); continue
        for x in r["rows"]:
            v = f.get(x["n"])
            cov["horses"] += 1
            if v is None:
                cov["unmatched"] += 1
            elif not v[1]:
                cov["no_prior_start"] += 1
            elif v[0] is None:
                cov["prior_no_price"] += 1
            else:
                cov["prior_price"] += 1
    cov["races"] = len(races)
    print("coverage", json.dumps(cov))
    (out / "coverage.json").write_text(json.dumps(cov, indent=1))
    if "--coverage-only" in sys.argv:
        return
    by_day = collections.defaultdict(list)
    for r in races:
        by_day[r["date"]].append(r)
    days = sorted(by_day)
    for arm, (u1, u2) in ARMS.items():
        samples, log, beta_of = [], [], {}
        for i, d in enumerate(days):
            b1, b2, coef = (0.0, 0.0, None) if i < WARMUP else fit(samples, u1, u2)
            beta_of[d] = (b1, b2)
            log.append({"date": d, "b1": round(b1, 4), "b2": round(b2, 4), "n_train": len(samples)})
            for r in by_day[d]:  # 當日賽果收市之後先入訓練
                f = feats[(r["meeting"], r["race"])]
                rows = [x for x in r["rows"] if isinstance(x.get("pos"), int) and x["pos"] > 0]
                if f is None or len(rows) < 3:
                    continue
                c = centred(r, f, u1, u2); m = statistics.mean(x["ability"] for x in rows)
                samples += [(x["ability"] - m, c[x["n"]][0], c[x["n"]][1], 1 if x["pos"] <= 3 else 0) for x in rows]
        cand = copy.deepcopy(data); moved = 0
        for r in cand["races"]:
            if r["date"] < START:
                continue
            f = feats[(r["meeting"], r["race"])]
            if f is None:
                continue
            b1, b2 = beta_of[r["date"]]
            c = centred(r, f, u1, u2)
            for x in r["rows"]:
                adj = b1 * c[x["n"]][0] + b2 * c[x["n"]][1]
                if adj:
                    x["ability"] += adj; moved += 1
        post = log[WARMUP:]
        print(f"{arm}: final b1 {log[-1]['b1']} b2 {log[-1]['b2']}; median post-warmup b1 "
              f"{statistics.median(e['b1'] for e in post):.3f} b2 {statistics.median(e['b2'] for e in post):.3f}; moved {moved}")
        (out / f"{arm}.betas.json").write_text(json.dumps(log, indent=0))
        p = out / f"{arm}.json"; p.write_text(json.dumps(cand))
        subprocess.run([sys.executable, str(W / "scratch/au_prior_odds_judge_20261116.py"),
                        str(base_path), str(p), str(out / f"{arm}.verdict.json")], check=True,
                       env=dict(os.environ, JUDGE_MODE="walk_forward_oos", PYTHONDONTWRITEBYTECODE="1"))
        p.unlink()


if __name__ == "__main__":
    main()
