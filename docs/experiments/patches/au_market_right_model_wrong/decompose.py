#!/usr/bin/env python3
"""EXP-20261125-06 第二部分：市場比模型多嘅資訊，有幾多其實已經喺我哋嘅輸入入面？

    PYTHONDONTWRITEBYTECODE=1 python3 decompose.py BASE.json [--out out.json]

入頭三 log-loss 階梯（全部 walk-forward：4 個時間塊，用之前嘅塊訓練、下一塊測試；每匹獨立 logistic／GBM）：
  flat → 模型（ability 校準）→ 重擬全部現有輸入（同一批 leaf＋context，唔加新數據）→ 早更價 → SP
  * 模型 → 重擬     = 「睇到但用得唔好」（輸入已有，權重／形狀問題）
  * 重擬 → 早更價   = 「市場有、我哋輸入冇」
  * 早更 → SP       = 「朝早之後先到嘅資訊（late money）」
  * SP 剩低嘅       = 「連市場都估唔到」= 運氣／不可預測
重擬只係量度上限，**唔係候選模型**：佢喺 live 語料上擬合，唔可以直接搬入引擎（EXP-20261013-01；合約 dev/holdout）。
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression

import disagree as D


def design(rows, feats):
    cols, names = [], []
    for f in feats + D.ADJ + ["ability"]:
        cols.append([x["z"][f] for x in rows]); names.append("z:" + f)
    for f in feats:
        cols.append([float(x["features"].get(f) == 60.0) for x in rows]); names.append("neutral:" + f)
    cols.append([math.log1p(x.get("career_starts") or 0) for x in rows]); names.append("log_starts")
    cols.append([math.log1p(min(x.get("days_since_last") or 0, 400)) for x in rows]); names.append("log_days")
    cols.append([float(x.get("days_since_last") is None) for x in rows]); names.append("days_missing")
    cols.append([float(x.get("barrier") or 0) / max(x.get("field_n") or 1, 1) for x in rows]); names.append("barrier_rel")
    cols.append([float(x.get("barrier") or 0) for x in rows]); names.append("barrier")
    cols.append([float(x.get("field_n") or 0) for x in rows]); names.append("field_n")
    cols.append([x["dist_m"] if x["dist_m"] == x["dist_m"] else 1400.0 for x in rows]); names.append("dist_m")
    for c, vals in (("prep_stage", ["debut", "first_up", "second_up", "third_up", "established_prep"]),
                    ("going0", ["Soft", "Heavy", "Synthetic"]),
                    ("style", ["前置 / 前領", "前置 / 跟前", "守中 / 守中", "後上 / 後上", "未知 / 未知"])):
        for v in vals:
            cols.append([float(x[c] == v) for x in rows]); names.append(f"{c}={v}")
    return np.array(cols).T, names


def nll(p, y):
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("base"); ap.add_argument("--out"); ap.add_argument("--boot", type=int, default=1000)
    a = ap.parse_args()
    races = D.load(a.base)
    import au_early_prices
    au_early_prices.attach(races)
    feats = D.enrich(races)
    races = [r for r in races if all(x.get("early_p") for x in r["rows"])]
    dates = sorted({r["date"] for r in races})
    blocks = np.array_split(np.array(dates), 4)
    rows = [x for r in races for x in r["rows"]]
    X, names = design(rows, feats)
    y = np.array([x["placed"] for x in rows], float)
    dt = np.array([x["date"] for x in rows])
    # 每個 arm 都帶 log(場內匹數)：入頭三基準率由匹數決定，唔應該算做「重擬」嘅功勞
    fld = np.array([math.log(x.get("field_n") or 10) for x in rows])[:, None]
    ab = np.column_stack([np.array([x["z"]["ability"] for x in rows]), fld])
    le = np.column_stack([np.array([math.log(x["early_p"]) for x in rows]), fld])
    ls = np.column_stack([np.array([math.log(x["mkt_p"]) for x in rows]), fld])
    arms = {"model": ab, "refit_lin": X, "refit_gbm": X, "early": le, "sp": ls,
            "early+refit_lin": np.column_stack([le, X]), "early+model": np.column_stack([le, ab])}
    pred = {k: np.full(len(y), np.nan) for k in arms}
    pred["flat"] = np.full(len(y), np.nan)
    for i in range(1, 4):
        tr = np.isin(dt, np.concatenate(blocks[:i])); te = np.isin(dt, blocks[i])
        pred["flat"][te] = y[tr].mean()
        for k, M in arms.items():
            if k == "refit_gbm":
                clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                                     min_samples_leaf=200, l2_regularization=1.0, random_state=0)
            else:
                clf = LogisticRegression(C=0.5, max_iter=2000)
            mu, sd = M[tr].mean(0), M[tr].std(0) + 1e-9
            clf.fit((M[tr] - mu) / sd, y[tr]); pred[k][te] = clf.predict_proba((M[te] - mu) / sd)[:, 1]
    te = ~np.isnan(pred["flat"])
    L = {k: nll(p[te], y[te]) for k, p in pred.items()}
    res = {"races": len(races), "test_runners": int(te.sum()), "ll": {k: float(v.mean()) for k, v in L.items()}}
    # 賽日 bootstrap 差距 CI
    tdt = dt[te]; ud = sorted(set(tdt)); idx = np.array([ud.index(d) for d in tdt])
    rng = np.random.default_rng(6)
    Wd = rng.multinomial(len(ud), np.ones(len(ud)) / len(ud), size=a.boot)
    cnt = np.bincount(idx, minlength=len(ud))

    def ci(diff):
        s = np.bincount(idx, weights=diff, minlength=len(ud))
        bs = (Wd @ s) / (Wd @ cnt)
        return [float(diff.mean()), float(np.percentile(bs, 2.5)), float(np.percentile(bs, 97.5))]
    res["gaps"] = {
        "flat-model": ci(L["flat"] - L["model"]),
        "model-refit_lin (睇到但用得唔好)": ci(L["model"] - L["refit_lin"]),
        "model-refit_gbm": ci(L["model"] - L["refit_gbm"]),
        "refit_lin-early (市場有、輸入冇)": ci(L["refit_lin"] - L["early"]),
        "refit_gbm-early": ci(L["refit_gbm"] - L["early"]),
        "early-sp (late money)": ci(L["early"] - L["sp"]),
        "early-(early+refit_lin) (輸入對朝早價有冇額外)": ci(L["early"] - L["early+refit_lin"]),
        "early-(early+model)": ci(L["early"] - L["early+model"]),
    }
    tot = res["ll"]["model"] - res["ll"]["sp"]
    best = min(res["ll"]["refit_lin"], res["ll"]["refit_gbm"])
    res["share_of_model_to_sp_gap"] = {"inputs_misused": (res["ll"]["model"] - best) / tot,
                                       "market_has_not_in_inputs": (best - res["ll"]["early"]) / tot,
                                       "late_money": (res["ll"]["early"] - res["ll"]["sp"]) / tot}
    res["luck_floor"] = {"sp_ll": res["ll"]["sp"], "flat_ll": res["ll"]["flat"],
                         "share_of_flat_uncertainty_left_after_sp": res["ll"]["sp"] / res["ll"]["flat"]}
    # 市場揀中、模型揀唔中（A）／D 喺 OOS 嘅平均預測
    rk = np.array([(x["k"] <= 2 and x["m"] >= 4) for x in rows])
    for g, mask in (("D", rk & te), ("A", rk & te & (y == 1)), ("D_miss", rk & te & (y == 0))):
        res.setdefault("cohort_mean_pred", {})[g] = {k: float(np.nanmean(p[mask])) for k, p in pred.items()} | {"n": int(mask.sum()), "actual": float(y[mask].mean())}
    # 重擬（全期線性）最大嘅係數，睇「用得唔好」主要喺邊
    mu, sd = X.mean(0), X.std(0) + 1e-9
    full = LogisticRegression(C=0.5, max_iter=3000).fit((X - mu) / sd, y)
    co = sorted(zip(names, full.coef_[0]), key=lambda t: -abs(t[1]))
    res["refit_lin_top_coefs_fullperiod"] = [(n, round(float(c), 3)) for n, c in co[:25]]
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
