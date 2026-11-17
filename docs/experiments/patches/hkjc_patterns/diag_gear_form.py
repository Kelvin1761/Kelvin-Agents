"""EXP-20261118-01：近績好嘅馬突然轉配備，下一仗成績（Kelvin 2026-11-18）。只做診斷。
殘差 = 實際入頭三（或贏）− 模型機率；模型機率 = σ(a + α·(raw − 場均))，raw = live 版（k7_K2），(a, α) 只用 dev fit。
近績好（預先登記）：香港近 3 仗至少 2 仗入頭三。配備比較「今仗」對「上仗」（HKJC 馬匹頁每仗配備欄）。
窗：dev 2020/21–2023/24 揀；holdout 2024/25–2025/26 只做確認。賽日 bootstrap 95% CI。
用法：python3 diag_gear_form.py <k7_K2.jsonl>
"""
import json
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/docs/experiments/patches/hkjc_patterns")
sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from diag import horse_runs, season  # noqa: E402

WIN = {"dev": (2020, 2023), "holdout": (2024, 2025)}


def pos_int(q):
    s = str(q.get("pos", "")).strip().lstrip("0")
    return int(s) if s.isdigit() else None


def gear_items(g):
    return [x.strip() for x in str(g or "").split("/") if x.strip() and x.strip() != "--"]   # "--" = 冇配備


def base_code(item):
    return item.rstrip("1-2")


def main():
    import hkjc_history_replay_pit as p
    df = p.load_all_rows_extended()
    df = df[df["Rank"].notna()]
    key = defaultdict(list)
    for r in df.itertuples():
        key[(str(r.Date)[:10], int(r.RaceNo), int(r.Rank))].append(r.HorseID)
    runs, _ = horse_runs()
    allrows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]

    def fit(rows, target):
        X, Y = [], []
        for x in rows:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs])
            X += list(r - r.mean()); Y += [target(h["pos"]) for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        return m.intercept_[0], m.coef_[0][0]

    dev = [x for x in allrows if WIN["dev"][0] <= season(x["date"]) <= WIN["dev"][1]]
    co3 = fit(dev, lambda p_: p_ <= 3)
    co1 = fit(dev, lambda p_: p_ == 1)
    rng = np.random.default_rng(0)
    for wname, (lo, hi) in WIN.items():
        rows = [x for x in allrows if lo <= season(x["date"]) <= hi]
        flags = defaultdict(list)   # name -> [(date, res3, res1, top3, win, pos)]
        for x in rows:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
            for h, z in zip(hs, rc):
                k = key.get((x["date"], x["race"], h["pos"]))
                if not k or len(k) != 1:
                    continue
                hid = k[0]
                past = [q for q in runs.get(hid, []) if q["d"] < x["date"]]
                today = next((q for q in runs.get(hid, []) if q["d"] == x["date"]), None)
                if not past or not today:
                    continue
                last3 = [pos_int(q) for q in past[-3:]]
                if len(last3) < 3 or None in last3:
                    continue
                good = sum(v <= 3 for v in last3) >= 2
                p3 = 1 / (1 + np.exp(-(co3[0] + co3[1] * z)))
                p1 = 1 / (1 + np.exp(-(co1[0] + co1[1] * z)))
                rec = (x["date"], float(h["pos"] <= 3) - p3, float(h["pos"] == 1) - p1, h["pos"] <= 3, h["pos"] == 1, h["pos"])
                tg, lg = gear_items(today.get("gear")), gear_items(last.get("gear")) if (last := past[-1]) else []
                first = [g for g in tg if g.endswith("1")]
                removed = [g for g in tg if g.endswith("-")]
                again = [g for g in tg if g.endswith("2")]
                changed = sorted(map(base_code, tg)) != sorted(map(base_code, lg)) or bool(first) or bool(removed) or bool(again)
                grp = "近績好" if good else "近績普通／差"
                def add(n):
                    flags[f"{grp}｜{n}"].append(rec)
                add("全部")
                add("配備有變" if changed else "配備冇變")
                if first:
                    add("首次配備（任何）")
                if removed:
                    add("除去配備（任何）")
                if again:
                    add("重新戴返配備（2）")
                if first and not removed:
                    add("只加首次配備")
                if removed and not first:
                    add("只除配備")
                for code, nm in (("B", "眼罩"), ("TT", "脷帶"), ("V", "開縫眼罩"), ("XB", "鼻箍"), ("CP", "羊毛面箍"), ("H", "頭罩"), ("SR", "防沙眼罩"), ("P", "防沙眼罩P"), ("E", "耳塞")):
                    if any(base_code(g) == code for g in first):
                        add(f"首次{nm} {code}1")
                    if any(base_code(g) == code for g in removed):
                        add(f"除去{nm} {code}-")
        print(f"\n=== {wname}（{len(rows)} 場）===")
        print(f"{'flag':34s} {'n':>6s} {'入位%':>6s} {'贏%':>5s} {'殘差入位pp':>11s}  95% CI           {'殘差贏pp':>9s}  95% CI")
        for name in sorted(flags):
            v = flags[name]
            if len(v) < 80:
                continue
            days = defaultdict(list)
            for rec in v:
                days[rec[0]].append(rec)
            dk = list(days)
            b3, b1 = [], []
            for _ in range(1000):
                s = [q for i in rng.integers(0, len(dk), len(dk)) for q in days[dk[i]]]
                b3.append(np.mean([q[1] for q in s])); b1.append(np.mean([q[2] for q in s]))
            m3 = np.mean([q[1] for q in v]) * 100; m1 = np.mean([q[2] for q in v]) * 100
            print(f"{name:34s} {len(v):6d} {np.mean([q[3] for q in v]) * 100:6.1f} {np.mean([q[4] for q in v]) * 100:5.1f} {m3:+11.2f}  [{np.percentile(b3, 2.5) * 100:+.2f},{np.percentile(b3, 97.5) * 100:+.2f}]   {m1:+8.2f}  [{np.percentile(b1, 2.5) * 100:+.2f},{np.percentile(b1, 97.5) * 100:+.2f}]")


if __name__ == "__main__":
    main()
