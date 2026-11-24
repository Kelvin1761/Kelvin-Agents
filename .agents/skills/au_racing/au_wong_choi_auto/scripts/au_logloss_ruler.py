#!/usr/bin/env python3
"""AU 主判決尺：入頭三 log-loss（Kelvin 2026-11-21 決定；docs/model-evaluation-contract.md「AU log-loss 尺」）。

同 HKJC v4／v5 一樣嘅判法，但 AU 冇長歷史回放（賽前輸入重砌唔到，EXP-20261121-35），
所以用 2026-08-05 起乾淨 point-in-time 語料，校準 walk-forward；(a, α[, γ]) baseline 同候選**各自** fit，
每 7 個賽日重 fit 一次，只用之前賽日；頭 20 個賽日只做訓練，唔計分。

**v2（2026-11-23，EXP-20261123-01，預設）**
  校準：p = σ(a + α·(raw − 場均) + γ·logit(3/N))（N = 場內匹數；標籤係入頭三，所以用 3/N）
  判法（三樣都過 = PASS）：
    1. Δlog-loss（候選 − baseline，每匹）95% CI 上界 < 0（賽日 bootstrap 2,000）
    2. 護欄：場內 AUC Δ 95% CI 下界 > −0.0015，**而且** Gold、Good 點估計 > −1.0pp
    3. Δlog-loss 好過 95% 場內洗牌 null
**v1（2026-11-21）**：校準冇 γ；護欄 = Gold、Good 各自 95% CI 下界 > −1.0pp。`version="v1"` 重現舊判決；
  11-23 之前登記嘅 forward（PR1 shadow、馬齡／up-nil）照用 v1。
另報 Gold、Good（連 CI）、場內 AUC、capture@5、頭二選有中（唔係閘）。

驗證：v1 見 EXP-20261121-35；v2 見 EXP-20261123-01（舊 Gold／Good 護欄對同幅度雜訊只捉到 8/30，AUC 護欄 29/30；
剷維度捉到 7/18 → 11/18；baseline 絕對 log-loss 0.5693 → 0.5533）。

輸入同 `au_eval` dump 一樣：races = [{"date", "meeting", "race", "rows": [{"ability", "pos"}, ...]}]，
baseline 同候選要同一批場次、同一個次序。fit 類候選嘅 dump 本身要係 walk-forward 預測（同 v3 規矩）。

    python3 au_logloss_ruler.py BASE.json CAND.json [--null 200] [--v1]
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
AUC_GUARD = -0.0015  # v2：場內 AUC Δ 95% CI 下界門檻（EXP-20261123-01 用 AU 數據量）
CURRENT = "v2"
NULL_SHARE = 0.95


def eligible(races):
    """乾淨語料、有頭馬兼 ≥ 3 匹入三甲；按日期排。"""
    out = [r for r in races if str(r.get("date") or "") >= CLEAN_SINCE
           and sum(x["pos"] <= 3 for x in r["rows"]) >= 3 and any(x["pos"] == 1 for x in r["rows"])]
    return sorted(out, key=lambda r: (r["date"], r["meeting"], r["race"]))


def _xy(race, raws=None, version="v1"):
    """→ (X, y)。v1：X = raw − 場均（一欄）；v2：再加 logit(3/N) 一欄。"""
    r = np.array([x["ability"] for x in race["rows"]], float) if raws is None else raws
    y = np.array([int(x["pos"] <= 3) for x in race["rows"]])
    if version == "v1":
        return r - r.mean(), y
    n = len(r)
    return np.column_stack([r - r.mean(), np.full(n, np.log(3 / max(n - 3, 1e-9)))]), y


def _fit(X, Y):
    """Logistic（有截距）Newton；X 一維 = v1 (a, α)，二維 = v2 (a, α, γ)。"""
    A = np.column_stack([np.ones(len(X)), X])
    beta = np.zeros(A.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(A @ beta, -30, 30)))
        step = np.linalg.solve((A * (p * (1 - p))[:, None]).T @ A, A.T @ (Y - p))
        beta = beta + step
        if np.abs(step).max() < 1e-9:
            break
    return tuple(float(v) for v in beta)


def calibrations(races, version="v1"):
    """→ {賽日: (a, α[, γ])}，只用嗰日之前嘅賽日；warm-up 日冇（唔計分）。

    預設 v1：`au_trainer_residual_table`（live 表）用緊 (a, α)，唔好靜靜改佢。"""
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
            x, y = _xy(r, version=version)
            X.append(x)
            Y.append(y)
    return out


def _nll(race, ab, raws=None, version="v1"):
    x, y = _xy(race, raws, version)
    z = ab[0] + (x * ab[1] if x.ndim == 1 else x @ np.array(ab[1:]))
    p = np.clip(1 / (1 + np.exp(-np.clip(z, -30, 30))), 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()), len(y)


def _auc(race):
    """場內 AUC：入頭三嘅馬分數高過唔入頭三嘅機率（同分計半）。"""
    r = np.array([x["ability"] for x in race["rows"]], float)
    y = np.array([x["pos"] <= 3 for x in race["rows"]])
    d = r[y][:, None] - r[~y][None, :]
    return float(((d > 0) + 0.5 * (d == 0)).mean()) if d.size else 0.5


def _metrics(race):
    order = sorted(range(len(race["rows"])), key=lambda i: -race["rows"][i]["ability"])
    pos = {i: race["rows"][i]["pos"] for i in range(len(race["rows"]))}
    m = race_metrics(order, {i for i, p in pos.items() if p <= 3}, actual_pos=pos)
    return [float(m["gold"]), float(m["good_positional"]), float(m["top3_capture_at5"]), float(m["top2_any_hit"]), _auc(race)]


def evaluate(baseline, candidate, *, nnull=200, seed=0, version=CURRENT):
    """→ {"verdict": PASS|REJECT, "reason", 數字…}。baseline／candidate 係已經 `eligible` 過、同次序嘅場次。

    version="v2"（預設，2026-11-23）／"v1"（2026-11-21，重現舊判決同舊 forward）。"""
    if version not in ("v1", "v2", "v2.1"):
        raise ValueError(f"unknown ruler version {version!r}")
    if [(r["meeting"], r["race"]) for r in baseline] != [(r["meeting"], r["race"]) for r in candidate]:
        raise ValueError("baseline／candidate 場次唔一致")
    # v2.1（EXP-20261124-41，研究選項，未做預設）：校準同 v2 一樣；分別只係 null 同埋逐匹對齊檢查。
    requested = version
    fixed_null = version == "v2.1"
    if fixed_null:
        for b, c in zip(baseline, candidate):
            nb = [x.get("n", x.get("name")) for x in b["rows"]]
            nc = [x.get("n", x.get("name")) for x in c["rows"]]
            if nb != nc:
                raise ValueError(f"{b['meeting']} R{b['race']}：baseline／candidate 匹馬次序唔一致")
        version = "v2"
    cb, cc = calibrations(baseline, version), calibrations(candidate, version)
    rows = []
    for b, c in zip(baseline, candidate):
        if b["date"] not in cb:
            continue
        lb, n = _nll(b, cb[b["date"]], version=version)
        lc, _ = _nll(c, cc[c["date"]], version=version)
        rows.append((b, c, b["date"], lc - lb, n, np.array(_metrics(c)) - np.array(_metrics(b))))
    if not rows:
        return {"verdict": "REJECT", "reason": "no_scored_races", "races": 0, "version": version}
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
    # v2.1：冇郁到嘅場次，佢喺實際 Δ 入面仍然有「兩邊各自校準」嘅差；洗牌一堆 0 都係 0，所以佢喺 null 嘅貢獻
    # 同實際一模一樣 —— v2 漏咗呢份（直接 continue），令 null 同實際唔係同一把尺（Sol 覆核 2026-11-24）。
    unchanged = 0.0
    if fixed_null:
        for b, c, day, dlt, *_ in rows:
            if not np.array([y["ability"] - x["ability"] for x, y in zip(b["rows"], c["rows"])]).any():
                unchanged += dlt
    for _ in range(nnull):
        tot = unchanged
        for b, c, day, *_ in rows:
            delta = np.array([y["ability"] - x["ability"] for x, y in zip(b["rows"], c["rows"])])
            if not delta.any():
                continue
            raws = np.array([x["ability"] for x in b["rows"]]) + rng.permutation(delta)
            tot += _nll(b, cc[day], raws, version)[0] - _nll(b, cb[day], version=version)[0]
        null.append(tot / nn.sum())
    null = np.array(null)
    lo = np.percentile(bm, 2.5, axis=0) * 100
    hi = np.percentile(bm, 97.5, axis=0) * 100
    pt = M.mean(0) * 100
    if version == "v1":
        guard = ("gold_good_guardrail", bool(lo[0] > GUARDRAIL_PP and lo[1] > GUARDRAIL_PP))
    else:
        guard = ("auc_guardrail", bool(lo[4] / 100 > AUC_GUARD and pt[0] > GUARDRAIL_PP and pt[1] > GUARDRAIL_PP))
    checks = {"logloss_ci_upper_below_0": bool(np.percentile(bl, 97.5) < 0),
              guard[0]: guard[1],
              "beats_null": bool(len(null) and (null > d).mean() >= NULL_SHARE)}
    failed = [k for k, ok in checks.items() if not ok]
    return {"verdict": "REJECT" if failed else "PASS", "reason": failed[0] if failed else "logloss_supported_gain",
            "version": requested, "checks": checks, "races": len(rows), "days": len(days),
            "dlogloss": [d, float(np.percentile(bl, 2.5)), float(np.percentile(bl, 97.5))],
            "beats_null_share": float((null > d).mean()) if len(null) else None,
            "gold_pp": [float(pt[0]), float(lo[0])], "good_pp": [float(pt[1]), float(lo[1])],
            "auc_delta": [float(pt[4] / 100), float(lo[4] / 100), float(hi[4] / 100)],
            "capture5_pp": float(pt[2]), "top2_any_hit_pp": float(pt[3])}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    nnull = int(argv[argv.index("--null") + 1]) if "--null" in argv else 200
    version = "v1" if "--v1" in argv else CURRENT
    paths = [a for i, a in enumerate(argv) if not a.startswith("--") and (i == 0 or argv[i - 1] != "--null")]
    load = lambda p: eligible(json.loads(Path(p).read_text())["races"])  # noqa: E731
    print(json.dumps(evaluate(load(paths[0]), load(paths[1]), nnull=nnull, version=version), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
