"""研究計劃第 3 步（診斷性 refit）／第 11 步（整合 refit）：外層 MATRIX_WEIGHTS 喺回放語料重新 fit。

預先登記（跑之前寫死）：
  特徵   八個維度（stability, trainer_signal, sectional, race_shape, horse_health, trackwork, form_line, class_advantage）嘅 m 值
         —— distance_fit 中心項同初出馬權重（DEBUT_MATRIX_WEIGHTS）唔郁；初出馬 raw 保持原值
  模型   場內置中 logistic（目標 = 入頭三），L2 C = 1.0；係數按現行權重總和縮放；負係數截為 0 再縮放
  dev 判 walk-forward：測試季 2021/22、2022/23、2023/24，各用之前嘅季（由 2020/21 起）fit
  holdout 用 2020/21–2023/24 全部 fit 嘅權重，hkjc_replay_compare --window holdout（登記簿一次）
  計分   raw' = raw + Σ(w' − w)·m（非初出馬）；picks 重排
輸出：<outdir>/refit_wf.jsonl（dev walk-forward 拼合）、<outdir>/refit_full.jsonl（全 dev fit，畀 holdout 用）、weights.json
  S 版（Kelvin「段速最重要、唔用缺訊號嘅數據調低段速」）：--fix sectional → 段速權重固定喺現行，其餘維度 fit 後縮放到（總和 − 段速）
用法：python3 hkjc_replay_refit.py <base.jsonl> <outdir> [--fix sectional]
"""
import json
import sys
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO / ".agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts"))
from hkjc_racing_engine import scoring  # noqa: E402

DIMS = ("stability", "trainer_signal", "sectional", "race_shape", "horse_health", "trackwork", "form_line", "class_advantage")
W0 = np.array([scoring.MATRIX_WEIGHTS[d] for d in DIMS])


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


FIX = sys.argv[sys.argv.index("--fix") + 1].split(",") if "--fix" in sys.argv else []


def fit(rows):
    X, y = [], []
    for x in rows:
        hs = [h for h in x["horses"] if not h.get("debut") and h["pos"]]
        if len(hs) < 4:
            continue
        M = np.array([[h["m"].get(d, 60.0) for d in DIMS] for h in hs])
        X.append(M - M.mean(0))
        y += [int(h["pos"] <= 3) for h in hs]
    X = np.vstack(X)
    sd = X.std(0)
    sd[sd == 0] = 1
    coef = LogisticRegression(C=1.0, max_iter=5000).fit(X / sd, y).coef_[0] / sd
    coef = np.clip(coef, 0, None)
    fixed = np.array([d in FIX for d in DIMS])
    w = np.where(fixed, W0, 0.0)
    free = coef * ~fixed
    w[~fixed] = free[~fixed] / free[~fixed].sum() * (W0.sum() - W0[fixed].sum())
    return w


def apply(x, w):
    hs = []
    for h in x["horses"]:
        if h.get("debut"):
            hs.append(h)
            continue
        m = np.array([h["m"].get(d, 60.0) for d in DIMS])
        hs.append(dict(h, raw=h["raw"] + float((w - W0) @ m)))
    ns = np.array([h["n"] for h in hs])
    raw = np.array([h["raw"] for h in hs])
    return dict(x, picks=[int(v) for v in ns[np.lexsort((ns, -raw))]], horses=hs)


def main():
    rows = [json.loads(line) for line in open(sys.argv[1]) if '"horses"' in line]
    if FIX:
        print("固定：", FIX)
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    dev = [x for x in rows if "2020-09-01" <= x["date"] <= "2024-07-31"]
    weights = {}
    with open(out / "refit_wf.jsonl", "w") as fh:
        for ts in (2021, 2022, 2023):
            w = fit([x for x in dev if season(x["date"]) < ts])
            weights[f"wf_{ts}"] = dict(zip(DIMS, map(float, w)))
            for x in dev:
                if season(x["date"]) == ts:
                    fh.write(json.dumps(apply(x, w), ensure_ascii=False) + "\n")
    wfull = fit(dev)
    weights["full_dev"] = dict(zip(DIMS, map(float, wfull)))
    weights["current"] = dict(zip(DIMS, map(float, W0)))
    with open(out / "refit_full.jsonl", "w") as fh:
        for x in rows:
            fh.write(json.dumps(apply(x, wfull), ensure_ascii=False) + "\n")
    json.dump(weights, open(out / "weights.json", "w"), ensure_ascii=False, indent=1)
    print("現行 vs 全 dev fit：")
    for d, a, b in zip(DIMS, W0, wfull):
        print(f"  {d:<16} {a:.4f} → {b:.4f}")


if __name__ == "__main__":
    main()
