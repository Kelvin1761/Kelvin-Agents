#!/usr/bin/env python3
"""EXP-20261125-06 第三部分：候選組別 S 喺模型之外嘅入頭三殘差（描述性，喺 live 語料；唔係判決）。

殘差 = 實際入頭三 − 模型校準機率（logistic：ability 場內 z ＋ log 匹數，前半段擬合、全期套用）。
同時報市場殘差（實際 − SP 校準機率）：市場殘差 ≈ 0 而模型殘差 ≠ 0 = 「市場睇到、模型冇用」。
輸出嘅 gap/coverage 只係 power_precheck 嘅輸入估計；真正判決要預先登記、用之後嘅新賽日。
"""
from __future__ import annotations

import json
import math
import sys

import numpy as np

import disagree as D


def main():
    races = D.load(sys.argv[1])
    import au_early_prices
    au_early_prices.attach(races)
    D.enrich(races)
    rows = [x for r in races for x in r["rows"]]
    dates = sorted({x["date"] for x in rows}); half = dates[len(dates) // 2]
    y = np.array([x["placed"] for x in rows], float)
    fld = np.array([math.log(x.get("field_n") or 10) for x in rows])
    ab = np.array([x["z"]["ability"] for x in rows]); mk = np.array([math.log(x["mkt_p"]) for x in rows])
    h1 = np.array([x["date"] < half for x in rows])

    def calib(v):
        b, _ = D.logit_fit(np.column_stack([v, fld])[h1], y[h1])
        return 1 / (1 + np.exp(-(b[0] + b[1] * v + b[2] * fld)))
    pmod, pmkt = calib(ab), calib(mk)
    rm, rk = y - pmod, y - pmkt
    S = {
        "debut": lambda x: x["prep_stage"] == "debut",
        "thin_evidence(neutral_leaves>=8)": lambda x: x["neutral_leaves"] >= 8,
        "no_sectional(sectional==60)": lambda x: x["features"].get("sectional_score") == 60.0,
        "wide_big_field(bar/field>0.66,field>=10)": lambda x: (x.get("field_n") or 0) >= 10 and (x.get("barrier") or 0) / x["field_n"] > 0.66,
        "inside_big_field(bar<=3,field>=10)": lambda x: (x.get("field_n") or 0) >= 10 and 0 < (x.get("barrier") or 99) <= 3,
        "spell>=90d": lambda x: (x.get("days_since_last") or 0) >= 90,
        "quick_backup<=14d": lambda x: 0 < (x.get("days_since_last") or 99) <= 14,
        "top_jockey(z>=1)": lambda x: x["z"]["jockey_score"] >= 1,
        "top_trainer(z>=1)": lambda x: x["z"]["trainer_score"] >= 1,
        "trial_strong(z>=1)": lambda x: x["z"]["trial_score"] >= 1,
        "prep_strong(z>=1)": lambda x: x["z"]["preparation_score"] >= 1,
        "heavy_track": lambda x: x["going0"] == "Heavy",
        "style_unknown": lambda x: x["style"].startswith("未知"),
        "leader(前置/前領)": lambda x: x["style"] == "前置 / 前領",
        "backmarker(後上)": lambda x: x["style"].startswith("後上"),
    }
    ud = sorted(set(dates)); di = np.array([ud.index(x["date"]) for x in rows])
    rng = np.random.default_rng(7); W = rng.multinomial(len(ud), np.ones(len(ud)) / len(ud), size=500)
    out = {}
    for name, f in S.items():
        s = np.array([bool(f(x)) for x in rows])

        def gap(res, mask_s=s):
            a = np.bincount(di, weights=res * mask_s, minlength=len(ud)); na = np.bincount(di, weights=mask_s.astype(float), minlength=len(ud))
            b = np.bincount(di, weights=res * ~mask_s, minlength=len(ud)); nb = np.bincount(di, weights=(~mask_s).astype(float), minlength=len(ud))
            pt = a.sum() / na.sum() - b.sum() / nb.sum()
            bs = (W @ a) / (W @ na) - (W @ b) / (W @ nb)
            return [round(100 * pt, 2), round(100 * np.percentile(bs, 2.5), 2), round(100 * np.percentile(bs, 97.5), 2)]
        h2 = ~h1
        out[name] = {"coverage": round(float(s.mean()), 4), "raw_top3_gap_pp": round(100 * (y[s].mean() - y[~s].mean()), 2),
                     "model_resid_gap_pp": gap(rm), "market_resid_gap_pp": gap(rk),
                     "model_resid_gap_pp_h2": round(100 * (rm[s & h2].mean() - rm[~s & h2].mean()), 2),
                     "share_in_D": round(float(np.mean([f(x) for x in rows if x["k"] <= 2 and x["m"] >= 4])), 4)}
    print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
