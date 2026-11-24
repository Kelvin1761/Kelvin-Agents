#!/usr/bin/env python3
"""實驗前功效預估（系統升級第 3 項，2026-11-25；合約「功效預估」）。

問題：265 REJECT 入面好多係「訊號細到把尺根本量唔到」—— 例：EXP-20261122-32 1.4pp × 9% 覆蓋，
效應 ≈ 0.00005，把尺門檻 ±0.0003。呢啲唔使開 dump、唔使跑 A/B 都知結果。

做法（最理想情況 = 上限）：喺真語料砌一個同模型**完全無關**嘅二元訊號 S：
  * 覆蓋率 = `--coverage`（佔馬次）；
  * S 入面入頭三率比 S 外面高 `--gap-pp`（即係你預期嘅組別差，研究通常就係報呢個）；
  * 候選 = baseline ability + δ·1[S]，δ = (logit 差) / 校準斜率 α（每分 ability 嘅 log-odds）。
然後用**真把尺**（AU log-loss v2／HKJC 回放 v5.2）判 k 次（唔同隨機 S）。
真訊號一定同現有模型有重疊，所以真實功效 ≤ 呢度量到嘅。PASS 率低過 50% = 唔好開實驗（或者先搵更大覆蓋）。

    python3 power_precheck.py --platform au   BASE.json   --gap-pp 1.4 --coverage 0.09 [--seeds 5]
    python3 power_precheck.py --platform hkjc BASE.jsonl  --gap-pp 1.4 --coverage 0.09 [--window dev]
"""
from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve()
SKILLS = HERE.parents[2]
AU_SCRIPTS = SKILLS / "au_racing" / "au_wong_choi_auto" / "scripts"
HKJC_V5 = SKILLS / "hkjc_racing" / "hkjc_reflector" / "scripts" / "hkjc_replay_compare_v5.py"


def _logit(p):
    return math.log(p / (1 - p))


def inclusion_probs(rate: float, coverage: float, gap: float) -> tuple[float, float]:
    """揀 S：入頭三嘅馬以 q1、其他以 q0 機率入 S，令 P(S)=coverage、P(top3|S) − P(top3|¬S) = gap。"""
    lo, hi = 0.0, 1.0
    for _ in range(100):              # gap(q1) 單調遞增 → 二分
        q1 = (lo + hi) / 2
        q0 = (coverage - rate * q1) / (1 - rate)
        if q0 < 0:
            hi = q1
            continue
        if q0 > 1:
            lo = q1
            continue
        g = rate * q1 / coverage - rate * (1 - q1) / (1 - coverage)
        lo, hi = (q1, hi) if g < gap else (lo, q1)
    q1 = (lo + hi) / 2
    q0 = (coverage - rate * q1) / (1 - rate)
    if not (0 <= q0 <= 1 and 0 <= q1 <= 1):
        raise ValueError("呢個覆蓋率配唔到咁大嘅 gap")
    return q1, q0


def delta_ability(rate: float, coverage: float, gap: float, alpha: float) -> float:
    p_in = rate + gap * (1 - coverage)
    p_out = rate - gap * coverage
    return (_logit(p_in) - _logit(p_out)) / alpha


def inject(horses, placed, ab_key, q1, q0, delta, rng):
    """horses: 可改嘅 dict list；placed: bool list。→ 入 S 匹數。"""
    n = 0
    for h, y in zip(horses, placed):
        if rng.random() < (q1 if y else q0):
            h[ab_key] = h[ab_key] + delta
            n += 1
    return n


# ---------------------------------------------------------------- AU

def run_au(path, gap, coverage, seeds, nnull):
    sys.path.insert(0, str(AU_SCRIPTS))
    import au_logloss_ruler as R
    base = R.eligible(json.loads(Path(path).read_text(encoding="utf-8"))["races"])
    rows = [x for r in base for x in r["rows"]]
    rate = float(np.mean([x["pos"] <= 3 for x in rows]))
    X = np.concatenate([R._xy(r, version="v2")[0] for r in base])
    Y = np.concatenate([R._xy(r, version="v2")[1] for r in base])
    alpha = R._fit(X, Y)[1]
    delta = delta_ability(rate, coverage, gap, alpha)
    q1, q0 = inclusion_probs(rate, coverage, gap)
    out = []
    for s in range(seeds):
        rng = np.random.default_rng(1000 + s)
        cand = [dict(r, rows=[dict(x) for x in r["rows"]]) for r in base]
        for r in cand:
            inject(r["rows"], [x["pos"] <= 3 for x in r["rows"]], "ability", q1, q0, delta, rng)
        res = R.evaluate(base, cand, nnull=nnull, seed=s)
        out.append({"seed": s, "verdict": res["verdict"], "dlogloss": res["dlogloss"]})
    return {"rate_top3": rate, "alpha_per_point": alpha, "delta_points": delta, "runs": out}


# ---------------------------------------------------------------- HKJC

def run_hkjc(path, gap, coverage, seeds, nnull, window):
    lines = [json.loads(l) for l in open(path, encoding="utf-8")]
    races = [x for x in lines if "horses" in x]
    hs = [h for x in races for h in x["horses"] if h.get("pos")]
    rate = float(np.mean([h["pos"] <= 3 for h in hs]))
    # 校準斜率：場內 raw − 場均 對 入頭三（同 v5 一樣形狀，簡化：唔加 logit(3/N)，只攞斜率量級）
    X, Y = [], []
    for x in races:
        if not ("2019-09-01" <= x["date"] <= "2024-07-31"):   # 斜率只用 v5 dev 窗，唔掂 holdout（Sol 覆核）
            continue
        h2 = [h for h in x["horses"] if h.get("pos")]
        if len(h2) < 4:
            continue
        r = np.array([h["raw"] for h in h2])
        X.extend(r - r.mean())
        Y.extend(h["pos"] <= 3 for h in h2)
    alpha = _slope(np.array(X), np.array(Y, float))
    delta = delta_ability(rate, coverage, gap, alpha)
    q1, q0 = inclusion_probs(rate, coverage, gap)
    out = []
    with tempfile.TemporaryDirectory() as td:
        for s in range(seeds):
            rng = np.random.default_rng(2000 + s)
            cp = Path(td) / f"cand{s}.jsonl"
            with open(cp, "w", encoding="utf-8") as fh:
                for x in lines:
                    if "horses" in x:
                        x = dict(x, horses=[dict(h) for h in x["horses"]])
                        hh = [h for h in x["horses"] if h.get("pos")]
                        inject(hh, [h["pos"] <= 3 for h in hh], "raw", q1, q0, delta, rng)
                        # 候選揀馬 = 按新 raw 排（引擎揀馬近似；只影響 Gold／Good 護欄）
                        x["picks"] = [h["n"] for h in sorted(x["horses"], key=lambda h: -h["raw"])]
                    fh.write(json.dumps(x, ensure_ascii=False) + "\n")
            proc = subprocess.run([sys.executable, str(HKJC_V5), path, str(cp), "--window", window,
                                   "--null", str(nnull)], capture_output=True, encoding="utf-8", errors="replace")
            m = re.search(r"判決：(PASS|REJECT)", proc.stdout)
            d = re.search(r"Δlog-loss（每匹）([+-][\d.]+) \[([+-][\d.]+),([+-][\d.]+)\]", proc.stdout)
            out.append({"seed": s, "verdict": m.group(1) if m else "ERROR",
                        "dlogloss": [float(v) for v in d.groups()] if d else None,
                        "error": None if m else proc.stderr[-300:]})
    return {"rate_top3": rate, "alpha_per_point": alpha, "delta_points": delta, "runs": out}


def _slope(x, y):
    b = np.zeros(2)
    A = np.column_stack([np.ones(len(x)), x])
    for _ in range(50):
        p = 1 / (1 + np.exp(-np.clip(A @ b, -30, 30)))
        step = np.linalg.solve((A * (p * (1 - p))[:, None]).T @ A, A.T @ (y - p))
        b += step
        if np.abs(step).max() < 1e-10:
            break
    return float(b[1])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--platform", required=True, choices=["au", "hkjc"])
    ap.add_argument("base")
    ap.add_argument("--gap-pp", type=float, required=True, help="S 入面入頭三率高過 S 外面幾多 pp")
    ap.add_argument("--coverage", type=float, required=True, help="S 佔馬次比例（0–1）")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--null", type=int, default=50)
    ap.add_argument("--window", default="dev", help="HKJC：dev／holdout")
    a = ap.parse_args(argv)
    if not 0 < a.coverage < 1:
        ap.error("--coverage 要喺 0 同 1 之間（佔馬次比例）")
    if not 0 < a.gap_pp < 50:
        ap.error("--gap-pp 要係正數 pp（例 1.4）")
    if a.seeds < 3:
        ap.error("--seeds 最少 3（太少 PASS 率冇意思）")
    gap = a.gap_pp / 100
    if a.platform == "au":
        res = run_au(a.base, gap, a.coverage, a.seeds, a.null)
    else:
        res = run_hkjc(a.base, gap, a.coverage, a.seeds, a.null, a.window)
    passes = sum(r["verdict"] == "PASS" for r in res["runs"])
    res |= {"platform": a.platform, "gap_pp": a.gap_pp, "coverage": a.coverage,
            "pass_rate": passes / len(res["runs"]),
            "advice": ("值得做（理想訊號大多量到）" if passes / len(res["runs"]) >= 0.8 else
                       "邊緣：真訊號同模型有重疊，好可能量唔到" if passes / len(res["runs"]) >= 0.5 else
                       "預設唔開：連同模型完全無關嘅理想訊號都量唔到；要開就喺實驗記錄寫明理由"),
            "note": "合成訊號同模型無關、組別差精確 = 近似上限；真訊號同現有維度重疊，功效通常更低"}
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
