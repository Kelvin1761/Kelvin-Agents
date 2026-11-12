"""審計第 3–9 項標籤嘅訊號檢查（只讀，唔改模型）：每個標籤喺現行模型之上有冇剩餘訊號。

用法：PYTHONDONTWRITEBYTECODE=1 python3 docs/experiments/patches/hkjc_label_signal_check2.py <base.jsonl>
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from hkjc_label_signal_check import boot_diff, coef, table  # noqa: E402


def cat(text, pairs, default="其他"):
    t = str(text or "")
    return next((lab for key, lab in pairs if key in t), default if t else "冇")


def main():
    import wongchoi_paths
    root = Path(wongchoi_paths.HK_RACING)
    rows = []
    for line in open(sys.argv[1], encoding="utf-8"):
        r = json.loads(line)
        if "error" in r or not r.get("horses"):
            continue
        logic = json.loads((root / r["meeting"] / f"Race_{r['race']}_Logic.json").read_text(encoding="utf-8"))
        dist = re.sub(r"\D", "", str((logic.get("race_analysis") or {}).get("distance") or ""))
        hv = "HappyValley" in r["meeting"]
        for h in r["horses"]:
            if h["pos"] is None:
                continue
            d = ((logic.get("horses") or {}).get(str(h["n"])) or {}).get("_data") or {}
            f = h["f"]
            fin = [int(x) for x in re.findall(r"\b\d+\b", str(((logic.get("horses") or {}).get(str(h["n"])) or {}).get("last_6_finishes") or ""))[:6]]
            best = str(d.get("best_distance") or "")
            rows.append({
                "race": f"{r['meeting']}|{r['race']}", "place": float(h["pos"] <= 3), "raw": h["raw"], "hv": hv, "debut": h["debut"],
                "fl_label": cat(d.get("formline_strength"), (("極強", "極強"), ("強", "強"), ("中", "中"), ("弱", "弱"))),
                "fl_score": f.get("formline_strength_score"),
                "draw": f.get("draw_score"), "rshape": f.get("race_shape_context_score"),
                "consistency": f.get("consistency_score"), "form": f.get("form_score"),
                "fin_sd": float(np.std(fin)) if len(fin) >= 3 else np.nan,
                "fin_mean": float(np.mean(fin)) if len(fin) >= 3 else np.nan,
                "dist_fit": (1.5 if (best.startswith(f"{dist}m") or f"今仗 {dist}m =" in best) else -1.5 if "未跑過" in best else 0.0) if best and dist else np.nan,
                "dist_fit_unplaced": bool(re.search(rf"今仗 {dist}m = \d+場 \(0-0-0\)", best)) if dist else False,
                "pi_trend": cat(d.get("position_pi"), (("上升", "上升"), ("衰退", "衰退"), ("下降", "衰退"), ("穩定", "穩定"), ("波動", "波動"))),
                "style": str(d.get("style_breakdown_6") or ""),
                "l400_trend": cat(d.get("l400_trend"), (("上升", "上升"), ("衰退", "衰退"), ("穩定", "穩定"), ("波動", "波動"))),
                "jockey": f.get("jockey_score"), "trainer": f.get("trainer_score"),
            })
    df = pd.DataFrame(rows)
    g = df.groupby("race")
    df["zraw"] = (df.raw - g.raw.transform("mean")) / g.raw.transform("std").replace(0, np.nan)
    df = df.dropna(subset=["zraw"]).reset_index(drop=True)
    df["exp"] = LogisticRegression(max_iter=3000, C=1e6).fit(df[["zraw"]], df.place).predict_proba(df[["zraw"]])[:, 1]

    def auc(col, s):
        v = [roc_auc_score(x.place, x[col]) for _r, x in s.dropna(subset=[col]).groupby("race") if 0 < x.place.sum() < len(x) and x[col].nunique() > 1]
        return np.mean(v), len(v)
    print(f"{df.race.nunique()} 場 / {len(df)} 匹")

    print("\n== 3. 賽績線強度（超強／極強）==")
    table(df, "fl_label", "標籤：上名 vs 模型預期")
    p, lo, hi = coef(df, "fl_score")
    print(f"  formline 分模型之上每分 {p:+.4f} [{lo:+.4f},{hi:+.4f}]；場內 AUC {auc('fl_score', df)[0]:.4f}")

    print("\n== 4. 跑馬地檔位與走位（檔位＋谷草表現）==")
    s = df[df.hv & ~df.debut].copy()
    s["surface_term"] = s.rshape - s.draw
    for c in ("draw", "surface_term", "rshape"):
        p, lo, hi = coef(s, c)
        print(f"  {c:<12} 場內 AUC {auc(c, s)[0]:.4f}；模型之上每分 {p:+.4f} [{lo:+.4f},{hi:+.4f}]")

    print("\n== 5. 穩定性分 ==")
    s = df[~df.debut]
    print(f"  corr(穩定性分, 近績分) = {s[['consistency','form']].corr().iloc[0,1]:+.2f}；corr(穩定性分, 名次平均) = {s[['consistency','fin_mean']].corr().iloc[0,1]:+.2f}；corr(穩定性分, 名次 SD) = {s[['consistency','fin_sd']].corr().iloc[0,1]:+.2f}")
    for c in ("consistency", "form"):
        print(f"  {c:<12} 場內 AUC {auc(c, s)[0]:.4f}")
    s2 = s.dropna(subset=["fin_sd"]).copy()
    s2["neg_sd"] = -s2.fin_sd
    print(f"  真穩定（−名次 SD）場內 AUC {auc('neg_sd', s2)[0]:.4f}")
    p, lo, hi = coef(s2, "neg_sd")
    print(f"  真穩定模型之上每單位 {p:+.4f} [{lo:+.4f},{hi:+.4f}]")
    p, lo, hi = coef(s2.assign(fm=-s2.fin_mean), "fm")
    print(f"  名次平均（−）模型之上 {p:+.4f} [{lo:+.4f},{hi:+.4f}]")

    print("\n== 6. 路程配合 ==")
    s = df.dropna(subset=["dist_fit"])
    s = s.assign(df_lab=s.dist_fit.map({1.5: "今程有往績 +1.5", -1.5: "未跑過 −1.5", 0.0: "其他 0"}))
    table(s, "df_lab", "標籤：上名 vs 模型預期")
    sub = s[s.dist_fit == 1.5]
    p, lo, hi = boot_diff(sub, lambda x: x.dist_fit_unplaced, lambda x: ~x.dist_fit_unplaced)
    print(f"  今程有往績入面：今程從未上名 − 有上名 {p:+.2f}pp [{lo:+.2f},{hi:+.2f}]（n={int(sub.dist_fit_unplaced.sum())}／{len(sub)}）")

    print("\n== 7. 海外騎師／練馬師後備分 ==")
    print(f"  騎師分 85／70（海外後備值）: {int(df.jockey.isin([85.0, 70.0]).sum())} 匹；練馬師分 85／75／70: {int(df.trainer.isin([85.0, 75.0, 70.0]).sum())} 匹（共 {len(df)}）")

    print("\n== 8. 走位 PI 趨勢 ==")
    table(df, "pi_trend", "標籤：上名 vs 模型預期")
    df["front"] = df["style"].str.contains(r"[1-9]場前置")
    print(f"  上升軌入面前置馬比例 {df[df.pi_trend=='上升'].front.mean()*100:.0f}% vs 衰退 {df[df.pi_trend=='衰退'].front.mean()*100:.0f}%")

    print("\n== 9. L400 趨勢 ==")
    table(df, "l400_trend", "標籤：上名 vs 模型預期")
    p, lo, hi = boot_diff(df, lambda x: x.l400_trend == "上升", lambda x: x.l400_trend == "衰退")
    print(f"  上升 − 衰退 {p:+.2f}pp [{lo:+.2f},{hi:+.2f}]")


if __name__ == "__main__":
    main()
