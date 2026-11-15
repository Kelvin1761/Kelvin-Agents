"""Kelvin 2026-11-15「有冇其他 pattern 搵到冷門馬、值得加標籤」—— 上仗競賽事件報告 → 今仗殘差（診斷）。

事件報告（HKJC 賽果頁）只覆蓋 2023-10 起。上仗 = 同一匹馬喺賽果索引入面、日期早過今仗嘅最近一仗（事件報告賽後公開，冇洩漏）。
殘差 = 入頭三 − p，p = 回放 v3 raw 用之前季校準（同 EXP-18）。
報告每個類別：全部馬、我哋排第 5 名或以後（「我哋睇淡」）、賽後賠率 ≥10（只做評估，冇入模型）；揀選 2023/24–2024/25，確認 2025/26 起。
用法：python3 diag.py <v3 base.jsonl>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
CATS = {
    "出閘慢／失地": r"出閘笨拙|出閘緩慢|起步緩慢|失地",
    "受碰撞／擠迫": r"碰撞|受擠迫|被夾|互相觸碰|失去平衡",
    "走外疊冇遮擋": r"沒有遮擋|走外疊|三疊|四疊",
    "受阻／搵唔到位": r"未能望空|未能找到空位|找不到空位|受阻|勒避|被困|未能.{0,4}走位|須收慢",
    "搶口": r"搶口",
    "反應差／表現難接受": r"毫無反應|反應欠奉|表現令人失望|表現難以接受|乏力",
    "醫療（喘鳴／流鼻血／心律／跛）": r"喘鳴|流鼻血|鼻孔流血|心律|跛|呼吸|肺部有血|不良於行",
    "內閃／外閃": r"內閃|外閃",
}


def season(d):
    return int(d[:4]) if int(d[5:7]) >= 9 else int(d[:4]) - 1


def main():
    import hkjc_history_replay_build as b
    idx = b.load_index()
    res = idx["results"]
    runs = defaultdict(list)      # code -> [(date, race, sentence, odds, horse_no)]
    for (d, n), race in res.items():
        inc = b._incident_by_horse(race.get("incident_report") or "") if race.get("incident_report") else None
        for row in race.get("results", []):
            m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
            if not m or not b._started(row):
                continue
            try:
                odds = float(row.get("win_odds"))
            except (TypeError, ValueError):
                odds = None
            runs[m.group(1)].append((d, n, None if inc is None else inc.get(m.group(1), ""), odds, str(row.get("horse_no"))))
    for v in runs.values():
        v.sort()
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, _, hn in v}
    odds_of = {(d, n, hn): o for c, v in runs.items() for d, n, _, o, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    by = defaultdict(list)
    for x in rows:
        by[season(x["date"])].append(x)
    calib = {}
    for s in sorted(by):
        X, Y = [], []
        for x in [y for t in by if t < s for y in by[t]] or by[s]:
            hs = [h for h in x["horses"] if h["pos"]]
            r = np.array([h["raw"] for h in hs]); X += list(r - r.mean()); Y += [h["pos"] <= 3 for h in hs]
        m = LogisticRegression(C=1e6, max_iter=5000).fit(np.array(X).reshape(-1, 1), Y)
        calib[s] = (m.intercept_[0], m.coef_[0][0])
    recs = []
    for x in rows:
        if x["date"] < "2023-10-15":
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, bb = calib[season(x["date"])]
        rank = {h["n"]: i + 1 for i, h in enumerate(sorted(hs, key=lambda h: -h["raw"]))}
        for h, z in zip(hs, rc):
            key = (x["date"], x["race"], str(h["n"]))
            c = code_of.get(key)
            if not c:
                continue
            prev = [v for v in runs[c] if v[0] < x["date"]]
            if not prev or prev[-1][2] is None:
                continue
            sent = prev[-1][2]
            cats = [k for k, pat in CATS.items() if re.search(pat, sent)]
            y = int(h["pos"] <= 3); p = 1 / (1 + np.exp(-(a + bb * z)))
            recs.append(dict(s=season(x["date"]), y=y, p=p, rank=rank[h["n"]], odds=odds_of.get(key), cats=cats))
    print(f"馬次 {len(recs)}（上仗有事件報告覆蓋）")

    def line(name, rs):
        if len(rs) < 30:
            return f"{name}: n={len(rs)}"
        y = np.array([r["y"] for r in rs]); p = np.array([r["p"] for r in rs])
        boots = [np.mean((y - p)[np.random.randint(0, len(y), len(y))]) for _ in range(500)]
        return (f"{name}: n={len(rs)} 實際 {100*y.mean():.1f}% 預測 {100*p.mean():.1f}% 殘差 {100*(y-p).mean():+.1f}pp "
                f"[{100*np.percentile(boots,2.5):+.1f},{100*np.percentile(boots,97.5):+.1f}]")
    np.random.seed(0)
    for win, cond in (("揀選 23/24–24/25", lambda r: r["s"] <= 2024), ("確認 25/26 起", lambda r: r["s"] >= 2025)):
        print(f"\n== {win}")
        base = [r for r in recs if cond(r)]
        print(line("全部", base))
        for k in list(CATS) + ["冇任何類別"]:
            sub = [r for r in base if (k in r["cats"]) or (k == "冇任何類別" and not r["cats"])]
            print(" ", line(k, sub))
            print("     我哋排 5+ ", line("", [r for r in sub if r["rank"] >= 5]))
            print("     賠率≥10  ", line("", [r for r in sub if (r["odds"] or 0) >= 10]))


if __name__ == "__main__":
    main()
