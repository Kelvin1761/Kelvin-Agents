"""EXP-20261115-09：Kelvin 8 條問題嘅診斷（只做診斷，冇候選）。
殘差 = 實際入頭三 − 模型機率；模型機率 = σ(a + α·(raw − 場均))，raw = 現行 live（S 版＋FT＋L400＋上仗賠率），(a, α) 用 dev fit。
每個 flag 報 n、殘差平均（pp）、按賽日 bootstrap 95% CI。只用 dev（2020/21–2023/24）。特徵全部只用日期早過今仗嘅賽事。
用法：python3 diag.py <market_A.jsonl>
"""
import gzip
import json
import re
import sys
from collections import defaultdict
from datetime import date

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def iso(dmy):
    d, m, y = dmy.split("/")
    return f"{y}-{m}-{d}"


def num(x):
    try:
        return float(str(x).strip())
    except ValueError:
        return None


def horse_runs():
    runs = defaultdict(list)
    prof = {}
    for line in gzip.open("/Volumes/Kelvin Hardisk 1/WongChoi-Archive/hkjc-history/parsed/horses.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        code = r["horse_id"].rsplit("_", 1)[-1]
        prof[code] = r.get("profile") or {}
        for x in r.get("runs") or []:
            try:
                x["d"] = iso(x["date"])
            except Exception:
                continue
            runs[code].append(x)
    for v in runs.values():
        v.sort(key=lambda x: x["d"])
    return runs, prof


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    key = defaultdict(list)
    for r in df.itertuples():
        key[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append((r.HorseID, float(r.Odds) if r.Odds == r.Odds else None, r.Jockey, r.Trainer))
    runs, prof = horse_runs()
    # 騎師一年入位率（as-of 粗略：用全 dev 前一季）
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x and 2020 <= season(x["date"]) <= 2023]
    X, Y = [], []
    for x in rows:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs])
        X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
    m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
    a, b = m.intercept_[0], m.coef_[0][0]
    flags = defaultdict(list)     # name -> [(date, resid, odds)]
    for x in rows:
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        for h, z in zip(hs, rc):
            k = key.get((x["date"], x["race"], h["pos"]))
            if not k or len(k) != 1:
                continue
            hid, odds, jockey, trainer = k[0]
            res = float(h["pos"] <= 3) - 1 / (1 + np.exp(-(a + b * z)))
            past = [q for q in runs.get(hid, []) if q["d"] < x["date"]]
            today = next((q for q in runs.get(hid, []) if q["d"] == x["date"]), None)
            def add(name):
                flags[name].append((x["date"], res, odds))
            add("全部")
            if not past:
                imp = str(prof.get(hid, {}).get("進口類別", ""))
                add("初出／首次在港出賽")
                add(f"首戰｜進口類別={imp or '未知'}")
                continue
            last = past[-1]
            # Q1 換騎
            if today:
                tj = today.get("jockey"); lj = last.get("jockey")
                if tj and lj and tj != lj:
                    prev_rides = [q for q in past if q.get("jockey") == tj]
                    placed = [q for q in prev_rides if str(q.get("pos", "")).strip().lstrip("0").isdigit() and int(str(q["pos"]).strip()) <= 3]
                    add("換騎｜全部")
                    add("換騎｜新騎師從未騎過")
                    if prev_rides:
                        flags["換騎｜新騎師從未騎過"].pop()
                        add("換騎｜回到騎過嘅騎師")
                        if placed:
                            add("換騎｜回到同佢跑入過位嘅騎師")
                else:
                    add("同一騎師")
                # Q7 配備
                tg, lg = str(today.get("gear") or ""), str(last.get("gear") or "")
                items = [g for g in tg.split("/") if g]
                if any(re.search(r"1$", g) for g in items):
                    add("配備｜有首次配備")
                if any(g.startswith("B") and g.endswith("1") for g in items):
                    add("配備｜首次眼罩 B1")
                if any(g.startswith("TT") and g.endswith("1") for g in items):
                    add("配備｜首次脷帶 TT1")
                if any(g.endswith("-") for g in items):
                    add("配備｜除去配備")
                if tg == lg:
                    add("配備｜冇變")
                # Q6 練馬師出擊
                tr, lr = num(today.get("rating")), num(last.get("rating"))
                tc, lc = num(today.get("class")), num(last.get("class"))
                if tc and lc and tc > lc:
                    add("降班")
                if tc and lc and tc < lc:
                    add("升班")
                if tr is not None and lr is not None and tr <= lr - 3:
                    add("評分跌 ≥3")
                gap = (date.fromisoformat(x["date"]) - date.fromisoformat(last["d"])).days
                if gap >= 90:
                    add("休息 ≥90 日復出")
                if today.get("trainer") and last.get("trainer") and today["trainer"] != last["trainer"]:
                    add("轉馬房")
                if tc and lc and tc > lc and tj and tj != lj:
                    add("降班＋換騎")
                # Q4 上仗熱門
                lo = num(last.get("win_odds"))
                if lo is not None and lo <= 5:
                    add("上仗熱門 ≤5｜全部")
                    if tc and lc and tc < lc:
                        add("上仗熱門 ≤5｜今仗升班")
                    ld, td = num(last.get("distance")), num(today.get("distance"))
                    if ld and td and abs(td - ld) >= 200:
                        add("上仗熱門 ≤5｜今仗轉路程 ≥200m")
                    lv, tv = str(last.get("venue_track", ""))[:2], str(today.get("venue_track", ""))[:2]
                    if lv and tv and lv != tv:
                        add("上仗熱門 ≤5｜轉場地")
                    lp = str(last.get("pos", "")).strip()
                    if lp.isdigit() and int(lp) >= 6:
                        add("上仗熱門 ≤5｜上仗跑第 6 或之後")
                    if gap >= 90:
                        add("上仗熱門 ≤5｜休息 ≥90 日")
                if lo is not None and lo >= 20:
                    add("上仗冷門 ≥20｜全部")
                    lp = str(last.get("pos", "")).strip()
                    if lp.isdigit() and int(lp) <= 3:
                        add("上仗冷門 ≥20｜但上仗入位")
    rng = np.random.default_rng(0)
    print(f"{'flag':30s} {'n':>6s} {'殘差pp':>7s}  95% CI            今仗賠率中位")
    for name, v in flags.items():
        if len(v) < 150:
            continue
        days = defaultdict(list)
        for d, res, _ in v:
            days[d].append(res)
        dk = list(days)
        bs = []
        for _ in range(1000):
            s = [days[dk[i]] for i in rng.integers(0, len(dk), len(dk))]
            flat = [q for a_ in s for q in a_]
            bs.append(np.mean(flat))
        mean = np.mean([q[1] for q in v]) * 100
        odds = [q[2] for q in v if q[2]]
        print(f"{name:30s} {len(v):6d} {mean:+7.2f}  [{np.percentile(bs, 2.5) * 100:+.2f},{np.percentile(bs, 97.5) * 100:+.2f}]   {np.median(odds) if odds else float('nan'):.1f}")


if __name__ == "__main__":
    main()
