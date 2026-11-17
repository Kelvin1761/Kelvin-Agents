"""Kelvin 2026-11-17 七個標籤構思 —— live 之上殘差（入頭三 − 之前季校準 p，base = dist_D1 = 現行 live）。

1 3 歲＋負磅 ≥133（馬齡只有現役馬：馬匹頁「出生地 / 馬齡」係 2026-11-13 嘅歲數，每年 8 月 1 日減一歲倒推）
2 升班輕磅（唔計上仗贏咗即升班）
3 初落班＋同程上過名
4 騎師同場揀馬：騎過呢匹 ≥3 次（之前），今場同場騎另一匹 → 被棄／被揀
5 同馬房同場 ≥2 匹：正選（騎師一年勝率最高）／次選
6 上仗由「下游」騎師（一年勝率低過 8%）贏，今仗潘頓（另：任何前五騎師）
7 轉場：谷草（跑馬地）／田草（沙田草地）／泥地 —— 上仗 → 今仗、初次
用法：python3 diag_kelvin7.py <dist_D1.jsonl>
"""
import gzip
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
import features as F  # noqa: E402

RAW = "/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/raw/horse"
SCRAPE = date(2026, 11, 13)
CLS = {"Class 1": 1, "Class 2": 2, "Class 3": 3, "Class 4": 4, "Class 5": 5}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def surf(venue_track):
    v = str(venue_track or "")
    if "全天候" in v or "泥" in v:
        return "泥地"
    if v.startswith("跑馬地"):
        return "谷草"
    if v.startswith("沙田"):
        return "田草"
    return None


def ages():
    out = {}
    for f in os.listdir(RAW):
        try:
            t = gzip.open(os.path.join(RAW, f), "rt", encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        m = re.search(r"出生地\s*/\s*馬齡\s*:\s*\S+\s*/\s*(\d+)", re.sub(r"<[^>]+>", " ", t))
        if m:
            out[f.split(".")[0].rsplit("_", 1)[-1]] = int(m.group(1))
    return out


def age_at(age_now, d):
    d = date.fromisoformat(d)
    n = sum(1 for y in range(d.year, SCRAPE.year + 1) if d < date(y, 8, 1) <= SCRAPE)
    return age_now - n


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()].assign(d=lambda x: x["Date"].astype(str).str[:10]).sort_values(["d", "RaceNo"])
    pages, _ = F.load()
    pidx = {c: {q["d"]: i for i, q in enumerate(rr)} for c, rr in pages.items()}
    AGE = ages()
    print("有馬齡嘅馬", len(AGE), flush=True)
    # 騎師一年勝率（as-of）
    jhist = defaultdict(list)
    jrate_cache = {}

    def jrate(j, d):
        k = (j, d)
        if k not in jrate_cache:
            cut = date.fromisoformat(d).replace(year=date.fromisoformat(d).year - 1).isoformat()
            v = [w for dd, w in jhist.get(j, []) if cut <= dd < d]
            jrate_cache[k] = (sum(v) / len(v)) if len(v) >= 40 else None
        return jrate_cache[k]

    top5_by_day = {}
    feats = {}
    for (d, rn), g in df.groupby(["d", "RaceNo"], sort=False):
        if d not in top5_by_day:
            rates = {j: jrate(j, d) for j in set(df.loc[df["d"] == d, "Jockey"])}
            # 前五：當日之前一年勝率最高（≥40 騎）
            allj = {j for j, v in jhist.items()}
            rr_ = sorted(((jrate(j, d) or 0, j) for j in allj), reverse=True)[:5]
            top5_by_day[d] = {j for _, j in rr_}
        rows = list(g.itertuples())
        tr_count = defaultdict(list)
        for r in rows:
            tr_count[r.Trainer].append(r)
        # 4：騎師同場揀馬
        jock_today = {r.Jockey: r.HorseID for r in rows}
        for r in rows:
            hid = r.HorseID
            i = pidx.get(hid, {}).get(d)
            past = pages[hid][:i] if i is not None else []
            f = {}
            cls = CLS.get(str(r.RaceClass))
            dist = r.Distance
            last = past[-1] if past else None
            # 1
            if hid in AGE:
                a = age_at(AGE[hid], d)
                f["1 3歲（現役馬）"] = a == 3
                f["1 3歲＋負磅 ≥130"] = a == 3 and (r.ActualWt or 0) >= 130
                f["1 3歲＋負磅 ≥133"] = a == 3 and (r.ActualWt or 0) >= 133
                f["1 4歲＋負磅 ≥133（對照）"] = a == 4 and (r.ActualWt or 0) >= 133
                f["1 5歲以上＋負磅 ≥133（對照）"] = a >= 5 and (r.ActualWt or 0) >= 133
            if last:
                lc, lp = F.num(last.get("class")), F.pos(last.get("pos"))
                up = cls is not None and lc is not None and cls < lc
                drop = cls is not None and lc is not None and cls > lc
                light = (r.ActualWt or 200) <= 118
                f["2 升班（全部）"] = up
                f["2 升班＋上仗唔係贏"] = up and lp != 1
                f["2 升班＋上仗唔係贏＋輕磅 ≤118"] = up and lp != 1 and light
                f["2 升班＋上仗贏（一場即升，對照）"] = up and lp == 1
                f["2 升班＋上仗贏＋輕磅 ≤118"] = up and lp == 1 and light
                first_here = drop and not any(F.num(q.get("class")) == cls for q in past)
                placed_dist = any(F.num(q.get("distance")) == dist and (F.pos(q.get("pos")) or 99) <= 3 for q in past)
                f["3 降班（全部）"] = drop
                f["3 初落呢班"] = first_here
                f["3 初落呢班＋同程上過名"] = first_here and placed_dist
                f["3 降班＋同程上過名（唔理初唔初）"] = drop and placed_dist
                # 6
                lj = str(last.get("jockey") or "").strip()
                won = lp == 1
                lr = jrate(lj, d)
                down = lr is not None and lr < 0.08
                f["6 上仗贏（全部）"] = won
                f["6 上仗下游騎師贏＋今仗潘頓"] = won and down and r.Jockey == "潘頓"
                f["6 上仗下游騎師贏＋今仗前五騎師"] = won and down and r.Jockey in top5_by_day[d] and lj not in top5_by_day[d]
                f["6 上仗下游騎師贏＋今仗唔係前五"] = won and down and r.Jockey not in top5_by_day[d]
                # 7
                s_now = "泥地" if r.Track == "AWT" or "全天候" in str(r.Course) else ("谷草" if r.Venue == "跑馬地" else "田草")
                s_last = surf(last.get("venue_track"))
                seen = {surf(q.get("venue_track")) for q in past}
                if s_last and s_last != s_now:
                    f[f"7 {s_last}→{s_now}"] = True
                if s_now not in seen:
                    f[f"7 初次{s_now}"] = True
                if s_last == s_now:
                    f["7 同場地（對照）"] = True
            # 4
            rides = [q for q in past if str(q.get("jockey") or "").strip()]
            for j, other in jock_today.items():
                if other == hid:
                    continue
                if sum(1 for q in rides if q["jockey"].strip() == j) >= 3:
                    f["4 被常騎騎師棄（佢今場騎另一匹）"] = True
            if r.Jockey and any(r.Jockey == j for j in jock_today) and past:
                # 今場騎師之前騎過同場另一匹 ≥3 次 → 呢匹係「被揀」
                for r2 in rows:
                    if r2.HorseID == hid:
                        continue
                    i2 = pidx.get(r2.HorseID, {}).get(d)
                    p2 = pages[r2.HorseID][:i2] if i2 is not None else []
                    if sum(1 for q in p2 if str(q.get("jockey") or "").strip() == r.Jockey) >= 3:
                        f["4 被揀（騎師放棄咗佢常騎嗰匹）"] = True
                        break
            # 4b（Kelvin「騎過三次以上今場突然唔騎」）：上仗佢騎＋騎過 ≥3 次，今場同場騎另一匹
            lastj = str(last.get("jockey") or "").strip() if last else ""
            if lastj and lastj != r.Jockey and lastj in jock_today and sum(1 for q in rides if q["jockey"].strip() == lastj) >= 3:
                f["4b 上仗騎師（騎過≥3次）今場同場騎另一匹 → 被棄"] = True
            for r2 in rows:
                if r2.HorseID == hid or r2.Jockey != r.Jockey:
                    pass
            # 今場騎師上仗騎同場另一匹（≥3 次）→ 呢匹「被揀」
            for r2 in rows:
                if r2.HorseID == hid:
                    continue
                i2 = pidx.get(r2.HorseID, {}).get(d)
                p2 = pages[r2.HorseID][:i2] if i2 is not None else []
                if p2 and str(p2[-1].get("jockey") or "").strip() == r.Jockey and                         sum(1 for q in p2 if str(q.get("jockey") or "").strip() == r.Jockey) >= 3:
                    f["4b 被揀（騎師棄咗佢上仗騎、騎過≥3次嗰匹）"] = True
                    break
            # 4c（Kelvin 2026-11-17 定義）：最近三場都係同一個騎師，今場轉人
            last3 = [str(q.get("jockey") or "").strip() for q in past[-3:]]
            if len(last3) == 3 and len(set(last3)) == 1 and last3[0] and last3[0] != r.Jockey:
                reg = last3[0]
                f["4c 近三場同一騎師、今場轉人（全部）"] = True
                if reg in jock_today:
                    f["4c …常騎騎師今場同場騎另一匹"] = True
                else:
                    f["4c …常騎騎師今場唔喺呢場"] = True
            if len(last3) == 3 and len(set(last3)) == 1 and last3[0] == r.Jockey:
                f["4c 近三場同一騎師、今場照騎（對照）"] = True
            # 5
            same = tr_count[r.Trainer]
            if len(same) >= 2:
                best = max(same, key=lambda x: (jrate(x.Jockey, d) or 0))
                f["5 同馬房同場 ≥2 匹（全部）"] = True
                f["5 正選（同馬房騎師勝率最高）"] = best.HorseID == hid
                f["5 次選"] = best.HorseID != hid
            else:
                f["5 單獨出（對照）"] = True
            feats[(d, int(rn), int(r.Rank))] = f
        for r in rows:
            jhist[r.Jockey].append((d, float(r.Rank == 1)))
    print("特徵完成", len(feats), flush=True)
    import pickle
    pickle.dump(feats, open(sys.argv[2], "wb")) if len(sys.argv) > 2 else None
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
    recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, b = calib[s]
        for h, z in zip(hs, rc):
            f = feats.get((x["date"], x["race"], h["pos"]))
            if f is not None:
                recs.append(dict(s=s, d=x["date"], y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + b * z))), f=f))
    print(f"馬次 {len(recs)}")
    names = sorted({k for r in recs for k in r["f"]})
    rng = np.random.default_rng(0)
    for k in names:
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            days = defaultdict(list)
            for r in recs:
                if lo <= r["s"] <= hi and r["f"].get(k):
                    days[r["d"]].append(r["y"] - r["p"])
            n = sum(len(v) for v in days.values())
            if n < 30:
                out.append(f"n={n}"); continue
            dk = list(days)
            mean = np.mean([e for v in days.values() for e in v])
            bt = [np.mean([e for j in rng.integers(0, len(dk), len(dk)) for e in days[dk[j]]]) for _ in range(400)]
            out.append(f"{100*mean:+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={n}")
        seas = " ".join(f"{100*np.mean(v):+.0f}" if len(v) >= 20 else "." for v in
                        ([r["y"] - r["p"] for r in recs if r["s"] == s and r["f"].get(k)] for s in sorted({r["s"] for r in recs})))
        print(f"{k}｜dev {out[0]}｜holdout {out[1]}｜逐季 {seas}", flush=True)


if __name__ == "__main__":
    main()
