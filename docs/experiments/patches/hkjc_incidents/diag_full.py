"""EXP-20261115-22 跟進：全語料（2019-09 起）上仗事件報告 → 今仗殘差。舊格式由 parse_old.py；2023-10 起照 diag.py 用索引。
殘差 = 入頭三 − p，p 用之前季校準（live dump）。逐季列殘差同類別命中率（檢查新舊格式一致）。
用法：python3 diag_full.py <live dump> <old_incidents.json>
"""
import json
import re
import sys
from collections import defaultdict

import numpy as np
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, "/Users/imac/Antigravity-repo/.agents/skills/hkjc_racing/hkjc_reflector/scripts")
from diag import CATS, season  # noqa: E402

CUT = "2023-10-15"


def load_runs(old_path):
    """code -> [(date, race, sentence or None, horse_no)]，按日期排序。"""
    import hkjc_history_replay_build as b
    idx = b.load_index()
    old = json.load(open(old_path))
    runs = defaultdict(list)
    for (d, n), race in idx["results"].items():
        if d < CUT:
            o = old.get(f"{d}|{n}")
            inc = None if o is None else o
        else:
            inc = b._incident_by_horse(race.get("incident_report") or "") if race.get("incident_report") else None
        for row in race.get("results", []):
            m = re.search(r"\(([A-Z]\d{3})\)", str(row.get("horse_name") or ""))
            if not m or not b._started(row):
                continue
            runs[m.group(1)].append((d, n, None if inc is None else inc.get(m.group(1), ""), str(row.get("horse_no"))))
    for v in runs.values():
        v.sort()
    return runs


def calibrate(rows):
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
    return calib


def prev_cats(runs, code_of, x, h):
    c = code_of.get((x["date"], x["race"], str(h["n"])))
    if not c:
        return None
    prev = [v for v in runs[c] if v[0] < x["date"]]
    if not prev or prev[-1][2] is None:
        return None
    return [k for k, pat in CATS.items() if re.search(pat, prev[-1][2])]


def main():
    runs = load_runs(sys.argv[2])
    code_of = {(d, n, hn): c for c, v in runs.items() for d, n, _, hn in v}
    rows = [x for x in map(json.loads, open(sys.argv[1])) if "horses" in x]
    calib = calibrate(rows)
    recs = []
    for x in rows:
        s = season(x["date"])
        if s < 2020:
            continue
        hs = [h for h in x["horses"] if h["pos"]]
        r = np.array([h["raw"] for h in hs]); rc = r - r.mean()
        a, bb = calib[s]
        for h, z in zip(hs, rc):
            cats = prev_cats(runs, code_of, x, h)
            if cats is None:
                continue
            recs.append(dict(s=s, y=int(h["pos"] <= 3), p=1 / (1 + np.exp(-(a + bb * z))), cats=cats))
    print(f"馬次 {len(recs)}")
    np.random.seed(0)
    seasons = sorted({r["s"] for r in recs})
    print("類別 " + " ".join(f"{s}" for s in seasons) + "  ｜dev(20–23) holdout(24–25)")
    for k in list(CATS) + ["冇任何類別"]:
        cells = []
        for s in seasons:
            sub = [r for r in recs if r["s"] == s and ((k in r["cats"]) or (k == "冇任何類別" and not r["cats"]))]
            allr = [r for r in recs if r["s"] == s]
            e = np.mean([r["y"] - r["p"] for r in sub]) if sub else np.nan
            cells.append(f"{100*e:+.1f}({100*len(sub)/len(allr):.0f}%)")
        out = []
        for lo, hi in ((2020, 2023), (2024, 2025)):
            sub = [r for r in recs if lo <= r["s"] <= hi and ((k in r["cats"]) or (k == "冇任何類別" and not r["cats"]))]
            y = np.array([r["y"] - r["p"] for r in sub])
            bt = [y[np.random.randint(0, len(y), len(y))].mean() for _ in range(400)]
            out.append(f"{100*y.mean():+.1f}[{100*np.percentile(bt,2.5):+.1f},{100*np.percentile(bt,97.5):+.1f}] n={len(y)}")
        print(k, " ".join(cells), "｜", " ".join(out))


if __name__ == "__main__":
    main()
