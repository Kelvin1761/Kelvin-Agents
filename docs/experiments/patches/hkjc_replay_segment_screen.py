"""Kelvin 決定 5（泥地深挖）／7（直路 1000 深挖）：分段專屬訊號，模型（S 版）之上有冇剩餘。

預先登記（跑之前寫死；唔准睇完結果先加）：
  --seg awt       泥地賽事
    A1 awt_vs_turf  近 730 日泥地平均名次百分位 − 草地平均名次百分位（各 ≥1 仗，收縮 k=3 向 0；越大 = 泥地相對好）× −1
    A2 front_v      EXP-08 first_v（前段對標準）
    A3 going_front  今仗場地濕（濕快／濕慢）× 前置習慣（近 6 仗第一段走位百分位 ≤ 0.33）
    A4 draw_rel     (檔位 − 1)/(出賽數 − 1)
    A5 sire_awt     父系泥地入頭三率（as-of、收縮 k=20 向全體），只限冇泥地經驗嘅馬（其餘 = 缺失）
  --seg straight  沙田草地 1000 米
    S1 draw_rel     (檔位 − 1)/(出賽數 − 1)
    S2 front_v      first_v
    S3 straight_pct 近 730 日直路 1000 米平均名次百分位（≥1 仗）× −1
    S4 carried_rel  今仗負磅 − 全場平均
    S5 bodywt_rel   排位體重 − 全場平均
  方法  入頭三 ~ 模型場內排名百分位 ＋ 單一特徵（logistic 標準化）；按場 bootstrap 300；5 個特徵 Holm
  判法  dev Holm < 0.05 而且 holdout 同方向 CI 唔跨零 → 開排名候選；否則唔開
用法：python3 hkjc_replay_segment_screen.py <base.jsonl> <replay_index.pkl> <sect_features_v2.pkl> --seg awt|straight
"""
import datetime as dt
import json
import pickle
import sys
from collections import defaultdict

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

WIN = {"dev": ("2020-09-01", "2024-07-31"), "holdout": ("2024-09-01", "2026-07-31")}


def pct(pos, field):
    return (pos - 1) / max(field - 1, 1)


def main():
    seg = sys.argv[sys.argv.index("--seg") + 1]
    rows = sorted((json.loads(l) for l in open(sys.argv[1]) if '"horses"' in l), key=lambda x: (x["date"], x["race"]))
    idx = pickle.load(open(sys.argv[2], "rb"))
    F = pd.read_pickle(sys.argv[3]).set_index(["race", "code"])
    is_awt = lambda x: bool(x.get("awt"))
    is_str = lambda x: not x.get("awt") and "跑馬地" not in str(x.get("venue")) and int(x.get("distance") or 0) == 1000
    target = is_awt if seg == "awt" else is_str
    # 父系泥地 as-of（按日累積）
    sire_hist, all_hist, buf, cur = defaultdict(lambda: [0, 0]), [0, 0], [], None
    recs = []
    for x in rows:
        if x["date"] != cur:
            for s, p in buf:
                sire_hist[s][0] += p
                sire_hist[s][1] += 1
                all_hist[0] += p
                all_hist[1] += 1
            buf.clear()
            cur = x["date"]
        sec = idx["sect"].get((x["date"], x["race"])) or {}
        res = idx["results"].get((x["date"], x["race"])) or {}
        no2 = {str(h.get("horse_no")): h for h in sec.get("horses", [])}
        rr = {str(r.get("horse_no")): r for r in res.get("results", [])}
        ven = "HV" if "跑馬地" in x["venue"] else "ST"
        d0 = dt.date.fromisoformat(x["date"])
        field = len(x["horses"])
        n = len(x["picks"])
        rank = {hn: i / max(n - 1, 1) for i, hn in enumerate(x["picks"])}
        wts = [float(rr.get(str(h["n"]), {}).get("actual_wt") or "nan") for h in x["horses"]]
        bws = [float(rr.get(str(h["n"]), {}).get("horse_wt") or "nan") if str(rr.get(str(h["n"]), {}).get("horse_wt") or "").isdigit() else np.nan for h in x["horses"]]
        mw, mb = np.nanmean(wts) if wts else np.nan, np.nanmean(bws) if bws else np.nan
        for h, w, bw in zip(x["horses"], wts, bws):
            sh = no2.get(str(h["n"])) or {}
            horse = idx["horses"].get(sh.get("horse_id")) or {}
            sire = (horse.get("profile") or {}).get("父系") or "?"
            if x.get("awt") and h["pos"]:
                buf.append((sire, int(h["pos"] <= 3)))
            if not target(x) or not h["pos"] or x["date"] < "2020-09-01":
                continue
            past = [r for r in horse.get("runs", []) if r["iso"] < x["date"] and (d0 - dt.date.fromisoformat(r["iso"])).days <= 730
                    and str(r.get("pos", "")).lstrip("0")[:1].isdigit()]
            def ppct(r):
                try:
                    return pct(int(str(r["pos"]).split()[0]), 12)
                except ValueError:
                    return None
            awt_p = [ppct(r) for r in past if "全天候" in r.get("venue_track", "")]
            turf_p = [ppct(r) for r in past if "全天候" not in r.get("venue_track", "")]
            awt_p, turf_p = [v for v in awt_p if v is not None], [v for v in turf_p if v is not None]
            fv = F["first_v"].get((f"{x['date']}|{ven}|{x['race']}", sh.get("code")), np.nan) if sh.get("code") else np.nan
            draw = rr.get(str(h["n"]), {}).get("draw")
            draw_rel = (int(draw) - 1) / max(field - 1, 1) if str(draw or "").isdigit() else np.nan
            rec = {"date": x["date"], "race": (x["meeting"], x["race"]), "n": h["n"], "rank": rank[h["n"]], "place": int(h["pos"] <= 3)}
            if seg == "awt":
                diff = (np.mean(awt_p) - np.mean(turf_p)) * len(awt_p) / (len(awt_p) + 3) if awt_p and turf_p else np.nan
                going = str(sec.get("going") or res.get("going") or "")
                rec.update({"A1_awt_vs_turf": -diff if not np.isnan(diff) else np.nan, "A2_front_v": fv,
                            "A4_draw_rel": draw_rel})
                # A3：前置習慣 = 分段頁近 6 仗第一段走位百分位平均 ≤ 0.33
                hist_pos = HABIT.get(sh.get("horse_id"), [])
                prior = [p for d, p in hist_pos if d < x["date"]][-6:]
                front = float(np.mean(prior) <= 0.33) if len(prior) >= 2 else np.nan
                wet = float("濕" in going)
                rec["A3_going_front"] = wet * front if not np.isnan(front) else np.nan
                sh_ = sire_hist[sire]
                base = all_hist[0] / all_hist[1] if all_hist[1] else 0.25
                rec["A5_sire_awt"] = (sh_[0] + 20 * base) / (sh_[1] + 20) if not awt_p else np.nan
            else:
                sp = [ppct(r) for r in past if r.get("venue_track", "").startswith("沙田草地") and str(r.get("distance")) == "1000"]
                sp = [v for v in sp if v is not None]
                rec.update({"S1_draw_rel": draw_rel, "S2_front_v": fv, "S3_straight_pct": -np.mean(sp) if sp else np.nan,
                            "S4_carried_rel": w - mw if not np.isnan(w) else np.nan, "S5_bodywt_rel": bw - mb if not np.isnan(bw) else np.nan})
            recs.append(rec)
    feats = [k for k in recs[0] if k[:2] in ("A1", "A2", "A3", "A4", "A5", "S1", "S2", "S3", "S4", "S5")]
    if "--dump" in sys.argv:
        pd.DataFrame(recs).to_pickle(sys.argv[sys.argv.index("--dump") + 1])
    print(f"{seg}：{len(recs)} 匹次")
    for wname, (lo, hi) in WIN.items():
        R = [r for r in recs if lo <= r["date"] <= hi]
        races = sorted({r["race"] for r in R})
        ri = defaultdict(list)
        for i, r in enumerate(R):
            ri[r["race"]].append(i)
        y = np.array([r["place"] for r in R])
        out = []
        for f in feats:
            v = np.array([r[f] for r in R], dtype=float)
            ok = ~np.isnan(v)
            if ok.sum() < 50 or np.nanstd(v) == 0:
                out.append((f, np.nan, np.nan, np.nan, 1.0, int(ok.sum())))
                continue
            X = np.c_[np.array([r["rank"] for r in R]), v][ok]
            Xs = (X - X.mean(0)) / (X.std(0) + 1e-9)
            yy = y[ok]
            pm = np.cumsum(ok) - 1
            fit = lambda ii: LogisticRegression(C=1e6, max_iter=3000).fit(Xs[ii], yy[ii]).coef_[0][1]
            c = fit(np.arange(len(yy)))
            rng = np.random.default_rng(0)
            bs = []
            for _ in range(300):
                ii = np.concatenate([ri[races[k]] for k in rng.integers(0, len(races), len(races))])
                ii = pm[ii[ok[ii]]]
                bs.append(fit(ii))
            bs = np.array(bs)
            p = max(2 * min((bs <= 0).mean(), (bs >= 0).mean()), 1 / 300)
            out.append((f, c, np.percentile(bs, 2.5), np.percentile(bs, 97.5), p, int(ok.sum())))
        order = sorted(range(len(out)), key=lambda i: out[i][4])
        holm = {i: min(1.0, out[i][4] * (len(out) - k)) for k, i in enumerate(order)}
        print(f"== {wname}：{len(R)} 匹次、{len(races)} 場")
        for i, (f, c, lo_, hi_, p, nn) in enumerate(out):
            print(f"  {f:<16} n {nn:>5}｜每 SD {c:+.3f} [{lo_:+.3f},{hi_:+.3f}] Holm {holm[i]:.3f}")


HABIT = {}

if __name__ == "__main__":
    idx_ = pickle.load(open(sys.argv[2], "rb"))
    for (d, n), sec in idx_["sect"].items():
        fld = len(sec.get("horses", []))
        for h in sec.get("horses", []):
            p1 = (h.get("sections") or [{}])[0].get("pos")
            if h.get("horse_id") and p1:
                HABIT.setdefault(h["horse_id"], []).append((d, (p1 - 1) / max(fld - 1, 1)))
    for v in HABIT.values():
        v.sort()
    del idx_
    main()
