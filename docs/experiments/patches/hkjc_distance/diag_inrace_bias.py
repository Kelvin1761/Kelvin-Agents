"""Kelvin 2026-11-17「情境」功能嘅幅度同「即場」有冇用。

(1) 校準斜率：每季 logistic(入頭三 ~ raw 置中) 嘅 b（原始分 → logit）；顯示尺 1 原始分 = DISPLAY_SLOPE 顯示分。
(2) 偏差日幅度：每個賽日、每種跑法（實際走位，run_style 標準）／檔位段（1–4／5–9／10+），殘差（入頭三 − p）嘅分佈；
    「強偏差日」= 90 百分位。
(3) 即場持續性：同一賽日，頭一半場次某跑法／檔位段殘差 > +5pp（偏差日），下半場同一類殘差係幾多？
    下半場用「慣性跑法」（賽前知）分類，因為即場用嘅係賽前標籤。
用法：python3 diag_inrace_bias.py <dist_D1.jsonl>
"""
import json
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_wong_choi_auto/scripts")
from hkjc_racing_engine.run_style import classify, fraction  # noqa: E402


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10]).sort_values(["d", "RaceNo"])
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    hist = defaultdict(list)
    info = {}
    for r in df.itertuples():
        h = hist[r.HorseID]
        habit = classify(sum(h[-6:]) / len(h[-6:])) if len(h) >= 2 else None
        rp = str(r.RunningPos or "").split()
        actual = classify(fraction(rp[0], r.F)) if rp and rp[0].isdigit() else None
        try:
            dr = int(float(r.Draw))
        except (TypeError, ValueError):
            dr = 0
        band = ("內" if dr <= 4 else "中" if dr <= 9 else "外") if dr > 0 else None
        info[(r.d, int(r.RaceNo), int(r.Rank))] = (habit, actual, band)
        if rp and rp[0].isdigit():
            h.append(int(rp[0]) / r.F)
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    from sklearn.linear_model import LogisticRegression
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in ([x for t in by if t < s for x in by[t]] or by[s]):
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        calib[s] = (m.intercept_[0], m.coef_[0][0])
    print("校準斜率 b（logit／原始分）", {s: round(float(v[1]), 3) for s, v in calib.items()})
    day = defaultdict(list)
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, b = calib[s]
        for h, z in zip(hs, rc):
            i = info.get((x["date"], x["race"], h["pos"]))
            if i:
                day[(x["date"], x["venue"])].append((x["race"], int(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z))), *i))
    # (2) 偏差日幅度（實際走位、檔位段；每日每類 ≥ 8 馬次）
    for idx, name, cats in ((3, "實際走位", ("放頭", "守中", "後上")), (4, "檔位段", ("內", "中", "外"))):
        vals = {c: [] for c in cats}
        for recs in day.values():
            for c in cats:
                e = [rr[1] for rr in recs if rr[idx] == c]
                if len(e) >= 8:
                    vals[c].append(np.mean(e))
        print(name, {c: f"P10 {100*np.percentile(v,10):+.1f} P50 {100*np.percentile(v,50):+.1f} P90 {100*np.percentile(v,90):+.1f}" for c, v in vals.items()})
    # (3) 持續性：頭一半場次（實際）殘差 > +5pp → 下半場（慣性跑法／檔位段）殘差
    for idx_first, idx_later, name, cats in ((3, 2, "跑法", ("放頭", "守中", "後上")), (4, 4, "檔位段", ("內", "中", "外"))):
        for c in cats:
            hot, cold, other = [], [], []
            for recs in day.values():
                races = sorted({rr[0] for rr in recs})
                if len(races) < 6:
                    continue
                half = races[len(races) // 2 - 1]
                first = [rr[1] for rr in recs if rr[0] <= half and rr[idx_first] == c]
                later = [rr[1] for rr in recs if rr[0] > half and rr[idx_later] == c]
                if len(first) < 6 or not later:
                    continue
                m1 = np.mean(first)
                (hot if m1 > 0.05 else cold if m1 < -0.05 else other).extend(later)
            fmt = lambda v: f"{100*np.mean(v):+.1f}（n {len(v)}）" if v else "-"
            print(f"持續性 {name} {c}：頭半場偏好（>+5pp）→ 下半場 {fmt(hot)}｜頭半場偏差（<−5pp）→ {fmt(cold)}｜冇偏差 → {fmt(other)}")


if __name__ == "__main__":
    main()
