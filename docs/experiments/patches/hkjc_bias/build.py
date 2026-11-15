"""EXP-20261115-08：HKJC 跑法／檔位／場地偏差（Kelvin 2026-11-15「dig deeper 跑法，檔位，場地偏差」）。

全部特徵只用日期**嚴格早過**今仗嘅 HKJC 賽果（按日期順序處理，當日賽果喺當日之後先入表）。
跑道格 = (場地, 跑道欄位 A/A+3/B/B+2/C/C+3/AWT, 路程)。早段位置 = 走位第一個數 /(出賽數)。
三個預先登記候選（Holm 3）：
  D 檔位偏差：跑道格 × 檔位組（1–3／4–6／7–9／10+）之前季入位率 − 3/出賽數（n ≥ 30，否則 0）
  S 跑法偏差：跑道格 × 匹馬習慣跑法（近 3 仗早段位置平均：前 <0.34／中／後 ≥0.67）入位率殘差（n ≥ 30）
  E 上仗逆偏差：上仗當日同跑道格入位馬早段位置平均 m（全日偏差）；excuse = (上仗早段位置 − 0.5) × (0.5 − m) × 4
     （上仗跑後面而當日前領著數 → 正 = 今仗應該好啲）
冇值 → 場均。β 用 logistic（入頭三；raw 放大唔受罰）逐季 walk-forward，holdout 用全 dev。
用法：python3 build.py <base.jsonl> <outdir> [--diag]
"""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def rail(course):
    c = str(course)
    if "全天候" in c:
        return "AWT"
    m = re.search(r'"([ABC](?:\+\d)?)"', c)
    return m.group(1) if m else None


def dbucket(d):
    return "1-3" if d <= 3 else "4-6" if d <= 6 else "7-9" if d <= 9 else "10+"


def sbucket(e):
    return "F" if e < 0.34 else "B" if e >= 0.67 else "M"


def sectional_rails():
    """(日期, 場次) → 跑道欄位。賽果庫 2024-09–2026-05 嘅 Course 欄裝咗賽事名（25.5% 行冇欄位），所以用分段頁嘅 meta。"""
    import gzip
    out = {}
    for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/sectionals.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        c = "AWT" if r.get("surface") == "全天候" else r.get("course")
        if c:
            out[(r["date"], int(r["race_no"]))] = c
    return out


def features():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna() & df["Draw"].notna()].copy()
    df["d"] = df["Date"].astype(str).str[:10]
    sr = sectional_rails()
    df["rail"] = [sr.get((d, int(n))) or rail(c) for d, n, c in zip(df["d"], df["RaceNo"], df["Course"])]
    df = df[df["rail"].notna()]
    df["F"] = df.groupby(["d", "RaceNo"])["Rank"].transform("count")
    def early(s):
        m = re.match(r"\s*(\d+)", str(s))
        return int(m.group(1)) if m else None
    df["e1"] = df["RunningPos"].map(early)
    df["ef"] = (df["e1"] - 1) / (df["F"] - 1).clip(lower=1)
    df = df.sort_values(["d", "RaceNo"])
    draw_t = defaultdict(lambda: [0.0, 0.0, 0])      # cell -> [placed, expected, n]
    style_t = defaultdict(lambda: [0.0, 0.0, 0])
    horse_ef = defaultdict(list)                       # HorseID -> [(d, ef, excuse_inputs)]
    last_run = {}                                      # HorseID -> (d, ef, cellday)
    day_bias = {}                                      # (d, cell) -> mean ef of placegetters
    out = {}
    for d, g in df.groupby("d", sort=True):
        rows = list(g.itertuples())
        # 1) 先用之前日子嘅表計今日特徵
        for r in rows:
            cell = (r.Venue, r.rail, int(r.Distance) if r.Distance == r.Distance else 0)
            dk = cell + (dbucket(int(r.Draw)),)
            t = draw_t.get(dk)
            D = (t[0] - t[1]) / t[2] if t and t[2] >= 30 else None
            past = [x for x in horse_ef[r.HorseID] if x[0] < d and x[1] == x[1]][-3:]
            S = None
            if past:
                sk = cell + (sbucket(float(np.mean([x[1] for x in past]))),)
                t = style_t.get(sk)
                S = (t[0] - t[1]) / t[2] if t and t[2] >= 30 else None
            E = None
            lr = last_run.get(r.HorseID)
            if lr and lr[0] < d and lr[1] == lr[1] and lr[2] in day_bias:
                E = (lr[1] - 0.5) * (0.5 - day_bias[lr[2]]) * 4
            out[(d, int(r.RaceNo), int(r.Rank))] = out.get((d, int(r.RaceNo), int(r.Rank)), []) + [(D, S, E)]
        # 2) 今日賽果入表（之後日子先用到）
        placed_ef = defaultdict(list)
        for r in rows:
            cell = (r.Venue, r.rail, int(r.Distance) if r.Distance == r.Distance else 0)
            pl, ex = float(r.Rank <= 3), 3.0 / r.F
            t = draw_t[cell + (dbucket(int(r.Draw)),)]; t[0] += pl; t[1] += ex; t[2] += 1
            past = [x for x in horse_ef[r.HorseID] if x[1] == x[1]][-3:]
            if past:
                t = style_t[cell + (sbucket(float(np.mean([x[1] for x in past]))),)]; t[0] += pl; t[1] += ex; t[2] += 1
            if r.Rank <= 3 and r.ef == r.ef:
                placed_ef[(d,) + cell].append(r.ef)
        for k, v in placed_ef.items():
            if len(v) >= 6:          # 當日同跑道格最少兩場
                day_bias[k] = float(np.mean(v))
        for r in rows:
            cell = (r.Venue, r.rail, int(r.Distance) if r.Distance == r.Distance else 0)
            horse_ef[r.HorseID].append((d, r.ef))
            last_run[r.HorseID] = (d, r.ef, (d,) + cell)
    return out


IDX = {"D": 0, "S": 1, "E": 2}


def race_feats(x, feat, which):
    vals = []
    for h in x["horses"]:
        f = feat.get((x["date"], x["race"], h["pos"])) if h["pos"] else None
        f = f[0] if f and len(f) == 1 else None
        vals.append(None if f is None else f[IDX[which]])
    obs = [v for v in vals if v is not None]
    fill = float(np.mean(obs)) if obs else 0.0
    v = np.array([fill if a is None else a for a in vals], float)
    return (v - v.mean()).reshape(-1, 1)


def fit(races, feat, which):
    R, Z, Y = [], [], []
    for x in races:
        keep = [i for i, h in enumerate(x["horses"]) if h["pos"]]
        r = np.array([h["raw"] for h in x["horses"]], float)
        R.append((r - r.mean())[keep]); Z.append(race_feats(x, feat, which)[keep]); Y += [int(x["horses"][i]["pos"] <= 3) for i in keep]
    X = np.column_stack([np.concatenate(R) * 10, np.vstack(Z)])
    b = LogisticRegression(C=1e6, max_iter=5000).fit(X, Y).coef_[0]
    return b[1:] / (b[0] * 10)


def main():
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    out = Path(sys.argv[2])
    feat = features()
    for lo, hi in (("2019", "2024-08"), ("2024-09", "2026-08"), ("2026-08", "2099")):
        fs = [f[0] for k, f in feat.items() if len(f) == 1 and lo <= k[0] < hi]
        print("覆蓋", lo, {w: round(np.mean([x[IDX[w]] is not None for x in fs]) * 100, 1) for w in IDX})
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    for which in IDX:
        betas = {s: fit([x for t in by if t < min(s, 2024) for x in by[t]], feat, which) for s in sorted(by) if s > 2019}
        with open(out / f"bias_{which}.jsonl", "w") as f:
            for x in rows:
                b = betas.get(season(x["date"]))
                y = dict(x, arm=f"bias_{which}")
                if b is not None:
                    add = race_feats(x, feat, which) @ b
                    y["horses"] = [dict(h, raw=round(h["raw"] + float(a), 4)) for h, a in zip(x["horses"], add)]
                    y["picks"] = [h["n"] for h in sorted(y["horses"], key=lambda h: -h["raw"])]
                f.write(json.dumps(y, ensure_ascii=False) + "\n")
        print(which, {s: np.round(b, 2).tolist() for s, b in betas.items() if s <= 2024})


if __name__ == "__main__":
    main()
