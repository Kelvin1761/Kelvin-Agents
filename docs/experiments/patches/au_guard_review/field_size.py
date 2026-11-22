"""(3) 校準加馬匹數：p = σ(a + α·(raw − 場均) + γ·logit(k/N))。
k = 3（尺嘅標籤係「入頭三」，所以 3/N 先係基準率）；另試 k = AU 派位數（≥8 匹 3 個、5–7 匹 2 個）做對照。
報 baseline 絕對 walk-forward log-loss（v1 vs 加 N）、γ，同舊候選喺兩把校準下嘅 Δlog-loss／判決（一致性檢查）。

    field_size.py abs                 baseline 絕對 log-loss
    field_size.py pairs [NNULL]       舊候選重判（v1 vs v1+N 兩個 k）
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from common import BASE, SCR, R, load  # noqa: E402

ORIG = {k: getattr(R, k) for k in ("_xy", "_fit", "_nll")}


def places(n):
    return 3 if n >= 8 else 2


def use(mode):
    """mode: v1（現行）、n3（logit(3/N)）、np（logit(派位數/N)）。直接換 ruler module 嘅三個函數，evaluate／calibrations 照用。"""
    if mode == "v1":
        for k, f in ORIG.items():
            setattr(R, k, f)
        return

    def _xy(race, raws=None):
        r = np.array([x["ability"] for x in race["rows"]], float) if raws is None else raws
        n = len(r)
        k = 3 if mode == "n3" else places(n)
        z = np.full(n, np.log(k / (n - k)))
        return np.column_stack([r - r.mean(), z]), np.array([int(x["pos"] <= 3) for x in race["rows"]])

    def _fit(X, Y):
        A = np.column_stack([np.ones(len(X)), X])
        beta = np.zeros(A.shape[1])
        for _ in range(50):
            p = 1 / (1 + np.exp(-np.clip(A @ beta, -30, 30)))
            step = np.linalg.solve((A * (p * (1 - p))[:, None]).T @ A, A.T @ (Y - p))
            beta += step
            if np.abs(step).max() < 1e-9:
                break
        return tuple(beta)

    def _nll(race, ab, raws=None):
        X, y = _xy(race, raws)
        z = ab[0] + X @ np.array(ab[1:])
        p = np.clip(1 / (1 + np.exp(-np.clip(z, -30, 30))), 1e-6, 1 - 1e-6)
        return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()), len(y)

    R._xy, R._fit, R._nll = _xy, _fit, _nll


def absolute(races):
    out = {}
    for mode in ("v1", "n3", "np"):
        use(mode)
        cal = R.calibrations(races)
        tot = n = 0
        for r in races:
            if r["date"] in cal:
                a, b = R._nll(r, cal[r["date"]])
                tot, n = tot + a, n + b
        last = cal[max(cal)]
        out[mode] = {"logloss": tot / n, "runners": n, "last_fit": [round(float(v), 4) for v in last]}
    use("v1")
    return out


PAIRS = {
    "F1": ("fq-scale/BASE.json", "fq-scale/F1.json"), "F2": ("fq-scale/BASE.json", "fq-scale/F2.json"),
    "G50": ("au-going-sim/BASE.json", "au-going-sim/G50.json"), "G25": ("au-going-sim/BASE.json", "au-going-sim/G25.json"),
    "31-S": ("EXP-20261101-31/arms/base.json", "EXP-20261101-31/arms/S.json"),
    "31-S0": ("EXP-20261101-31/arms/base.json", "EXP-20261101-31/arms/S0.json"),
    "33-SH": ("EXP-20261101-33/arms/base.json", "EXP-20261101-33/arms/SH.json"),
    "37-GW": ("EXP-20261101-37/arms/base.json", "EXP-20261101-37/arms/GW.json"),
    "37-GWX": ("EXP-20261101-37/arms/base.json", "EXP-20261101-37/arms/GWX.json"),
    "P": ("au-noise-20261113/BASE.json", "au-prior-odds-logloss/P.json"),
    "P1": ("au-noise-20261113/BASE.json", "au-prior-odds-logloss/P1.json"),
}

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "abs":
        for p in (BASE, SCR / "au-noise-20261113/BASE.json", SCR / "fq-scale/BASE.json"):
            print(p, json.dumps(absolute(load(p)), ensure_ascii=False), flush=True)
    else:
        nnull = int(sys.argv[2]) if len(sys.argv) > 2 else 100
        res = {}
        for name, (bp, cp) in PAIRS.items():
            base, cand = load(SCR / bp), load(SCR / cp)
            row = {}
            for mode in ("v1", "n3", "np"):
                use(mode)
                try:
                    v = R.evaluate(base, cand, nnull=nnull)
                except ValueError as e:
                    v = {"verdict": "ERR", "reason": str(e)}
                row[mode] = {k: v.get(k) for k in ("verdict", "reason", "dlogloss", "beats_null_share", "gold_pp", "good_pp")}
            use("v1")
            res[name] = row
            print(name, "｜".join(f"{m} {row[m]['verdict']} {row[m]['reason']} Δ "
                                  + ("{:+.5f} [{:+.5f},{:+.5f}]".format(*row[m]['dlogloss']) if row[m].get('dlogloss') else "-")
                                  + f" null {row[m].get('beats_null_share')}" for m in row), flush=True)
        print(json.dumps(res, ensure_ascii=False, default=float))
